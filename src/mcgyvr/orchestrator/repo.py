"""Attach the orchestrator to a git repository.

``attach`` resolves a caller-supplied source — a local checkout or a clonable
URL — into an :class:`AttachedRepo`, which records the repository root, the
revision everything downstream is judged against, how the repository was
obtained, whether the root is temporary, and the paths that were dirty at
attach time. ssh remotes are refused: nothing here opens an ssh connection.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

# The object id of git's empty tree. Used as the revision sentinel for a
# repository with no commits yet: `git rev-parse HEAD^{commit}` fails there,
# and the empty tree is the only revision such a repository can be compared
# against.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# Matches a leading ``scheme://``, which is how a string is recognised as a URL
# rather than a filesystem path.
_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

# Matches git's scp-like ``[user@]host:path`` form. git clones that form over
# ssh, so it is recognised here in order to be refused rather than cloned.
# The negative lookahead requires the character after the colon not to be a
# backslash, so a Windows drive path such as ``C:\src`` is not a remote.
_SCP_LIKE = re.compile(r"^([\w.-]+@)?[\w.-]+:(?![\\]).+$")

# The URL schemes that carry git over ssh, matched case-insensitively: a
# source matching this is refused before any clone is attempted, and
# ``git+ssh://`` and ``ssh+git://`` are alternative spellings of the same
# transport, so all three are treated alike.
_SSH_SCHEME = re.compile(r"^(?:ssh|git\+ssh|ssh\+git)://", re.IGNORECASE)

_SSH_REFUSED = (
    "an ssh remote is refused: nothing in mcgyvr opens ssh except the rig "
    "door; use https://, git://, file:// or a local path"
)


class AttachError(Exception):
    """A source could not be attached: it was blank, missing, not a git
    checkout, not a clonable URL, or an ssh remote."""


@dataclass(frozen=True)
class AttachedRepo:
    """A repository the orchestrator has attached to, together with the
    revision and working-tree state it started from. Frozen: an instance
    describes a moment rather than a live handle."""

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
        """Whether any path had uncommitted changes at attach time."""
        return bool(self.dirty)

    @property
    def is_unborn(self) -> bool:
        """Whether the repository had no commit at attach time, so the
        revision is the empty-tree sentinel."""
        return self.revision == _EMPTY_TREE


@contextmanager
def attach(source: str | None, *, into: Path | None = None) -> Iterator[AttachedRepo]:
    """Attach to the repository named by ``source`` and yield its descriptor.

    An existing directory is used in place. A URL — https://, git://, file://
    or the scp-like ``host:path`` form — is cloned into ``into`` when given,
    otherwise into a fresh temporary directory that is removed when the context
    exits. ssh remotes are refused, as is a source that is neither an existing
    directory nor a clonable URL, and a blank or missing source.
    """
    if source is None or not source.strip():
        raise AttachError(
            "no repository supplied: pass a path to a local git checkout "
            "or a URL to clone"
        )
    supplied = source.strip()

    local = _as_local_dir(supplied)
    if local is not None:
        # An existing directory is attached in place: nothing is cloned and
        # nothing is cleaned up afterwards.
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
    """Return ``source`` as a directory path when it names one, None when it
    names nothing that exists on disk, and raise AttachError when it names
    something that is not a directory."""
    path = Path(source)
    if path.is_dir():
        return path
    if path.exists():
        raise AttachError(f"{source!r} is a file, not a repository directory")
    return None


def _looks_remote(source: str) -> bool:
    """Whether ``source`` has a URL scheme or the scp-like form, i.e. whether
    it is a candidate for cloning."""
    return bool(_URL_SCHEME.match(source) or _SCP_LIKE.match(source))


def _ssh_form(source: str) -> str | None:
    """Name the ssh form ``source`` would be cloned over, or None when it is
    not ssh. A URL with an ssh scheme is reported as such; a scp-like
    ``host:path`` is reported because git clones that form over ssh."""
    if _URL_SCHEME.match(source):
        return "an ssh:// URL" if _SSH_SCHEME.match(source) else None
    if _SCP_LIKE.match(source):
        return "the scp-like host:path form, which git clones over ssh"
    return None


def _attach_local(path: Path, source: str) -> AttachedRepo:
    """Describe ``path`` as a checkout used in place, resolving the repository
    toplevel so that a subdirectory input still yields the root."""
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
    """Clone ``source`` and yield the descriptor of the clone.

    The clone goes into ``into``, created if absent and left in place, or into
    a new temporary directory when ``into`` is None — in that case the clone is
    ephemeral and the directory is removed when the generator is closed, which
    happens when the ``attach`` context exits.
    """
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
    """Run ``git clone`` of ``source`` into ``dest``, raising AttachError with
    git's own error text when the clone fails."""
    proc = subprocess.run(
        ["git", "clone", "--quiet", "--", source, str(dest)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise AttachError(f"could not clone {source!r}: {detail}")


def _describe(root: Path, *, source: str, origin: str, ephemeral: bool) -> AttachedRepo:
    """Build the AttachedRepo for ``root`` by reading its starting revision and
    its dirty paths."""
    return AttachedRepo(
        root=root,
        revision=_revision(root),
        source=source,
        origin=origin,
        ephemeral=ephemeral,
        dirty=_dirty_paths(root),
    )


def _revision(root: Path) -> str:
    """Return the commit HEAD resolves to, or the empty-tree sentinel when the
    repository has no commit yet or HEAD cannot be resolved."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    revision = proc.stdout.strip()
    return revision if proc.returncode == 0 and revision else _EMPTY_TREE


def head_only_note(root: Path) -> str | None:
    """Warn that the sandbox is built from a commit, so the working tree's
    uncommitted and untracked paths will not be in it — or None when there is
    nothing to warn about.

    None is returned when ``root`` is not a checkout (no ``.git``), when the
    tree is clean, and when git cannot be read.
    """
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
    # Name only the first few paths and count the rest, so the note stays
    # readable however much of the tree is dirty.
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
    """Return the paths git reports as changed or untracked, in git's order.

    Parses the NUL-separated ``--porcelain -z`` output, so paths containing
    spaces or quotes come back verbatim.
    """
    raw = _git(root, "status", "--porcelain", "-z").encode("utf-8", "surrogateescape")
    tokens = raw.split(b"\x00")
    paths: list[str] = []
    i = 0
    while i < len(tokens):
        record = tokens[i]
        if not record:  # the trailing NUL leaves an empty token
            break
        status = record[:2]
        path = record[3:]  # two status columns, one space, then the path
        paths.append(path.decode("utf-8", "surrogateescape"))
        # A rename or copy record is followed by the original path as a
        # separate token; skip it so only the current path is reported.
        if status[:1] in (b"R", b"C"):
            i += 2
        else:
            i += 1
    return tuple(paths)


def _git(root: Path, *args: str, on_error: str | None = None) -> str:
    """Run git with ``args`` inside ``root`` and return its stdout, raising
    AttachError carrying ``on_error`` — or a generic message naming the
    subcommand — when git exits non-zero."""
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
