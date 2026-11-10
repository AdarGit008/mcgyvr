"""Forward this rig's tunnel ports on its home router, keep them, give them back.

A rig behind a home router is reached by its peers directly only when the
router forwards its tunnel ports. Consent to that is the owner's twice: on
the hub, when they add the rig, and on this rig (:class:`Consent`, the
``port_forward`` lending setting, off until they set it). The hub asks
(``port_map``) only after the first, and only a rig that names the
``port_map`` feature, which it does only after the second; an ask this rig
does not allow is refused all the same (``failed``, ``not_allowed``), and a
forward the owner withdraws here is given back within ``IDLE_S``. The ask
names the first of a block of external ports the hub chose (so two rigs
behind one router never ask for the same) and a lease. This module maps the
block, in order, on to this rig's own tunnel ports at its LAN address, by
UPnP IGD when the router answers it and else by NAT-PMP, renews every lease
before half of it is gone, and releases the block when the hub says so (a
``port_map`` with no external port), when the agent stops and when the rig
leaves. A lease is never permanent unless the owner allowed that too
(``port_forward_permanent``): a router that grants only permanent leases is
refused (``failed``, ``permanent_only``). Each outcome goes to the hub as a
``port_map_report``: mapped (with the method, the addresses and the lease),
failed (with why: the owner can then forward the ports by hand) or released.

Every mapping this rig makes is recorded (:data:`RECORD_FILE`, under the data
home) until it is given back, so an agent that starts after one that crashed
gives back what that one left first: a permanent mapping is kept on record
until its router takes the release, a leased one ends on its own.

The hub then checks the forward from outside (``port_check``): this rig opens
its first tunnel port for a few seconds and answers each probe ping that
carries the check's secret with its pong, at most
``udpwire.PORT_CHECK_MAX_PONGS`` of them, and sends nothing else from it.
Only a port this rig tunnels on is opened, and never one a session holds.

Everything a router or the network says is hostile. A UPnP description is
fetched only from the address that answered the discovery, over plain HTTP on
a private address, at most ``MAX_DESCRIPTION_BYTES``, and refused when it
declares a document type or an entity; a control URL must stay on that
address. At most ``MAX_LOCATIONS`` descriptions are fetched, each once, and a
device that answers only as a root device (a TV, a printer) is asked only
when nothing better answered, and is a router only if its description names
a WAN service. A NAT-PMP answer counts only from the gateway's own port with the
opcode and internal port that were asked.

The routers, the LAN hosts the tunnel is published on, this rig's tunnel
ports, the socket maker, the clock and the wait are handed in, so all of
this runs off fakes.
"""

from __future__ import annotations

import contextlib
import http.client
import ipaddress
import json
import re
import select
import socket
import struct
import sys
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mcgyvr import atomic, hubwire
from mcgyvr.rig import commands, protocol, sessionwire, tunnel, udpwire
from mcgyvr.rig.sessionwire import PortMapped, SessionCode

#: NAT-PMP (RFC 6886): the gateway's port, the first wait and the tries; each
#: try waits twice as long as the one before.
NATPMP_PORT = 5351
NATPMP_FIRST_WAIT_S = 0.25
NATPMP_TRIES = 4
#: UPnP: the discovery address, how long discovery listens, the WAN services
#: a router is called on (best first), the most bytes of a description or a
#: control answer, and each HTTP wait.
SSDP_ADDRESS = ("239.255.255.250", 1900)
SSDP_WAIT_S = 2.0
WAN_SERVICES = (
    "urn:schemas-upnp-org:service:WANIPConnection:2",
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
)
#: The gateway device types, and the root device every UPnP device is: some
#: routers answer only a search for one of these. A root device may be a TV or
#: a printer, so its description is fetched only when no better answer named a
#: router, and only its description decides (it must name a WAN service).
IGD_DEVICES = (
    "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
    "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
)
ROOT_DEVICE = "upnp:rootdevice"
SEARCH_TARGETS = (*WAN_SERVICES, *IGD_DEVICES, ROOT_DEVICE)
#: How many times each search is sent (a datagram may be lost), all within
#: the first half of ``SSDP_WAIT_S``; and the most locations discovery keeps.
SSDP_SENDS = 3
MAX_LOCATIONS = 8
MAX_DESCRIPTION_BYTES = 64 * 1024
HTTP_WAIT_S = 3.0
#: What a mapping says it is on the router.
DESCRIPTION = "mcgyvr tunnel"
#: How long the worker waits at most before it looks again; how soon, and how
#: many times, it retries a renewal the router did not take before it gives
#: the forward up; and how long stopping waits for a mapping under way.
IDLE_S = 60.0
RENEW_RETRY_S = 30.0
RENEW_TRIES = 3
CLOSE_WAIT_S = 30.0
#: How long one check's socket waits for datagrams per pass.
CHECK_SLICE_S = 0.1
#: The file, under the data home, that records the mappings this rig made and
#: has not given back; the most entries it keeps, and its largest size read.
RECORD_FILE = "rig-port-forward.json"
MAX_RECORDED = 8
MAX_RECORD_BYTES = 16384
#: The report's tags for a forward this rig's owner did not allow: the forward
#: itself, and a permanent lease (the only one some routers grant).
NOT_ALLOWED = hubwire.PORT_MAP_NOT_ALLOWED
PERMANENT_ONLY = hubwire.PORT_MAP_PERMANENT_ONLY
#: The settings that allow each, as the owner sets them (``mcgyvr rig share``).
ALLOW_FORWARD = "mcgyvr rig share --port-forward"
ALLOW_PERMANENT = "mcgyvr rig share --permanent-forward"
#: A router that could not be reached keeps what it holds: the release is
#: tried again at the next start.
_UNREACHED = {"timeout", "no_gateway"}

