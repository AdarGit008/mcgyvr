""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr.config import (
    Config,
)

if TYPE_CHECKING:  #
    from mcgyvr.contract import Contract


def _reads_the_tree(contract: Contract) -> bool:
    ""
    if not contract.is_session:
        return True
    return bool(contract.sources or contract.acceptance or contract.demonstration)


def _say_what_the_sandbox_leaves_out(repo: Path) -> list[str]:
    ""
    from mcgyvr.orchestrator import head_only_note

    note = head_only_note(repo)
    if note is None:
        return []
    print(f"note: {note}", file=sys.stderr)
    return [note]


def _sandbox_policy(config: Config | None) -> dict[str, Any]:
    ""
    if config is None:
        return {"allow_fallback": False, "network": "bridge"}
    return {
        "allow_fallback": bool(config.get("sandbox.allow_fallback", False)),
        "network": config.get("sandbox.network", "bridge"),
    }
