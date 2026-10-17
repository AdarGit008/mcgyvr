"""The sandbox inputs the CLI commands share.

`_reads_the_tree` decides whether a contract reads the committed tree at all,
`_say_what_the_sandbox_leaves_out` prints and returns the note naming what that
tree leaves out, and `_sandbox_policy` reads the settings a run hands to the
sandbox it opens.
"""

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
    """Whether the contract's commands look at the tree the sandbox is built from.

    A session task that names no source, acceptance or demonstration command only
    stages its reply, so the tree is irrelevant to it; every other contract, and
    a session that does name one of those, reads the tree and needs to hear which
    parts of it the sandbox does not have.
    """
    if not contract.is_session:
        return True
    return bool(contract.sources or contract.acceptance or contract.demonstration)


def _say_what_the_sandbox_leaves_out(repo: Path) -> list[str]:
    """Print the note naming what the sandbox, built from HEAD, does not hold.

    `head_only_note` composes that sentence, and gives None where there is
    nothing to report: not a git repository, no uncommitted or untracked path, or
    git unable to answer. The note is written to stderr as it is found, and
    returned as a one-item list so a caller can keep it on the result; an empty
    list means there was nothing to say.
    """
    from mcgyvr.orchestrator import head_only_note

    note = head_only_note(repo)
    if note is None:
        return []
    print(f"note: {note}", file=sys.stderr)
    return [note]


def _sandbox_policy(config: Config | None) -> dict[str, Any]:
    """The `allow_fallback` and `network` a sandbox is opened with.

    With no config at all both take their defaults: no fallback to the weaker
    tempdir backend when Docker does not answer, and Docker's `bridge` network.
    Otherwise they are read from `sandbox.allow_fallback` (default off) and
    `sandbox.network` (default `bridge`), so the same policy reaches a run that
    has a setup and one that does not.
    """
    if config is None:
        return {"allow_fallback": False, "network": "bridge"}
    return {
        "allow_fallback": bool(config.get("sandbox.allow_fallback", False)),
        "network": config.get("sandbox.network", "bridge"),
    }
