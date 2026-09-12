"""A fleet is a named layout, and it moves only along the switches listed for it.

RED. ``mcgyvr.fleet.layout`` does not exist. The intent is
``records/plans/fleet-identity.md`` §1 and §3 (owner, 2026-09-11).

* A **combination** is one rig's **room slots**, in order. Each slot holds a
  unit, ``awake`` or ``asleep``, or is free (owner: "list position is a room
  slot"). An asleep unit keeps its room; a unit whose room is freed leaves its
  slot free. Keeping the room and freeing it are two combinations and so two
  fleets ("save room vs don't save = 2 different rig setups = 2 different
  fleets"). Level-1 vLLM sleep is refused where it is reached today
  (``src/mcgyvr/serving/servelib.py``), and a unit has no third state.
* A **fleet** is a name (``flt-05``) pinned to the sha256 of its layout, one
  combination per rig. A layout edited after it was locked no longer matches
  its pin.
* A **switch** is listed: ``flt-05`` may move to ``flt-02``, ``flt-11`` or
  ``flt-14`` and nowhere else. It is commanded at fleet level and carried out
  per rig and per slot: slot k of the source pairs with slot k of the target,
  and a leaving slot's stop precedes its arrival's start. Only slots that
  differ act. Slot k is identity; the order units start in is not.
* A switch's dev run is keyed by its **rig move** (the rig, the combination it
  starts from and the actions), so one run proves every fleet switch that
  derives the same move.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

import pytest

from tests.red_port.conftest import required

RIG1 = "rig-" + "1" * 64
RIG2 = "rig-" + "2" * 64
U1B = "unt-" + "1" * 64
U3B = "unt-" + "3" * 64
U4B = "unt-" + "4" * 64
U7B = "unt-" + "7" * 64
U9B = "unt-" + "9" * 64
U35B = "unt-" + "5" * 64
NEXT = {"flt-05": ["flt-02", "flt-11", "flt-14"], "flt-02": ["flt-05"]}


def _layout() -> Any:
    return required(
        "name a combination and a fleet layout by room slot, allow only listed "
        "switches, and derive a switch's actions per rig and slot",
        lambda: importlib.import_module("mcgyvr.fleet.layout"),
    )


def test_a_combination_names_its_rig_and_what_each_room_slot_holds() -> None:
    layout = _layout()
    both = layout.combination_id(RIG2, [(U7B, "awake"), (U3B, "awake")])
    assert both.startswith("cmb-"), both
    swapped = layout.combination_id(RIG2, [(U3B, "awake"), (U7B, "awake")])
    assert swapped != both, "list position is a room slot, and slot k is identity"
    asleep = layout.combination_id(RIG2, [(U7B, "awake"), (U3B, "asleep")])
    freed = layout.combination_id(RIG2, [(U7B, "awake"), None])
    assert len({both, asleep, freed}) == 3, "awake, asleep and a free slot all differ"
    assert layout.combination_id(RIG1, [(U7B, "awake"), (U3B, "awake")]) != both


def test_a_unit_is_awake_or_asleep_and_nothing_else() -> None:
    layout = _layout()
    for state in ("asleep-L1", "released", "down"):
        with pytest.raises(ValueError, match=state):
            layout.combination_id(RIG2, [(U7B, state)])


def test_a_fleet_name_is_pinned_to_the_sha256_of_its_layout() -> None:
    layout = _layout()
    srv2 = layout.combination_id(RIG2, [(U7B, "awake"), (U3B, "asleep")])
    srv1 = layout.combination_id(RIG1, [(U35B, "awake")])
    pinned = layout.layout_sha256({RIG2: srv2, RIG1: srv1})
    assert re.fullmatch(r"[0-9a-f]{64}", pinned), pinned
    assert layout.layout_sha256({RIG1: srv1, RIG2: srv2}) == pinned
    assert layout.check_pin("flt-05", {RIG2: srv2, RIG1: srv1}, pinned) is None
    edited = layout.combination_id(RIG2, [(U7B, "awake"), (U3B, "awake")])
    with pytest.raises(layout.FleetError, match="flt-05") as refused:
        layout.check_pin("flt-05", {RIG2: edited, RIG1: srv1}, pinned)
    assert "re-lock" in str(refused.value), refused.value


def test_only_a_listed_switch_is_approved() -> None:
    layout = _layout()
    for target in NEXT["flt-05"]:
        assert layout.approve_switch(NEXT, "flt-05", target) is None
    with pytest.raises(layout.SwitchRefusedError, match="flt-07"):
        layout.approve_switch(NEXT, "flt-05", "flt-07")
    with pytest.raises(layout.SwitchRefusedError, match="flt-11"):
        layout.approve_switch(NEXT, "flt-11", "flt-05")


def test_a_switch_acts_only_on_the_slots_that_differ() -> None:
    """srv2's slot 1 holds an asleep 3B and takes a 4B; slot 0 and srv1 stay."""
    layout = _layout()
    flt05 = {RIG2: [(U7B, "awake"), (U3B, "asleep")], RIG1: [(U35B, "awake")]}
    flt02 = {RIG2: [(U7B, "awake"), (U4B, "awake")], RIG1: [(U35B, "awake")]}
    assert layout.actions(flt05, flt02) == [
        (RIG2, "drain", U3B),
        (RIG2, "stop", U3B),
        (RIG2, "start", U4B),
    ]


