""

from __future__ import annotations

import fcntl
import hashlib
import itertools
import json
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr import atomic
from mcgyvr.availability import PROBE_TIMEOUT_S, AvailabilityVerdict, probe_endpoint
from mcgyvr.cooldown import COOLDOWN_S, Cooldown, SharedHold
from mcgyvr.runner import unit_in_flight
from mcgyvr.serving import host_of, port_of
from mcgyvr.wake import _ours, resting

if TYPE_CHECKING:  #
    from mcgyvr.capacity import Capacity
    from mcgyvr.local_pool import Endpoint, SourceMap

#
#ot
#
#
_SLUG = re.compile(r"[^A-Za-z0-9.-]+")

#
_BOARD = "pipeline.json"
#
#
_SCRATCH = re.compile(r"^.+\.(\d+)\.\d+\.tmp$")

#
#
#
_numbers = itertools.count()
_numbers_lock = threading.Lock()


def _next_number() -> int:
    with _numbers_lock:
        return next(_numbers)


def default_directory() -> Path:
    ""
    return Path(tempfile.gettempdir()) / f"mcgyvr-pressure-{os.getuid()}"


def _stem(key: str) -> str:
    ""
    slug = _SLUG.sub("-", key).strip("-")[-40:] or "key"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"{slug}.{digest}"


def climbed_key(rung: str) -> str:
    ""
    return f"climbed.{rung}"


def _usable(where: Path, *, make: bool) -> Path | None:
    ""
    if make:
        try:
            where.mkdir(parents=True, mode=0o700, exist_ok=True)
        except OSError:
            return None
    return where if _ours(where) else None


def _quietly_remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return


