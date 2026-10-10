"""The runner streams from every unit, and hangs up when whoever asked has gone.

A unit notices that whoever asked has gone only when it writes to them, and an
answer not streamed is written once, at its end: a dispatch left mid-answer
(a timeout, Ctrl-C, a facade client that closed its connection) had the slot
decode the rest for nobody. So the runner now asks every unit for a stream
(``stream`` and ``stream_options.include_usage`` on the body, ``Accept:
text/event-stream``) and assembles the whole answer itself with the
product-core piece (:mod:`mcgyvr.whole`), so the completion is what the unit's
answer not streamed would have given: the same text, stop reason, counts and
the unit's own ``timings``. What is held here:

* the completion assembled from the stream equals the one read from the
  unit's whole answer, field for field;
* ``timeout_s`` bounds the whole dispatch, not each token: a stream slower
  than it ends at the deadline, as a transport failure, and the unit sees the
  hang-up at once;
* a :class:`~mcgyvr.runner.Hangup` held by whoever asked ends the dispatches
  made under it at once (the unit's next write fails), the dispatch raises
  :class:`~mcgyvr.runner.HungUpError`, and a dispatch made under it afterwards
  reaches no unit; :func:`~mcgyvr.runner.hang_up_all` does the same for every
  dispatch of the process (Ctrl-C);
* a unit that answers anything but a 200 stream is read as before: an error
  status is :class:`~mcgyvr.runner.BackendError` with its body, a whole JSON
  answer is parsed as it comes, an error event mid-stream is the status it
  says, and a stream that ends without its answer is a transport failure.
"""

from __future__ import annotations

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

from mcgyvr import runner as runner_module
from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.runner import (
    BackendError,
    Hangup,
    HungUpError,
    ProtocolError,
    Request,
    StopReason,
    TransportError,
    hang_up_all,
    runner_for,
)
from mcgyvr.whole import MAX_EVENT_BYTES

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


def _gone(sock: socket.socket) -> bool:
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


def _serve(unit: Unit) -> ThreadingHTTPServer:
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
                    if _gone(self.connection):
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


@pytest.fixture
def unit() -> Iterator[Unit]:
    built = Unit()
    built.server = _serve(built)
    yield built
    built.server.shutdown()


ASK = Request(prompt="hi", max_output_tokens=300, timeout_s=5.0)


def _generate(unit: Unit, request: Request = ASK) -> Any:
    return runner_for(unit.endpoint).generate(MODEL, request)


def _in_thread(
    unit: Unit, request: Request = ASK
) -> tuple[threading.Thread, dict[str, Any]]:
    """A dispatch on a thread of its own; its outcome, once it has one."""
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["done"] = _generate(unit, request)
        except Exception as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcome


# -- the stream is asked, the whole is assembled -------------------------------


def test_every_dispatch_asks_the_unit_for_a_stream_and_its_counts(unit: Unit) -> None:
    _generate(unit)
    (seen,) = unit.seen
    assert seen["path"] == "/v1/chat/completions"
    assert seen["body"]["stream"] is True
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert seen["headers"]["accept"] == "text/event-stream"
    assert seen["headers"]["content-type"] == "application/json"
    assert unit.seen_event("answered")


def test_the_completion_is_what_the_units_whole_answer_would_have_given(
    unit: Unit,
) -> None:
    """Field for field: what the parser reads from the assembled answer is
    what it reads from the answer the unit writes a request not streamed."""
    done = _generate(unit)
    assert done.text == "Hello, world"
    assert done.stop_reason is StopReason.COMPLETE
    assert done.raw_stop_reason == "stop"
    assert done.served_model == MODEL
    assert (done.input_tokens, done.output_tokens) == (23, 7)
    assert done.decode_tok_s == pytest.approx(56.726)
    assert done.prefill_tok_s == pytest.approx(390.625)
    assert (done.draft_n, done.draft_n_accepted) == (4, 3)
    assert done.complete is True

    parsed = runner_for(unit.endpoint)._parse(unit.whole())
    assert parsed.text == done.text
    assert parsed.raw_stop_reason == done.raw_stop_reason
    assert (parsed.input_tokens, parsed.output_tokens) == (
        done.input_tokens,
        done.output_tokens,
    )
    assert parsed.decode_tok_s == done.decode_tok_s
    assert parsed.prefill_tok_s == done.prefill_tok_s


def test_a_reply_cut_by_the_cap_and_one_with_no_counts_read_as_before(
    unit: Unit,
) -> None:
    unit.finish_reason = "length"
    unit.usage = None
    unit.timings = None
    done = _generate(unit)
    assert done.stop_reason is StopReason.TRUNCATED
    assert done.truncated is True
    assert done.output_tokens is None
    assert done.decode_tok_s is None


# -- the deadline ----------------------------------------------------------------


