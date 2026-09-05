"""Gate 7 compares the rig's containers AFTER the step with BEFORE it, not a prefix.

Gate 7 (``07-teardown.py``) once asked ``docker ps --filter name=^<RUN_ID>-``
and called the rig clean when that came back empty. A step that started a
container under any other name — a driver's own ``--name``, a server left by
hand, a name with a typo in the prefix — left it running on the rig, held the
card, and the run exited green. ``rig-snapshot.sh`` already prints
``containers=`` (every container up, by id, or ``none``), gate 2 refuses a
reading that is not ``none``, and gate 7 re-reads the rig; nothing compared
the two.

So gate 7 lists every container up after the step (``docker ps`` with id and
name, and the reader's own ``containers=`` beside it) and names each one that
gate 2's reading did not carry — exit 1, whatever it is called. The
``<RUN_ID>-`` prefix survives only as the label of "named for this run"
against "NOT named for this run", so the operator reading the line knows
which is which. Nothing is removed: the kill is the operator's.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")


def _step_that_leaves(root: Path, tmp_path: Path, *, stray: bool, own: bool) -> Path:
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", after=f"touch '{flag}'"),
    )
    onedoor.docker_stub(
        onedoor.stubs_dir(root),
        leftover_flag=flag if own else None,
        stray_flag=flag if stray else None,
    )
    return flag


def test_a_container_without_the_prefix_is_named_and_the_run_is_not_green(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    _step_that_leaves(root, tmp_path, stray=True, own=False)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert onedoor.STRAY_NAME in result.stderr, result.stderr
    assert f"NOT named for this run (no {run_id}- prefix): {onedoor.STRAY_NAME}" in (
        result.stderr
    ), result.stderr
    assert "gate 2 read none of before it" in result.stderr, result.stderr
    log = onedoor.docker_log(root)
    assert any(line.startswith("ps") for line in log), log
    assert not any(line.startswith("rm") for line in log), "the door removed it"


def test_both_kinds_are_named_and_labelled(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    _step_that_leaves(root, tmp_path, stray=True, own=True)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert f"named for this run: {run_id}-lcps" in result.stderr, result.stderr
    assert f"NOT named for this run (no {run_id}- prefix): {onedoor.STRAY_NAME}" in (
        result.stderr
    ), result.stderr


def test_the_prefix_filter_is_no_longer_what_gate_7_asks_docker(tmp_path: Path) -> None:
    """The question is "what is up", not "what is up under my name": the
    ``docker ps`` gate 7 issues carries no name filter."""
    root = onedoor.fixture_repo(tmp_path)
    _step_that_leaves(root, tmp_path, stray=False, own=False)
    result = onedoor.door(root, PROBE)
    assert result.returncode == 0, (result.stdout, result.stderr)
    asked = [line for line in onedoor.docker_log(root) if line.startswith("ps")]
    assert asked, onedoor.docker_log(root)
    assert all("--filter" not in line for line in asked), asked
    assert all("{{.ID}}" in line and "{{.Names}}" in line for line in asked), asked


def test_a_container_the_rigs_reader_lists_is_named_by_id(tmp_path: Path) -> None:
    """The second reading: ``rig-snapshot.sh``'s ``containers=`` after the
    step, taken in the same breath as the rest of the rig. An id there that
    ``docker ps`` did not list is still a container up on the rig."""
    root = onedoor.fixture_repo(tmp_path)
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", after=f"touch '{flag}'"),
    )
    stubs = onedoor.stubs_dir(root)
    onedoor.rig_stub(stubs, "srv1", moved_flag=flag)
    (stubs / "snapshot-moved.txt").write_text(
        onedoor.snapshot_lines("srv1", containers="deadbeef0042"), encoding="utf-8"
    )
    result = onedoor.door(root, PROBE)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "deadbeef0042" in result.stderr, result.stderr
    assert "the rig's reader lists containers up after the step" in result.stderr
    assert "RIGMOVED" not in result.stderr, "containers= is not a rig key that moves"
