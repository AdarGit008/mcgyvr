"""The rig agent speaks the hub's published schema, and refuses what it refuses.

The hub's JSON Schema is the one definition of the wire. The agent's own
limits (version, frame size, frame rate, close codes, card count and bounds,
the id and tag shapes) are the schema's, every frame the agent writes is valid
against it, every hub frame it allows is read, and a hub frame it refuses is
refused by the agent too, without reading on. The pinned copy is the one its
digest names, and, with a hub checkout named, is that hub's file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests import rig_schema


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return rig_schema.load()


def _defs(schema: dict[str, Any], name: str) -> dict[str, Any]:
    node: dict[str, Any] = schema["$defs"][name]
    return node


def test_the_pinned_copy_is_the_one_its_digest_names() -> None:
    data = rig_schema.FIXTURE.read_bytes()
    assert rig_schema.sha256(data) == rig_schema.PINNED_SHA256


def test_the_pinned_copy_is_a_named_hubs_file_pinned() -> None:
    named = os.environ.get(rig_schema.HUB_SCHEMA_ENV)
    if not named:
        pytest.skip(f"${rig_schema.HUB_SCHEMA_ENV} names no hub schema file")
    hub_file = Path(named).read_bytes()
    assert rig_schema.sha256(hub_file) == rig_schema.HUB_SCHEMA_SHA256, (
        "the hub's schema moved: re-pin with `python -m tests.rig_schema` "
        "and bring the agent's limits to it"
    )
    assert rig_schema.pin(hub_file) == rig_schema.FIXTURE.read_bytes()


def test_the_agents_limits_are_the_schemas(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import protocol as p

    assert schema["x-protocol-version"] == p.PROTOCOL_VERSION
    assert schema["x-max-message-bytes"] == p.MAX_MESSAGE_BYTES
    assert schema["x-max-frames-per-second"] == p.MAX_FRAMES_PER_SECOND
    assert schema["x-close-codes"] == {c.name.lower(): c.value for c in p.CloseCode}

    envelope = _defs(schema, "Envelope")["properties"]
    assert envelope["v"]["minimum"] == envelope["v"]["maximum"] == p.PROTOCOL_VERSION
    assert envelope["id"]["pattern"] == f"^{p.MESSAGE_ID.pattern}$"
    assert envelope["type"]["pattern"] == f"^{p.TAG.pattern}$"

    hello = _defs(schema, "HelloBody")["properties"]
    assert hello["machine_id"]["pattern"] == f"^{p.MACHINE_ID.pattern}$"
    assert hello["agent_version"]["pattern"] == f"^{p.AGENT_VERSION.pattern}$"
    assert hello["cards"]["maxItems"] == p.MAX_CARDS
    assert hello["ram_total_mb"]["maximum"] == p.MAX_MB
    assert _defs(schema, "HeartbeatBody")["properties"]["cards"]["maxItems"] == (
        p.MAX_CARDS
    )

    card = _defs(schema, "CardReport")["properties"]
    assert card["index"]["exclusiveMaximum"] == p.MAX_CARD_INDEX + 1
    assert card["index"]["minimum"] == 0
    assert card["name"]["pattern"] == f"^{p.CARD_NAME.pattern}$"
    assert card["name"]["maxLength"] == p.CARD_NAME_MAX
    assert card["vram_total_mb"]["maximum"] == p.MAX_MB

    error = _defs(schema, "ErrorBody")["properties"]
    assert error["code"]["pattern"] == f"^{p.TAG.pattern}$"
    assert error["message"]["maxLength"] == p.MAX_ERROR_TEXT

    interval = _defs(schema, "AckBody")["properties"]["heartbeat_interval_s"]
    bounds = next(b for b in interval["anyOf"] if b.get("type") == "integer")
    assert (bounds["minimum"], bounds["maximum"]) == p.HEARTBEAT_INTERVAL_S


def _hellos() -> list[str]:
    from mcgyvr.rig import protocol as p

    many = [
        p.CardReport(index=i, name=f"card {i}", vram_total_mb=8192, vram_free_mb=i)
        for i in range(p.MAX_CARDS)
    ]
    edge = p.CardReport(
        index=p.MAX_CARD_INDEX,
        name="x" * p.CARD_NAME_MAX,
        vram_total_mb=p.MAX_MB,
        vram_free_mb=p.MAX_MB,
    )
    return [
        p.hello(
            "h1",
            machine_id="mch-example-machine",
            agent_version="0.1.1.dev3+g0123abc",
            ram_total_mb=0,
            ram_free_mb=None,
            cards=(),
        ),
        p.hello(
            p.new_id(),
            machine_id="m",
            agent_version="1",
            ram_total_mb=p.MAX_MB,
            ram_free_mb=12,
            cards=tuple(many),
        ),
        p.hello(
            p.new_id(),
            machine_id="mch-1",
            agent_version="2.0",
            ram_total_mb=1,
            ram_free_mb=1,
            cards=(edge,),
        ),
    ]


def _heartbeats() -> list[str]:
    from mcgyvr.rig import protocol as p

    return [
        p.heartbeat(p.new_id(), ram_free_mb=None, cards=()),
        p.heartbeat(
            "beat-2",
            ram_free_mb=4096,
            cards=tuple(
                p.CardReading(index=i, vram_free_mb=i) for i in range(p.MAX_CARDS)
            ),
        ),
    ]


def _replies() -> list[str]:
    from mcgyvr.rig import protocol as p

    return [
        p.error(p.new_id(), code="unsupported_type", message="", re="cmd-1"),
        p.error(p.new_id(), code="bad_message", message="m" * 600, re=None),
    ]


def test_every_frame_the_agent_writes_is_valid_against_the_schema(
    schema: dict[str, Any],
) -> None:
    from mcgyvr.rig import protocol as p

    for frame in [*_hellos(), *_heartbeats(), *_replies()]:
        assert len(frame.encode()) <= p.MAX_MESSAGE_BYTES
        message = json.loads(frame)
        rig_schema.validate(message, schema, "#/$defs/AgentMessage")
        rig_schema.validate(message, schema, "#/$defs/Envelope")


def test_the_agent_refuses_to_write_what_the_schema_refuses() -> None:
    from mcgyvr.rig import protocol as p

    def card(**changes: Any) -> p.CardReport:
        fields: dict[str, Any] = {
            "index": 0,
            "name": "card",
            "vram_total_mb": 10,
            "vram_free_mb": 5,
        }
        fields.update(changes)
        return p.CardReport(**fields)

    bad_cards = [
        (card(index=-1),),
        (card(index=p.MAX_CARD_INDEX + 1),),
        (card(name=""),),
        (card(name="a\nb"),),
        (card(name="\u202eevil"),),
        (card(name="x" * (p.CARD_NAME_MAX + 1)),),
        (card(vram_free_mb=11),),
        (card(vram_total_mb=p.MAX_MB + 1, vram_free_mb=0),),
        (card(vram_total_mb=True),),
        (card(), card()),
        tuple(card(index=i) for i in range(p.MAX_CARDS + 1)),
    ]
    for cards in bad_cards:
        with pytest.raises(ValueError):
            p.hello(
                "h",
                machine_id="m",
                agent_version="1",
                ram_total_mb=1,
                ram_free_mb=None,
                cards=cards,
            )
    for machine_id in ("", "-lead", "a b", "x" * 129, "m\n"):
        with pytest.raises(ValueError):
            p.hello(
                "h",
                machine_id=machine_id,
                agent_version="1",
                ram_total_mb=1,
                ram_free_mb=None,
                cards=(),
            )
    for message_id in ("", "a" * 65, "a.b", "a\n"):
        with pytest.raises(ValueError):
            p.heartbeat(message_id, ram_free_mb=None, cards=())
    with pytest.raises(ValueError):
        p.heartbeat("b", ram_free_mb=-1, cards=())
    with pytest.raises(ValueError):
        p.error("e", code="Not-A-Tag", message="", re=None)


def _hub_frames() -> list[dict[str, Any]]:
    return [
        {"v": 1, "type": "ack", "id": "a1", "re": "h1", "body": {}},
        {
            "v": 1,
            "type": "ack",
            "id": "a2",
            "re": "h1",
            "body": {"rig_id": "r-1", "heartbeat_interval_s": 15},
        },
        {"v": 1, "type": "ack", "id": "a3", "re": "b1"},
        {
            "v": 1,
            "type": "ack",
            "id": "a4",
            "re": "b1",
            "body": {"heartbeat_interval_s": None, "rig_id": None, "later": [1]},
            "later": True,
        },
        {"v": 1, "type": "error", "id": "e1", "body": {"code": "timeout"}},
        {
            "v": 1,
            "type": "error",
            "id": "e2",
            "re": None,
            "body": {"code": "some_new_code", "message": "m" * 500},
        },
    ]


def test_every_hub_frame_the_schema_allows_is_read(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import protocol as p

    for frame in _hub_frames():
        rig_schema.validate(frame, schema, "#/$defs/HubMessage")
        envelope = p.decode(json.dumps(frame))
        assert envelope.type == frame["type"] and envelope.id == frame["id"]
        if envelope.type == "ack":
            ack = p.read_ack(envelope)
            assert ack.re == frame["re"]
        else:
            error = p.read_error(envelope)
            assert error.code == frame["body"]["code"]


def _refused_hub_frames() -> list[dict[str, Any]]:
    good: dict[str, Any] = {"v": 1, "type": "ack", "id": "a1", "re": "h1"}
    return [
        {**good, "v": 2},
        {**good, "v": True},
        {**good, "v": "1"},
        {**good, "id": "a" * 65},
        {**good, "id": "a1\n"},
        {**good, "id": ""},
        {**good, "re": "h 1"},
        {k: v for k, v in good.items() if k != "re"},
        {**good, "body": {"heartbeat_interval_s": 0}},
        {**good, "body": {"heartbeat_interval_s": 3601}},
        {**good, "body": {"heartbeat_interval_s": "15"}},
        {**good, "body": {"heartbeat_interval_s": True}},
        {**good, "body": {"heartbeat_interval_s": 1.5}},
        {**good, "body": {"rig_id": 7}},
        {**good, "body": []},
        {"v": 1, "type": "error", "id": "e1", "body": {}},
        {"v": 1, "type": "error", "id": "e1", "body": {"code": "Bad"}},
        {"v": 1, "type": "error", "id": "e1", "body": {"code": "x", "message": 3}},
        {
            "v": 1,
            "type": "error",
            "id": "e1",
            "body": {"code": "x", "message": "m" * 501},
        },
        {"v": 1, "type": "error", "id": "e1"},
    ]


def test_a_hub_frame_the_schema_refuses_is_refused(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import protocol as p

    for frame in _refused_hub_frames():
        with pytest.raises(rig_schema.SchemaError):
            rig_schema.validate(frame, schema, "#/$defs/HubMessage")
        with pytest.raises(p.ProtocolError):
            envelope = p.decode(json.dumps(frame))
            if envelope.type == "ack":
                p.read_ack(envelope)
            else:
                p.read_error(envelope)


def test_a_frame_that_is_not_one_json_object_in_bounds_is_refused() -> None:
    from mcgyvr.rig import protocol as p

    deep = "[" * 100_000 + "]" * 100_000
    too_big = json.dumps(
        {"v": 1, "type": "ack", "id": "a", "re": "b", "x": "y" * p.MAX_MESSAGE_BYTES}
    )
    for raw in (
        "",
        "not json",
        "[1, 2]",
        '"text"',
        "null",
        deep,
        too_big,
        b"\xff\xfe",
        "1" * 5000,
        '{"v": 1, "type": "ack", "id": "a", "re": "b", "body": {"x": 1e999}}x',
    ):
        with pytest.raises(p.ProtocolError) as refused:
            p.decode(raw)
        assert refused.value.code == "bad_message"


def test_an_unknown_type_is_read_as_an_envelope_for_the_dispatcher() -> None:
    from mcgyvr.rig import protocol as p

    envelope = p.decode(
        '{"v": 1, "type": "start_worker", "id": "c1", "body": {"x": 1}}'
    )
    assert (envelope.type, envelope.id, envelope.re) == ("start_worker", "c1", None)
    assert envelope.body == {"x": 1}


def test_the_validator_refuses_a_keyword_it_does_not_read() -> None:
    with pytest.raises(rig_schema.SchemaError):
        rig_schema.validate({}, {"$defs": {"X": {"uniqueItems": True}}}, "#/$defs/X")
