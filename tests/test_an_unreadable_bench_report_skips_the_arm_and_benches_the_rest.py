"""Step 3: an unreadable llama-bench report is one SKIP cell, not the end of the bench.

``3-llama-bench.sh`` says so itself — "a cell with nothing filed, which is what
SKIP means (§1.4)" — and then ``return 1``'d from ``bench_arm``, which
``main`` calls as a bare command under ``set -e``: the first arm whose report
the parser refused ended the run with one SKIP row, no rows for the arms
after it and no ``### END``, behind a write-once artifact that makes the
re-run cost a move-aside.

So the SKIP branch returns 0 like every other filed-nothing branch, and the
loop goes on to the next arm. Pinned through the door against the real step
with a docker behind the shim whose llama-bench prints nothing: every arm of
the step's default list files a SKIP, and ``### END`` follows the last.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.test_a_vulkan_arm_that_measured_the_cpu_is_refused_not_filed import (
    CAMPAIGN,
    _bench,
    _bench_fixture,
)


def test_unreadable_reports_are_skip_rows_under_one_end(tmp_path: Path) -> None:
    body = (
        'case "${1:-}" in\n'
        f'  image) printf \'[{{"Id":"sha256:{onedoor.LOCAL_ID_HEX}",'
        '"RepoDigests":[]}]\\n\'; exit 0 ;;\n'
        "  *) exit 0 ;;\n"  # `run --entrypoint test` passes; llama-bench prints nothing
        "esac\n"
    )
    root, env_extra = _bench_fixture(tmp_path, body)
    result = onedoor.door(root, _bench(root, env_extra), env_extra=env_extra)
    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    text = (onedoor.envelope(root, CAMPAIGN) / "srv1-llama-bench.tsv").read_text(
        encoding="utf-8"
    )
    rows = [line.split("\t") for line in text.splitlines() if "\t" in line]
    assert rows, text
    assert {r[2] for r in rows} == {"SKIP"}, text
    skipped = sorted(r[1] for r in rows)
    assert {"L0-p512", "L1-p512"} <= set(skipped), text
    assert any(line.startswith("### END") for line in text.splitlines()), text
