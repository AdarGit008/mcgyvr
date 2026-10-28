"""A fleet that could not be sampled is locked, on no evidence, only once the
user acknowledges it; and it goes live the way every fleet does.

One script locks a fleet. A fleet ``mcgyvr setup`` bound that no
sample could run on (hosted units, or the user's own machines read but not
sampled) IS locked: :func:`mcgyvr.fleet.lock.write_unsampled` writes the lock
of the fleet ``own``, approved by the product itself on empty evidence, and
refuses unless the caller says the user acknowledged that. From there the
chain is every live fleet's: :func:`mcgyvr.fleet.promote.promote` then
:func:`mcgyvr.fleet.promote.use`. Nothing else writes a fleet folder.

* The lock pins the layout: each read rig laid out with its units awake, and
  each such unit given the id the lock pins. Hosted units are carried as they
  are, and a lock with no combination record is dated by its approval.
* Refused, with no lock written: no acknowledgment; a unit on a rig that was
  not read; a read rig with no unit on it; a hosted unit at a machine of the
  user's; a setup that already lays out rigs or fleets; a setup that cannot be
  read.
* A second approval on one day is its own folder, ``own@<day>-2``.

The machines are invented; nothing is read.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.fleet.promote import LOCK_DIR

HOSTED = "api_hosted-model"
LOCAL = "local_small-model"
RIG = "box.invalid"
RIG_ID = "rig-" + "2" * 64


def _hosted(address: str = "https://api.hosted.example/v1") -> dict[str, Any]:
    return {
        "address": address,
        "model": "hosted-model",
        "api_key_env": "K",
        "width": 1,
        "output_tokens": 32768,
    }


def _on_rig(rig: str = RIG) -> dict[str, Any]:
    return {
        "address": f"http://{rig}:8080/v1",
        "model": "small-model",
        "width": 1,
        "rig": rig,
    }


def _setup(tmp_path: Path, units: dict[str, Any], **more: Any) -> Path:
    setup = tmp_path / "setup"
    setup.mkdir(exist_ok=True)
    fleet = {"units": units, **more}
    (setup / "fleet.yaml").write_text(yaml.safe_dump(fleet), encoding="utf-8")
    policy = {
        "use_case": "mcgyvr-code",
        "ladder": list(units),
        "journal": {"dir": str(tmp_path / "journal")},
    }
    (setup / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    return setup


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _live(dev: Path, setup: Path, rigs: dict[str, str]) -> Path:
    from mcgyvr.fleet.lock import OWN_FLEET, write_unsampled
    from mcgyvr.fleet.promote import promote, use

    tree = write_unsampled(dev, setup, rigs=rigs, acknowledged=True)
    assert tree == dev / LOCK_DIR
    folder = promote(dev, dev / "setup", OWN_FLEET)
    assert use(folder.name).name == folder.name
    return folder


def test_a_hosted_fleet_is_locked_promoted_and_named_live(tmp_path: Path) -> None:
    from mcgyvr.fleet.lock import is_own
    from mcgyvr.fleet.promote import lock_date
    from mcgyvr.fleet.roots import fleets_dir, live_fleet

    setup = _setup(tmp_path, {HOSTED: _hosted()})

    folder = _live(tmp_path / "dev", setup, {})

    assert folder == fleets_dir() / f"own@{_today()}"
    assert live_fleet() == folder.name and is_own(folder.name)
    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    assert "profile" not in live
    assert live["units"] == {HOSTED: _hosted()}, "a hosted unit is carried as it is"
    assert live["fleets"] == {"own": {"layout": {}}}
    policy = yaml.safe_load((folder / "policy.yaml").read_text(encoding="utf-8"))
    assert policy["ladder"] == [HOSTED]
    lock = json.loads((folder / LOCK_DIR / "own.json").read_text(encoding="utf-8"))
    assert lock["approved_by"] == "mcgyvr setup" and lock["approved_at"]
    assert lock["next"] == [] and lock["switches"] == []
    assert not (folder / LOCK_DIR / "rigs").exists(), "no evidence, no record"
    assert lock_date(folder, live, "own") == _today()


def test_a_read_rig_is_laid_out_awake_and_its_units_pinned(tmp_path: Path) -> None:
    from mcgyvr.fleet.admit import admit_live

    setup = _setup(tmp_path, {LOCAL: _on_rig(), HOSTED: _hosted()})

    folder = _live(tmp_path / "dev", setup, {RIG: RIG_ID})

    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    assert live["rigs"] == {RIG: {"rig_id": RIG_ID}}
    assert live["fleets"] == {"own": {"layout": {RIG: [[LOCAL, "awake"]]}}}
    unit_id = live["units"][LOCAL]["unit_id"]
    assert unit_id.startswith("unt-")
    assert live["units"][HOSTED] == _hosted()
    policy = yaml.safe_load((folder / "policy.yaml").read_text(encoding="utf-8"))
    assert policy["ladder"] == [LOCAL, HOSTED]
    plan = admit_live(
        folder,
        live,
        "own",
        {RIG: {"rig_id": RIG_ID, "units": {unit_id: "awake"}, "foreign": []}},
    )
    assert plan.clean == [] and plan.restore == [], plan


def test_a_second_approval_of_a_day_is_its_own_folder(tmp_path: Path) -> None:
    from mcgyvr.fleet.roots import fleets_dir

    setup = _setup(tmp_path, {HOSTED: _hosted()})
    first = _live(tmp_path / "dev1", setup, {})
    before = (first / "fleet.yaml").read_bytes()

    second = _live(tmp_path / "dev2", setup, {})
    third = _live(tmp_path / "dev3", setup, {})

    assert second.name == f"own@{_today()}-2" and third.name == f"own@{_today()}-3"
    assert (first / "fleet.yaml").read_bytes() == before
    assert sorted(p.name for p in fleets_dir().iterdir()) == sorted(
        [first.name, second.name, third.name]
    )


REFUSED = {
    "unacknowledged": ({HOSTED: _hosted()}, {}, "acknowledg"),
    "unread rig": ({LOCAL: _on_rig()}, {}, "not approved"),
    "other unread rig": (
        {LOCAL: _on_rig(), "other": _on_rig("other.invalid")},
        {RIG: RIG_ID},
        "other.invalid",
    ),
    "empty rig": ({HOSTED: _hosted()}, {RIG: RIG_ID}, "no unit on"),
    "users machine": (
        {HOSTED: _hosted("http://127.0.0.1:8080/v1")},
        {},
        "machine of yours",
    ),
    "users machine beside a rig": (
        {LOCAL: _on_rig(), HOSTED: _hosted("http://127.0.0.1:8080/v1")},
        {RIG: RIG_ID},
        "machine of yours",
    ),
}


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_a_fleet_it_cannot_vouch_for_is_refused_and_nothing_is_locked(
    tmp_path: Path, case: str
) -> None:
    from mcgyvr.fleet.lock import LockRefusedError, write_unsampled

    units, rigs, word = REFUSED[case]
    setup = _setup(tmp_path, units)
    dev = tmp_path / "dev"

    with pytest.raises(LockRefusedError, match=word):
        write_unsampled(dev, setup, rigs=rigs, acknowledged=case != "unacknowledged")
    assert not (dev / LOCK_DIR).exists()


@pytest.mark.parametrize("laid_out", ["rigs", "fleets"])
def test_a_setup_that_lays_out_its_own_fleet_is_locked_from_its_evidence(
    tmp_path: Path, laid_out: str
) -> None:
    from mcgyvr.fleet.lock import LockRefusedError, write_unsampled

    more: dict[str, Any] = (
        {"rigs": {RIG: {"rig_id": RIG_ID}}}
        if laid_out == "rigs"
        else {"fleets": {"mine": {"layout": {}}}}
    )
    setup = _setup(tmp_path, {HOSTED: _hosted()}, **more)

    with pytest.raises(LockRefusedError, match="lays out"):
        write_unsampled(tmp_path / "dev", setup, rigs={}, acknowledged=True)
    assert not (tmp_path / "dev" / LOCK_DIR).exists()


def test_a_setup_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    from mcgyvr.fleet.lock import LockRefusedError, write_unsampled

    with pytest.raises(LockRefusedError, match=r"fleet\.yaml"):
        write_unsampled(
            tmp_path / "dev", tmp_path / "nowhere", rigs={}, acknowledged=True
        )


def test_is_own_recognises_a_lock_of_the_own_fleet_and_nothing_else() -> None:
    """A folder of the fleet ``own`` holding its lock is the user's own: one
    ``mcgyvr init`` approved before the rename, or one setup locked from its
    sample's stamp. A folder whose lock is no lock, or that has none, is not."""
    from mcgyvr.fleet.lock import is_own
    from mcgyvr.fleet.roots import fleets_dir

    records: dict[str, dict[str, str]] = {
        "own@2026-01-02": {"approved_by": "mcgyvr init"},
        "own@2026-01-03": {},
        "own@2026-01-05": {"layout_sha256": "0" * 64},
        "lab@2026-01-05": {"layout_sha256": "0" * 64},
    }
    for name, record in records.items():
        folder = fleets_dir() / name
        (folder / LOCK_DIR).mkdir(parents=True)
        (folder / LOCK_DIR / f"{name.split('@')[0]}.json").write_text(
            json.dumps(record), encoding="utf-8"
        )

    assert is_own("own@2026-01-02") is True
    assert is_own("own@2026-01-03") is False
    assert is_own("own@2026-01-04") is False
    assert is_own("own@2026-01-05") is True
    assert is_own("lab@2026-01-05") is False


