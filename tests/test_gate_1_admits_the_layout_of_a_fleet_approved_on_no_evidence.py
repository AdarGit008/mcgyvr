"""Gate 1 admits a live ``serve up`` of the layout a fleet approved on no evidence.

Owner, 2026-10-15: a lock ``mcgyvr setup`` approved on no evidence
(:func:`mcgyvr.fleet.lock.write_unsampled`) writes no combination record, as
nothing was validated, so gate 1 -- which admits a live ``serve up`` only for
containers the lock's records name -- refused every unit of an acknowledged
unsampled fleet, and the waker that passed it could not wake it through the
door. Gate 1 now also admits the containers such a lock lays out on the rig,
by the rule :func:`mcgyvr.fleet.admit.host_is_locked` already reads: only
while the ``fleet.yaml`` beside the lock still hashes to the lock's pin, and
only the units that layout places on that rig, by the container the lock
pinned for each (its ``containers``, as a measured lock's records name each
unit's container): a container edited into ``fleet.yaml`` afterwards leaves
the layout's hash as it was, and is refused by gate 1 and by
``host_is_locked`` alike. A lock measured from dev evidence answers from its
records alone, exactly as before.

The door's first gate is called in this process with the variables the door
would have set; nothing reaches a machine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests._helpers import by_path
from tests._paths import REPO
from tests.doors import UNITS
from tests.fleetlocks import BOX1_EVIDENCE, BOX1_FLEET

GATE_1 = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "01-round.py"
RIG = "box.invalid"
RIG_ID = "rig-" + "2" * 64
CONTAINER = "mcgyvr-box-local"


def _gate() -> Any:
    return by_path("gate_01_round", GATE_1)


def _unsampled_live(tmp_path: Path) -> Path:
    """An acknowledged unsampled fleet with one unit on ``RIG``, named live."""
    from mcgyvr.fleet.lock import OWN_FLEET, write_unsampled
    from mcgyvr.fleet.promote import promote, use

    setup = tmp_path / "setup"
    setup.mkdir()
    units = {
        "local": {
            "address": f"http://{RIG}:8080/v1",
            "model": "small-model",
            "width": 1,
            "rig": RIG,
            "container": CONTAINER,
        }
    }
    (setup / "fleet.yaml").write_text(
        yaml.safe_dump({"profile": "live", "units": units}), encoding="utf-8"
    )
    policy = {"use_case": "coding", "ladder": ["local"]}
    policy["journal"] = {"dir": str(tmp_path / "journal")}  # type: ignore[assignment]
    (setup / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    dev = tmp_path / "dev"
    write_unsampled(dev, setup, rigs={RIG: RIG_ID}, acknowledged=True)
    folder = promote(dev, dev / "setup", OWN_FLEET)
    use(folder.name)
    return folder


def _serve_up(
    monkeypatch: pytest.MonkeyPatch, host: str, *containers: str
) -> int | None:
    """Gate 1's live check of a ``serve up`` of ``containers`` on ``host``:
    ``None`` admitted, else the exit status it refused with."""
    monkeypatch.setenv("RUN_HOST", host)
    monkeypatch.setenv("RUN_SERVE_EXPECTED", " ".join(containers))
    monkeypatch.delenv("RUN_SERVE_ONLY", raising=False)
    try:
        _gate().refuse_unless_the_fleet_lock_names("up", "live")
    except SystemExit as refused:
        return int(refused.code or 0)
    return None


def test_an_acknowledged_unsampled_fleets_container_is_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unsampled_live(tmp_path)

    assert _serve_up(monkeypatch, RIG, CONTAINER) is None


def test_a_container_its_layout_does_not_name_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _unsampled_live(tmp_path)

    assert _serve_up(monkeypatch, RIG, CONTAINER, "mcgyvr-box-stranger") == 2
    said = capsys.readouterr().err
    assert "gate 1:" in said and "names mcgyvr-box-stranger, which" in said, said
    assert _serve_up(monkeypatch, "other.invalid", CONTAINER) == 2, (
        "a rig the layout does not place the unit on"
    )


def test_an_edited_layout_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _unsampled_live(tmp_path)
    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    live["fleets"]["own"]["layout"][RIG] = [["local", "asleep"]]
    (folder / "fleet.yaml").write_text(yaml.safe_dump(live), encoding="utf-8")

    assert _serve_up(monkeypatch, RIG, CONTAINER) == 2, "an edited layout"


def test_the_lock_pins_each_units_container_and_an_edited_one_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from mcgyvr.fleet.admit import host_is_locked
    from mcgyvr.fleet.roots import LOCK_DIR

    folder = _unsampled_live(tmp_path)
    lock = json.loads((folder / LOCK_DIR / "own.json").read_text(encoding="utf-8"))
    assert lock["containers"] == {RIG: {"local": CONTAINER}}
    assert _serve_up(monkeypatch, RIG, CONTAINER) is None
    assert host_is_locked(folder, RIG) is True

    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    live["units"]["local"]["container"] = "mcgyvr-box-edited"
    (folder / "fleet.yaml").write_text(yaml.safe_dump(live), encoding="utf-8")

    assert _serve_up(monkeypatch, RIG, "mcgyvr-box-edited") == 2, "edited in"
    assert _serve_up(monkeypatch, RIG, CONTAINER) == 2, "no longer laid out"
    assert host_is_locked(folder, RIG) is False


def test_a_measured_lock_answers_from_its_records_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock measured from dev evidence admits the containers its records
    name, and nothing its ``fleet.yaml`` lays out besides: a container renamed
    there leaves the layout's pin as it was, and is still refused."""
    from mcgyvr.fleet import lock

    live = Path.home() / ".mcgyvr"
    live.mkdir(parents=True, exist_ok=True)
    (live / "live.json").write_text('{"fleet": "flt-01"}', encoding="utf-8")
    folder = live / "fleets" / "flt-01"
    lock.write(
        folder,
        BOX1_FLEET,
        BOX1_EVIDENCE,
        policy={"ladder": ["a", "b"]},
        tolerances={"warm_decode_class_pct": {"llamacpp": 5.0}},
    )
    beside: dict[str, Any] = yaml.safe_load(yaml.safe_dump(BOX1_FLEET))
    beside["units"]["a"]["container"] = "mcgyvr-box1-renamed"
    (folder / "fleet.yaml").write_text(yaml.safe_dump(beside), encoding="utf-8")

    assert _serve_up(monkeypatch, "box1", *UNITS) is None
    assert _serve_up(monkeypatch, "box1", "mcgyvr-box1-renamed") == 2
