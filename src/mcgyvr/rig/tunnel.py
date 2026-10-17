""

from __future__ import annotations

import fcntl
import ipaddress
import socket
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from mcgyvr.rig import sessionwire

#
NARROWEST_PREFIX = 30
#
_SIOCGIFADDR = 0x8915
_SIOCGIFNETMASK = 0x891B
#
_IFREQ_BYTES = 256
_IFNAME_BYTES = 16
_SOCKADDR_ADDRESS = slice(20, 24)
#
#
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
    ""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


#
PATHS = {"lan": "lan", "public": "direct", "reflexive": "direct"}


@dataclass(frozen=True, kw_only=True)
class Candidate:
    ""

    endpoint: sessionwire.Endpoint
    host: ipaddress.IPv4Address
    port: int

    @property
    def path(self) -> str:
        return PATHS[self.endpoint.kind]


@dataclass(frozen=True, kw_only=True)
class RelayAim:
    ""

    grant: sessionwire.RelayGrant
    host: ipaddress.IPv4Address


@dataclass(frozen=True, kw_only=True)
class PeerPlan:
    ""

    rig_id: str
    public_key: str
    keepalive_s: int
    allowed: tuple[ipaddress.IPv4Network, ...]
    candidates: tuple[Candidate, ...]
    relay: RelayAim | None = None

    @property
    def tunnel_host(self) -> ipaddress.IPv4Address | None:
        ""
        for net in self.allowed:
            if net.prefixlen == net.max_prefixlen:
                return net.network_address
        return None


@dataclass(frozen=True, kw_only=True)
class TunnelPlan:
    ""

    address: ipaddress.IPv4Interface
    listen_port: int
    peers: tuple[PeerPlan, ...]

    def script_args(self) -> list[str]:
        ""
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
        ""
        for peer in self.peers:
            if any(host in net for net in peer.allowed):
                return peer
        return None

    def peer_nets(self) -> tuple[ipaddress.IPv4Network, ...]:
        ""
        return tuple(net for peer in self.peers for net in peer.allowed)


def is_lan(address: ipaddress.IPv4Address) -> bool:
    ""
    return address.is_private and not (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def read_interfaces() -> tuple[tuple[str, ipaddress.IPv4Interface], ...]:
    ""
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
    ""
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
    ""
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
    ""
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
    ""
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
