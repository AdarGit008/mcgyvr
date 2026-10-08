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


_PINS = pytest.mark.parametrize(
    "pinned", rig_schema.PINS, ids=[p.hub_name for p in rig_schema.PINS]
)


@_PINS
def test_the_pinned_copy_is_the_one_its_digest_names(
    pinned: rig_schema.Pinned,
) -> None:
    data = pinned.fixture.read_bytes()
    assert rig_schema.sha256(data) == pinned.pinned_sha256


@_PINS
def test_the_pinned_copy_is_a_named_hubs_file_pinned(
    pinned: rig_schema.Pinned,
) -> None:
    named = rig_schema.hub_file(pinned)
    if named is None:
        pytest.skip(f"neither ${pinned.env} nor ${rig_schema.HUB_REPO_ENV} names a hub")
    hub_file = named.read_bytes()
    assert rig_schema.sha256(hub_file) == pinned.hub_sha256, (
        f"the hub's {pinned.hub_name} moved: re-pin with "
        "`python -m tests.rig_schema` and bring the agent's limits to it"
    )
    assert rig_schema.pin(hub_file) == pinned.fixture.read_bytes()


def test_a_hub_is_named_by_its_files_own_variable_else_by_its_checkout(
    tmp_path: Path,
) -> None:
    rider = rig_schema.RIDER
    assert rig_schema.hub_file(rider, {}) is None
    repo = {rig_schema.HUB_REPO_ENV: str(tmp_path)}
    assert rig_schema.hub_file(rider, repo) == tmp_path / "schemas" / rider.hub_name
    alone = {**repo, rider.env: str(tmp_path / "x.json")}
    assert rig_schema.hub_file(rider, alone) == tmp_path / "x.json"
    assert rig_schema.hub_file(rig_schema.PROTOCOL, alone) == (
        tmp_path / "schemas" / rig_schema.PROTOCOL.hub_name
    )


def test_a_re_pin_rewrites_every_copy_and_its_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    work = tmp_path / "tests"
    (work / "fixtures").mkdir(parents=True)
    for pinned in rig_schema.PINS:
        shutil.copy(pinned.fixture, work / "fixtures" / pinned.fixture.name)
    here = work / "rig_schema.py"
    shutil.copy(rig_schema.__file__, here)
    hub = tmp_path / "hub" / "schemas"
    hub.mkdir(parents=True)
    for pinned in rig_schema.PINS:
        moved = json.loads(pinned.fixture.read_bytes())
        moved["$id"] = "https://hub.invalid/" + pinned.hub_name
        moved["x-moved"] = True
        (hub / pinned.hub_name).write_text(json.dumps(moved), encoding="utf-8")
    import importlib.util
    import sys

    # The rewritten file is as long as before, maybe in the same second: a
    # cached compile of it would be taken for it.
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    spec = importlib.util.spec_from_file_location("moved_rig_schema", here)
    assert spec is not None and spec.loader is not None
    moved_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, moved_module)
    spec.loader.exec_module(moved_module)

    assert moved_module.main([str(tmp_path / "hub")]) == 0

    spec.loader.exec_module(moved_module)
    for pinned in moved_module.PINS:
        hub_bytes = (hub / pinned.hub_name).read_bytes()
        assert pinned.hub_sha256 == rig_schema.sha256(hub_bytes)
        assert pinned.fixture.read_bytes() == rig_schema.pin(hub_bytes)
        assert moved_module.load(pinned)["x-moved"] is True


def test_every_feature_the_agent_speaks_is_one_the_hub_publishes(
    schema: dict[str, Any],
) -> None:
    """A subset, not the same set: the hub may publish a behaviour before this
    agent speaks it, and keeps serving agents that lack it; a name it does not
    publish is a behaviour it never uses, switched off without a word."""
    from mcgyvr.rig import session

    assert len(set(session.FEATURES)) == len(session.FEATURES)
    assert set(session.FEATURES) <= set(schema["x-features"])


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


def test_the_validator_refuses_a_key_a_closed_object_does_not_name() -> None:
    closed = {
        "$defs": {
            "X": {
                "type": "object",
                "properties": {"a": {"type": "integer"}},
                "additionalProperties": False,
            }
        }
    }
    rig_schema.validate({"a": 1}, closed, "#/$defs/X")
    rig_schema.validate({}, closed, "#/$defs/X")
    with pytest.raises(rig_schema.SchemaError, match="'b'"):
        rig_schema.validate({"a": 1, "b": 2}, closed, "#/$defs/X")
    open_ = {"$defs": {"X": {"additionalProperties": True}}}
    rig_schema.validate({"b": 2}, open_, "#/$defs/X")
    typed = {"$defs": {"X": {"additionalProperties": {"type": "string"}}}}
    with pytest.raises(rig_schema.SchemaError):
        rig_schema.validate({}, typed, "#/$defs/X")
