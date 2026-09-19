"""What the door's two serve steps share: reading a compose file, asking a
unit whether it answers, and talking to the rig's daemon through the shims.

A compose file is read and never executed to learn its services: the
``container_name`` and the ``--port`` in each service's ``command`` are what
gate 7 and the health check need, and both are literal in the file
:mod:`mcgyvr.emit` wrote. A service without either is refused by name, before
anything is started, because a unit the door cannot name is a unit gate 7
cannot tell from a stranger.

**Answering is not the same as serving.** A vLLM unit slept at level 2 answers
``/v1/models`` with 200, reports ``{"is_sleeping": true}``, and then hangs on a
real request (``mcgyvr-lab/records/measurements/vllm-sleep-2026-09-09/README.md``). So
the probe asks a second question, and :func:`sleeping` is careful about what
an answer to it is.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

# Re-exported, not merely used: the door polls by these, and a caller checking
# a wake budget against the door reads them off the door.
from mcgyvr.config import HEALTH_INTERVAL_S as HEALTH_INTERVAL_S
from mcgyvr.config import HEALTH_POLLS as HEALTH_POLLS
from mcgyvr.serving.gatelib import ssh

#: The compose project every live unit is filed under on a rig. One name, so
#: ``down`` finds exactly what ``up`` started and nothing a campaign left.
PROJECT = "mcgyvr"


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


def restart_count(container: str) -> int:
    """The container's ``docker inspect`` ``RestartCount``, or 0 if unreadable.

    Read through the door's shim, so it asks the rig's daemon and nothing
    else. Restarts are held at exactly 0, and the one thing worse than
    recording a restart is not asking; a daemon that cannot answer after a
    successful ``compose up`` is recorded as 0 rather than as a count that
    was never read.
    """
    try:
        done = subprocess.run(
            ["docker", "inspect", "--format", "{{.RestartCount}}", container],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 0
    if done.returncode != 0:
        return 0
    try:
        return int(done.stdout.strip())
    except ValueError:
        return 0


def models_served(host: str, port: int) -> list[str] | None:
    """The model ids a unit on ``host``:``port`` lists, or None if it does not answer.

    ``/v1/models`` rather than ``/health``: both engines serve it, and it
    names what was loaded.
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


#: What :func:`sleeping` answers when the unit's ``/is_sleeping`` could not be
#: read: not a 404, not a readable answer. Owner ruling on FLT-02: a failed read.
SLEEP_UNREAD = "unread"


