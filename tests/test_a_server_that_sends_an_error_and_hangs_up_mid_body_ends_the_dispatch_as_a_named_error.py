"""A server that sends an error and hangs up mid-body ends as a named error.

A model server that fails can fail twice in one reply: it sends an error
status, starts a body, and closes the connection before the body is all there.
The dispatch must end as the runner's own error for an error status, saying
which status came back, that the body ended before it was complete, and the
part of the body the HTTP library kept. When that part is empty it must not
claim the body was empty: bytes may have arrived and been dropped, as the
library drops a chunk that was cut off. It must never end as a raw exception
from the HTTP library: the callers that catch the runner's errors would miss
it, and the failure would not be recorded as a runner failure.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.runner import BackendError, Request, runner_for

STATUS = 500
HEAD = f"HTTP/1.1 {STATUS} Internal Server Error\r\n".encode()
#: What the server sends of its error body before it hangs up.
SENT = b'{"error": "the model ran out of'
#: A body promised longer than what is sent.
CUT_BY_LENGTH = HEAD + b"Content-Length: %d\r\n\r\n" % (len(SENT) + 64) + SENT
#: A chunked body: one whole chunk, then a chunk cut off partway.
CUT_AFTER_A_CHUNK = (
    HEAD
    + b"Transfer-Encoding: chunked\r\n\r\n"
    + b"5\r\nfirst\r\n"
    + b"40\r\nsecond chunk, partly sent"
)
#: A chunked body whose first chunk is cut off partway.
CUT_IN_THE_FIRST_CHUNK = (
    HEAD + b"Transfer-Encoding: chunked\r\n\r\n" + b"40\r\nfirst chunk, partly sent"
)


@contextlib.contextmanager
def replying(raw: bytes) -> Iterator[str]:
    """A loopback server that answers a POST with ``raw`` and hangs up."""

    class _Reply(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.wfile.write(raw)
            self.wfile.flush()
            self.close_connection = True

        def log_message(self, *_: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Reply)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _dispatch_error(raw: bytes) -> str:
    with replying(raw) as base_url:
        endpoint = Endpoint(
            source="local",
            base_url=base_url,
            protocol=Protocol.OPENAI,
            max_parallel=1,
            credential_env=None,
        )
        with pytest.raises(BackendError) as raised:
            runner_for(endpoint).generate(
                "m", Request(prompt="hi", max_output_tokens=16)
            )
    return str(raised.value)


def test_an_error_status_cut_short_is_a_backend_error_that_says_what_happened() -> None:
    message = _dispatch_error(CUT_BY_LENGTH)
    assert f"HTTP {STATUS}" in message
    assert "ended before it was complete" in message
    assert SENT.decode() in message


def test_a_chunked_error_body_cut_short_shows_the_part_that_was_kept() -> None:
    message = _dispatch_error(CUT_AFTER_A_CHUNK)
    assert f"HTTP {STATUS}" in message
    assert "ended before it was complete" in message
    assert "first" in message
    assert "empty body" not in message


def test_an_error_body_cut_short_with_nothing_kept_is_not_called_empty() -> None:
    message = _dispatch_error(CUT_IN_THE_FIRST_CHUNK)
    assert f"HTTP {STATUS}" in message
    assert "ended before it was complete" in message
    assert "empty body" not in message
