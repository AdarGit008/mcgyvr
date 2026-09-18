"""A step with no ``RUN_OUT_DIR`` has no envelope — it never falls back to the record.

A step that guards itself with ``[ -n "$RUN_ID" ]`` and resolves its envelope
as ``${RUN_OUT_DIR:-<the committed dir>}`` is one stale ``RUN_ID`` away from
the committed evidence: ``RUN_ID`` is any non-empty string, a stale one sits in
an operator's shell (``export``ed once, or a driver call reproduced by hand),
and a step that truncates its file BEFORE ``round_stamp`` gets to refuse
destroys that evidence on a run that then exits 1.

So ``door_required`` (``tools/runs/_common.sh``) refuses with exit 2 unless ``RUN_ID``,
``RUN_OUT_DIR``, ``RUN_ROUND`` and ``RUN_PRODUCT_SHA256`` are all set — the
four things only ``python -m mcgyvr.serving.run`` exports — and no step names
the recorded directory. Pinned against a copy of the campaign and of
the recorded envelope, never the tree. The steps are run BARE here, on
purpose: this is what happens outside the door.
"""

from __future__ import annotations

import hashlib
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
    env = onedoor.bare_env(
        tmp_path / "stubs",
        RUN_REPO=str(root),
        RUN_ID="stale-from-my-shell",
        RUN_RETRY_SLEEP="0",
    )
    assert "RUN_OUT_DIR" not in env
    result = subprocess.run(
        [str(root / "tools" / "runs" / "campaigns" / "srv1-kernel-arms" / step)],
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 2, (step, result.returncode, result.stderr[-400:])
    assert "RUN_OUT_DIR" in result.stderr, (step, result.stderr[-400:])
    assert "mcgyvr.serving.run" in result.stderr, (step, result.stderr[-400:])
    assert _digest_tree(envelope) == before, f"{step} touched the recorded envelope"
