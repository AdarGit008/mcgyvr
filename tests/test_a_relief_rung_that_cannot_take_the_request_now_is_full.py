"""A relief rung that cannot take the request now is a full rung, not a failure.

The hub answers a request to a relief rung it cannot serve yet with ``503``
and the code ``hitchhike_not_served_yet``, one whose host went away with
``503`` and ``hitchhike_host_away``, and one to a rung it no longer matches
this rider to (a stale ``relief.yaml``) with ``404`` and ``model_not_found``.
None is a verdict on the work: nothing was asked of a model. So the dispatch
ends as :class:`~mcgyvr.capacity.SlotUnavailableError`, the one capacity error
a climb may route around — the driver turns it into a decline, which spends no
attempt and funds no escalation, and the climb goes on as if the rung had been
full.

A host that left is not waited for: the rung is asked once and passed over,
whatever the answer says of retrying.

Only those three answers, and only from a relief rung. Any other error status
from a relief rung is still the error it was, and either ``503`` body from a
unit of the rider's own ladder is that unit's error. (A ladder rung's ``404``
``model_not_found`` is passed over by its own rule, with a line in the log:
``tests/test_a_rung_whose_model_is_not_known_where_it_points_is_passed_over.py``.)

Every server here is a loopback one this test starts.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import parse
from mcgyvr.pool import source_map
from mcgyvr.runner import BackendError, Request, RunnerError, dispatch

RUNG_ID = "0f3c9a1e2b4d4c6f8a0b1c2d3e4f5a6b"
RIDE = f"hitchhike-{RUNG_ID}"
KEY = "mhu_" + "1" * 16


def error(status: int, code: str) -> tuple[int, bytes]:
    body = {
        "error": {
            "message": "the hub cannot serve this now",
            "type": "pool_unavailable",
            "code": code,
            "param": None,
        }
    }
    return status, json.dumps(body).encode()


NOT_SERVED_YET = error(503, "hitchhike_not_served_yet")
HOST_AWAY = error(503, "hitchhike_host_away")
STALE = error(404, "model_not_found")
UNAVAILABLE = [NOT_SERVED_YET, HOST_AWAY, STALE]
IDS = ["503", "503-host-away", "404"]


@contextlib.contextmanager
def answering(status: int, body: bytes, seen: list[dict[str, Any]]) -> Iterator[str]:
    """A loopback hub that answers every POST with ``status`` and ``body``."""

    class _Hub(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            seen.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "body": json.loads(self.rfile.read(length)),
                }
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Hub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


def setup(address: str) -> str:
    return f"""
units:
  local_fast:
    address: {address}
    model: qwen2.5-coder-3b
    width: 1
ladder: [local_fast]
fanout: idle
relief:
  {RIDE}:
    address: {address}
    model: hitchhike@{RUNG_ID}
    api_key_env: HUB_KEY
    width: 1
    position: within
"""


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", KEY)


def ask(address: str, rung: str, tmp_path: Path) -> tuple[Capacity, Any]:
    config = parse(setup(address))
    capacity = Capacity.of(config, root=tmp_path / "slots")
    request = Request(prompt="hello", max_output_tokens=8)
    try:
        return capacity, dispatch(source_map(config), rung, request, capacity=capacity)
    except Exception as exc:
        return capacity, exc


@pytest.mark.parametrize("answer", UNAVAILABLE, ids=IDS)
def test_a_relief_rung_that_cannot_take_it_now_is_a_full_rung(
    tmp_path: Path, answer: tuple[int, bytes]
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*answer, seen) as address:
        capacity, outcome = ask(address, RIDE, tmp_path)

    assert isinstance(outcome, SlotUnavailableError)
    # Not a runner error, so the cooldown does not learn the rung as failing.
    assert not isinstance(outcome, RunnerError)
    assert RIDE in str(outcome)
    assert capacity.load(RIDE) == 0, "the slot it held is given back"


def test_a_ride_whose_host_went_away_is_passed_over_without_a_retry(
    tmp_path: Path,
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*HOST_AWAY, seen) as address:
        capacity, outcome = ask(address, RIDE, tmp_path)

    assert isinstance(outcome, SlotUnavailableError)
    assert len(seen) == 1, "the rung was asked once and not again"
    assert "hitchhike_host_away" in str(outcome)
    assert capacity.load(RIDE) == 0


def test_a_ride_is_asked_with_the_hubs_model_and_the_personal_key(
    tmp_path: Path,
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*NOT_SERVED_YET, seen) as address:
        ask(address, RIDE, tmp_path)

    (request,) = seen
    assert request["path"] == "/v1/chat/completions"
    assert request["authorization"] == f"Bearer {KEY}"
    assert request["body"]["model"] == f"hitchhike@{RUNG_ID}"


@pytest.mark.parametrize(
    "answer",
    [error(503, "pool_unavailable"), error(401, "invalid_api_key"), (500, b"{}")],
    ids=["503-other", "401", "500"],
)
def test_any_other_error_from_a_relief_rung_is_still_that_error(
    tmp_path: Path, answer: tuple[int, bytes]
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*answer, seen) as address:
        _, outcome = ask(address, RIDE, tmp_path)

    assert isinstance(outcome, BackendError)
    assert not isinstance(outcome, SlotUnavailableError)


@pytest.mark.parametrize("answer", [NOT_SERVED_YET, HOST_AWAY], ids=IDS[:2])
def test_the_same_answer_from_a_rung_of_the_riders_own_ladder_is_its_error(
    tmp_path: Path, answer: tuple[int, bytes]
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*answer, seen) as address:
        _, outcome = ask(address, "local_fast", tmp_path)

    assert isinstance(outcome, BackendError)
    assert not isinstance(outcome, SlotUnavailableError)
