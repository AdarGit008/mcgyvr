"""Meta-loop gate (RED).

This repo must be baseline-green AND its dependencies green. This test is the
health contract that drives compliance. It is RED until baseline reports 0
blockers for this repo.
"""
import json
import os
import subprocess
from pathlib import Path


def _baseline_checker() -> Path:
    env = os.environ.get("META_BASELINE_CHECKER")
    if env:
        return Path(env)
    # repos/<repo>/tests/... -> parents[2] = repos/ ; baseline lives beside us
    return Path(__file__).resolve().parents[2] / "baseline-skill" / "check.mjs"


def test_meta_loop_gate():
    checker = _baseline_checker()
    assert checker.exists(), (
        "baseline checker not found; set META_BASELINE_CHECKER to baseline-skill/check.mjs"
    )
    r = subprocess.run(
        ["node", str(checker), "--repo", ".", "--no-exec", "--json"],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    )
    assert r.returncode == 0, f"repo is NOT baseline-green:\n{r.stdout}\n{r.stderr}"
    summary = json.loads(r.stdout).get("summary", {})
    assert summary.get("blockers", 0) == 0, f"blockers present: {summary}"
