"""What the door's two serve steps share: reading a compose file, asking a
unit whether it answers, and talking to the rig's daemon through the shims.

A compose file is read and never executed to learn its services: the
``container_name`` and the ``--port`` in each service's ``command`` are what
gate 7 and the health check need, and both are literal in the file
:mod:`mcgyvr.emit` wrote. A service without either is refused by name, before
anything is started, because a unit the door cannot name is a unit gate 7
cannot tell from a stranger.

**Answering is not the same as serving, and since 2026-09-09 the door knows
it.** A vLLM unit slept at level 2 answers ``/v1/models`` with 200, reports
``{"is_sleeping": true}``, and then hangs forever on a real request — no
response in 60 s (``records/measurements/vllm-sleep-2026-09-09/README.md``).
Until a unit could sleep, up meant serving and one question was enough; it no
longer is, and the failure it leaves is silent rather than loud: the door would
print ``up``, gate 7 would find every declared container running, the run would
be green, and the first contract dispatched to the rig would hang until
``budgets.request_timeout_s``. So the probe asks a second question, and
:func:`sleeping` is careful about what an answer to it is.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from mcgyvr.serving.gatelib import ssh

#: The compose project every live unit is filed under on a rig. One name, so
#: ``down`` finds exactly what ``up`` started and nothing a campaign left.
PROJECT = "mcgyvr"
#: How long a unit may take to answer ``/v1/models`` after ``up``: a vLLM
#: server measured 87 s to health on srv2 and llama.cpp 54-129 s on srv1
#: (2026-09-05), so six minutes is three of the slowest with room.
HEALTH_POLLS = 120
HEALTH_INTERVAL_S = 3.0


class ComposeError(Exception):
    """The compose file does not name its units the way the door needs."""


@dataclass(frozen=True)
class Service:
    """One unit as the compose file spells it: what to look for, where to knock."""

    name: str
    container: str
    port: int


def services(compose: Path) -> tuple[Service, ...]:
    """Every service in ``compose``, by container name and port, or refused."""
    try:
        doc = yaml.safe_load(compose.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ComposeError(
            f"{compose}: cannot be read as a compose file: {exc}"
        ) from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("services"), dict):
        raise ComposeError(f"{compose}: carries no `services:` mapping")
    found: list[Service] = []
    for name, block in doc["services"].items():
        if not isinstance(block, dict):
            raise ComposeError(f"{compose}: service {name!r} is not a mapping")
        container = block.get("container_name")
        if not isinstance(container, str) or not container.strip():
            raise ComposeError(
                f"{compose}: service {name!r} states no container_name, and gate 7 "
                "tells a unit from a stranger by that name and nothing else"
            )
        command = block.get("command")
        if not isinstance(command, list) or "--port" not in command:
            raise ComposeError(
                f"{compose}: service {name!r} carries no `--port` in its command, "
                "so the door has nowhere to knock to ask whether it is up"
            )
        raw = command[command.index("--port") + 1]
        try:
            port = int(raw)
        except (TypeError, ValueError):
            raise ComposeError(
                f"{compose}: service {name!r} states --port {raw!r}, not a number"
            ) from None
        found.append(Service(name=str(name), container=container.strip(), port=port))
    if not found:
        raise ComposeError(f"{compose}: declares no services")
    return tuple(found)


def compose(
    compose_file: Path, *args: str, timeout: float = 900.0
) -> subprocess.CompletedProcess[str]:
    """``docker compose`` against ``compose_file``, through the door's shim."""
    return subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "-p", PROJECT, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def containers_up() -> list[str]:
    """The names the rig's daemon lists now, through the shim."""
    done = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if done.returncode != 0:
        raise ComposeError(f"docker ps failed: {done.stderr.strip()[:300]}")
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def models_served(host: str, port: int) -> list[str] | None:
    """The model ids a unit on ``host``:``port`` lists, or None if it does not answer.

    ``/v1/models`` rather than ``/health``: both engines serve it, and a
    server that lists its models has loaded them, where a health endpoint on
    llama.cpp answers while the weights are still being read.
    """
    try:
        done = ssh(host, f"curl -sf http://localhost:{port}/v1/models", timeout=30)
    except subprocess.TimeoutExpired:
        return None
    if done.returncode != 0:
        return None
    try:
        doc = json.loads(done.stdout)
    except ValueError:
        return None
    rows = doc.get("data") if isinstance(doc, dict) else None
    if not rows and isinstance(doc, dict):
        rows = doc.get("models")
    ids: list[str] = []
    for row in rows or []:
        if isinstance(row, dict):
            ident = row.get("id") or row.get("name") or row.get("model")
            if ident:
                ids.append(str(ident))
    return ids


