"""Plan a rig's WireGuard tunnel from the addresses this machine actually has.

The machine's IPv4 interfaces are read from the kernel with ioctl and nothing
spawned, its LAN addresses are told apart from its plumbing, and each peer's
endpoints are reduced to the ones this rig may aim at, in the peer's own order.
A tunnel-up is then laid out into a plan whose address, port and peer
reachability have been checked first, and whose allowed addresses do not
overlap this machine or each other; the plan hands the tunnel script exactly
those settings.
"""

from __future__ import annotations

import fcntl
import ipaddress
import socket
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from mcgyvr.rig import sessionwire

#: The narrowest tunnel network allowed: a /30, the smallest that still holds
#: two host addresses.
NARROWEST_PREFIX = 30
#: ioctl requests for an interface's IPv4 address and its netmask.
_SIOCGIFADDR = 0x8915
_SIOCGIFNETMASK = 0x891B
#: The buffer an ifreq ioctl is handed, the room the interface's name takes in
#: it, and where the address sits in the buffer the ioctl hands back.
_IFREQ_BYTES = 256
_IFNAME_BYTES = 16
_SOCKADDR_ADDRESS = slice(20, 24)
#: Interface names starting with these are this machine's own plumbing, not a
#: LAN to offer a peer: loopback, container and VM bridges and their pairs,
#: cluster and overlay networks, and other tunnels.
VIRTUAL_PREFIXES = (
    "lo",
    "docker",
    "br-",
    "veth",
    "virbr",
    "vnet",
    "cni",
    "flannel",
    "cali",
    "tailscale",
    "wg",
    "tun",
    "tap",
    "zt",
)


class RefusedError(Exception):
    """A tunnel was refused, with the code and message to refuse it by."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


#: The path a reachable peer is reported on: one found on this LAN is "lan",
#: one reached at a public or reflexive address is "direct".
PATHS = {"lan": "lan", "public": "direct", "reflexive": "direct"}


@dataclass(frozen=True, kw_only=True)
class Candidate:
    """One address a peer may be reached at, and the port to aim at there."""

    endpoint: sessionwire.Endpoint
    host: ipaddress.IPv4Address
    port: int

    @property
    def path(self) -> str:
        return PATHS[self.endpoint.kind]


@dataclass(frozen=True, kw_only=True)
class RelayAim:
    """The relay granted for a peer, and the address this rig may reach it at."""

    grant: sessionwire.RelayGrant
    host: ipaddress.IPv4Address


@dataclass(frozen=True, kw_only=True)
class PeerPlan:
    """A peer as the tunnel is told about it: its key, its keepalive interval,
    the addresses it is allowed, the candidates to aim at in order, and a relay
    to fall back on when none of them answers."""

    rig_id: str
    public_key: str
    keepalive_s: int
    allowed: tuple[ipaddress.IPv4Network, ...]
    candidates: tuple[Candidate, ...]
    relay: RelayAim | None = None

    @property
    def tunnel_host(self) -> ipaddress.IPv4Address | None:
        """The peer's own address inside the tunnel, taken from the first
        allowed network that is a single host, or None if it has none."""
        for net in self.allowed:
            if net.prefixlen == net.max_prefixlen:
                return net.network_address
        return None


@dataclass(frozen=True, kw_only=True)
class TunnelPlan:
    """This rig's end of a tunnel: its address on it, the port it listens on,
    and what was planned for each peer."""

    address: ipaddress.IPv4Interface
    listen_port: int
    peers: tuple[PeerPlan, ...]

    def script_args(self) -> list[str]:
        """The arguments the tunnel script is run with: this end's address and
        listen port, then five per peer — its public key, the first candidate's
        address and port ("-" and "0" when it has none), its keepalive in
        seconds, and its allowed addresses joined by commas."""
        args = [str(self.address), str(self.listen_port)]
        for peer in self.peers:
            first = peer.candidates[0] if peer.candidates else None
            args += [
                peer.public_key,
                str(first.host) if first else "-",
                str(first.port) if first else "0",
                str(peer.keepalive_s),
                ",".join(str(net) for net in peer.allowed),
            ]
        return args

    def peer_of(self, host: ipaddress.IPv4Address) -> PeerPlan | None:
        """The peer whose allowed addresses hold this address, or None."""
        for peer in self.peers:
            if any(host in net for net in peer.allowed):
                return peer
        return None

    def peer_nets(self) -> tuple[ipaddress.IPv4Network, ...]:
        """Every peer's allowed addresses, peer by peer."""
        return tuple(net for peer in self.peers for net in peer.allowed)


