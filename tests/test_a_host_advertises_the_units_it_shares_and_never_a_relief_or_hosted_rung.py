"""A host advertises the units it shares, and never a relief or a hosted rung.

A host runs their own units and may let riders the hub matches use open slots
of them (hitchhike, ``units.<name>.rider_slots``). The host's agent tells the
hub which, in a ``unit_advert`` (:mod:`mcgyvr.rig.hitchhike`):

* **What is shared.** A unit of the ladder, in ladder order, with
  ``rider_slots`` of 1 or more, that needs no key and is not a relief rung
  (another person's unit, lent to this host as a rider). One unit per model,
  the first the ladder climbs; at most 16. A unit is advertised with its
  ``width`` as its slots, its ``window`` as the context of each slot, and its
  ``rider_slots`` as the most rides at once; one whose window is not stated,
  or whose width or window the hub cannot carry, is not advertised, and the
  agent says so once.
* **Its id** is the unit's name where the name is already an id, the name
  with every other character made a dash (and cut to 64) where it is not, and
  a short digest of the name where that leaves no letter or digit or is taken
  by a unit before it: the same while the setup is.
* **Its free slots** are what the host's own requests leave free now: the
  unit's server's count of requests in flight, less the rides this agent is
  serving on it (a ride is not the host's own), never below none or above the
  unit's width. A server that does not say is read as full, so its slots are
  never offered on a guess.
* **When.** After the hello is acked, then when the set or a unit's free
  slots changed (checked at the heartbeat and when a ride ends, at most once a
  second), and at least every 60 s while anything is shared. A setup that
  shares nothing sends nothing; one that stops sharing sends the empty set,
  which withdraws it. Nothing is sent while the channel is down.
* **The hello says so.** ``hitchhike_units`` is one of the agent's features,
  and a rig that lends no session but shares a unit still names it, with no
  roles, so the hub takes its adverts.

Nothing here touches a network: the server's count, the clock and the thread a
check runs on are handed in.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import Config, parse
from tests import rig_pool_fakes as fakes
from tests import rig_schema


def _setup(
    *units: dict[str, Any], ladder: list[str] | None = None, relief: str = ""
) -> Config:
    lines = ["units:"]
    for unit in units:
        lines.append(f"  {unit['name']}:")
        lines.append(f"    address: {unit.get('address', 'http://127.0.0.1:8080')}")
        for key, value in unit.items():
            if key not in ("name", "address"):
                lines.append(f"    {key}: {value}")
    names = ladder if ladder is not None else [unit["name"] for unit in units]
    lines.append(f"ladder: [{', '.join(names)}]")
    return parse("\n".join(lines) + "\n" + relief)


def _unit(name: str, model: str, **more: Any) -> dict[str, Any]:
    return {
        "name": name,
        "model": model,
        "width": 4,
        "window": 8192,
        "rider_slots": 2,
        **more,
    }


# --- what is shared -----------------------------------------------------------------


def test_the_shared_units_are_the_ladders_own_in_its_order_with_their_facts() -> None:
    from mcgyvr.rig import hitchhike

    config = _setup(
        _unit(
            "big",
            "qwen-32b",
            address="http://127.0.0.1:8081",
            width=2,
            rider_slots=1,
            window=4096,
        ),
        _unit("small", "qwen-7b", address="http://127.0.0.1:8080/v1"),
        _unit("quiet", "llama-8b", rider_slots=0),
        ladder=["small", "quiet", "big"],
    )

    shared, notes = hitchhike.shared_units(config)

    assert [(s.unit_id, s.model, s.slots, s.ctx, s.rider_cap) for s in shared] == [
        ("small", "qwen-7b", 4, 8192, 2),
        ("big", "qwen-32b", 2, 4096, 1),
    ]
    assert [s.address for s in shared] == [
        "http://127.0.0.1:8080/v1",
        "http://127.0.0.1:8081",
    ]
    assert notes == ()


def test_a_relief_rung_is_never_shared_even_of_a_model_the_host_runs() -> None:
    from mcgyvr.rig import hitchhike

    relief = (
        "relief:\n"
        "  hitchhike-" + "a" * 32 + ":\n"
        "    address: https://hub.example.org/v1\n"
        "    model: hitchhike@" + "a" * 32 + "\n"
        "    api_key_env: MCGYVR_HUB_API_KEY\n"
        "    width: 4\n"
        "    position: within\n"
    )
    config = _setup(_unit("own", "qwen-7b"), relief=relief)

    shared, _ = hitchhike.shared_units(config)

    assert [s.unit_id for s in shared] == ["own"]
    assert all(not s.model.startswith("hitchhike@") for s in shared)


def test_a_hosted_rung_is_never_shared() -> None:
    from mcgyvr.rig import hitchhike

    config = _setup(
        _unit("hosted", "gpt-x", rider_slots=0, api_key_env="SOME_KEY"),
        _unit("own", "qwen-7b"),
    )

    shared, _ = hitchhike.shared_units(config)

    assert [s.unit_id for s in shared] == ["own"]


def test_one_unit_per_model_the_first_the_ladder_climbs_and_the_other_is_said() -> None:
    from mcgyvr.rig import hitchhike

    config = _setup(
        _unit("second", "qwen-7b", address="http://127.0.0.1:8082"),
        _unit("first", "qwen-7b"),
        ladder=["first", "second"],
    )

    shared, notes = hitchhike.shared_units(config)

    assert [s.unit_id for s in shared] == ["first"]
    assert len(notes) == 1 and "second" in notes[0] and "qwen-7b" in notes[0]


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"window": None}, "window"),
        ({"window": 255}, "window"),
        ({"window": (1 << 20) + 1}, "window"),
        ({"width": 17}, "width"),
    ],
)
def test_a_unit_the_hub_cannot_carry_is_not_shared_and_is_said(
    changes: dict[str, Any], says: str
) -> None:
    from mcgyvr.rig import hitchhike

    unit = _unit("odd", "qwen-7b")
    unit.update({k: v for k, v in changes.items() if v is not None})
    if changes.get("window", 0) is None:
        del unit["window"]
    config = _setup(unit, _unit("fine", "qwen-14b"))

    shared, notes = hitchhike.shared_units(config)

    assert [s.unit_id for s in shared] == ["fine"]
    assert len(notes) == 1 and "odd" in notes[0] and says in notes[0]


def test_at_most_sixteen_units_are_shared_and_the_rest_is_said() -> None:
    from mcgyvr.rig import hitchhike, sessionwire

    config = _setup(
        *[
            _unit(f"u{i}", f"model-{i}", address=f"http://127.0.0.1:{8000 + i}")
            for i in range(sessionwire.MAX_UNITS + 2)
        ]
    )

    shared, notes = hitchhike.shared_units(config)

    assert [s.unit_id for s in shared] == [
        f"u{i}" for i in range(sessionwire.MAX_UNITS)
    ]
    assert len(notes) == 2 and all("16" in note for note in notes)


def test_a_units_id_is_its_name_made_an_id_and_stays_while_the_setup_does() -> None:
    from mcgyvr.rig import hitchhike, protocol

    def ids() -> list[str]:
        config = _setup(
            _unit("plain_name-1", "m1", address="http://127.0.0.1:8001"),
            _unit("qwen.coder 7b", "m2", address="http://127.0.0.1:8002"),
            _unit("qwen-coder-7b", "m3", address="http://127.0.0.1:8003"),
            _unit("é", "m4", address="http://127.0.0.1:8004"),
            _unit("x" * 70, "m5", address="http://127.0.0.1:8005"),
        )
        return [s.unit_id for s in hitchhike.shared_units(config)[0]]

    found = ids()
    assert found[:2] == ["plain_name-1", "qwen-coder-7b"]
    assert found[2] != "qwen-coder-7b"  # taken by the unit before it
    assert found[3] != "-"
    assert found[4] == "x" * 64
    assert all(protocol.MESSAGE_ID.fullmatch(unit_id) for unit_id in found)
    assert len(set(found)) == len(found)
    assert ids() == found


# --- free slots -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("in_flight", "riding", "free"),
    [
        (0, 0, 4),
        (1, 0, 3),
        (3, 1, 2),  # one of the three in flight is a ride, not the host's
        (2, 2, 4),
        (1, 3, 4),  # a ride admitted that has not reached the server yet
        (9, 0, 0),  # never below none
        (None, 0, 0),  # a server that does not say is read as full
    ],
)
def test_free_slots_are_what_the_hosts_own_requests_leave(
    in_flight: int | None, riding: int, free: int
) -> None:
    from mcgyvr.rig import hitchhike

    assert hitchhike.free_slots(4, in_flight, riding) == free


# --- when an advert goes ------------------------------------------------------------


class Now:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Wire:
    """What the agent's outbox would carry, while it is open."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self.open = True

    def __call__(self, frame: str, timeout: float | None = None) -> bool:
        if not self.open:
            return False
        self.frames.append(json.loads(frame))
        return True

    def adverts(self) -> list[list[dict[str, Any]]]:
        return [f["body"]["units"] for f in self.frames if f["type"] == "unit_advert"]


