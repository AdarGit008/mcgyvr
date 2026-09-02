"""Gate 4: one workload module, imported by every driver, digesting to the pin.

Three drivers at the repo root each carry their own copy of the workload block
— ``PROMPT_DECILES`` through ``mkprompt`` — and ``tools/bench/serving/sweep.py``
carries a fourth the repo already ruled 2.4x misleading (BRIEF "The problem
being solved"). Copies agree until one is edited; ``WORKLOAD_DIGEST``
(``tests/sweeprows.py:293``, ``2f2bb7932a0b660653def819``) is the check that
would catch that, and it is only run in CI, post-hoc, over one directory.

After the change the block lives once, in ``tools/runs/workload.py``; the
three drivers under ``tools/runs/drivers/`` import it from ``tools.runs``; the
parser (now ``tools/runs/rows.py``) digests the module to the pinned value;
and ``_common.sh``'s ``workload_stamp`` accepts the module's path, so the
``### WORKLOAD driver=`` field names the one file that generated the prompts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests import onedoor

IMPORTS_WORKLOAD = re.compile(
    r"^(from tools\.runs import workload\b|from tools\.runs\.workload import\b)",
    re.MULTILINE,
)


def test_the_workload_module_exists_and_digests_to_the_pin() -> None:
    assert onedoor.WORKLOAD_PY.is_file(), "tools/runs/workload.py does not exist"
    rows = onedoor.rows_module()
    assert rows.WORKLOAD_DIGEST == "2f2bb7932a0b660653def819"
    got = rows.workload_digest(onedoor.WORKLOAD_PY)
    assert got == rows.WORKLOAD_DIGEST, (
        f"tools/runs/workload.py generates workload {got}, not "
        f"{rows.WORKLOAD_DIGEST}; every comparison in the campaign is void"
    )


def test_the_shim_and_the_module_expose_one_digest() -> None:
    """``tests/sweeprows.py`` becomes a shim over ``tools/runs/rows.py``; the
    twelve behaviour tests keep importing it and must see the same constant."""
    from tests import sweeprows

    rows = onedoor.rows_module()
    assert sweeprows.WORKLOAD_DIGEST == rows.WORKLOAD_DIGEST
    assert sweeprows.workload_digest(onedoor.WORKLOAD_PY) == rows.WORKLOAD_DIGEST


@pytest.mark.parametrize("name", onedoor.DRIVER_NAMES)
def test_every_driver_imports_the_workload_and_defines_none_of_it(name: str) -> None:
    path = onedoor.DRIVERS / name
    assert path.is_file(), f"{path.relative_to(onedoor.REPO)} does not exist"
    source = path.read_text(encoding="utf-8")
    assert IMPORTS_WORKLOAD.search(source), (
        f"{name} does not import workload from tools.runs "
        "(`from tools.runs import workload`)"
    )
    for symbol in ("PROMPT_DECILES", "COMPL_DECILES", "SYSTEM", "def mkprompt"):
        assert not re.search(rf"^{re.escape(symbol)}\b", source, re.MULTILINE), (
            f"{name} still defines {symbol}: a second copy of the workload"
        )


def test_workload_stamp_accepts_the_module_path(tmp_path: Path) -> None:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.bare_env(stubs, RUN_REPO=str(onedoor.REPO))
    result = onedoor.bash(
        f"set -euo pipefail\n. '{onedoor.COMMON_SH}'\n"
        "workload_stamp tools/runs/workload.py\n",
        env,
        onedoor.REPO,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "### WORKLOAD digest=2f2bb7932a0b660653def819 driver=tools/runs/workload.py"
    ), result.stdout
