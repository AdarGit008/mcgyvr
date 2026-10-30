"""Fetch a pinned GitHub release's archives, verified, into a private folder.

A :class:`Release` names a repository, a tag and the archives mcgyvr may take
from it, each with the size and sha256 committed in this tree. :func:`install`
makes one folder of the archives it is asked for, in this order (the
supply-chain order of the pooled-sessions design note, 7.7):

1. each archive is downloaded into a folder only this user may enter, by
   :func:`mcgyvr.serving.fetcher.fetch_one`, which resumes a partial download
   and keeps a file only when its length and sha256 are the committed ones;
2. the archives are unpacked into a fresh staging folder: no member may name
   an absolute path, climb out with ``..``, or be a link leading out of the
   folder (the tar ``data`` filter, and the same rules held to a zip by hand);
   when every member sits under one top folder, that folder is dropped, so
   the programs and their libraries land side by side;
3. on macOS the ``com.apple.quarantine`` attribute is removed from the whole
   folder (``xattr -dr``): "all downloaded files should be given a quarantine
   xattr", which sends a program through Gatekeeper's first-run check
   (https://eclecticlight.co/2019/04/15/sandboxing-makes-quarantine-flags-almost-meaningless/);
   ``-d`` deletes the named attribute and ``-r`` acts on the folder's whole
   content (https://keith.github.io/xcode-man-pages/xattr.1.html). Files this
   module downloads usually carry no flag ("Tools such as curl can skip this
   step", ibid.), so a failure to remove one is said, not fatal;
4. the programs asked for are marked executable for their owner, and a
   record of the archives and each program's sha256 is written beside them;
5. the staging folder takes the folder's name in one rename.

A folder whose record names the same archives, and whose programs still hash
as recorded, is used as it is. The pooled-sessions helper reuses this module
with a release of its own (repo, tag, archives), so nothing here is
llama.cpp's.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from mcgyvr import hostos
from mcgyvr.serving import fetcher

#: Where a release's archives are published.
DOWNLOAD_URL = "https://github.com/{repo}/releases/download/{tag}/{name}"
#: The record an installed folder keeps of what it was made from.
RECORD = ".mcgyvr-release.json"
#: The folder archives are downloaded into, beside the installed folders.
DOWNLOADS = ".downloads"
#: macOS's attribute tool, by its full path, and the attribute it removes.
XATTR = "/usr/bin/xattr"
QUARANTINE = "com.apple.quarantine"
#: How long removing the attribute may take.
XATTR_S = 60.0
#: The variable a GitHub token is read from, when one is set.
TOKEN_ENV = "GITHUB_TOKEN"
#: Bytes copied per read.
CHUNK = 1 << 20


class ReleaseError(Exception):
    """An archive could not be fetched, verified or unpacked; nothing was installed."""


@dataclass(frozen=True)
class Asset:
    """One archive of a release: its file name, length in bytes and sha256."""

    name: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class Release:
    """A pinned release: the GitHub repository (``owner/name``), the tag, and
    the archives mcgyvr takes from it."""

    repo: str
    tag: str
    assets: tuple[Asset, ...]

    def asset(self, name: str) -> Asset:
        """The archive named `name`, or :class:`ReleaseError` when it is not pinned."""
        for asset in self.assets:
            if asset.name == name:
                return asset
        raise ReleaseError(
            f"{name} is not an archive pinned for {self.repo} {self.tag}; "
            "nothing that is not pinned with its sha256 is fetched"
        )

    def url(self, name: str) -> str:
        """Where the archive `name` is downloaded from."""
        return DOWNLOAD_URL.format(repo=self.repo, tag=self.tag, name=name)


def install(
    release: Release,
    names: Sequence[str],
    folder: Path,
    *,
    executables: Iterable[str],
) -> Path:
    """Make `folder` hold the archives `names` unpacked, verified; return it.

    `executables` are the programs (named without ``.exe``) the folder must
    hold; each is marked executable and its sha256 recorded. Raises
    :class:`ReleaseError` when an archive is not pinned, cannot be fetched,
    does not hash as pinned, holds a member that would land outside the
    folder, or lacks one of the programs; the folder is then left as it was.
    """
    wanted = [release.asset(name) for name in names]
    programs = tuple(executables)
    if _current(folder, release, wanted, programs):
        return folder
    parent = folder.parent
    _private_dir(parent)
    downloads = parent / DOWNLOADS
    _private_dir(downloads)
    staging = parent / f"{folder.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    _private_dir(staging)
    try:
        for asset in wanted:
            archive = _fetch(release, asset, downloads)
            unpack(archive, staging)
        strip_quarantine(staging)
        recorded = {}
        for program in programs:
            path = staging / hostos.exe(program)
            if not path.is_file() or path.is_symlink():
                raise ReleaseError(
                    f"{', '.join(names)} holds no {hostos.exe(program)}; the "
                    "pinned archives are not what this build expects"
                )
            _mark_executable(path)
            recorded[program] = sha256_of(path)
        (staging / RECORD).write_text(
            json.dumps(
                {
                    "repo": release.repo,
                    "tag": release.tag,
                    "assets": {asset.name: asset.sha256 for asset in wanted},
                    "executables": recorded,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if folder.exists():
            shutil.rmtree(folder)
        os.replace(staging, folder)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    for asset in wanted:
        (downloads / asset.name).unlink(missing_ok=True)
    return folder


#: How much of a file is hashed at a time.
HASH_CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    """The sha256 of the file at `path`, as hex.

    Read in chunks, not by 3.11's ``hashlib.file_digest``: this module is
    shipped to rigs whose Python may be 3.9 (``mcgyvr.serving.shipped``).
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current(
    folder: Path, release: Release, wanted: list[Asset], programs: tuple[str, ...]
) -> bool:
    """Whether `folder` was made from exactly `wanted` and its programs are intact.

    The programs are hashed again, not the libraries beside them, and the
    record sits in the folder it describes: this finds an install that broke
    or was swapped, not one changed on purpose by this user, who owns the
    folder and could change the record too.
    """
    try:
        record = json.loads((folder / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(record, dict) or record.get("assets") != {
        asset.name: asset.sha256 for asset in wanted
    }:
        return False
    if (record.get("repo"), record.get("tag")) != (release.repo, release.tag):
        return False
    recorded = record.get("executables")
    if not isinstance(recorded, dict):
        return False
    for program in programs:
        path = folder / hostos.exe(program)
        try:
            if path.is_symlink() or sha256_of(path) != recorded.get(program):
                return False
        except OSError:
            return False
    return True


def _private_dir(path: Path) -> None:
    """Make `path` a folder of this user's alone (0700 where modes say so).

    :func:`mcgyvr.userdir.private_dir` refuses a link, another user's folder
    and one others may write into; then the mode is narrowed.
    """
    from mcgyvr.userdir import private_dir

    if private_dir(path, make=True) is None:
        raise ReleaseError(
            f"{path} is not a folder of this user's own (a link, another "
            "user's, or writable by others); nothing is installed"
        )
    hostos.chmod_private(path, directory=True)


def _fetch(release: Release, asset: Asset, downloads: Path) -> Path:
    """Download `asset` into `downloads`, verified by length and sha256."""
    row = fetcher.fetch_one(
        {
            "name": asset.name,
            "bytes": asset.bytes,
            "sha256": asset.sha256,
            "url": release.url(asset.name),
        },
        str(downloads),
        TOKEN_ENV,
        # Release archives are public; a token, when set, only lifts GitHub's
        # rate limit, and fetch_one never replays it to a redirect's host.
        os.environ.get(TOKEN_ENV) or None,
    )
    if row.get("state") not in fetcher.GOOD:
        raise ReleaseError(
            f"{asset.name} of {release.repo} {release.tag} was not installed: "
            f"{row.get('why') or row.get('state')}"
        )
    return downloads / asset.name


def unpack(archive: Path, into: Path) -> None:
    """Unpack the tar or zip `archive` into the folder `into`, held inside it."""
    if archive.name.endswith(".zip"):
        _unpack_zip(archive, into)
    elif archive.name.endswith((".tar.gz", ".tgz", ".tar")):
        _unpack_tar(archive, into)
    else:
        raise ReleaseError(f"{archive.name} is neither a tar nor a zip archive")


def _top(names: Iterable[str]) -> str | None:
    """The one top folder every member sits under, or None."""
    tops = set()
    for name in names:
        parts = PurePosixPath(name).parts
        if not parts:
            continue
        tops.add(parts[0] if len(parts) > 1 or name.endswith("/") else "")
    if len(tops) == 1:
        (top,) = tops
        return top or None
    return None


def _inside(name: str, top: str | None) -> str | None:
    """`name` with `top` dropped, refused when it would leave the folder."""
    if "\\" in name or name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        raise ReleaseError(f"the archive member {name!r} names an absolute path")
    parts = [part for part in PurePosixPath(name).parts if part not in ("", ".")]
    if ".." in parts:
        raise ReleaseError(f"the archive member {name!r} climbs out of its folder")
    if top is not None and parts and parts[0] == top:
        parts = parts[1:]
    return "/".join(parts) or None


def _unpack_tar(archive: Path, into: Path) -> None:
    try:
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            # A folder's own entry has its trailing slash dropped by tarfile;
            # it is given back, so the folder reads as one.
            top = _top(m.name + "/" if m.isdir() else m.name for m in members)
            # The "data" extraction filter is 3.12's (and 3.9.17's); a Python
            # without it extracts only files, folders and the links checked
            # below, and nothing else (no devices, fifos), as it would allow.
            filtered = hasattr(tarfile, "data_filter")
            for member in members:
                relative = _inside(member.name, top)
                if relative is None:
                    continue
                if not (member.isfile() or member.isdir() or member.issym()) and not (
                    member.islnk()
                ):
                    raise ReleaseError(
                        f"the archive member {member.name!r} is not a file, a "
                        "folder or a link"
                    )
                member.name = relative
                if member.issym() and (
                    member.linkname.startswith("/")
                    or ".." in PurePosixPath(member.linkname).parts
                ):
                    raise ReleaseError(
                        f"the archive link {relative!r} -> {member.linkname!r} "
                        "leads out of its folder"
                    )
                if member.islnk():
                    linked = _inside(member.linkname, top)
                    if linked is None:
                        raise ReleaseError(f"the archive link {relative!r} is empty")
                    member.linkname = linked
                if filtered:
                    tar.extract(member, into, filter="data")
                else:
                    member.mode &= 0o755
                    tar.extract(member, into)
    except (tarfile.TarError, OSError) as exc:
        raise ReleaseError(f"{archive.name} could not be unpacked: {exc}") from exc


def _unpack_zip(archive: Path, into: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as zipped:
            infos = zipped.infolist()
            top = _top(info.filename for info in infos)
            for info in infos:
                relative = _inside(info.filename, top)
                if relative is None or info.is_dir():
                    continue
                kind = (info.external_attr >> 16) & 0o170000
                if kind and not stat.S_ISREG(kind):
                    raise ReleaseError(
                        f"the archive member {info.filename!r} is not a plain file"
                    )
                target = into / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(info) as source, target.open("xb") as out:
                    shutil.copyfileobj(source, out, CHUNK)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ReleaseError(f"{archive.name} could not be unpacked: {exc}") from exc


def strip_quarantine(folder: Path) -> bool | None:
    """Remove macOS's quarantine attribute from everything under `folder`.

    None off macOS, where there is none. True when ``xattr`` exited 0; False
    otherwise, said on stderr: a folder whose files carry no flag makes
    ``xattr -d`` exit non-zero too, and a flag left on is Gatekeeper's prompt
    the first time the program runs, not a broken install.
    """
    if hostos.os_name() != hostos.DARWIN:
        return None
    try:
        done = subprocess.run(
            [XATTR, "-dr", QUARANTINE, str(folder)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=XATTR_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(
            f"release: {QUARANTINE} not removed from {folder}: {exc}", file=sys.stderr
        )
        return False
    if done.returncode != 0:
        print(
            f"release: {QUARANTINE} not removed from {folder} (xattr exited "
            f"{done.returncode}; files fetched here usually carry none): "
            f"{done.stderr.strip()[:200]}",
            file=sys.stderr,
        )
    return done.returncode == 0


def _mark_executable(path: Path) -> None:
    """Let the owner run `path`; nothing to do on Windows, which runs by extension."""
    if hostos.os_name() == hostos.WINDOWS:
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod((mode | stat.S_IXUSR) & ~(stat.S_IWGRP | stat.S_IWOTH))
