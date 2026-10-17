""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

#
#
#
#
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

#
_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

#
#
#he
#
_SCP_LIKE = re.compile(r"^([\w.-]+@)?[\w.-]+:(?![\\]).+$")

#
#he
#
#
_SSH_SCHEME = re.compile(r"^(?:ssh|git\+ssh|ssh\+git)://", re.IGNORECASE)

_SSH_REFUSED = (
    "an ssh remote is refused: nothing in mcgyvr opens ssh except the rig "
    "door; use https://, git://, file:// or a local path"
)


class AttachError(Exception):
    ""


@dataclass(frozen=True)
class AttachedRepo:
    ""

    root: Path
    """The repository root — a canonical, absolute path. For a clone this is
    the working location; for a local checkout it is the toplevel even when a
    subdirectory was supplied."""

    revision: str
    """The starting revision everything downstream is judged against: the
    resolved HEAD commit, or the empty-tree sentinel for an unborn repository."""

    source: str
    """The input exactly as supplied — a path or a URL. Kept for messages so a
    failure or a report names what the caller actually passed."""

    origin: str
    """How the repository was obtained: ``"local"`` for a checkout used in
    place, ``"clone"`` for a URL cloned to a working location."""

    ephemeral: bool
    """Whether ``root`` is removed when the attach context closes. True for a
    clone into a temp location; False for a local checkout or a clone into a
    caller-owned directory."""

    dirty: tuple[str, ...]
    """Paths with uncommitted changes at attach time, in git's report order.
    Empty for a clean tree and, by construction, for a fresh clone."""

    @property
    def is_dirty(self) -> bool:
        ""
        return bool(self.dirty)

    @property
    def is_unborn(self) -> bool:
        ""
        return self.revision == _EMPTY_TREE


@contextmanager
def attach(source: str | None, *, into: Path | None = None) -> Iterator[AttachedRepo]:
    ""
    if source is None or not source.strip():
        raise AttachError(
            "no repository supplied: pass a path to a local git checkout "
            "or a URL to clone"
        )
    supplied = source.strip()

    local = _as_local_dir(supplied)
    if local is not None:
        #
        yield _attach_local(local, supplied)
        return

    ssh_form = _ssh_form(supplied)
    if ssh_form is not None:
        raise AttachError(f"{supplied!r} is {ssh_form}: {_SSH_REFUSED}")

    if _looks_remote(supplied):
        yield from _attach_clone(supplied, into)
        return

    raise AttachError(
        f"{supplied!r} is neither an existing directory nor a clonable URL: "
        "pass a path to a local git checkout, or an https://, git:// or "
        "file:// URL (an ssh remote is refused)"
    )


def _as_local_dir(source: str) -> Path | None:
    ""
    path = Path(source)
    if path.is_dir():
        return path
    if path.exists():
        raise AttachError(f"{source!r} is a file, not a repository directory")
    return None


def _looks_remote(source: str) -> bool:
    ""
    return bool(_URL_SCHEME.match(source) or _SCP_LIKE.match(source))


def _ssh_form(source: str) -> str | None:
    ""
    if _URL_SCHEME.match(source):
        return "an ssh:// URL" if _SSH_SCHEME.match(source) else None
    if _SCP_LIKE.match(source):
        return "the scp-like host:path form, which git clones over ssh"
    return None


def _attach_local(path: Path, source: str) -> AttachedRepo:
    ""
    toplevel = _git(
        path,
        "rev-parse",
        "--show-toplevel",
        on_error=(
            f"{source!r} is not a git repository: the orchestrator needs a "
            "starting revision, so a local path must be a git checkout"
        ),
    ).strip()
    root = Path(toplevel).resolve()
    return _describe(root, source=source, origin="local", ephemeral=False)


def _attach_clone(source: str, into: Path | None) -> Iterator[AttachedRepo]:
    ""
    ephemeral = into is None
    if into is not None:
        dest = into.resolve()
        dest.mkdir(parents=True, exist_ok=True)
    else:
        dest = Path(tempfile.mkdtemp(prefix="mcgyvr-attach-")).resolve()

    try:
        _clone(source, dest)
        repo = _describe(dest, source=source, origin="clone", ephemeral=ephemeral)
        yield repo
    finally:
        if ephemeral:
            shutil.rmtree(dest, ignore_errors=True)


def _clone(source: str, dest: Path) -> None:
    ""
    proc = subprocess.run(
        ["git", "clone", "--quiet", "--", source, str(dest)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise AttachError(f"could not clone {source!r}: {detail}")


def _describe(root: Path, *, source: str, origin: str, ephemeral: bool) -> AttachedRepo:
    ""
    return AttachedRepo(
        root=root,
        revision=_revision(root),
        source=source,
        origin=origin,
        ephemeral=ephemeral,
        dirty=_dirty_paths(root),
    )


def _revision(root: Path) -> str:
    ""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    revision = proc.stdout.strip()
    return revision if proc.returncode == 0 and revision else _EMPTY_TREE


def head_only_note(root: Path) -> str | None:
    ""
    if not (root / ".git").exists():
        return None
    try:
        dirty = _dirty_paths(root)
        if not dirty:
            return None
        revision = _revision(root)
        base = (
            "no commit (the repository has none yet)"
            if revision == _EMPTY_TREE
            else f"commit {_git(root, 'rev-parse', '--short', revision).strip()}"
        )
    except AttachError:
        return None
    #
    #
    shown = 3
    named = ", ".join(dirty[:shown])
    more = len(dirty) - shown
    if more > 0:
        named += f" (+{more} more)"
    return (
        f"the sandbox is built from {base}; {len(dirty)} uncommitted or "
        f"untracked path(s) are not in it: {named}. Commit them if the "
        f"contract's commands need them."
    )


def _dirty_paths(root: Path) -> tuple[str, ...]:
    ""
    raw = _git(root, "status", "--porcelain", "-z").encode("utf-8", "surrogateescape")
    tokens = raw.split(b"\x00")
    paths: list[str] = []
    i = 0
    while i < len(tokens):
        record = tokens[i]
        if not record:  #
            break
        status = record[:2]
        path = record[3:]  #
        paths.append(path.decode("utf-8", "surrogateescape"))
        #
        if status[:1] in (b"R", b"C"):
            i += 2
        else:
            i += 1
    return tuple(paths)


def _git(root: Path, *args: str, on_error: str | None = None) -> str:
    ""
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip()
        raise AttachError(on_error or f"git {args[0]} failed: {detail}")
    return proc.stdout
