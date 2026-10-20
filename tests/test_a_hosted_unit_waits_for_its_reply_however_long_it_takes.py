"""A hosted unit waits for its reply however long it takes.

A hosted model with a large reply cap can take minutes to answer: a reasoning
model asked for 16k tokens can run for about 229 s, and the 120 s bound
every unit used to get by default ended that read, and with it the whole run, as an
`error`. The time a hosted reply takes is the provider's, and no number written
here knows it. So a unit with `api_key_env` and no `request_timeout_s` sends
its request with no bound on the reply at all.

What still fails fast is the connect: an address nothing answers at is refused
within :data:`mcgyvr.runner.HOSTED_CONNECT_TIMEOUT_S`, a bound on reaching the server
and never on its reply. A unit that states `request_timeout_s` keeps it, hosted
or local, and a local unit that states none keeps the bound it always had.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from mcgyvr import decision as decision_module
from mcgyvr import runner as runner_module
from mcgyvr.config import parse
from mcgyvr.decision import Noul, classify
from mcgyvr.local_pool import Endpoint, Protocol, source_map
from mcgyvr.runner import (
    GENERATE_TIMEOUT_S,
    Request,
    TransportError,
    dispatch,
    runner_for,
)

KEY_ENV = "MCGYVR_TEST_KEY"

HOSTED = Endpoint(
    source="hosted",
    base_url="https://api.example.invalid",
    protocol=Protocol.OPENAI,
    max_parallel=1,
    credential_env=KEY_ENV,
)

LOCAL = Endpoint(
    source="local",
    base_url="http://localhost:8081",
    protocol=Protocol.OPENAI,
    max_parallel=1,
    credential_env=None,
)

ASK = Request(prompt="p", max_output_tokens=8)


def _answer(text: str = "done") -> dict[str, Any]:
    return {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }


def _bounds(monkeypatch: pytest.MonkeyPatch) -> list[float | None]:
    """Stub the runner's transport; return the bound each dispatch was sent."""
    seen: list[float | None] = []

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: Any
    ) -> dict[str, Any]:
        seen.append(timeout)
        return _answer()

    monkeypatch.setattr(runner_module, "_post_json", fake_post, raising=True)
    return seen


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, "not-a-real-key")


# --- the bound each dispatch is sent ----------------------------------------


def test_a_hosted_unit_with_no_timeout_sends_no_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _bounds(monkeypatch)
    runner_for(HOSTED).generate("m", ASK)
    assert seen == [None], (
        f"a hosted unit that states no `request_timeout_s` was sent with a bound "
        f"of {seen[0]}s: a reply the provider takes longer than that to write "
        f"ends the run as an error"
    )


def test_a_hosted_unit_that_states_a_timeout_keeps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _bounds(monkeypatch)
    stated = dataclasses.replace(HOSTED, request_timeout_s=600.0)
    runner_for(stated).generate("m", ASK)
    assert seen == [600.0]


def test_a_request_that_states_a_timeout_keeps_it_on_any_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _bounds(monkeypatch)
    asked = Request(prompt="p", max_output_tokens=8, timeout_s=300.0)
    runner_for(HOSTED).generate("m", asked)
    runner_for(LOCAL).generate("m", asked)
    assert seen == [300.0, 300.0]


def test_a_local_unit_with_no_timeout_keeps_the_one_it_always_had(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _bounds(monkeypatch)
    runner_for(LOCAL).generate("m", ASK)
    assert seen == [GENERATE_TIMEOUT_S]


def test_a_hosted_unit_read_from_a_config_sends_no_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """From the config a `setup --api` writes, through the pool, to the wire."""
    config = parse(
        f"""\
units:
  api_deepseek:
    address: https://api.example.invalid
    model: deepseek-v4-pro
    api_key_env: {KEY_ENV}
    width: 1
ladder:
- api_deepseek
"""
    )
    seen = _bounds(monkeypatch)
    dispatch(source_map(config), "api_deepseek", ASK)
    assert seen == [None]


def test_a_typed_decision_on_a_hosted_unit_sends_no_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: Any
    ) -> dict[str, Any]:
        seen.append(timeout)
        top = [{"token": "Yes", "logprob": 0.0}, {"token": "No", "logprob": -1.0}]
        return {
            "choices": [
                {
                    "index": 0,
                    "logprobs": {"content": [{"token": "Yes", "top_logprobs": top}]},
                    "finish_reason": "length",
                }
            ]
        }

    monkeypatch.setattr(decision_module, "_post_json", fake_post)
    classify(HOSTED, "m", {}, {"q": Noul("is it?")})
    classify(LOCAL, "m", {}, {"q": Noul("is it?")})
    assert seen == [None, GENERATE_TIMEOUT_S]


# --- over a socket ----------------------------------------------------------


@contextlib.contextmanager
def answering_after(delay_s: float) -> Iterator[str]:
    """A loopback server that holds each request ``delay_s`` before answering."""

    class _Slow(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            time.sleep(delay_s)
            body = json.dumps(_answer("slow but whole")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Slow)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_connect_bound_does_not_bound_the_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reply slower than the connect bound still arrives: the bound on
    reaching the server is lifted once the request is sent."""
    monkeypatch.setattr(runner_module, "HOSTED_CONNECT_TIMEOUT_S", 0.2)
    with answering_after(0.8) as base_url:
        hosted = dataclasses.replace(HOSTED, base_url=base_url)
        done = runner_for(hosted).generate("m", ASK)
    assert done.text == "slow but whole"


def test_an_address_nothing_answers_at_still_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No bound on the reply is not no bound on the connect."""
    monkeypatch.setattr(runner_module, "HOSTED_CONNECT_TIMEOUT_S", 0.25)
    # Reserved for documentation (RFC 5737) and not routable.
    unroutable = dataclasses.replace(HOSTED, base_url="http://192.0.2.1:9")
    started = time.monotonic()
    with pytest.raises(TransportError, match="could not reach"):
        runner_for(unroutable).generate("m", ASK)
    assert time.monotonic() - started < 5.0
