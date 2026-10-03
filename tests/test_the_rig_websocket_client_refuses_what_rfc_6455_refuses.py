"""The rig agent's websocket client speaks RFC 6455 and refuses what it refuses.

The client is the standard library's sockets and nothing else. Its handshake
carries the bearer token and asks for no extension; a server's answer that is
not a correct switch is refused, as is one that grows past a bound or never
comes. Every frame the client sends is masked. A message arrives whole even in
fragments and across reads that time out, a ping is answered with its own
payload, and a close carries the server's code and reason. A server frame the
RFC forbids (masked, reserved bits, unknown opcode, an oversized or split
control frame, a stray continuation, text that is not UTF-8, a length past the
client's bound) closes the channel with the RFC's code, and an oversized
length is refused before its payload is read.
"""

from __future__ import annotations

import contextlib
import socket
import ssl
import struct
import time
from typing import Any

import pytest

from tests.rig_fake_hub import (
    BINARY,
    CLOSE,
    CONTINUATION,
    PING,
    PONG,
    TEXT,
    Peer,
    Server,
)

TOKEN = "mhr_example_token"


def _connect(server: Server, **kwargs: Any) -> Any:
    from mcgyvr.rig import websocket

    options: dict[str, Any] = {
        "headers": {"Authorization": f"Bearer {TOKEN}"},
        "timeout": 5.0,
        "max_message": 1024,
    }
    options.update(kwargs)
    return websocket.connect(server.url, **options)


def test_the_handshake_carries_the_token_and_asks_for_no_extension() -> None:
    def script(peer: Peer) -> None:
        peer.handshake()
        peer.send_text("hi")
        peer.recv_frame()

    with Server(script) as server:
        ws = _connect(server)
        assert ws.receive(timeout=5) == "hi"
        ws.close()
    assert not server.failures, server.failures
    peer = server.peers[0]
    assert peer.request == "GET /api/v1/agent HTTP/1.1"
    assert peer.headers["authorization"] == f"Bearer {TOKEN}"
    assert peer.headers["upgrade"].lower() == "websocket"
    assert "upgrade" in peer.headers["connection"].lower()
    assert peer.headers["sec-websocket-version"] == "13"
    assert peer.headers["host"] == f"127.0.0.1:{server.port}"
    assert "sec-websocket-extensions" not in peer.headers
    assert "sec-websocket-protocol" not in peer.headers


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        (lambda p: p.handshake(status="403 Forbidden"), 403),
        (lambda p: p.handshake(status="401 Unauthorized"), 401),
        (lambda p: p.handshake(status="503 Service Unavailable"), 503),
        (lambda p: p.handshake(accept="d3Jvbmc="), 101),
        (
            lambda p: p.handshake(
                extra="Sec-WebSocket-Extensions: permessage-deflate\r\n"
            ),
            101,
        ),
        (lambda p: p.handshake(extra="Sec-WebSocket-Protocol: other\r\n"), 101),
        (lambda p: (p.read_request(), p.send_raw(b"SSH-2.0-not-http\r\n\r\n")), None),
        (
            lambda p: (
                p.read_request(),
                p.send_raw(b"HTTP/1.1 101 OK\r\n" + b"X: " + b"y" * 20000),
            ),
            None,
        ),
    ],
)
def test_an_answer_that_is_not_a_correct_switch_is_refused(
    answer: Any, status: int | None
) -> None:
    from mcgyvr.rig import websocket

    with Server(answer) as server, pytest.raises(websocket.HandshakeError) as refused:
        _connect(server)
    assert refused.value.status == status


def test_a_server_that_never_answers_is_given_up_on() -> None:
    from mcgyvr.rig import websocket

    def script(peer: Peer) -> None:
        peer.read_request()
        time.sleep(1.0)

    with Server(script) as server:
        started = time.monotonic()
        with pytest.raises(websocket.HandshakeError):
            _connect(server, timeout=0.3)
        assert time.monotonic() - started < 0.9


def test_every_client_frame_is_masked_and_a_ping_gets_its_payload_back() -> None:
    seen: list[Any] = []

    def script(peer: Peer) -> None:
        peer.handshake()
        seen.append(peer.recv_frame())
        peer.send_frame(PING, b"are you there")
        peer.send_text("after the ping")
        seen.append(peer.recv_frame())
        seen.append(peer.recv_frame())

    with Server(script) as server:
        ws = _connect(server)
        ws.send_text('{"v": 1}')
        assert ws.receive(timeout=5) == "after the ping"
        ws.close()
    assert not server.failures, server.failures
    sent, pong, close = seen
    assert sent.masked and sent.opcode == TEXT and sent.payload == b'{"v": 1}'
    assert pong.masked and pong.opcode == PONG and pong.payload == b"are you there"
    assert close.masked and close.opcode == CLOSE
    assert struct.unpack("!H", close.payload[:2])[0] == 1000


