"""The router clients speak NAT-PMP and UPnP IGD, and trust no answer blindly.

NAT-PMP maps, unmaps and reads the external address against a gateway on a
local UDP port, and refuses an answer for another port, a refusal and a
different external port (a conflict, undone). UPnP keeps a discovery answer
only when its URL is plain HTTP on the private address that answered, reads
a description only without a document type or entity and with its control
URL on the same host, and maps, unmaps and reads the address by SOAP against
a local HTTP server, a conflict and a permanent-only lease read by code.
Discovery, against devices on a local UDP port, searches for WAN services,
gateway devices and the root device, each more than once and on each LAN
interface, within the same wait; a root device (a printer) costs one fetch at
most and is never a router, and at most eight descriptions are fetched, each
over within its wait however slowly the device answers.
"""

from __future__ import annotations

import contextlib
import inspect
import ipaddress
import socket
import struct
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from mcgyvr.rig import portmap, tunnel

# --- NAT-PMP ---------------------------------------------------------------------


class Gateway:
    """A NAT-PMP gateway on 127.0.0.1: answers each request by ``answer``."""

    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port: int = self.sock.getsockname()[1]
        self.asked: list[bytes] = []
        self.result = 0
        self.give_external: int | None = None  # else the suggested one
        self.give_lease: int | None = None  # else the asked one
        self.wrong_internal = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while True:
            try:
                data, source = self.sock.recvfrom(64)
            except OSError:
                return
            self.asked.append(data)
            if data[1] == 0:
                answer = struct.pack("!BBHI", 0, 128, self.result, 7) + bytes(
                    [198, 51, 100, 7]
                )
            else:
                _, _, _, internal, external, lease = struct.unpack("!BBHHHI", data)
                if self.give_external is not None and external:
                    external = self.give_external
                if self.wrong_internal:
                    internal += 1
                if self.give_lease is not None and external:
                    lease = self.give_lease
                answer = struct.pack(
                    "!BBHIHHI", 0, 129, self.result, 7, internal, external, lease
                )
            self.sock.sendto(answer, source)

    def close(self) -> None:
        self.sock.close()


@pytest.fixture
def gateway() -> Iterator[Gateway]:
    found = Gateway()
    yield found
    found.close()


def natpmp(gateway: Gateway) -> portmap.NatPmp:
    return portmap.NatPmp(
        "127.0.0.1",
        port=gateway.port,
        first_wait_s=0.05,
        tries=2,
        lan=lambda _: "192.168.1.20",
    )


def test_natpmp_maps_unmaps_and_reads_the_external_address(gateway: Gateway) -> None:
    client = natpmp(gateway)
    assert client.lan_host() == "192.168.1.20"
    assert client.external_address() == "198.51.100.7"
    lease = client.add(
        lan_host="192.168.1.20", internal=51820, external=52000, lease_s=600
    )
    assert lease == 600
    assert struct.unpack("!BBHHHI", gateway.asked[-1]) == (0, 1, 0, 51820, 52000, 600)
    client.remove(lan_host="192.168.1.20", internal=51820, external=52000)
    assert struct.unpack("!BBHHHI", gateway.asked[-1]) == (0, 1, 0, 51820, 0, 0)


def test_natpmp_says_a_refusal_and_a_conflict_and_undoes_the_conflict(
    gateway: Gateway,
) -> None:
    client = natpmp(gateway)
    gateway.give_external = 60000
    with pytest.raises(portmap.MapError) as conflict:
        client.add(lan_host="x", internal=51820, external=52000, lease_s=600)
    assert conflict.value.error == "conflict"
    assert struct.unpack("!BBHHHI", gateway.asked[-1])[4:] == (0, 0)  # undone
    gateway.give_external = None
    gateway.result = 2
    with pytest.raises(portmap.MapError) as refused:
        client.add(lan_host="x", internal=51820, external=52000, lease_s=600)
    assert refused.value.error == "refused"


