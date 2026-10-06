"""The facade hangs up on the rung when its client has gone.

A harness that closes its connection mid-turn (Ctrl-C, a closed session) has
no further use for the answer, and a unit that goes on decoding it decodes for
nobody. So the facade runs each turn under a :class:`~mcgyvr.runner.Hangup`
and looks for its client's leave at every ping interval: a connection the
client closed hangs up on the rung's dispatch, so the unit's next write fails
and it stops, and nothing is written back. What is held here, on both the
message and the streamed path, against a real loopback unit reached through
the real runner:

* a client that closes mid-turn is noticed within a ping interval or two, the
  unit sees the hang-up a token or two later, never answers, and no traceback
  reaches stderr; the server goes on serving the next request;
* a client that stays gets its answer as before;
* a client with bytes of its next request already sent (a pipelining client)
  has not gone, and is answered.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, BinaryIO

import pytest

from mcgyvr.mcorch import serve
from mcgyvr.mcorch.anthropic import MessagesRequest
from mcgyvr.mcorch.loop import Turn
from mcgyvr.runner import HungUpError, Request, runner_for
from tests.mcorch_fakes import text
from tests.test_mcorch_serves_the_messages_api_at_a_local_address import TRACE
from tests.test_the_runner_streams_from_every_unit_and_hangs_up_when_the_asker_has_gone import (  # noqa: E501
    MODEL,
    Unit,
    _serve,
)

#: A turn long enough that only a hang-up ends it early: 400 pieces at 0.02 s.
LONG = ["x"] * 400
PACE_S = 0.02

#: The runner's own deadline, well past the long turn, so no timeout ends it.
ASK = Request(prompt="hi", max_output_tokens=500, timeout_s=30.0)


@dataclass
class _Rung:
    """A stand-in for the loop that asks the unit through the real runner and
    keeps what each turn ended as."""

    unit: Unit
    ended: list[Any] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __call__(self, request: MessagesRequest) -> Turn:
        try:
            done = runner_for(self.unit.endpoint).generate(MODEL, ASK)
        except Exception as exc:
            with self.lock:
                self.ended.append(exc)
            raise
        with self.lock:
            self.ended.append(done.text)
        return Turn(reply=text(done.text), trace=TRACE)

    def ended_as(self, timeout: float = 5.0) -> list[Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if self.ended:
                    return list(self.ended)
            time.sleep(0.005)
        return list(self.ended)


@pytest.fixture
def unit() -> Iterator[Unit]:
    built = Unit()
    built.server = _serve(built)
    yield built
    built.server.shutdown()
    built.server.server_close()


@pytest.fixture
def facade(unit: Unit) -> Iterator[tuple[int, _Rung]]:
    rung = _Rung(unit)
    server = serve.make_server(
        serve.Facade(respond=rung, ping_interval_s=0.05), bind="127.0.0.1", port=0
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield int(server.server_address[1]), rung
    finally:
        server.shutdown()
        server.server_close()


def _body(**fields: object) -> bytes:
    base: dict[str, object] = {
        "model": "claude-sonnet-x",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "hi"}],
    }
    base.update(fields)
    return json.dumps(base).encode("utf-8")


def _raw(method: str, path: str, body: bytes = b"") -> bytes:
    head = (
        f"{method} {path} HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/json\r\n"
        "anthropic-version: 2023-06-01\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    )
    return head.encode("ascii") + body


def _read_response(reader: BinaryIO) -> tuple[int, bytes]:
    """One response with a ``Content-Length``, read off a shared reader."""
    status = int(reader.readline().split()[1])
    length = 0
    while (line := reader.readline()) not in (b"\r\n", b"\n", b""):
        name, _, value = line.decode("latin-1").partition(":")
        if name.strip().lower() == "content-length":
            length = int(value.strip())
    return status, reader.read(length)


def _ask(port: int, **fields: object) -> http.client.HTTPResponse:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10.0)
    connection.request(
        "POST",
        "/v1/messages",
        body=_body(**fields),
        headers={"Content-Type": "application/json"},
    )
    return connection.getresponse()


def _leave_mid_turn(port: int, unit: Unit, *, stream: bool) -> None:
    """Ask for a long turn, then close the connection a few tokens in."""
    unit.pieces = list(LONG)
    unit.pace_s = PACE_S
    client = socket.create_connection(("127.0.0.1", port), timeout=5.0)
    client.sendall(_raw("POST", "/v1/messages", _body(stream=stream)))
    assert unit.seen_event("decoded")
    if stream:
        assert client.recv(4096).startswith(b"HTTP/1.1 200")  # headers, a ping
    time.sleep(0.1)
    client.close()


def _the_unit_stopped_and_nothing_was_said(
    port: int, unit: Unit, rung: _Rung, capfd: pytest.CaptureFixture[str]
) -> None:
    assert unit.seen_event("hung up", timeout=1.5)
    decoded = unit.decoded()
    assert decoded < 20, decoded  # a token or two past the leave, not the answer
    assert "answered" not in unit.events
    (ended,) = rung.ended_as()
    assert isinstance(ended, HungUpError)
    # The server goes on serving: the next request is answered.
    unit.pieces = ["Hello", ",", " world"]
    unit.pace_s = 0.0
    again = _ask(port)
    assert again.status == 200
    assert json.loads(again.read())["content"] == [
        {"type": "text", "text": "Hello, world"}
    ]
    assert "Traceback" not in capfd.readouterr().err


def test_a_message_client_that_leaves_mid_turn_is_hung_up_on(
    facade: tuple[int, _Rung], unit: Unit, capfd: pytest.CaptureFixture[str]
) -> None:
    port, rung = facade
    _leave_mid_turn(port, unit, stream=False)
    _the_unit_stopped_and_nothing_was_said(port, unit, rung, capfd)


def test_a_streaming_client_that_leaves_mid_turn_is_hung_up_on(
    facade: tuple[int, _Rung], unit: Unit, capfd: pytest.CaptureFixture[str]
) -> None:
    port, rung = facade
    _leave_mid_turn(port, unit, stream=True)
    _the_unit_stopped_and_nothing_was_said(port, unit, rung, capfd)


def test_a_client_that_stays_is_answered_on_both_paths(
    facade: tuple[int, _Rung], unit: Unit
) -> None:
    port, _ = facade
    unit.pieces = ["x"] * 10
    unit.pace_s = PACE_S  # a few ping intervals, each one looking for a leave
    message = _ask(port)
    assert message.status == 200
    assert json.loads(message.read())["content"] == [{"type": "text", "text": "x" * 10}]
    streamed = _ask(port, stream=True)
    assert streamed.status == 200
    raw = streamed.read().decode("utf-8")
    assert "event: ping" in raw
    assert '"text": "xxxxxxxxxx"' in raw
    assert raw.rstrip().endswith('data: {"type": "message_stop"}')
    assert unit.seen_event("answered", count=2)  # noted just after its last write


def test_a_client_that_has_sent_its_next_request_has_not_gone(
    facade: tuple[int, _Rung], unit: Unit
) -> None:
    """Bytes waiting on the connection are a pipelining client, not a leave."""
    port, rung = facade
    unit.pieces = ["x"] * 20
    unit.pace_s = PACE_S
    client = socket.create_connection(("127.0.0.1", port), timeout=5.0)
    try:
        client.sendall(_raw("POST", "/v1/messages", _body()))
        assert unit.seen_event("decoded")
        client.sendall(_raw("GET", "/v1/models"))  # the next one, sent early
        reader = client.makefile("rb")
        status, body = _read_response(reader)
        assert status == 200
        assert json.loads(body)["content"] == [{"type": "text", "text": "x" * 20}]
        status, body = _read_response(reader)
        assert status == 200
        assert json.loads(body)["data"][0]["id"] == serve.MODEL_ID
    finally:
        client.close()
    assert "hung up" not in unit.events
    assert rung.ended == ["x" * 20]
