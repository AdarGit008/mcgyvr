"""R8 — repair is a writer and must take the same sandbox seam the other writers do.

:func:`mcgyvr.repair.repair` rewrites files in place, but its only entry point
takes a bare ``repo`` path — the one writer that cannot be handed the sandbox a
caller is already holding. Every other writer takes either a workspace path or a
:class:`~mcgyvr.sandbox.Sandbox`, so the caller mid-attempt can point it at the
workspace it already gated without re-deriving the base by hand.

The fix accepts a ``sandbox`` as the alternative to ``repo``, deriving the
workspace and its base from it the way the other writers do.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcgyvr.repair import repair
from mcgyvr.sandbox.tempdir import TempDirSandbox

UNFORMATTED = (
    "import os\n"
    "import time\n"
    "def fetch(url):\n"
    "    for _ in range( 3 ):\n"
    "        time.sleep(1)\n"
    "        return url\n"
)


def test_repair_accepts_the_sandbox_it_is_inside(repo: Path, contract: Any) -> None:
    """A caller holding a sandbox repairs in it, without re-deriving the base."""
    with TempDirSandbox(repo) as sandbox:
        target = sandbox.workspace / "src" / "pkg" / "fetch.py"
        target.write_text(UNFORMATTED)

        outcome = repair(sandbox=sandbox, contract=contract)

    assert outcome.changed, (
        f"repair did not accept a sandbox seam: {outcome.environment_issues}"
    )
    assert "src/pkg/fetch.py" in outcome.repaired
