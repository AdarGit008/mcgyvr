"""Sandbox policy and tree-reading helpers shared by sandbox, run and delegate."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.config import (
    Config,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract


def _reads_the_tree(contract: Contract) -> bool:
    """Whether a run of ``contract`` reads anything off the repository's HEAD.

    The note :func:`_say_what_the_sandbox_leaves_out` prints is about what a
    sandbox of HEAD holds, so it is worth reading only to a run that looks in
    it. Every run that writes a change does. A session (``chat``, ``agent``)
    writes nothing and has no target: it reads the tree only through the
    ``sources`` it names and the commands it declares. One with neither — a
    plain ``chat`` — reads nothing there, and telling it to commit files it
    never opens is noise (e2e run 3, T4). An ``agent``'s sources are read off
    HEAD, so it is told. Read off the contract and the catalog's ``session``
    flag, never a task type's name, which no consumer of the vocabulary
    spells.
    """
    if not contract.is_session:
        return True
    return bool(contract.sources or contract.acceptance or contract.demonstration)


def _say_what_the_sandbox_leaves_out(repo: Path) -> list[str]:
    """Say on stderr what a sandbox of ``repo``'s HEAD will not hold.

    Returns the note as a one-item list, or an empty one when there is
    nothing to say, for a run to carry into its result file as well.
    """
    from mcgyvr.orchestrator import head_only_note

    note = head_only_note(repo)
    if note is None:
        return []
    print(f"note: {note}", file=sys.stderr)
    return [note]


def _sandbox_policy(config: Config | None) -> dict[str, Any]:
    """What the `sandbox` block says about a sandbox beyond its mode.

    Read in one place for both paths that open one, so the floor and the climb
    cannot come to disagree about whether a missing daemon falls back or what
    network a container gets. No config is the schema's defaults: refuse
    rather than fall back, and Docker's default network.
    """
    if config is None:
        return {"allow_fallback": False, "network": "bridge"}
    return {
        "allow_fallback": bool(config.get("sandbox.allow_fallback", False)),
        "network": config.get("sandbox.network", "bridge"),
    }
