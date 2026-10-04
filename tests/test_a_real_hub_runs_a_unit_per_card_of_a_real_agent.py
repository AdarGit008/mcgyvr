"""A real hub runs a unit per card of a rig whose real agent says ``multi_session``.

Opt in: ``MCGYVR_HUB_REPO`` names a hub checkout whose virtualenv is built
(``uv sync`` in it). Without it every test here skips; a checkout named
without its ``.venv/bin/mcgyvr-hub`` fails.

The hub is that checkout's own server, a process on loopback with a database
of its own, placing units per card (``MCGYVR_HUB_PLACEMENT=card``). Each rig
is this repository's ``mcgyvr rig share`` and ``mcgyvr rig join`` in a process
of its own, on a machine :mod:`tests.rig_fake_machine` invents: two 8 GiB
cards, three small models, a daemon that starts nothing and an engine on
loopback that says which model and cards its head was started with. So a
chat answered through the hub says which card served it.

Held, on one rig of two cards whose agent says ``multi_session``:

* two models run as two units on its two cards, one card each, and the
  hub's ``fleet status``, its live board and ``/v1/models`` say so;
* a third model is not planned while both cards are held;
* a unit stopped frees its card alone: the other unit keeps answering, and
  the freed card runs a unit again.

And a rig whose agent does not say ``multi_session`` is taken whole: one unit
on both its cards, named on the fleet's ``placed_whole`` and on the board.

What it does not cover: units are heads alone on one rig, so no tunnel
between rigs is ever raised; the rig's LAN address is a documentation address
(:data:`tests.rig_pool_fakes.LAN_ADDRESS`) named with ``--endpoints``, since
a host may have no LAN of its own to find; and the hub is whatever the named
checkout holds, working tree included.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_fake_machine import Machine, Model

HUB_REPO_ENV = "MCGYVR_HUB_REPO"
REPO = Path(__file__).resolve().parent.parent

ALPHA, BETA, GAMMA = "m-alpha.gguf", "m-beta.gguf", "m-gamma.gguf"
MODELS = tuple(Model(name, gib=2, layers=24) for name in (ALPHA, BETA, GAMMA))
#: How long the hub gets to plan, start and ready a unit.
READY_S = 90.0
#: How long a third model is watched for, while both cards are held: more
#: than three of the hub's planning ticks (``MCGYVR_HUB_FLEET_TICK_INTERVAL_S``).
HELD_S = 10.0


def _free_port(kind: socket.SocketKind = socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _tail(path: Path, lines: int = 25) -> str:
    text = path.read_text(errors="replace") if path.exists() else ""
    return f"--- {path.name}\n" + "\n".join(text.splitlines()[-lines:])


class Hub:
    """The named checkout's hub on loopback, and the rigs joined to it."""

    def __init__(self, checkout: Path, work: Path) -> None:
        self.command = [str(checkout / ".venv" / "bin" / "mcgyvr-hub")]
        self.checkout = checkout
        self.work = work
        port = _free_port()
        self.url = f"http://127.0.0.1:{port}"
        self.port = port
        self.procs: list[subprocess.Popen[bytes]] = []
        self.logs: list[Path] = []
        self.key = ""  # alice's, the hub's admin, once she has one
        env = {k: v for k, v in os.environ.items() if not k.startswith("MCGYVR_")}
        udp = socket.SOCK_DGRAM
        self.env = env | {
            "MCGYVR_HUB_DB": str(work / "hub.db"),
            "MCGYVR_HUB_PLACEMENT": "card",
            "MCGYVR_HUB_ADMIN_HANDLES": "alice",
            "MCGYVR_HUB_STUN_HOST": "127.0.0.1",
            "MCGYVR_HUB_STUN_BIND": "127.0.0.1",
            "MCGYVR_HUB_STUN_PORT": str(_free_port(udp)),
            "MCGYVR_HUB_STUN_PORT_ALT": str(_free_port(udp)),
            "MCGYVR_HUB_RELAY_HOST": "127.0.0.1",
            "MCGYVR_HUB_RELAY_PORT": str(_free_port(udp)),
            "MCGYVR_HUB_RELAY_SECRET": os.urandom(24).hex(),
            "MCGYVR_HUB_RELAY_EMBEDDED_BIND": "127.0.0.1",
            "MCGYVR_HUB_FLEET_TICK_INTERVAL_S": "3",
            "MCGYVR_HUB_FLEET_REPLAN_POLL_S": "1",
            "MCGYVR_HUB_FLEET_RETRY_S": "10",
            "MCGYVR_HUB_SESSION_TEARDOWN_WAIT_S": "20",
        }

    # --- the hub ---------------------------------------------------------

    def serve(self) -> None:
        self._start(
            "hub",
            [*self.command, "serve", "--port", str(self.port)],
            self.env,
            self.checkout,
        )
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            with contextlib.suppress(OSError):
                if self.call("GET", "/api/v1/health")[0] == 200:
                    break
            time.sleep(0.3)
        else:
            raise AssertionError(f"the hub never answered\n{self.said()}")
        status, body = self.call("POST", "/api/v1/users", {"handle": "alice"})
        assert status == 201, body
        self.key = body["token"]

    def cli(self, *args: str) -> str:
        """``mcgyvr-hub ARGS`` against this hub, as alice; what it printed."""
        env = self.env | {"MCGYVR_HUB_API_KEY": self.key}
        done = subprocess.run(
            [*self.command, *args],
            env=env,
            cwd=self.checkout,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert done.returncode == 0, (args, done.stdout, done.stderr)
        return done.stdout

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        """``method path`` with ``body`` as JSON, as alice once she has a key;
        the status, and the answer as JSON or else as text."""
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.key:
            request.add_header("Authorization", f"Bearer {self.key}")
        try:
            with urllib.request.urlopen(request, timeout=60) as answer:
                raw, status = answer.read(), answer.status
        except urllib.error.HTTPError as refused:
            raw, status = refused.read(), refused.code
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, raw.decode(errors="replace")

    def fleet(self) -> dict[str, Any]:
        status, body = self.call("GET", "/api/v1/fleet")
        assert status == 200, body
        fleet: dict[str, Any] = body
        return fleet

    def units(self) -> list[dict[str, Any]]:
        return [u for scope in self.fleet()["scopes"] for u in scope["units"]]

    def board(self) -> list[tuple[str, str]]:
        """Each card on the live board: its rig's name, and what it says it runs."""
        status, html = self.call("GET", "/pool/live")
        assert status == 200, html
        found = []
        for slot in re.findall(r'<li class="slot">(.*?)</li>', html, re.S):
            rig = re.search(r'<span class="mono">([^<]*)</span>', slot)
            unit = re.search(r'<div class="unit">(.*?)</div>\s*$', slot, re.S)
            assert rig and unit, slot
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unit.group(1)))
            found.append((rig.group(1), text.strip()))
        return found

    def chat(self, model: str) -> tuple[int, str]:
        """A chat to ``model`` through the hub; its status, and what the engine
        said (its model and cards) or the hub's refusal."""
        body = {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": "hi"}],
        }
        deadline = time.monotonic() + 30.0
        while True:
            status, said = self.call("POST", "/v1/chat/completions", body)
            if status != 503 or time.monotonic() > deadline:
                break
            time.sleep(1.0)
        if status == 200:
            return status, str(said["choices"][0]["message"]["content"])
        return status, str(said)

    def models(self) -> set[str]:
        status, body = self.call("GET", "/v1/models")
        assert status == 200, body
        return {model["id"] for model in body["data"]}

    # --- the rigs --------------------------------------------------------

    def rig(self, name: str, machine: Machine) -> None:
        """Alice's pool rig ``name``, lent by an agent on ``machine``."""
        status, body = self.call(
            "POST", "/api/v1/rigs", {"name": name, "sharing_mode": "pool"}
        )
        assert status == 201, body
        home = self.work / f"home-{name}"
        (home / "models").mkdir(parents=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("MCGYVR_")}
        env |= machine.env() | {
            "MCGYVR_HOME": str(home),
            "MCGYVR_DATA": str(home / "data"),
        }
        agent = [sys.executable, "-m", "tests.rig_fake_machine", "rig"]
        shared = subprocess.run(
            [
                *agent,
                "share",
                "--on",
                "--image",
                "engine:rpc",
                "--roles",
                "head,worker",
                "--models",
                str(home / "models"),
                "--endpoints",
                fakes.LAN_ADDRESS,
            ],
            env=env,
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert shared.returncode == 0, (shared.stdout, shared.stderr)
        self._start(
            name, [*agent, "join", self.url, "--token", body["join_token"]], env, REPO
        )

    def _start(
        self, name: str, argv: list[str], env: dict[str, str], cwd: Path
    ) -> None:
        log = self.work / f"{name}.log"
        self.logs.append(log)
        with log.open("wb") as out:
            self.procs.append(
                subprocess.Popen(
                    argv, env=env, cwd=cwd, stdout=out, stderr=subprocess.STDOUT
                )
            )

    def said(self) -> str:
        return "\n".join(_tail(log) for log in self.logs)

    def wait[T](self, found: Callable[[], T | None], what: str) -> T:
        deadline = time.monotonic() + READY_S
        while time.monotonic() < deadline:
            got = found()
            if got:
                return got
            time.sleep(1.0)
        raise AssertionError(f"timed out: {what}; units {self.units()}\n{self.said()}")

    def close(self) -> None:
        for proc in reversed(self.procs):
            proc.terminate()
        for proc in reversed(self.procs):
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


@pytest.fixture
def hub(tmp_path: Path) -> Iterator[Hub]:
    named = os.environ.get(HUB_REPO_ENV)
    if not named:
        pytest.skip(f"${HUB_REPO_ENV} names no hub checkout")
    checkout = Path(named)
    assert (checkout / ".venv" / "bin" / "mcgyvr-hub").exists(), (
        f"${HUB_REPO_ENV} names {checkout}, which has no .venv/bin/mcgyvr-hub: "
        "run `uv sync` there"
    )
    made = Hub(checkout, tmp_path)
    try:
        yield made
    finally:
        made.close()


def _cards(unit: dict[str, Any]) -> list[str]:
    return sorted(f"{c['rig_name']}#{c['card_index']}" for c in unit["cards"])


def _ready(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [u for u in units if u["state"] == "ready"]


def test_two_models_run_on_two_cards_of_one_rig_and_one_stops_alone(hub: Hub) -> None:
    for model in (ALPHA, BETA):
        hub.cli("models", "add", model, "--copies", "1")
    hub.serve()
    assert hub.fleet()["placement"] == "card"
    hub.rig("two", Machine("mch-example-two", 2, MODELS))

    def two_ready() -> list[dict[str, Any]] | None:
        ready = _ready(hub.units())
        return ready if len(ready) == 2 else None

    ready = hub.wait(two_ready, "a unit ready on each card")
    unit = {u["model"]: u for u in ready}
    assert set(unit) == {ALPHA, BETA}, ready
    assert sorted(_cards(unit[ALPHA]) + _cards(unit[BETA])) == ["two#0", "two#1"]

    status = hub.cli("fleet", "status", "--url", hub.url)
    for model, u in unit.items():
        line = f"unit {u['id']} {model} ready:"
        assert any(
            row.strip().startswith(line) and row.endswith(f"cards {_cards(u)[0]}")
            for row in status.splitlines()
        ), status
    assert sorted(hub.board()) == [("two", f"runs {ALPHA}"), ("two", f"runs {BETA}")]
    assert hub.models() >= {ALPHA, BETA}
    for model, u in unit.items():
        code, said = hub.chat(model)
        device = _cards(u)[0].split("#")[1]
        assert code == 200 and model in said and f"device={device}" in said, said

    hub.cli("models", "add", GAMMA, "--copies", "1")
    hub.cli("fleet", "replan")
    deadline = time.monotonic() + HELD_S
    while time.monotonic() < deadline:
        assert all(u["model"] != GAMMA for u in hub.units()), hub.units()
        time.sleep(1.0)

    alpha, beta = unit[ALPHA], unit[BETA]
    code, body = hub.call("POST", f"/api/v1/sessions/{alpha['id']}/stop")
    assert code == 204, body
    code, said = hub.chat(BETA)
    assert code == 200 and BETA in said, said
    assert [u["state"] for u in hub.units() if u["id"] == beta["id"]] == ["ready"]
    again = hub.wait(
        lambda: [
            u
            for u in _ready(hub.units())
            if u["id"] not in (alpha["id"], beta["id"]) and _cards(u) == _cards(alpha)
        ],
        "a unit again on the freed card",
    )
    assert again[0]["model"] in (ALPHA, GAMMA), again
    code, said = hub.chat(BETA)
    assert code == 200 and BETA in said, said


def test_a_rig_whose_agent_lacks_multi_session_is_taken_whole(hub: Hub) -> None:
    hub.cli("models", "add", ALPHA, "--copies", "1")
    hub.serve()
    machine = Machine("mch-example-whole", 2, MODELS, multi_session=False)
    hub.rig("whole", machine)

    ready = hub.wait(lambda: _ready(hub.units()), "a unit on the rig")
    assert [(u["model"], _cards(u)) for u in ready] == [(ALPHA, ["whole#0", "whole#1"])]
    assert [r["rig_name"] for r in hub.fleet()["placed_whole"]] == ["whole"]
    assert "placed whole (agent lacks multi_session): whole" in hub.cli(
        "fleet", "status", "--url", hub.url
    )
    whole = "whole rig: its agent runs one unit at a time"
    assert hub.board() == [("whole", f"runs {ALPHA} · {whole}")] * 2
    assert ALPHA in hub.models()
    code, said = hub.chat(ALPHA)
    assert code == 200 and ALPHA in said and "device=0,1" in said, said