def test_a_read_rig_of_the_own_fleet_is_a_locked_host(tmp_path: Path) -> None:
    """A live wake asks :func:`mcgyvr.fleet.admit.host_is_locked` of the live
    folder. A lock approved on no evidence writes no combination record, so its
    layout answers instead: a rig it lays out, under the rig id it pins, is
    locked, and nothing else is, nor a rig edited into the layout afterwards."""
    from mcgyvr.fleet.admit import host_is_locked

    setup = _setup(tmp_path, {LOCAL: _on_rig(), HOSTED: _hosted()})
    folder = _live(tmp_path / "dev", setup, {RIG: RIG_ID})

    assert host_is_locked(folder, RIG) is True
    assert host_is_locked(folder, "other.invalid") is False

    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    live["rigs"]["other.invalid"] = {"rig_id": "rig-" + "4" * 64}
    live["units"]["other"] = {**_on_rig("other.invalid"), "unit_id": "unt-x"}
    live["fleets"]["own"]["layout"]["other.invalid"] = [["other", "awake"]]
    (folder / "fleet.yaml").write_text(yaml.safe_dump(live), encoding="utf-8")
    assert host_is_locked(folder, "other.invalid") is False, "the pin is the lock's"
    assert host_is_locked(folder, RIG) is False, "an edited layout matches no pin"