def sleeping(host: str, port: int) -> bool | str | None:
    """Whether the unit says it is asleep; None with no sleep route; else unread.

    ``/is_sleeping`` is a **vLLM** development route, registered only when the
    server runs with ``VLLM_SERVER_DEV_MODE=1`` (sleeping also needs
    ``--enable-sleep-mode``); without the variable it is 404, and llama.cpp has
    no such route at any launch
    (``mcgyvr-lab/records/measurements/vllm-sleep-2026-09-09/README.md``). **So
    a 404 is None, the ordinary answer, and it means awake.** An engine that
    cannot report a sleep has no way to be asleep.

    ``{"is_sleeping": true}`` or ``false`` is the unit's own answer. Everything
    else — the ssh failing, a 5xx, a body that does not parse, a body of some
    other shape — is :data:`SLEEP_UNREAD` (owner ruling, FLT-02): the probe was
    asked and could not read the answer, and a unit that may be asleep hangs
    the first contract dispatched to it.
    """
    try:
        done = ssh(
            host,
            f"curl -s -w '\\n%{{http_code}}' http://localhost:{port}/is_sleeping",
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return SLEEP_UNREAD
    if done.returncode != 0:
        return SLEEP_UNREAD
    body, _, code = done.stdout.rpartition("\n")
    if not (code.isascii() and code.isdigit() and len(code) == 3):
        body, code = done.stdout, ""
    if code == "404":
        return None
    try:
        doc = json.loads(body)
    except ValueError:
        return SLEEP_UNREAD
    said = doc.get("is_sleeping") if isinstance(doc, dict) else None
    return said if isinstance(said, bool) else SLEEP_UNREAD


class SleepLevelError(ValueError):
    """A sleep was asked for at a level this fleet has measured and banned."""


#: The host RAM a level-1 sleep surrenders for the life of the process, measured
#: on srv2 twice on 2026-09-09 with identical results: 3.14 GiB for the 3B and
#: 10.32 for the 7B. A later level-2 sleep does not release it and sixty seconds
#: idle does not release it; only a container restart does.
_LEVEL_ONE_RAM_GIB = 13.46


def sleep(host: str, port: int, level: int) -> bool:
    """Put the unit on ``host``:``port`` to sleep, refusing every banned level.

    **The one place in ``src/`` a sleep level is spelled**, so that the ban
    below has somewhere to live.

    **Level 1 is refused.** It keeps the weights in host RAM to wake faster, and
    on this fleet it never gives that RAM back: 3.14 GiB for the 3B, 10.32 for
    the 7B, 13.46 GiB in total, for the life of the process. It is bounded
    rather than a leak — a second cycle costs nothing more — and it buys nothing
    at all, because it releases the same card as level 2 (within 14-26 MiB)
    while being slower to sleep and to wake. Its only distinguishing
    property on this fleet is RAM it does not return
    (``mcgyvr-lab/records/measurements/fleet-gaps-2026-09-09/README.md``, M7).

    The refusal is raised **before the transport**, because the cost is paid by
    the request arriving rather than by it succeeding: a ban that dialled first
    and refused the answer would have surrendered the RAM already.

    Anything that is not 1 or 2 is refused for a different reason — nobody has
    measured it. Two levels exist and one is banned, which leaves exactly one; a
    third number is not a conservative default, it is an unmeasured call to a
    live rig.

    A rig that cannot be reached is ``False`` and not a refusal. That is the
    same distinction :func:`sleeping` keeps between ``None`` and ``False``: a
    transport that failed has not been asked to do anything wrong, and reading
    one as the other would make an ssh timeout look like a policy violation.
    """
    if level == 1:
        raise SleepLevelError(
            f"refusing a level-1 sleep of {host}:{port}. It surrenders "
            f"{_LEVEL_ONE_RAM_GIB:g} GiB of host RAM permanently — a level 2 "
            f"sleep does not release it and only a container restart does — to "
            f"free the same card a level 2 frees for nothing, and faster. "
            f"Use level 2."
        )
    if level != 2:
        raise SleepLevelError(
            f"refusing a level-{level} sleep of {host}:{port}: vLLM has levels "
            f"1 and 2, level 1 is banned on this fleet, and nobody has measured "
            f"what {level} does here. Use level 2."
        )
    try:
        done = ssh(
            host,
            f"curl -sf -X POST 'http://localhost:{port}/sleep?level=2'",
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def wait_for(host: str, service: Service) -> dict[str, object]:
    """Poll one unit until it is serving, or the budget is spent.

    Serving is two readings and not one: the unit lists its models *and* does
    not say it is asleep. A sleeper reads as not-yet rather than as no, so the
    poll keeps waiting: giving up the first time ``is_sleeping`` came back true
    would abandon a wake that may already be under way.

    ``/v1/models`` stays the gate on asking at all: a unit still reading its
    weights — 50-129 s of it on srv1 — cannot answer either question, and a
    second ssh per poll for two minutes buys nothing.

    The row carries ``sleeping`` so the envelope can tell the two failures
    apart, and ``restarts`` so it records the container's restart count.
    A unit that never came up wants its container log read; one that is
    asleep wants a wake, and its log is clean. :func:`sleep` sleeps only at
    level 2, which discards the weights, so vLLM's wake is three calls:
    ``POST /wake_up?tags=weights``, ``POST /collective_rpc`` with
    ``{"method": "reload_weights"}``, then ``POST /wake_up?tags=kv_cache``.
    ``None`` is "never got an answer to that question" — nobody asked, or the
    engine has no sleep route — and it is deliberately not ``False``, which is
    an engine that was asked and said no. :data:`SLEEP_UNREAD` is an answer that
    could not be read, and it does not read as serving.
    """
    started = time.monotonic()
    asleep: bool | str | None = None
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
                "restarts": restart_count(service.container),
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
        "restarts": restart_count(service.container),
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