def test_natpmp_never_asks_for_nor_keeps_a_lifetime_of_zero(gateway: Gateway) -> None:
    client = natpmp(gateway)
    # A lifetime of 0 deletes in NAT-PMP: never sent as a "permanent" lease.
    with pytest.raises(portmap.MapError) as zero:
        client.add(lan_host="x", internal=51820, external=52000, lease_s=0)
    assert zero.value.error == portmap.PERMANENT_ONLY
    assert gateway.asked == []
    gateway.give_lease = 0
    with pytest.raises(portmap.MapError) as none:
        client.add(lan_host="x", internal=51820, external=52000, lease_s=600)
    assert none.value.error == "failed"
    assert struct.unpack("!BBHHHI", gateway.asked[-1])[4:] == (0, 0)  # undone


def test_natpmp_refuses_an_answer_for_another_port(gateway: Gateway) -> None:
    gateway.wrong_internal = True
    with pytest.raises(portmap.MapError) as wrong:
        natpmp(gateway).add(lan_host="x", internal=51820, external=52000, lease_s=600)
    assert wrong.value.error == "failed"


def test_natpmp_times_out_on_a_silent_gateway() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as silent:
        silent.bind(("127.0.0.1", 0))
        client = portmap.NatPmp(
            "127.0.0.1", port=silent.getsockname()[1], first_wait_s=0.02, tries=2
        )
        with pytest.raises(portmap.MapError) as timed_out:
            client.external_address()
    assert timed_out.value.error == "timeout"


def test_the_default_gateway_is_read_from_the_route_table(tmp_path: Path) -> None:
    table = tmp_path / "route"
    table.write_text(
        "Iface\tDestination\tGateway\tFlags\n"
        "eth0\t0001A8C0\t00000000\t0001\n"
        "eth0\t00000000\t0101A8C0\t0003\n",
        encoding="ascii",
    )
    assert portmap.default_gateway(str(table)) == "192.168.1.1"
    table.write_text("Iface\tDestination\tGateway\n", encoding="ascii")
    assert portmap.default_gateway(str(table)) is None
    assert portmap.default_gateway(str(tmp_path / "none")) is None


# --- UPnP: discovery and description ------------------------------------------

WAN = "urn:schemas-upnp-org:service:WANIPConnection:1"


def ssdp(location: str, st: str = WAN) -> bytes:
    return (
        f"HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=120\r\nST: {st}\r\n"
        f"LOCATION: {location}\r\n\r\n"
    ).encode()


def test_a_discovery_answer_is_kept_only_from_its_own_private_address() -> None:
    url = "http://192.168.1.1:5000/rootDesc.xml"
    assert portmap.read_ssdp(ssdp(url), "192.168.1.1") == (url, WAN)
    assert portmap.read_ssdp(ssdp(url), "192.168.1.9") is None
    public = "http://8.8.8.8/desc.xml"
    assert portmap.read_ssdp(ssdp(public), "8.8.8.8") is None
    assert portmap.read_ssdp(ssdp("https://192.168.1.1/x"), "192.168.1.1") is None
    assert portmap.read_ssdp(b"NOTIFY * HTTP/1.1\r\n\r\n", "192.168.1.1") is None


def test_an_answer_to_a_gateway_device_or_the_root_device_is_kept_too() -> None:
    url = "http://192.168.1.1:5000/rootDesc.xml"
    for target in (*portmap.IGD_DEVICES, portmap.ROOT_DEVICE):
        assert portmap.read_ssdp(ssdp(url, st=target), "192.168.1.1") == (url, target)
        assert portmap.read_ssdp(ssdp(url, st=target), "192.168.1.9") is None
    other = "urn:schemas-upnp-org:device:MediaRenderer:1"
    assert portmap.read_ssdp(ssdp(url, st=other), "192.168.1.1") is None
    assert portmap.read_ssdp(ssdp(url, st="ssdp:all"), "192.168.1.1") is None
    # A LOCATION no URL parser takes is dropped, not raised out of discovery.
    for broken in ("http://[192.168.1.1/x", "http://192.168.1.1:99999/x"):
        assert portmap.read_ssdp(ssdp(broken), "192.168.1.1") is None


