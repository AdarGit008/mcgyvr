"""A probe measures only the peers the hub named, and answers only them.

Before any session the hub asks two rigs how well they reach each other.
Each opens one UDP socket, asks the hub's responder from it (so the hub sees
the socket's public address), and says which LAN endpoints it has; then
each pings every candidate the hub named for its peer, answers its peer's
pings, sends its peer a bulk train, and reports reached or not, the
candidate, the median and least round trip, the loss and the train's rate.

Everything that comes off the socket is hostile. A ping is answered only
when it carries the secret of a peer of the running probe and comes from an
address the hub named for that peer — never for anyone else, never larger
than the ping, and only so many times per peer; a pong counts once, for a
ping this rig sent, so a replay measures nothing. A rig pings no address a
peer cannot be at (loopback, multicast and the like) unless told it may, and
its socket closes when the probe's time is up or the agent ends.

These run on real sockets on this machine's loopback, with the address rule
opened to loopback for the rigs under test and kept for the rule's own test.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from tests import rig_schema
from tests.rig_pool_fakes import LAN_ADDRESS

TOKEN = "00112233445566778899aabbccddeeff"
SECRET = "ffeeddccbbaa99887766554433221100"


class Box:
    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def put(self, frame: str, timeout: float | None = None) -> bool:
        message = json.loads(frame)
        rig_schema.validate(message, rig_schema.load(), "#/$defs/AgentMessage")
        with self.lock:
            self.frames.append(message)
        return True

    def wait(self, kind: str, timeout: float = 5.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                found = [f for f in self.frames if f["type"] == kind]
            if found:
                return found[-1]
            time.sleep(0.01)
        raise AssertionError(f"no {kind} in {self.frames}")


@dataclass
class Responder:
    sock: socket.socket
    seen: list[tuple[bytes, tuple[str, int]]] = field(default_factory=list)
    stop: threading.Event = field(default_factory=threading.Event)

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.sock.getsockname()
        return str(host), int(port)

    def serve(self) -> None:
        while not self.stop.is_set():
            try:
                data, source = self.sock.recvfrom(4096)
            except TimeoutError:
                continue
            self.seen.append((data, source))
            host = bytes(int(part) for part in source[0].split("."))
            answer = (
                b"MCGS\x01\x02\x04\x00" + data[24:36] + source[1].to_bytes(2, "big")
            )
            self.sock.sendto(answer + host, source)


@pytest.fixture
def responder() -> Iterator[Responder]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.05)
    made = Responder(sock)
    thread = threading.Thread(target=made.serve, daemon=True)
    thread.start()
    yield made
    made.stop.set()
    thread.join()
    sock.close()


def _rig(box: Box, **changes: Any) -> Any:
    from mcgyvr.rig import probe

    settings: dict[str, Any] = {
        "send": box.put,
        "port": lambda: None,
        "hosts": lambda: (LAN_ADDRESS,),
        "allowed": lambda address: True,
        "bind_host": "127.0.0.1",
    }
    settings.update(changes)
    return probe.Probes(**settings)


def _frame(kind: str, message_id: str, **body: Any) -> Any:
    from mcgyvr.rig import protocol

    return protocol.decode(
        json.dumps({"v": 1, "type": kind, "id": message_id, "body": body})
    )


def _open(rig: Any, box: Box, responder: Responder, probe_id: str = "pr1") -> int:
    host, port = responder.address
    stun = [{"host": host, "port": port, "kind": "stun"}]
    assert (
        rig.open(_frame("probe_open", "o1", probe_id=probe_id, token=TOKEN, stun=stun))
        is None
    )
    opened = box.wait("probe_opened")
    assert opened["re"] == "o1"
    endpoints = opened["body"]["endpoints"]
    assert {e["host"] for e in endpoints} == {LAN_ADDRESS}
    return int(endpoints[0]["port"])


def _run(rig: Any, peer_port: int, **changes: Any) -> None:
    body: dict[str, Any] = {
        "probe_id": "pr1",
        "peers": [
            {
                "rig_id": "rig-peer",
                "secret": SECRET,
                "endpoints": [{"host": "127.0.0.1", "port": peer_port, "kind": "lan"}],
            }
        ],
        "count": 5,
        "interval_ms": 10,
        "deadline_ms": 1500,
    }
    body.update(changes)
    assert rig.run(_frame("probe_run", "r1", **body)) is None


def test_a_probe_asks_the_hubs_responder_from_its_own_socket(
    responder: Responder,
) -> None:
    box = Box()
    rig = _rig(box)
    port = _open(rig, box, responder)
    opened = box.wait("probe_opened")["body"]
    assert 0 < opened["stun_rtt_us"] < 1_000_000
    assert responder.seen and all(
        data[8:24].hex() == TOKEN for data, _ in responder.seen
    )
    assert {source[1] for _, source in responder.seen} == {port}
    rig.close()


def test_two_rigs_measure_each_other_and_report_the_path(responder: Responder) -> None:
    box_a, box_b = Box(), Box()
    a, b = _rig(box_a), _rig(box_b)
    port_a, port_b = _open(a, box_a, responder), _open(b, box_b, responder)
    _run(a, port_b, bulk_bytes=64 * 1024)
    _run(b, port_a, bulk_bytes=64 * 1024)
    for box, port in ((box_a, port_b), (box_b, port_a)):
        result = box.wait("probe_result")
        assert result["re"] == "r1"
        (found,) = result["body"]["results"]
        assert found["rig_id"] == "rig-peer" and found["reached"] is True
        assert found["endpoint"] == {"host": "127.0.0.1", "port": port, "kind": "lan"}
        assert 0 <= found["rtt_min_us"] <= found["rtt_us"] < 500_000
        assert found["loss_pct"] == 0
        assert found["rate_kbps"] >= 1
    a.close()
    b.close()


def _peer_socket(host: str = "127.0.0.1") -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, 0))
    sock.settimeout(0.3)
    return sock


def _received(sock: socket.socket) -> list[bytes]:
    got = []
    while True:
        try:
            got.append(sock.recvfrom(4096)[0])
        except TimeoutError:
            return got


def test_a_ping_is_answered_only_for_a_named_peer_from_a_named_address(
    responder: Responder,
) -> None:
    from mcgyvr.rig import probe, udpwire

    box = Box()
    rig = _rig(box)
    port = _open(rig, box, responder)
    peer, intruder = _peer_socket(), _peer_socket("127.0.0.2")
    _run(rig, peer.getsockname()[1], deadline_ms=3000)
    secret = bytes.fromhex(SECRET)
    ping = udpwire.probe_packet(udpwire.PING, secret, 1, 99, size=200)
    intruder.sendto(ping, ("127.0.0.1", port))  # the secret, the wrong address
    peer.sendto(
        udpwire.probe_packet(udpwire.PING, bytes(16), 1, 99), ("127.0.0.1", port)
    )  # the address, the wrong secret
    peer.sendto(ping + bytes(1200), ("127.0.0.1", port))  # oversized
    peer.sendto(b"MCGP\x01\x01", ("127.0.0.1", port))  # short
    assert _received(intruder) == []
    answers = [a for a in _received(peer) if udpwire.read_probe(a).kind == udpwire.PONG]  # type: ignore[union-attr]
    assert answers == []
    for seq in range(probe.MAX_PONGS_PER_PEER + 50):
        peer.sendto(
            udpwire.probe_packet(udpwire.PING, secret, seq, 7), ("127.0.0.1", port)
        )
    pongs = [
        a
        for a in _received(peer)
        if (read := udpwire.read_probe(a)) is not None and read.kind == udpwire.PONG
    ]
    assert 0 < len(pongs) <= probe.MAX_PONGS_PER_PEER
    assert all(len(p) == udpwire.PROBE_PACKET_MIN_BYTES for p in pongs)
    rig.close()
    peer.close()
    intruder.close()


def test_a_replayed_pong_measures_nothing(responder: Responder) -> None:
    from mcgyvr.rig import udpwire

    box = Box()
    rig = _rig(box)
    port = _open(rig, box, responder)
    peer = _peer_socket()
    _run(rig, peer.getsockname()[1], deadline_ms=800)
    first = None
    deadline = time.monotonic() + 3
    while first is None and time.monotonic() < deadline:
        data, _ = peer.recvfrom(4096)
        read = udpwire.read_probe(data)
        if read is not None and read.kind == udpwire.PING:
            first = data
    assert first is not None
    answer = udpwire.pong(first)
    assert answer is not None
    for _ in range(5):
        peer.sendto(answer, ("127.0.0.1", port))
    forged = answer[:28] + bytes(8)  # the stamp changed
    peer.sendto(forged, ("127.0.0.1", port))
    (found,) = box.wait("probe_result")["body"]["results"]
    assert found["reached"] is True
    assert found["loss_pct"] == 80  # one of five pings answered, however often
    rig.close()
    peer.close()


def _at(*parts: int) -> ipaddress.IPv4Address:
    return ipaddress.IPv4Address(bytes(parts))


def test_the_address_rule_keeps_a_probe_off_what_no_peer_can_be() -> None:
    from mcgyvr.rig import probe

    never = [
        _at(127, 0, 0, 1),  # loopback
        _at(169, 254, 1, 1),  # link-local
        _at(224, 0, 0, 1),  # multicast
        _at(0, 0, 0, 0),  # unspecified
        _at(255, 255, 255, 255),  # the limited broadcast
        _at(240, 0, 0, 1),  # reserved
    ]
    for address in never:
        assert not probe.reachable(address), address
    for address in (_at(192, 0, 2, 10), _at(10, 1, 2, 3), _at(100, 64, 0, 1)):
        assert probe.reachable(address), address


def test_a_rig_under_the_address_rule_pings_no_loopback_peer(
    responder: Responder,
) -> None:
    from mcgyvr.rig import probe

    box = Box()
    rig = _rig(box, allowed=probe.reachable)
    _open(rig, box, responder)
    opened = box.wait("probe_opened")["body"]
    assert "stun_rtt_us" not in opened  # the responder is on loopback: not asked
    peer = _peer_socket()
    _run(rig, peer.getsockname()[1], deadline_ms=300)
    (found,) = box.wait("probe_result")["body"]["results"]
    assert found == {"rig_id": "rig-peer", "reached": False}
    assert _received(peer) == []
    rig.close()
    peer.close()


def test_a_probe_command_out_of_turn_is_refused_by_name(responder: Responder) -> None:
    from mcgyvr.rig import probe

    box = Box()
    rig = _rig(box)
    early = rig.run(
        _frame(
            "probe_run",
            "r0",
            probe_id="nobody",
            peers=[
                {
                    "rig_id": "p",
                    "secret": SECRET,
                    "endpoints": [{"host": LAN_ADDRESS, "port": 1, "kind": "lan"}],
                }
            ],
        )
    )
    assert json.loads(early)["body"]["code"] == "not_ready"
    _open(rig, box, responder)
    _run(rig, 9, deadline_ms=200)
    again = rig.run(
        _frame(
            "probe_run",
            "r2",
            probe_id="pr1",
            peers=[
                {
                    "rig_id": "p",
                    "secret": SECRET,
                    "endpoints": [{"host": LAN_ADDRESS, "port": 1, "kind": "lan"}],
                }
            ],
        )
    )
    assert json.loads(again)["body"]["code"] == "duplicate"
    for n in range(probe.MAX_OPEN - 1):
        assert (
            rig.open(_frame("probe_open", f"o{n + 5}", probe_id=f"x{n}", token=TOKEN))
            is None
        )
    busy = rig.open(_frame("probe_open", "o99", probe_id="one-too-many", token=TOKEN))
    assert json.loads(busy)["body"]["code"] == "busy"
    from mcgyvr.rig import protocol

    with pytest.raises(protocol.ProtocolError) as refused:
        rig.open(_frame("probe_open", "o100", probe_id="bad", token="NOT-HEX"))
    assert "body.token" in refused.value.message
    rig.close()


def test_a_probe_socket_closes_when_its_time_is_up_or_the_agent_ends(
    responder: Responder,
) -> None:
    now = [1000.0]
    box = Box()
    rig = _rig(box, clock=lambda: now[0])
    _open(rig, box, responder)
    assert rig.open_count() == 1
    now[0] += 31  # the default time to live is 30 s
    deadline = time.monotonic() + 3
    while rig.open_count() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert rig.open_count() == 0
    box = Box()
    other = _rig(box)
    _open(other, box, responder)
    assert other.open_count() == 1
    other.close()
    deadline = time.monotonic() + 3
    while other.open_count() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert other.open_count() == 0
