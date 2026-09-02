"""A step with no ``RUN_OUT_DIR`` has no envelope — it never falls back to the record.

Every kernel-arms step guarded itself with ``[ -n "$RUN_ID" ]`` and then
resolved its envelope as ``${RUN_OUT_DIR:-<the committed 2026-09-02 dir>}``.
``RUN_ID`` is any non-empty string, so a stale one in an operator's shell
(``export``ed once, or a driver call reproduced by hand) took a bare step
straight to the committed evidence, where steps 1/3/6/8 truncate their file
BEFORE ``round_stamp`` gets to refuse: ``srv1-vllm-arms.tsv`` went 3755 -> 249
bytes on a run that then exited 1. Twice in one session, by accident.

So ``door_required`` (``_common.sh``) refuses with exit 2 unless ``RUN_ID``,
``RUN_OUT_DIR``, ``RUN_ROUND`` and ``RUN_PRODUCT_SHA256`` are all set — the
four things only ``tools/runs/run.sh`` exports — and no step names the
recorded directory any more. Pinned against a copy of the campaign and of the
recorded envelope, never the tree.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests import onedoor

RECORDED = onedoor.REPO / "records" / "evidence" / "2026-09-02-srv1-kernel-arms"


def _digest_tree(top: Path) -> dict[str, str]:
    return {
        str(p.relative_to(top)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(top.rglob("*"))
        if p.is_file()
    }


def _steps() -> list[str]:
    return sorted(p.name for p in onedoor.KERNEL_ARMS.glob("[0-9]*-*.sh"))


@pytest.mark.parametrize("step", _steps())
def test_a_bare_step_with_a_stale_run_id_refuses_and_touches_no_record(
    tmp_path: Path, step: str
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    shutil.copytree(
        onedoor.KERNEL_ARMS, root / "tools" / "runs" / "campaigns" / "srv1-kernel-arms"
    )
    envelope = root / "records" / "evidence" / "2026-09-02-srv1-kernel-arms"
    shutil.copytree(RECORDED, envelope)
    before = _digest_tree(envelope)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    env = onedoor.bare_env(
        stubs,
        RUN_REPO=str(root),
        RUN_ID="stale-from-my-shell",
        RUN_RIG_SNAPSHOT_CMD=str(onedoor.rig_stub(stubs, "srv1")),
        RUN_SSH=str(onedoor.ssh_stub(stubs)),
        RUN_RETRY_SLEEP="0",
    )
    env["PATH"] = f"{stubs}{os.pathsep}{env['PATH']}"
    assert "RUN_OUT_DIR" not in env
    result = subprocess.run(
        [str(root / "tools" / "runs" / "campaigns" / "srv1-kernel-arms" / step)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 2, (step, result.returncode, result.stderr[-400:])
    assert "RUN_OUT_DIR" in result.stderr, (step, result.stderr[-400:])
    assert "run.sh" in result.stderr, (step, result.stderr[-400:])
    assert _digest_tree(envelope) == before, f"{step} touched the recorded envelope"
