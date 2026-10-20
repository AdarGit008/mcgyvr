"""A fleet is a named layout of room slots, pinned to the sha256 of that layout.

* A **combination** is one rig's **room slots**, in order. Each slot holds a
  unit, ``awake`` or ``asleep``, or is free: a list position is a room
  slot. An asleep unit keeps its room; a unit whose room is freed leaves its
  slot free. Keeping the room and freeing it are two combinations and so two
  fleets ("save room vs don't save = 2 different rig setups = 2 different
  fleets"). Level-1 vLLM sleep is refused where a sleep level is spelled
  (``mcgyvr.serving.servelib.sleep``), and a unit has no third state.
* A **fleet** is a name (``flt-05``) pinned to the sha256 of its layout, one
  combination per rig. A layout edited after it was locked no longer matches
  its pin.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

import pytest

from tests._helpers import required

RIG1 = "rig-" + "1" * 64
RIG2 = "rig-" + "2" * 64
U1B = "unt-" + "1" * 64
U3B = "unt-" + "3" * 64
U4B = "unt-" + "4" * 64
U7B = "unt-" + "7" * 64
U9B = "unt-" + "9" * 64
U35B = "unt-" + "5" * 64


def _layout() -> Any:
    return required(
        "name a combination and a fleet layout by room slot",
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
    box2 = layout.combination_id(RIG2, [(U7B, "awake"), (U3B, "asleep")])
    box1 = layout.combination_id(RIG1, [(U35B, "awake")])
    pinned = layout.layout_sha256({RIG2: box2, RIG1: box1})
    assert re.fullmatch(r"[0-9a-f]{64}", pinned), pinned
    assert layout.layout_sha256({RIG1: box1, RIG2: box2}) == pinned
    edited = layout.combination_id(RIG2, [(U7B, "awake"), (U3B, "awake")])
    assert layout.layout_sha256({RIG2: edited, RIG1: box1}) != pinned, (
        "a layout edited after it was locked no longer matches its pin"
    )
