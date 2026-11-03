"""The port forward's frames speak the hub's published schema, and refuse by name.

The hub's schema grew the port forward: ``port_map`` (the hub's block of
external ports, or a release), ``port_check`` (answer the hub's pings a
while) and the agent's ``port_map_report``. The agent's bounds for them are
the schema's; every report it writes is valid against it, and one the schema
refuses is never written; every command the schema allows is read, and one it
refuses is refused by its field.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests import rig_schema

TOKEN = "00112233445566778899aabbccddeeff"


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


def _envelope(kind: str, body: dict[str, Any]) -> Any:
    from mcgyvr.rig import protocol

    return protocol.decode(json.dumps({"v": 1, "type": kind, "id": "c1", "body": body}))


def test_the_bounds_are_the_schemas(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import session
    from mcgyvr.rig import sessionwire as w

    assert session.PORT_MAP_FEATURE in schema["x-features"]
    asked = _props(schema, "PortMapBody")
    ports = asked["ports"]
    assert (ports["minimum"], ports["maximum"], ports["default"]) == (
        1,
        w.PORT_MAP_PORTS,
        w.PORT_MAP_PORTS,
    )
    lease = asked["lease_s"]
    assert (lease["minimum"], lease["maximum"], lease["default"]) == (
        w.MIN_PORT_MAP_LEASE_S,
        w.MAX_PORT_MAP_LEASE_S,
        w.DEFAULT_PORT_MAP_LEASE_S,
    )
    check = _props(schema, "PortCheckBody")
    ttl = check["ttl_s"]
    assert (ttl["minimum"], ttl["maximum"], ttl["default"]) == (
        w.MIN_PORT_CHECK_TTL_S,
        w.MAX_PORT_CHECK_TTL_S,
        w.DEFAULT_PORT_CHECK_TTL_S,
    )
    assert check["secret"]["pattern"] == f"^{w.TOKEN.pattern}$"
    report = _props(schema, "PortMapReportBody")
    assert tuple(report["state"]["enum"]) == w.PORT_MAP_STATES
    assert _branch(report["lease_s"])["maximum"] == w.MAX_PORT_MAP_LEASE_S


def test_every_report_the_agent_writes_is_valid(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import sessionwire as w

    reports = [
        w.PortMapped(
            state="mapped",
            method="upnp",
            lan_host="192.168.1.20",
            internal_port=51820,
            external_port=65532,
            ports=4,
            router_host="198.51.100.7",
            lease_s=0,
        ),
        w.PortMapped(state="failed", error="conflict", message="taken \x1b[31m"),
        w.PortMapped(state="released"),
    ]
    for report in reports:
        frame = json.loads(w.port_map_report(report))
        rig_schema.validate(frame, schema, "#/$defs/AgentMessage")
        assert "\x1b" not in frame["body"].get("message", "")


@pytest.mark.parametrize(
    "report",
    [
        {"state": "mapped", "method": "upnp"},
        {"state": "failed"},
        {"state": "lost"},
        {"state": "released", "lan_host": "router.lan"},
        {"state": "released", "method": "UPnP"},
        {"state": "released", "external_port": 65534, "ports": 4},
        {"state": "released", "lease_s": 86_401},
    ],
)
def test_a_report_the_schema_would_refuse_is_never_written(
    report: dict[str, Any],
) -> None:
    from mcgyvr.rig import sessionwire as w

    with pytest.raises(ValueError):
        w.port_map_report(w.PortMapped(**report))


def test_what_the_schema_allows_is_read(schema: dict[str, Any]) -> None:
    from mcgyvr.rig import sessionwire as w

    for kind, body in (
        ("port_map", {"external_port": 51824, "ports": 4, "lease_s": 3600}),
        ("port_map", {"external_port": None}),
        ("port_check", {"check_id": "k1", "secret": TOKEN, "port": 51820}),
    ):
        rig_schema.validate(
            {"v": 1, "type": kind, "id": "c1", "body": body},
            schema,
            "#/$defs/HubMessage",
        )
    asked = w.read_port_map(
        _envelope("port_map", {"external_port": 51824, "lease_s": 600})
    )
    assert asked == w.PortMap(external_port=51824, ports=w.PORT_MAP_PORTS, lease_s=600)
    released = w.read_port_map(_envelope("port_map", {"external_port": None}))
    assert released.external_port is None
    check = w.read_port_check(
        _envelope("port_check", {"check_id": "k1", "secret": TOKEN, "port": 51820})
    )
    assert check.secret == bytes.fromhex(TOKEN)
    assert check.ttl_s == w.DEFAULT_PORT_CHECK_TTL_S


@pytest.mark.parametrize(
    ("kind", "body", "field"),
    [
        ("port_map", {"external_port": 65534, "ports": 4}, "body.ports"),
        ("port_map", {"external_port": 0}, "body.external_port"),
        ("port_map", {"external_port": 51820, "lease_s": 60}, "body.lease_s"),
        ("port_check", {"check_id": "k1", "secret": "XYZ", "port": 1}, "body.secret"),
        (
            "port_check",
            {"check_id": "k1", "secret": TOKEN, "port": 1, "ttl_s": 61},
            "body.ttl_s",
        ),
    ],
)
def test_what_the_schema_refuses_is_refused_by_its_field(
    schema: dict[str, Any], kind: str, body: dict[str, Any], field: str
) -> None:
    from mcgyvr.rig import protocol
    from mcgyvr.rig import sessionwire as w

    readers = {"port_map": w.read_port_map, "port_check": w.read_port_check}
    if field != "body.ports":  # a block past the end: the hub's model refuses
        # it, and a JSON Schema cannot say it
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
