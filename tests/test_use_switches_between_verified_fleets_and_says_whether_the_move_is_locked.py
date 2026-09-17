"""``use`` switches between any verified fleet, and says whether the move is locked.

Owner, 2026-09-16: "switching between verified fleets is a common action during
runtime". A verified fleet is a promoted folder whose layout still matches its
own lock; ``mcgyvr fleet use <name>`` names any one of them live. What it
prints is what the lock knows of the move from the fleet that was live:

* a **locked move** when the target's layout is in the live fleet's locked
  ``next`` — with the downtime and wake the lock measured for it, per rig;
* an **unmeasured switch** otherwise — the live lock lists no move there, and
  nothing is refused for it: ``use`` starts nothing, and the door admits a
  live serve up from the lock of the fleet it names.

The refusals that stay: a name with no folder, and a folder whose layout no
longer matches its own lock. A folder promoted before the ruling has no date in
its name; ``use`` accepts it, says it is untagged and how to tag it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tests.test_dev_and_live_locks_flow_one_way import (
    MODELLED,
    cli,
    dev_setup,
    fleets,
    live_json,
)
from tests.test_the_fleet_lock_is_written_only_from_passing_dev_runs import FLT02

DATE = "2026-09-11"
FLT05, FLT02_TAGGED, FLT07 = f"flt-05@{DATE}", f"flt-02@{DATE}", f"flt-07@{DATE}"


def _live() -> Any:
    return json.loads(live_json().read_text(encoding="utf-8"))


def _three_fleets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """flt-05 (next: flt-02), flt-02 (next: flt-05) and flt-07 (next: []), promoted."""
    fleet = copy.deepcopy(MODELLED)
    fleet["fleets"]["flt-07"] = {"layout": {"srv2": copy.deepcopy(FLT02)}, "next": []}
    _dev, setup = dev_setup(tmp_path, monkeypatch, locked_fleet=fleet)
    for name in ("flt-05", "flt-02", "flt-07"):
        assert cli("fleet", "promote", name, "--setup", str(setup)) == 0


def test_use_switches_to_any_verified_fleet_whether_or_not_the_lock_lists_the_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _three_fleets(tmp_path, monkeypatch)

    assert cli("fleet", "use", FLT05) == 0
    assert _live()["fleet"] == FLT05 and _live()["since"]
    first = capsys.readouterr().out
    assert FLT05 in first and "no fleet was live" in first

    assert cli("fleet", "use", FLT07) == 0, "a verified fleet outside next is a switch"
    assert _live()["fleet"] == FLT07
    said = capsys.readouterr().out
    assert "unmeasured" in said and f"{FLT05} -> {FLT07}" in said, said
    assert "locked" not in said.replace("lock lists no", ""), said

    assert cli("fleet", "use", FLT05) == 0
    assert _live()["fleet"] == FLT05

    assert cli("fleet", "use", FLT02_TAGGED) == 0
    assert _live()["fleet"] == FLT02_TAGGED
    said = capsys.readouterr().out
    assert "locked" in said and f"{FLT05} -> {FLT02_TAGGED}" in said, said
    # The fixture lock measured flt-05 -> flt-02 on srv2: downtime 0.3 s, and
    # srv2_3b woken in 0.25 s.
    assert "srv2" in said and "0.3" in said and "srv2_3b" in said and "0.25" in said


def test_use_of_the_live_fleet_again_is_no_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _three_fleets(tmp_path, monkeypatch)
    assert cli("fleet", "use", FLT05) == 0
    capsys.readouterr()
    assert cli("fleet", "use", FLT05) == 0
    assert _live()["fleet"] == FLT05
    assert "already live" in capsys.readouterr().out


def test_use_still_refuses_no_folder_and_a_layout_that_no_longer_matches_its_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml

    _three_fleets(tmp_path, monkeypatch)
    assert cli("fleet", "use", "flt-09@2026-09-11") != 0, "no such folder"
    assert cli("fleet", "use", "flt-05") != 0, "no folder under the plain name"
    assert not live_json().exists()

    fleet_file = fleets() / FLT07 / "fleet.yaml"
    edited = yaml.safe_load(fleet_file.read_text(encoding="utf-8"))
    slots = edited["fleets"]["flt-07"]["layout"]["srv2"]
    edited["fleets"]["flt-07"]["layout"]["srv2"] = list(reversed(slots))
    fleet_file.write_text(yaml.safe_dump(edited, sort_keys=False), encoding="utf-8")
    assert cli("fleet", "use", FLT07) != 0
    assert not live_json().exists()


def test_use_accepts_an_untagged_folder_and_says_how_to_tag_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _three_fleets(tmp_path, monkeypatch)
    (fleets() / FLT05).rename(fleets() / "flt-05")

    assert cli("fleet", "use", "flt-05") == 0
    assert _live()["fleet"] == "flt-05"
    said = capsys.readouterr().out
    assert "untagged" in said and "mcgyvr fleet tag flt-05" in said and FLT05 in said

    assert cli("fleet", "use", FLT02_TAGGED) == 0, (
        "a locked move from an untagged fleet"
    )
    said = capsys.readouterr().out
    assert "locked" in said and f"flt-05 -> {FLT02_TAGGED}" in said, said


def test_a_switch_from_a_pointer_whose_folder_is_gone_is_unmeasured_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A folder tagged by hand (`mv`) leaves the pointer naming the old name."""
    _three_fleets(tmp_path, monkeypatch)
    assert cli("fleet", "use", FLT05) == 0
    (fleets() / FLT05).rename(fleets() / "flt-05@2026-09-10")
    capsys.readouterr()

    assert cli("fleet", "use", "flt-05@2026-09-10") == 0
    assert _live()["fleet"] == "flt-05@2026-09-10"
    said = capsys.readouterr().out
    assert "unmeasured" in said and "no folder" in said, said
