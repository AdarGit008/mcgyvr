"""A tunnel's endpoints are this rig's LAN addresses, never its own plumbing.

A rig offers its peers the addresses of its LAN interfaces, read from the
kernel with nothing spawned: not loopback, not a container bridge or its
pairs, not a virtual machine's bridge, not another tunnel, and not an
address a LAN peer cannot be reached at (link-local, multicast, reserved,
public). The plan of a tunnel keeps each peer's allowed addresses and the
LAN endpoint chosen for it, and hands the tunnel exactly those.
"""

from __future__ import annotations

import ipaddress

import pytest


def _iface(name: str, cidr: str) -> tuple[str, ipaddress.IPv4Interface]:
    return name, ipaddress.IPv4Interface(cidr)


def test_only_lan_interfaces_are_offered() -> None:
    from mcgyvr.rig import tunnel

    found = [
        _iface("lo", "127.0.0.1/8"),
        _iface("eth0", "192.0.2.10/24"),
        _iface("docker0", "198.51.100.1/24"),
        _iface("br-abc", "198.51.100.65/26"),
        _iface("veth12", "198.51.100.66/26"),
        _iface("tailscale0", "203.0.113.5/32"),
        _iface("wg0", "203.0.113.6/32"),
        _iface("enp5s0", "203.0.113.20/24"),
        _iface("eth2", str(ipaddress.IPv4Address(2**31 + 5)) + "/24"),
    ]
    assert [str(h) for h in tunnel.lan_hosts(found)] == ["192.0.2.10", "203.0.113.20"]


@pytest.mark.parametrize(
    ("address", "lan"),
    [
        ("192.0.2.1", True),
        ("127.0.0.1", False),
        ("0.0.0.0", False),
        (str(ipaddress.IPv4Address(2**31 + 5)), False),
    ],
)
def test_a_lan_address_is_private_and_nothing_else(address: str, lan: bool) -> None:
    from mcgyvr.rig import tunnel

    assert tunnel.is_lan(ipaddress.IPv4Address(address)) is lan


def test_this_machines_interfaces_are_read_from_the_kernel() -> None:
    from mcgyvr.rig import tunnel

    found = dict(tunnel.read_interfaces())
    assert any(iface.ip.is_loopback for iface in found.values())


def test_a_plan_hands_the_tunnel_exactly_the_peers_it_was_given() -> None:
    from mcgyvr.rig import sessionwire, tunnel

    up = sessionwire.TunnelUp(
        session_id="s1",
        address=ipaddress.IPv4Interface("198.51.100.2/24"),
        listen_port=51820,
        peers=(
            sessionwire.TunnelPeer(
                rig_id="r1",
                public_key="B" * 42 + "g=",
                endpoints=(
                    sessionwire.Endpoint(host="peer.invalid", port=1, kind="lan"),
                    sessionwire.Endpoint(host="192.0.2.20", port=51821, kind="lan"),
                ),
                allowed_ips=(ipaddress.IPv4Network("198.51.100.1/32"),),
                keepalive_s=0,
            ),
        ),
    )
    plan = tunnel.plan(
        up, listen_port=51820, own=[ipaddress.IPv4Interface("192.0.2.10/24")]
    )
    assert plan.script_args() == [
        "198.51.100.2/24",
        "51820",
        "B" * 42 + "g=",
        "192.0.2.20",
        "51821",
        "0",
        "198.51.100.1/32",
    ]
    peer = plan.peer_of(ipaddress.IPv4Address("198.51.100.1"))
    assert peer is not None and peer.rig_id == "r1"
    assert plan.peer_of(ipaddress.IPv4Address("198.51.100.3")) is None
