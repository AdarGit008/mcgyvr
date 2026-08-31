"""D8 — a repair subprocess that hangs must be cut off, not hang forever.

Repair runs two ruff subprocesses with no timeout: a ruff that does not return
— a stuck daemon, a pathological file — hangs the whole repair and, with it,
the attempt loop it was meant to make cheaper. The fix bounds each subprocess
and records a timeout as an environment issue, the way a missing ruff is.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.contract import loads
from mcgyvr.repair import repair
from tests.red_port.conftest import git

UNFORMATTED = (
    "import os\n"
    "import time\n"
    "def fetch(url):\n"
    "    for _ in range( 3 ):\n"
    "        time.sleep(1)\n"
    "        return url\n"
)

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""


def test_a_hung_ruff_is_an_environment_issue_not_a_hang(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ruff that never returns is reported; repair does not wait for it."""
    contract: Any = loads(CONTRACT)
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / "src" / "pkg" / "fetch.py").write_text(UNFORMATTED)

    real_run = subprocess.run

    def hung(cmd: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(cmd, (list, tuple)) and cmd and str(cmd[0]).endswith("ruff"):
            raise subprocess.TimeoutExpired(cmd, 120.0)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", hung)

    outcome = repair(repo=repo, contract=contract, base=base)

    assert any("timed out" in issue.lower() for issue in outcome.environment_issues), (
        f"a hung ruff was not reported as an environment issue: "
        f"{outcome.environment_issues}"
    )