def test_a_switch_pairs_slot_k_with_slot_k_and_stops_it_before_it_starts() -> None:
    """Both slots change: each leaving unit stops before the unit that takes its
    room starts. How the two slots interleave is not pinned: the order units
    start in is not identity."""
    layout = _layout()
    before = {RIG2: [(U7B, "awake"), (U3B, "awake")]}
    after = {RIG2: [(U9B, "awake"), (U1B, "awake")]}
    acts = layout.actions(before, after)
    assert set(acts) == {
        (RIG2, "drain", U7B),
        (RIG2, "stop", U7B),
        (RIG2, "start", U9B),
        (RIG2, "drain", U3B),
        (RIG2, "stop", U3B),
        (RIG2, "start", U1B),
    }, acts
    for leaving, arriving in ((U7B, U9B), (U3B, U1B)):
        stop = acts.index((RIG2, "stop", leaving))
        assert acts.index((RIG2, "drain", leaving)) < stop, acts
        assert stop < acts.index((RIG2, "start", arriving)), acts


def test_sleep_and_wake_are_switches_like_any_other() -> None:
    layout = _layout()
    awake = {RIG2: [(U7B, "awake"), (U3B, "awake")]}
    asleep = {RIG2: [(U7B, "awake"), (U3B, "asleep")]}
    assert layout.actions(awake, asleep) == [
        (RIG2, "drain", U3B),
        (RIG2, "sleep", U3B),
    ]
    assert layout.actions(asleep, awake) == [(RIG2, "wake", U3B)]


def test_a_rig_move_proven_once_serves_every_fleet_switch_that_derives_it() -> None:
    layout = _layout()
    srv2_from = [(U7B, "awake"), (U3B, "asleep")]
    srv2_to = [(U7B, "awake"), (U4B, "awake")]
    flt05 = {RIG2: srv2_from, RIG1: [(U35B, "awake")]}
    flt02 = {RIG2: srv2_to, RIG1: [(U35B, "awake")]}
    flt07 = {RIG2: srv2_from, RIG1: [(U35B, "asleep")]}
    flt09 = {RIG2: srv2_to, RIG1: [(U35B, "asleep")]}
    one = layout.rig_moves(flt05, flt02)
    assert len(one) == 1, one
    assert layout.rig_moves(flt07, flt09) == one, "the same srv2 move, once"
    elsewhere = {RIG2: [(U7B, "awake"), (U3B, "awake")], RIG1: [(U35B, "awake")]}
    assert layout.rig_moves(elsewhere, flt02) != one, (
        "the same actions from another combination are another move"
    )