def _units(
    config: Callable[[], Config],
    in_flight: dict[str, int | None],
    now: Now,
    wire: Wire,
    said: list[str],
) -> Any:
    from mcgyvr.rig import hitchhike

    def setup() -> hitchhike.Setup:
        shared, notes = hitchhike.shared_units(config())
        return hitchhike.Setup(
            units=shared,
            notes=notes,
            in_flight=lambda unit: in_flight.get(unit.name),
        )

    return hitchhike.Units(
        setup=setup, send=wire, clock=now, say=said.append, start=lambda work: work()
    )


def _two() -> Config:
    return _setup(
        _unit("small", "qwen-7b"),
        _unit("big", "qwen-32b", address="http://127.0.0.1:8081"),
    )


def test_the_first_advert_goes_once_the_hello_is_acked_and_is_the_schemas() -> None:
    now, wire, said = Now(), Wire(), list[str]()
    units = _units(_two, {"small": 1, "big": 0}, now, wire, said)

    units.tick()
    units.soon()
    assert wire.frames == []  # the channel is not up yet

    units.online()

    assert wire.adverts() == [
        [
            {
                "unit_id": "small",
                "model": "qwen-7b",
                "slots": 4,
                "ctx": 8192,
                "free_slots": 3,
                "rider_cap": 2,
            },
            {
                "unit_id": "big",
                "model": "qwen-32b",
                "slots": 4,
                "ctx": 8192,
                "free_slots": 4,
                "rider_cap": 2,
            },
        ]
    ]
    schema = rig_schema.load()
    for frame in wire.frames:
        rig_schema.validate(frame, schema, "#/$defs/AgentMessage")


