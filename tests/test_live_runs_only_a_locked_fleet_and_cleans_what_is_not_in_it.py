"""Live runs only a locked fleet on its own rigs, and cleans what is not in it.

RED. ``mcgyvr.fleet.admit`` does not exist, and the Waker wakes whatever
``serving.compose_dir`` holds (``src/mcgyvr/wake.py:368``). The intent is
``records/plans/fleet-identity.md`` §6 (owner, 2026-09-10 and 2026-09-11).

Live is production: mcgyvr delegating real code tasks. It runs a fleet the
user picked from the locked set, and nothing else:

* no fleet named, or a fleet with no lock, is refused;
* a fleet whose layout was edited after it was locked is refused, and the
  refusal says to re-lock;
* a rig that is not the rig it was locked on is refused, naming it;
* units of ours (containers of the ``mcgyvr`` compose project) that the fleet
  does not name are cleaned, and the fleet's own units are restored; an empty
  rig is simply restored;
* a process that is not ours refuses that rig and names the process, because
  live does not kill what it does not own;
* the Waker wakes a unit only along a listed switch: it spawns one door run
  toward a fleet the current one lists, and nothing toward one it does not.

A dev run holding the rig's lease is displaced by gate 2's existing rule (live
outranks dev); tearing down its serve units is P0
(``tests/test_a_live_run_tears_down_the_serve_units_of_the_dev_run_it_displaced.py``).
"""

from __future__ import annotations

import copy
import importlib
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tests.red_port.conftest import required
from tests.test_a_sleeping_rung_is_woken_rather_than_declined import (
    RUNG_7B,
    compose_dir,
    door_log,
    ladder,
)
from tests.test_the_fleet_lock_is_written_only_from_passing_dev_runs import (
    EVIDENCE,
    FLEET,
    POLICY,
    RIG2,
    TOLERANCES,
    U3B,
    U7B,
)

STRAY = "unt-" + "9" * 64
MOVED = "rig-" + "8" * 64


def _admit() -> Any:
    return required(
        "admit a live run only on a locked fleet on its own rigs, cleaning units "
        "of ours it does not name, refusing a process it did not start, and "
        "waking only along a listed switch",
        lambda: importlib.import_module("mcgyvr.fleet.admit"),
    )


def locked(
    root: Path,
    fleet: dict[str, Any] = FLEET,
    evidence: dict[str, Any] = EVIDENCE,
) -> Path:
    lock = required(
        "write the fleet lock from passing dev runs, refusing what it cannot pin",
        lambda: importlib.import_module("mcgyvr.fleet.lock"),
    )
    lock.write(root, fleet, evidence, policy=POLICY, tolerances=TOLERANCES)
    return root


def observed(
    units: dict[str, str] | None = None,
    *,
    rig_id: str = RIG2,
    foreign: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "srv2": {
            "rig_id": rig_id,
            "units": {U7B: "awake", U3B: "asleep"} if units is None else units,
            "foreign": foreign or [],
        }
    }


def test_live_names_a_locked_fleet_or_refuses(tmp_path: Path) -> None:
    admit = _admit()
    root = locked(tmp_path)
    with pytest.raises(admit.LiveRefusedError, match="no fleet"):
        admit.admit_live(root, FLEET, None, observed())
    with pytest.raises(admit.LiveRefusedError, match="flt-99"):
        admit.admit_live(root, FLEET, "flt-99", observed())


def test_a_fleet_whose_layout_was_edited_after_locking_is_refused(
    tmp_path: Path,
) -> None:
    admit = _admit()
    root = locked(tmp_path)
    fleet = copy.deepcopy(FLEET)
    fleet["fleets"]["flt-05"]["layout"]["srv2"][1] = ["srv2_3b", "awake"]
    with pytest.raises(admit.LiveRefusedError, match="flt-05") as refused:
        admit.admit_live(root, fleet, "flt-05", observed())
    assert "re-lock" in str(refused.value), refused.value