# UPnP error codes that say why a mapping was refused.
_UPNP_CONFLICT = {718}  # ConflictInMappingEntry
_UPNP_PERMANENT_ONLY = 725  # OnlyPermanentLeasesSupported
# NAT-PMP result codes.
_NATPMP_REFUSED = {2}  # not authorized
_NATPMP_UNSUPPORTED = {1, 5}
_DECLARATION = re.compile(rb"<!(DOCTYPE|ENTITY)", re.IGNORECASE)
_UPNP_NO_ENTRY = 714  # NoSuchEntryInArray: the external port maps nothing
# Which failure the report names when no router maps: the most telling one.
_RANK = {"conflict": 2, "permanent_only": 1}


def _plain(raw: bytes) -> bool:
    """Whether ``raw`` is XML this module reads: bounded, one-byte encoded (no
    NUL, so no UTF-16 past the declaration check), with no type or entity."""
    return (
        len(raw) <= MAX_DESCRIPTION_BYTES
        and b"\x00" not in raw
        and not _DECLARATION.search(raw)
    )


@dataclass(frozen=True)
class Consent:
    """What the owner allowed on this rig: a port forward at all, and one
    with a permanent lease on a router that grants no other."""

    forward: bool = False
    permanent: bool = False


class MapError(Exception):
    """A router would not map a port; ``error`` is the report's tag for why."""

    def __init__(self, error: str, message: str) -> None:
        super().__init__(message)
        self.error = error
        self.message = message


class Router(Protocol):
    """One way to ask the home router for a forward."""

    method: str  # upnp, natpmp

    def address(self) -> dict[str, str]:
        """What names this router again after a restart (:func:`recall`)."""
        ...

    def lan_host(self) -> str:
        """This host's address on the router's LAN, where forwards land."""
        ...

    def external_address(self) -> str | None:
        """The address the router says it has outside, when it says one."""
        ...

    def add(self, *, lan_host: str, internal: int, external: int, lease_s: int) -> int:
        """Forward ``external`` to ``lan_host:internal``; the lease granted."""
        ...

    def remove(self, *, lan_host: str, internal: int, external: int) -> None:
        """Take that forward away again, unless it now forwards somewhere else."""
        ...


# --- finding the router --------------------------------------------------------


def default_gateway(route_table: str = "/proc/net/route") -> str | None:
    """The IPv4 default gateway, from the kernel's route table, or None."""
    try:
        with open(route_table, encoding="ascii") as table:
            lines = table.read().splitlines()[1:]
    except OSError:
        return None
    for line in lines:
        fields = line.split()
        if len(fields) < 3 or fields[1] != "00000000":
            continue
        try:
            raw = int(fields[2], 16)
        except ValueError:
            continue
        gateway = ipaddress.IPv4Address(struct.pack("<I", raw))
        if gateway.is_private and not gateway.is_unspecified:
            return str(gateway)
    return None


