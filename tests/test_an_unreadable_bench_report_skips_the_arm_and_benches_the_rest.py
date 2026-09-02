"""Step 3: an unreadable llama-bench report is one SKIP cell, not the end of the bench.

``3-llama-bench.sh`` says so itself — "a cell with nothing filed, which is what
SKIP means (§1.4)" — and then ``return 1``'d from ``bench_arm``, which
``main`` calls as a bare command under ``set -e``: the first arm whose report
the parser refused ended the run with one SKIP row, no rows for the arms
after it and no ``### END``, behind a write-once artifact that makes the
re-run cost a move-aside.

So the SKIP branch returns 0 like every other filed-nothing branch, and the
loop goes on to the next arm. Pinned through the door against the real step
with a docker on PATH whose llama-bench prints nothing.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from tests import onedoor

CAMPAIGN = "srv1-kernel-arms"


def test_two_unreadable_reports_are_two_skip_rows_under_one_end(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    shutil.copytree(
        onedoor.KERNEL_ARMS, root / "tools" / "runs" / "campaigns" / CAMPAIGN
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    docker = onedoor.executable(
        stubs / "docker",
        "#!/usr/bin/env bash\n"
        'case "${1:-}" in\n'
        f'  image) printf \'[{{"Id":"sha256:{onedoor.LOCAL_ID_HEX}",'
        '"RepoDigests":[]}]\\n\'; exit 0 ;;\n'
        "  *) exit 0 ;;\n"  # `run --entrypoint test` passes; llama-bench prints nothing
        "esac\n",
    )
    models = tmp_path / "models" / "dense"
    models.mkdir(parents=True)
    (models / "Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf").write_bytes(b"gguf")
    env = onedoor.door_env(root, stubs, docker=docker)
    env["PATH"] = f"{stubs}{os.pathsep}{env['PATH']}"
    env["RUN_ARMS"] = "L0 L1"
    env["RUN_MODELS_DIR"] = str(tmp_path / "models")
    env["RUN_RETRY_SLEEP"] = "0"
    result = onedoor.door(root, [CAMPAIGN, "llama-bench", "--host", "srv1"], env)
    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    text = (onedoor.envelope(root, CAMPAIGN) / "srv1-llama-bench.tsv").read_text(
        encoding="utf-8"
    )
    rows = [line.split("\t") for line in text.splitlines() if "\t" in line]
    skipped = sorted(r[1] for r in rows if r[2] == "SKIP")
    assert skipped == ["L0-p512", "L1-p512"], text
    assert any(line.startswith("### END") for line in text.splitlines()), text
