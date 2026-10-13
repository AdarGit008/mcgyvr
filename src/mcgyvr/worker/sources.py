"""A contract's ``sources``, read for the worker that answers from them.

E2e run 2, R11: an ``agent`` worker was asked to cite sources it was never
given, because ``sources`` never reached its prompt. They reach it now —
numbered, whole, in the user message (:mod:`mcgyvr.worker.prompt`) — and this
module is the read, held to the rules every other read of the tree for a worker
already follows, so a source is never a way around them:

* **From the tree the run started from.** The attempt reads each source off its
  sandbox workspace, as it reads the target's own content: HEAD's tracked files
  for a git repository, so an ignored ``.env`` is not there to be named, and a
  non-git source copied minus the files that hold secrets.
* **Inside the tree.** Through :func:`mcgyvr.scope.inside`, so an absolute
  path, ``..``, a symlink and ``.git`` are refused rather than followed.
* **Not a secret.** A file the sandbox's non-git copy leaves behind for
  holding a secret (:func:`mcgyvr.sandbox.base.holds_a_secret`) — a dotenv
  file, a key, a credential folder — is refused here too, tracked or not:
  a prompt may go to a hosted API.
* **Text, and bounded.** The orchestrator's own reader
  (:func:`mcgyvr.orchestrator.index.read_source`) refuses a binary file and
  one over its size cap; the prompt's fit check then holds every source,
  whole, to the contract's ``context.max_input_tokens``. Nothing is truncated:
  a worker handed half a file is answering a question about a file it has not
  seen.

A source that cannot be given raises :class:`SourceError`, before anything is
sent, and names the source the way the contract does.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mcgyvr.orchestrator.index import DEFAULT_MAX_FILE_BYTES, SkipReason, read_source
from mcgyvr.sandbox.base import holds_a_secret
from mcgyvr.scope import OutsideTreeError, inside


class SourceError(Exception):
    """A source that cannot be given to the worker; nothing was sent."""


def read_sources(workspace: Path, sources: Sequence[str]) -> tuple[str, ...]:
    """The content of each of ``sources``, in order, read off ``workspace``."""
    return tuple(_read(workspace, index, rel) for index, rel in enumerate(sources))


def _read(workspace: Path, index: int, rel: str) -> str:
    where = f"sources.{index}: {rel!r}"

    def refused(why: str) -> SourceError:
        return SourceError(f"{where} {why}; nothing was sent")

    try:
        path = inside(workspace, rel)
    except OutsideTreeError as exc:
        raise refused(f"cannot be read: {exc}") from exc
    root = workspace.resolve()
    for held in (path, *path.parents):
        if held == root:
            break
        if holds_a_secret(held):
            raise refused(
                f"is where a secret is kept ({held.relative_to(root).as_posix()}), "
                f"and a secret is never put in a prompt"
            )
    raw = read_source(workspace, rel)
    if raw is SkipReason.GONE or not path.is_file():
        raise refused(
            "is not a file in the tree the run started from — in a git "
            "repository, HEAD's tracked files; commit it, or fix the path"
        )
    if raw is SkipReason.BINARY:
        raise refused("is binary, and a source is given to the worker as text")
    if raw is SkipReason.LARGE:
        raise refused(
            f"is over {DEFAULT_MAX_FILE_BYTES} bytes, the most of one file the "
            f"orchestrator reads"
        )
    assert isinstance(raw, bytes)
    return raw.decode("utf-8", "surrogateescape")