def test_a_fragmented_message_arrives_whole_with_a_ping_between() -> None:
    def script(peer: Peer) -> None:
        peer.handshake()
        peer.send_frame(TEXT, b"caf", fin=False)
        peer.send_frame(PING, b"p")
        peer.send_frame(CONTINUATION, "é ".encode(), fin=False)
        peer.send_frame(CONTINUATION, b"au lait", fin=True)
        peer.send_frame(BINARY, b"\x00\x01")
        assert peer.recv_frame().opcode == PONG
        peer.recv_frame()

    with Server(script) as server:
        ws = _connect(server)
        assert ws.receive(timeout=5) == "café au lait"
        assert ws.receive(timeout=5) == b"\x00\x01"
        ws.close()
    assert not server.failures, server.failures


def test_a_frame_split_across_a_timeout_is_not_lost() -> None:
    def script(peer: Peer) -> None:
        peer.handshake()
        frame = struct.pack("!BB", 0x81, 5) + b"hello"
        peer.send_raw(frame[:3])
        time.sleep(0.3)
        peer.send_raw(frame[3:])
        peer.recv_frame()

    with Server(script) as server:
        ws = _connect(server)
        assert ws.receive(timeout=0.05) is None
        deadline = time.monotonic() + 5
        message = None
        while message is None and time.monotonic() < deadline:
            message = ws.receive(timeout=0.05)
        assert message == "hello"
        ws.close()
    assert not server.failures, server.failures


def test_a_close_carries_the_servers_code_and_reason_and_is_answered() -> None:
    from mcgyvr.rig import websocket

    answered: list[Any] = []

    def script(peer: Peer) -> None:
        peer.handshake()
        peer.send_close(4001, "revoked")
        answered.append(peer.recv_frame())

    with Server(script) as server:
        ws = _connect(server)
        with pytest.raises(websocket.ClosedError) as closed:
            ws.receive(timeout=5)
        time.sleep(0.1)
    assert (closed.value.code, closed.value.reason) == (4001, "revoked")
    assert closed.value.by_peer
    assert answered and answered[0].opcode == CLOSE
    assert struct.unpack("!H", answered[0].payload[:2])[0] == 4001


def test_a_dropped_connection_is_an_abnormal_close() -> None:
    from mcgyvr.rig import websocket

    def script(peer: Peer) -> None:
        peer.handshake()

    with Server(script) as server:
        ws = _connect(server)
        with pytest.raises(websocket.ClosedError) as closed:
            ws.receive(timeout=5)
    assert closed.value.code == 1006


def _hostile(*frames: Any) -> Any:
    def script(peer: Peer) -> None:
        peer.handshake()
        for frame in frames:
            frame(peer)
        with contextlib.suppress(ConnectionError, OSError):
            peer.recv_frame()

    return script