def local_address(peer: str, port: int = NATPMP_PORT) -> str | None:
    """The address this host sends to ``peer`` from (no packet goes out)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect((peer, port))
            host: str = sock.getsockname()[0]
        except OSError:
            return None
    return host


def _lan_address(host: str) -> bool:
    """A private address a router or a LAN host may have: not loopback, not
    link-local (what a record names, which is read back, not found)."""
    if not _private(host):
        return False
    address = ipaddress.IPv4Address(host)
    return not (address.is_loopback or address.is_link_local)


def _private(host: str) -> bool:
    try:
        address = ipaddress.IPv4Address(host)
    except ValueError:
        return False
    return address.is_private and not (address.is_unspecified or address.is_multicast)


# --- NAT-PMP --------------------------------------------------------------------


class NatPmp:
    """NAT-PMP (RFC 6886) against one gateway: UDP map, unmap and its address."""

    method = "natpmp"

    def __init__(
        self,
        gateway: str,
        *,
        port: int = NATPMP_PORT,
        first_wait_s: float = NATPMP_FIRST_WAIT_S,
        tries: int = NATPMP_TRIES,
        lan: Callable[[str], str | None] = local_address,
    ) -> None:
        self._gateway = gateway
        self._port = port
        self._first_wait_s = first_wait_s
        self._tries = tries
        self._lan = lan

    def address(self) -> dict[str, str]:
        return {"gateway": self._gateway}

    def lan_host(self) -> str:
        host = self._lan(self._gateway)
        if host is None:
            raise MapError("no_gateway", f"no route to the gateway {self._gateway}")
        return host

    def _ask(self, request: bytes, opcode: int) -> bytes:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            wait = self._first_wait_s
            for _ in range(self._tries):
                try:
                    sock.sendto(request, (self._gateway, self._port))
                except OSError as exc:
                    raise MapError("no_gateway", f"NAT-PMP: {exc}") from exc
                ends = time.monotonic() + wait
                while (left := ends - time.monotonic()) > 0:
                    ready, _, _ = select.select([sock], [], [], left)
                    if not ready:
                        break
                    data, source = sock.recvfrom(64)
                    if source != (self._gateway, self._port) or len(data) < 8:
                        continue
                    if data[0] != 0 or data[1] != 128 + opcode:
                        continue
                    return data
                wait *= 2
        raise MapError("timeout", "the gateway does not answer NAT-PMP")

    @staticmethod
    def _result(data: bytes) -> None:
        (code,) = struct.unpack_from("!H", data, 2)
        if code == 0:
            return
        if code in _NATPMP_REFUSED:
            raise MapError("refused", "NAT-PMP: the gateway refused the mapping")
        if code in _NATPMP_UNSUPPORTED:
            raise MapError("unsupported", f"NAT-PMP: result {code}")
        raise MapError("failed", f"NAT-PMP: result {code}")

    def external_address(self) -> str | None:
        data = self._ask(b"\x00\x00", 0)
        if len(data) < 12:
            return None
        self._result(data)
        return str(ipaddress.IPv4Address(data[8:12]))

    def _map(self, internal: int, external: int, lease_s: int) -> tuple[int, int]:
        request = struct.pack("!BBHHHI", 0, 1, 0, internal, external, lease_s)
        data = self._ask(request, 1)
        if len(data) < 16:
            raise MapError("failed", "NAT-PMP: a short answer")
        self._result(data)
        _, _, _, _, got_internal, got_external, granted = struct.unpack(
            "!BBHIHHI", data[:16]
        )
        if got_internal != internal:
            raise MapError("failed", "NAT-PMP: an answer for another port")
        return got_external, granted

    def add(self, *, lan_host: str, internal: int, external: int, lease_s: int) -> int:
        if lease_s == 0:  # a lifetime of 0 asks NAT-PMP to delete, not to keep
            raise MapError(PERMANENT_ONLY, "NAT-PMP maps with a lease only")
        got, granted = self._map(internal, external, lease_s)
        if got != external:
            with contextlib.suppress(MapError):
                self._map(internal, 0, 0)
            raise MapError("conflict", f"NAT-PMP gave port {got}, not {external}")
        if granted == 0:
            with contextlib.suppress(MapError):
                self._map(internal, 0, 0)
            raise MapError("failed", "NAT-PMP granted no lifetime")
        return granted

    def remove(self, *, lan_host: str, internal: int, external: int) -> None:
        # NAT-PMP removes this host's own mapping of ``internal``, nobody else's.
        self._map(internal, 0, 0)


# --- UPnP IGD -------------------------------------------------------------------


def ssdp_search(target: str, mx: int = 2) -> bytes:
    """The M-SEARCH datagram that asks for one search target, to be answered
    within ``mx`` seconds."""
    return (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDRESS[0]}:{SSDP_ADDRESS[1]}\r\n"
        'MAN: "ssdp:discover"\r\n'
        f"MX: {mx}\r\n"
        f"ST: {target}\r\n\r\n"
    ).encode("ascii")


def read_ssdp(data: bytes, source: str) -> tuple[str, str] | None:
    """The description URL a discovery answer names, and the target it
    answers (:data:`SEARCH_TARGETS`), when it may be fetched.

    Only an HTTP answer naming one of the targets searched for, whose URL is
    plain HTTP on the very private address the answer came from, is kept.
    """
    try:
        text = data.decode("latin-1")
    except UnicodeDecodeError:  # pragma: no cover - latin-1 decodes any byte
        return None
    lines = text.split("\r\n")
    if not lines or not lines[0].startswith("HTTP/1.") or " 200 " not in lines[0]:
        return None
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    target = headers.get("st", "")
    if target not in SEARCH_TARGETS:
        return None
    location = headers.get("location", "")
    try:
        url = urllib.parse.urlsplit(location)
        _ = url.port  # a port out of range raises here, not at the fetch
    except ValueError:
        return None
    if url.scheme != "http" or url.hostname != source or not _private(source):
        return None
    return location, target


def read_description(raw: bytes, location: str) -> tuple[str, str] | None:
    """The first WAN service a device description names: its type and control URL.

    Refused (None) when the document declares a type or an entity, does not
    parse, or puts its control URL on another host than the description's.
    """
    if not _plain(raw):
        return None
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None
    base = urllib.parse.urlsplit(location)
    found: dict[str, str] = {}
    for node in root.iter():
        if not node.tag.endswith("service"):
            continue
        kind = control = None
        for child in node:
            if child.tag.endswith("serviceType"):
                kind = (child.text or "").strip()
            elif child.tag.endswith("controlURL"):
                control = (child.text or "").strip()
        if kind in WAN_SERVICES and control and kind not in found:
            url = urllib.parse.urljoin(location, control)
            parts = urllib.parse.urlsplit(url)
            if parts.scheme == "http" and parts.netloc == base.netloc:
                found[kind] = url
    for kind in WAN_SERVICES:
        if kind in found:
            return kind, found[kind]
    return None


def _xml_text(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def soap_body(
    service: str, action: str, arguments: Sequence[tuple[str, object]]
) -> str:
    """The SOAP envelope that calls ``action`` on ``service``."""
    inner = "".join(f"<{k}>{_xml_text(v)}</{k}>" for k, v in arguments)
    return (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f'<s:Body><u:{action} xmlns:u="{_xml_text(service)}">{inner}'
        f"</u:{action}></s:Body></s:Envelope>"
    )


def read_soap(raw: bytes) -> dict[str, str]:
    """The leaf values of a SOAP answer, by local name (a fault's too)."""
    if not _plain(raw):
        raise MapError("failed", "UPnP: an answer that is no plain SOAP")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise MapError("failed", "UPnP: an answer that does not parse") from exc
    values = {}
    for node in root.iter():
        if len(node) == 0:
            values[node.tag.rpartition("}")[2]] = (node.text or "").strip()
    return values


@dataclass(frozen=True)
class Gateway:
    """A UPnP gateway found on the LAN: its service and where to call it."""

    service: str
    control: str


class Upnp:
    """UPnP IGD against one gateway's WAN service: map, unmap and its address."""

    method = "upnp"

    def __init__(
        self,
        gateway: Gateway,
        *,
        lan: Callable[[str], str | None] = local_address,
        wait_s: float = HTTP_WAIT_S,
    ) -> None:
        self._gateway = gateway
        self._url = urllib.parse.urlsplit(gateway.control)
        self._lan = lan
        self._wait_s = wait_s

    def address(self) -> dict[str, str]:
        return {"service": self._gateway.service, "control": self._gateway.control}

    def lan_host(self) -> str:
        host = self._lan(self._url.hostname or "")
        if host is None:
            raise MapError("no_gateway", "no route to the UPnP gateway")
        return host

    def _call(
        self, action: str, arguments: Sequence[tuple[str, object]]
    ) -> dict[str, str]:
        body = soap_body(self._gateway.service, action, arguments).encode()
        connection = http.client.HTTPConnection(
            self._url.hostname or "", self._url.port or 80, timeout=self._wait_s
        )
        try:
            connection.request(
                "POST",
                self._url.path or "/",
                body=body,
                headers={
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPAction": f'"{self._gateway.service}#{action}"',
                },
            )
            answer = connection.getresponse()
            raw = answer.read(MAX_DESCRIPTION_BYTES + 1)
        except (OSError, http.client.HTTPException) as exc:
            raise MapError("timeout", f"UPnP {action}: {exc}") from exc
        finally:
            connection.close()
        values = read_soap(raw)
        if answer.status != 200:
            code = values.get("errorCode", "")
            raise _upnp_error(action, int(code) if code.isdigit() else 0, values)
        return values

    def external_address(self) -> str | None:
        found = self._call("GetExternalIPAddress", ()).get("NewExternalIPAddress", "")
        try:
            return str(ipaddress.IPv4Address(found))
        except ValueError:
            return None

    def _add(self, lan_host: str, internal: int, external: int, lease_s: int) -> None:
        self._call(
            "AddPortMapping",
            (
                ("NewRemoteHost", ""),
                ("NewExternalPort", external),
                ("NewProtocol", "UDP"),
                ("NewInternalPort", internal),
                ("NewInternalClient", lan_host),
                ("NewEnabled", 1),
                ("NewPortMappingDescription", DESCRIPTION),
                ("NewLeaseDuration", lease_s),
            ),
        )

    def _held_by_another(self, lan_host: str, internal: int, external: int) -> bool:
        """Whether the external port already forwards somewhere else (a router
        may overwrite another device's forward without a word)."""
        try:
            entry = self._call(
                "GetSpecificPortMappingEntry",
                (
                    ("NewRemoteHost", ""),
                    ("NewExternalPort", external),
                    ("NewProtocol", "UDP"),
                ),
            )
        except MapError:
            return False  # no such entry (714), or a router that cannot say
        if not entry.get("NewInternalClient"):
            return False
        return (entry.get("NewInternalClient"), entry.get("NewInternalPort")) != (
            lan_host,
            str(internal),
        )

    def add(self, *, lan_host: str, internal: int, external: int, lease_s: int) -> int:
        """Map with ``lease_s``, 0 for a permanent lease; a router that takes
        only a permanent one refuses any other (``permanent_only``)."""
        if self._held_by_another(lan_host, internal, external):
            raise MapError("conflict", f"UPnP: port {external} forwards elsewhere")
        self._add(lan_host, internal, external, lease_s)
        return lease_s

    def remove(self, *, lan_host: str, internal: int, external: int) -> None:
        if self._held_by_another(lan_host, internal, external):
            return  # the port went to another device since: it is not ours to take
        self._call(
            "DeletePortMapping",
            (
                ("NewRemoteHost", ""),
                ("NewExternalPort", external),
                ("NewProtocol", "UDP"),
            ),
        )


def _upnp_error(action: str, code: int, values: dict[str, str]) -> MapError:
    said = sessionwire.scrub(values.get("errorDescription", ""))[:200]
    if code == _UPNP_PERMANENT_ONLY:
        return MapError(PERMANENT_ONLY, f"UPnP {action}: only permanent leases")
    if code in _UPNP_CONFLICT:
        return MapError("conflict", f"UPnP {action}: {code} {said}".strip())
    if code in {606, 714, 729} or 600 <= code < 700:
        return MapError("refused", f"UPnP {action}: {code} {said}".strip())
    return MapError("failed", f"UPnP {action}: {code} {said}".strip())


def lan_interfaces() -> tuple[str, ...]:
    """This host's LAN addresses, its own plumbing (bridges, tunnels, loopback)
    left out (:func:`mcgyvr.rig.tunnel.lan_hosts`): discovery searches on each."""
    return tuple(str(host) for host in tunnel.lan_hosts(tunnel.read_interfaces()))


def _udp() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def _search(
    sock: socket.socket,
    address: tuple[str, int],
    ways: Sequence[str | None],
    mx: int,
) -> bool:
    """Send every search target once on each way out (an interface's address,
    or None for the system's default); whether any datagram went. A way that
    cannot send is skipped."""
    sent = False
    for way in ways:
        try:
            sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_MULTICAST_IF,
                socket.inet_aton(way or "0.0.0.0"),
            )
            for target in SEARCH_TARGETS:
                sock.sendto(ssdp_search(target, mx), address)
                sent = True
        except OSError:
            continue
    return sent


