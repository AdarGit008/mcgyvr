"""A read without a lock never pulls a live unit.

A live alert pulls its combination (:func:`mcgyvr.fleet.alerts.pulled`), and
``mcgyvr run`` warns before a pulled step (``live_pulled_units``) and ``mcgyvr
fleet alerts`` lists it. ``read --fleet F`` reads a fleet of a setup that holds
no lock, and files its rows ``locked=false``. A setup may share the live
fleet's journal, its unit ids and its rig ids, so its combinations are the live
ones, while declaring a tighter ``room_mib`` than the lock proved:

* **A row filed without a lock is no pull.** A named-setup read whose card is
  over the setup's own room alerts in its row, and no live unit is pulled by it.
* **A row read with the lock still pulls**, as does a row filed before rows
  said whether they were locked: those carry no ``locked`` at all.

No rig is reached: the reading is canned text and the fleets are files in the
test's own HOME. Every id and figure is invented.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.test_a_read_measures_before_it_judges_and_loads_a_unit import rig_text
from tests.test_a_rig_is_read_through_the_door_without_leasing_it import (
    FLEET,
    FLEET_NAME,
    RUN_ID,
    UNIT_3B,
    unit_rows,
)

#: An invented rig id, the one both setups declare for srv2.
RIG_ID = "rig-" + "a1" * 32
#: The room the live lock proved for srv2_3b and the tighter one the setup
#: declares.
LIVE_ROOM, SETUP_ROOM = 5000, 3000
#: The live lock's validation, older than the read.
VALIDATED_AT = "2026-09-01T00:00:00Z"


def fleet(room: int) -> dict[str, Any]:
    """The fleet both setups declare, with srv2_3b's room at ``room``."""
    shape = copy.deepcopy(FLEET)
    shape["rigs"] = {"srv2": {"rig_id": RIG_ID}}
    shape["units"]["srv2_3b"]["room_mib"] = room
    return shape


def write_setup(folder: Path, shape: dict[str, Any], journal: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "fleet.yaml").write_text(yaml.safe_dump(shape), encoding="utf-8")
    policy = {"ladder": ["srv2_3b", "srv2_7b"], "journal": {"dir": str(journal)}}
    (folder / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")


def go_live(tmp_path: Path) -> tuple[Path, Path]:
    """The live fleet and its lock in this HOME, and a journal: (folder, journal)."""
    from mcgyvr.fleet.admit import layout_ids

    journal = tmp_path / "journal"
    home = Path(os.environ["HOME"]) / ".mcgyvr"
    folder = home / "fleets" / FLEET_NAME
    shape = fleet(LIVE_ROOM)
    write_setup(folder, shape, journal)
    combination = layout_ids(shape, shape["fleets"][FLEET_NAME]["layout"])[RIG_ID]
    record = folder / "records" / "fleet" / "rigs" / RIG_ID
    record.mkdir(parents=True)
    (record / f"{combination}.json").write_text(
        json.dumps({"validated_at": VALIDATED_AT}), encoding="utf-8"
    )
    (home / "live.json").write_text(
        json.dumps({"fleet": FLEET_NAME, "since": VALIDATED_AT}), encoding="utf-8"
    )
    return folder, journal / "fleet"


def read(card: int, profile: str, **more: Any) -> None:
    from mcgyvr.fleet import read

    read.record("srv2", rig_text(card_3b=card), run_id=RUN_ID, profile=profile, **more)


def test_a_named_setup_read_over_its_own_room_pulls_no_live_unit(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet.alerts import AlertError, live_pulled_units, pulled

    live_folder, journal = go_live(tmp_path)
    setup = tmp_path / "setup"
    write_setup(setup, fleet(SETUP_ROOM), journal.parent)
    assert live_pulled_units() == {}

    # A card over the setup's room, and inside the room the lock proved.
    with pytest.raises(AlertError):
        read(SETUP_ROOM + 1000, "dev", fleet_name=FLEET_NAME, setup=setup)

    card = unit_rows(journal, UNIT_3B)["card_mib"]
    assert card["alert"] is True, "the card is over the setup's own room"
    assert card["locked"] == "false"
    assert live_pulled_units() == {}, "a read without a lock pulled a live unit"
    assert pulled(journal, live_folder) == {}


def test_a_read_with_the_lock_still_pulls_its_live_unit(tmp_path: Path) -> None:
    from mcgyvr.fleet.alerts import live_pulled_units

    _, journal = go_live(tmp_path)

    read(LIVE_ROOM + 1000, "live")

    card = unit_rows(journal, UNIT_3B)["card_mib"]
    assert card["alert"] is True and "locked" not in card
    pulls = live_pulled_units()
    assert set(pulls) == {"srv2_3b", "srv2_7b"}
    assert {(p["unit"], p["field"]) for p in pulls["srv2_3b"]} == {
        ("srv2_3b", "card_mib")
    }
