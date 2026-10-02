"""The rig's UDP packets are the hub's formats, and whatever is not one is dropped.

Binding requests, probe packets and relay binds are spoken outside the
agent's channel, straight off the network, so every byte read is hostile:
each reader takes a datagram of any length and says ``None`` to anything
that is not exactly its format (a short or long packet, another magic, a
version or kind the format does not have, an address of the wrong length, a
port of zero), and nothing is answered that is larger than what asked. Every
bound and magic here is the one the hub's pinned schema states. A binding
request is answered by the responder asked, for a transaction the rig sent;
an answer from anywhere else, or replayed, is not taken.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import pytest

from tests import rig_schema

TOKEN = bytes(range(16))
SECRET = bytes(range(16, 32))
TXID = bytes(range(12))


def test_the_constants_are_the_schemas() -> None:
    from mcgyvr.rig import udpwire as u

    said = rig_schema.load()["x-udp"]
    assert said == {
        "version": u.VERSION,
        "stun_magic": u.STUN_MAGIC.decode(),
        "probe_magic": u.PROBE_MAGIC.decode(),
        "relay_magic": u.RELAY_MAGIC.decode(),
        "stun_request_min_bytes": u.STUN_REQUEST_MIN_BYTES,
        "stun_request_max_bytes": u.STUN_REQUEST_MAX_BYTES,
        "probe_packet_min_bytes": u.PROBE_PACKET_MIN_BYTES,
        "probe_packet_max_bytes": u.PROBE_PACKET_MAX_BYTES,
        "relay_bind_min_bytes": u.RELAY_BIND_MIN_BYTES,
        "relay_bind_max_bytes": u.RELAY_BIND_MAX_BYTES,
        "relay_max_packet_bytes": u.RELAY_MAX_PACKET_BYTES,
    }


def test_a_binding_request_is_its_layout_and_its_bounds() -> None:
    from mcgyvr.rig import udpwire as u

    packet = u.binding_request(TOKEN, TXID)
    assert len(packet) == u.STUN_REQUEST_MIN_BYTES
    assert packet[:8] == b"MCGS\x01\x01\x00\x00"
    assert packet[8:24] == TOKEN and packet[24:36] == TXID
    assert set(packet[36:]) == {0}
    for size in (u.STUN_REQUEST_MIN_BYTES - 1, u.STUN_REQUEST_MAX_BYTES + 1):
        with pytest.raises(ValueError):
            u.binding_request(TOKEN, TXID, size=size)
    with pytest.raises(ValueError):
        u.binding_request(TOKEN[:15], TXID)


def _answer(family: int, txid: bytes, port: int, address: bytes) -> bytes:
    head = b"MCGS\x01\x02" + bytes([family, 0]) + txid
    return head + port.to_bytes(2, "big") + address


def test_a_binding_answer_is_read_and_anything_else_is_not() -> None:
    from mcgyvr.rig import udpwire as u

    v4 = _answer(4, TXID, 40000, bytes([198, 51, 100, 7]))
    read = u.read_binding_answer(v4)
    assert read == u.BindingAnswer(txid=TXID, host="198.51.100.7", port=40000)
    v6 = _answer(6, TXID, 40001, bytes([0x20, 0x01, 0x0D, 0xB8]) + bytes(12))
    assert u.read_binding_answer(v6) == u.BindingAnswer(
        txid=TXID, host="2001:db8::", port=40001
    )
    for hostile in (
        b"",
        v4[:-1],
        v4 + b"\x00",
        b"MCGX" + v4[4:],
        v4[:4] + b"\x02" + v4[5:],
        v4[:5] + b"\x01" + v4[6:],
        _answer(6, TXID, 40000, bytes(4)),
        _answer(4, TXID, 40000, bytes(16)),
        _answer(5, TXID, 40000, bytes(4)),
        _answer(4, TXID, 0, bytes(4)),
        bytes(4096),
    ):
        assert u.read_binding_answer(hostile) is None


def test_a_probe_packet_is_its_layout_and_a_pong_is_the_ping_echoed() -> None:
    from mcgyvr.rig import udpwire as u

    ping = u.probe_packet(u.PING, SECRET, 7, 123456789, size=200)
    assert len(ping) == 200 and ping[:8] == b"MCGP\x01\x01\x00\x00"
    read = u.read_probe(ping)
    assert read == u.Probe(kind=u.PING, secret=SECRET, seq=7, stamp=123456789, size=200)
    answer = u.pong(ping)
    assert answer is not None and len(answer) == len(ping)
    assert u.read_probe(answer) == u.Probe(
        kind=u.PONG, secret=SECRET, seq=7, stamp=123456789, size=200
    )
    assert u.pong(answer) is None  # a pong is never answered
    assert u.pong(u.probe_packet(u.BULK, SECRET, 1, 8)) is None


@pytest.mark.parametrize(
    "hostile",
    [
        b"",
        b"MCGP",
        bytes(35),
        b"MCGP\x01\x01\x00\x00" + SECRET + bytes(12) + bytes(1200 - 36 + 1),
        b"MCGQ\x01\x01\x00\x00" + SECRET + bytes(12),
        b"MCGP\x02\x01\x00\x00" + SECRET + bytes(12),
        b"MCGP\x01\x04\x00\x00" + SECRET + bytes(12),
        b"MCGP\x01\x00\x00\x00" + SECRET + bytes(12),
    ],
)
def test_what_is_not_a_probe_packet_is_none(hostile: bytes) -> None:
    from mcgyvr.rig import udpwire as u

    assert u.read_probe(hostile) is None
    assert u.pong(hostile) is None


def test_a_relay_bind_and_its_answers() -> None:
    from mcgyvr.rig import udpwire as u

    ticket = "T" * 40
    bind = u.relay_bind(ticket)
    assert len(bind) == u.RELAY_BIND_MIN_BYTES
    assert bind[:8] == b"MCGR\x01\x01\x00\x28" and bind[8:48] == ticket.encode()
    assert len(u.relay_bind("T" * 256)) >= 8 + 256
    for bad in ("short", "T" * 257, "T" * 30 + " ;", "T" * 30 + "\n"):
        with pytest.raises(ValueError):
            u.relay_bind(bad)
    assert u.read_relay_answer(b"MCGR\x01\x02\x9c\x41") == 40001
    assert u.read_relay_answer(b"MCGR\x01\x03\x02") == u.RelayRefused(reason=2)
    for hostile in (
        b"",
        b"MCGR\x01\x02\x00\x00",
        b"MCGR\x01\x02\x9c\x41\x00",
        b"MCGR\x02\x02\x9c\x41",
        b"MCGX\x01\x02\x9c\x41",
        b"MCGR\x01\x01\x9c\x41",
        b"MCGR\x01\x04\x02",
        bytes(2048),
    ):
        assert u.read_relay_answer(hostile) is None


@pytest.fixture
def responder() -> Iterator[tuple[tuple[str, int], list[bytes], list[str]]]:
    """A binding responder on loopback: answers each request with its source,
    after whatever the test scripted first (``extra``)."""
    from mcgyvr.rig import udpwire as u

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(0.05)
    seen: list[bytes] = []
    script: list[str] = []
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                data, source = sock.recvfrom(4096)
            except TimeoutError:
                continue
            seen.append(data)
            txid = data[24:36]
            host = bytes(int(part) for part in source[0].split("."))
            good = _answer(4, txid, source[1], host)
            if "forged-txid" in script:
                sock.sendto(_answer(4, bytes(12), 1, host), source)
            if "silent" in script:
                continue
            assert len(good) <= len(data) and len(data) >= u.STUN_REQUEST_MIN_BYTES
            sock.sendto(good, source)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield sock.getsockname(), seen, script
    stop.set()
    thread.join()
    sock.close()


def test_a_rig_asks_its_bindings_from_its_own_port_and_takes_only_true_answers(
    responder: tuple[tuple[str, int], list[bytes], list[str]],
) -> None:
    from mcgyvr.rig import udpwire as u

    server, seen, script = responder
    script.append("forged-txid")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        intruder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        intruder.sendto(_answer(4, TXID, 9, bytes(4)), sock.getsockname())
        found = u.ask_bindings(sock, TOKEN, [server], attempts=2, wait_s=1.0)
        intruder.close()
        assert list(found) == [server]
        rtt_us, answer = found[server]
        assert 0 < rtt_us < 1_000_000
        assert (answer.host, answer.port) == sock.getsockname()
    assert seen and all(packet[8:24] == TOKEN for packet in seen)


def test_a_responder_that_never_answers_is_no_answer_in_bounded_time(
    responder: tuple[tuple[str, int], list[bytes], list[str]],
) -> None:
    from mcgyvr.rig import udpwire as u

    server, seen, script = responder
    script.append("silent")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        assert u.ask_bindings(sock, TOKEN, [server], attempts=3, wait_s=0.05) == {}
    assert len(seen) == 3


def test_the_container_helper_runs_as_a_script_and_prints_round_trips(
    responder: tuple[tuple[str, int], list[bytes], list[str]],
) -> None:
    import subprocess
    import sys
    from pathlib import Path

    from mcgyvr.rig import udpwire as u

    server, _, _ = responder
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    source = Path(u.__file__).read_text(encoding="utf-8")
    said = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            source,
            "stun",
            str(port),
            TOKEN.hex(),
            "2",
            "500",
            server[0],
            str(server[1]),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.split()
    assert said[:3] == ["rtt", server[0], str(server[1])] and int(said[3]) > 0


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        (["bound"], 40001),
        (["refused"], "refused"),
        (["foreign", "bound"], 40001),
        (["silent"], None),
        (["garbage", "bound"], 40001),
    ],
)
def test_a_relay_bind_takes_only_the_relays_own_answer(
    script: list[str], expected: object
) -> None:
    from mcgyvr.rig import udpwire as u

    relay = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    relay.bind(("127.0.0.1", 0))
    relay.settimeout(2.0)
    foreign = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    foreign.bind(("127.0.0.2", 0))
    got: list[bytes] = []

    def serve() -> None:
        try:
            data, source = relay.recvfrom(4096)
        except TimeoutError:
            return
        got.append(data)
        for step in script:
            if step == "bound":
                relay.sendto(b"MCGR\x01\x02\x9c\x41", source)
            elif step == "refused":
                relay.sendto(b"MCGR\x01\x03\x01", source)
            elif step == "foreign":
                foreign.sendto(b"MCGR\x01\x02\x00\x07", source)
            elif step == "garbage":
                relay.sendto(bytes(4096), source)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    host, port = relay.getsockname()
    answer = u.bind_relay(host, port, "T" * 30, attempts=1, wait_s=0.5)
    thread.join()
    relay.close()
    foreign.close()
    if expected == "refused":
        assert answer == u.RelayRefused(reason=1)
    else:
        assert answer == expected
    assert got and u.TICKET.fullmatch(got[0][8:38].decode())
    assert len(got[0]) >= u.RELAY_BIND_MIN_BYTES