def description(control: str, kind: str = WAN, extra: str = "") -> bytes:
    return (
        f'<?xml version="1.0"?>{extra}<root xmlns="urn:schemas-upnp-org:device-1-0">'
        "<device><serviceList><service>"
        "<serviceType>urn:schemas-upnp-org:service:Layer3Forwarding:1</serviceType>"
        "<controlURL>/l3f</controlURL></service></serviceList>"
        "<deviceList><device><serviceList><service>"
        f"<serviceType>{kind}</serviceType><controlURL>{control}</controlURL>"
        "</service></serviceList></device></deviceList></device></root>"
    ).encode()


def test_a_description_names_its_wan_service_on_its_own_host() -> None:
    at = "http://192.168.1.1:5000/rootDesc.xml"
    assert portmap.read_description(description("/ctl/IPConn"), at) == (
        WAN,
        "http://192.168.1.1:5000/ctl/IPConn",
    )
    assert portmap.read_description(description("http://10.0.0.9/ctl"), at) is None
    assert portmap.read_description(description("/ctl", kind="urn:x"), at) is None
    bomb = '<!DOCTYPE r [<!ENTITY a "aaaa">]>'
    assert portmap.read_description(description("/ctl", extra=bomb), at) is None
    assert portmap.read_description(b"<root><unclosed>", at) is None
    big = description("/ctl") + b" " * portmap.MAX_DESCRIPTION_BYTES
    assert portmap.read_description(big, at) is None


def igd_tree(
    control: str, kind: str = WAN, device: str = portmap.IGD_DEVICES[1]
) -> bytes:
    """A router's description as IGD:1 and :2 lay it out: the gateway device,
    its WAN device, and the WAN connection device that holds the service."""
    return (
        '<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0">'
        "<specVersion><major>1</major><minor>0</minor></specVersion>"
        f"<device><deviceType>{device}</deviceType><deviceList>"
        "<device><deviceType>urn:schemas-upnp-org:device:WANDevice:1</deviceType>"
        "<serviceList><service><serviceType>urn:schemas-upnp-org:service:"
        "WANCommonInterfaceConfig:1</serviceType><controlURL>/cic</controlURL>"
        "</service></serviceList><deviceList><device><deviceType>"
        "urn:schemas-upnp-org:device:WANConnectionDevice:1</deviceType>"
        f"<serviceList><service><serviceType>{kind}</serviceType>"
        f"<controlURL>{control}</controlURL></service></serviceList>"
        "</device></deviceList></device></deviceList></device></root>"
    ).encode()


TV = (
    b'<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device>'
    b"<deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>"
    b"<serviceList><service><serviceType>urn:schemas-upnp-org:service:"
    b"AVTransport:1</serviceType><controlURL>/av</controlURL></service>"
    b"</serviceList></device></root>"
)


def test_a_wan_service_is_found_deep_in_a_gateway_devices_tree() -> None:
    at = "http://192.168.1.1:5000/rootDesc.xml"
    for device in portmap.IGD_DEVICES:
        assert portmap.read_description(igd_tree("/ctl", device=device), at) == (
            WAN,
            "http://192.168.1.1:5000/ctl",
        )
    assert portmap.read_description(igd_tree("http://10.0.0.9/ctl"), at) is None
    assert portmap.read_description(TV, at) is None  # a root device, no router


# --- UPnP: discovery on the LAN ---------------------------------------------------

#: How long the discovery tests listen: short, the same logic as the 2 s.
WAIT_S = 0.4


