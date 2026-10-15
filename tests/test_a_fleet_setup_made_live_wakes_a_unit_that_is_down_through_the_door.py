"""A fleet ``mcgyvr setup`` made live wakes a unit that is down, through the door.

Owner, 2026-10-14: auto-wake is on. Setup writes ``serving.enable_sleep_wake:
true`` and a ``serving.compose_dir`` holding the launch specs it emitted -- the
staged folder, which is kept -- so the live fleet it promotes yields a waker
(:func:`mcgyvr.wake.for_config`), and a request refused by a unit that is down
is a door ``serve up`` of its launch spec, then the request again. Live wakes
only a rig its lock names (:func:`mcgyvr.fleet.admit.host_is_locked`), which
holds both for a fleet locked from its sample's stamp and for one locked on no
evidence.

The rig is :class:`tests.setup_door.FakeRig` behind the door; nothing reaches
a machine.
"""

from __future__ import annotations

import pytest

from mcgyvr import cli, wake
from mcgyvr.config import load
from mcgyvr.fleet.admit import host_is_locked
from mcgyvr.fleet.roots import data_home, live_fleet_dir
from mcgyvr.runner import RefusedConnectionError
from tests import setup_door as sd

START = "Start the serving containers"
LOCK = "Lock the fleet and name it live?"
UNSAMPLED = "no evidence"

#: Two ways setup makes its own fleet live: from a green sample's stamp, and,
#: having started nothing, on no evidence once acknowledged.
WAYS = {
    "stamped": {START: True, LOCK: True},
    "unsampled": {START: False, UNSAMPLED: True},
}


@pytest.mark.parametrize("way", sorted(WAYS))
def test_the_live_fleet_setup_made_wakes_a_refused_unit_through_the_door(
    monkeypatch: pytest.MonkeyPatch, way: str
) -> None:
    rig = sd.FakeRig()
    sd.interactive(monkeypatch, rig, WAYS[way])
    assert cli.main(["setup"]) == 0
    (staged,) = (data_home() / "setup").iterdir()
    live = live_fleet_dir()
    assert live is not None

    config = load()

    assert config.path == live
    assert config.get("serving.enable_sleep_wake") is True
    assert config.get("serving.compose_dir") == str(staged)
    assert (staged / f"compose.{sd.RIG}.yml").is_file()
    assert host_is_locked(live, sd.RIG)
    waker = wake.for_config(config)
    assert waker is not None

    rig.calls.clear()
    rig.up.clear()
    (rung,) = config.ladder.names
    sent: list[int] = []

    def send() -> str:
        sent.append(1)
        if not rig.up:
            raise RefusedConnectionError(f"{rung}: connection refused")
        return "answered"

    assert waker.dispatching(rung, send) == "answered"
    assert len(sent) == 2
    ((verb, direction, host, spec, *_),) = rig.calls
    assert (verb, host, spec) == ("serve", sd.RIG, f"compose.{sd.RIG}.yml")
    assert direction in ("up", "wake")


def test_the_staged_setup_says_auto_wake_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sd.interactive(monkeypatch, sd.FakeRig(), {START: False, UNSAMPLED: False})
    assert cli.main(["setup"]) == 0
    (staged,) = (data_home() / "setup").iterdir()

    config = load(staged)

    assert config.get("serving.enable_sleep_wake") is True
    assert config.get("serving.compose_dir") == str(staged)