def test_a_change_goes_at_the_next_check_and_checks_are_a_second_apart() -> None:
    now, wire, said = Now(), Wire(), list[str]()
    busy: dict[str, int | None] = {"small": 0, "big": 0}
    units = _units(_two, busy, now, wire, said)
    units.online()

    busy["small"] = 2
    now.now = 0.5
    units.soon()  # a beat half a second after the last check: too soon
    assert len(wire.adverts()) == 1
    now.now = 1.0
    units.tick()  # the asked-for check is still owed, and now it may run
    assert len(wire.adverts()) == 2
    assert wire.adverts()[-1][0]["free_slots"] == 2

    now.now = 20.0
    units.soon()  # a beat: nothing changed, nothing goes
    assert len(wire.adverts()) == 2


def test_an_unchanged_advert_goes_again_every_sixty_seconds() -> None:
    from mcgyvr.rig import sessionwire

    now, wire, said = Now(), Wire(), list[str]()
    units = _units(_two, {"small": 0, "big": 0}, now, wire, said)
    units.online()

    for at in range(1, 3 * sessionwire.UNIT_ADVERT_INTERVAL_S + 1):
        now.now = float(at)
        units.tick()

    assert len(wire.adverts()) == 4
    assert all(advert == wire.adverts()[0] for advert in wire.adverts())


