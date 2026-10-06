"""An answer not streamed is streamed from the head, so a requester's leave stops it.

A requester who leaves a streamed request stops its head within a token: the
agent hangs up and the head's next write fails. A requester who left a request
not streamed did not: the head (llama.cpp) notices a hang-up only when it
writes, and a whole answer is written once, at its end, so the slot decoded
the rest of the answer for nobody while the hub charged the requester for
what was made at the leave.

So the agent now asks the head for a stream behind the scenes whatever the
requester asked, and for a request not streamed assembles the whole answer
itself, as the head would have written it: the same content, finish reason,
usage and shape, byte for byte for everything the stream carries (the
``timings`` of the head's last event are passed through). The hub still
receives one ``relay_response`` and the answer in frames once it is complete,
as before; nothing reaches it early. A head that answers the stream with an
error status is passed through as it answers; an error event mid-stream
becomes the status and body the head gives a request not streamed; a body that
is no JSON object goes to the head as it came. A ride is asked of its unit
the same way, by the same code: a ride not streamed is streamed from its unit
and assembled whole, so a rider who leaves stops the host's unit at once too,
and a unit that answers with no stream is passed through as it answers. The
head's slot is at work until the stream ends, so a leave mid-answer reads its
counts as a streamed request's leave does; a ride's leave reads no counts, as
a ride's never has.
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

BUILD = "b10644-abcdef0"
MODEL = "a-model.gguf"
COMPLETION_ID = "chatcmpl-abc123def456"
JSON_TYPE = "application/json; charset=utf-8"


def _dump(value: Any) -> bytes:
    """As nlohmann::json's ``dump()`` writes it: compact, keys sorted."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _gone(sock: socket.socket) -> bool:
    readable, _, _ = select.select([sock], [], [], 0)
    if not readable:
        return False
    try:
        return sock.recv(1, socket.MSG_PEEK) == b""
    except OSError:
        return True


