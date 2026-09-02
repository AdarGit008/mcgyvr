"""Step 7 of srv1-kernel-arms runs through the door as its own step file.

RUN-ORDER.md runs ``4-kernel-arms.sh`` twice: ``--step serve`` (invocation 5,
creates ``srv1-lcpp-arms.tsv``) and, three steps later, ``--step crash``
(invocation 8, only APPENDS to step 6's ``srv1-moe-slots.tsv``). One file
declared ``# RUN_ARTIFACTS: srv1-lcpp-arms.tsv`` for both, so gate 5 refused
invocation 8 the moment invocation 5 had run — the only way through was to
move step 5's evidence aside by hand, the waiver the door exists to end.

So the crash study is ``7-crash.sh``, a step file of its own that declares
only ``# RUN_APPENDS: srv1-moe-slots.tsv`` and hands off to
``4-kernel-arms.sh --step crash``; the door exports ``RUN_STEP`` (the step it
started) and ``4-kernel-arms.sh`` refuses a ``--step`` that is not the one it
was started as, and ``--step all`` outright: one door invocation, one file.

Seams: the ``tests/onedoor.py`` stubs; the real campaign copied into the
fixture; ``--dry-run`` so nothing is launched.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests import onedoor

CAMPAIGN = "srv1-kernel-arms"


def _door_shaped(run_id: str, *extra: str) -> str:
    lines = [
        "### WORKLOAD digest=2f2bb7932a0b660653def819 driver=tools/runs/workload.py",
        f"### START uptime_since={onedoor.UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
        "pl1_source=constraint_0_power_limit_uw cpu_max_mhz=4600 ram_mt_s=3600 "
        f"run_id={run_id}",
        f"### ROUND id={onedoor.ROUND_ID} product_sha256={onedoor.PRODUCT_SHA256}",
        *extra,
        f"### END uptime_since={onedoor.UPTIME} pl1_uw=95000000 pl2_uw=120000000 "
        "cpu_max_mhz=4600 ram_mt_s=3600",
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    shutil.copytree(
        onedoor.KERNEL_ARMS, repo / "tools" / "runs" / "campaigns" / CAMPAIGN
    )
    out_dir = onedoor.envelope(repo, CAMPAIGN)
    out_dir.mkdir(parents=True)
    # What a green invocation 5 (serve) and invocation 7 (step 6) leave behind.
    (out_dir / "srv1-lcpp-arms.tsv").write_text(
        _door_shaped(f"{onedoor.RUN_DATE}-{CAMPAIGN}-kernel-arms"), encoding="utf-8"
    )
    (out_dir / "srv1-moe-slots.tsv").write_text(
        _door_shaped(
            f"{onedoor.RUN_DATE}-{CAMPAIGN}-moe-slots",
            "### INSTRUMENT step=6 behaviour=10 driver=tools/breadth/measure.py",
        ),
        encoding="utf-8",
    )
    return repo


@pytest.fixture
def env(root: Path, tmp_path: Path) -> dict[str, str]:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    return onedoor.door_env(root, stubs)


def test_the_door_lists_crash_as_a_step_of_the_campaign(
    root: Path, env: dict[str, str]
) -> None:
    result = onedoor.door(root, [CAMPAIGN], env)
    assert result.returncode == 2, result.stderr
    assert "7-crash" in result.stderr, result.stderr


def test_the_crash_step_passes_gate_5_after_serve_has_written_its_file(
    root: Path, env: dict[str, str]
) -> None:
    result = onedoor.door(
        root, [CAMPAIGN, "crash", "--host", "srv1", "--", "--dry-run"], env
    )
    assert result.returncode != 2, (result.stdout, result.stderr)
    assert "written once" not in result.stderr, result.stderr
    assert "step 7 (crash)" in result.stdout, (result.stdout, result.stderr)
    assert "srv1-moe-slots.tsv" in result.stdout, result.stdout


@pytest.mark.parametrize("mode", ["crash", "all"])
def test_kernel_arms_refuses_a_step_it_was_not_started_as(
    root: Path, env: dict[str, str], mode: str
) -> None:
    (onedoor.envelope(root, CAMPAIGN) / "srv1-lcpp-arms.tsv").unlink()
    result = onedoor.door(
        root,
        [CAMPAIGN, "kernel-arms", "--host", "srv1", "--", "--step", mode, "--dry-run"],
        env,
    )
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "7-crash" in result.stderr, result.stderr
    assert "step 7 (crash)" not in result.stdout, result.stdout
