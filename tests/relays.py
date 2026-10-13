"""A head relaying a request, and the stream it sends back."""

from __future__ import annotations

import base64
import json
import select
import socket
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.mcorch.loop import Trace
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
    # A held page is answered only once ``page_free`` is set: as slow as a
    # test needs, by what the test does, not by how long a clock runs.
    page_held: bool = False
    page_free: threading.Event = field(default_factory=threading.Event)
    answers_first: bool = True  # its headers go out before it generates
    chunks: int = 400
    events: list[str] = field(default_factory=list)  # in the order they happen
    lock: threading.Lock = field(default_factory=threading.Lock)
    asked: threading.Semaphore = field(default_factory=lambda: threading.Semaphore(0))
    streaming: threading.Event = field(default_factory=threading.Event)  # 1st piece
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
            if head.page_held:
                head.page_free.wait()
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
                    head.streaming.set()
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

    def at_work(self, request_id: str = "q1", timeout: float = 5.0) -> None:
        """Wait until the agent counts the head at work on ``request_id``.

        The head has the request (:meth:`ask`) a moment before the agent's
        relay thread, back from sending it, says so; a cancel in between is
        read for nothing, rightly, and on a loaded machine that moment is
        long. A stream's first frame (:meth:`answering`) comes after it; an
        answer not streamed sends the hub nothing to wait for, so this waits
        on the relay itself."""
        deadline = time.monotonic() + timeout
        while True:
            with self.relays._lock:
                relay = self.relays._active.get(request_id)
            if relay is not None:
                with relay.changed:
                    if relay.working:
                        return
            assert time.monotonic() < deadline, "the head never went to work"
            time.sleep(0.005)


CANCELLED = {"request_id": "q1", "outcome": "cancelled", "error_code": "cancelled"}


MADE = CANCELLED | {"tokens_in": 40, "tokens_out": 7}


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


#: An answer that is still streaming whenever a test ends it: the head
#: writes it until it is hung up on.
ENDLESS = 1 << 20


PROMPT = "the secret prompt words"


@dataclass
class RelayHead:
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


def _relay_serve(head: RelayHead) -> ThreadingHTTPServer:
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


class RelayHeads:
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

    def head_slots(self, session_id: str) -> int:
        return 1

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        return (self.state, self.role) if session_id == "s1" else ("absent", None)


def _relay_body() -> bytes:
    return json.dumps({"messages": [{"role": "user", "content": PROMPT}]}).encode()


MODEL = "a-model.gguf"


USAGE = {"completion_tokens": 7, "prompt_tokens": 23, "total_tokens": 30}


TIMINGS = {
    "prompt_n": 23,
    "prompt_per_second": 390.625,
    "predicted_n": 7,
    "predicted_per_second": 56.726,
    "draft_n": 4,
    "draft_n_accepted": 3,
}


