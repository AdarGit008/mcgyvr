"""The router clients speak NAT-PMP and UPnP IGD, and trust no answer blindly.

NAT-PMP maps, unmaps and reads the external address against a gateway on a
local UDP port, and refuses an answer for another port, a refusal and a
different external port (a conflict, undone). UPnP keeps a discovery answer
only when its URL is plain HTTP on the private address that answered, reads
a description only without a document type or entity and with its control
URL on the same host, and maps, unmaps and reads the address by SOAP against
a local HTTP server, a conflict and a permanent-only lease read by code.
"""

from __future__ import annotations

import socket
import struct
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from mcgyvr.rig import portmap

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
    client.remove(internal=51820, external=52000)
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
    assert portmap.read_ssdp(ssdp(url), "192.168.1.1") == url
    assert portmap.read_ssdp(ssdp(url), "192.168.1.9") is None
    public = "http://8.8.8.8/desc.xml"
    assert portmap.read_ssdp(ssdp(public), "8.8.8.8") is None
    assert portmap.read_ssdp(ssdp("https://192.168.1.1/x"), "192.168.1.1") is None
    assert portmap.read_ssdp(ssdp(url, st="upnp:rootdevice"), "192.168.1.1") is None
    assert portmap.read_ssdp(b"NOTIFY * HTTP/1.1\r\n\r\n", "192.168.1.1") is None


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
    igd.remove(internal=51820, external=52000)
    assert Igd.calls[-1][0] == "DeletePortMapping"


def test_upnp_reads_a_conflict_and_falls_back_to_a_permanent_lease(
    igd: portmap.Upnp,
) -> None:
    Igd.fault["AddPortMapping"] = 718
    with pytest.raises(portmap.MapError) as conflict:
        igd.add(lan_host="192.168.1.20", internal=51820, external=52000, lease_s=600)
    assert conflict.value.error == "conflict"
    Igd.fault["AddPortMapping"] = 725
    granted = igd.add(
        lan_host="192.168.1.20", internal=51820, external=52000, lease_s=600
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


def test_a_utf16_description_is_refused_before_it_is_parsed() -> None:
    at = "http://192.168.1.1:5000/rootDesc.xml"
    text = description("/ctl", extra='<!DOCTYPE r [<!ENTITY a "aaaa">]>').decode()
    assert portmap.read_description(text.encode("utf-16"), at) is None
