""

from __future__ import annotations

import fcntl
import hashlib
import inspect
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from typing import Protocol as TypingProtocol

if TYPE_CHECKING:  #
    from mcgyvr.config import Config
    from mcgyvr.local_pool import Endpoint
    from mcgyvr.pressure import Gauge

#
#
#
#
_POLL_SECONDS = 0.02

#
#ot
#
_SLUG = re.compile(r"[^A-Za-z0-9.-]+")


def _default_lock_dir() -> Path:
    ""
    return Path(tempfile.gettempdir()) / f"mcgyvr-capacity-{os.getuid()}"


@dataclass(frozen=True)
class Fullness:
    ""

    #
    load: int
    #
    server: int | None
    #
    width: int

    @property
    def full(self) -> bool:
        ""
        if self.load >= self.width:
            return True
        return self.server is not None and self.server >= self.width

    @property
    def server_read(self) -> bool:
        return self.server is not None

    @property
    def why(self) -> str:
        ""
        server = (
            "the server was not read"
            if self.server is None
            else f"the server has {self.server} in flight"
        )
        return f"{self.load} of {self.width} here; {server}"


def _waiting_key(stem: str) -> str:
    ""
    return f"wait.{stem}"


def _slot_stem(base_url: str, rung: str | None = None) -> str:
    ""
    normalized = base_url.strip().rstrip("/").lower()
    slug = _SLUG.sub("-", normalized).strip("-")[-40:]
    if rung is not None:
        tidied = rung.strip().lower()
        normalized = f"{normalized}#{tidied}"
        slug = f"{slug}.{_SLUG.sub('-', tidied).strip('-')[-24:]}"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{slug}.{digest}"


class SourceWidthProbe(TypingProtocol):
    ""

    def width(self, source: str) -> int | None:
        ""
        ...


class WidthProbe(TypingProtocol):
    ""

    def width(self, source: str, rung: str | None = None) -> int | None:
        ""
        ...


def _reported(
    probe: WidthProbe | SourceWidthProbe, source: str, rung: str | None
) -> int | None:
    ""
    if rung is None:
        return probe.width(source)
    try:
        inspect.signature(probe.width).bind(source, rung)
    except (TypeError, ValueError):
        return None
    return cast("WidthProbe", probe).width(source, rung)


class CapacityError(Exception):
    ""


class SlotUnavailableError(CapacityError):
    ""


#
#at
#ng
#
type _Bound = tuple[str, str | None]


class _Claims:
    ""

    __slots__ = ("covering", "parent", "taken")

    def __init__(self, parent: _Claims | None = None) -> None:
        self.parent = parent
        self.taken: dict[_Bound, int] = {}
        self.covering: dict[_Bound, int] = {}


@dataclass(frozen=True)
class RungWidth:
    ""

    source: str
    limit: int
    confirmed: bool = False


@dataclass(frozen=True)
class Usage:
    ""

    source: str
    limit: int
    acquisitions: int
    peak: int
    waited_seconds: float
    rung: str | None = None

    @property
    def saturated(self) -> bool:
        ""
        return self.peak >= self.limit


@dataclass(frozen=True)
class Concurrency:
    ""

    peak: int
    """The most dispatches in flight at once, summed across every source."""

    total: int
    """The most that could ever be, if every source were saturated together."""

    @property
    def saturated(self) -> bool:
        ""
        return self.peak >= self.total


