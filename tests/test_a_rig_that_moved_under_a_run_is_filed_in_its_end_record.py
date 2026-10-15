"""A rig that moved under a run is filed in the run's own end record.

Gate 7 (``07-teardown.py``) re-reads the rig after the step and compares the
keys it holds a run to (``COMPARED``) with gate 2's reading before it. A key
that changed used to be stamped in a ``<artifact>.RIGMOVED`` sidecar beside
every artifact the run wrote. It is now filed once, where the run's end is
already filed — ``<RUN_ID>.end.json`` in the run's envelope — as
``rig_moved``: each moved key with its value before and after. The run's
output says it in one line. A rig that did not move files no ``rig_moved``.

A moved rig keeps the exit it had: the run is not green (gate 7 exits 1, and
the door with it).
"""

from __future__ import annotations

import json
from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")


def _run(tmp_path: Path, *, moves: bool) -> tuple[Path, int, str]:
    """One probe run on box1, whose PL1 reads 4095 W after the step when
    ``moves``; returns the fixture root, the door's exit and its output."""
    root = onedoor.fixture_repo(tmp_path)
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", after=f"touch '{flag}'"),
    )
    onedoor.rig_stub(
        onedoor.stubs_dir(root), "box1", moved_flag=flag if moves else None
    )
    result = onedoor.door(root, PROBE)
    return root, result.returncode, result.stdout + result.stderr


def _end(root: Path) -> dict[str, object]:
    run = onedoor.envelope(root, PROBE)
    path = run / f"{run.name}.end.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), loaded
    return loaded


def test_a_moved_rig_is_filed_in_the_end_record_and_logged_without_a_sidecar(
    tmp_path: Path,
) -> None:
    root, code, said = _run(tmp_path, moves=True)

    assert code == 1, said
    before = onedoor.RIG["box1"]["pl1_uw"]
    assert _end(root)["rig_moved"] == {
        "pl1_uw": {"before": before, "after": "4095000000"}
    }, said
    assert f"rig changed during the run: pl1_uw {before} -> 4095000000" in said, said
    assert not list(root.rglob("*.RIGMOVED")), sorted(
        str(p) for p in root.rglob("*.RIGMOVED")
    )
    assert "RIGMOVED" not in said, said
    run = onedoor.envelope(root, PROBE)
    assert (run / "probe.json").is_file(), sorted(p.name for p in run.iterdir())


def test_a_rig_that_did_not_move_files_no_rig_moved(tmp_path: Path) -> None:
    root, code, said = _run(tmp_path, moves=False)

    assert code == 0, said
    assert "rig_moved" not in _end(root), said
    assert "rig changed during the run" not in said, said
