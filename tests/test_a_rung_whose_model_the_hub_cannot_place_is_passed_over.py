"""A rung whose model the hub cannot place is passed over, not failed.

A hub that holds a request for a pooled model ends the hold with ``503`` and
the code ``model_unplaced``, and no ``Retry-After``, once nothing can serve
it: the rig that held the model is gone for good. Nothing was asked of a
model, and the requester is not pinned to that one, so the answer is not the
task's error and not a reason to ask again: the dispatch ends as
:class:`~mcgyvr.capacity.SlotUnavailableError`, the driver turns it into a
decline, and the climb tries the next rung at once, another model's included.
It spends no attempt and the cooldown does not learn the rung as failing.

Only that answer. Any other ``503`` is still the rung's error. (A ``404``
``model_not_found`` is passed over too, with a line in the log:
``tests/test_a_rung_whose_model_is_not_known_where_it_points_is_passed_over.py``.)

Every server here is a loopback one this test starts.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import parse
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import worker_attempt
from mcgyvr.escalate import Delivered, escalate
from mcgyvr.pool import source_map
from mcgyvr.route import Verdict
from mcgyvr.runner import BackendError, Request, RunnerError, dispatch
from mcgyvr.sandbox.tempdir import TempDirSandbox

KEY = "mhu_" + "1" * 16
POOLED = "pooled-coder-14b"
OTHER = "another-coder-32b"


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


def answer(model: str, text: str) -> tuple[int, bytes]:
    body = {
        "model": model,
        "choices": [
            {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7},
    }
    return 200, json.dumps(body).encode()


UNPLACED = error(503, "model_unplaced")


@contextlib.contextmanager
def answering(status: int, body: bytes, seen: list[str]) -> Iterator[str]:
    """A loopback server that answers every POST with ``status`` and ``body``."""

    class _Server(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            seen.append(json.loads(self.rfile.read(length))["model"])
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Server)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


def setup(hub: str, other: str) -> str:
    return f"""
units:
  pooled:
    address: {hub}
    model: {POOLED}
    api_key_env: HUB_KEY
    width: 1
  other:
    address: {other}
    model: {OTHER}
    api_key_env: HUB_KEY
    width: 1
ladder: [pooled, other]
"""


CONTRACT = """
id: impl
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/value.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/value.py'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", KEY)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "value.py").write_text("VALUE = 0\n", encoding="utf-8")
    for args in (
        ("init", "-q"),
        ("add", "-A"),
        (
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-qm",
            "base",
        ),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def ask(hub: str, tmp_path: Path) -> tuple[Capacity, Any]:
    config = parse(setup(hub, hub))
    capacity = Capacity.of(config, root=tmp_path / "slots")
    request = Request(prompt="hello", max_output_tokens=8)
    try:
        return capacity, dispatch(
            source_map(config), "pooled", request, capacity=capacity
        )
    except Exception as exc:
        return capacity, exc


def test_a_model_the_hub_cannot_place_is_a_full_rung_asked_once(
    tmp_path: Path,
) -> None:
    seen: list[str] = []
    with answering(*UNPLACED, seen) as hub:
        capacity, outcome = ask(hub, tmp_path)

    assert isinstance(outcome, SlotUnavailableError)
    # Not a runner error, so the cooldown does not learn the rung as failing.
    assert not isinstance(outcome, RunnerError)
    assert "pooled" in str(outcome) and "model_unplaced" in str(outcome)
    assert seen == [POOLED], "the rung was asked once and not again"
    assert capacity.load("pooled") == 0, "the slot it held is given back"


@pytest.mark.parametrize(
    "refusal",
    [error(503, "pool_unavailable"), error(404, "not_found"), (503, b"{}")],
    ids=["503-other", "404-other", "503-no-code"],
)
def test_any_other_error_is_still_the_rungs_error(
    tmp_path: Path, refusal: tuple[int, bytes]
) -> None:
    seen: list[str] = []
    with answering(*refusal, seen) as hub:
        _, outcome = ask(hub, tmp_path)

    assert isinstance(outcome, BackendError)
    assert not isinstance(outcome, SlotUnavailableError)


def test_the_climb_tries_the_next_rung_at_once(repo: Path) -> None:
    """The whole way: the pooled rung is unplaced, another model's rung answers."""
    asked_hub: list[str] = []
    asked_other: list[str] = []
    good = answer(OTHER, "```python\nVALUE = 1\n```")
    with (
        answering(*UNPLACED, asked_hub) as hub,
        answering(*good, asked_other) as other,
    ):
        config = parse(setup(hub, other))
        pool = source_map(config)
        contract = load_contract(CONTRACT)
        with TempDirSandbox(repo) as sandbox:
            outcome = escalate(
                config, pool, contract, worker_attempt(config, pool, contract, sandbox)
            )

    assert isinstance(outcome, Delivered), outcome
    assert outcome.rung == "other"
    assert asked_hub == [POOLED], "the unplaced rung was asked once"
    assert asked_other == [OTHER]
    assert [(a.rung, a.verdict) for a in outcome.history] == [
        ("pooled", Verdict.DECLINED),
        ("other", Verdict.PASSED),
    ]
    assert (outcome.attempts_spent, outcome.escalations) == (1, 0)
