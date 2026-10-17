""

from __future__ import annotations

import json
import math
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import ROLE_SLEEPER, Config
from mcgyvr.runner import RefusedConnectionError
from mcgyvr.serving import DEFAULT_ENGINE, Card, cards, host_of, port_of

if TYPE_CHECKING:  #
    from mcgyvr.scan import Scan

#
#
#
#
#
#
#
#
from mcgyvr.serving.gatelib import DOOR_MODULE, NO_SLEEP_ROUTE

#
#
#
Answer = TypeVar("Answer")


class WakeError(Exception):
    ""


def spawn_door(argv: Sequence[str], **kwargs: object) -> int:
    ""
    done = subprocess.run(list(argv), check=False, **kwargs)  #
    code: int = done.returncode
    return code


def door_argv(
    *,
    direction: str,
    host: str,
    compose: Path,
    suffix: str,
    units: Sequence[str] = (),
) -> tuple[str, ...]:
    ""
    return (
        sys.executable,
        "-m",
        DOOR_MODULE,
        "serve",
        direction,
        "--host",
        host,
        "--compose",
        str(compose),
        "--suffix",
        suffix,
        *(part for unit in units for part in ("--unit", unit)),
    )


def _suffix() -> str:
    ""
    return f"wake-{os.getpid()}-{int(time.monotonic() * 1000) % 1_000_000}"


@dataclass(frozen=True)
class Wake:
    ""

    host: str
    compose_file: Path
    direction: str
    seconds: float
    predicted_s: float | None
    code: int
    #
    #
    ports: tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def deviation(self) -> str | None:
        ""
        return None


def _clock_dir() -> Path:
    ""
    return Path(tempfile.gettempdir()) / f"mcgyvr-wake-{os.getuid()}"


def _ours(where: Path) -> bool:
    ""
    try:
        found = os.lstat(where)
    except OSError:
        return False
    if not stat.S_ISDIR(found.st_mode):
        return False
    if found.st_uid != os.getuid():
        return False
    return not found.st_mode & (stat.S_IWGRP | stat.S_IWOTH)


def _history(card: Card) -> Path:
    return _clock_dir() / f"{_safe(card.host)}.wake.json"


def _safe(host: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in host)


def predicted_wake_s(card: Card) -> float | None:
    ""
    where = _clock_dir()
    if not _ours(where):
        return None
    try:
        raw = _history(card).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    try:
        said = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(said, dict):
        return None
    seconds = said.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return None
    #
    number = float(seconds)
    return number if math.isfinite(number) else None


def _remember(made: Wake) -> None:
    ""
    if not made.ok or made.direction != "up":
        return
    try:
        where = _clock_dir()
        where.mkdir(parents=True, mode=0o700, exist_ok=True)
        if not _ours(where):
            return
        (where / f"{_safe(made.host)}.wake.json").write_text(
            json.dumps({"host": made.host, "seconds": round(made.seconds, 3)}),
            encoding="utf-8",
        )
    except OSError:
        return


def _rest_mark(host: str, port: int) -> Path:
    return _clock_dir() / f"{_safe(host)}-{port}.resting"


def resting(host: str, port: int | None = None) -> bool:
    ""
    where = _clock_dir()
    if not _ours(where):
        return False
    if port is not None:
        return _rest_mark(host, port).exists()
    prefix, suffix = f"{_safe(host)}-", ".resting"
    try:
        names = os.listdir(where)
    except OSError:
        return False
    return any(
        name.startswith(prefix)
        and name.endswith(suffix)
        and name[len(prefix) : -len(suffix)].isdigit()
        for name in names
    )


def _note_rest(made: Wake) -> None:
    ""
    if not made.ok:
        return
    try:
        where = _clock_dir()
        where.mkdir(parents=True, mode=0o700, exist_ok=True)
        if not _ours(where):
            return
        for port in made.ports:
            if made.direction == "sleep":
                _rest_mark(made.host, port).touch()
            else:
                _rest_mark(made.host, port).unlink(missing_ok=True)
    except OSError:
        return


