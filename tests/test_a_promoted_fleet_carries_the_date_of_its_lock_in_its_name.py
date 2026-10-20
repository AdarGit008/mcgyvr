"""A promoted fleet carries the date of its lock in its name.

Every fleet is tagged with a date: it is promoted with the date in its name,
because switching between verified fleets is a common action at runtime.

* :func:`mcgyvr.fleet.promote.promote` is handed the plain fleet name and
  writes ``~/.mcgyvr/fleets/<fleet>@<YYYY-MM-DD>/``, where the
  date is the lock's own: the latest ``validated_at`` among the combination
  records the lock wrote for that fleet's layout. Never today's date.
* Inside the folder nothing is renamed: ``fleet.yaml`` keys the fleet by its
  plain name and the lock sits at ``lock/<fleet>.json``, so a tagged
  folder and a folder promoted before tagging have one shape.
* A re-lock on a new date gets a new folder beside the old one, which stays as
  a verified config. The same tagged name is refused, as any existing folder.
* A name that already carries a tag is refused by ``promote``: the date is the
  lock's to say. A lock whose records carry no ``validated_at`` cannot be dated
  and is refused, with nothing written.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.fleetlocks import (
    EVIDENCE,
    LOCK_DATE,
    MODELLED,
    POLICY,
    TOLERANCES,
    cli,
    dev_setup,
    fleets,
    flt05_records,
    listing,
    promote_fleet,
    tree,
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
    from mcgyvr.fleet.promote import promote

    written_to = promote(dev, setup, "flt-05")

    assert [path.name for path in fleets().iterdir()] == [TAGGED], (
        "the promoted folder is named <fleet>@<the lock's validated_at date>"
    )
    folder = fleets() / TAGGED
    assert written_to == folder, "promote returns the folder it wrote"

    lock, record = flt05_records()
    written = tree(folder)
    assert set(written) == {"fleet.yaml", "policy.yaml", lock, record}, (
        "inside the folder the fleet keeps its plain name: the lock is "
        "lock/flt-05.json, not flt-05@date.json"
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
    assert lock_date(dev, MODELLED, "flt-05") == LOCK_DATE
    # flt-02's one record is dated 10:30 the same day.
    assert lock_date(dev, MODELLED, "flt-02") == LOCK_DATE

    _relock(dev, "2026-09-12T08:00:00Z")
    assert lock_date(dev, MODELLED, "flt-05") == "2026-09-12"


def test_a_relock_on_a_new_date_is_promoted_beside_the_old_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dev, setup = dev_setup(tmp_path, monkeypatch)
    assert promote_fleet(dev, setup, "flt-05") == 0
    old = tree(fleets() / TAGGED)

    assert promote_fleet(dev, setup, "flt-05") != 0, (
        "the same lock promoted twice is the same tagged folder, which exists"
    )
    assert sorted(path.name for path in fleets().iterdir()) == [TAGGED]

    _relock(dev, "2026-09-12T08:00:00Z")
    assert promote_fleet(dev, setup, "flt-05") == 0
    assert sorted(path.name for path in fleets().iterdir()) == [
        TAGGED,
        "flt-05@2026-09-12",
    ]
    assert tree(fleets() / TAGGED) == old, "the earlier verified config was touched"


def test_promote_takes_the_plain_fleet_name_and_refuses_a_tagged_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev, setup = dev_setup(tmp_path, monkeypatch)
    assert promote_fleet(dev, setup, TAGGED) != 0
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

    assert promote_fleet(dev, setup, "flt-05") != 0
    assert "validated_at" in capsys.readouterr().err
    assert listing(fleets()) == []


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