def discover_upnp(
    *,
    wait_s: float = SSDP_WAIT_S,
    fetch: Callable[[str], bytes] | None = None,
    interfaces: Callable[[], Sequence[str]] = lan_interfaces,
    address: tuple[str, int] = SSDP_ADDRESS,
    sock: Callable[[], socket.socket] = _udp,
) -> list[Gateway]:
    """The UPnP WAN services that answer discovery on the LAN, best first.

    Every target of :data:`SEARCH_TARGETS` is searched for on the system's
    default way out and on each LAN interface (``interfaces``, by address),
    :data:`SSDP_SENDS` times within the first half of ``wait_s``, and answers
    are heard for ``wait_s`` in all. An answer to a WAN service or a gateway
    device is fetched first; a root device's only when none of those named a
    router. At most :data:`MAX_LOCATIONS` descriptions are fetched, each one
    once, and only a description naming a WAN service becomes a gateway.
    """
    fetch = fetch or _fetch
    own = tuple(dict.fromkeys(interfaces()))
    # The default way out is searched on too, unless it is one of those.
    ways = (*(() if local_address(*address) in own else (None,)), *own)
    routers: list[str] = []  # answered a WAN service or a gateway device
    roots: list[str] = []  # answered the root device alone so far
    with sock() as udp:
        udp.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        started = time.monotonic()
        ends = started + wait_s
        if not _search(udp, address, ways, max(1, int(wait_s))):
            return []
        sends = 1
        while (left := ends - time.monotonic()) > 0 and len(routers) < MAX_LOCATIONS:
            due = started + sends * wait_s / (2 * max(1, SSDP_SENDS - 1))
            if sends < SSDP_SENDS and time.monotonic() >= due:
                _search(udp, address, ways, max(1, int(left)))
                sends += 1
                continue
            wait = min(left, due - time.monotonic()) if sends < SSDP_SENDS else left
            ready, _, _ = select.select([udp], [], [], max(0.0, wait))
            if not ready:
                continue
            try:
                data, source = udp.recvfrom(2048)
            except OSError:  # an ICMP error some systems hand an unconnected socket
                continue
            answer = read_ssdp(data, source[0])
            if answer is None:
                continue
            location, target = answer
            if target != ROOT_DEVICE:
                if location in roots:
                    roots.remove(location)
                if location not in routers:
                    routers.append(location)
            elif location not in routers and location not in roots:
                if len(roots) < MAX_LOCATIONS:
                    roots.append(location)
    found: list[Gateway] = []
    for index, location in enumerate([*routers, *roots][:MAX_LOCATIONS]):
        if index >= len(routers) and found:
            break  # a root device is asked only when nothing better is a router
        try:
            described = read_description(fetch(location), location)
        except (OSError, http.client.HTTPException):
            continue
        if described is not None and Gateway(*described) not in found:
            found.append(Gateway(*described))
    return sorted(found, key=lambda gateway: WAN_SERVICES.index(gateway.service))


