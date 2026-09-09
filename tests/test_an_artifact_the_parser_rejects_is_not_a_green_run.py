"""Gate 8: the door parses what the step wrote before it returns 0.

The artifact parser once ran only in CI, post-hoc, over one hard-coded
directory. A run that wrote a file the parser rejects therefore exited green
on the rig and turned red a commit later, when the rig time was spent.
``srv1-locktest-ling-60min.tsv:1`` is the shape: ``uptime_since=2026-09-01
08:11:08`` is split on whitespace, the clock is dropped, and START compared
equal to END across two different moments — the rig check passed on a run
whose machine state was never re-read.

Gate 8 (``08-parse.py``) reads back every artifact the step wrote with
``rows.read()`` before the door exits. A raise is exit 1 with the parser's own
words on stderr, and the artifact is left on disk unmodified: it is evidence
of what the step did, and a door that tidied it would be destroying the
record of its own failure.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario

LOOSE_END = "### END uptime_since=2026-09-01 08:11:08Z pl1_uw=95000000"


def test_a_stamp_with_whitespace_in_a_value_is_exit_1_with_the_file_kept(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", end_line=LOOSE_END),
    )
    result = onedoor.door(root, Scenario("alpha", "1-probe.sh"))
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "not key=value" in result.stderr, (
        f"the parser's reason is not on stderr: {result.stderr}"
    )
    artifact = onedoor.envelope(root, "alpha") / "probe.tsv"
    assert artifact.is_file(), "the rejected artifact was removed"
    text = artifact.read_text(encoding="utf-8")
    assert text.rstrip("\n").endswith(LOOSE_END), (
        f"the artifact was modified after the step wrote it:\n{text}"
    )
    assert text.count("### START") == 1 and text.count("### END") == 1