def _wake_direction(card: Card, ports: Sequence[int] = ()) -> str:
    ""
    if ports:
        return "wake" if any(resting(card.host, port) for port in ports) else "up"
    return "wake" if resting(card.host) else "up"


def _ports(config: Config, rungs: Sequence[str]) -> tuple[int, ...]:
    ""
    return tuple(
        port_of(config.units[rung].address) for rung in rungs if rung in config.units
    )


def _all_vllm(config: Config, card: Card) -> bool:
    ""
    units = [config.units.get(name) for name in card.sources]
    return bool(units) and all(
        unit is not None and unit.engine == "vllm" for unit in units
    )


#
#
#
#
_ALONE_ENGINES = ("vllm", DEFAULT_ENGINE)


def _engine(config: Config, rung: str) -> str | None:
    ""
    unit = config.units.get(rung)
    return None if unit is None else unit.engine or DEFAULT_ENGINE


def _stopped_alone(config: Config, rungs: Sequence[str]) -> bool:
    ""
    return bool(rungs) and all(_engine(config, r) == DEFAULT_ENGINE for r in rungs)


def _sleeper(config: Config, rung: str) -> bool:
    ""
    unit = config.units.get(rung)
    return unit is not None and unit.role == ROLE_SLEEPER


def _unit_containers(
    config: Config, card: Card, compose: Path, rungs: Sequence[str]
) -> tuple[str, ...] | None:
    ""
    from mcgyvr.serving import servelib

    try:
        by_port = {
            service.port: service.container for service in servelib.services(compose)
        }
    except (servelib.ComposeError, OSError):
        return None
    found: list[str] = []
    for port in _ports(config, rungs):
        if port not in by_port:
            return None
        found.append(by_port[port])
    return tuple(found) if len(found) == len(rungs) else None


def _per_unit(config: Config, card: Card) -> bool:
    ""
    if len(card.rungs) < 2 or not all(
        _engine(config, name) in _ALONE_ENGINES for name in card.sources
    ):
        return False
    compose = compose_for(card)
    return compose is not None and (
        _unit_containers(config, card, compose, card.rungs) is not None
    )


def card_rooms(scans: Mapping[str, Scan]) -> dict[str, dict[int, int]]:
    ""
    return {
        host: {gpu.index: gpu.vram.total_mib for gpu in scan.gpus}
        for host, scan in scans.items()
        if scan.gpus
    }


def compose_for(card: Card) -> Path | None:
    ""
    if len(card.specs) == 1:
        return card.specs[0]
    return None


def resident_units(config: Config) -> frozenset[str]:
    ""
    bound = config.get("jev.unit")
    return frozenset({str(bound)}) if bound else frozenset()


def holds_resident(config: Config, card: Card) -> str | None:
    ""
    for name in resident_units(config):
        unit = config.units.get(name)
        if unit is not None and host_of(unit.address) == card.host:
            return name
    return None


def wakeable_rungs(config: Config) -> tuple[str, ...]:
    ""
    return tuple(
        name
        for name, card in cards(config).items()
        if compose_for(card) is not None and holds_resident(config, card) is None
    )


def _split_elsewhere(config: Config, card: Card) -> str | None:
    ""
    from mcgyvr.serving import SHARDS_KEY, UnitError, host_of

    for source in card.sources:
        unit = config.units[source]
        shards = unit.launch.get(SHARDS_KEY)
        try:
            home = host_of(unit.address).lower()
        except UnitError:
            continue
        elsewhere = sorted(
            {
                str(shard.get("rig"))
                for shard in (shards if isinstance(shards, list) else ())
                if isinstance(shard, Mapping)
                and str(shard.get("rig", "")).lower() != home
            }
        )
        if elsewhere:
            return f"{source} is split onto {', '.join(elsewhere)}"
    return None


def left_alone(config: Config) -> dict[str, str]:
    ""
    wakeable = set(wakeable_rungs(config))
    found: dict[str, str] = {}
    for name, card in cards(config).items():
        if name not in wakeable:
            continue
        split = _split_elsewhere(config, card)
        if split is not None:
            found[name] = f"{split}, and a sleep or wake acts on {card.host} alone"
    return found


