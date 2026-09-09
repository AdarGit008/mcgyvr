"""A step declares what it writes on ONE line; a second line is refused, not dropped.

Gate 5 (``05-envelope.py``) reads ``# RUN_ARTIFACTS:`` (and ``RUN_REWRITES``,
``RUN_APPENDS``) as text and never executes the step. The first cut kept only
the first match: a step carrying two ``# RUN_ARTIFACTS:`` lines had its second
file neither write-once-guarded (gate 5) nor stamped (gate 7) nor read back
(gate 8), and an existing file of that name was overwritten under a green
line that named only the first. The door's premise is that it does not trust
the step; silently narrowing the declaration is trusting it twice.

So a directive that appears more than once is exit 2 naming it, before the
envelope exists and before anything runs.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario

LEGACY = "### START legacy\n"


def test_two_run_artifacts_lines_are_exit_2_and_the_second_file_is_untouched(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    body = onedoor.probe_step(
        tmp_path / "e", after='cp "$out" "${RUN_OUT_DIR:?}/other.tsv"'
    )
    body = body.replace(
        "# RUN_ARTIFACTS: probe.tsv\n",
        "# RUN_ARTIFACTS: probe.tsv\n# RUN_ARTIFACTS: other.tsv\n",
    )
    onedoor.add_step(root, "alpha", "1-probe.sh", body)
    out_dir = onedoor.envelope(root, "alpha")
    out_dir.mkdir(parents=True)
    (out_dir / "other.tsv").write_text(LEGACY, encoding="utf-8")
    before = onedoor.written_under_records(root)

    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "RUN_ARTIFACTS" in result.stderr, result.stderr
    assert (out_dir / "other.tsv").read_text(encoding="utf-8") == LEGACY
    assert onedoor.written_under_records(root) == before
    assert not (tmp_path / "e").exists(), "the step ran on a narrowed declaration"