class Lan:
    """Devices on 127.0.0.1 that answer M-SEARCH: ``answers`` maps a search
    target to the locations that answer it; the first ``lose`` searches of
    each target are lost on the way."""

    def __init__(self, answers: dict[str, list[str]], lose: int = 0) -> None:
        self.answers = answers
        self.lose = lose
        self.heard: list[str] = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.address: tuple[str, int] = self.sock.getsockname()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                data, source = self.sock.recvfrom(2048)
            except OSError:
                return
            text = data.decode("ascii")
            assert text.startswith("M-SEARCH * HTTP/1.1\r\n")
            target = text.partition("\r\nST: ")[2].partition("\r\n")[0]
            self.heard.append(target)
            if self.heard.count(target) <= self.lose:
                continue
            for location in self.answers.get(target, []):
                try:
                    self.sock.sendto(ssdp(location, st=target), source)
                except OSError:  # closed by the test while answering
                    return

    def close(self) -> None:
        self.sock.close()


@pytest.fixture
def lan() -> Iterator[list[Lan]]:
    made: list[Lan] = []
    yield made
    for one in made:
        one.close()


class Ways(socket.socket):
    """A real UDP socket that records the interface each search goes out on,
    fails to send on the addresses in ``dead``, and takes the invented
    interfaces in ``invented`` as this host's (the kernel refuses them)."""

    def __init__(
        self, dead: tuple[str, ...] = (), invented: tuple[str, ...] = ()
    ) -> None:
        super().__init__(socket.AF_INET, socket.SOCK_DGRAM)
        self.dead = dead
        self.invented = invented
        self.out: list[str] = []
        self.via = ""

    def setsockopt(self, level: int, name: int, value: Any) -> None:  # type: ignore[override]
        if name == socket.IP_MULTICAST_IF:
            self.via = socket.inet_ntoa(value)
            if self.via in self.dead:
                raise OSError(99, "Cannot assign requested address")
            if self.via in self.invented:
                return
        super().setsockopt(level, name, value)

    def sendto(self, data: Any, address: Any) -> int:  # type: ignore[override]
        self.out.append(self.via)
        return super().sendto(data, address)


ROUTER = "http://127.0.0.1:5000/rootDesc.xml"
PRINTER = "http://127.0.0.1:6000/printer.xml"


class Fetch:
    """Descriptions by location, and every location asked for."""

    def __init__(self, documents: dict[str, bytes]) -> None:
        self.documents = documents
        self.asked: list[str] = []

    def __call__(self, location: str) -> bytes:
        self.asked.append(location)
        if location not in self.documents:
            raise OSError("connection refused")
        return self.documents[location]


def discover(
    lan: Lan,
    fetch: Fetch,
    interfaces: tuple[str, ...] = (),
    sock: Ways | None = None,
) -> list[portmap.Gateway]:
    made = sock or Ways()
    return portmap.discover_upnp(
        wait_s=WAIT_S,
        fetch=fetch,
        interfaces=lambda: interfaces,
        address=lan.address,
        sock=lambda: made,
    )


def test_a_router_that_answers_only_a_gateway_device_search_is_found(
    lan: list[Lan],
) -> None:
    for device in portmap.IGD_DEVICES:
        lan.append(Lan({device: [ROUTER]}))
        fetch = Fetch({ROUTER: igd_tree("/ctl", device=device)})
        assert discover(lan[-1], fetch) == [
            portmap.Gateway(WAN, "http://127.0.0.1:5000/ctl")
        ]
        assert fetch.asked == [ROUTER]


def test_a_root_device_is_a_router_only_if_its_description_names_a_wan_service(
    lan: list[Lan],
) -> None:
    lan.append(Lan({portmap.ROOT_DEVICE: [PRINTER, ROUTER]}))
    fetch = Fetch({PRINTER: TV, ROUTER: igd_tree("/ctl")})
    assert discover(lan[0], fetch) == [
        portmap.Gateway(WAN, "http://127.0.0.1:5000/ctl")
    ]
    assert sorted(fetch.asked) == [ROUTER, PRINTER]  # each fetched once, no more
    # A LAN of root devices alone: each costs one fetch and none is a router.
    lan.append(Lan({portmap.ROOT_DEVICE: [PRINTER]}))
    fetch = Fetch({PRINTER: TV})
    assert discover(lan[1], fetch) == []
    assert fetch.asked == [PRINTER]


