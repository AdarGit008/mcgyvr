"""A rig syncing its rungs, and what it reports back."""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from tests._paths import TESTS

HANDLE = "bob"


KEY = "mhu_0123456789abcdef_" + "k" * 40


TOKEN = "mhr_0123456789abcdef_" + "t" * 43


FIRST = "0f3c9a1e2b4d4c6f8a0b1c2d3e4f5a6b"


SECOND = "1a2b3c4d5e6f708192a3b4c5d6e7f809"


PRIVACY = (
    "Riding sends your prompts to other people's machines: the host of each "
    "rung runs the model on hardware they control and can read your prompts "
    "and the answers. Ride only with prompts you would show them."
)


FLEET = """\
# what runs where
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    width: 1
"""


POLICY = """\
# my own ladder, commented by hand
ladder: [local_fast]
fanout: idle
"""


def rung(
    rung_id: str, address: str, *, position: str = "below_floor"
) -> dict[str, Any]:
    return {
        "id": rung_id,
        "host": HANDLE,
        "address": address,
        "model": f"hitchhike@{rung_id}",
        "served_model": "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf",
        "width": 2,
        "relief": True,
        "position": position,
        "price": {
            "currency": "credits",
            "per_tokens": 1000,
            "input": "0.5",
            "output": "1",
        },
    }


class Hub:
    """What the loopback hub answers, and what it was asked."""

    def __init__(self) -> None:
        self.status = 200
        self.body: bytes = b""
        self.asked: list[dict[str, Any]] = []
        self.address = ""

    def answer(self, document: object, status: int = 200) -> None:
        self.status = status
        self.body = json.dumps(document).encode()

    def listing(self, *rung_ids: str, ride: bool = True) -> dict[str, Any]:
        return {
            "ride": ride,
            "privacy": PRIVACY,
            "refresh_s": 60,
            "rungs": [rung(i, f"{self.address}/v1") for i in rung_ids],
        }


@contextlib.contextmanager
def serving(hub: Hub) -> Iterator[Hub]:
    class _Hub(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            hub.asked.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "content_type": self.headers.get("Content-Type"),
                    "body": self.rfile.read(length),
                }
            )
            self.send_response(hub.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(hub.body)))
            self.end_headers()
            self.wfile.write(hub.body)

        def log_message(self, *_: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Hub)
    hub.address = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield hub
    finally:
        server.shutdown()
        server.server_close()


def a_syncing_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "setup"
    folder.mkdir()
    (folder / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (folder / "policy.yaml").write_text(POLICY, encoding="utf-8")
    monkeypatch.setenv("MCGYVR_CONFIG", str(folder))
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "config-folder"))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data-folder"))
    monkeypatch.setenv("MCGYVR_HUB_API_KEY", KEY)
    return folder


@contextlib.contextmanager
def a_syncing_hub(setup: Path) -> Iterator[Hub]:
    from mcgyvr.rig import credentials

    with serving(Hub()) as running:
        credentials.save(credentials.Credentials(hub=running.address, token=TOKEN))
        yield running


def cli(*argv: str) -> int:
    from mcgyvr.cli import main

    return main(["rig", "rungs", "sync", *argv])


FIXTURE = TESTS / "fixtures" / "gguf_geometry.json"


SCANNED = "4b-Q4_K_M.gguf"


REPORTING_FLEET = """\
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    width: 1
    launch:
      geometry_json: geometry.json
  local_big:
    address: http://big-box.example:8001
    model: "qwen2.5-coder:7b"
    width: 1
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    width: 1
    api_key_env: EXAMPLE_API_KEY
"""


def policy(ladder: str, escalations: int) -> str:
    return f"ladder: [{ladder}]\nfanout: idle\nmax_escalations: {escalations}\n"


def a_reporting_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "setup"
    folder.mkdir()
    (folder / "fleet.yaml").write_text(REPORTING_FLEET, encoding="utf-8")
    (folder / "policy.yaml").write_text(
        policy("local_fast, local_big, api_big", 1), encoding="utf-8"
    )
    row = json.loads(FIXTURE.read_text(encoding="utf-8"))[SCANNED]
    (folder / "geometry.json").write_text(json.dumps(row), encoding="utf-8")
    monkeypatch.setenv("MCGYVR_CONFIG", str(folder))
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "config-folder"))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data-folder"))
    monkeypatch.setenv("MCGYVR_HUB_API_KEY", KEY)
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "e" * 24)
    return folder


@contextlib.contextmanager
def a_reporting_hub(setup: Path) -> Any:
    from mcgyvr.rig import credentials

    with serving(Hub()) as running:
        credentials.save(credentials.Credentials(hub=running.address, token=TOKEN))
        running.answer(running.listing(FIRST))
        yield running


def sent(hub: Hub) -> dict[str, Any]:
    (asked,) = hub.asked[-1:]
    assert asked["content_type"] == "application/json"
    body: dict[str, Any] = json.loads(asked["body"])
    return body
