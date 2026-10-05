"""A cancelled relay reports what its head made, read before the agent hangs up.

A requester who leaves early has the hub cancel the relay. The rig stops at
once, as before, and now says in its ``relay_end`` what the head made by
then (``tokens_in``, ``tokens_out``), so the hub can charge exactly that: the
agent reads the head's own status page (``/slots``, on the loopback API the
relay posts to) just before it hangs up, on a thread of its own, never the
one that hears the hub.

The counts are the slot's that serves this relay, and the page does not say
which that is. So they are reported only when it cannot be another's: this
relay is the only one in its head, none began meanwhile, the head is still
working on it, and exactly one slot is busy. In every other case (no page, a
page that is not llama.cpp's, several slots busy, another relay in the head,
an answer the head has already given, a ride to a unit its host uses too, a
page that is slow) the relay ends as it always did, ``cancelled`` and no
counts, and the hub falls back to what it did before. It is never an error.
"""

from __future__ import annotations

import base64
import json
import select
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes

IDLE = {"id": 1, "n_ctx": 4096, "speculative": False, "is_processing": False}


def busy(slot_id: int = 0, *, n_in: Any = 40, n_out: Any = 7) -> dict[str, Any]:
    """A slot at work, as llama.cpp's ``/slots`` shows it."""
    return {
        "id": slot_id,
        "n_ctx": 4096,
        "speculative": False,
        "is_processing": True,
        "id_task": 12,
        "n_prompt_tokens": n_in,
        "n_prompt_tokens_processed": n_in,
        "n_prompt_tokens_cache": 0,
        "params": {"n_predict": 512, "stream": True},
        "next_token": [
            {
                "has_next_token": True,
                "has_new_line": False,
                "n_remain": 505,
                "n_decoded": n_out,
            }
        ],
    }


@dataclass
class Head:
    """A model server on loopback: an answer that takes its time, and the
    status page it shows meanwhile."""

    page: bytes = json.dumps([busy(), IDLE]).encode()
    page_status: int = 200
    page_delay_s: float = 0.0
    answers_first: bool = True  # its headers go out before it generates
    chunks: int = 400
    events: list[str] = field(default_factory=list)  # in the order they happen
    lock: threading.Lock = field(default_factory=threading.Lock)
    asked: threading.Semaphore = field(default_factory=lambda: threading.Semaphore(0))
    server: ThreadingHTTPServer | None = None

    def note(self, event: str) -> None:
        with self.lock:
            self.events.append(event)

    def seen(self, event: str, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if event in self.events:
                    return True
            time.sleep(0.005)
        return False

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.server_address[1])


def _gone(sock: socket.socket) -> bool:
    """Whether the other end hung up on ``sock``."""
    readable, _, _ = select.select([sock], [], [], 0)
    if not readable:
        return False
    try:
        return sock.recv(1, socket.MSG_PEEK) == b""
    except OSError:
        return True


def _serve(head: Head) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            head.note(f"GET {self.path}")
            time.sleep(head.page_delay_s)
            self.send_response(head.page_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(head.page)))
            self.end_headers()
            self.wfile.write(head.page)

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            head.asked.release()
            try:
                if not head.answers_first:  # generating: nothing said yet
                    for _ in range(head.chunks):
                        if _gone(self.connection):
                            raise OSError
                        time.sleep(0.01)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for _ in range(head.chunks if head.answers_first else 1):
                    chunk = b"data: x\n\n"
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.flush()
                    time.sleep(0.01)
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
                head.note("answered")
            except OSError:
                head.note("hung up")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Heads:
    """One ready head, of ``slots`` slots."""

    def __init__(self, port: int, slots: int = 1) -> None:
        self.port = port
        self.slots = slots

    def head_port(self, session_id: str) -> int | None:
        return self.port if session_id == "s1" else None

    def head_slots(self, session_id: str) -> int:
        return self.slots

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        return ("ready", "head") if session_id == "s1" else ("absent", None)


