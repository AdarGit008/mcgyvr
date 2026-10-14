"""``mcgyvr setup`` samples the fleet it started, stamps it, and locks it on a yes.

Owner, 2026-10-14: setup runs READ -> PLAN -> STAGE -> START -> SAMPLE ->
STAMP -> LOCK -> promote -> use. Once the containers are up, the staged setup
is laid out as the user's own fleet and sampled through the door
(``read --fleet own`` of the rig, ``--probe U --load WxN`` of every awake
unit, and a last read), with the use case's sample task between them; the
sample is judged and stamped (:func:`mcgyvr.fleet.stamp.stamp`); behind "Lock
the fleet and name it live? [y/N]" the stamp is locked
(:func:`mcgyvr.fleet.lock.write_from_stamp`), promoted and named live. A red
sample is never locked, and its reasons are printed.

The rig is :class:`tests.setup_door.FakeRig` behind the door; nothing reaches
a machine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from mcgyvr import cli
from mcgyvr.fleet import ids, sampler
from mcgyvr.fleet.roots import data_home, fleets_dir, live_file
from mcgyvr.fleet.stamp import stamps_dir
from tests import setup_door as sd

LOCK = "Lock the fleet and name it live?"
START = "Start the serving containers"


def _staged() -> Path:
    (staged,) = (data_home() / "setup").iterdir()
    return staged


def test_a_green_sample_is_stamped_locked_promoted_and_named_live(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rig = sd.FakeRig()
    asked = sd.interactive(monkeypatch, rig, {START: True, LOCK: True})

    assert cli.main(["setup"]) == 0

    out = capsys.readouterr().out
    assert [q.split("?")[0] + "?" for q in asked] == [
        f"{START} on {sd.RIG}?",
        LOCK,
    ]
    staged = _staged()
    doc = yaml.safe_load((staged / "fleet.yaml").read_text(encoding="utf-8"))
    (unit,) = doc["fleets"]["own"]["layout"][sd.RIG]
    assert unit[1] == "awake"
    assert doc["rigs"][sd.RIG]["rig_id"] == ids.rig_id(sd.reading())

    (stamp,) = (stamps_dir() / "own").iterdir()
    assert stamp.name == staged.name, "the stamp is named by the setup run"
    assert f"stamped: own ({stamp})" in out

    live = json.loads(live_file().read_text(encoding="utf-8"))["fleet"]
    assert live.startswith("own@")
    assert (fleets_dir() / live / "fleet.yaml").is_file()
    assert "Approved your own fleet for live runs on its sample's evidence" in out


def test_every_door_call_is_the_sample_in_order_under_the_staged_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = sd.FakeRig()
    sd.interactive(monkeypatch, rig, {START: True, LOCK: True})

    assert cli.main(["setup"]) == 0

    staged = _staged()
    doc = yaml.safe_load((staged / "fleet.yaml").read_text(encoding="utf-8"))
    ((name, _),) = doc["fleets"]["own"]["layout"][sd.RIG]
    assert rig.calls == [
        ("serve", "up", sd.RIG, f"compose.{sd.RIG}.yml"),
        ("read", sd.RIG, "own", (), None),
        ("read", sd.RIG, "own", (name,), f"1x{sd.WINDOW}"),
        ("read", sd.RIG, "own", (), None),
    ]
    assert rig.configs == [str(staged)] * 4


def test_the_staged_unit_states_the_reply_its_measured_rate_finishes_in_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = sd.FakeRig()
    sd.interactive(monkeypatch, rig, {START: True, LOCK: False})

    assert cli.main(["setup"]) == 0

    doc = yaml.safe_load((_staged() / "fleet.yaml").read_text(encoding="utf-8"))
    ((name, _),) = doc["fleets"]["own"]["layout"][sd.RIG]
    unit = doc["units"][name]
    assert unit["room_mib"] == sd.ROOM_MIB
    assert unit["output_tokens"] == int(sd.WARM * unit["request_timeout_s"])
    assert unit["unit_id"] == sampler.unit_id(unit)


def test_a_no_to_the_lock_leaves_the_stamp_and_names_nothing_live(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sd.interactive(monkeypatch, sd.FakeRig(), {START: True, LOCK: False})

    assert cli.main(["setup"]) == 0

    out = capsys.readouterr().out
    (stamp,) = (stamps_dir() / "own").iterdir()
    assert f"mcgyvr fleet lock --stamp {stamp}" in out
    assert not live_file().exists()


def test_a_red_sample_is_never_locked_and_says_why(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = sd.interactive(monkeypatch, sd.FakeRig(), {START: True, LOCK: True})
    monkeypatch.setattr(
        sampler, "run_contract", lambda argv: sd.accepted(argv, outcome="ladder_spent")
    )

    assert cli.main(["setup"]) == 0

    out = capsys.readouterr().out
    assert LOCK not in " ".join(asked), "a red sample is not offered for locking"
    assert "no stamp: own" in out
    assert "gate" in out and "ladder_spent" in out, out
    assert "The sample was red" in out
    assert not stamps_dir().exists() or not list(stamps_dir().rglob("evidence.json"))
    assert not live_file().exists()


def test_a_door_read_that_fails_is_a_red_sample(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sd.interactive(monkeypatch, sd.FakeRig(read_fails=True), {START: True, LOCK: True})

    assert cli.main(["setup"]) == 0

    captured = capsys.readouterr()
    assert "read --host" in captured.err and "exited 1" in captured.err
    assert "no stamp: own" in captured.out
    assert not live_file().exists()