class Capacity:
    ""

    def __init__(
        self,
        limits: Mapping[str, int],
        *,
        lock_dir: Path | None = None,
        confirmed: Iterable[str] = (),
        declared: Mapping[str, int] | None = None,
        rungs: Mapping[str, RungWidth] | None = None,
        urls: Mapping[str, str] | None = None,
        reserved: Mapping[str, int] | None = None,
        queue_timeout_s: float | None = None,
        gauge: Gauge | None = None,
        busy: Callable[[str], int | None] | None = None,
    ) -> None:
        for source, limit in limits.items():
            if limit < 1:
                raise CapacityError(
                    f"unit {source!r} declares width={limit}, which "
                    f"would admit no dispatch at all. The config schema floors "
                    f"it at 1; a source that should not be used belongs out of "
                    f"the ladder, not at zero capacity."
                )
        self._limits = dict(limits)
        #
        #
        #en a
        #
        #
        #
        self._confirmed = frozenset(confirmed)
        unknown = ", ".join(sorted(self._confirmed - set(self._limits)))
        if unknown:
            raise CapacityError(
                f"confirmed width(s) for source(s) {unknown}, which this "
                f"capacity does not bound. A confirmation is a fact about a "
                f"source's limit, so there has to be a limit for it to be about."
            )
        #
        #
        #
        #
        # the
        #
        self._role_reserved = dict(reserved or {})
        unknown = ", ".join(sorted(set(self._role_reserved) - set(self._limits)))
        if unknown:
            raise CapacityError(
                f"reserved slot(s) for source(s) {unknown}, which this "
                f"capacity does not bound. A reservation is a claim against a "
                f"bound, so there has to be a bound for it to be about."
            )
        for source, count in self._role_reserved.items():
            if count < 0:
                raise CapacityError(
                    f"unit {source!r} reserves {count} slot(s), which is not "
                    f"a number of slots."
                )
        #
        # a
        #ed
        #
        #
        #
        #
        #he
        #
        #
        #
        self._declared = dict(self._limits)
        for source, width in dict(declared or {}).items():
            enforced = self._limits.get(source)
            if enforced is None:
                raise CapacityError(
                    f"a declared width for unit {source!r}, which this capacity "
                    f"does not bound. A declaration and a bound are two numbers "
                    f"about one unit, so there has to be a unit."
                )
            if width < 1:
                raise CapacityError(
                    f"unit {source!r} declares width={width}, which the "
                    f"config schema floors at 1. A capacity cannot be built from "
                    f"a declaration no config could have written."
                )
            physical = enforced + self._role_reserved.get(source, 0)
            if width > physical:
                raise CapacityError(
                    f"unit {source!r} declares width={width} but is bounded at "
                    f"{physical}. A width is only ever widened from its "
                    f"declaration and never narrowed — :meth:`of` refuses a "
                    f"machine reporting less rather than quietly lowering the "
                    f"bound — so a bound under the declaration is not something "
                    f"this module can have produced."
                )
            role_reserved = self._role_reserved.get(source, 0) > 0 and width == physical
            if (
                width != enforced
                and source not in self._confirmed
                and not role_reserved
            ):
                raise CapacityError(
                    f"unit {source!r} declares width={width} and is bounded at "
                    f"{enforced} without a confirmation. Only a machine's own "
                    f"report may widen a declaration, so two different numbers "
                    f"with nothing confirming them are two configs rather than "
                    f"one measurement."
                )
            self._declared[source] = width
        self._rungs = dict(rungs or {})
        for name, rung in self._rungs.items():
            if rung.limit < 1:
                raise CapacityError(
                    f"unit {name!r} declares width={rung.limit}, which "
                    f"would admit no dispatch at all. The config schema floors "
                    f"it at 1; a rung that should not be used belongs out of "
                    f"the ladder, not at zero capacity."
                )
            if rung.source not in self._limits:
                raise CapacityError(
                    f"unit {name!r} bounds unit {rung.source!r}, which this "
                    f"capacity does not bound. A rung's width is a width of the "
                    f"rig it runs on, so the rig has to be one this capacity "
                    f"knows."
                )
        #
        #
        # the
        #
        #
        self._urls = dict(urls or {})
        #
        #
        #s,
        #of
        #
        self._bounds: dict[_Bound, int] = {
            (source, None): limit + self._role_reserved.get(source, 0)
            for source, limit in self._limits.items()
        }
        for name, rung in self._rungs.items():
            self._bounds[(rung.source, name)] = rung.limit
        #
        #
        #
        #
        #
        #
        self._queue_timeout = queue_timeout_s
        #
        # —
        #
        #
        self._gauge = gauge
        #
        #
        #e.
        self._busy = busy
        self._lock_dir = lock_dir if lock_dir is not None else _default_lock_dir()
        #
        #
        #
        #
        #
        self._lock = threading.RLock()
        self._in_use = dict.fromkeys(self._bounds, 0)
        #
        #er
        #
        #
        #
        self._reserved = dict.fromkeys(self._bounds, 0)
        #
        #
        #
        #
        #
        self._covered = dict.fromkeys(self._bounds, 0)
        self._peak = dict.fromkeys(self._bounds, 0)
        #
        #
        #
        self._in_flight = 0
        self._in_flight_peak = 0
        self._acquisitions = dict.fromkeys(self._bounds, 0)
        self._waited = dict.fromkeys(self._bounds, 0.0)
        #
        #
        #
        #
        # a
        #
        self._holding = threading.local()

    @classmethod
    def of(
        cls,
        config: Config,
        *,
        probe: WidthProbe | SourceWidthProbe | None = None,
        root: Path | None = None,
        gauge: Gauge | None = None,
        busy: Callable[[str], int | None] | None = None,
    ) -> Capacity:
        ""
        limits: dict[str, int] = {}
        declarations: dict[str, int] = {}
        reserved: dict[str, int] = {}
        confirmed: list[str] = []
        orchestrator_name = config.get("orchestrator.unit")
        #
        #
        #
        #
        #��
        #
        #ef
        #
        orchestrator_unit = (
            config.units.get(orchestrator_name) if orchestrator_name else None
        )
        #
        #se
        #
        #
        role_orchestrator = (
            orchestrator_name
            if config.provisions_local_orchestrator
            and orchestrator_unit is not None
            and not orchestrator_unit.requires_credential
            else None
        )
        users = int(config.get("users", 1))
        #
        #
        #
        bounded = {**config.units, **config.relief}
        for name, unit in bounded.items():
            declared = unit.width or 1
            if name == role_orchestrator:
                #
                #
                #
                declared = unit.width or users
            declarations[name] = declared
            reported = None if probe is None else _reported(probe, name, None)
            if reported is None:
                #
                #
                enforced = declared
            elif reported < declared:
                raise CapacityError(
                    f"unit {name!r} declares {declared} but reports "
                    f"{reported}. Two answers to one question, and this time the "
                    f"machine gave one of them, so the config is the one that is "
                    f"wrong. Enforcing the declaration would not make the rig "
                    f"wider: a backend handed more concurrent requests than it "
                    f"has slots serializes them rather than refusing, so the "
                    f"over-declaration would show up as a rig that is merely "
                    f"slow and never as a config that is merely wrong. Declare "
                    f"{reported}, or start the backend with {declared} slots."
                )
            else:
                enforced = reported
                confirmed.append(name)
            if name == role_orchestrator:
                ladder = max(enforced - 1, 1)
                reserved[name] = enforced - ladder
                limits[name] = ladder
            else:
                limits[name] = enforced

        return cls(
            limits,
            lock_dir=root,
            confirmed=confirmed,
            declared=declarations,
            urls={name: unit.address for name, unit in bounded.items()},
            reserved=reserved,
            #
            #
            #
            queue_timeout_s=float(config.get("task_timeout_s")),
            gauge=gauge,
            busy=busy,
        )

    @property
    def limits(self) -> Mapping[str, int]:
        ""
        return dict(self._limits)

    def _bound(self, source: str, rung: str | None) -> _Bound:
        ""
        if rung is not None and (source, rung) in self._bounds:
            return (source, rung)
        return (source, None)

    def limit(self, source: str, rung: str | None = None) -> int:
        ""
        bound = self._bound(source, rung)
        if bound in self._bounds:
            #
            #
            #
            if bound[1] is not None:
                return self._bounds[bound]
            return self._limits[bound[0]]
        known = ", ".join(sorted(self._limits)) or "none"
        raise CapacityError(
            f"no declared capacity for unit {source!r}, so there is no "
            f"width to report for it. Known units: {known}"
        )

    def queue(self, source: str, rung: str | None = None) -> str | None:
        ""
        return self._bound(source, rung)[1]

    def confirmed(self, source: str, rung: str | None = None) -> bool:
        ""
        if source not in self._limits:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for unit {source!r}, so there is "
                f"nothing about it to have confirmed. Answering False here "
                f"would claim this capacity knows the unit and merely could "
                f"not confirm its width. Known units: {known}"
            )
        bound = self._bound(source, rung)
        if bound[1] is not None:
            return self._rungs[bound[1]].confirmed
        return source in self._confirmed

    def declared(self, source: str) -> int:
        ""
        self._bounded(source)
        return self._declared[source]

    @property
    def total(self) -> int:
        ""
        by_source: dict[str, int] = {}
        for rung in self._rungs.values():
            by_source[rung.source] = by_source.get(rung.source, 0) + rung.limit
        return sum(
            max(self._bounds[(source, None)], by_source.get(source, 0))
            for source in self._limits
        )

    def in_use(self, source: str) -> int:
        ""
        return self.in_flight(source)

    def in_flight(self, source: str, rung: str | None = None) -> int:
        ""
        self._bounded(source)
        with self._lock:
            return self._in_use[self._bound(source, rung)]

    def waiting(self, source: str, rung: str | None = None) -> int | None:
        ""
        self._bounded(source)
        if self._gauge is None:
            return None
        bound = self._bound(source, rung)
        stem = _slot_stem(self._urls.get(source, source), bound[1])
        return self._gauge.count(_waiting_key(stem))

    def queued(self, sources: Iterable[str]) -> int | None:
        ""
        named = set(sources)
        for source in named:
            self._bounded(source)
        if self._gauge is None:
            return None
        stems = {
            _slot_stem(self._urls.get(source, source), rung)
            for source, rung in self._bounds
            if source in named
        }
        total = 0
        for stem in sorted(stems):
            count = self._gauge.count(_waiting_key(stem))
            if count is None:
                return None
            total += count
        return total

    def load(self, source: str, rung: str | None = None) -> int:
        ""
        self._bounded(source)
        bound = self._bound(source, rung)
        with self._lock:
            #
            #
            #
            #
            waiting = self._reserved[bound] - self._covered[bound]
            return self._in_use[bound] + max(0, waiting)

    def fullness(self, source: str, rung: str | None = None) -> Fullness:
        ""
        return self.judge(source, rung, self.server_busy(source))

    def server_busy(self, source: str) -> int | None:
        ""
        self._bounded(source)
        return None if self._busy is None else self._busy(source)

    def judge(self, source: str, rung: str | None, server: int | None) -> Fullness:
        ""
        self._bounded(source)
        return Fullness(
            load=self.load(source, rung),
            server=server,
            width=self.limit(source, rung),
        )

    def reserve(self, source: str, rung: str | None = None) -> None:
        ""
        self._bounded(source)
        bound = self._bound(source, rung)
        with self._lock:
            self._reserved[bound] += 1
            mine = self._reservations().taken
            mine[bound] = mine.get(bound, 0) + 1

    def release(self, source: str, rung: str | None = None) -> None:
        ""
        bound = self._bound(source, rung)
        with self._lock:
            mine = self._reservations().taken
            held = mine.get(bound, 0)
            if held > 0:
                mine[bound] = held - 1
            current = self._reserved.get(bound, 0)
            if current > 0:
                self._reserved[bound] = current - 1

    @contextmanager
    def reserving(self, source: str, rung: str | None = None) -> Iterator[None]:
        ""
        self.reserve(source, rung)
        try:
            yield
        finally:
            self.release(source, rung)

    @contextmanager
    def deciding(self) -> Iterator[None]:
        ""
        with self._lock:
            yield

    def usage(self) -> tuple[Usage, ...]:
        ""
        with self._lock:
            return tuple(
                Usage(
                    source=bound[0],
                    rung=bound[1],
                    limit=limit,
                    acquisitions=self._acquisitions[bound],
                    peak=self._peak[bound],
                    waited_seconds=round(self._waited[bound], 6),
                )
                for bound, limit in self._bounds.items()
            )

    def concurrency(self) -> Concurrency:
        ""
        with self._lock:
            return Concurrency(peak=self._in_flight_peak, total=self.total)

    @contextmanager
    def hold(
        self,
        source: Endpoint | str,
        *,
        rung: str | None = None,
        timeout: float | None = None,
    ) -> Iterator[None]:
        ""
        #
        #
        #
        #
        #
        if timeout is None:
            timeout = self._queue_timeout
        endpoint = None if isinstance(source, str) else source
        name = source if isinstance(source, str) else source.source
        if name not in self._limits:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for unit {name!r} — this capacity and "
                f"the source map it is bounding were built from different "
                f"configs. Known units: {known}"
            )
        declared = self._declared[name]
        if endpoint is not None and endpoint.max_parallel != declared:
            if self._limits[name] == declared:
                widened = ""
            elif self._role_reserved.get(name, 0):
                widened = (
                    f" (This source reserves {self._role_reserved[name]} "
                    f"slot(s) for its role, so the ladder-facing width is "
                    f"{self._limits[name]}; an endpoint still carries the "
                    f"served width, so {declared} is what it has to agree "
                    f"with.)"
                )
            else:
                widened = (
                    f" (A probe widened this source to {self._limits[name]}, "
                    f"which is what is enforced; an endpoint still carries the "
                    f"declared number, so {declared} is what it has to agree "
                    f"with.)"
                )
            raise CapacityError(
                f"unit {name!r} is bounded at {declared} here "
                f"but the endpoint declares width="
                f"{endpoint.max_parallel}. Two answers to one question means one "
                f"of them is from a stale config; rebuild both from the same "
                f"one.{widened}"
            )
        bound = self._bound(name, rung)
        limit = self._bounds[bound]
        if rung is not None and bound[1] is None:
            #
            #
            #
            #
            #
            #
            limit = self._limits[name]
        where = f"unit {bound[1]!r} of unit {name!r}" if bound[1] else f"unit {name!r}"
        #
        #
        #
        base_url = (
            endpoint.base_url if endpoint is not None else self._urls.get(name, name)
        )
        #
        #
        #
        stem = _slot_stem(base_url, bound[1])
        held = self._held()
        if stem in held:
            raise CapacityError(
                f"this thread already holds a slot on {where}, or on a unit "
                f"that shares its address. A "
                f"nested dispatch to it waits for a slot the waiter "
                f"is itself holding, so at the default width of 1 it would "
                f"deadlock silently. Finish the outer dispatch first."
            )

        started = time.monotonic()
        fd = self._acquire_slot(where, base_url, bound[1], limit, timeout)
        waited = time.monotonic() - started
        held.add(stem)
        with self._lock:
            self._acquisitions[bound] += 1
            self._waited[bound] += waited
            self._in_use[bound] += 1
            self._peak[bound] = max(self._peak[bound], self._in_use[bound])
            self._in_flight += 1
            self._in_flight_peak = max(self._in_flight_peak, self._in_flight)
            #
            #: it
            #
            #
            #
            # a
            #
            #
            #
            covering: _Claims | None = self._reservations()
            while covering is not None and covering.taken.get(
                bound, 0
            ) <= covering.covering.get(bound, 0):
                covering = covering.parent
            if covering is not None:
                covering.covering[bound] = covering.covering.get(bound, 0) + 1
                self._covered[bound] += 1
        try:
            yield
        finally:
            with self._lock:
                self._in_use[bound] -= 1
                self._in_flight -= 1
                if covering is not None:
                    covering.covering[bound] -= 1
                    self._covered[bound] -= 1
            held.discard(stem)
            os.close(fd)  #

    @contextmanager
    def drain(
        self, sources: Iterable[str], *, timeout: float | None = None
    ) -> Iterator[None]:
        ""
        named = sorted(set(sources))
        for source in named:
            self._bounded(source)
        wanted = sorted(
            (bound for bound in self._bounds if bound[0] in set(named)),
            key=lambda bound: (bound[0], bound[1] or ""),
        )
        taken: list[int] = []
        #
        #
        #
        locked: set[tuple[str, int]] = set()
        try:
            for source, rung in wanted:
                base_url = self._urls.get(source, source)
                stem = _slot_stem(base_url, rung)
                for index in range(self._bounds[(source, rung)]):
                    if (stem, index) in locked:
                        continue
                    locked.add((stem, index))
                    taken.append(
                        self._acquire_one(
                            f"unit {source!r}" + (f" rung {rung!r}" if rung else ""),
                            base_url,
                            rung,
                            index,
                            timeout,
                        )
                    )
            yield
        finally:
            for fd in taken:
                os.close(fd)  #

    def _acquire_one(
        self,
        where: str,
        base_url: str,
        rung: str | None,
        index: int,
        timeout: float | None,
    ) -> int:
        ""
        directory = self._lock_dir
        directory.mkdir(parents=True, exist_ok=True)
        stem = _slot_stem(base_url, rung)
        deadline = None if timeout is None else time.monotonic() + timeout
        fd = os.open(directory / f"{stem}.{index}.slot", os.O_RDWR | os.O_CREAT)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                if deadline is not None and time.monotonic() >= deadline:
                    os.close(fd)
                    raise SlotUnavailableError(
                        f"{where} slot {index} was still in use after "
                        f"{timeout}s, so the card was not drained and nothing "
                        f"was taken down. A dispatch that is already admitted "
                        f"is never interrupted by a sleep."
                    ) from None
                time.sleep(_POLL_SECONDS)
                continue
            return fd

    def _acquire_slot(
        self,
        where: str,
        base_url: str,
        rung: str | None,
        limit: int,
        timeout: float | None,
    ) -> int:
        ""
        directory = self._lock_dir
        directory.mkdir(parents=True, exist_ok=True)
        stem = _slot_stem(base_url, rung)
        deadline = None if timeout is None else time.monotonic() + timeout
        with ExitStack() as queued:
            announced = False
            while True:
                for index in range(limit):
                    fd = os.open(
                        directory / f"{stem}.{index}.slot", os.O_RDWR | os.O_CREAT
                    )
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except OSError:
                        os.close(fd)
                        continue
                    return fd
                if deadline is not None and time.monotonic() >= deadline:
                    raise SlotUnavailableError(
                        f"{where} has all {limit} declared slot(s) in use "
                        f"host-wide and none freed within {timeout}s. The bound "
                        f"counts every mcgyvr process on this host; a longer or "
                        f"absent timeout queues instead of refusing."
                    )
                if self._gauge is not None and not announced:
                    queued.enter_context(self._gauge.present(_waiting_key(stem)))
                    announced = True
                time.sleep(_POLL_SECONDS)

    def _bounded(self, source: str) -> None:
        ""
        if source not in self._limits:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for unit {source!r} — this capacity and "
                f"the caller's view of the ladder were built from different "
                f"configs. Known units: {known}"
            )

    def _held(self) -> set[str]:
        ""
        stems: set[str] | None = getattr(self._holding, "stems", None)
        if stems is None:
            stems = set()
            self._holding.stems = stems
        return stems

    @contextmanager
    def _inheriting(self, parent: _Claims) -> Iterator[None]:
        ""
        previous = getattr(self._holding, "reserved", None)
        self._holding.reserved = _Claims(parent)
        try:
            yield
        finally:
            self._holding.reserved = previous

    def _reservations(self) -> _Claims:
        ""
        mine: _Claims | None = getattr(self._holding, "reserved", None)
        if mine is None:
            mine = _Claims()
            self._holding.reserved = mine
        return mine


@dataclass(frozen=True)
class Outcome[T]:
    ""

    index: int
    value: T | None = None
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def run_batch[T](
    jobs: Sequence[Callable[[Capacity], T]],
    capacity: Capacity,
    *,
    workers: int | None = None,
) -> tuple[Outcome[T], ...]:
    ""
    if not jobs:
        return ()
    limit = workers if workers is not None else capacity.total
    if limit < 1:
        raise CapacityError(f"workers={limit} would run nothing; ask for at least 1")

    #
    #
    #
    parent = capacity._reservations()

    def adopted(job: Callable[[Capacity], T]) -> T:
        with capacity._inheriting(parent):
            return job(capacity)

    with ThreadPoolExecutor(max_workers=limit) as pool:
        futures = [pool.submit(adopted, job) for job in jobs]
        outcomes: list[Outcome[T]] = []
        for index, future in enumerate(futures):
            error = future.exception()
            if error is None:
                outcomes.append(Outcome(index=index, value=future.result()))
            elif isinstance(error, Exception):
                outcomes.append(Outcome(index=index, error=error))
            else:
                #
                #
                #
                raise error
    return tuple(outcomes)