def test_a_root_device_is_not_asked_once_a_router_answered_as_one(
    lan: list[Lan],
) -> None:
    lan.append(Lan({WAN: [ROUTER], portmap.ROOT_DEVICE: [ROUTER, PRINTER]}))
    fetch = Fetch({ROUTER: igd_tree("/ctl"), PRINTER: TV})
    assert discover(lan[0], fetch) == [
        portmap.Gateway(WAN, "http://127.0.0.1:5000/ctl")
    ]
    assert fetch.asked == [ROUTER]


def test_at_most_eight_descriptions_are_fetched_however_many_answer(
    lan: list[Lan],
) -> None:
    many = [f"http://127.0.0.1:{6000 + n}/d.xml" for n in range(20)]
    lan.append(Lan({portmap.ROOT_DEVICE: many, WAN: many[10:]}))
    fetch = Fetch({})
    assert discover(lan[0], fetch) == []
    assert len(fetch.asked) == portmap.MAX_LOCATIONS
    assert len(set(fetch.asked)) == len(fetch.asked)
    assert set(fetch.asked) <= set(many[10:])  # the routers' answers first


def test_each_search_is_sent_again_so_one_lost_datagram_is_no_lost_router(
    lan: list[Lan],
) -> None:
    lan.append(Lan({WAN: [ROUTER]}, lose=portmap.SSDP_SENDS - 1))
    fetch = Fetch({ROUTER: igd_tree("/ctl")})
    assert discover(lan[0], fetch) == [
        portmap.Gateway(WAN, "http://127.0.0.1:5000/ctl")
    ]
    for target in portmap.SEARCH_TARGETS:
        assert lan[0].heard.count(target) == portmap.SSDP_SENDS


def test_discovery_searches_on_each_lan_interface_and_skips_one_that_cannot_send(
    lan: list[Lan],
) -> None:
    lan.append(Lan({WAN: [ROUTER]}))
    fetch = Fetch({ROUTER: igd_tree("/ctl")})
    sock = Ways(dead=("192.168.7.20",))
    # 127.0.0.1 is the way the system sends to the LAN fake by default: it is
    # searched on once as an interface, not again as the default.
    found = discover(lan[0], fetch, ("127.0.0.1", "192.168.7.20"), sock)
    assert found == [portmap.Gateway(WAN, "http://127.0.0.1:5000/ctl")]
    targets = len(portmap.SEARCH_TARGETS) * portmap.SSDP_SENDS
    assert sock.out == ["127.0.0.1"] * targets
    # An interface that is not the default way: both are searched on.
    lan.append(Lan({WAN: [ROUTER]}))
    sock = Ways(invented=("10.9.9.9",))
    discover(lan[1], Fetch({ROUTER: igd_tree("/ctl")}), ("10.9.9.9",), sock)
    assert sorted(set(sock.out)) == ["0.0.0.0", "10.9.9.9"]


def test_discovery_with_no_way_to_send_gives_up_at_once(lan: list[Lan]) -> None:
    lan.append(Lan({WAN: [ROUTER]}))
    sock = Ways(dead=("0.0.0.0", "10.9.9.9"))
    started = time.monotonic()
    assert discover(lan[0], Fetch({}), ("10.9.9.9",), sock) == []
    assert time.monotonic() - started < WAIT_S / 2
    assert lan[0].heard == []


def test_the_best_service_comes_first_whichever_router_answered_first(
    lan: list[Lan],
) -> None:
    ppp = "urn:schemas-upnp-org:service:WANPPPConnection:1"
    best = portmap.WAN_SERVICES[0]
    second = "http://127.0.0.1:5001/rootDesc.xml"
    lan.append(Lan({ppp: [ROUTER], best: [second]}))
    fetch = Fetch(
        {ROUTER: igd_tree("/ppp", kind=ppp), second: igd_tree("/ip2", kind=best)}
    )
    assert discover(lan[0], fetch) == [
        portmap.Gateway(best, "http://127.0.0.1:5001/ip2"),
        portmap.Gateway(ppp, "http://127.0.0.1:5000/ppp"),
    ]


