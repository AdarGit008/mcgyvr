"""``mcgyvr rig status`` says what the rig lends and the balance the hub answers.

Beside the machine's reading, status names each resource the rig advertises as
lent (a card whole, memory in MiB, cores) or says why it lends nothing, and
says when memory and cores alone are lent, which no hub places a head on yet. With
the member's personal hub key in ``$MCGYVR_HUB_API_KEY`` it asks the hub's
``/api/v1/me/credits`` with that key in the ``Authorization`` header and prints
the balance; a hub that refuses, redirects (the key never follows), or
answers something that is not a balance, is a note, never a failed status;
with no key it says where the key goes.
"""

from __future__ import annotations

import http.server
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from tests.machine_shapes import Card, HostShape, host_reading

TOKEN = "mhr_0123456789abcdef_" + "s" * 43
KEY = "mhk_example_personal_key"
RAM = hubwire.LEND_FLOOR_MB[hubwire.RESOURCE_RAM] * 2

MACHINE = HostShape(
    label="linux-lender",
    system="linux",
    machine_id="0123456789abcdef0123456789abcdf4",
    memory_mib=32 * 1024,
    available_mib=20000,
    cpu_model="Example CPU L8",
    cores=4,
    threads=8,
    version="6.1-example",
    cards=(Card(index=0, name="Example Card T", vendor="vendor-a", total_mib=16384),),
)


class _Hub:
    """A hub on this machine that answers ``/api/v1/me/credits`` alone."""

    def __init__(self) -> None:
        self.status = 200
        self.answer: Any = {"balance": "123.456789", "entries": []}
        self.seen: list[tuple[str, str | None]] = []
        self.moved_to: str | None = None
        hub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                hub.seen.append((self.path, self.headers.get("Authorization")))
                if hub.moved_to is not None:
                    self.send_response(302)
                    self.send_header("Location", hub.moved_to)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                raw = json.dumps(hub.answer).encode()
                self.send_response(
                    hub.status if self.path.endswith("/credits") else 404
                )
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args: Any) -> None:
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Hub]:
    from mcgyvr import cli
    from mcgyvr.rig import hardware, sharing, verbs

    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("MCGYVR_HUB_API_KEY", raising=False)
    monkeypatch.setattr(verbs, "run_agent", lambda kept, config=None: 0)
    reading = host_reading(MACHINE)
    monkeypatch.setattr(hardware, "read_machine", lambda: reading)
    made = _Hub()
    assert cli.main(["rig", "join", made.url, "--token", TOKEN]) == 0
    models = tmp_path / "models"
    models.mkdir()
    sharing.save(
        sharing.Sharing(
            enabled=True,
            roles=("head", "worker"),
            image="engine:rpc",
            models_dir=str(models),
            ram_mb=RAM,
            cpu_cores=4,
        )
    )
    yield made
    made.server.shutdown()


def _status(capsys: pytest.CaptureFixture[str]) -> str:
    from mcgyvr import cli

    capsys.readouterr()
    assert cli.main(["rig", "status"]) == 0
    return capsys.readouterr().out


def test_status_names_each_lent_resource(
    hub: _Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _status(capsys)
    assert "lends:   card 0: Example Card T, 16384 MiB reading" in out
    assert f"ram {RAM} MiB reading" in out and "cpu 4 cores" in out
    assert "$MCGYVR_HUB_API_KEY" in out
    assert hub.seen == []


def test_status_says_why_nothing_is_lent(
    hub: _Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.rig import sharing

    sharing.save(sharing.Sharing())
    assert "lends:   nothing (lending is off)" in _status(capsys)


def test_status_prints_the_balance_the_hub_answers(
    hub: _Hub, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_HUB_API_KEY", KEY)
    out = _status(capsys)
    assert "credits: 123.456789" in out
    assert hub.seen == [("/api/v1/me/credits", f"Bearer {KEY}")]
    assert KEY not in out


@pytest.mark.parametrize(
    ("status", "answer"),
    [
        (401, {"detail": "no"}),
        (200, {"balance": "lots"}),
        (200, {"balance": "1" * 100}),
        (200, ["not", "an", "object"]),
    ],
)
def test_a_balance_the_hub_does_not_give_is_a_note(
    hub: _Hub,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    answer: Any,
) -> None:
    monkeypatch.setenv("MCGYVR_HUB_API_KEY", KEY)
    hub.status, hub.answer = status, answer
    out = _status(capsys)
    assert "credits: not read" in out
    assert "lots" not in out


def test_a_hub_that_redirects_is_not_followed_with_the_key(
    hub: _Hub, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    other = _Hub()
    try:
        monkeypatch.setenv("MCGYVR_HUB_API_KEY", KEY)
        hub.moved_to = f"{other.url}/api/v1/me/credits"
        out = _status(capsys)
        assert "credits: not read" in out
        assert other.seen == [] and KEY not in out
    finally:
        other.server.shutdown()


def test_status_says_a_lend_of_memory_and_cores_alone_is_not_yet_placeable(
    hub: _Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    from dataclasses import replace

    from mcgyvr.rig import sharing

    sharing.save(replace(sharing.load(), cards=()))
    out = _status(capsys)
    assert "lends:   ram" in out and f"ram {RAM} MiB" in out
    assert "not yet placeable" in out
    sharing.save(replace(sharing.load(), cards=None))
    assert "not yet placeable" not in _status(capsys)
