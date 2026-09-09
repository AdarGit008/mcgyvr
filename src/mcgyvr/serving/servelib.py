"""What the door's two serve steps share: reading a compose file, asking a
unit whether it answers, and talking to the rig's daemon through the shims.

A compose file is read and never executed to learn its services: the
``container_name`` and the ``--port`` in each service's ``command`` are what
gate 7 and the health check need, and both are literal in the file
:mod:`mcgyvr.emit` wrote. A service without either is refused by name, before
anything is started, because a unit the door cannot name is a unit gate 7
cannot tell from a stranger.
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


def wait_for(host: str, service: Service) -> dict[str, object]:
    """Poll one unit until it lists its models or the budget is spent."""
    started = time.monotonic()
    for attempt in range(HEALTH_POLLS):
        ids = models_served(host, service.port)
        if ids is not None:
            return {
                "container": service.container,
                "port": service.port,
                "healthy": True,
                "seconds": round(time.monotonic() - started, 1),
                "models": ids,
            }
        if attempt + 1 < HEALTH_POLLS:
            time.sleep(HEALTH_INTERVAL_S)
    return {
        "container": service.container,
        "port": service.port,
        "healthy": False,
        "seconds": round(time.monotonic() - started, 1),
        "models": [],
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