def test_an_answer_no_url_parser_takes_ends_no_discovery(lan: list[Lan]) -> None:
    broken = ["http://[127.0.0.1/x", "http://127.0.0.1:99999/x"]
    lan.append(Lan({WAN: [*broken, ROUTER]}))
    fetch = Fetch({ROUTER: igd_tree("/ctl")})
    assert discover(lan[0], fetch) == [
        portmap.Gateway(WAN, "http://127.0.0.1:5000/ctl")
    ]
    assert fetch.asked == [ROUTER]


def test_discovery_listens_no_longer_than_its_wait(lan: list[Lan]) -> None:
    lan.append(Lan({}))
    started = time.monotonic()
    assert discover(lan[0], Fetch({})) == []
    took = time.monotonic() - started
    assert WAIT_S <= took < 2 * WAIT_S  # the sends add no wait of their own


class Refusing(Ways):
    """A UDP socket whose first read fails as an ICMP error does on some
    systems; the datagram that woke it is still there to read."""

    def __init__(self) -> None:
        super().__init__()
        self.refused = False

    def recvfrom(self, size: int, flags: int = 0) -> tuple[bytes, Any]:
        if not self.refused:
            self.refused = True
            raise OSError(111, "Connection refused")
        return super().recvfrom(size, flags)


def test_a_read_the_socket_refuses_is_skipped(lan: list[Lan]) -> None:
    lan.append(Lan({WAN: [ROUTER]}))
    sock = Refusing()
    found = discover(lan[0], Fetch({ROUTER: igd_tree("/ctl")}), sock=sock)
    assert found == [portmap.Gateway(WAN, "http://127.0.0.1:5000/ctl")]
    assert sock.refused


def test_discovery_searches_on_this_hosts_lan_interfaces_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = (
        ("eth0", ipaddress.IPv4Interface("192.168.1.20/24")),
        ("docker0", ipaddress.IPv4Interface("172.17.0.1/16")),  # its own bridge
    )
    monkeypatch.setattr(tunnel, "read_interfaces", lambda: found)
    assert portmap.lan_interfaces() == ("192.168.1.20",)
    default = inspect.signature(portmap.discover_upnp).parameters["interfaces"]
    assert default.default is portmap.lan_interfaces