def _fetch(location: str) -> bytes:
    url = urllib.parse.urlsplit(location)
    connection = http.client.HTTPConnection(
        url.hostname or "", url.port or 80, timeout=HTTP_WAIT_S
    )
    try:
        connection.request("GET", url.path or "/")
        answer = connection.getresponse()
        if answer.status != 200:
            return b""
        return answer.read(MAX_DESCRIPTION_BYTES + 1)
    finally:
        connection.close()


def find_routers() -> list[Router]:
    """The ways to ask this LAN's router for a forward: UPnP first, then NAT-PMP."""
    routers: list[Router] = [Upnp(g) for g in discover_upnp()]
    gateway = default_gateway()
    if gateway is not None:
        routers.append(NatPmp(gateway))
    return routers


def recall(method: str, address: Mapping[str, str]) -> Router | None:
    """The router a record names (:meth:`Router.address`), held to what a
    found one may be: a NAT-PMP gateway or a UPnP control URL, plain HTTP, on
    a private LAN address (no loopback, no link-local); else None."""
    if method == NatPmp.method:
        gateway = address.get("gateway", "")
        return NatPmp(gateway) if _lan_address(gateway) else None
    if method == Upnp.method:
        service, control = address.get("service", ""), address.get("control", "")
        try:
            url = urllib.parse.urlsplit(control)
            _ = url.port
        except ValueError:
            return None
        if (
            service in WAN_SERVICES
            and url.scheme == "http"
            and _lan_address(url.hostname or "")
        ):
            return Upnp(Gateway(service, control))
    return None


# --- the record -------------------------------------------------------------------


@dataclass(frozen=True)
class Recorded:
    """A mapping this rig made and has not given back, as its record keeps it."""

    method: str
    address: dict[str, str]
    lan_host: str
    internal: int
    external: int
    ports: int
    lease_s: int

    def data(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "address": dict(self.address),
            "lan_host": self.lan_host,
            "internal": self.internal,
            "external": self.external,
            "ports": self.ports,
            "lease_s": self.lease_s,
        }


def _recorded(entry: object) -> Recorded | None:
    """One record entry, or None when it is not the shape this module writes."""
    if not isinstance(entry, dict):
        return None
    address = entry.get("address")
    numbers = [entry.get(k) for k in ("internal", "external", "ports", "lease_s")]
    whole = [n for n in numbers if type(n) is int]
    if (
        not isinstance(entry.get("method"), str)
        or not isinstance(address, dict)
        or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in address.items()
        )
        or not _lan_address(str(entry.get("lan_host", "")))
        or len(whole) != len(numbers)
    ):
        return None
    internal, external, ports, lease = whole
    if not (
        1 <= ports <= sessionwire.PORT_MAP_PORTS
        and 1 <= internal <= sessionwire.MAX_PORT - ports + 1
        and 1 <= external <= sessionwire.MAX_PORT - ports + 1
        and 0 <= lease <= sessionwire.MAX_PORT_MAP_LEASE_S
    ):
        return None
    return Recorded(
        method=entry["method"],
        address=address,
        lan_host=entry["lan_host"],
        internal=internal,
        external=external,
        ports=ports,
        lease_s=lease,
    )