@dataclass
class Answer:
    """What a head's slot generates for a request: the pieces of its answer
    in the order they come, as llama.cpp hands them to both shapes."""

    content: list[str] = field(default_factory=lambda: ["Hello", ",", " world"])
    reasoning: list[str] = field(default_factory=list)
    # (index, id, name, [argument pieces])
    tool_calls: list[tuple[int, str, str, list[str]]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] | None = None
    timings: dict[str, Any] | None = field(
        default_factory=lambda: {
            "cache_n": 3,
            "prompt_n": 20,
            "prompt_ms": 51.2,
            "prompt_per_token_ms": 2.56,
            "prompt_per_second": 390.625,
            "predicted_n": 7,
            "predicted_ms": 123.4,
            "predicted_per_token_ms": 17.628,
            "predicted_per_second": 56.726,
        }
    )
    logprobs: list[dict[str, Any]] | None = None
    error: dict[str, Any] | None = None  # raised after the pieces, mid-stream
    cut_after: int | None = None  # the head dies after this many pieces
    pace_s: float = 0.0  # between pieces

    def pieces(self) -> list[dict[str, Any]]:
        """The deltas, one per piece, as the stream writes them."""
        out: list[dict[str, Any]] = [{"reasoning_content": r} for r in self.reasoning]
        out += [{"content": c} for c in self.content]
        for index, call_id, name, arguments in self.tool_calls:
            first: dict[str, Any] = {"index": index}
            if call_id:
                first["id"] = call_id
                first["type"] = "function"
            first["function"] = {"name": name, "arguments": arguments[0]}
            out.append({"tool_calls": [first]})
            for piece in arguments[1:]:
                out.append(
                    {"tool_calls": [{"index": index, "function": {"arguments": piece}}]}
                )
        return out

    def whole(self, created: int) -> bytes:
        """``to_json_oaicompat_chat``: the answer a request not streamed gets."""
        message: dict[str, Any] = {"role": "assistant"}
        reasoning = "".join(self.reasoning)
        if reasoning:
            message["reasoning_content"] = reasoning
        content = "".join(self.content)
        message["content"] = None if not content and self.tool_calls else content
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "type": "function",
                    "function": {"name": name, "arguments": "".join(arguments)},
                    "id": call_id,
                }
                for _, call_id, name, arguments in self.tool_calls
            ]
        choice: dict[str, Any] = {
            "finish_reason": self.finish_reason,
            "index": 0,
            "message": message,
        }
        if self.logprobs:
            choice["logprobs"] = {"content": self.logprobs}
        answer: dict[str, Any] = {
            "choices": [choice],
            "created": created,
            "model": MODEL,
            "system_fingerprint": BUILD,
            "object": "chat.completion",
            "id": COMPLETION_ID,
        }
        if self.usage is not None:
            answer["usage"] = self.usage
        if self.timings is not None:
            answer["timings"] = self.timings
        return _dump(answer)

    def events(self, created: int) -> list[bytes]:
        """``to_json_oaicompat_chat_stream``: the events a stream gets, the
        first with the role, the last with the finish reason, then the usage
        when asked, ``timings`` on whichever is last; ``[DONE]`` closes."""

        def chunk(choices: list[dict[str, Any]], **more: Any) -> dict[str, Any]:
            return {
                "choices": choices,
                "created": created,
                "id": COMPLETION_ID,
                "model": MODEL,
                "system_fingerprint": BUILD,
                "object": "chat.completion.chunk",
                **more,
            }

        def choice(delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
            return {"finish_reason": finish, "index": 0, "delta": delta}

        chunks = [chunk([choice({"role": "assistant", "content": None})])]
        pieces = self.pieces()
        for n, delta in enumerate(pieces):
            one = chunk([choice(delta)])
            if self.logprobs and n < len(self.logprobs):
                one["choices"][0]["logprobs"] = {"content": [self.logprobs[n]]}
            chunks.append(one)
        chunks.append(chunk([choice({}, self.finish_reason)]))
        if self.usage is not None:
            chunks.append(chunk([], usage=self.usage))
        if self.timings is not None:
            chunks[-1]["timings"] = self.timings
        return [b"data: " + _dump(c) + b"\n\n" for c in chunks]


BUSY = {
    "id": 3,
    "n_ctx": 12288,
    "speculative": False,
    "is_processing": True,
    "id_task": 230,
    "n_prompt_tokens": 36,
    "n_prompt_tokens_processed": 20,
    "n_prompt_tokens_cache": 3,
    "next_token": [
        {"has_next_token": True, "has_new_line": True, "n_remain": 287, "n_decoded": 13}
    ],
}
IDLE = {"id": 0, "n_ctx": 12288, "speculative": False, "is_processing": False}


@dataclass
class Head:
    """A model server on loopback as llama.cpp's behaves: a request not
    streamed is decoded to its end and written once, whoever is listening;
    a stream is written as it comes and stops at a hang-up."""

    answer: Answer = field(default_factory=Answer)
    status: int = 200  # of the answer to a request that parses
    refused: bytes | None = None  # a JSON error body, in place of an answer
    whole_json: bool = False  # answers whole, even a stream asked for
    created: int = 1_770_000_000
    seen: list[tuple[str, bytes, dict[str, str]]] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    asked: threading.Semaphore = field(default_factory=lambda: threading.Semaphore(0))
    server: ThreadingHTTPServer | None = None

    def note(self, event: str) -> None:
        with self.lock:
            self.events.append(event)

    def seen_event(self, event: str, timeout: float = 5.0) -> bool:
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


def _serve(head: Head) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _json(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", JSON_TYPE)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            head.note(f"GET {self.path}")
            self._json(200, json.dumps([IDLE, BUSY]).encode())

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            head.seen.append(
                (self.path, body, {k.lower(): v for k, v in self.headers.items()})
            )
            head.asked.release()
            try:
                asked = json.loads(body)
            except ValueError:
                asked = None
            if head.refused is not None or not isinstance(asked, dict):
                self._json(
                    head.status if head.refused is not None else 400,
                    head.refused or b'{"error":{"code":400,"message":"bad"}}',
                )
                return
            answer = head.answer
            try:
                if not asked.get("stream") or head.whole_json:
                    # Decoded to the end, written once: a hang-up goes unseen.
                    for _ in answer.pieces():
                        time.sleep(answer.pace_s)
                        head.note("decoded")
                    self._json(head.status, answer.whole(head.created))
                    head.note("answered")
                    return
                self.send_response(head.status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                events = answer.events(head.created)
                if asked.get("stream_options", {}).get("include_usage") is not True:
                    events = [e for e in events if b'"usage"' not in e]
                if answer.error is not None:
                    events = [
                        *events[: 1 + len(answer.pieces())],
                        b"error: " + _dump(answer.error) + b"\n\n",
                    ]
                for n, event in enumerate(events):
                    if _gone(self.connection):
                        raise OSError
                    if 0 < n <= len(answer.pieces()):
                        time.sleep(answer.pace_s)
                        head.note("decoded")
                    if answer.cut_after is not None and n > answer.cut_after:
                        self.connection.shutdown(socket.SHUT_RDWR)  # dead mid-answer
                        head.note("died")
                        return
                    self.wfile.write(f"{len(event):x}\r\n".encode() + event + b"\r\n")
                    self.wfile.flush()
                done = b"data: [DONE]\n\n"
                self.wfile.write(f"{len(done):x}\r\n".encode() + done + b"\r\n")
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
    def __init__(self, port: int) -> None:
        self.port = port

    def head_port(self, session_id: str) -> int | None:
        return self.port if session_id == "s1" else None

    def head_slots(self, session_id: str) -> int:
        return 1

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        return ("ready", "head") if session_id == "s1" else ("absent", None)


REQUEST = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "the secret prompt words"}],
    "max_tokens": 300,
    "temperature": 0.0,
}


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

    def ask(
        self,
        body: bytes = json.dumps(REQUEST).encode(),
        *,
        stream: bool = False,
        request_id: str = "q1",
        max_response_bytes: int = 1 << 20,
        ride: bool = False,
    ) -> None:
        self.send(
            "unit_relay_request" if ride else "relay_request",
            f"r-{request_id}",
            **({"unit_id": "u1"} if ride else {"session_id": "s1"}),
            request_id=request_id,
            endpoint="chat_completions",
            body_bytes=len(body),
            stream=stream,
            timeout_s=20,
            max_response_bytes=max_response_bytes,
            window=64,
        )
        self.send(
            "relay_data",
            f"d-{request_id}",
            request_id=request_id,
            seq=0,
            data_b64=base64.b64encode(body).decode(),
        )
        assert self.head.asked.acquire(timeout=5.0)

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
        raise AssertionError(f"no relay_end in {self.box.frames}")

    def response(self) -> dict[str, Any]:
        (response,) = self.box.of_type("relay_response")
        body: dict[str, Any] = response["body"]
        return body

    def data(self) -> bytes:
        frames = [f["body"] for f in self.box.of_type("relay_data")]
        assert [f["seq"] for f in frames] == list(range(len(frames)))
        return b"".join(base64.b64decode(f["data_b64"]) for f in frames)

    def posted(self) -> dict[str, Any]:
        """The one request the head received, parsed, and its headers."""
        ((path, body, headers),) = self.head.seen
        assert path == "/v1/chat/completions"
        return {"body": json.loads(body), "headers": headers}


