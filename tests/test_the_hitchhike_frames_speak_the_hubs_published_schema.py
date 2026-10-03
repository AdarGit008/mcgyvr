"""The rig agent's hitchhike frames speak the hub's published schema.

A host shares open slots of its own units with riders (hitchhike): its agent
advertises them (``unit_advert``), and the hub relays a rider's request to one
(``unit_relay_request``, then the frames of a head relay). The hub's schema is
the one definition of both, so the agent's bounds for them (how many units an
advert carries, a unit's slots, context, free slots and rider cap, how often an
advert goes and when the hub drops one) are the schema's; every advert the
agent writes, at its edges, is valid against it, and one the schema refuses
the agent refuses to write; every ride the schema allows is read, and one it
refuses is refused by name. ``unknown_unit`` is one of the hub's error codes,
and the agent's.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from tests import rig_schema


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return rig_schema.load()


def _props(schema: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = schema["$defs"][name]["properties"]
    return found


def test_the_agents_hitchhike_bounds_are_the_schemas(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import sessionwire as w

    assert schema["x-max-units"] == w.MAX_UNITS
    assert schema["x-unit-advert-interval-s"] == w.UNIT_ADVERT_INTERVAL_S
    assert schema["x-unit-advert-stale-s"] == w.UNIT_ADVERT_STALE_S
    assert w.SessionCode.UNKNOWN_UNIT == "unknown_unit"
    assert w.SessionCode.UNKNOWN_UNIT in schema["x-error-codes"]

    advert = _props(schema, "UnitAdvertBody")
    assert advert["units"]["maxItems"] == w.MAX_UNITS
    unit = _props(schema, "AdvertisedUnit")
    assert unit["unit_id"]["pattern"] == f"^{p.MESSAGE_ID.pattern}$"
    assert unit["model"]["pattern"] == f"^{p.MODEL_NAME.pattern}$"
    assert (unit["slots"]["minimum"], unit["slots"]["maximum"]) == (1, w.MAX_SLOTS)
    assert (unit["ctx"]["minimum"], unit["ctx"]["maximum"]) == (w.MIN_CTX, w.MAX_CTX)
    assert (unit["free_slots"]["minimum"], unit["free_slots"]["maximum"]) == (
        0,
        w.MAX_SLOTS,
    )
    assert (unit["rider_cap"]["minimum"], unit["rider_cap"]["maximum"]) == (
        1,
        w.MAX_SLOTS - 1,
    )

    ride = _props(schema, "UnitRelayRequestBody")
    head = _props(schema, "RelayRequestBody")
    assert ride["unit_id"]["pattern"] == f"^{p.MESSAGE_ID.pattern}$"
    assert {k: v for k, v in ride.items() if k != "unit_id"} == {
        k: v for k, v in head.items() if k != "session_id"
    }


def _unit(i: int = 0, **changes: Any) -> Any:
    from mcgyvr.rig import sessionwire as w

    fields: dict[str, Any] = {
        "unit_id": f"u{i}",
        "model": f"model-{i}.gguf",
        "slots": 4,
        "ctx": 8192,
        "free_slots": 2,
        "rider_cap": 2,
    }
    fields.update(changes)
    return w.AdvertisedUnit(**fields)


def test_every_advert_the_agent_writes_is_valid_against_the_schema(
    schema: dict[str, Any],
) -> None:
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import sessionwire as w

    frames = [
        w.unit_advert([]),
        w.unit_advert([_unit()]),
        w.unit_advert(
            [
                _unit(
                    i,
                    unit_id="u" * 63 + str(i % 10) if i < 10 else f"unit_{i}-x",
                    model="M" + "m" * 127 if i == 0 else f"m{i}",
                    slots=w.MAX_SLOTS,
                    ctx=w.MAX_CTX,
                    free_slots=w.MAX_SLOTS,
                    rider_cap=w.MAX_SLOTS - 1,
                )
                for i in range(w.MAX_UNITS)
            ]
        ),
        w.unit_advert(
            [_unit(slots=2, ctx=w.MIN_CTX, free_slots=0, rider_cap=1)],
        ),
    ]
    for frame in frames:
        assert len(frame.encode()) <= p.MAX_MESSAGE_BYTES
        message = json.loads(frame)
        assert message["type"] == "unit_advert"
        assert "re" not in message
        rig_schema.validate(message, schema, "#/$defs/AgentMessage")
    assert json.loads(frames[1])["body"] == {
        "units": [
            {
                "unit_id": "u0",
                "model": "model-0.gguf",
                "slots": 4,
                "ctx": 8192,
                "free_slots": 2,
                "rider_cap": 2,
            }
        ]
    }


def test_the_agent_refuses_to_write_an_advert_the_schema_refuses() -> None:
    from mcgyvr.rig import sessionwire as w

    bad: list[Callable[[], object]] = [
        lambda: w.unit_advert([_unit(i) for i in range(w.MAX_UNITS + 1)]),
        lambda: w.unit_advert([_unit(0), _unit(1, unit_id="u0")]),
        lambda: w.unit_advert([_unit(0), _unit(1, model="model-0.gguf")]),
        lambda: w.unit_advert([_unit(unit_id="a b")]),
        lambda: w.unit_advert([_unit(unit_id="")]),
        lambda: w.unit_advert([_unit(model="../m.gguf")]),
        lambda: w.unit_advert([_unit(slots=0, free_slots=0)]),
        lambda: w.unit_advert([_unit(slots=w.MAX_SLOTS + 1)]),
        lambda: w.unit_advert([_unit(ctx=w.MIN_CTX - 1)]),
        lambda: w.unit_advert([_unit(ctx=w.MAX_CTX + 1)]),
        lambda: w.unit_advert([_unit(free_slots=-1)]),
        lambda: w.unit_advert([_unit(free_slots=5)]),
        lambda: w.unit_advert([_unit(rider_cap=0)]),
        lambda: w.unit_advert([_unit(rider_cap=4)]),
        lambda: w.unit_advert([_unit(slots=1, free_slots=1, rider_cap=1)]),
        lambda: w.unit_advert([_unit(slots=True)]),
    ]
    for write in bad:
        with pytest.raises(ValueError):
            write()


def _ride(**changes: Any) -> dict[str, Any]:
    body = {
        "unit_id": "u0",
        "request_id": "q1",
        "endpoint": "chat_completions",
        "body_bytes": 0,
        "stream": True,
        "timeout_s": 3600,
        "max_response_bytes": 1,
        "window": 64,
    }
    body.update(changes)
    return {"v": 1, "id": "c1", "type": "unit_relay_request", "body": body}


def _read(frame: dict[str, Any]) -> Any:
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import sessionwire as w

    return w.read_unit_relay_request(p.decode(json.dumps(frame)))


def test_every_ride_the_schema_allows_is_read(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import sessionwire as w

    for frame in (
        _ride(),
        _ride(unit_id="u" * 64, body_bytes=1 << 20, stream=False, later="ignored"),
        _ride(timeout_s=1, max_response_bytes=64 << 20, window=1),
    ):
        rig_schema.validate(frame, schema, "#/$defs/HubMessage")
        asked = _read(frame)
        assert isinstance(asked, w.UnitRelayRequest)
        body = frame["body"]
        assert (asked.unit_id, asked.request_id, asked.endpoint) == (
            body["unit_id"],
            body["request_id"],
            "chat_completions",
        )
        assert (asked.body_bytes, asked.stream, asked.timeout_s) == (
            body["body_bytes"],
            body["stream"],
            body["timeout_s"],
        )
        assert (asked.max_response_bytes, asked.window) == (
            body["max_response_bytes"],
            body["window"],
        )


@pytest.mark.parametrize(
    "change",
    [
        {"unit_id": "a b"},
        {"unit_id": "u" * 65},
        {"unit_id": None},
        {"endpoint": "completions"},
        {"body_bytes": (1 << 20) + 1},
        {"stream": "yes"},
        {"timeout_s": 0},
        {"max_response_bytes": (64 << 20) + 1},
        {"window": 65},
    ],
)
def test_a_ride_the_schema_refuses_is_refused_by_name(
    schema: dict[str, Any], change: dict[str, Any]
) -> None:
    from mcgyvr.rig import protocol as p

    frame = _ride(**change)
    if change.get("unit_id", "") is None:
        del frame["body"]["unit_id"]
    with pytest.raises(rig_schema.SchemaError):
        rig_schema.validate(frame, schema, "#/$defs/HubMessage")
    with pytest.raises(p.ProtocolError) as refused:
        _read(frame)
    assert refused.value.code == "bad_message"
    assert next(iter(change)) in refused.value.message