def test_a_setup_that_shares_nothing_sends_nothing_and_one_that_stops_withdraws() -> (
    None
):
    now, wire, said = Now(), Wire(), list[str]()
    sharing = {"on": False}

    def config() -> Config:
        return (
            _two()
            if sharing["on"]
            else _setup(_unit("small", "qwen-7b", rider_slots=0))
        )

    units = _units(config, {"small": 0, "big": 0}, now, wire, said)
    units.online()
    for at in range(1, 200):
        now.now = float(at)
        units.tick()
    assert wire.frames == []

    sharing["on"] = True
    units.soon()
    assert [len(a) for a in wire.adverts()] == [2]

    sharing["on"] = False
    now.now += 1
    units.soon()
    assert wire.adverts()[-1] == []
    for _ in range(1, 200):
        now.now += 1
        units.tick()
    assert len(wire.adverts()) == 2


def test_nothing_goes_while_the_channel_is_down_and_all_again_once_it_is_back() -> None:
    now, wire, said = Now(), Wire(), list[str]()
    units = _units(_two, {"small": 0, "big": 0}, now, wire, said)
    units.online()
    assert len(wire.adverts()) == 1

    units.offline()
    wire.open = False
    for at in range(1, 200):
        now.now = float(at)
        units.tick()
        units.soon()
    wire.open = True
    assert len(wire.adverts()) == 1

    units.online()
    assert len(wire.adverts()) == 2
    assert wire.adverts()[1] == wire.adverts()[0]


def test_what_cannot_be_shared_is_said_once() -> None:
    now, wire, said = Now(), Wire(), list[str]()

    def config() -> Config:
        return _setup(
            _unit("small", "qwen-7b"),
            {"name": "blind", "model": "qwen-14b", "width": 4, "rider_slots": 1},
        )

    units = _units(config, {"small": None}, now, wire, said)
    units.online()
    for at in range(1, 200):
        now.now = float(at)
        units.soon()

    assert len([line for line in said if "blind" in line]) == 1
    assert len([line for line in said if "small" in line]) == 1  # its server is unread
    assert wire.adverts()[0][0]["free_slots"] == 0


def test_a_check_runs_off_the_callers_thread_one_at_a_time() -> None:
    from mcgyvr.rig import hitchhike

    now, wire = Now(), Wire()
    pending: list[Callable[[], None]] = []

    def setup() -> hitchhike.Setup:
        return hitchhike.Setup(units=hitchhike.shared_units(_two())[0])

    units = hitchhike.Units(
        setup=setup, send=wire, clock=now, say=lambda line: None, start=pending.append
    )
    units.online()
    now.now = 5.0
    units.soon()
    assert len(pending) == 1 and wire.frames == []

    pending.pop()()
    assert len(wire.adverts()) == 1


# --- the hello ------------------------------------------------------------------


def test_the_hello_names_hitchhike_units_while_the_rig_lends_or_shares(
    tmp_path: Path,
) -> None:
    from mcgyvr.rig import protocol, session

    assert "hitchhike_units" in session.FEATURES
    held = fakes.inventory(tmp_path)
    idle = fakes.sharing(tmp_path, enabled=False)

    assert session.offer(idle, held, (fakes.LAN_ADDRESS,), ()) is None
    sharing_only = session.offer(
        idle, held, (fakes.LAN_ADDRESS,), (), shares_units=True
    )
    assert sharing_only == protocol.Offer(
        roles=(),
        runtime=None,
        endpoints=(),
        models=(),
        sessions=(),
        features=("hitchhike_units",),
    )
    lending = session.offer(
        fakes.sharing(tmp_path), held, (fakes.LAN_ADDRESS,), (), shares_units=True
    )
    assert lending is not None and lending.features == session.FEATURES

    schema = rig_schema.load()
    for offer in (sharing_only, lending):
        hello = json.loads(
            protocol.hello(
                "h",
                machine_id="m",
                agent_version="1",
                ram_total_mb=1,
                ram_free_mb=None,
                cards=(),
                offer=offer,
            )
        )
        rig_schema.validate(hello, schema, "#/$defs/Hello")
        assert "hitchhike_units" in hello["body"]["capabilities"]["features"]
    assert (
        json.loads(
            protocol.hello(
                "h",
                machine_id="m",
                agent_version="1",
                ram_total_mb=1,
                ram_free_mb=None,
                cards=(),
                offer=sharing_only,
            )
        )["body"]["capabilities"]["roles"]
        == []
    )