@dataclass
class Rig:
    head: Head
    box: fakes.Box
    relays: Any
    dispatcher: Any

    def send(self, kind: str, message_id: str, **body: Any) -> None:
        answer = self.dispatcher.dispatch(
            fakes.frame(kind, message_id, **body), fakes.Stub()
        )
        assert answer is None, answer

    def ask(self, request_id: str = "q1", *, stream: bool = True) -> None:
        body = b'{"messages": []}'
        self.send(
            "relay_request",
            f"r-{request_id}",
            session_id="s1",
            request_id=request_id,
            endpoint="chat_completions",
            body_bytes=len(body),
            stream=stream,
            timeout_s=20,
            max_response_bytes=1 << 20,
            window=64,
        )
        self.send(
            "relay_data",
            f"d-{request_id}",
            request_id=request_id,
            seq=0,
            data_b64=base64.b64encode(body).decode(),
        )
        assert self.head.asked.acquire(timeout=5.0)  # the head has the request

    def cancel(self, request_id: str = "q1") -> None:
        self.send("relay_cancel", f"c-{request_id}", request_id=request_id)

    def ended(self, request_id: str = "q1", timeout: float = 5.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for end in self.box.of_type("relay_end"):
                if end["body"]["request_id"] == request_id:
                    body: dict[str, Any] = end["body"]
                    return body
            time.sleep(0.005)
        raise AssertionError("no relay_end")

    def answering(self, request_id: str = "q1", timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while not self.box.of_type("relay_data"):
            assert time.monotonic() < deadline, "the answer never started"
            time.sleep(0.005)


def _rig(head: Head, slots: int = 1) -> Rig:
    from mcgyvr.rig import commands, relay

    head.server = _serve(head)
    box = fakes.Box()
    relays = relay.Relays(heads=Heads(head.port, slots), send=box.put)
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, relays)
    return Rig(head, box, relays, dispatcher)


@pytest.fixture
def rig() -> Iterator[Rig]:
    built = _rig(Head())
    yield built
    built.relays.cancel_all()
    assert built.head.server is not None
    built.head.server.shutdown()


CANCELLED = {"request_id": "q1", "outcome": "cancelled", "error_code": "cancelled"}
MADE = CANCELLED | {"tokens_in": 40, "tokens_out": 7}


def test_a_stream_cancelled_mid_answer_says_what_its_slot_made(rig: Rig) -> None:
    rig.ask()
    rig.answering()
    rig.cancel()
    assert rig.ended() == MADE  # and the frame is the hub's schema's (the box)
    assert rig.head.seen("hung up")
    # read first, then hung up: once it hangs up the slot is no longer at work
    assert rig.head.events == ["GET /slots", "hung up"]


def test_an_answer_not_streamed_cancelled_while_the_head_works_says_it_too(
    rig: Rig,
) -> None:
    rig.head.answers_first = False
    rig.ask(stream=False)
    rig.cancel()
    assert rig.ended() == MADE
    assert rig.head.seen("hung up")
    assert rig.head.events == ["GET /slots", "hung up"]
    assert not rig.box.of_type("relay_response")


PAGES = {
    "no such page": (404, b'{"error": {"code": 404, "message": "File Not Found"}}'),
    "the page is turned off": (
        501,
        b'{"error": {"code": 501, "message": "This server does not support slots '
        b'endpoint.", "type": "not_supported_error"}}',
    ),
    "an error object": (200, b'{"error": {"code": 501}}'),
    "not json": (200, b"vllm:num_requests_running 1.0\n"),
    "no slots": (200, b"[]"),
    "no slot at work": (200, json.dumps([IDLE]).encode()),
    "two slots at work": (200, json.dumps([busy(0), busy(1, n_out=9)]).encode()),
    "a slot that does not say whether it works": (
        200,
        json.dumps([busy(), {"id": 1}]).encode(),
    ),
    "no count of the prompt": (200, json.dumps([busy(n_in=None)]).encode()),
    "a prompt not counted yet": (200, json.dumps([busy(n_in=0)]).encode()),
    "no count of the answer": (200, json.dumps([busy(n_out=None)]).encode()),
    "a count that is no number": (200, json.dumps([busy(n_out=True)]).encode()),
    "a count below zero": (200, json.dumps([busy(n_out=-1)]).encode()),
    "a count past the protocol's": (200, json.dumps([busy(n_in=1 << 40)]).encode()),
}


@pytest.mark.parametrize("why", PAGES)
def test_a_page_that_does_not_say_for_certain_leaves_the_end_as_it_was(
    rig: Rig, why: str
) -> None:
    rig.head.page_status, rig.head.page = PAGES[why]
    rig.ask()
    rig.answering()
    rig.cancel()
    assert rig.ended() == CANCELLED
    assert rig.head.seen("hung up")


def test_a_slow_page_is_not_waited_for_and_the_agents_thread_never_waits(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import relay

    monkeypatch.setattr(relay, "REPORT_WAIT_S", 0.2)
    rig.head.page_delay_s = 3.0
    rig.ask()
    rig.answering()
    began = time.monotonic()
    rig.cancel()  # the handler, on the thread that hears the hub
    assert time.monotonic() - began < 0.1
    assert rig.ended() == CANCELLED
    assert time.monotonic() - began < 2.0
    assert rig.head.seen("hung up")


def test_with_another_relay_in_the_head_no_slot_is_this_relays_for_certain() -> None:
    built = _rig(Head(), slots=2)
    try:
        built.ask("q1")
        built.ask("q2")
        built.cancel("q1")
        assert built.ended("q1") == CANCELLED
        built.cancel("q2")  # alone in its head now: its slot is the one at work
        assert built.ended("q2") == MADE | {"request_id": "q2"}
    finally:
        built.relays.cancel_all()
        assert built.head.server is not None
        built.head.server.shutdown()


def test_an_answer_not_streamed_that_the_head_has_given_is_not_read_for(
    rig: Rig,
) -> None:
    """Its slot is done: whatever slot is at work now is somebody else's."""
    rig.head.answers_first = True  # the answer is on its way, in pieces
    rig.ask(stream=False)
    rig.answering()
    rig.cancel()
    assert rig.ended() == CANCELLED
    assert rig.head.seen("hung up")
    assert "GET /slots" not in rig.head.events


def test_a_ride_is_cancelled_as_before_and_its_unit_is_not_read() -> None:
    """A unit its host uses too: a slot at work there may be the host's."""
    from mcgyvr.rig import commands, relay

    head = Head()
    head.server = _serve(head)

    @dataclass
    class Shared:
        rider_cap: int = 1

        def url(self, endpoint: str) -> str:
            return f"http://127.0.0.1:{head.port}/v1/chat/completions"

    class Units:
        def advertised(self, unit_id: str) -> Shared | None:
            return Shared()

        def ride(self, unit_id: str) -> Any:
            from contextlib import nullcontext

            return nullcontext()

    box = fakes.Box()
    relays = relay.Relays(heads=Heads(head.port), send=box.put, units=Units())
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, relays)
    built = Rig(head, box, relays, dispatcher)
    try:
        body = b"{}"
        built.send(
            "unit_relay_request",
            "r1",
            unit_id="u1",
            request_id="q1",
            endpoint="chat_completions",
            body_bytes=len(body),
            stream=True,
            timeout_s=20,
            max_response_bytes=1 << 20,
            window=64,
        )
        built.send(
            "relay_data",
            "d1",
            request_id="q1",
            seq=0,
            data_b64=base64.b64encode(body).decode(),
        )
        built.answering()
        built.cancel()
        assert built.ended() == CANCELLED
        assert head.seen("hung up")
        assert "GET /slots" not in head.events
    finally:
        relays.cancel_all()
        head.server.shutdown()


def test_a_relay_that_ends_some_other_way_reports_nothing(rig: Rig) -> None:
    rig.ask()
    rig.answering()
    rig.relays.session_ended("s1")
    assert rig.ended() == CANCELLED
    assert "GET /slots" not in rig.head.events


def test_a_relay_end_says_both_counts_or_neither() -> None:
    from mcgyvr.rig import sessionwire

    said = json.loads(
        sessionwire.relay_end(
            "q1", outcome="cancelled", error_code="cancelled", made=(40, 7)
        )
    )
    assert said["body"] == MADE
    for made in ((-1, 7), (40, -1), (1 << 40, 7)):
        with pytest.raises(ValueError):
            sessionwire.relay_end("q1", outcome="cancelled", made=made)