def _why_not_one(card: Card) -> str:
    ""
    if not card.specs:
        return (
            f"{card.host}: this config holds no launch spec for that card. "
            f"`asleep` is `down` plus a file mcgyvr wrote, and there is no "
            f"file: set `serving.compose_dir` to where `mcgyvr emit --out` "
            f"wrote, and emit if it has not been emitted"
        )
    listed = ", ".join(path.name for path in card.specs)
    return (
        f"{card.host}: this config holds {len(card.specs)} launch specs for "
        f"that card — {listed} — and only one of them is ever up. Which one is "
        f"current is not a question the config answers, so mcgyvr will not "
        f"guess: name the file to `python -m {DOOR_MODULE} serve` yourself. If "
        f"one of these is an older cut of the rig, `mcgyvr emit --check` says "
        f"which, and deleting it leaves one"
    )


def _run_door(
    config: Config,
    card: Card,
    direction: str,
    compose: Path,
    *,
    only: Sequence[str] = (),
) -> Wake:
    ""
    predicted = predicted_wake_s(card)
    containers = _unit_containers(config, card, compose, only) if only else None
    acting = tuple(only) if containers is not None else card.rungs
    started = time.monotonic()
    code = spawn_door(
        door_argv(
            direction=direction,
            host=card.host,
            compose=compose,
            suffix=_suffix(),
            units=containers or (),
        )
    )
    made = Wake(
        host=card.host,
        compose_file=compose,
        direction=direction,
        seconds=time.monotonic() - started,
        predicted_s=predicted,
        code=code,
        ports=_ports(config, acting),
    )
    _remember(made)
    _note_rest(made)
    said = made.deviation
    if said is not None:
        print(f"warning: {said}", file=sys.stderr)
    return made


class Waker:
    ""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._cards = cards(config)
        #
        #
        #nd
        #ld
        #
        self._woken: dict[str, tuple[bool, float]] = {}
        #
        #
        #
        #
        #
        #
        self._lock = threading.Lock()
        self._card_locks: dict[str, threading.Lock] = {}

    def dispatching(self, rung: str, send: Callable[[], Answer]) -> Answer:
        ""
        card = self._cards.get(rung)
        if rung in resident_units(self._config) or (
            card is not None and holds_resident(self._config, card) is not None
        ):
            #
            #
            return send()
        if _sleeper(self._config, rung):
            #
            #
            #
            return send()
        if card is not None and any(
            resting(card.host, port) for port in _ports(self._config, (rung,))
        ):
            #
            #
            #
            if not self.wake_for(rung, refused_at=time.monotonic()):
                raise RefusedConnectionError(
                    f"{rung}: its card {card.host} was put to sleep with its "
                    "process kept, and could not be woken"
                )
            return send()
        try:
            return send()
        except RefusedConnectionError as refused:
            #
            #
            if not self.wake_for(rung, refused_at=time.monotonic()):
                raise refused
            return send()

    def wake_for(self, rung: str, *, refused_at: float | None = None) -> bool:
        ""
        card = self._cards.get(rung)
        if card is None:
            return False
        with self._lock:
            card_lock = self._card_locks.setdefault(card.host, threading.Lock())
        with card_lock:
            return self._wake_for(card, refused_at, rung)

    def _wake_for(self, card: Card, refused_at: float | None, rung: str) -> bool:
        #
        #
        #
        alone = _per_unit(self._config, card)
        key = f"{card.host}:{rung}" if alone else card.host
        if key in self._woken:
            ok, ended = self._woken[key]
            return ok and refused_at is not None and refused_at < ended
        #
        #he
        #
        #ke
        #
        #
        #
        from mcgyvr.fleet.roots import LiveFleetError, live_fleet_dir, runs_live

        if runs_live(self._config.path):
            from mcgyvr.fleet.admit import host_is_locked

            try:
                root = live_fleet_dir()
            except LiveFleetError as exc:
                print(f"warning: {exc}", file=sys.stderr)
                return False
            if root is None or not host_is_locked(root, card.host):
                return False
        compose = compose_for(card)
        if compose is None:
            #
            #
            #
            #
            #
            #
            #
            #
            #he
            #or
            #
            #
            if card.specs:
                self._woken[key] = (False, time.monotonic())
                print(f"warning: {_why_not_one(card)}", file=sys.stderr)
            return False
        if alone:
            direction = _wake_direction(card, _ports(self._config, (rung,)))
            #
            #
            only: tuple[str, ...] = (
                (rung,)
                if direction == "wake" or _stopped_alone(self._config, (rung,))
                else ()
            )
        else:
            direction, only = _wake_direction(card), ()
        ok = _run_door(self._config, card, direction, compose, only=only).ok
        self._woken[key] = (ok, time.monotonic())
        return ok