def test_the_timeout_bounds_the_whole_dispatch_and_the_unit_sees_the_hang_up(
    unit: Unit,
) -> None:
    """Each token comes well inside the timeout; the answer does not."""
    unit.pieces = ["x"] * 200
    unit.pace_s = 0.02
    started = time.monotonic()
    with pytest.raises(TransportError, match=r"within 0\.3s"):
        _generate(unit, Request(prompt="hi", max_output_tokens=300, timeout_s=0.3))
    assert time.monotonic() - started < 2.0
    assert unit.seen_event("hung up")
    assert unit.decoded() < 60, unit.decoded()
    assert "answered" not in unit.events


# -- whoever asked has gone ------------------------------------------------------


def test_a_hangup_ends_the_dispatches_made_under_it_and_the_unit_stops_at_once(
    unit: Unit,
) -> None:
    unit.pieces = ["x"] * 400
    unit.pace_s = 0.02
    hangup = Hangup()
    outcome: dict[str, Any] = {}

    def run() -> None:
        with hangup:
            try:
                outcome["done"] = _generate(unit)
            except Exception as exc:
                outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert unit.seen_event("decoded")
    time.sleep(0.1)  # a few tokens in
    hangup.hang_up()
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert isinstance(outcome.get("error"), HungUpError)
    assert isinstance(outcome["error"], TransportError)  # the climb's one kind
    assert unit.seen_event("hung up")
    decoded = unit.decoded()
    assert decoded < 20, decoded  # a token or two past the leave, not the answer
    assert "answered" not in unit.events
    assert hangup.hung_up is True


def test_a_dispatch_made_under_a_hangup_that_was_hung_up_reaches_no_unit(
    unit: Unit,
) -> None:
    hangup = Hangup()
    hangup.hang_up()
    with hangup, pytest.raises(HungUpError):
        _generate(unit)
    assert unit.seen == []


def test_a_hangup_is_the_threads_own_and_leaves_other_dispatches_be(unit: Unit) -> None:
    """A hangup ends what was asked under it, on its thread; a dispatch on
    another thread, under no hangup, runs to its end."""
    unit.pieces = ["x"] * 20
    unit.pace_s = 0.02
    thread, outcome = _in_thread(unit)
    assert unit.seen_event("decoded")
    Hangup().hang_up()  # nothing was asked under this one
    with Hangup() as other:
        other.hang_up()
    thread.join(timeout=5.0)
    assert "done" in outcome
    assert outcome["done"].text == "x" * 20


def test_hang_up_all_ends_every_dispatch_of_the_process_at_once(
    unit: Unit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C: every dispatch in flight is hung up on, and none is made after."""
    monkeypatch.setattr(runner_module, "_every", Hangup())  # this process's, reset
    unit.pieces = ["x"] * 400
    unit.pace_s = 0.02
    first, one = _in_thread(unit)
    second, two = _in_thread(unit)
    assert unit.seen_event("decoded")
    time.sleep(0.1)
    hang_up_all()
    first.join(timeout=5.0)
    second.join(timeout=5.0)
    assert isinstance(one.get("error"), HungUpError)
    assert isinstance(two.get("error"), HungUpError)
    assert unit.seen_event("hung up", count=2)
    assert unit.decoded() < 40, unit.decoded()
    with pytest.raises(HungUpError):
        _generate(unit)
    assert len(unit.seen) == 2


# -- anything but a 200 stream is read as before -----------------------------------


def test_a_unit_that_refuses_the_request_is_a_backend_error_with_its_body(
    unit: Unit,
) -> None:
    unit.status = 400
    unit.refused = b'{"error":{"code":400,"message":"bad request","type":"invalid"}}'
    with pytest.raises(BackendError, match="HTTP 400") as caught:
        _generate(unit)
    assert caught.value.status == 400
    assert "bad request" in str(caught.value)


def test_a_unit_that_answers_a_whole_json_body_is_read_as_it_comes(unit: Unit) -> None:
    """An engine that ignores ``stream`` answers whole; the answer is parsed as
    it comes, as PR #597's relay passes it through."""
    unit.whole_json = True
    done = _generate(unit)
    assert done.text == "Hello, world"
    assert done.output_tokens == 7
    assert unit.seen_event("answered")


def test_an_error_event_mid_stream_is_the_status_it_says(unit: Unit) -> None:
    unit.error = {"code": 503, "message": "slot unavailable", "type": "unavailable"}
    with pytest.raises(BackendError, match="HTTP 503") as caught:
        _generate(unit)
    assert caught.value.status == 503
    assert "slot unavailable" in str(caught.value)


def test_a_stream_that_ends_without_its_answer_is_a_transport_failure(
    unit: Unit,
) -> None:
    unit.pieces = ["x"] * 50
    unit.cut_after = 3
    with pytest.raises(TransportError, match="ended before its answer"):
        _generate(unit)
    assert unit.seen_event("died")


def test_a_stream_that_is_no_chat_completions_is_a_protocol_error(unit: Unit) -> None:
    """One event held longer than any of a chat completion's, its end not in
    sight: a server that speaks no stream."""
    unit.pieces = ["y" * (3 * MAX_EVENT_BYTES)]
    with pytest.raises(ProtocolError, match="not a chat completion"):
        _generate(unit)
