"""What a serve step does to a rig, shared by the four serve gate scripts.

A serve step (`serve up`, `serve sleep`, `serve wake`, `serve down`) runs
behind the door and reaches the one host the door named. This module holds
what they share: reading the emitted compose file into `Service` records,
running `docker compose` against it, probing the units over ssh on their
serving ports (`/v1/models`, `/is_sleeping`, `/sleep`, `/wake_up`, the
shipped card reader), polling a unit until it serves, and filing what the
step saw as a `serve-<mode>.json` record. `rigfile`, `run.py` and `wake.py`
read the same file through `services` when they need its containers and
ports.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

# The health budget `wait_for` spends on every unit, re-exported under this
# module's name so a caller — and a test — reads and cuts it here.
from mcgyvr.config import HEALTH_INTERVAL_S as HEALTH_INTERVAL_S
from mcgyvr.config import HEALTH_POLLS as HEALTH_POLLS
from mcgyvr.config import LAUNCHER_DOCKER, LAUNCHER_NATIVE, LAUNCHERS
from mcgyvr.serving import CARDS_KEY, LAUNCHER_KEY
from mcgyvr.serving.gatelib import LOCAL_RIGS, door_required, need, ssh, tool

#: The compose project every file is brought up under, passed as `-p`, so a
#: container's project is this tool; fleet read calls such a container ours.
PROJECT = "mcgyvr"


class ComposeError(Exception):
    """A compose file cannot be read as the spec a serve step acts on.

    Raised for a file that cannot be read or is not YAML, carries no
    `services:` mapping, or declares a service that is not a mapping,
    names no container or names no port, and for a `docker ps` that
    failed. The serve steps print it as a refusal rather than act on a
    half-read file.
    """


@dataclass(frozen=True)
class Service:
    """One compose service, as the emitted file states it.

    `name` is the service key the `docker compose` verbs take, `container` the
    `container_name` the file must state (gate 7 tells this run's unit from a
    stranger by that name), `port` the number after `--port` in the service's
    command, `devices` the card indexes it reserves, and `asleep` whether a
    profile keeps it down.
    """

    name: str
    container: str
    port: int
    #: The `device_ids` the service reserves under deploy.resources.reservations,
    #: in file order; rigfile reads them as the card indexes the unit takes.
    devices: tuple[str, ...] = ()
    #: A service written under a compose profile, so a plain `docker compose up`
    #: leaves it down: that is how the swap partner that starts asleep is declared.
    #: A whole `serve up` does not wait for it; a whole `serve down` names it.
    asleep: bool = False
    #: `docker`, or `native` for a unit `mcgyvr.serving.native` runs and keeps up.
    launcher: str = LAUNCHER_DOCKER


def launcher_of(units: tuple[Service, ...]) -> str:
    """How a launch spec's units run: all in containers, or all natively.

    A spec mixing the two is a `ComposeError`: one step either runs `docker
    compose` over the file or hands it to the native launcher, not both.
    """
    found = {unit.launcher for unit in units} or {LAUNCHER_DOCKER}
    if len(found) > 1:
        raise ComposeError(
            "the launch spec mixes containers and native units; `mcgyvr emit` "
            "writes a rig's native units and its containers apart"
        )
    (only,) = found
    return only


def services(compose: Path) -> tuple[Service, ...]:
    """Read every service the compose file declares, or refuse the whole file.

    The document must be a mapping with a `services:` mapping, and each service
    a mapping with a non-empty `container_name` and a `command` list carrying
    `--port` followed by a number, that being where the health probe knocks. Any
    departure — including a file with no services — raises `ComposeError`, so no
    caller acts on a partial reading.
    """
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
        launcher = block.get(LAUNCHER_KEY, LAUNCHER_DOCKER)
        if launcher not in LAUNCHERS:
            raise ComposeError(
                f"{compose}: service {name!r} states {LAUNCHER_KEY}: {launcher!r}, "
                f"not one of {', '.join(LAUNCHERS)}"
            )
        found.append(
            Service(
                name=str(name),
                container=container.strip(),
                port=port,
                devices=(
                    tuple(str(card) for card in block.get(CARDS_KEY) or ())
                    if launcher == LAUNCHER_NATIVE
                    else _devices(block)
                ),
                asleep=bool(block.get("profiles")),
                launcher=launcher,
            )
        )
    if not found:
        raise ComposeError(f"{compose}: declares no services")
    return tuple(found)


def _devices(block: dict[object, object]) -> tuple[str, ...]:
    """The card indexes a service reserves, in file order.

    Read from `deploy.resources.reservations.devices[].device_ids`. A missing or
    malformed chain at any step yields no devices rather than an error.
    """
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
    """Run one `docker compose` verb against the file, capturing its output.

    The project name is always `-p mcgyvr`, so every container the call
    creates is traceable to this tool. The call is never `check=True`: a
    non-zero exit comes back as the result for the caller to judge, while
    a call that outlasts `timeout` (900s by default) raises
    `subprocess.TimeoutExpired`.
    """
    return subprocess.run(
        [*tool("docker"), "compose", "-f", str(compose_file), "-p", PROJECT, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def up(
    compose_file: Path, units: tuple[Service, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Bring units up in the background, and say how the call ended.

    With no units named, compose starts everything the file starts by default
    and removes orphans. With units named, only those services start
    (`--no-deps`), which is how `serve up --unit` brings up a sleeper written
    under a profile without pulling in the partners it swaps with.

    A spec of native units is handed to `mcgyvr.serving.native` instead, which
    answers in the same shape.
    """
    if _is_native(compose_file):
        from mcgyvr.serving import native

        _native_here()
        done = native.up(compose_file, (u.name for u in units))
        return done
    if not units:
        return compose(compose_file, "up", "-d", "--remove-orphans")
    return compose(compose_file, "up", "-d", "--no-deps", *(u.name for u in units))


