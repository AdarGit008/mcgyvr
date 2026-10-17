""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

#
#
from mcgyvr.config import HEALTH_INTERVAL_S as HEALTH_INTERVAL_S
from mcgyvr.config import HEALTH_POLLS as HEALTH_POLLS
from mcgyvr.serving.gatelib import door_required, need, ssh

#
#
PROJECT = "mcgyvr"


class ComposeError(Exception):
    ""


@dataclass(frozen=True)
class Service:
    ""

    name: str
    container: str
    port: int
    #
    #
    devices: tuple[str, ...] = ()
    #
    #
    #
    asleep: bool = False


def services(compose: Path) -> tuple[Service, ...]:
    ""
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
        found.append(
            Service(
                name=str(name),
                container=container.strip(),
                port=port,
                devices=_devices(block),
                asleep=bool(block.get("profiles")),
            )
        )
    if not found:
        raise ComposeError(f"{compose}: declares no services")
    return tuple(found)


def _devices(block: dict[object, object]) -> tuple[str, ...]:
    ""
    found: list[str] = []
    node: object = block.get("deploy")
    for key in ("resources", "reservations", "devices"):
        node = node.get(key) if isinstance(node, dict) else None
    for device in node if isinstance(node, list) else ():
        ids = device.get("device_ids") if isinstance(device, dict) else None
        if isinstance(ids, list):
            found.extend(str(each) for each in ids)
    return tuple(found)


def compose(
    compose_file: Path, *args: str, timeout: float = 900.0
) -> subprocess.CompletedProcess[str]:
    ""
    return subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "-p", PROJECT, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def up(
    compose_file: Path, units: tuple[Service, ...] = ()
) -> subprocess.CompletedProcess[str]:
    ""
    if not units:
        return compose(compose_file, "up", "-d", "--remove-orphans")
    return compose(compose_file, "up", "-d", "--no-deps", *(u.name for u in units))


def down(
    compose_file: Path, units: tuple[Service, ...] = ()
) -> subprocess.CompletedProcess[str]:
    ""
    if not units:
        return compose(compose_file, "down", "--remove-orphans")
    return compose(compose_file, "rm", "--stop", "--force", *(u.name for u in units))


def containers_up() -> list[str]:
    ""
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
    ""
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
    ""
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


#
#
SLEEP_UNREAD = "unread"


def sleeping(host: str, port: int) -> bool | str | None:
    ""
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
    ""


#
#
#
#
_LEVEL_ONE_RAM_GIB = 13.46


def sleep(host: str, port: int, level: int) -> bool:
    ""
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


def wake(host: str, port: int) -> bool:
    ""
    calls = (
        (f"curl -sf -X POST 'http://localhost:{port}/wake_up?tags=weights'", 60),
        (
            f"curl -sf -X POST 'http://localhost:{port}/collective_rpc' "
            "-H 'Content-Type: application/json' "
            '-d \'{"method": "reload_weights"}\'',
            900,
        ),
        (f"curl -sf -X POST 'http://localhost:{port}/wake_up?tags=kv_cache'", 60),
    )
    for command, budget in calls:
        try:
            done = ssh(host, command, timeout=budget)
        except subprocess.TimeoutExpired:
            return False
        if done.returncode != 0:
            return False
    return True


def wait_for(host: str, service: Service) -> dict[str, object]:
    ""
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
    ""
    from mcgyvr.serving.gatelib import cards_read_command

    try:
        done = ssh(host, cards_read_command(), timeout=60)
    except subprocess.TimeoutExpired:
        return {"error": "the reader did not answer in 60s"}
    if done.returncode != 0:
        return {"error": done.stderr.strip()[:200]}
    try:
        reading = json.loads(done.stdout)
        cards = [c for c in reading["cards"] if c.get("vendor") == "nvidia"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return {"error": f"unreadable: {done.stdout.strip()[:100]!r}"}
    if not cards:
        return {"error": "the reader read no card"}
    first = min(cards, key=lambda c: c.get("index", 0))
    used, free = first.get("used_mib"), first.get("free_mib")
    if type(used) is not int or type(free) is not int:
        return {"error": f"card {first.get('index')}: used or free memory unread"}
    return {"used_mib": used, "free_mib": free}


@dataclass(frozen=True)
class ServeContext:
    ""

    host: str
    compose_file: Path
    out: Path
    units: tuple[Service, ...]
    expected: list[str]
    only: set[str]


def serve_prologue(mode: str, *, verify_refusal: str = "") -> ServeContext | None:
    ""
    door_required(f"serve-{mode}")
    host = need("RUN_HOST")
    compose_file = Path(need("RUN_COMPOSE"))
    out = Path(need("RUN_OUT_DIR")) / f"serve-{mode}.json"
    try:
        units = services(compose_file)
    except ComposeError as exc:
        print(f"serve-{mode}: REFUSED — {exc}", file=sys.stderr)
        return None
    expected = need("RUN_SERVE_EXPECTED").split()
    if sorted(expected) != sorted(service.container for service in units):
        print(
            f"serve-{mode}: REFUSED — the compose file no longer names the "
            f"containers the door read from it{verify_refusal}",
            file=sys.stderr,
        )
        return None
    only = set(os.environ.get("RUN_SERVE_ONLY", "").split())
    return ServeContext(host, compose_file, out, units, expected, only)


def write_serve_record(ctx: ServeContext, mode: str, body: dict[str, object]) -> None:
    ""
    record: dict[str, object] = {
        "run_id": need("RUN_ID"),
        "host": ctx.host,
        "mode": mode,
        "compose_file": str(ctx.compose_file),
        "only": sorted(ctx.only),
        **body,
        "card_after": card(ctx.host),
    }
    ctx.out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