class Gauge:
    ""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory if directory is not None else default_directory()

    @contextmanager
    def present(self, key: str) -> Iterator[None]:
        ""
        held = self._mark(key)
        try:
            yield
        finally:
            if held is not None:
                fd, marker = held
                _quietly_remove(marker)
                with suppress(OSError):
                    os.close(fd)

    def _mark(self, key: str) -> tuple[int, Path] | None:
        where = _usable(self._directory, make=True)
        if where is None:
            return None
        name = f"{_stem(key)}.{os.getpid()}.{_next_number()}"
        scratch = where / f"{name}.tmp"
        marker = where / f"{name}.mark"
        try:
            fd = os.open(scratch, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError:
            return None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.rename(scratch, marker)
        except OSError:
            _quietly_remove(scratch)
            os.close(fd)
            return None
        return fd, marker

    def count(self, key: str) -> int | None:
        ""
        where = _usable(self._directory, make=True)
        if where is None:
            return None
        mine = re.compile(rf"^{re.escape(_stem(key))}\.\d+\.\d+\.mark$")
        try:
            names = os.listdir(where)
        except OSError:
            return None
        _sweep_scratch(where, names)
        return sum(1 for name in names if mine.match(name) and _held(where / name))


def _sweep_scratch(where: Path, names: list[str]) -> None:
    ""
    for name in names:
        found = _SCRATCH.match(name)
        if found is not None and not _running(int(found.group(1))):
            _quietly_remove(where / name)


def _running(pid: int) -> bool:
    ""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _held(marker: Path) -> bool:
    ""
    try:
        fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        #s to
        #
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            return False
        _quietly_remove(marker)
        return False
    finally:
        os.close(fd)


class Board:
    ""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory if directory is not None else default_directory()

    def publish(self, doc: Mapping[str, Any]) -> bool:
        ""
        where = _usable(self._directory, make=True)
        if where is None:
            return False
        try:
            text = json.dumps({**doc, "written_at": time.time()})
        except (TypeError, ValueError):
            return False
        scratch = where / f"{_BOARD}.{os.getpid()}.{_next_number()}.tmp"
        try:
            atomic.write(where / _BOARD, text, private=True, staging=scratch)
        except OSError:
            return False
        return True

    def read(self) -> dict[str, Any] | None:
        ""
        where = _usable(self._directory, make=False)
        if where is None:
            return None
        try:
            raw = (where / _BOARD).read_text(encoding="utf-8")
            said = json.loads(raw)
        except (OSError, ValueError, RecursionError):
            return None
        return said if isinstance(said, dict) else None


class HostCooling:
    ""

    def __init__(
        self, directory: Path | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        self._directory = directory if directory is not None else default_directory()
        self._clock = clock

    def _file(self, where: Path, source: str) -> Path:
        return where / f"held.{_stem(source)}.json"

    def hold(self, source: str, seconds: float) -> None:
        ""
        where = _usable(self._directory, make=True)
        if where is None:
            return
        until = self._clock() + seconds
        if (self._until(where, source) or 0.0) >= until:
            return
        target = self._file(where, source)
        scratch = where / f"{target.name}.{os.getpid()}.{_next_number()}.tmp"
        try:
            body = json.dumps({"source": source, "until": until})
            atomic.write(target, body, private=True, staging=scratch)
        except OSError:
            return

    def held(self, source: str) -> float | None:
        ""
        where = _usable(self._directory, make=False)
        if where is None:
            return None
        until = self._until(where, source)
        if until is None:
            return None
        left = until - self._clock()
        return left if left > 0 else None

    def _until(self, where: Path, source: str) -> float | None:
        try:
            said = json.loads(self._file(where, source).read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
        until = said.get("until") if isinstance(said, dict) else None
        if isinstance(until, bool) or not isinstance(until, (int, float)):
            return None
        return float(until)


@contextmanager
def exclusive(name: str, directory: Path | None = None) -> Iterator[bool | None]:
    ""
    where = _usable(
        directory if directory is not None else default_directory(), make=True
    )
    if where is None:
        yield None
        return
    try:
        fd = os.open(
            where / f"{_stem(name)}.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
    except OSError:
        yield None
        return
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            held: bool | None = False
        except OSError:
            held = None
        else:
            held = True
        yield held
    finally:
        os.close(fd)


@dataclass(frozen=True)
class Reading:
    ""

    rung: str
    awake: bool
    in_flight: int | None
    waiting: int | None
    climbed: int | None
    width: int
    full: bool = False


def _probed(endpoint: Endpoint) -> bool:
    ""
    if resting(host_of(endpoint.base_url), port_of(endpoint.base_url)):
        return False
    return probe_endpoint(endpoint, PROBE_TIMEOUT_S).live


def _status(endpoint: Endpoint) -> int | None:
    ""
    return unit_in_flight(
        endpoint.source, endpoint.base_url, endpoint.engine, endpoint.max_parallel
    )


class Pressure:
    ""

    def __init__(
        self,
        pool: SourceMap,
        capacity: Capacity,
        gauge: Gauge,
        *,
        live: Callable[[Endpoint], bool] | None = None,
        in_flight: Callable[[Endpoint], int | None] | None = None,
    ) -> None:
        self._pool = pool
        self._capacity = capacity
        self._gauge = gauge
        self._live = live if live is not None else _probed
        self._in_flight = in_flight if in_flight is not None else _status

    def read(self, rung: str) -> Reading:
        ""
        endpoint = self._pool.bind(rung)
        awake = self._live(endpoint)
        in_flight = self._in_flight(endpoint) if awake else None
        return Reading(
            rung=rung,
            awake=awake,
            in_flight=in_flight,
            waiting=self._capacity.waiting(endpoint.source, rung),
            climbed=self._gauge.count(climbed_key(rung)),
            width=self._capacity.limit(endpoint.source, rung),
            full=self._capacity.judge(endpoint.source, rung, in_flight).full,
        )


def server_counts(pool: SourceMap) -> Callable[[str], int | None]:
    ""

    from mcgyvr.local_pool import UnknownRungError

    def count(source: str) -> int | None:
        try:
            endpoint = pool.bind(source)
        except UnknownRungError:
            return None
        return _status(endpoint)

    return count


def _asleep_is_not_down(endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
    ""
    return AvailabilityVerdict(
        source=endpoint.source,
        live=True,
        reason="",
        how="stub probe, no network",
        elapsed_s=0.0,
    )


class RungCooling:
    ""

    def __init__(
        self,
        pool: SourceMap,
        cooldown: Cooldown | None = None,
        *,
        hold_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        shared: SharedHold | None = None,
    ) -> None:
        self._pool = pool
        if cooldown is None:
            cooldown = Cooldown(
                probe=_asleep_is_not_down,
                clock=clock,
                cooldown_s=COOLDOWN_S if hold_s is None else max(COOLDOWN_S, hold_s),
                shared=shared,
            )
        self._cooldown = cooldown

    def cooled(self, rungs: tuple[str, ...]) -> frozenset[str]:
        ""
        endpoints = [self._pool.bind(r) for r in rungs if self._pool.get(r) is not None]
        return frozenset(self._cooldown.unavailable(endpoints))

    def failed(self, rung: str) -> None:
        ""
        self._cooldown.record_failure(self._source(rung))

    def worked(self, rung: str) -> None:
        ""
        self._cooldown.record_success(self._source(rung))

    def _source(self, rung: str) -> str:
        return self._pool.bind(rung).source
