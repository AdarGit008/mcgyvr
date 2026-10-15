"""A rung that takes an answer, and the room its replies need."""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capacity import Capacity
from mcgyvr.config import parse
from mcgyvr.local_pool import Protocol, source_map
from mcgyvr.runner import Completion, Request, dispatch

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


POOLED = "pooled-coder-14b"


OTHER = "another-coder-32b"


def answer(model: str, text: str) -> tuple[int, bytes]:
    body = {
        "model": model,
        "choices": [
            {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7},
    }
    return 200, json.dumps(body).encode()


@contextlib.contextmanager
def answering_unplaced(status: int, body: bytes, seen: list[str]) -> Iterator[str]:
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
    window: 32768
  other:
    address: {other}
    model: {OTHER}
    api_key_env: HUB_KEY
    width: 1
    window: 32768
ladder: [pooled, other]
"""


CONTRACT = """
id: impl
task_type: code
task: Set VALUE to 1.
target: src/pkg/value.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/value.py'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


#: A model-executed contract whose own cap is the 1024 the live rows were
#: written under, declared rather than derived so the number is the operator's.
ROOM_CONTRACT = """
id: impl
task_type: code
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  max_output_tokens: 1024
"""


#: The same contract as an uncapped raw-text reply: no declared cap, and a
#: context ceiling small enough to sit inside the tiny window the preflight
#: check uses to prove a prose reply is not refused for its (absent) reserve.
PROSE_CONTRACT = (
    ROOM_CONTRACT.replace("limits:\n  max_output_tokens: 1024\n", "")
    + "context:\n  max_input_tokens: 64\n"
    + "output_schema: prose\n"
)


def caps_sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int | None]]:
    """Record the rung and the cap of every request the driver dispatches.

    The substitution is the seam the whole project is built on:
    ``mcgyvr.runner.dispatch`` takes a rung name and a source map, so nothing
    above it knows a socket exists. What is asserted is the number on the
    request, which is the number the backend is actually given.
    """
    from mcgyvr import drive
    from mcgyvr.runner import Completion, StopReason

    seen: list[tuple[str, int | None]] = []

    def fake_dispatch(
        source_map: Any, rung: str, request: Any, *, capacity: Any = None
    ) -> Completion:
        seen.append((rung, request.max_output_tokens))
        return Completion(
            text="```python\nx = 1\n```",
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="qwen2.5-coder:3b",
            source="box1",
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return seen


SERVED = "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"


PROMPT = "the rider's private prompt"


def completion(model: str | None) -> bytes:
    body: dict[str, Any] = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }
    if model is not None:
        body["model"] = model
    return json.dumps(body).encode()


def set_hub_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", "mhu_" + "1" * 16)


def ride(answer: bytes, tmp_path: Path) -> Any:
    seen: list[dict[str, Any]] = []
    with answering(200, answer, seen) as address:
        config = parse(
            f"""
units:
  local_fast:
    address: {address}
    model: qwen2.5-coder-3b
    width: 1
    window: 32768
ladder: [local_fast]
fanout: idle
relief:
  {RIDE}:
    address: {address}
    model: hitchhike@{RUNG_ID}
    api_key_env: HUB_KEY
    width: 1
    position: within
    served_model: {SERVED}
"""
        )
        capacity = Capacity.of(config, root=tmp_path / "slots")
        try:
            return dispatch(
                source_map(config),
                RIDE,
                Request(prompt=PROMPT, max_output_tokens=8),
                capacity=capacity,
            )
        except Exception as exc:
            return exc