def for_config(config: Config) -> Waker | None:
    ""
    if not config.get("serving.enable_sleep_wake"):
        return None
    if not config.get("serving.compose_dir"):
        return None
    return Waker(config)


def card_named(config: Config, host: str) -> Card:
    ""
    for card in cards(config).values():
        if card.host == host:
            return card
    known = sorted({card.host for card in cards(config).values()})
    raise WakeError(
        f"no rung of this ladder is served by {host!r}"
        + (f" — this config's rigs are {', '.join(known)}" if known else "")
    )


def sleep(config: Config, host: str) -> Wake:
    ""
    card = card_named(config, host)
    _refuse_resident(config, card, "slept")
    return put_down(config, card)


def put_down(config: Config, card: Card, only: tuple[str, ...] = ()) -> Wake:
    ""
    _refuse_resident(config, card, "slept")
    compose = compose_for(card)
    if compose is None:
        raise WakeError(_why_not_one(card))
    split = _split_elsewhere(config, card)
    if split is not None:
        #
        #
        print(
            f"note: {split}; vLLM's sleep at level 2 is not measured for a unit "
            f"split across machines, so {card.host} is stopped instead",
            file=sys.stderr,
        )
    elif only and _per_unit(config, card) and _stopped_alone(config, only):
        return _run_door(config, card, "down", compose, only=only)
    elif _all_vllm(config, card):
        asked = _run_door(config, card, "sleep", compose, only=only)
        if asked.code != NO_SLEEP_ROUTE:
            return asked
    #
    #
    #
    return _run_door(config, card, "down", compose)


def _refuse_resident(config: Config, card: Card, verb: str) -> None:
    held = holds_resident(config, card)
    if held is not None:
        raise WakeError(
            f"{card.host} holds {held!r}, the jev unit, which is resident: it is "
            f"never slept or woken, so its card is not {verb}. Unbind `jev.unit` "
            "to make the card a switch again."
        )


def wake(config: Config, host: str) -> Wake:
    ""
    card = card_named(config, host)
    _refuse_resident(config, card, "woken")
    compose = compose_for(card)
    if compose is None:
        #
        #ed
        #
        #
        raise WakeError(_why_not_one(card))
    return _run_door(config, card, _wake_direction(card), compose)


def drain_timeout(config: Config, card: Card) -> float | None:
    ""
    timeouts: list[float] = []
    for name in card.sources:
        unit = config.units.get(name)
        if unit is not None and unit.request_timeout_s is not None:
            timeouts.append(unit.request_timeout_s)
    return max(timeouts) if timeouts else None


