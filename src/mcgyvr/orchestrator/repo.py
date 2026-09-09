"""Attach a repository — the required first input to any orchestration.

Everything the orchestrator does is judged against a repository at a known
starting revision: the index (#47) reads its files, the resolver (#48) points
at them, and delivery (E8) diffs and pushes against the revision established
here. So attach is where the two forms of input — a local checkout and a
remote URL — are collapsed into **one** internal state, and where the design
boundary "a repository is required" is enforced loudly rather than guessed
around.

Three things are settled at attach time, once, so nothing downstream has to
re-derive them or disagree:

* **The working location.** A local path is used in place; a URL is cloned to
  a working location with a *declared lifetime* — ephemeral (removed when the
  attach context closes) unless the caller names a directory it will own.
* **The starting revision.** The commit everything is judged against. A
  repository with no commit yet resolves to git's empty tree, matching the
  gate's own convention (:mod:`mcgyvr.gate.changeset`) so a first-ever change
  is attributed as wholly added rather than failing to resolve.
* **Whether the working tree is dirty.** Uncommitted changes in a local
  checkout are captured and reported *before any work begins*, because a dirty
  tree is the difference between a diff that reflects the worker and one that
  also carries the human's unfinished edits. A fresh clone is clean by
  construction.

Both input forms flow through one describe step (:func:`_describe`), so "both
reach the same internal state" is a property of the code path, not a promise
maintained in two places.
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

# The well-known SHA-1 of git's empty tree. A repository with no commit has no
# HEAD to name as its starting revision; the empty tree stands in, so an
# unborn repo attaches with a revision like any other and its whole content
# reads as added. This is the same sentinel the gate uses (changeset._EMPTY_TREE).
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# A URL with an explicit scheme: https://, ssh://, git://, file://, http://.
_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

# The scp-like short form git accepts: `git@github.com:owner/repo.git`. A host
# and a path separated by a colon, with an optional `user@`. This deliberately
# will not match a bare Windows drive path (`C:\...`) — the path part after the
# colon must not start with a backslash.
_SCP_LIKE = re.compile(r"^([\w.-]+@)?[\w.-]+:(?![\\]).+$")

# The schemes git resolves over ssh. With the scp-like form above, these are
# every input that makes `git clone` spawn `ssh` from PATH — which would be the
# only ssh spawn in the product outside the rig door
# (mcgyvr.serving.gatelib.ssh). All of them are refused before git is run.
_SSH_SCHEME = re.compile(r"^(?:ssh|git\+ssh|ssh\+git)://", re.IGNORECASE)

_SSH_REFUSED = (
    "an ssh remote is refused: nothing in mcgyvr opens ssh except the rig "
    "door; use https://, git://, file:// or a local path"
)


class AttachError(Exception):
    """A repository could not be attached.

    Raised loudly and early: no repository supplied, an input that is neither a
    checkout nor a URL, a local path that is not a git repository, or a clone
    that failed. The message always names what to supply or fix — attach never
    guesses a repository into existence.
    """


@dataclass(frozen=True)
class AttachedRepo:
    """A repository ready to orchestrate against, at a known revision.

    Both a local checkout and a freshly cloned URL produce this same state.
    Instances are immutable; the working tree they point at is not, but every
    fact recorded here (``revision``, ``dirty``) is a snapshot taken at attach.
    """

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
        """Whether the working tree had uncommitted changes at attach."""
        return bool(self.dirty)

    @property
    def is_unborn(self) -> bool:
        """Whether the repository had no commit, so ``revision`` is the empty tree."""
        return self.revision == _EMPTY_TREE


@contextmanager
def attach(source: str | None, *, into: Path | None = None) -> Iterator[AttachedRepo]:
    """Attach ``source`` and yield the repository for the duration of the block.

    ``source`` is either a path to a local git checkout or a URL git can clone
    without opening an ssh (``https://``, ``git://``, ``file://``). An ssh
    remote — ``ssh://``, ``git+ssh://``, or the scp-like ``git@host:owner/repo``
    and ``host:path`` forms — is refused before git runs: nothing in mcgyvr
    opens ssh except the rig door. A path that exists is used in place; a URL
    is cloned.

    ``into`` names where a clone lands and declares its lifetime. Omitted, a
    clone goes to an ephemeral temp directory removed when this context closes.
    Given a directory, the clone lands there and is left for the caller to own —
    ``into`` is ignored for a local checkout, which is never copied.

    Raises :class:`AttachError` — before yielding — when nothing is supplied,
    when the input is neither a checkout nor a clonable URL, when a local path
    is not a git repository, or when a clone fails. This is the "a repository is
    required" boundary: attach fails loud rather than proceeding without one.
    """
    if source is None or not source.strip():
        raise AttachError(
            "no repository supplied: pass a path to a local git checkout "
            "or a URL to clone"
        )
    supplied = source.strip()

    local = _as_local_dir(supplied)
    if local is not None:
        # A checkout used in place: nothing to tear down, `into` does not apply.
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
    """The source as an existing local directory, or None if it is not one.

    A path that exists but is a file is a caller error, not a URL to try, so it
    is rejected here with a message rather than falling through to a confusing
    "not a URL" further down.
    """
    path = Path(source)
    if path.is_dir():
        return path
    if path.exists():
        raise AttachError(f"{source!r} is a file, not a repository directory")
    return None


def _looks_remote(source: str) -> bool:
    """Whether ``source`` is shaped like a URL git could clone.

    Shape only: an ssh remote is shaped like one and is still refused, by
    :func:`_ssh_form`, which :func:`attach` consults first.
    """
    return bool(_URL_SCHEME.match(source) or _SCP_LIKE.match(source))


def _ssh_form(source: str) -> str | None:
    """How ``source`` would make git open an ssh, or None if it would not.

    A scheme is decisive when present: ``ssh://`` and ``git+ssh://`` are ssh,
    ``https://``/``git://``/``file://`` are not. Without a scheme, the scp-like
    ``[user@]host:path`` form is ssh — git never names the transport, it just
    spawns ``ssh`` from PATH.
    """
    if _URL_SCHEME.match(source):
        return "an ssh:// URL" if _SSH_SCHEME.match(source) else None
    if _SCP_LIKE.match(source):
        return "the scp-like host:path form, which git clones over ssh"
    return None


def _attach_local(path: Path, source: str) -> AttachedRepo:
    """Describe a local checkout, normalising a subdirectory to the repo root.

    ``git rev-parse --show-toplevel`` both validates that the path is inside a
    git repository and yields its canonical root, so being handed a
    subdirectory attaches the whole repository rather than a fragment of it.
    """
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
    """Clone ``source`` and yield it, tearing an ephemeral clone down after.

    A generator so the caller's ``with`` block brackets the clone's lifetime:
    an ephemeral clone (``into`` omitted) is removed on exit; a clone into a
    caller-named directory is left in place.
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
    """Clone ``source`` into ``dest`` (which must be empty), failing loud.

    ``--`` guards against a source that begins with a dash being read as a
    flag; the error carries git's own stderr so a bad URL or an unreachable
    host is reported as what it is.
    """
    proc = subprocess.run(
        ["git", "clone", "--quiet", "--", source, str(dest)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise AttachError(f"could not clone {source!r}: {detail}")


def _describe(root: Path, *, source: str, origin: str, ephemeral: bool) -> AttachedRepo:
    """The one path both input forms flow through to reach identical state."""
    return AttachedRepo(
        root=root,
        revision=_revision(root),
        source=source,
        origin=origin,
        ephemeral=ephemeral,
        dirty=_dirty_paths(root),
    )


def _revision(root: Path) -> str:
    """The HEAD commit, or the empty-tree sentinel for an unborn repository.

    An unborn repository (``git init`` with no commit) has no HEAD to name;
    rather than fail, it resolves to the empty tree so it attaches like any
    other and its whole content reads as added downstream.
    """
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    revision = proc.stdout.strip()
    return revision if proc.returncode == 0 and revision else _EMPTY_TREE


def _dirty_paths(root: Path) -> tuple[str, ...]:
    """Paths with uncommitted changes, read from ``status --porcelain -z``.

    ``-z`` makes the output NUL-delimited, so a filename with spaces or
    non-ASCII bytes is carried through verbatim rather than quoted — the same
    quoting hazard :mod:`mcgyvr.gate.changeset` guards against. Each record is
    a two-character status followed by the path; renames (``R``) carry an extra
    NUL-delimited origin path, which is skipped.
    """
    raw = _git(root, "status", "--porcelain", "-z").encode("utf-8", "surrogateescape")
    tokens = raw.split(b"\x00")
    paths: list[str] = []
    i = 0
    while i < len(tokens):
        record = tokens[i]
        if not record:  # trailing NUL leaves an empty final token
            break
        status = record[:2]
        path = record[3:]  # skip the two status chars and the separating space
        paths.append(path.decode("utf-8", "surrogateescape"))
        # A rename/copy record is followed by its origin path as its own token.
        if status[:1] in (b"R", b"C"):
            i += 2
        else:
            i += 1
    return tuple(paths)


def _git(root: Path, *args: str, on_error: str | None = None) -> str:
    """Run a git command in ``root``, returning stdout as text.

    ``on_error`` overrides the message when the command fails — used to turn
    "rev-parse failed" into "not a git repository", which is the actionable
    thing the caller needs to hear.
    """
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
