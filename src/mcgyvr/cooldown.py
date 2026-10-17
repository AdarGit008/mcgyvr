""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from mcgyvr.availability import (
    PROBE_TIMEOUT_S,
    Availability,
    AvailabilityVerdict,
    ProbeFn,
)
from mcgyvr.local_pool import Endpoint

#
#
#
CONSECUTIVE_FAILURES = 3

#
#
#
#
COOLDOWN_S = 60.0


class SharedHold(Protocol):
    ""

    def hold(self, source: str, seconds: float) -> None: ...

    def held(self, source: str) -> float | None: ...


@dataclass
class _Record:
    ""

    failures: int = 0
    until: float = 0.0


class Cooldown:
    ""

    def __init__(
        self,
        probe: ProbeFn | None = None,
        clock: Callable[[], float] = time.monotonic,
        cooldown_s: float = COOLDOWN_S,
        threshold: int = CONSECUTIVE_FAILURES,
        timeout_s: float = PROBE_TIMEOUT_S,
        shared: SharedHold | None = None,
    ) -> None:
        if cooldown_s <= 0:
            raise ValueError(f"cooldown_s must be positive, got {cooldown_s}")
        if threshold < 2:
            raise ValueError(
                f"threshold must be at least 2, got {threshold}: a source dropped on "
                f"one failure is lost to a single hiccup"
            )
        self._liveness = Availability(timeout_s=timeout_s, probe=probe)
        self._clock = clock
        self._cooldown_s = cooldown_s
        self._threshold = threshold
        self._records: dict[str, _Record] = {}
        self._shared = shared
        #
        #
        #
        #e.
        #
        self._lock = threading.Lock()

    @property
    def verdicts(self) -> Mapping[str, AvailabilityVerdict]:
        ""
        return self._liveness.verdicts

    def record_failure(self, source: str) -> None:
        ""
        with self._lock:
            record = self._records.setdefault(source, _Record())
            record.failures += 1
            sentenced = record.failures >= self._threshold
            if sentenced:
                record.until = self._clock() + self._cooldown_s
        #
        #
        if sentenced and self._shared is not None:
            self._shared.hold(source, self._cooldown_s)

    def record_success(self, source: str) -> None:
        ""
        with self._lock:
            record = self._records.get(source)
            if record is not None and record.until > 0.0:
                record.failures = 0
                return
            self._records.pop(source, None)

    def unavailable(self, endpoints: Sequence[Endpoint]) -> Mapping[str, str]:
        ""
        down = dict(self._liveness.unavailable(endpoints))
        now = self._clock()
        for endpoint in endpoints:
            if endpoint.source in down:
                continue
            cooling = self._cooling(endpoint.source, now)
            if cooling is None:
                cooling = self._held(endpoint.source)
            if cooling is not None:
                down[endpoint.source] = cooling
        return down

    def _held(self, source: str) -> str | None:
        ""
        if self._shared is None:
            return None
        left = self._shared.held(source)
        if left is None:
            return None
        return (
            f"source {source!r} failed for another process on this host, which "
            f"held it out for everyone; another {left:.0f}s before it is offered "
            f"again"
        )

    def _cooling(self, source: str, now: float) -> str | None:
        ""
        record = self._records.get(source)
        if record is None or record.until == 0.0:
            return None
        if now >= record.until:
            del self._records[source]
            return None
        return (
            f"source {source!r} failed {record.failures} dispatches in a row; it is "
            f"cooling down for another {record.until - now:.0f}s before it is "
            f"offered again. The probe still reports it reachable, so this is a "
            f"source that answers and does not work"
        )