class CardSwitches:
    ""

    def __init__(
        self,
        config: Config,
        capacity: Capacity,
        *,
        card_mib: Mapping[str, Mapping[int, int]] | None = None,
    ) -> None:
        self._config = config
        self._capacity = capacity
        self._cards = cards(config)
        self._card_mib = {host: dict(sizes) for host, sizes in (card_mib or {}).items()}

    def _allowed(self) -> bool:
        return bool(
            self._config.get("serving.enable_sleep_wake")
            and self._config.get("serving.compose_dir")
        )

    def _resident(self, rung: str) -> bool:
        ""
        if rung in resident_units(self._config):
            return True
        card = self._cards.get(rung)
        return card is not None and holds_resident(self._config, card) is not None

    def wake(self, rung: str) -> bool:
        ""
        if self._resident(rung):
            return False
        waker = for_config(self._config)
        return waker is not None and waker.wake_for(rung)

    def sleep(self, rung: str) -> bool:
        ""
        if not self._allowed() or self._resident(rung):
            return False
        card = self._cards.get(rung)
        if card is None or compose_for(card) is None:
            return False
        alone = _per_unit(self._config, card)
        #
        sources = (rung,) if alone else card.sources
        try:
            with self._capacity.drain(
                sources, timeout=drain_timeout(self._config, card)
            ):
                #
                #
                #
                if self._capacity.queued(sources) != 0:
                    return False
                return self._put_down(card, (rung,) if alone else ())
        except (SlotUnavailableError, WakeError):
            return False

    def _put_down(self, card: Card, only: tuple[str, ...]) -> bool:
        ""
        return put_down(self._config, card, only).ok

    def room_for(self, rung: str) -> tuple[str, ...]:
        ""
        return self._room(rung)[0]

    def why_no_room(self, rung: str) -> str | None:
        ""
        return self._room(rung)[1]

    def _room(self, rung: str) -> tuple[tuple[str, ...], str | None]:
        card = self._cards.get(rung)
        if card is None or not _per_unit(self._config, card):
            return (), None
        sizes = self._card_mib.get(card.host, {})
        if not sizes:
            return (), (
                f"no recorded scan gives {card.host}'s card memory "
                f"(`mcgyvr scan` records one)"
            )
        rooms: dict[str, int] = {}
        for name in card.rungs:
            unit = self._config.units.get(name)
            if unit is None or unit.room_mib is None:
                return (), f"{name} states no room_mib"
            rooms[name] = unit.room_mib
        on = self._placement(card, sizes)
        if isinstance(on, str):
            return (), on
        index = on[rung]
        if index not in sizes:
            return (), (
                f"no recorded scan of {card.host} has card {index}, which {rung} is on"
            )
        others = sorted(
            (r for r in card.rungs if r != rung and on[r] == index),
            key=lambda r: (rooms[r], r),
        )
        total = rooms[rung] + sum(rooms[r] for r in others)
        making: list[str] = []
        for other in others:
            if total <= sizes[index]:
                break
            making.append(other)
            total -= rooms[other]
        return tuple(making), None

    def _placement(self, card: Card, sizes: Mapping[int, int]) -> dict[str, int] | str:
        ""
        from mcgyvr.serving import servelib

        compose = compose_for(card)
        if compose is None:
            return _why_not_one(card)
        try:
            by_port = {service.port: service for service in servelib.services(compose)}
        except (servelib.ComposeError, OSError) as exc:
            return f"its launch spec cannot be read: {exc}"
        on: dict[str, int] = {}
        for name in card.rungs:
            service = by_port.get(port_of(self._config.units[name].address))
            ids = service.devices if service is not None else ()
            if not ids:
                if len(sizes) == 1:
                    on[name] = next(iter(sizes))
                    continue
                return (
                    f"{compose.name} does not say which card {name} is on, and "
                    f"{card.host} has {len(sizes)} cards"
                )
            if len(ids) > 1:
                return (
                    f"{name} is reserved more than one card ({', '.join(ids)}) "
                    f"in {compose.name}, and room is reckoned one card at a time"
                )
            if not ids[0].isdigit():
                return (
                    f"{compose.name} names {name}'s card {ids[0]!r}, not by the "
                    f"index a scan reads it at, so which card it is cannot be told"
                )
            on[name] = int(ids[0])
        return on

    def card_of(self, rung: str) -> tuple[str, ...]:
        ""
        card = self._cards.get(rung)
        if card is None:
            return (rung,)
        return (rung,) if _per_unit(self._config, card) else tuple(card.rungs)
