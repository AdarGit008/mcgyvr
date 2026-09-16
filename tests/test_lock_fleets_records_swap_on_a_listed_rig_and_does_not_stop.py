"""lock-fleets records swap growth on a listed rig, and does not stop there.

Owner ruling, 2026-09-15: "Record swap on srv1, don't stop". srv1's driver
stopped after ``rig-id-relock``'s srv1-01 on ``pswpout rose during the run
(264920 -> 312345)``: 47,425 pages, inside the 35,000-48,000 pages per wake
``records/measurements/ram-headroom-2026-09-09/README.md`` measured for that
blob mapped on srv1 at swappiness 60, with decode unaffected.

A use's ``use.json`` names the rigs whose swap growth is recorded and not
stopped on (``swap_recorded_not_stopped_on``). On such a rig a run's pswpout
start, end and delta are filed and are no reason to stop; every other stop
still applies there, and every other rig keeps the swap stop.

srv2 was added to that list on 2026-09-16 ("Record swap on srv2 too"), through
this same mechanism; what that ruling says is pinned in
``tests/test_srv2_swap_is_recorded_and_does_not_stop_a_run.py``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.lockfleets_window import (
    REPO,
    USE,
    Window,
    assemble_module,
    context,
    frozen_window,
    make_tree,
    plan_module,
    use_doc,
)

Change = Callable[[dict[str, Any]], None]
SWAP = "pswpout rose during the run"
#: The fixture's runs read pswpout 10 at START; this is 47,425 pages later.
SWAPPED = 47435


def _swapped(payload: dict[str, Any]) -> None:
    payload["doc"]["vmstat"]["end"]["pswpout"] = SWAPPED


def _swapped_and_rebooted(payload: dict[str, Any]) -> None:
    _swapped(payload)
    payload["doc"]["markers"]["end"] = (
        "### END uptime_since=2026-09-16T11:00:00Z "
        "pl1_uw=95000000 pl2_uw=120000000 ram_mt_s=3600"
    )


@pytest.fixture
def window(tmp_path: Path) -> Window:
    return frozen_window(tmp_path, use=use_doc(swap_recorded_not_stopped_on=["alpha"]))


def test_the_planner_reads_the_rigs_whose_swap_is_recorded(window: Window) -> None:
    use = plan_module().load_use(window.root, USE)
    assert use.swap_recorded_not_stopped_on == ("alpha",)


def test_a_listed_rig_no_fleet_places_a_unit_on_is_refused(tmp_path: Path) -> None:
    make_tree(tmp_path, use=use_doc(swap_recorded_not_stopped_on=["gamma"]))
    plan = plan_module()
    with pytest.raises(plan.PlanRefusedError, match=r"use\.json names rig gamma"):
        plan.freeze(tmp_path, USE)


def test_swap_growth_on_a_listed_rig_is_filed_and_does_not_stop(
    window: Window,
) -> None:
    window.write_all({"alpha-02": _swapped})
    asm = assemble_module()
    assert asm.check(context(window), "alpha", "alpha-02") == []
    _, runs, _ = asm.assemble(context(window))
    assert runs["runs"]["alpha-02"]["pswpout"] == {
        "start": 10,
        "end": SWAPPED,
        "delta": SWAPPED - 10,
    }


def test_swap_growth_still_stops_on_a_rig_the_use_does_not_list(
    window: Window,
) -> None:
    window.write_all({"beta-01": _swapped})
    reasons = assemble_module().check(context(window), "beta", "beta-01")
    assert f"{SWAP} (10 -> {SWAPPED})" in reasons, reasons


def test_a_marker_change_still_stops_on_a_listed_rig(window: Window) -> None:
    window.write_all({"alpha-02": _swapped_and_rebooted})
    reasons = assemble_module().check(context(window), "alpha", "alpha-02")
    assert any(
        "the START and END markers differ: uptime_since" in why for why in reasons
    ), reasons
    assert not any(SWAP in why for why in reasons), reasons


def test_rig_id_relock_records_swap_on_the_rigs_its_use_lists() -> None:
    """srv1 from 2026-09-15, srv2 from 2026-09-16 ("Record swap on srv2 too",
    ``tests/test_srv2_swap_is_recorded_and_does_not_stop_a_run.py``). Both are
    the one mechanism this module pins; the 09-15 citation stays where it was."""
    use = plan_module().load_use(REPO, "rig-id-relock")
    assert use.swap_recorded_not_stopped_on == ("srv1", "srv2")
    path = REPO / "records/measurements/lock-fleets/rig-id-relock/use.json"
    why = json.loads(path.read_text("utf-8"))["_swap_recorded_not_stopped_on"]
    assert "2026-09-15" in why and "ram-headroom-2026-09-09" in why, why
