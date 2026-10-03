"""A relayed request reaches only the head's loopback API and streams back in credit.

The hub relays one OpenAI-compatible request to the head a session runs on
this rig. The agent takes the request body from the hub's ``relay_data``
frames, in order and no more than announced, and sends it to one fixed path
of the head's API on loopback — never a path, a host or a port the hub
names. The answer goes back as ``relay_response``, then ``relay_data``
frames of at most the protocol's chunk, never more uncredited than the
hub's window (the agent stops reading the head while out of credit), then
exactly one ``relay_end``: ``complete``, ``cancelled`` on the hub's word,
``timeout`` and ``too_large`` at the hub's limits, ``error`` with the hub's
code for a session that is not there or not ready, a request id used before,
a body that runs over or out of order, or a head that fails. The prompt is
never printed, and never put in a message the agent writes.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes

PROMPT = "the secret prompt words"


@dataclass
class Head:
    """A model server's API on this machine's loopback, scripted."""

    chunks: list[bytes] = field(default_factory=lambda: [b'{"ok": true}'])
    pause_s: float = 0.0
    status: int = 200
    content_type: str = "application/json; charset=utf-8"
    seen: list[tuple[str, str, bytes, dict[str, str]]] = field(default_factory=list)
    hung_up: threading.Event = field(default_factory=threading.Event)
    server: ThreadingHTTPServer | None = None

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.server_address[1])


def _serve(head: Head) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            head.seen.append(
                (
                    self.command,
                    self.path,
                    body,
                    {k.lower(): v for k, v in self.headers.items()},
                )
            )
            self.send_response(head.status)
            self.send_header("Content-Type", head.content_type)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                for chunk in head.chunks:
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.flush()
                    time.sleep(head.pause_s)
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                head.hung_up.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Heads:
    def __init__(
        self, port: int | None, state: str = "ready", role: str = "head"
    ) -> None:
        self.port = port
        self.state = state
        self.role = role

    def head_port(self, session_id: str) -> int | None:
        if session_id == "s1" and self.state == "ready" and self.role == "head":
            return self.port
        return None

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        return (self.state, self.role) if session_id == "s1" else ("absent", None)


@dataclass
class Relay:
    head: Head
    heads: Heads
    box: fakes.Box
    relays: Any
    dispatcher: Any

    def send(
        self, kind: str, message_id: str = "r1", **body: Any
    ) -> dict[str, Any] | None:
        reply = self.dispatcher.dispatch(
            fakes.frame(kind, message_id, **body), fakes.Stub()
        )
        if reply is None:
            return None
        self.box.put(reply)  # the agent sends a handler's answer on the channel
        answer: dict[str, Any] = json.loads(reply)
        return answer

    def request(self, body: bytes, **changes: Any) -> None:
        fields: dict[str, Any] = {
            "session_id": "s1",
            "request_id": "q1",
            "endpoint": "chat_completions",
            "body_bytes": len(body),
            "stream": False,
            "timeout_s": 5,
            "max_response_bytes": 1 << 20,
            "window": 8,
        }
        fields.update(changes)
        self.send("relay_request", "r1", **fields)
        half = len(body) // 2
        for seq, part in enumerate((body[:half], body[half:])):
            if part:
                self.send(
                    "relay_data",
                    f"d{seq}",
                    request_id=fields["request_id"],
                    seq=seq,
                    data_b64=base64.b64encode(part).decode(),
                )

    def ended(self, request_id: str = "q1", timeout: float = 5.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ends = [
                f
                for f in self.box.of_type("relay_end")
                if f["body"]["request_id"] == request_id
            ]
            if ends:
                body: dict[str, Any] = ends[0]["body"]
                return body
            time.sleep(0.005)
        raise AssertionError(f"no relay_end in {self.box.frames}")

    def data(self, request_id: str = "q1") -> bytes:
        frames = [
            f["body"]
            for f in self.box.of_type("relay_data")
            if f["body"]["request_id"] == request_id
        ]
        assert [f["seq"] for f in frames] == list(range(len(frames)))
        return b"".join(base64.b64decode(f["data_b64"]) for f in frames)


def _relay(head: Head, heads: Heads | None = None) -> Relay:
    from mcgyvr.rig import commands, relay

    head.server = _serve(head)
    box = fakes.Box()
    known = heads or Heads(head.port)
    relays = relay.Relays(heads=known, send=box.put)
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, relays)
    return Relay(head, known, box, relays, dispatcher)


@pytest.fixture
def made() -> Iterator[Relay]:
    built = _relay(Head())
    yield built
    built.relays.cancel_all()
    assert built.head.server is not None
    built.head.server.shutdown()


def _body() -> bytes:
    return json.dumps({"messages": [{"role": "user", "content": PROMPT}]}).encode()


def test_a_request_goes_whole_to_the_one_path_on_loopback_and_comes_back_whole(
    made: Relay, capsys: pytest.CaptureFixture[str]
) -> None:
    made.head.chunks = [b"data: one\n\n", b"data: two\n\n", b"data: [DONE]\n\n"]
    made.head.content_type = "text/event-stream"
    made.request(_body(), stream=True)
    assert made.ended() == {"request_id": "q1", "outcome": "complete"}
    ((method, path, body, headers),) = made.head.seen
    assert (method, path, body) == ("POST", "/v1/chat/completions", _body())
    assert headers["content-type"] == "application/json"
    assert headers["host"].startswith("127.0.0.1:")
    (response,) = made.box.of_type("relay_response")
    assert response["body"] == {
        "request_id": "q1",
        "status": 200,
        "content_type": "text/event-stream",
    }
    assert made.data() == b"data: one\n\ndata: two\n\ndata: [DONE]\n\n"
    said = capsys.readouterr()
    assert PROMPT not in said.out + said.err
    assert all(PROMPT not in json.dumps(f) for f in made.box.frames)


def test_no_more_than_the_window_goes_uncredited_and_credit_lets_the_rest_go(
    made: Relay,
) -> None:
    made.head.chunks = [f"data: {i}\n\n".encode() for i in range(6)]
    made.head.pause_s = 0.02
    made.request(_body(), window=2)
    time.sleep(0.5)
    sent = made.box.of_type("relay_data")
    assert len(sent) == 2
    assert not made.box.of_type("relay_end")
    for _ in range(4):
        made.send("relay_credit", "k", request_id="q1", chunks=1)
        time.sleep(0.1)
    made.send("relay_credit", "k", request_id="q1", chunks=4)
    assert made.ended()["outcome"] == "complete"
    assert made.data() == b"".join(made.head.chunks)


def test_a_cancel_ends_the_relay_and_hangs_up_on_the_head(made: Relay) -> None:
    made.head.chunks = [b"data: x\n\n"] * 200
    made.head.pause_s = 0.02
    made.request(_body(), stream=True)
    time.sleep(0.1)
    made.send("relay_cancel", "c1", request_id="q1", reason="client_gone")
    assert made.ended() == {
        "request_id": "q1",
        "outcome": "cancelled",
        "error_code": "cancelled",
    }
    assert made.head.hung_up.wait(5.0)


def test_the_hubs_time_limit_ends_the_relay(made: Relay) -> None:
    made.head.chunks = [b"data: x\n\n"] * 400
    made.head.pause_s = 0.01
    made.request(_body(), timeout_s=1)
    assert made.ended()["outcome"] == "timeout"


def test_an_answer_over_the_hubs_size_ends_too_large(made: Relay) -> None:
    made.head.chunks = [b"x" * 1000] * 5
    made.request(_body(), max_response_bytes=2500)
    assert made.ended() == {
        "request_id": "q1",
        "outcome": "too_large",
        "error_code": "too_large",
    }
    assert len(made.data()) <= 2500


def test_a_chunk_never_exceeds_the_protocols(made: Relay) -> None:
    from mcgyvr.rig import sessionwire

    made.head.chunks = [b"y" * (3 * sessionwire.RELAY_MAX_CHUNK_BYTES + 7)]
    made.request(_body(), window=64)
    assert made.ended()["outcome"] == "complete"
    for frame in made.box.of_type("relay_data"):
        raw = base64.b64decode(frame["body"]["data_b64"])
        assert 0 < len(raw) <= sessionwire.RELAY_MAX_CHUNK_BYTES
    assert len(made.data()) == 3 * sessionwire.RELAY_MAX_CHUNK_BYTES + 7


@pytest.mark.parametrize(
    ("state", "role", "session", "code"),
    [
        ("ready", "head", "nobody", "unknown_session"),
        ("loading", "head", "s1", "not_ready"),
        ("ready", "worker", "s1", "not_capable"),
    ],
)
def test_a_relay_for_a_head_that_is_not_there_or_not_ready_ends_in_error(
    state: str, role: str, session: str, code: str
) -> None:
    head = Head()
    built = _relay(head, Heads(None, state=state, role=role))
    try:
        built.request(b"{}", session_id=session)
        assert built.ended() == {
            "request_id": "q1",
            "outcome": "error",
            "error_code": code,
        }
        assert head.seen == []
    finally:
        assert head.server is not None
        head.server.shutdown()


def test_a_request_id_used_before_is_a_duplicate(made: Relay) -> None:
    made.request(b"{}")
    assert made.ended()["outcome"] == "complete"
    made.request(b"{}")
    ends = [f["body"] for f in made.box.of_type("relay_end")]
    assert ends[-1] == {
        "request_id": "q1",
        "outcome": "error",
        "error_code": "duplicate",
    }
    assert len(made.head.seen) == 1


def test_a_body_that_runs_over_or_out_of_order_is_refused_and_never_sent(
    made: Relay,
) -> None:
    assert (
        made.send(
            "relay_request",
            "r1",
            session_id="s1",
            request_id="q1",
            endpoint="chat_completions",
            body_bytes=4,
            stream=False,
            timeout_s=5,
            max_response_bytes=100,
            window=1,
        )
        is None
    )
    made.send(
        "relay_data",
        "d0",
        request_id="q1",
        seq=0,
        data_b64=base64.b64encode(b"123456").decode(),
    )
    assert made.ended()["outcome"] == "too_large"
    assert (
        made.send(
            "relay_request",
            "r2",
            session_id="s1",
            request_id="q2",
            endpoint="chat_completions",
            body_bytes=8,
            stream=False,
            timeout_s=5,
            max_response_bytes=100,
            window=1,
        )
        is None
    )
    made.send(
        "relay_data",
        "d1",
        request_id="q2",
        seq=1,
        data_b64=base64.b64encode(b"1234").decode(),
    )
    assert made.ended("q2") == {
        "request_id": "q2",
        "outcome": "error",
        "error_code": "bad_message",
    }
    time.sleep(0.1)
    assert made.head.seen == []


def test_an_endpoint_that_is_not_the_relays_one_is_refused(made: Relay) -> None:
    made.request(b"{}", endpoint="../admin")
    assert made.ended() == {
        "request_id": "q1",
        "outcome": "error",
        "error_code": "bad_message",
    }
    assert made.head.seen == []


def test_a_head_that_does_not_answer_ends_upstream_failed() -> None:
    head = Head()
    built = _relay(head)
    assert head.server is not None
    head.server.shutdown()
    head.server.server_close()
    try:
        built.request(b"{}")
        assert built.ended() == {
            "request_id": "q1",
            "outcome": "error",
            "error_code": "upstream_failed",
        }
    finally:
        built.relays.cancel_all()


def test_a_sessions_end_ends_its_relays(made: Relay) -> None:
    made.head.chunks = [b"data: x\n\n"] * 200
    made.head.pause_s = 0.02
    made.request(_body(), stream=True)
    time.sleep(0.1)
    made.relays.session_ended("s1")
    assert made.ended()["outcome"] == "cancelled"
