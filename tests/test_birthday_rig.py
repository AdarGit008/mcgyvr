"""The rig's half of the birthday-paradox rung: it walks a ``birthday`` or
``birthday_burst`` candidate like any direct path, and probes/bursts a bounded
port range (never a scan of the whole space)."""

from __future__ import annotations

import ipaddress

import pytest

from mcgyvr import hubwire
from mcgyvr.rig import sessionwire, tunnel, udpwire


def _plan(peer: sessionwire.TunnelPeer) -> tunnel.TunnelPlan:
    up = sessionwire.TunnelUp(
        session_id="s1",
        address=ipaddress.IPv4Interface("198.51.100.2/24"),
        listen_port=51820,
        peers=(peer,),
    )
    return tunnel.plan(
        up, listen_port=51820, own=[ipaddress.IPv4Interface("192.0.2.10/24")]
    )


def test_a_birthday_candidate_is_a_direct_path_with_its_range() -> None:
    peer = sessionwire.TunnelPeer(
        rig_id="r1",
        public_key="B" * 42 + "g=",
        endpoints=(
            sessionwire.Endpoint(
                host="203.0.113.9", port=6000, kind="birthday", ports=1024
            ),
        ),
        allowed_ips=(ipaddress.IPv4Network("198.51.100.1/32"),),
        keepalive_s=0,
    )
    plan = _plan(peer)
    (candidate,) = plan.peers[0].candidates
    assert candidate.path == "direct"
    assert candidate.endpoint.kind == hubwire.BIRTHDAY_KIND
    assert candidate.ports == 1024


def test_a_burst_candidate_is_also_direct() -> None:
    peer = sessionwire.TunnelPeer(
        rig_id="r1",
        public_key="B" * 42 + "g=",
        endpoints=(
            sessionwire.Endpoint(
                host="203.0.113.9", port=4000, kind="birthday_burst", ports=256
            ),
        ),
        allowed_ips=(ipaddress.IPv4Network("198.51.100.1/32"),),
        keepalive_s=0,
    )
    plan = _plan(peer)
    (candidate,) = plan.peers[0].candidates
    assert candidate.path == "direct"
    assert candidate.endpoint.kind == hubwire.BIRTHDAY_BURST_KIND
    assert candidate.ports == 256


def test_endpoints_read_the_probe_hint_and_default_it_to_one() -> None:
    frame = sessionwire._frame(
        "tunnel_up",
        {
            "session_id": "s1",
            "address": "198.51.100.2/24",
            "listen_port": 51820,
            "peers": [
                {
                    "rig_id": "r1",
                    "public_key": "B" * 42 + "g=",
                    "allowed_ips": ["198.51.100.1/32"],
                    "endpoints": [
                        {
                            "host": "203.0.113.9",
                            "port": 6000,
                            "kind": "birthday",
                            "ports": 1024,
                        },
                        {"host": "198.51.100.1", "port": 4000, "kind": "reflexive"},
                    ],
                }
            ],
        },
        "a",
    )
    from mcgyvr.rig import protocol

    up = sessionwire.read_tunnel_up(protocol.decode(frame))
    (peer,) = up.peers
    birthday, reflexive = peer.endpoints
    assert birthday.ports == 1024
    assert reflexive.ports == 1  # the hint defaults to one


def test_the_probe_range_is_bounded_and_wraps() -> None:
    assert udpwire.birthday_ports(40001, 1024)[:3] == [40001, 40002, 40003]
    assert udpwire.birthday_ports(40001, 1024)[-1] == 41024
    assert udpwire.birthday_ports(65534, 3) == [65534, 65535, 1]
    assert len(udpwire.birthday_ports(60000, 2048)) == 2048
    with pytest.raises(ValueError):
        udpwire.birthday_ports(0, 1024)
    with pytest.raises(ValueError):
        udpwire.birthday_ports(40001, 2049)  # over the bound
