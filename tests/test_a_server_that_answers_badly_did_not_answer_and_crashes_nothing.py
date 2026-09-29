"""A server that answers badly is a server that did not answer properly.

The promise: a server that answers badly — a body that ends before the length
it stated, a status line that is not one, a connection closed before any byte,
a reply that is not JSON, a reply nested deeper than the JSON reader follows —
is reported as a server that did not answer properly, never as a crash.

Two readers make that promise here:

* :mod:`mcgyvr.detect`, whose sweep asks every conventional port of a host what
  it serves. One misbehaving server on a swept port must not end the sweep; it
  is "nothing usable is listening" (``None``), like a refused port. A reply
  that is JSON of another shape than a model listing (a list, a number, an
  object with no list of models) is not a server that failed to answer: it
  answered at the address asked, so it is a backend that names no model. That
  is the difference :mod:`mcgyvr.initialize` and :mod:`mcgyvr.propose` act on:
  a reachable backend that names no model is a place a model may be pulled
  onto, and nothing listening is not. (JSON ``null`` alone reads as nothing
  listening, because the reader's ``None`` stands for both.)
* :mod:`mcgyvr.fleet.harness`, which measures a unit at its address. Its model
  list and its requests fail as :class:`~mcgyvr.fleet.harness.HarnessError`
  naming the address, and so does a measurement given JSON of another shape,
  which is not the answer it asked for. The error quotes a bounded part of
  what the server sent. Its status pages read as ``None`` (a page that could
  not be read), the way an unreachable page already does.

Every bad reply comes from a one-shot server on the loopback address, started
inside the test on a port the kernel picks. It reads one request, its headers
and its body, sends its bytes at once, and closes. No sleep is used, and no
timeout decides an outcome: a bad reply read too slowly is a timeout, which is
the same outcome, and the one reply that must arrive whole is given a generous
timeout.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from mcgyvr import detect
from mcgyvr.fleet import harness

#: Short: every reply below is sent and closed at once, so nothing waits on it.
TIMEOUT_S = 0.5
#: For the one reply that must arrive whole, so a loaded machine cannot turn a
#: good answer into a timeout.
GENEROUS_TIMEOUT_S = 30.0

_JSON_HEAD = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"


def _reply(body: bytes, *, stated: int | None = None) -> bytes:
    """A 200 whose headers state ``stated`` bytes (the body's own length if None)."""
    length = len(body) if stated is None else stated
    return _JSON_HEAD + f"Content-Length: {length}\r\n\r\n".encode() + body


#: The bad replies, by what is wrong with them. ``b""`` is a close before any byte.
CUT_SHORT = _reply(b'{"data": [{"id": "invented', stated=4096)
NOT_A_STATUS_LINE = b"THIS IS NOT A STATUS LINE\r\n\r\n"
CLOSED_BEFORE_ANY_BYTE = b""
NOT_JSON = _reply(b"<html>a page, not a document</html>")
JSON_OF_ANOTHER_SHAPE = _reply(
    json.dumps(["a", "list", "not", "a", "listing"]).encode()
)
#: Deeper than the JSON reader follows on every supported Python. The reader
#: gives up with ``RecursionError`` somewhere between a thousand and fifty
#: thousand levels, by interpreter version; four times the deepest of those is
#: still a body of a few hundred kilobytes, read in milliseconds. The test
#: below checks that this depth does cross the limit of the Python running it.
NESTING_DEPTH = 200_000
DEEPLY_NESTED_BODY = b"[" * NESTING_DEPTH + b"]" * NESTING_DEPTH
DEEPLY_NESTED = _reply(DEEPLY_NESTED_BODY)
#: A status line tens of kilobytes long, under the length the HTTP client
#: refuses outright, so it is quoted back in the error it raises.
LONG_BAD_STATUS_LINE = b"NOT A STATUS " + b"x" * 60_000 + b"\r\n\r\n"

#: Replies that can never be read as JSON, whatever the reader wanted from them.
UNREADABLE = {
    "a body that ends before its stated length": CUT_SHORT,
    "a status line that is not one": NOT_A_STATUS_LINE,
    "a connection closed before any byte": CLOSED_BEFORE_ANY_BYTE,
    "a reply that is not JSON": NOT_JSON,
    "a reply nested deeper than the JSON reader follows": DEEPLY_NESTED,
}
EVERY_BAD_REPLY = {
    **UNREADABLE,
    "a reply that is JSON of another shape": (JSON_OF_ANOTHER_SHAPE),
}


@pytest.fixture(autouse=True)
def _no_proxy_between(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reply under test comes from the loopback server, not a proxy."""
    for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)


def _stated_length(head: bytes) -> int:
    """The Content-Length a request's headers state, 0 when they state none."""
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            return int(value.strip())
    return 0


@contextmanager
def answering(reply: bytes) -> Iterator[str]:
    """``http://127.0.0.1:<port>``, where one request is answered with ``reply``."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5.0)
    port = listener.getsockname()[1]

    def serve() -> None:
        try:
            connection, _ = listener.accept()
        except OSError:
            return
        with connection:
            connection.settimeout(5.0)
            received = b""
            try:
                while b"\r\n\r\n" not in received:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    received += chunk
                head, _, body = received.partition(b"\r\n\r\n")
                stated = _stated_length(head)
                while len(body) < stated:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    body += chunk
                if reply:
                    connection.sendall(reply)
            except OSError:
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        listener.close()
        thread.join(timeout=5.0)


# --- detect: a swept port that answers badly is nothing usable listening ----


@pytest.mark.parametrize("reply", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_detect_reads_a_bad_reply_as_nothing_listening(reply: bytes) -> None:
    with answering(reply) as base:
        assert detect._get_json(f"{base}/v1/models", TIMEOUT_S) is None


@pytest.mark.parametrize("reply", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_a_probe_of_a_bad_reply_finds_no_backend(reply: bytes) -> None:
    with answering(reply) as base:
        target = detect.ProbeTarget("invented", base, "openai", host="127.0.0.1")
        assert detect.probe(target, TIMEOUT_S) is None


def test_the_nesting_crosses_the_json_readers_limit_here() -> None:
    """The deeply nested reply is a real case on the Python running this."""
    with pytest.raises(RecursionError):
        json.loads(DEEPLY_NESTED_BODY)


#: JSON that answers, but is not a model listing.
OTHER_SHAPES = {
    "a list": ["a", "list", "not", "a", "listing"],
    "a number": 7,
    "an object whose data is not a list": {"data": None},
    "an object with no data": {"object": "list"},
}


@pytest.mark.parametrize("payload", OTHER_SHAPES.values(), ids=OTHER_SHAPES.keys())
def test_a_listing_of_another_shape_is_a_backend_that_names_no_model(
    payload: object,
) -> None:
    """It answered at the address asked, so it is a backend, with no model."""
    with answering(_reply(json.dumps(payload).encode())) as base:
        target = detect.ProbeTarget("invented", base, "openai", host="127.0.0.1")
        found = detect.probe(target, GENEROUS_TIMEOUT_S)
    assert found is not None
    assert (found.base_url, found.models) == (base, ())


def test_one_bad_server_in_a_sweep_does_not_end_the_sweep() -> None:
    """A sweep over a good server and a cut-short one keeps the good one."""
    listing = json.dumps({"data": [{"id": "invented-model"}]}).encode()
    with answering(_reply(listing)) as good, answering(CUT_SHORT) as bad:
        targets = (
            detect.ProbeTarget("good", good, "openai", host="127.0.0.1"),
            detect.ProbeTarget("bad", bad, "openai", host="127.0.0.1"),
        )
        found = detect.probe_all(targets, GENEROUS_TIMEOUT_S)
    assert [(b.name, b.models) for b in found] == [("good", ("invented-model",))]


# --- harness: a unit that answers badly is a measurement not taken ---------


@pytest.mark.parametrize("reply", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_the_harness_model_list_fails_as_a_harness_error_naming_the_address(
    reply: bytes,
) -> None:
    with answering(reply) as base:
        url = f"{base}/v1/models"
        with pytest.raises(harness.HarnessError) as raised:
            harness.HttpTransport().get(url, TIMEOUT_S)
    assert url in str(raised.value)


def test_a_harness_error_quotes_a_bounded_part_of_what_the_server_sent() -> None:
    """A status line of any length makes an error of bounded length."""
    with answering(LONG_BAD_STATUS_LINE) as base:
        url = f"{base}/v1/models"
        with pytest.raises(harness.HarnessError) as raised:
            harness.HttpTransport().get(url, TIMEOUT_S)
    said = str(raised.value)
    assert url in said
    assert len(said) <= len(url) + harness.REPLY_QUOTED_AT_MOST + 100


@pytest.mark.parametrize("reply", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_a_harness_request_fails_as_a_harness_error_naming_the_address(
    reply: bytes,
) -> None:
    with answering(reply) as base:
        url = f"{base}/completion"
        with pytest.raises(harness.HarnessError) as raised:
            harness.HttpTransport().post(url, {"prompt": "x"}, TIMEOUT_S)
    assert url in str(raised.value)


@pytest.mark.parametrize("reply", EVERY_BAD_REPLY.values(), ids=EVERY_BAD_REPLY.keys())
def test_a_measurement_of_a_unit_that_answers_badly_is_a_harness_error(
    reply: bytes,
) -> None:
    with answering(reply) as base, pytest.raises(harness.HarnessError) as raised:
        harness.measure_vllm(base, harness.HttpTransport(), lambda: 0.0)
    assert base in str(raised.value)


@pytest.mark.parametrize("reply", EVERY_BAD_REPLY.values(), ids=EVERY_BAD_REPLY.keys())
def test_a_status_page_that_answers_badly_is_a_page_not_read(reply: bytes) -> None:
    with answering(reply) as base:
        page = harness._page(f"{base}/slots")
    assert harness.slots_in_flight(page) is None


@pytest.mark.parametrize("reply", EVERY_BAD_REPLY.values(), ids=EVERY_BAD_REPLY.keys())
def test_a_load_status_page_that_answers_badly_is_a_page_not_read(
    reply: bytes,
) -> None:
    with answering(reply) as base:
        page = harness._unbounded_page(f"{base}/slots")
    assert harness.slots_in_flight(page) is None


@pytest.mark.parametrize("reply", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_the_rig_side_harness_answers_one_error_line_not_a_traceback(
    reply: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    """``python3 - mcgyvr-harness SPEC`` prints one JSON line, always."""
    with answering(reply) as base:
        port = int(base.rsplit(":", 1)[1])
        spec = json.dumps({"engine": "vllm", "port": port})
        code = harness.main(["-", harness.HARNESS_WORD, spec])
    answer = json.loads(capsys.readouterr().out.strip())
    assert code == 1
    assert "error" in answer
