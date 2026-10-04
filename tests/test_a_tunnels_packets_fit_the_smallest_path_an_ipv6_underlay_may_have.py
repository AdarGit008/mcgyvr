"""A tunnel's packets fit the smallest path an IPv6 underlay may have.

WireGuard wraps each packet of the tunnel in its own header, a UDP header
and the underlay's IP header. A wrapped packet larger than a link on the
path is lost, and the tunnel cannot learn of it: its table drops the ICMP
that would say so. So the interface's MTU is set once, to what fits the
smallest MTU an IPv6 path may have, and a model's weights cross a relay over
such a path as they cross a LAN.
"""

from __future__ import annotations

#: The smallest MTU a link carrying IPv6 may have (RFC 8200).
SMALLEST_IPV6_MTU = 1280
#: What WireGuard adds to a packet over IPv6: its header and tag (32), UDP (8)
#: and IPv6 (40).
OVERHEAD = 32 + 8 + 40


def test_a_wrapped_packet_fits_the_smallest_ipv6_link() -> None:
    from mcgyvr.sandbox import pooled

    assert pooled.TUNNEL_MTU + OVERHEAD <= SMALLEST_IPV6_MTU


def test_the_tunnel_brings_its_interface_up_at_that_mtu() -> None:
    from mcgyvr.sandbox import pooled

    entry = pooled.TUNNEL_ENTRY
    ups = [line for line in entry.splitlines() if line.startswith("ip link set wg0")]
    assert ups == [f"ip link set wg0 mtu {pooled.TUNNEL_MTU} up"]
    # The interface has its MTU before the agent is told the tunnel is ready.
    assert entry.index(ups[0]) < entry.index('echo "ready"')