def sleeping(host: str, port: int) -> bool | None:
    """Whether the unit on ``host``:``port`` says it is asleep, or None if it cannot.

    ``/is_sleeping`` is a **vLLM** endpoint and exists only on a unit launched
    ``--enable-sleep-mode`` with ``VLLM_SERVER_DEV_MODE=1``; without those it is
    404, and llama.cpp has no such route at any launch
    (``records/measurements/vllm-sleep-2026-09-09/README.md``). That is not a
    corner case, it is the fleet: the 2026-09-09 handoff leaves srv2's vLLM pair
    with sleep mode off and ``/is_sleeping`` 404, and srv1 is llama.cpp
    throughout. **So None is the ordinary answer and it means awake.** An engine
    that cannot report a sleep has no way to be asleep, and a probe that read a
    404 as an error — or, worse, as a yes — would take every rig in the fleet out
    of service the day it landed.

    Only an explicit ``{"is_sleeping": true}`` may take a unit out of service.
    Everything else — the route missing, the ssh failing, a body that does not
    parse, a body of some other shape — is None. Failing closed on an unreadable
    answer would mean refusing to serve on every engine nobody has taught this
    function about yet, which today is both of them.
    """
    try:
        done = ssh(host, f"curl -sf http://localhost:{port}/is_sleeping", timeout=30)
    except subprocess.TimeoutExpired:
        return None
    if done.returncode != 0:
        return None
    try:
        doc = json.loads(done.stdout)
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    said = doc.get("is_sleeping")
    return said if isinstance(said, bool) else None


def wait_for(host: str, service: Service) -> dict[str, object]:
    """Poll one unit until it is serving, or the budget is spent.

    Serving is two readings and not one: the unit lists its models *and* does
    not say it is asleep. A sleeper reads as not-yet rather than as no, so the
    poll keeps waiting — a vLLM wake is 0.24-0.82 s, well inside one 3.0 s
    interval, and giving up the first time ``is_sleeping`` came back true would
    abandon a wake that was about to succeed.

    ``/v1/models`` stays the gate on asking at all: a unit still reading its
    weights — 50-129 s of it on srv1 — cannot answer either question, and a
    second ssh per poll for two minutes buys nothing.

    The row carries ``sleeping`` so the envelope can tell the two failures
    apart. A unit that never came up wants its container log read; one that is
    asleep wants a ``POST /wake_up`` and nothing else, and its log is clean.
    ``None`` is "never got an answer to that question" — nobody asked, or the
    engine cannot say — and it is deliberately not ``False``, which is an engine
    that was asked and said no.
    """
    started = time.monotonic()
    asleep: bool | None = None
    ids: list[str] | None = None
    for attempt in range(HEALTH_POLLS):
        ids = models_served(host, service.port)
        asleep = sleeping(host, service.port) if ids is not None else None
        if ids is not None and not asleep:
            return {
                "container": service.container,
                "port": service.port,
                "healthy": True,
                "sleeping": asleep,
                "seconds": round(time.monotonic() - started, 1),
                "models": ids,
            }
        if attempt + 1 < HEALTH_POLLS:
            time.sleep(HEALTH_INTERVAL_S)
    return {
        "container": service.container,
        "port": service.port,
        "healthy": False,
        "sleeping": asleep,
        "seconds": round(time.monotonic() - started, 1),
        "models": ids or [],
    }


def card(host: str) -> dict[str, object]:
    """The card's used and free MiB as the rig reads them now, or why not."""
    try:
        query = "--query-gpu=memory.used,memory.free --format=csv,noheader,nounits"
        done = ssh(host, f"nvidia-smi {query}", timeout=60)
    except subprocess.TimeoutExpired:
        return {"error": "nvidia-smi did not answer in 60s"}
    if done.returncode != 0:
        return {"error": done.stderr.strip()[:200]}
    parts = (
        [p.strip() for p in done.stdout.strip().splitlines()[0].split(",")]
        if done.stdout.strip()
        else []
    )
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return {"error": f"unreadable: {done.stdout.strip()[:100]!r}"}
    return {"used_mib": int(parts[0]), "free_mib": int(parts[1])}