HOSTILE = {
    "masked": (_hostile(lambda p: p.send_frame(TEXT, b"x", mask=True)), 1002),
    "reserved bits": (_hostile(lambda p: p.send_frame(TEXT, b"x", rsv=4)), 1002),
    "unknown opcode": (_hostile(lambda p: p.send_frame(3, b"x")), 1002),
    "long ping": (_hostile(lambda p: p.send_frame(PING, b"x" * 126)), 1002),
    "split ping": (_hostile(lambda p: p.send_frame(PING, b"x", fin=False)), 1002),
    "stray continuation": (_hostile(lambda p: p.send_frame(CONTINUATION, b"x")), 1002),
    "new message mid-fragment": (
        _hostile(
            lambda p: p.send_frame(TEXT, b"a", fin=False),
            lambda p: p.send_frame(TEXT, b"b"),
        ),
        1002,
    ),
    "not utf-8": (_hostile(lambda p: p.send_frame(TEXT, b"\xff\xfe")), 1007),
    "split not utf-8": (
        _hostile(
            lambda p: p.send_frame(TEXT, b"\xc3", fin=False),
            lambda p: p.send_frame(CONTINUATION, b"(", fin=True),
        ),
        1007,
    ),
    "length past the bound": (
        _hostile(lambda p: p.send_raw(struct.pack("!BBH", 0x81, 126, 2000))),
        1009,
    ),
    "huge length": (
        _hostile(lambda p: p.send_raw(struct.pack("!BBQ", 0x81, 127, 1 << 62))),
        1009,
    ),
    "length with the top bit": (
        _hostile(lambda p: p.send_raw(struct.pack("!BBQ", 0x81, 127, 1 << 63))),
        1002,
    ),
    "fragments past the bound": (
        _hostile(
            lambda p: p.send_frame(TEXT, b"a" * 600, fin=False),
            lambda p: p.send_frame(CONTINUATION, b"a" * 600, fin=True),
        ),
        1009,
    ),
    "close of one byte": (_hostile(lambda p: p.send_frame(CLOSE, b"\x03")), 1002),
    "close with a code no one sends": (
        _hostile(lambda p: p.send_frame(CLOSE, struct.pack("!H", 1005))),
        1002,
    ),
    "close reason not utf-8": (
        _hostile(lambda p: p.send_frame(CLOSE, struct.pack("!H", 1000) + b"\xff")),
        1007,
    ),
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_a_frame_the_rfc_forbids_closes_the_channel_with_its_code(name: str) -> None:
    from mcgyvr.rig import websocket

    script, code = HOSTILE[name]
    with Server(script) as server:
        ws = _connect(server)
        with pytest.raises(websocket.ClosedError) as closed:
            ws.receive(timeout=5)
        time.sleep(0.05)
    assert closed.value.code == code
    assert not closed.value.by_peer
    with pytest.raises(websocket.ClosedError):
        ws.send_text("after the close")


def test_the_client_will_not_send_a_message_past_its_bound() -> None:
    def script(peer: Peer) -> None:
        peer.handshake()
        peer.recv_frame()

    with Server(script) as server:
        ws = _connect(server)
        with pytest.raises(ValueError):
            ws.send_text("x" * 1025)
        ws.close()


@pytest.mark.parametrize(
    ("url", "target"),
    [
        (
            "ws://127.0.0.1:8765/api/v1/agent",
            (False, "127.0.0.1", 8765, "/api/v1/agent"),
        ),
        (
            "wss://hub.example.com/api/v1/agent",
            (True, "hub.example.com", 443, "/api/v1/agent"),
        ),
        ("ws://localhost/x?y=1", (False, "localhost", 80, "/x?y=1")),
        ("ws://[::1]:9000/", (False, "::1", 9000, "/")),
        ("WSS://HUB.EXAMPLE.COM", (True, "hub.example.com", 443, "/")),
    ],
)
def test_a_websocket_url_names_its_target(url: str, target: tuple[Any, ...]) -> None:
    from mcgyvr.rig import websocket

    parsed = websocket.parse_url(url)
    assert (parsed.secure, parsed.host, parsed.port, parsed.path) == target


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "ws://user:pw@127.0.0.1/",
        "ws:///nohost",
        "ws://127.0.0.1:0/",
        "ws://127.0.0.1:70000/",
        "ws://127.0.0.1/a#frag",
        "ws://127.0.0.1/a b",
        "ws://127.0.0.1/\r\nX: y",
    ],
)
def test_a_url_that_is_not_a_plain_websocket_address_is_refused(url: str) -> None:
    from mcgyvr.rig import websocket

    with pytest.raises(ValueError):
        websocket.parse_url(url)


def test_a_header_that_would_break_the_request_is_refused() -> None:
    from mcgyvr.rig import websocket

    with pytest.raises(ValueError):
        websocket.connect(
            "ws://127.0.0.1:9/",
            headers={"Authorization": "Bearer x\r\nX-Evil: 1"},
            timeout=1.0,
            max_message=1024,
        )


def test_a_secure_url_is_wrapped_in_tls_for_its_host() -> None:
    from mcgyvr.rig import websocket

    wrapped: list[Any] = []

    class Refusing(ssl.SSLContext):
        def wrap_socket(self, sock: socket.socket, **kwargs: Any) -> Any:  # type: ignore[override]
            wrapped.append(kwargs.get("server_hostname"))
            raise ssl.SSLError("refused by the test")

    def script(peer: Peer) -> None:
        with contextlib.suppress(ConnectionError, OSError):
            peer.read_request()

    with Server(script) as server:
        url = f"wss://localhost:{server.port}/api/v1/agent"
        with pytest.raises(websocket.HandshakeError):
            websocket.connect(
                url,
                headers={},
                timeout=2.0,
                max_message=1024,
                ssl_context=Refusing(ssl.PROTOCOL_TLS_CLIENT),
            )
    assert wrapped == ["localhost"]


def test_the_default_tls_context_checks_the_certificate_and_the_name() -> None:
    from mcgyvr.rig import websocket

    context = websocket.default_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