def read_record(path: Path) -> list[Recorded]:
    """The mappings ``path`` records; nothing for a missing, oversized or
    unreadable file, and entries of another shape are skipped."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_RECORD_BYTES + 1)
        data = json.loads(raw.decode("utf-8")) if len(raw) <= MAX_RECORD_BYTES else []
    except (OSError, UnicodeError, ValueError):
        return []
    entries = data.get("mappings") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    return [r for r in map(_recorded, entries[:MAX_RECORDED]) if r is not None]


def write_record(path: Path, mappings: Sequence[Recorded]) -> None:
    """Record ``mappings`` (the file goes when there are none), at most
    :data:`MAX_RECORDED`: past that the oldest leased ones go first (they end
    on their own), and a permanent one only with a note that it is forgotten."""
    if not mappings:
        path.unlink(missing_ok=True)
        return
    kept = list(mappings)
    for permanent in (False, True):
        while len(kept) > MAX_RECORDED:
            index = next(
                (i for i, m in enumerate(kept) if (m.lease_s == 0) == permanent), None
            )
            if index is None:
                break
            gone = kept.pop(index)
            if permanent:
                print(
                    f"note: the port forward's record is full; the permanent "
                    f"forward of external port {gone.external} on {gone.lan_host} "
                    "is forgotten, not given back",
                    file=sys.stderr,
                )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = {"mappings": [m.data() for m in kept]}
    atomic.write(path, json.dumps(data) + "\n", private=True)


# --- the mapper -----------------------------------------------------------------


@dataclass
class _Held:
    router: Router
    lan_host: str
    internal: int
    external: int
    ports: int
    lease_s: int
    renew_at: float | None  # None: a permanent lease, never renewed
    misses: int = 0  # renewals in a row the router did not take


@dataclass
class _Check:
    asked: sessionwire.PortCheck
    sock: socket.socket
    ends_at: float
    pongs: int = 0
    closed: threading.Event = field(default_factory=threading.Event)


class Mapper:
    """The forward the hub asked for, kept until it says otherwise or the agent ends.

    ``send`` posts a frame through the agent's one outbox. ``tunnel_ports`` is
    this rig's tunnel ports in order (the block maps on to its first ones),
    ``hosts`` the LAN addresses its tunnel is published on (a forward to any
    other address would land nowhere), and ``routers`` finds the ways to ask
    the router, best first. ``consent`` is what the owner allowed on this rig,
    read afresh at each pass (none by default: every ask is refused).
    ``record`` is the file the mappings are recorded in (None: not recorded),
    and ``recall`` names a recorded router again. ``clock`` drives renewals
    and checks.
    """

    def __init__(
        self,
        *,
        send: Callable[[str], bool],
        tunnel_ports: Callable[[], Sequence[int]],
        hosts: Callable[[], Sequence[str]],
        routers: Callable[[], Sequence[Router]] = find_routers,
        consent: Callable[[], Consent] = Consent,
        record: Path | None = None,
        recall: Callable[[str, Mapping[str, str]], Router | None] = recall,
        bind_host: str = "0.0.0.0",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._send = send
        self._tunnel_ports = tunnel_ports
        self._hosts = hosts
        self._routers = routers
        self._consent = consent
        self._record = record
        self._recall = recall
        self._leftover: list[Recorded] = []  # permanent, not given back yet
        self._pending: Recorded | None = None  # being mapped: recorded first
        self._bind_host = bind_host
        self._clock = clock
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._wanted: sessionwire.PortMap | None = None
        self._asked = False  # a port_map came that the worker has not acted on
        self._held: _Held | None = None
        self._checks: list[_Check] = []
        self._thread: threading.Thread | None = None

    # Frames from the hub: each returns a refusal to send back, or the ack.

    def ask(self, envelope: protocol.Envelope) -> str | None:
        """Take a ``port_map``: the worker maps, moves or releases the block."""
        asked = sessionwire.read_port_map(envelope)
        with self._lock:
            self._wanted = asked if asked.external_port is not None else None
            self._asked = True
        self._wake.set()
        return sessionwire.ack(envelope.id)

    def check(self, envelope: protocol.Envelope) -> str | None:
        """Take a ``port_check``: answer the hub's pings on a tunnel port a while."""
        asked = sessionwire.read_port_check(envelope)
        if not self._consent().forward:
            return sessionwire.refusal(
                envelope.id,
                SessionCode.NOT_CAPABLE,
                "port: no port forward is allowed on this rig",
            )
        if asked.port not in self._tunnel_ports():
            return sessionwire.refusal(
                envelope.id, SessionCode.NOT_CAPABLE, "port: not a tunnel port here"
            )
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self._bind_host, asked.port))
        except OSError:
            sock.close()
            return sessionwire.refusal(
                envelope.id, SessionCode.BUSY, "port: held by a session"
            )
        check = _Check(asked=asked, sock=sock, ends_at=self._clock() + asked.ttl_s)
        with self._lock:
            self._checks.append(check)
        threading.Thread(target=self._answer, args=(check,), daemon=True).start()
        return sessionwire.ack(envelope.id)

    # What the agent calls.

    def start(self) -> None:
        """Run the worker on a thread of its own."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def release_check(self, port: int) -> None:
        """Close any check on ``port``: a session is about to take it."""
        with self._lock:
            holding = [c for c in self._checks if c.asked.port == port]
        for check in holding:
            check.closed.set()
            with contextlib.suppress(OSError):
                check.sock.close()

    def close(self) -> None:
        """Give the forward back and end the worker: the agent stops."""
        self._stopped.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=CLOSE_WAIT_S)
        with self._lock:
            checks = list(self._checks)
        for check in checks:
            check.closed.set()
        self._release(report=self._held is not None)

    # The worker.

    def give_back_recorded(self) -> None:
        """Give back what an agent before this one recorded and left mapped
        (it crashed, or its host lost power): this one wants none of it until
        the hub asks. Only to a router this rig is on the LAN of now, as the
        one that mapped it: a rig that moved (a laptop that crashed at home
        and starts elsewhere) sends nothing to whatever holds that address
        here. A permanent mapping not given back (its router is elsewhere or
        not reached) stays on record for the next start; a leased one ends on
        its own."""
        if self._record is None:
            return
        left = read_record(self._record)
        kept = []
        given = 0
        for entry in left:
            router = self._recall(entry.method, entry.address)
            if router is None:
                continue
            reached = self._here(router, entry.lan_host) and self._give_back(
                router, entry.lan_host, entry.internal, entry.external, entry.ports
            )
            if reached:
                given += 1
            elif entry.lease_s == 0:
                kept.append(entry)
        if left:
            print(
                f"port forward: gave back {given} of the {len(left)} forward(s) "
                "an agent before this one left on the router"
                + (f"; {len(kept)} kept on record" if kept else ""),
                file=sys.stderr,
            )
        self._leftover = kept
        self._write_record()

    def _run(self) -> None:
        try:
            self.give_back_recorded()
        except Exception as exc:  # the worker must outlive a bad record
            print(f"port forward: {exc!r}", file=sys.stderr)
        while not self._stopped.is_set():
            try:
                wait = self.tick()
            except Exception as exc:  # the worker must outlive any one pass
                print(f"port forward: {exc!r}", file=sys.stderr)
                wait = IDLE_S
            self._wake.wait(wait)
            self._wake.clear()

    def tick(self) -> float:
        """One pass of the worker: act on the latest ask, renew what is due.

        Returns how long to wait before the next pass at most.
        """
        with self._lock:
            wanted, asked = self._wanted, self._asked
            self._asked = False
        allowed = self._consent()
        held = self._held
        if not allowed.forward and (held is not None or (asked and wanted is not None)):
            # Not allowed on this rig (or no longer): what is held goes back,
            # and the hub hears it refused, with how the owner allows it.
            print(
                "port forward: "
                + ("no longer allowed here, given back" if held else "refused")
                + f": this rig does not allow it; `{ALLOW_FORWARD}` allows it",
                file=sys.stderr,
            )
            if asked and wanted is None:  # the hub asked it back: it is
                self._release(report=True)
                return IDLE_S
            self._release(report=False)
            self._report(
                PortMapped(
                    state="failed",
                    error=NOT_ALLOWED,
                    message="the rig's owner has not allowed a port forward on "
                    f"the rig; `{ALLOW_FORWARD}` there allows it",
                )
            )
            return IDLE_S
        if held is not None and held.lease_s == 0 and not allowed.permanent:
            # A permanent lease the owner no longer allows: given back, and
            # the block mapped again with a lease, or refused.
            self._release(report=wanted is None)
            held = None
            asked = wanted is not None
        if asked:
            if held is not None and self._same(held, wanted):
                # The same block again (a reconnect): map it afresh, since the
                # router may have lost it, and say so, so the hub checks it
                # once more. A refusal or a new LAN address maps from scratch.
                if self._refresh(held):
                    self._report(self._mapped(held))
                else:
                    self._release(report=False)
                    held = None
            elif held is not None:
                self._release(report=wanted is None)
                held = None
            elif wanted is None:
                self._report(PortMapped(state="released"))
            if wanted is not None and held is None:
                self._map(wanted, allowed)
                if self._stopped.is_set():  # it stopped while the router mapped
                    self._release(report=False)
        elif held is not None and held.renew_at is not None:
            if self._clock() >= held.renew_at:
                self._renew(held)
        held = self._held
        if held is None or held.renew_at is None:
            return IDLE_S
        return max(0.0, min(IDLE_S, held.renew_at - self._clock()))

    def _same(self, held: _Held, wanted: sessionwire.PortMap | None) -> bool:
        return wanted is not None and (wanted.external_port, wanted.ports) == (
            held.external,
            held.ports,
        )

    def _block(self, wanted: sessionwire.PortMap) -> tuple[int, int] | None:
        ports = list(self._tunnel_ports())
        count = min(wanted.ports, len(ports))
        if count == 0 or ports[:count] != list(range(ports[0], ports[0] + count)):
            return None
        return ports[0], count

    def _map(self, wanted: sessionwire.PortMap, allowed: Consent) -> None:
        assert wanted.external_port is not None
        block = self._block(wanted)
        if block is None:
            self._report(
                PortMapped(state="failed", error="no_port", message="no tunnel ports")
            )
            return
        internal, count = block
        failure = MapError("no_gateway", "no UPnP or NAT-PMP router answered")
        for router in self._routers():
            try:
                held = self._add(
                    router, internal, wanted.external_port, count, wanted, allowed
                )
            except MapError as exc:
                # A conflict says the hub's block is taken, a permanent lease
                # what the owner may allow: worth saying over a router that
                # merely does not speak the method.
                if _RANK.get(exc.error, 0) >= _RANK.get(failure.error, 0):
                    failure = exc
                continue
            self._held = held
            self._write_record()
            self._report(self._mapped(held))
            return
        message = failure.message
        if failure.error == PERMANENT_ONLY and not allowed.permanent:
            message += (
                "; this rig allows no permanent lease "
                f"(`{ALLOW_PERMANENT}` allows one), or forward the ports by hand"
            )
            print(f"port forward: refused: {message}", file=sys.stderr)
        # What the owner forwards by hand instead: the block on to the first
        # private IPv4 address the tunnel is published on (none: the hub says).
        lan = next((h for h in self._hosts() if _private(h)), None)
        self._report(
            PortMapped(
                state="failed",
                error=failure.error,
                message=message,
                lan_host=lan,
                internal_port=internal,
                external_port=wanted.external_port,
                ports=count,
            )
        )

    def _add(
        self,
        router: Router,
        internal: int,
        external: int,
        count: int,
        wanted: sessionwire.PortMap,
        allowed: Consent,
    ) -> _Held:
        lan_host = router.lan_host()
        if lan_host not in self._hosts():
            raise MapError("no_lan_host", f"{lan_host} is no address the tunnel is on")
        added: set[int] = set()
        # Recorded before the router is asked, so a crash mid-way leaves it on
        # record (as permanent when one may be granted, which only UPnP does:
        # kept until given back).
        self._pending = Recorded(
            method=router.method,
            address=router.address(),
            lan_host=lan_host,
            internal=internal,
            external=external,
            ports=count,
            lease_s=(
                0
                if allowed.permanent and router.method == Upnp.method
                else wanted.lease_s
            ),
        )
        self._write_record()

        def block(lease_s: int) -> list[int]:
            granted = []
            for offset in range(count):
                granted.append(
                    router.add(
                        lan_host=lan_host,
                        internal=internal + offset,
                        external=external + offset,
                        lease_s=lease_s,
                    )
                )
                added.add(offset)
            return granted

        try:
            try:
                granted = block(wanted.lease_s)
            except MapError as exc:
                if exc.error != PERMANENT_ONLY or not allowed.permanent:
                    raise
                granted = block(0)  # the whole block, so no port's lease runs out
            if 0 in granted and not allowed.permanent:
                raise MapError(
                    PERMANENT_ONLY,
                    f"{router.method}: the router granted a permanent lease",
                )
        except MapError:
            for offset in sorted(added):
                with contextlib.suppress(MapError):
                    router.remove(
                        lan_host=lan_host,
                        internal=internal + offset,
                        external=external + offset,
                    )
            self._pending = None
            self._write_record()
            raise
        self._pending = None
        lease = min(min(granted), sessionwire.MAX_PORT_MAP_LEASE_S)
        return _Held(
            router=router,
            lan_host=lan_host,
            internal=internal,
            external=external,
            ports=count,
            lease_s=lease,
            renew_at=None if lease == 0 else self._clock() + lease / 2,
        )

    def _mapped(self, held: _Held) -> PortMapped:
        try:
            outside = held.router.external_address()
        except MapError:
            outside = None
        if outside is not None and not _ipv4(outside):
            outside = None
        return PortMapped(
            state="mapped",
            method=held.router.method,
            lan_host=held.lan_host,
            internal_port=held.internal,
            external_port=held.external,
            ports=held.ports,
            router_host=outside,
            lease_s=held.lease_s,
        )

    def _refresh(self, held: _Held) -> bool:
        """Map the held block again where it is; False when the router refuses
        or this host's LAN address changed (the forward would land elsewhere)."""
        try:
            self._readd(held)
        except MapError:
            return False
        held.misses = 0
        held.renew_at = None if held.lease_s == 0 else self._clock() + held.lease_s / 2
        return True

    def _readd(self, held: _Held) -> None:
        if held.router.lan_host() != held.lan_host:
            raise MapError("no_lan_host", "this host's LAN address changed")
        for offset in range(held.ports):
            held.router.add(
                lan_host=held.lan_host,
                internal=held.internal + offset,
                external=held.external + offset,
                lease_s=held.lease_s,
            )

    def _renew(self, held: _Held) -> None:
        try:
            self._readd(held)
        except MapError as exc:
            if exc.error == "no_lan_host":
                # The DHCP lease moved this host: the old address may be
                # another device's now. Give it back, map the block afresh.
                self._release(report=False)
                with self._lock:
                    wanted = self._wanted
                if wanted is not None:
                    self._map(wanted, self._consent())
                return
            held.misses += 1
            if held.misses < RENEW_TRIES:
                held.renew_at = self._clock() + RENEW_RETRY_S
                return
            self._release(report=False)
            self._report(
                PortMapped(state="failed", error=exc.error, message=exc.message)
            )
            return
        held.misses = 0
        held.renew_at = self._clock() + held.lease_s / 2

    def _release(self, *, report: bool) -> None:
        held, self._held = self._held, None
        if held is not None:
            reached = self._give_back(
                held.router, held.lan_host, held.internal, held.external, held.ports
            )
            if not reached and held.lease_s == 0:
                self._leftover.append(self._recorded(held))
            self._write_record()
        if report:
            self._report(PortMapped(state="released"))

    def _here(self, router: Router, lan_host: str) -> bool:
        """Whether this rig is on ``router``'s LAN now, at ``lan_host``: a
        route lookup, no packet sent (a router with no route is not here)."""
        try:
            return router.lan_host() == lan_host and lan_host in self._hosts()
        except MapError:
            return False

    @staticmethod
    def _give_back(
        router: Router, lan_host: str, internal: int, external: int, ports: int
    ) -> bool:
        """Remove each port of a block; False when the router was not reached."""
        reached = True
        for offset in range(ports):
            try:
                router.remove(
                    lan_host=lan_host,
                    internal=internal + offset,
                    external=external + offset,
                )
            except MapError as exc:
                reached = reached and exc.error not in _UNREACHED
        return reached

    @staticmethod
    def _recorded(held: _Held) -> Recorded:
        return Recorded(
            method=held.router.method,
            address=held.router.address(),
            lan_host=held.lan_host,
            internal=held.internal,
            external=held.external,
            ports=held.ports,
            lease_s=held.lease_s,
        )

    def _write_record(self) -> None:
        """Record what is held and what is not given back yet."""
        if self._record is None:
            return
        entries = [*self._leftover]
        if self._held is not None:
            entries.append(self._recorded(self._held))
        if self._pending is not None:
            entries.append(self._pending)
        try:
            write_record(self._record, entries)
        except OSError as exc:
            print(
                f"note: the port forward's record was not written: {exc}",
                file=sys.stderr,
            )

    def _report(self, report: PortMapped) -> None:
        self._send(sessionwire.port_map_report(report))

    # A check's thread.

    def _answer(self, check: _Check) -> None:
        try:
            while not check.closed.is_set() and self._clock() < check.ends_at:
                try:
                    ready, _, _ = select.select([check.sock], [], [], CHECK_SLICE_S)
                except (OSError, ValueError):
                    return
                if not ready:
                    continue
                try:
                    data, source = check.sock.recvfrom(udpwire.RECEIVE_BYTES)
                except OSError:
                    return
                if self._pong(check, data):
                    with contextlib.suppress(OSError):
                        check.sock.sendto(udpwire.pong(data) or b"", source)
                    if check.pongs >= udpwire.PORT_CHECK_MAX_PONGS:
                        return
        finally:
            with contextlib.suppress(OSError):
                check.sock.close()
            with self._lock:
                if check in self._checks:
                    self._checks.remove(check)

    @staticmethod
    def _pong(check: _Check, data: bytes) -> bool:
        packet = udpwire.read_probe(data)
        if packet is None or packet.kind != udpwire.PING:
            return False
        if packet.secret != check.asked.secret or udpwire.pong(data) is None:
            return False
        check.pongs += 1
        return True


def _ipv4(host: str) -> bool:
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return False
    return True


def register(dispatcher: commands.Dispatcher, mapper: Mapper) -> None:
    """Handle ``port_map`` and ``port_check`` on the agent's dispatcher."""
    dispatcher.register("port_map", lambda envelope, _: mapper.ask(envelope))
    dispatcher.register("port_check", lambda envelope, _: mapper.check(envelope))
