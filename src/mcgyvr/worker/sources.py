"""The files a contract names as `sources`, read out of the workspace and handed
to a worker as text.

`read_sources` returns the content of each named source in the order the contract
states them, and it reads under the rules every read of the tree for a worker
follows: a path must stay inside the workspace (no absolute path, no `.git`
entry, no symlink crossing, no climb out of the root), no file on the way to it
may be one `holds_a_secret` recognizes, and it must be a text file the run's base
tree still has and that the orchestrator will read at its size. A source that
fails any of these raises `SourceError` naming the source and saying nothing was
sent, so the attempt is refused before a token is spent — a single unreadable
source does not silently vanish from the prompt.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mcgyvr.orchestrator.index import DEFAULT_MAX_FILE_BYTES, SkipReason, read_source
from mcgyvr.sandbox.base import holds_a_secret
from mcgyvr.scope import OutsideTreeError, inside


class SourceError(Exception):
    """A source the contract named cannot be given to the worker as text, so no
    prompt is sent. The message names the source by its position in the contract
    and its relative path, says why it was refused, and ends by stating that
    nothing was sent."""


def read_sources(workspace: Path, sources: Sequence[str]) -> tuple[str, ...]:
    """The content of each source in `sources`, in the order they were named.

    The result lines up with `sources` by position, so the index of each is what
    `SourceError` reports. The first source that cannot be read raises, before
    any content is returned; `_read` holds the rules a read follows.
    """
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