def _dump(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _runner_gone(sock: socket.socket) -> bool:
    readable, _, _ = select.select([sock], [], [], 0)
    if not readable:
        return False
    try:
        return sock.recv(1, socket.MSG_PEEK) == b""
    except OSError:
        return True


@dataclass
class Unit:
    """A model server on loopback as llama.cpp's behaves: an answer not
    streamed is decoded to its end and written once, whoever is listening;
    a stream is written as it comes and stops at a hang-up."""

    pieces: list[str] = field(default_factory=lambda: ["Hello", ",", " world"])
    finish_reason: str = "stop"
    usage: dict[str, int] | None = field(default_factory=lambda: dict(USAGE))
    timings: dict[str, Any] | None = field(default_factory=lambda: dict(TIMINGS))
    pace_s: float = 0.0
    error: dict[str, Any] | None = None  # written mid-stream, after the pieces
    cut_after: int | None = None  # the unit dies after this many pieces
    status: int = 200
    refused: bytes | None = None  # a body in place of an answer
    whole_json: bool = False  # answers a stream asked with a whole JSON body
    logprobs: list[dict[str, Any]] | None = None  # one entry per piece
    seen: list[dict[str, Any]] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    server: ThreadingHTTPServer | None = None

    def note(self, event: str) -> None:
        with self.lock:
            self.events.append(event)

    def seen_event(self, event: str, timeout: float = 5.0, count: int = 1) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if self.events.count(event) >= count:
                    return True
            time.sleep(0.005)
        return False

    def decoded(self) -> int:
        with self.lock:
            return self.events.count("decoded")

    @property
    def endpoint(self) -> Endpoint:
        assert self.server is not None
        return Endpoint(
            source="unit",
            base_url=f"http://127.0.0.1:{self.server.server_address[1]}",
            protocol=Protocol.OPENAI,
            max_parallel=1,
            credential_env=None,
        )

    def whole(self) -> dict[str, Any]:
        """The answer a request not streamed gets."""
        choice: dict[str, Any] = {
            "finish_reason": self.finish_reason,
            "index": 0,
            "message": {"role": "assistant", "content": "".join(self.pieces)},
        }
        if self.logprobs:
            choice["logprobs"] = {"content": self.logprobs}
        answer: dict[str, Any] = {
            "choices": [choice],
            "created": 1_770_000_000,
            "model": MODEL,
            "object": "chat.completion",
            "id": "chatcmpl-abc",
        }
        if self.usage is not None:
            answer["usage"] = self.usage
        if self.timings is not None:
            answer["timings"] = self.timings
        return answer

    def stream(self) -> list[bytes]:
        def chunk(choices: list[dict[str, Any]], **more: Any) -> bytes:
            event = {
                "choices": choices,
                "created": 1_770_000_000,
                "id": "chatcmpl-abc",
                "model": MODEL,
                "object": "chat.completion.chunk",
                **more,
            }
            return b"data: " + _dump(event) + b"\n\n"

        events = [
            chunk([{"index": 0, "delta": {"role": "assistant", "content": None}}])
        ]
        for n, piece in enumerate(self.pieces):
            choice: dict[str, Any] = {"index": 0, "delta": {"content": piece}}
            if self.logprobs and n < len(self.logprobs):
                choice["logprobs"] = {"content": [self.logprobs[n]]}
            events.append(chunk([choice]))
        events.append(
            chunk([{"index": 0, "delta": {}, "finish_reason": self.finish_reason}])
        )
        if self.usage is not None:
            events.append(chunk([], usage=self.usage))
        if self.timings is not None:
            last = json.loads(events[-1][6:])
            last["timings"] = self.timings
            events[-1] = b"data: " + _dump(last) + b"\n\n"
        return events


def _runner_serve(unit: Unit) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _json(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            asked = json.loads(body)
            unit.seen.append(
                {
                    "path": self.path,
                    "body": asked,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                }
            )
            if unit.refused is not None:
                self._json(unit.status, unit.refused)
                return
            try:
                if not asked.get("stream") or unit.whole_json:
                    for _ in unit.pieces:
                        time.sleep(unit.pace_s)
                        unit.note("decoded")
                    self._json(unit.status, _dump(unit.whole()))
                    unit.note("answered")
                    return
                self.send_response(unit.status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                events = unit.stream()
                if asked.get("stream_options", {}).get("include_usage") is not True:
                    events = [e for e in events if b'"usage"' not in e]
                if unit.error is not None:
                    events = [
                        *events[: 1 + len(unit.pieces)],
                        b"error: " + _dump(unit.error) + b"\n\n",
                    ]
                for n, event in enumerate(events):
                    if _runner_gone(self.connection):
                        raise OSError
                    if 0 < n <= len(unit.pieces):
                        time.sleep(unit.pace_s)
                        unit.note("decoded")
                    if unit.cut_after is not None and n > unit.cut_after:
                        self.connection.shutdown(socket.SHUT_RDWR)
                        unit.note("died")
                        return
                    self.wfile.write(f"{len(event):x}\r\n".encode() + event + b"\r\n")
                    self.wfile.flush()
                done = b"data: [DONE]\n\n"
                self.wfile.write(f"{len(done):x}\r\n".encode() + done + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
                unit.note("answered")
            except OSError:
                unit.note("hung up")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


TRACE = Trace(
    kind="main",
    intent="work",
    jev=(),
    dropped_tools=(),
    dropped_system_bytes=0,
    dropped_blocks=(),
    rounds=1,
    internal_calls=(),
    next=None,
)


RIDE_PROMPT = "the rider's secret words"


RIDE_MODEL = "qwen-coder-7b.gguf"


SERVED = "Qwen2.5-Coder-7B-Instruct-Q5_K_M"


@dataclass
class UnitServer:
    """A host's own model server on loopback, answering as its weights name it."""

    hold: bool = False
    release: threading.Event = field(default_factory=threading.Event)
    seen: list[tuple[str, bytes]] = field(default_factory=list)
    running: int = 0
    hung_up: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    server: ThreadingHTTPServer | None = None

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.server_address[1])

    def answer(self) -> bytes:
        return json.dumps(
            {"model": SERVED, "choices": [{"message": {"content": "ok"}}]}
        ).encode()


def _ride_serve(unit: UnitServer) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            with unit.lock:
                unit.seen.append((self.path, body))
                unit.running += 1
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                # While held, a space now and then: writing is how a hang-up
                # is found, and a few of them stay well inside the window.
                while unit.hold and not unit.release.wait(0.25):
                    self.wfile.write(b"1\r\n \r\n")
                    self.wfile.flush()
                chunk = unit.answer()
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                unit.hung_up.set()
            finally:
                with unit.lock:
                    unit.running -= 1

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Now:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class NoHeads:
    def head_port(self, session_id: str) -> int | None:
        return None

    def head_slots(self, session_id: str) -> int:
        return 1

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        return ("absent", None)


@dataclass
class Host:
    unit: UnitServer
    box: fakes.Box
    units: Any
    relays: Any
    dispatcher: Any
    capacity: Any
    busy: dict[str, int | None]
    now: Now
    checks: list[float]

    def send(self, kind: str, message_id: str = "r1", **body: Any) -> None:
        reply = self.dispatcher.dispatch(
            fakes.frame(kind, message_id, **body), fakes.Stub()
        )
        if reply is not None:
            self.box.put(reply)

    def ride(self, body: bytes, request_id: str = "q1", **changes: Any) -> None:
        fields: dict[str, Any] = {
            "unit_id": "coder",
            "request_id": request_id,
            "endpoint": "chat_completions",
            "body_bytes": len(body),
            "stream": False,
            "timeout_s": 10,
            "max_response_bytes": 1 << 20,
            "window": 64,
        }
        fields.update(changes)
        self.send("unit_relay_request", f"r-{request_id}", **fields)
        if body:
            self.send(
                "relay_data",
                f"d-{request_id}",
                request_id=request_id,
                seq=0,
                data_b64=base64.b64encode(body).decode(),
            )

    def ended(self, request_id: str = "q1", timeout: float = 5.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ends = [
                f["body"]
                for f in self.box.of_type("relay_end")
                if f["body"]["request_id"] == request_id
            ]
            if ends:
                found: dict[str, Any] = ends[0]
                return found
            time.sleep(0.005)
        raise AssertionError(f"no relay_end for {request_id} in {self.box.frames}")

    def running(self, count: int, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.unit.lock:
                if self.unit.running == count:
                    return
            time.sleep(0.005)
        raise AssertionError(f"the unit runs {self.unit.running}, not {count}")

    def answer(self, request_id: str = "q1") -> bytes:
        frames = [
            f["body"]
            for f in self.box.of_type("relay_data")
            if f["body"]["request_id"] == request_id
        ]
        return b"".join(base64.b64decode(f["data_b64"]) for f in frames).strip()


def _host(
    tmp_path: Path,
    *,
    width: int = 4,
    rider_slots: int = 2,
    max_active: int = 16,
    second: bool = False,
) -> Host:
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import parse
    from mcgyvr.rig import commands, hitchhike, relay

    unit = UnitServer()
    unit.server = _ride_serve(unit)
    text = (
        "units:\n"
        "  coder:\n"
        f"    address: http://127.0.0.1:{unit.port}/v1\n"
        f"    model: {RIDE_MODEL}\n"
        f"    width: {width}\n"
        "    window: 8192\n"
    )
    if second:
        text += (
            "  other:\n"
            f"    address: http://127.0.0.1:{unit.port}\n"
            "    model: other.gguf\n"
            "    width: 2\n"
            "    window: 4096\n"
        )
    text += "ladder: [coder" + (", other" if second else "") + "]\n"
    text += f"rider_slots: {{coder: {rider_slots}" + (", other: 1" if second else "")
    text += "}\n"
    config = parse(text)
    capacity = Capacity.of(config, root=tmp_path / "slots")
    busy: dict[str, int | None] = {"coder": 0, "other": 0}
    checks: list[float] = []
    now = Now()

    def setup() -> hitchhike.Setup:
        checks.append(now.now)
        shared, notes = hitchhike.shared_units(config)
        return hitchhike.Setup(
            units=shared,
            notes=notes,
            in_flight=lambda shared_unit: busy[shared_unit.name],
            hold=lambda shared_unit: capacity.hold(shared_unit.name, timeout=0),
        )

    box = fakes.Box()
    units = hitchhike.Units(
        setup=setup,
        send=box.put,
        clock=now,
        say=lambda line: None,
        start=lambda work: work(),
    )
    units.online()
    made = relay.Relays(
        heads=NoHeads(),
        send=box.put,
        units=units,
        max_active=max_active,
    )
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, made)
    return Host(unit, box, units, made, dispatcher, capacity, busy, now, checks)


def _ride_body(model: str = RIDE_MODEL) -> bytes:
    return json.dumps(
        {"model": model, "messages": [{"role": "user", "content": RIDE_PROMPT}]}
    ).encode()
