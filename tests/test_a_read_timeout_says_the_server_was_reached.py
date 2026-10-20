"""A read that times out says the server was reached, not that it could not be.

A hosted unit can take the request and still be writing its reply when the
120 s bound runs out, and the run used to report "could not reach
https://api.deepseek.com/... within 120s: The read operation timed out". The
server had been reached; it had not finished. The two failures ask for
different fixes — an address, a network or a key against a bound or a cap — so
the message names which one it was, and for a reply that ran out of time it
names the setting that bounded it.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.runner import Request, TransportError, runner_for


@contextlib.contextmanager
def silent() -> Iterator[str]:
    """A loopback server that reads each request and never answers it."""
    release = threading.Event()

    class _Silent(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            release.wait()
            self.close_connection = True

        def log_message(self, *_: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Silent)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _endpoint(base_url: str) -> Endpoint:
    return Endpoint(
        source="slow",
        base_url=base_url,
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def test_a_reply_that_runs_out_of_time_says_the_server_was_reached() -> None:
    with silent() as base_url, pytest.raises(TransportError) as raised:
        runner_for(_endpoint(base_url)).generate(
            "m", Request(prompt="hi", max_output_tokens=16, timeout_s=0.3)
        )
    said = str(raised.value)
    assert "could not reach" not in said, (
        f"the server took the request and the message says it could not be "
        f"reached: {said}"
    )
    assert "was reached" in said and "did not reply within 0.3s" in said, said
    assert "request_timeout_s" in said, (
        f"the message does not name the setting that bounded the reply: {said}"
    )


def test_an_address_that_cannot_be_reached_still_says_so() -> None:
    # Reserved for documentation (RFC 5737) and not routable.
    with pytest.raises(TransportError) as raised:
        runner_for(_endpoint("http://192.0.2.1:9")).generate(
            "m", Request(prompt="hi", max_output_tokens=16, timeout_s=0.25)
        )
    said = str(raised.value)
    assert "could not reach" in said and "within 0.25s" in said, said
    assert "was reached" not in said, said