def down(
    compose_file: Path, units: tuple[Service, ...] = ()
) -> subprocess.CompletedProcess[str]:
    """Take units down, and say how the call ended.

    With no units named this is `docker compose down --remove-orphans` over the
    whole file. With units named it is `docker compose rm --stop --force` on
    those services only — the verb that also reaches a service written under a
    profile, which `down` is not promised to touch. A spec of native units
    stops them through `mcgyvr.serving.native`.
    """
    if _is_native(compose_file):
        from mcgyvr.serving import native

        _native_here()
        named = units or services(compose_file)
        return native.down(u.container for u in named)
    if not units:
        return compose(compose_file, "down", "--remove-orphans")
    return compose(compose_file, "rm", "--stop", "--force", *(u.name for u in units))


def _native_here() -> None:
    """Refuse a native step whose run names a rig other than this machine."""
    host = os.environ.get("RUN_HOST", "")
    if host not in LOCAL_RIGS:
        raise ComposeError(
            f"the launch spec runs natively, on this machine, and the run is for "
            f"{host or 'no host'}"
        )


def _is_native(compose_file: Path) -> bool:
    return launcher_of(services(compose_file)) == LAUNCHER_NATIVE


def containers_up(launcher: str = LAUNCHER_DOCKER) -> list[str]:
    """The names of every container the docker daemon reports as up.

    For `native`, the names of the units a native supervisor keeps up. Raises
    `ComposeError` when `docker ps` fails, so a daemon that could not be read
    is never mistaken for a rig with nothing left running.
    """
    if launcher == LAUNCHER_NATIVE:
        from mcgyvr.serving import native

        return sorted(native.running().values())
    done = subprocess.run(
        [*tool("docker"), "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if done.returncode != 0:
        raise ComposeError(f"docker ps failed: {done.stderr.strip()[:300]}")
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


def restart_count(container: str) -> int:
    """How many times the daemon has restarted the container, for the serve record.

    0 when the container cannot be inspected — a timeout, a non-zero exit, a
    container that is gone — because an unreadable count is no evidence of a
    restart.
    """
    if container in _native_units():
        from mcgyvr.serving import native

        found = (native.read_record(container) or {}).get("restarts")
        return found if isinstance(found, int) else 0
    try:
        done = subprocess.run(
            [*tool("docker"), "inspect", "--format", "{{.RestartCount}}", container],
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


def _native_units() -> set[str]:
    """The units this run's launch spec runs natively (none outside a native run)."""
    if os.environ.get("RUN_LAUNCHER") != LAUNCHER_NATIVE:
        return set()
    compose_file = os.environ.get("RUN_COMPOSE")
    if not compose_file:
        return set()
    try:
        return {s.container for s in services(Path(compose_file))}
    except ComposeError:
        return set()


def models_served(host: str, port: int) -> list[str] | None:
    """The model ids the unit on `host:port` lists at `/v1/models`, or None.

    None means the probe could not be read at all: ssh timed out, curl failed,
    the body did not parse. A list — possibly empty — means the unit answered;
    each row's `id`, else `name`, else `model` is taken as its id.
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


#: What `sleeping` answers when the unit's sleep state could not be read: an
#: answer of its own, so a failed probe reads neither as awake nor as asleep.
SLEEP_UNREAD = "unread"


def sleeping(host: str, port: int) -> bool | str | None:
    """Whether the unit on `host:port` says it is asleep, or why that is unread.

    `True` or `False` is the unit's own `is_sleeping` answer. None means the
    route is not there at all (404): a unit with no sleep route has no way to be
    asleep, so it is awake. `SLEEP_UNREAD` means the probe failed in any other
    way — ssh timed out, curl failed, a non-404 status, a body that does not
    parse or states no bool — and such a unit never reads as serving.
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
    """A sleep level this fleet does not issue was asked for, and nothing dialled."""


#: The host RAM a level-1 sleep surrenders and never gives back — a later
#: level-2 sleep does not release it, only a container restart does — measured
#: in GiB on this fleet, and carried here for one purpose: the refusal in
#: `sleep` states the number rather than only naming the ban.
_LEVEL_ONE_RAM_GIB = 13.46


def sleep(host: str, port: int, level: int) -> bool:
    """Sleep the unit on `host:port` at level 2; say whether the request landed.

    Level 1 and every other level are refused with `SleepLevelError` before the
    transport is dialled, so a banned request costs the rig nothing. False is a
    transport answer only: the rig was asked and did not accept, or did not
    answer in 60s.
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


def wake(host: str, port: int) -> bool:
    """Wake the unit on `host:port`; say whether the whole sequence landed.

    Three calls over ssh, in order: `/wake_up?tags=weights` (60s),
    `/collective_rpc` with `reload_weights` (900s, the rig reloads the weights
    from disk), then `/wake_up?tags=kv_cache` (60s). A timeout or a non-zero
    exit stops there and returns False — a half-woken unit is not woken.
    """
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
    """Poll a unit until it serves, and describe what was seen.

    `/v1/models` is asked first and `/is_sleeping` only once that answered,
    so a unit that is not answering is not credited with a sleep state
    either. At most `HEALTH_POLLS` polls, `HEALTH_INTERVAL_S` apart, ending
    as soon as the unit lists models and does not read as asleep; if the
    budget runs out first, the unit is reported down. The row carries
    container, port, healthy, sleeping, seconds, models and restarts, and
    is what the serve steps print and file.
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
    """The first NVIDIA card's memory on `host`, or why it could not be read.

    The reading comes from the shipped card reader, whose command
    `gatelib.cards_read_command` builds and which is imported in the call. The
    lowest `index` wins. Anything short of two integers says so in `error` — the
    reader did not answer in 60s, exited non-zero, printed something unreadable,
    listed no NVIDIA card, or stated no used/free pair — so a record never
    carries a memory figure that was guessed.
    """
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
    """What a serve step acts on, read from the door's environment once.

    `host` is the one host the run reaches, `compose_file` the emitted compose
    file, `out` the `serve-<mode>.json` path inside `RUN_OUT_DIR`, `units` every
    service that file declares, `expected` the containers the door read from it,
    and `only` the containers `--unit` narrowed the step to (empty for a
    whole-stack step).
    """

    host: str
    compose_file: Path
    out: Path
    units: tuple[Service, ...]
    expected: list[str]
    only: set[str]


def serve_prologue(mode: str, *, verify_refusal: str = "") -> ServeContext | None:
    """Gate the step, read the run from the environment, re-read the compose file.

    `door_required` refuses a step that does not descend from the door. The
    host, compose file, out directory, expected containers and `--unit` set are
    then read from the environment, and the compose file is read again into
    `units`. A file that no longer names the containers the door read from it is
    refused, since nothing is started or stopped from a file that changed under
    the run; the refusal carries `verify_refusal`, so a step can say what it did
    not do. A refusal prints `serve-<mode>: REFUSED — ...` on stderr and returns
    None, which the gate script answers with exit 2; otherwise the context comes
    back.
    """
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
    """File what the step did as `serve-<mode>.json` in `RUN_OUT_DIR`.

    The record names the run, host, mode, compose file and `--unit` set, spreads
    `body`'s findings, and ends with `card_after`: the card the host holds when
    the step ends, so a step that freed or refilled memory states it in its own
    record.
    """
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
