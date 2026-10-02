"""The probe and traversal frames speak the hub's published schema, and refuse by name.

The hub's schema grew the latency probe (``probe_open``, ``probe_run`` and
their answers), the traversal of a session's tunnel (``session_prepare``'s
binding token and responders, ``tunnel_up``'s time per candidate, deadline
and relay grants, ``tunnel_report``), the hello's features and the grace a
dropped agent gets. The agent's bounds and shapes for them are the schema's;
every frame it writes for them, at its edges, is valid against it; every
command the schema allows is read, and one it refuses — a token that is not
hex, a responder too many, a ticket of the wrong shape, a time per candidate
of zero, a peer or a secret twice — is refused by its field.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from tests import rig_schema

TOKEN = "00112233445566778899aabbccddeeff"
KEY = "A" * 42 + "Q="


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return rig_schema.load()


def _props(schema: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = schema["$defs"][name]["properties"]
    return found


def _branch(node: dict[str, Any]) -> dict[str, Any]:
    if "anyOf" in node:
        return next(b for b in node["anyOf"] if b.get("type") != "null")
    return node


def test_the_bounds_and_shapes_are_the_schemas(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import session
    from mcgyvr.rig import sessionwire as w

    assert schema["x-reconnect-grace-s"] == session.Timing().grace_s
    opened = _props(schema, "ProbeOpenBody")
    assert opened["token"]["pattern"] == f"^{w.TOKEN.pattern}$"
    assert opened["stun"]["maxItems"] == w.MAX_STUN_ENDPOINTS
    ttl = opened["ttl_s"]
    assert (ttl["minimum"], ttl["maximum"], ttl["default"]) == (
        w.MIN_PROBE_TTL_S,
        w.MAX_PROBE_TTL_S,
        w.DEFAULT_PROBE_TTL_S,
    )
    run = _props(schema, "ProbeRunBody")
    for field, low, high, default in (
        ("count", 1, w.MAX_PROBE_COUNT, w.DEFAULT_PROBE_COUNT),
        (
            "interval_ms",
            w.MIN_PROBE_INTERVAL_MS,
            w.MAX_PROBE_INTERVAL_MS,
            w.DEFAULT_PROBE_INTERVAL_MS,
        ),
        ("bulk_bytes", 0, w.MAX_PROBE_BULK_BYTES, 0),
        (
            "deadline_ms",
            w.MIN_PROBE_DEADLINE_MS,
            w.MAX_PROBE_DEADLINE_MS,
            w.DEFAULT_PROBE_DEADLINE_MS,
        ),
    ):
        node = run[field]
        assert (node["minimum"], node["maximum"], node["default"]) == (
            low,
            high,
            default,
        ), field
    assert run["peers"]["maxItems"] == w.MAX_PEERS
    outcome = _props(schema, "ProbeOutcome")
    assert _branch(outcome["rate_kbps"])["maximum"] == w.MAX_RATE_KBPS
    assert _branch(outcome["rtt_us"])["maximum"] == w.MAX_RTT_US
    assert _props(schema, "StunEndpoints")["stun"]["maxItems"] == w.MAX_STUN_ENDPOINTS
    grant = _props(schema, "RelayGrant")
    assert grant["ticket"]["pattern"] == f"^{w.TICKET.pattern}$"
    up = _props(schema, "TunnelUpBody")
    assert _branch(up["attempt_s"])["maximum"] == w.MAX_ATTEMPT_S
    assert _branch(up["connect_timeout_s"])["maximum"] == w.MAX_CONNECT_TIMEOUT_S
    assert _props(schema, "Capabilities")["features"]["maxItems"] == p.MAX_FEATURES


def _valid(schema: dict[str, Any], frame: str) -> dict[str, Any]:
    message: dict[str, Any] = json.loads(frame)
    rig_schema.validate(message, schema, "#/$defs/AgentMessage")
    return message


def test_every_frame_the_agent_writes_for_them_is_valid(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import protocol as p
    from mcgyvr.rig import sessionwire as w

    lan = w.Endpoint(host="192.0.2.10", port=51820, kind="lan")
    _valid(schema, w.probe_opened("o1", probe_id="pr", endpoints=[lan], stun_rtt_us=1))
    _valid(schema, w.probe_opened("o1", probe_id="pr", endpoints=[], stun_rtt_us=None))
    full = w.ProbeOutcome(
        rig_id="r1",
        reached=True,
        endpoint=lan,
        rtt_us=w.MAX_RTT_US,
        rtt_min_us=0,
        loss_pct=100,
        rate_kbps=w.MAX_RATE_KBPS,
    )
    many = [w.ProbeOutcome(rig_id=f"r{i}", reached=False) for i in range(w.MAX_PEERS)]
    _valid(schema, w.probe_result("r1", probe_id="pr", results=[full]))
    _valid(schema, w.probe_result("r1", probe_id="pr", results=many))
    _valid(schema, w.probe_result("r1", probe_id="pr", results=[]))
    paths = [
        w.PeerPath(rig_id="r1", path="direct", endpoint=lan, rtt_us=5),
        w.PeerPath(rig_id="r2", path="none"),
    ]
    _valid(schema, w.tunnel_report("t1", session_id="s1", peers=paths))
    _valid(schema, w.tunnel_report(None, session_id="s1", peers=paths))
    _valid(
        schema,
        w.session_prepared(
            "p1",
            session_id="s1",
            public_key=KEY,
            listen_port=51820,
            endpoints=[lan],
            stun_rtt_us=1234,
        ),
    )
    offer = p.Offer(
        roles=("worker",),
        runtime="engine:rpc",
        endpoints=(),
        models=(),
        sessions=(),
        features=("probe", "traversal"),
    )
    hello = _valid(
        schema,
        p.hello(
            "h",
            machine_id="m",
            agent_version="1",
            ram_total_mb=1,
            ram_free_mb=None,
            cards=(),
            offer=offer,
        ),
    )
    assert hello["body"]["capabilities"]["features"] == ["probe", "traversal"]


@pytest.mark.parametrize(
    "bad",
    [
        lambda w: w.probe_result(
            "r",
            probe_id="pr",
            results=[w.ProbeOutcome(rig_id="a", reached=True, loss_pct=101)],
        ),
        lambda w: w.probe_result(
            "r",
            probe_id="pr",
            results=[w.ProbeOutcome(rig_id="a", reached=True, rate_kbps=0)],
        ),
        lambda w: w.probe_result(
            "r",
            probe_id="pr",
            results=[
                w.ProbeOutcome(rig_id="a", reached=False),
                w.ProbeOutcome(rig_id="a", reached=False),
            ],
        ),
        lambda w: w.tunnel_report("t", session_id="s", peers=[]),
        lambda w: w.tunnel_report(
            "t", session_id="s", peers=[w.PeerPath(rig_id="a", path="Not A Tag")]
        ),
        lambda w: w.probe_opened("o", probe_id="pr", endpoints=[], stun_rtt_us=-1),
    ],
)
def test_a_frame_the_schema_would_refuse_is_never_written(
    bad: Callable[[Any], str],
) -> None:
    from mcgyvr.rig import sessionwire as w

    with pytest.raises(ValueError):
        bad(w)


def _envelope(kind: str, body: dict[str, Any]) -> Any:
    from mcgyvr.rig import protocol

    return protocol.decode(json.dumps({"v": 1, "type": kind, "id": "c1", "body": body}))


def _run_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "probe_id": "pr",
        "peers": [
            {
                "rig_id": "r1",
                "secret": TOKEN,
                "endpoints": [{"host": "192.0.2.20", "port": 1, "kind": "reflexive"}],
            }
        ],
    }
    body.update(changes)
    return body


def _up_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "session_id": "s1",
        "address": "198.51.100.2/24",
        "listen_port": 51820,
        "peers": [
            {
                "rig_id": "r1",
                "public_key": KEY,
                "allowed_ips": ["198.51.100.1/32"],
                "relay": {"host": "203.0.113.9", "port": 3478, "ticket": "T" * 30},
            }
        ],
        "attempt_s": 3,
        "connect_timeout_s": 60,
    }
    body.update(changes)
    return body


def test_what_the_schema_allows_is_read(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import sessionwire as w

    for kind, body in (
        ("probe_open", {"probe_id": "pr", "token": TOKEN}),
        ("probe_run", _run_body()),
        ("tunnel_up", _up_body()),
        (
            "session_prepare",
            {
                "session_id": "s1",
                "role": "worker",
                "traversal": {
                    "token": TOKEN,
                    "stun": [{"host": "203.0.113.9", "port": 3478, "kind": "stun"}],
                },
            },
        ),
    ):
        rig_schema.validate(
            {"v": 1, "type": kind, "id": "c1", "body": body},
            schema,
            "#/$defs/HubMessage",
        )
    opened = w.read_probe_open(
        _envelope("probe_open", {"probe_id": "pr", "token": TOKEN})
    )
    assert (opened.token, opened.stun, opened.ttl_s) == (bytes.fromhex(TOKEN), (), 30)
    run = w.read_probe_run(_envelope("probe_run", _run_body()))
    assert (run.count, run.interval_ms, run.bulk_bytes, run.deadline_ms) == (
        5,
        50,
        0,
        5000,
    )
    up = w.read_tunnel_up(_envelope("tunnel_up", _up_body()))
    assert up.attempt_s == 3 and up.connect_timeout_s == 60
    assert up.peers[0].relay == w.RelayGrant(
        host="203.0.113.9", port=3478, ticket="T" * 30
    )


@pytest.mark.parametrize(
    ("kind", "body", "field"),
    [
        ("probe_open", {"probe_id": "pr", "token": TOKEN.upper()}, "body.token"),
        ("probe_open", {"probe_id": "pr", "token": TOKEN[:-1]}, "body.token"),
        (
            "probe_open",
            {
                "probe_id": "pr",
                "token": TOKEN,
                "stun": [{"host": "203.0.113.9", "port": 1, "kind": "stun"}] * 3,
            },
            "body.stun",
        ),
        ("probe_open", {"probe_id": "pr", "token": TOKEN, "ttl_s": 4}, "body.ttl_s"),
        ("probe_run", _run_body(count=21), "body.count"),
        ("probe_run", _run_body(bulk_bytes=256 * 1024 + 1), "body.bulk_bytes"),
        ("probe_run", _run_body(interval_ms=True), "body.interval_ms"),
        (
            "probe_run",
            _run_body(peers=_run_body()["peers"] * 2),
            "body.peers",
        ),
        (
            "probe_run",
            _run_body(peers=[{**_run_body()["peers"][0], "endpoints": []}]),
            "body.peers.endpoints",
        ),
        ("tunnel_up", _up_body(attempt_s=0), "body.attempt_s"),
        ("tunnel_up", _up_body(connect_timeout_s=301), "body.connect_timeout_s"),
        (
            "tunnel_up",
            _up_body(
                peers=[
                    {
                        **_up_body()["peers"][0],
                        "relay": {"host": "203.0.113.9", "port": 1, "ticket": "short"},
                    }
                ]
            ),
            "body.peers.relay.ticket",
        ),
        (
            "session_prepare",
            {
                "session_id": "s1",
                "role": "worker",
                "traversal": {"token": TOKEN, "stun": []},
            },
            "body.traversal.stun",
        ),
    ],
)
def test_what_the_schema_refuses_is_refused_by_its_field(
    schema: dict[str, Any], kind: str, body: dict[str, Any], field: str
) -> None:
    from mcgyvr.rig import protocol
    from mcgyvr.rig import sessionwire as w

    readers = {
        "probe_open": w.read_probe_open,
        "probe_run": w.read_probe_run,
        "tunnel_up": w.read_tunnel_up,
        "session_prepare": w.read_session_prepare,
    }
    if field != "body.peers":  # a peer twice: the hub's models refuse it, and
        # a JSON Schema cannot say it
        with pytest.raises(rig_schema.SchemaError):
            rig_schema.validate(
                {"v": 1, "type": kind, "id": "c1", "body": body},
                schema,
                "#/$defs/HubMessage",
            )
    with pytest.raises(protocol.ProtocolError) as refused:
        readers[kind](_envelope(kind, body))
    assert refused.value.code == "bad_message"
    assert refused.value.message.startswith(f"{field}:"), refused.value.message
