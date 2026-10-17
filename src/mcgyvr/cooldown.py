"""Sources that answer and still do not work are held out for a while.

:class:`Cooldown` answers one question for the routing layer: which of these
sources should not be dispatched to right now. Two kinds of source are named.
The probe from :mod:`mcgyvr.availability` reports the ones whose port does not
answer or which refuse to serve; this module adds the ones the probe calls
live but whose dispatches keep failing. ``threshold`` failures in a row arm a
``cooldown_s`` sentence, during which the source is reported unavailable with
a reason naming the streak and the seconds left. A success ends the streak but
does not shorten an armed sentence. When a ``shared`` record is supplied, an
armed sentence is also written there so other processes on the host hold the
source out, and a hold written by another process is reported the same way.
"""

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

# Consecutive dispatch failures that arm a cooldown, and the default for
# ``threshold``. The constructor refuses anything below two: a source dropped
# on a single failure is lost to one hiccup.
CONSECUTIVE_FAILURES = 3

# Seconds a source stays out of the ladder once its sentence is armed, used as
# the default ``cooldown_s``. Measured on the injected clock (monotonic unless
# another one is passed in), so a wall-clock jump neither shortens nor
# stretches it.
COOLDOWN_S = 60.0


class SharedHold(Protocol):
    """Where a cooldown is published for the other processes on the host.

    ``hold`` records that ``source`` is out for ``seconds``; ``held`` returns
    the seconds still left on such a record, or ``None`` when the source is not
    held. :class:`Cooldown` asks nothing else of it, and treats a ``None`` from
    ``held`` as "no hold".
    """

    def hold(self, source: str, seconds: float) -> None: ...

    def held(self, source: str) -> float | None: ...


@dataclass
class _Record:
    """One source's failure streak, and when an armed sentence runs out.

    ``failures`` counts dispatches that failed in a row. ``until`` is a reading
    of the injected clock at which the cooldown ends, or ``0.0`` while no
    sentence is armed.
    """

    failures: int = 0
    until: float = 0.0


class Cooldown:
    """Which sources should not be dispatched to, and why.

    :meth:`unavailable` answers for a batch of endpoints: a source is named
    when the probe calls it dead, when it has failed ``threshold`` dispatches
    in a row and the ``cooldown_s`` sentence has not run out, or when a
    ``shared`` record holds it out. Reasons are prose meant for the report;
    sources that are fine are absent from the result.

    In-process state is one :class:`_Record` per source name, mutated under an
    instance lock. Expired sentences are dropped by whichever lookup notices
    them, so nothing sweeps in the background.
    """

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
        # Serialises the read-modify-write of ``_records`` in
        # ``record_failure`` and ``record_success``, so two threads counting
        # failures on one source cannot lose an increment. ``unavailable``
        # reads and expires the same dict without taking it, and the shared
        # record is written after the lock is released.
        self._lock = threading.Lock()

    @property
    def verdicts(self) -> Mapping[str, AvailabilityVerdict]:
        """The probe verdicts gathered so far, keyed by source name.

        A snapshot held by the wrapped ``Availability``: asking for it probes
        nothing new.
        """
        return self._liveness.verdicts

    def record_failure(self, source: str) -> None:
        """Count one failed dispatch against ``source``.

        The failure streak grows by one. Reaching ``threshold`` arms the
        sentence: ``until`` is stamped ``cooldown_s`` from now, and if a
        ``shared`` record was given, the same sentence is written there for the
        other processes on the host. A failure recorded inside an armed
        sentence restamps it, so a source that keeps failing while cooling
        stays out.
        """
        with self._lock:
            record = self._records.setdefault(source, _Record())
            record.failures += 1
            sentenced = record.failures >= self._threshold
            if sentenced:
                record.until = self._clock() + self._cooldown_s
        # Taken outside the lock: the shared hold writes a file, and threads
        # recording failures on other sources have no reason to wait on that.
        if sentenced and self._shared is not None:
            self._shared.hold(source, self._cooldown_s)

    def record_success(self, source: str) -> None:
        """Count one successful dispatch against ``source``.

        An armed sentence is left in place while its streak goes back to zero,
        so the cooldown still has to run out before the source is offered
        again. A source that is not cooling is forgotten outright: the count is
        of *consecutive* failures, and one success ends the streak.
        """
        with self._lock:
            record = self._records.get(source)
            if record is not None and record.until > 0.0:
                record.failures = 0
                return
            self._records.pop(source, None)

    def unavailable(self, endpoints: Sequence[Endpoint]) -> Mapping[str, str]:
        """The endpoints that must not be dispatched to, each with a reason.

        Starts from the sources the probe calls dead, then adds those cooling
        down here or held out through the ``shared`` record, keeping the first
        reason found for a source. Sources missing from the result are the ones
        still worth a dispatch.
        """
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
        """The shared record's reason for holding ``source`` out, if any.

        ``None`` when no ``shared`` record was given or it holds nothing for
        this source.
        """
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
        """The local cooldown reason for ``source`` at ``now``, if in force.

        A record whose sentence has run out is deleted here and reported as not
        cooling, so the dict does not keep sources that are serviceable again.
        ``None`` means no record, or a record with nothing armed.
        """
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
