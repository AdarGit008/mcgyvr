"""Every shell script under ``gate-scripts/`` passes ``shellcheck -S error``.

``bash`` runs a script that shellcheck calls an error, so no other test sees
one: ``"$HOSTS_JSON[$RUN_HOST]"`` expands ``$HOSTS_JSON`` and keeps the
brackets as text, and the message reads the same either way. A caller that
holds the script to shellcheck refuses it all the same, so the script is held
to it here, where the script lives.

Only the error level is held. The notes and warnings shellcheck raises below
it are left to each script's author. With no shellcheck on PATH the test
skips.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE_SCRIPTS = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts"
SCRIPTS = sorted(GATE_SCRIPTS.glob("*.sh"))

needs_shellcheck = pytest.mark.skipif(
    shutil.which("shellcheck") is None,
    reason="the check under test is a real shellcheck",
)


def test_there_are_shell_scripts_to_check() -> None:
    assert SCRIPTS, f"no *.sh under {GATE_SCRIPTS}"


@needs_shellcheck
@pytest.mark.parametrize("script", SCRIPTS, ids=[path.name for path in SCRIPTS])
def test_the_script_passes_shellcheck_at_error_level(script: Path) -> None:
    done = subprocess.run(
        ["shellcheck", "-S", "error", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
