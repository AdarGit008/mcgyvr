"""A promoted fleet carries the date of its lock in its name.

Owner, 2026-09-16: "all fleets get tagged with date - promote with the date in
fleet name - switching between verified fleets is a common action during
runtime".

* ``mcgyvr fleet promote <fleet> --setup <dev dir>`` is invoked with the plain
  fleet name and writes ``~/.mcgyvr/fleets/<fleet>@<YYYY-MM-DD>/``, where the
  date is the lock's own: the latest ``validated_at`` among the combination
  records the lock wrote for that fleet's layout. Never today's date.
* Inside the folder nothing is renamed: ``fleet.yaml`` keys the fleet by its
  plain name and the lock sits at ``records/fleet/<fleet>.json``, so a tagged
  folder and a folder promoted before the ruling have one shape, and tagging
  one is a rename.
* A re-lock on a new date gets a new folder beside the old one, which stays as
  a verified config. The same tagged name is refused, as any existing folder.
* A name that already carries a tag is refused by ``promote``: the date is the
  lock's to say. A lock whose records carry no ``validated_at`` cannot be dated
  and is refused, with nothing written.
* ``mcgyvr fleet tag <fleet>`` renames a folder promoted before the ruling to
  ``<fleet>@<its lock date>``; a pointer naming it follows the rename.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_dev_and_live_locks_flow_one_way import (
    LOCK_DATE,
    MODELLED,
    cli,
    dev_setup,
    fleets,
    flt05_records,
    listing,
    live_json,
    name_live,
    tree,
)
from tests.test_the_fleet_lock_is_written_only_from_passing_dev_runs import (
    EVIDENCE,
    POLICY,
    TOLERANCES,
)

#: flt-05 at the fixture lock's date: the latest validated_at among its records.
TAGGED = f"flt-05@{LOCK_DATE}"


def _relock(dev: Path, validated_at: str) -> None:
    """Write the same layout's lock again under ``dev`` with a new date."""
    from mcgyvr.fleet import lock

    evidence = copy.deepcopy(EVIDENCE)
    for combination in evidence["combinations"]:
        combination["validated_at"] = validated_at
    lock.write(dev, MODELLED, evidence, policy=POLICY, tolerances=TOLERANCES)


def test_promote_writes_the_folder_under_the_fleet_name_and_its_lock_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev, setup = dev_setup(tmp_path, monkeypatch)
    before = tree(dev)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert today != LOCK_DATE, "the fixture's lock date must not be today"

    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) == 0

    assert [path.name for path in fleets().iterdir()] == [TAGGED], (
        "the promoted folder is named <fleet>@<the lock's validated_at date>"
    )
    folder = fleets() / TAGGED
    assert str(folder) in capsys.readouterr().out, "promote reports the folder it wrote"

    lock, record = flt05_records()
    written = tree(folder)
    assert set(written) == {"fleet.yaml", "policy.yaml", lock, record}, (
        "inside the folder the fleet keeps its plain name: the lock is "
        "records/fleet/flt-05.json, not flt-05@date.json"
    )
    assert written[lock] == before[lock] and written[record] == before[record]
    fleet_text = written["fleet.yaml"].decode("utf-8")
    assert "flt-05:" in fleet_text and TAGGED not in fleet_text, (
        "fleet.yaml keys the fleet by its plain name"
    )
    assert cli("config", str(folder)) == 0
    assert tree(dev) == before, "promote wrote into the dev root"


def test_the_date_is_the_latest_validated_at_of_the_layouts_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet.promote import lock_date

    dev, _setup = dev_setup(tmp_path, monkeypatch)
    assert lock_date(dev, "flt-05") == LOCK_DATE
    # flt-02's one record is dated 10:30 the same day.
    assert lock_date(dev, "flt-02") == LOCK_DATE

    _relock(dev, "2026-09-12T08:00:00Z")
    assert lock_date(dev, "flt-05") == "2026-09-12"


def test_a_relock_on_a_new_date_is_promoted_beside_the_old_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dev, setup = dev_setup(tmp_path, monkeypatch)
    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) == 0
    old = tree(fleets() / TAGGED)

    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) != 0, (
        "the same lock promoted twice is the same tagged folder, which exists"
    )
    assert sorted(path.name for path in fleets().iterdir()) == [TAGGED]

    _relock(dev, "2026-09-12T08:00:00Z")
    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) == 0
    assert sorted(path.name for path in fleets().iterdir()) == [
        TAGGED,
        "flt-05@2026-09-12",
    ]
    assert tree(fleets() / TAGGED) == old, "the earlier verified config was touched"


def test_promote_takes_the_plain_fleet_name_and_refuses_a_tagged_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _dev, setup = dev_setup(tmp_path, monkeypatch)
    assert cli("fleet", "promote", TAGGED, "--setup", str(setup)) != 0
    assert "plain" in capsys.readouterr().err
    assert listing(fleets()) == []


def test_a_lock_whose_records_carry_no_date_is_refused_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev, setup = dev_setup(tmp_path, monkeypatch)
    record = dev / flt05_records()[1]
    undated = json.loads(record.read_text(encoding="utf-8"))
    undated["validated_at"] = None
    record.write_text(json.dumps(undated), encoding="utf-8")

    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) != 0
    assert "validated_at" in capsys.readouterr().err
    assert listing(fleets()) == []


def test_tag_renames_a_folder_promoted_before_the_ruling_to_its_lock_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _dev, setup = dev_setup(tmp_path, monkeypatch)
    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) == 0
    # A folder as `promote` wrote it before the ruling: the same files, no tag.
    (fleets() / TAGGED).rename(fleets() / "flt-05")
    untagged = tree(fleets() / "flt-05")
    name_live("flt-05")

    assert cli("fleet", "tag", "flt-05") == 0
    assert sorted(path.name for path in fleets().iterdir()) == [TAGGED]
    assert tree(fleets() / TAGGED) == untagged, "tag is a rename and nothing else"
    assert json.loads(live_json().read_text(encoding="utf-8"))["fleet"] == TAGGED, (
        "the live pointer named the folder, so it follows the rename"
    )
    assert TAGGED in capsys.readouterr().out


def test_tag_refuses_a_tagged_name_a_missing_folder_and_an_occupied_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dev, setup = dev_setup(tmp_path, monkeypatch)
    assert cli("fleet", "tag", "flt-05") != 0, "nothing to tag"

    assert cli("fleet", "promote", "flt-05", "--setup", str(setup)) == 0
    assert cli("fleet", "tag", TAGGED) != 0, "already tagged"

    (fleets() / TAGGED).rename(fleets() / "flt-05")
    occupied = fleets() / TAGGED
    occupied.mkdir()
    (occupied / "keep.txt").write_text("mine", encoding="utf-8")
    before = (listing(fleets()), tree(fleets()))
    assert cli("fleet", "tag", "flt-05") != 0, "the tagged name is taken"
    assert (listing(fleets()), tree(fleets())) == before


def test_a_live_name_is_a_fleet_or_a_fleet_at_a_date() -> None:
    from mcgyvr.fleet.roots import is_fleet_name, layout_of, split_name

    assert split_name("b-small@2026-09-16") == ("b-small", "2026-09-16")
    assert split_name("b-small") == ("b-small", None)
    assert layout_of("b-small@2026-09-16") == "b-small"
    assert layout_of("b-small") == "b-small"
    assert is_fleet_name("b-small@2026-09-16")
    assert is_fleet_name("b-small")
    for bad in ("b-small@", "b-small@today", "b-small@2026-13-01", "@2026-09-16"):
        assert not is_fleet_name(bad), bad