def trickling(head: bytes, gap_s: float, for_s: float) -> tuple[int, threading.Event]:
    """A device on 127.0.0.1 that answers one fetch with ``head`` and then one
    byte every ``gap_s``, for ``for_s`` at most or until it is told to stop:
    no single read waits long, the whole answer never ends."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(for_s)
    stop = threading.Event()

    def serve() -> None:
        with server, contextlib.suppress(OSError):
            conn, _ = server.accept()
            with conn:
                conn.recv(2048)
                conn.sendall(head)
                ends = time.monotonic() + for_s
                while not stop.is_set() and time.monotonic() < ends:
                    conn.sendall(b"x")
                    time.sleep(gap_s)

    threading.Thread(target=serve, daemon=True).start()
    return server.getsockname()[1], stop


@pytest.mark.parametrize(
    "head",
    [
        b"HTTP/1.1 200 OK\r\nX-Slow: ",  # in the headers
        b"HTTP/1.1 200 OK\r\nContent-Length: 65537\r\n\r\n<root>",  # in the body
    ],
)
def test_a_fetch_is_over_within_its_wait_however_slowly_a_device_answers(
    monkeypatch: pytest.MonkeyPatch, head: bytes
) -> None:
    # Each byte comes well within the wait, so only a deadline on the whole
    # fetch ends it: a wait per read held it for all 5 s the device trickles.
    monkeypatch.setattr(portmap, "HTTP_WAIT_S", 0.3)
    port, stop = trickling(head, gap_s=0.05, for_s=5.0)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError):  # a failed fetch: an OSError
            portmap._fetch(f"http://127.0.0.1:{port}/rootDesc.xml")
        took = time.monotonic() - started
    finally:
        stop.set()
    assert took < 2.0  # 0.3 s and the host's slack; a wait per read took 5 s


def test_a_description_that_comes_within_its_wait_is_fetched_whole(
    igd: portmap.Upnp,
) -> None:
    location = igd.address()["control"].replace("/ctl", "/rootDesc.xml")
    assert portmap._fetch(location) == igd_tree("/ctl")


# --- UPnP: SOAP ------------------------------------------------------------------


class Igd(BaseHTTPRequestHandler):
    calls: ClassVar[list[tuple[str, bytes]]] = []
    fault: ClassVar[dict[str, int]] = {}
    held: ClassVar[tuple[str, int] | None] = None  # what 52000 forwards to now

    def do_POST(self) -> None:
        action = self.headers["SOAPAction"].strip('"').rpartition("#")[2]
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Igd.calls.append((action, body))
        code = Igd.fault.pop(action, 0)
        if code:
            self._fault(code)
            return
        if False:
            self._send(
                500,
                "<s:Envelope xmlns:s='http://schemas.xmlsoap.org/soap/envelope/'>"
                "<s:Body><s:Fault><detail><UPnPError xmlns='urn:schemas-upnp-org:"
                f"control-1-0'><errorCode>{code}</errorCode><errorDescription>"
                "no</errorDescription></UPnPError></detail></s:Fault></s:Body>"
                "</s:Envelope>",
            )
            return
        inner = ""
        if action == "GetSpecificPortMappingEntry":
            if Igd.held is None:
                code = 714
            else:
                inner = (
                    f"<NewInternalPort>{Igd.held[1]}</NewInternalPort>"
                    f"<NewInternalClient>{Igd.held[0]}</NewInternalClient>"
                )
        if code:
            self._fault(code)
            return
        if action == "GetExternalIPAddress":
            inner = "<NewExternalIPAddress>198.51.100.7</NewExternalIPAddress>"
        self._send(
            200,
            "<s:Envelope xmlns:s='http://schemas.xmlsoap.org/soap/envelope/'>"
            f"<s:Body><u:{action}Response xmlns:u='{WAN}'>{inner}"
            f"</u:{action}Response></s:Body></s:Envelope>",
        )

    def do_GET(self) -> None:
        self._send(200, igd_tree("/ctl").decode())

    def _fault(self, code: int) -> None:
        self._send(
            500,
            "<s:Envelope xmlns:s='http://schemas.xmlsoap.org/soap/envelope/'>"
            "<s:Body><s:Fault><detail><UPnPError xmlns='urn:schemas-upnp-org:"
            f"control-1-0'><errorCode>{code}</errorCode><errorDescription>"
            "no</errorDescription></UPnPError></detail></s:Fault></s:Body>"
            "</s:Envelope>",
        )

    def _send(self, status: int, text: str) -> None:
        raw = text.encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def igd() -> Iterator[portmap.Upnp]:
    Igd.calls = []
    Igd.fault = {}
    Igd.held = None
    server = HTTPServer(("127.0.0.1", 0), Igd)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield portmap.Upnp(
        portmap.Gateway(WAN, f"http://127.0.0.1:{port}/ctl"),
        lan=lambda _: "192.168.1.20",
    )
    server.shutdown()
    server.server_close()


def test_upnp_maps_unmaps_and_reads_the_external_address(igd: portmap.Upnp) -> None:
    assert igd.external_address() == "198.51.100.7"
    assert igd.add(lan_host="192.168.1.20", internal=51820, external=52000, lease_s=600)
    action, body = Igd.calls[-1]
    assert action == "AddPortMapping"
    for part in (
        b"<NewExternalPort>52000</NewExternalPort>",
        b"<NewProtocol>UDP</NewProtocol>",
        b"<NewInternalPort>51820</NewInternalPort>",
        b"<NewInternalClient>192.168.1.20</NewInternalClient>",
        b"<NewLeaseDuration>600</NewLeaseDuration>",
    ):
        assert part in body
    igd.remove(lan_host="192.168.1.20", internal=51820, external=52000)
    assert Igd.calls[-1][0] == "DeletePortMapping"


def test_upnp_reads_a_conflict_and_a_router_that_grants_only_permanent_leases(
    igd: portmap.Upnp,
) -> None:
    Igd.fault["AddPortMapping"] = 718
    with pytest.raises(portmap.MapError) as conflict:
        igd.add(lan_host="192.168.1.20", internal=51820, external=52000, lease_s=600)
    assert conflict.value.error == "conflict"
    # Only permanent leases: refused as such, never taken unasked; the
    # mapper asks for one (lease 0) only when the owner allowed it.
    Igd.fault["AddPortMapping"] = 725
    with pytest.raises(portmap.MapError) as permanent:
        igd.add(lan_host="192.168.1.20", internal=51820, external=52000, lease_s=600)
    assert permanent.value.error == portmap.PERMANENT_ONLY
    adds = [body for action, body in Igd.calls if action == "AddPortMapping"]
    assert not any(b"<NewLeaseDuration>0<" in body for body in adds)
    granted = igd.add(
        lan_host="192.168.1.20", internal=51820, external=52000, lease_s=0
    )
    assert granted == 0
    assert b"<NewLeaseDuration>0</NewLeaseDuration>" in Igd.calls[-1][1]


def test_upnp_says_a_dead_gateway_timed_out() -> None:
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    dead = portmap.Upnp(
        portmap.Gateway(WAN, f"http://127.0.0.1:{port}/ctl"), wait_s=0.2
    )
    with pytest.raises(portmap.MapError) as timed_out:
        dead.external_address()
    assert timed_out.value.error == "timeout"


def test_a_soap_answer_with_a_declaration_is_refused() -> None:
    with pytest.raises(portmap.MapError):
        portmap.read_soap(b'<!DOCTYPE x [<!ENTITY a "a">]><x>&a;</x>')


def test_upnp_never_takes_a_port_that_forwards_to_another_device(
    igd: portmap.Upnp,
) -> None:
    Igd.held = ("192.168.1.77", 3074)  # a console's forward
    with pytest.raises(portmap.MapError) as taken:
        igd.add(lan_host="192.168.1.20", internal=51820, external=52000, lease_s=600)
    assert taken.value.error == "conflict"
    assert "AddPortMapping" not in [action for action, _ in Igd.calls]
    Igd.held = ("192.168.1.20", 51820)  # its own, from before: renewed
    assert igd.add(lan_host="192.168.1.20", internal=51820, external=52000, lease_s=600)


def test_upnp_never_removes_a_port_that_forwards_to_another_device_now(
    igd: portmap.Upnp,
) -> None:
    """Its lease ran out and another device took the port: giving the forward
    back must not take that device's away."""
    Igd.held = ("192.168.1.77", 3074)
    igd.remove(lan_host="192.168.1.20", internal=51820, external=52000)
    assert "DeletePortMapping" not in [action for action, _ in Igd.calls]
    Igd.held = ("192.168.1.20", 51820)
    igd.remove(lan_host="192.168.1.20", internal=51820, external=52000)
    assert Igd.calls[-1][0] == "DeletePortMapping"


def test_a_utf16_description_is_refused_before_it_is_parsed() -> None:
    at = "http://192.168.1.1:5000/rootDesc.xml"
    text = description("/ctl", extra='<!DOCTYPE r [<!ENTITY a "aaaa">]>').decode()
    assert portmap.read_description(text.encode("utf-16"), at) is None