def test_a_rig_that_is_not_the_rig_it_was_locked_on_is_refused(
    tmp_path: Path,
) -> None:
    admit = _admit()
    root = locked(tmp_path)
    with pytest.raises(admit.LiveRefusedError, match="srv2") as refused:
        admit.admit_live(root, FLEET, "flt-05", observed(rig_id=MOVED))
    said = str(refused.value)
    assert MOVED in said or RIG2 in said, f"the refusal names no rig id: {said}"


def test_the_locked_fleet_on_its_own_rigs_is_admitted_with_nothing_to_do(
    tmp_path: Path,
) -> None:
    admit = _admit()
    root = locked(tmp_path)
    plan = admit.admit_live(root, FLEET, "flt-05", observed())
    assert list(plan.clean) == [] and list(plan.restore) == [], plan


def test_an_empty_rig_is_admitted_and_its_fleet_restored(tmp_path: Path) -> None:
    admit = _admit()
    root = locked(tmp_path)
    plan = admit.admit_live(root, FLEET, "flt-05", observed({}))
    assert list(plan.clean) == []
    assert set(plan.restore) == {("srv2", U7B, "awake"), ("srv2", U3B, "asleep")}


def test_units_of_ours_the_fleet_does_not_name_are_cleaned_and_it_is_restored(
    tmp_path: Path,
) -> None:
    admit = _admit()
    root = locked(tmp_path)
    plan = admit.admit_live(root, FLEET, "flt-05", observed({STRAY: "awake"}))
    assert list(plan.clean) == [("srv2", STRAY)], plan
    assert set(plan.restore) == {("srv2", U7B, "awake"), ("srv2", U3B, "asleep")}


def test_a_process_that_is_not_ours_refuses_that_rig_and_names_it(
    tmp_path: Path,
) -> None:
    admit = _admit()
    root = locked(tmp_path)
    busy = observed(foreign=["python3 train.py"])
    with pytest.raises(admit.LiveRefusedError, match=r"train\.py") as refused:
        admit.admit_live(root, FLEET, "flt-05", busy)
    assert "srv2" in str(refused.value), refused.value


def test_the_waker_does_not_wake_toward_a_fleet_nobody_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused port on a live setup with no locked fleet spawns nothing.

    The file is written here rather than through ``config_file``: this is the
    live, no-lock case itself, and it must not borrow a helper whose callers
    declare ``profile: dev``.
    """
    from mcgyvr import wake
    from mcgyvr.config import load

    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    spawned = door_log(monkeypatch)
    specs = compose_dir(tmp_path, with_spec=True)
    live = tmp_path / "live.yaml"
    live.write_text(
        ladder(engine="vllm")
        + f"journal:\n  dir: {tmp_path / 'j'}\n"
        + f"serving:\n  enable_sleep_wake: true\n  compose_dir: {specs}\n",
        encoding="utf-8",
    )
    waker = wake.for_config(load(live))
    woke = waker.wake_for(RUNG_7B) if waker is not None else False
    assert spawned == [], f"the door was spawned toward an unlocked fleet: {spawned}"
    assert woke is False


def test_the_waker_wakes_a_unit_along_a_listed_switch(tmp_path: Path) -> None:
    """flt-05 lists flt-02, where the asleep 3B is awake: one door run."""
    admit = _admit()
    root = locked(tmp_path)
    spawned: list[Any] = []
    target = admit.wake(root, FLEET, "flt-05", "srv2_3b", spawn=spawned.append)
    assert target == "flt-02"
    assert len(spawned) == 1, spawned


def test_the_waker_does_not_wake_along_a_switch_nobody_listed(tmp_path: Path) -> None:
    """The 3B is awake only in flt-02, and flt-05 lists no switch to it."""
    admit = _admit()
    fleet = copy.deepcopy(FLEET)
    for entry in fleet["fleets"].values():
        entry["next"] = []
    evidence = copy.deepcopy(EVIDENCE)
    evidence["moves"] = []
    root = locked(tmp_path, fleet, evidence)
    spawned: list[Any] = []
    with pytest.raises(admit.LiveRefusedError) as refused:
        admit.wake(root, fleet, "flt-05", "srv2_3b", spawn=spawned.append)
    said = str(refused.value)
    assert "flt-05" in said and "flt-02" in said, said
    assert spawned == [], spawned