def is_lan(address: ipaddress.IPv4Address) -> bool:
    """Whether a private address is one a peer on this LAN could be reached at:
    not loopback, link-local, multicast, reserved or unspecified."""
    return address.is_private and not (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def read_interfaces() -> tuple[tuple[str, ipaddress.IPv4Interface], ...]:
    """Every IPv4 interface this machine has, as its name and address, asked of
    the kernel with ioctl on one datagram socket and nothing spawned.

    An interface the kernel will not give an address for is left out, and an
    empty result means the kernel could not be asked at all.
    """
    found: list[tuple[str, ipaddress.IPv4Interface]] = []
    try:
        names = [name for _, name in socket.if_nameindex()]
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return ()
    with probe:
        for name in names:
            request = struct.pack(
                f"{_IFNAME_BYTES}s{_IFREQ_BYTES - _IFNAME_BYTES}x",
                name.encode()[: _IFNAME_BYTES - 1],
            )
            try:
                address = fcntl.ioctl(probe.fileno(), _SIOCGIFADDR, request)
                mask = fcntl.ioctl(probe.fileno(), _SIOCGIFNETMASK, request)
            except OSError:
                continue
            host = socket.inet_ntoa(address[_SOCKADDR_ADDRESS])
            netmask = socket.inet_ntoa(mask[_SOCKADDR_ADDRESS])
            found.append((name, ipaddress.IPv4Interface(f"{host}/{netmask}")))
    return tuple(found)


def lan_hosts(
    interfaces: Iterable[tuple[str, ipaddress.IPv4Interface]],
) -> tuple[ipaddress.IPv4Address, ...]:
    """The addresses of the interfaces a peer may be offered: those whose name
    is not this machine's plumbing and whose address is a LAN address."""
    return tuple(
        interface.ip
        for name, interface in interfaces
        if not name.startswith(VIRTUAL_PREFIXES) and is_lan(interface.ip)
    )


def may_aim_at(
    host: ipaddress.IPv4Address,
    network: ipaddress.IPv4Network | None,
    own: Sequence[ipaddress.IPv4Interface],
) -> bool:
    """Whether this rig may aim a tunnel at an address: not one no peer is
    reached at (loopback, link-local, multicast, reserved, unspecified), not
    one inside the tunnel's own network, and not one this machine already has."""
    return not (
        host.is_loopback
        or host.is_link_local
        or host.is_multicast
        or host.is_reserved
        or host.is_unspecified
        or (network is not None and host in network)
        or any(host == mine.ip for mine in own)
    )


def candidates(
    peer: sessionwire.TunnelPeer,
    network: ipaddress.IPv4Network,
    own: Sequence[ipaddress.IPv4Interface],
) -> tuple[Candidate, ...]:
    """The peer's endpoints this rig may aim at, in the order the peer gave
    them: each one an IPv4 address of a kind that has a path, a LAN endpoint
    only when its address is a LAN address, and none of them an address the rig
    may not aim at."""
    found = []
    for endpoint in peer.endpoints:
        host = sessionwire._ipv4(endpoint.host)
        if host is None or endpoint.kind not in PATHS:
            continue
        if endpoint.kind == "lan" and not is_lan(host):
            continue
        if may_aim_at(host, network, own):
            found.append(Candidate(endpoint=endpoint, host=host, port=endpoint.port))
    return tuple(found)


def _relay(
    peer: sessionwire.TunnelPeer,
    network: ipaddress.IPv4Network,
    own: Sequence[ipaddress.IPv4Interface],
) -> RelayAim | None:
    if peer.relay is None:
        return None
    host = sessionwire._ipv4(peer.relay.host)
    if host is None or not may_aim_at(host, network, own):
        return None
    return RelayAim(grant=peer.relay, host=host)


def plan(
    up: sessionwire.TunnelUp,
    *,
    listen_port: int,
    own: Sequence[ipaddress.IPv4Interface],
) -> TunnelPlan:
    """Lay out the tunnel a tunnel-up asks for, having checked it against this
    machine: the listen port is the one this session was prepared on, the
    tunnel's address is a host's address on a private network of at least two
    hosts that overlaps no network this machine is on, and every peer's allowed
    addresses sit inside the tunnel, leave this rig's own address alone, overlap
    no other peer's, and include an endpoint or relay this rig may aim at.

    A tunnel-up that breaks any of these is refused by code and message; an
    accepted one becomes a plan carrying the port asked for."""
    if up.listen_port != listen_port:
        raise RefusedError(
            "bad_message", "listen_port: not the port this session was prepared on"
        )
    address = up.address
    network = address.network
    if not (is_lan(address.ip) and network.is_private):
        raise RefusedError(
            sessionwire.SessionCode.TUNNEL_FAILED,
            "address: the tunnel's network is not a private one",
        )
    if network.prefixlen > NARROWEST_PREFIX:
        raise RefusedError(
            sessionwire.SessionCode.TUNNEL_FAILED,
            "address: the tunnel's network holds fewer than two hosts",
        )
    if address.ip in (network.network_address, network.broadcast_address):
        raise RefusedError(
            sessionwire.SessionCode.TUNNEL_FAILED, "address: not a host's address"
        )
    for mine in own:
        if network.overlaps(mine.network):
            raise RefusedError(
                sessionwire.SessionCode.TUNNEL_FAILED,
                "address: the tunnel's network overlaps one this machine is on",
            )
    peers = []
    taken: list[ipaddress.IPv4Network] = []
    for peer in up.peers:
        for net in peer.allowed_ips:
            if not net.subnet_of(network):
                raise RefusedError(
                    sessionwire.SessionCode.TUNNEL_FAILED,
                    f"peer {peer.rig_id}: an allowed address outside the tunnel",
                )
            if address.ip in net:
                raise RefusedError(
                    sessionwire.SessionCode.TUNNEL_FAILED,
                    f"peer {peer.rig_id}: allowed this rig's own address",
                )
            if any(net.overlaps(other) for other in taken):
                raise RefusedError(
                    sessionwire.SessionCode.TUNNEL_FAILED,
                    f"peer {peer.rig_id}: allowed another peer's address",
                )
            taken.append(net)
        found = candidates(peer, network, own)
        relay = _relay(peer, network, own)
        if not found and relay is None:
            raise RefusedError(
                sessionwire.SessionCode.TUNNEL_FAILED,
                f"peer {peer.rig_id}: no endpoint or relay this rig may reach it at",
            )
        peers.append(
            PeerPlan(
                rig_id=peer.rig_id,
                public_key=peer.public_key,
                keepalive_s=peer.keepalive_s,
                allowed=peer.allowed_ips,
                candidates=found,
                relay=relay,
            )
        )
    return TunnelPlan(address=address, listen_port=listen_port, peers=tuple(peers))