def _rig(head: Head) -> Rig:
    from contextlib import nullcontext

    from mcgyvr.rig import commands, relay

    head.server = _serve(head)

    @dataclass
    class Shared:
        rider_cap: int = 1

        def url(self, endpoint: str) -> str:
            return f"http://127.0.0.1:{head.port}/v1/chat/completions"

    class Units:
        def advertised(self, unit_id: str) -> Shared | None:
            return Shared() if unit_id == "u1" else None

        def ride(self, unit_id: str) -> Any:
            return nullcontext()

    box = fakes.Box()
    relays = relay.Relays(heads=Heads(head.port), send=box.put, units=Units())
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


COMPLETE = {"request_id": "q1", "outcome": "complete"}
CANCELLED = {"request_id": "q1", "outcome": "cancelled", "error_code": "cancelled"}
MADE = CANCELLED | {"tokens_in": 23, "tokens_out": 13}
USAGE = {"completion_tokens": 7, "prompt_tokens": 23, "total_tokens": 30}


def test_a_request_not_streamed_reaches_the_head_as_a_stream_asking_its_counts(
    rig: Rig,
) -> None:
    rig.ask()
    assert rig.ended() == COMPLETE
    posted = rig.posted()
    assert posted["body"] == REQUEST | {
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    assert posted["headers"]["accept"] == "text/event-stream"
    assert posted["headers"]["content-type"] == "application/json"


def test_the_requesters_own_stream_options_are_kept_beside_the_counts_asked(
    rig: Rig,
) -> None:
    asked = REQUEST | {
        "stream": False,
        "stream_options": {"include_obfuscation": False},
    }
    rig.ask(json.dumps(asked).encode())
    assert rig.ended() == COMPLETE
    assert rig.posted()["body"] == REQUEST | {
        "stream": True,
        "stream_options": {"include_obfuscation": False, "include_usage": True},
    }


ANSWERS = {
    "words": Answer(usage=USAGE),
    "words, no timings": Answer(usage=USAGE, timings=None),
    "words, no usage given": Answer(usage=None),
    "reasoning, then words": Answer(
        reasoning=["Let me", " think."], content=["Yes", "."], usage=USAGE
    ),
    "a tool call and no words": Answer(
        content=[],
        tool_calls=[(0, "call_1", "lookup", ['{"q":', ' "x"}'])],
        finish_reason="tool_calls",
        usage=USAGE,
    ),
    "two tool calls, one without an id, after words": Answer(
        content=["Sure"],
        tool_calls=[
            (0, "call_1", "lookup", ['{"q": "x"}']),
            (1, "", "count", ["{}"]),
        ],
        finish_reason="tool_calls",
        usage=USAGE,
    ),
    "cut by the length cap": Answer(finish_reason="length", usage=USAGE),
    "with the probabilities of each token": Answer(
        content=["a", "b"],
        logprobs=[
            {"token": "a", "logprob": -0.1, "bytes": [97], "top_logprobs": []},
            {"token": "b", "logprob": -0.2, "bytes": [98], "top_logprobs": []},
        ],
        usage=USAGE,
    ),
    "an empty answer": Answer(content=[], usage=USAGE),
    "text with quotes, newlines and non-ascii": Answer(
        content=['He said "hi"\n', "\tnaïve — 日本 \u0001"], usage=USAGE
    ),
}


@pytest.mark.parametrize("what", ANSWERS)
def test_the_answer_assembled_is_the_one_the_head_writes_unstreamed_byte_for_byte(
    rig: Rig, what: str
) -> None:
    rig.head.answer = ANSWERS[what]
    rig.ask()
    assert rig.ended() == COMPLETE
    assert rig.response() == {
        "request_id": "q1",
        "status": 200,
        "content_type": JSON_TYPE,
    }
    assert rig.data() == rig.head.answer.whole(rig.head.created)


def test_nothing_reaches_the_hub_before_the_whole_answer_and_it_goes_in_frames(
    rig: Rig,
) -> None:
    from mcgyvr.rig import sessionwire

    rig.head.answer = Answer(content=["y" * 20_000] * 5, usage=USAGE, pace_s=0.05)
    rig.ask()
    time.sleep(0.12)  # two or three pieces in: nothing is said yet
    assert rig.box.frames == []
    assert rig.ended() == COMPLETE
    frames = rig.box.of_type("relay_data")
    assert len(frames) >= 4
    for frame in frames:
        raw = base64.b64decode(frame["body"]["data_b64"])
        assert 0 < len(raw) <= sessionwire.RELAY_MAX_CHUNK_BYTES
    assert rig.data() == rig.head.answer.whole(rig.head.created)
    # the head's words are in no frame but the answer's
    assert all(
        f["type"] in ("relay_response", "relay_data", "relay_end")
        for f in rig.box.frames
    )


def test_a_requester_who_leaves_a_request_not_streamed_stops_the_head_at_once(
    rig: Rig,
) -> None:
    rig.head.answer = Answer(content=["x"] * 200, usage=USAGE, pace_s=0.02)
    rig.ask()
    assert rig.head.seen_event("decoded")
    rig.cancel()
    assert rig.ended() == MADE  # read from the slot, which is still at work
    assert rig.head.seen_event("hung up")
    decoded = rig.head.events.count("decoded")
    assert decoded < 20, decoded  # a token or two past the leave, not the answer
    assert "answered" not in rig.head.events
    assert rig.head.events.index("GET /slots") < rig.head.events.index("hung up")
    assert not rig.box.of_type("relay_response")
    assert not rig.box.of_type("relay_data")


def test_a_ride_not_streamed_is_streamed_from_its_unit_and_assembled_whole(
    rig: Rig,
) -> None:
    rig.head.answer = Answer(usage=USAGE)
    rig.ask(ride=True)
    assert rig.ended() == COMPLETE
    posted = rig.posted()
    assert posted["body"] == REQUEST | {
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    assert posted["headers"]["accept"] == "text/event-stream"
    assert rig.response() == {
        "request_id": "q1",
        "status": 200,
        "content_type": JSON_TYPE,
    }
    assert rig.data() == rig.head.answer.whole(rig.head.created)
    assert "GET /slots" not in rig.head.events


def test_a_rider_who_leaves_a_ride_not_streamed_stops_the_units_slot_at_once(
    rig: Rig,
) -> None:
    rig.head.answer = Answer(content=["x"] * 200, usage=USAGE, pace_s=0.02)
    rig.ask(ride=True)
    assert rig.head.seen_event("decoded")
    rig.cancel()
    assert rig.ended() == CANCELLED  # a ride's unit is its host's: no counts
    assert rig.head.seen_event("hung up")
    decoded = rig.head.events.count("decoded")
    assert decoded < 20, decoded  # a token or two past the leave, not the answer
    assert "answered" not in rig.head.events
    assert "GET /slots" not in rig.head.events
    assert not rig.box.of_type("relay_response")
    assert not rig.box.of_type("relay_data")


def test_a_unit_that_answers_a_ride_with_no_stream_is_passed_through_as_it_answers(
    rig: Rig,
) -> None:
    rig.head.answer = Answer(usage=USAGE)
    rig.head.whole_json = True
    rig.ask(ride=True)
    assert rig.ended() == COMPLETE
    assert rig.posted()["body"]["stream"] is True  # asked for one all the same
    assert rig.response() == {
        "request_id": "q1",
        "status": 200,
        "content_type": JSON_TYPE,
    }
    assert rig.data() == rig.head.answer.whole(rig.head.created)
    assert "GET /slots" not in rig.head.events


def test_an_error_mid_stream_is_the_status_and_body_the_head_gives_unstreamed(
    rig: Rig,
) -> None:
    error = {
        "code": 500,
        "message": "context shift is disabled",
        "type": "server_error",
    }
    rig.head.answer = Answer(content=["a", "b"], error=error)
    rig.ask()
    assert rig.ended() == COMPLETE
    assert rig.response() == {
        "request_id": "q1",
        "status": 500,
        "content_type": JSON_TYPE,
    }
    assert rig.data() == _dump({"error": error})


def test_an_error_mid_stream_with_no_status_of_its_own_is_a_server_error(
    rig: Rig,
) -> None:
    rig.head.answer = Answer(content=[], error={"message": "no code"})
    rig.ask()
    assert rig.ended() == COMPLETE
    assert rig.response()["status"] == 500
    assert rig.data() == _dump({"error": {"message": "no code"}})


def test_a_head_that_refuses_the_request_is_passed_through_as_it_answers(
    rig: Rig,
) -> None:
    rig.head.status = 400
    rig.head.refused = (
        b'{"error":{"code":400,"message":"bad request","type":"invalid"}}'
    )
    rig.ask()
    assert rig.ended() == COMPLETE
    assert rig.response() == {
        "request_id": "q1",
        "status": 400,
        "content_type": JSON_TYPE,
    }
    assert rig.data() == rig.head.refused


def test_a_body_that_is_no_json_object_goes_to_the_head_as_it_came(rig: Rig) -> None:
    for n, body in enumerate((b"[1, 2]", b"not json", b'"\\ud800"')):
        rig.head.seen.clear()
        rig.box.frames.clear()
        rig.ask(body, request_id=f"q{n}")
        assert rig.ended(f"q{n}")["outcome"] == "complete"
        ((_, posted, headers),) = rig.head.seen
        assert posted == body
        assert headers["accept"] == "application/json"
        assert rig.response()["status"] == 400


def test_a_stream_that_ends_without_its_answer_fails_upstream(rig: Rig) -> None:
    """The head died mid-answer: no finish reason and no error came. A
    request not streamed would have had the head's failure, not a cut body."""
    rig.head.answer = Answer(content=["a"] * 50, usage=USAGE, cut_after=3)
    rig.ask()
    assert rig.head.seen_event("died")
    assert rig.ended() == {
        "request_id": "q1",
        "outcome": "error",
        "error_code": "upstream_failed",
    }
    assert not rig.box.of_type("relay_response")
    assert not rig.box.of_type("relay_data")


def test_an_answer_past_the_hubs_size_ends_too_large_without_being_sent(
    rig: Rig,
) -> None:
    rig.head.answer = Answer(content=["z" * 1000] * 5, usage=USAGE)
    rig.ask(max_response_bytes=2500)
    assert rig.ended() == {
        "request_id": "q1",
        "outcome": "too_large",
        "error_code": "too_large",
    }
    assert not rig.box.of_type("relay_data")


def test_a_streamed_request_is_passed_through_as_before(rig: Rig) -> None:
    rig.head.answer = Answer(usage=USAGE)
    asked = REQUEST | {"stream": True, "stream_options": {"include_usage": True}}
    rig.ask(json.dumps(asked).encode(), stream=True)
    assert rig.ended() == COMPLETE
    assert rig.response()["content_type"] == "text/event-stream"
    assert rig.data() == b"".join(
        [*rig.head.answer.events(rig.head.created), b"data: [DONE]\n\n"]
    )
    assert rig.posted()["body"] == asked
