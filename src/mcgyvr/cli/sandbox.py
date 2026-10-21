"""The sandbox inputs the CLI commands share.

`_say_what_the_sandbox_leaves_out` prints and returns the note naming what the
committed tree a sandbox is built from leaves out, and `_sandbox_policy` reads
the settings a run hands to the sandbox it opens.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcgyvr.config import (
    Config,
)


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
