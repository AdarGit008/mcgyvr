"""Which addresses a session's tunnel may use, decided on this rig and nowhere else.

The hub says where a rig's tunnel sits and whom it talks to (``tunnel_up``);
nothing it says is taken on trust. :func:`plan` reads that command against
this machine and refuses, by name, any address the tunnel must not use:

* the tunnel's own network must be private, hold at least two hosts, and
  overlap no network this machine is on (its LAN, its bridges, the tunnel
  container's own bridge) — a hub that put the session on the LAN's own
  addresses would route the LAN into the tunnel;
* every peer's allowed addresses must lie inside that network and not hold
  this rig's own address — an ``0.0.0.0/0`` would hand a peer every packet;
* a peer is reached at the first of its endpoints that is a LAN address
  (private, not loopback, link-local, multicast or reserved, outside the
  tunnel's network and none of this machine's own); a host name, a public
  address or anything else is skipped, and a peer with none is refused. Only
  LAN endpoints are taken for now; the endpoint list keeps room for the
  other kinds (``reflexive``, ``public``) a later traversal can add.

The endpoints this rig offers are its own LAN addresses (:func:`lan_hosts`),
or the ones its owner named; :func:`read_interfaces` reads them from the
kernel, with nothing spawned.
"""

from __future__ import annotations

import fcntl
import ipaddress
import socket
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from mcgyvr.rig import sessionwire

#: The narrowest network that holds two hosts.
NARROWEST_PREFIX = 30
#: The kernel's requests for an interface's address and its mask.
_SIOCGIFADDR = 0x8915
_SIOCGIFNETMASK = 0x891B
#: An ``ifreq``'s size and where its address sits in it.
_IFREQ_BYTES = 256
_IFNAME_BYTES = 16
_SOCKADDR_ADDRESS = slice(20, 24)
#: Interfaces that are this machine's own plumbing, never a LAN: loopback,
#: container bridges and their pairs, virtual machines' bridges, and tunnels.
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
    """A command this rig will not carry out as asked; ``code`` is the hub's."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, kw_only=True)
class PeerPlan:
    """One peer as the tunnel will be told of it."""

    rig_id: str
    public_key: str
    endpoint: ipaddress.IPv4Address
    port: int
    keepalive_s: int
    allowed: tuple[ipaddress.IPv4Network, ...]


@dataclass(frozen=True, kw_only=True)
class TunnelPlan:
    """The tunnel as it will be brought up."""

    address: ipaddress.IPv4Interface
    listen_port: int
    peers: tuple[PeerPlan, ...]

    def script_args(self) -> list[str]:
        """The arguments :data:`mcgyvr.sandbox.pooled.TUNNEL_SCRIPT` takes."""
        args = [str(self.address), str(self.listen_port)]
        for peer in self.peers:
            args += [
                peer.public_key,
                str(peer.endpoint),
                str(peer.port),
                str(peer.keepalive_s),
                ",".join(str(net) for net in peer.allowed),
            ]
        return args

    def peer_of(self, host: ipaddress.IPv4Address) -> PeerPlan | None:
        """The peer whose allowed addresses hold ``host``, if any."""
        for peer in self.peers:
            if any(host in net for net in peer.allowed):
                return peer
        return None

    def peer_nets(self) -> tuple[ipaddress.IPv4Network, ...]:
        """Every peer's allowed addresses."""
        return tuple(net for peer in self.peers for net in peer.allowed)


def is_lan(address: ipaddress.IPv4Address) -> bool:
    """Whether ``address`` is one a LAN peer may be reached at."""
    return address.is_private and not (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def read_interfaces() -> tuple[tuple[str, ipaddress.IPv4Interface], ...]:
    """This machine's IPv4 interfaces, by name, as the kernel has them now;
    none when they cannot be read."""
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
    """The addresses of ``interfaces`` a LAN peer may reach this rig at."""
    return tuple(
        interface.ip
        for name, interface in interfaces
        if not name.startswith(VIRTUAL_PREFIXES) and is_lan(interface.ip)
    )


def _endpoint(
    peer: sessionwire.TunnelPeer,
    network: ipaddress.IPv4Network,
    own: Sequence[ipaddress.IPv4Interface],
) -> tuple[ipaddress.IPv4Address, int]:
    for endpoint in peer.endpoints:
        try:
            host = ipaddress.IPv4Address(endpoint.host)
        except ValueError:
            continue
        if (
            is_lan(host)
            and host not in network
            and all(host != mine.ip for mine in own)
        ):
            return host, endpoint.port
    raise RefusedError(
        sessionwire.SessionCode.TUNNEL_FAILED,
        f"peer {peer.rig_id}: no endpoint this rig reaches peers at (a LAN address)",
    )


def plan(
    up: sessionwire.TunnelUp,
    *,
    listen_port: int,
    own: Sequence[ipaddress.IPv4Interface],
) -> TunnelPlan:
    """``up`` as this rig will bring it up, or :class:`RefusedError` naming what it
    will not do. ``own`` is every address this machine and the session's
    tunnel container are on."""
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
        host, port = _endpoint(peer, network, own)
        peers.append(
            PeerPlan(
                rig_id=peer.rig_id,
                public_key=peer.public_key,
                endpoint=host,
                port=port,
                keepalive_s=peer.keepalive_s,
                allowed=peer.allowed_ips,
            )
        )
    return TunnelPlan(address=address, listen_port=listen_port, peers=tuple(peers))
