""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from mcgyvr.orchestrator.index import DEFAULT_MAX_FILE_BYTES, SkipReason, read_source
from mcgyvr.sandbox.base import holds_a_secret
from mcgyvr.scope import OutsideTreeError, inside


class SourceError(Exception):
    ""


def read_sources(workspace: Path, sources: Sequence[str]) -> tuple[str, ...]:
    ""
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
