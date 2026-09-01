"""Does it actually work — per-source failure history, learned from dispatches.

mcgyvr knows two things about a source and this is neither.
:class:`~mcgyvr.availability.Availability` asks *is anything there*, once, and
caches the answer for the life of a run. :class:`~mcgyvr.capacity.Capacity` asks
*is there room*, and bounds how many dispatches a source carries at once. Between
them sits the source that is reachable, uncontended, and does not work: it answers
the model-list path, accepts the connection, takes the slot, and fails the
generation. Every rung on it is handed to a dispatch that fails the same way, and
nothing in the run ever revises the verdict — because the verdict was reached
before the first dispatch and is never asked again.

This module revises it. A :class:`Cooldown` is an availability view that also
*learns*: it wraps a probe exactly as :class:`~mcgyvr.availability.Availability`
does, answers the same one-method question :func:`mcgyvr.pool.source_map` asks,
and additionally accepts the one fact a probe cannot produce — that a dispatch
against this source failed.

**Why the knowledge is free.** The removal costs no probe. A source taken out here
was taken out by the record of its failures, which the run already paid for at
dispatch; re-probing to reach the same conclusion would spend a connect timeout
per escalation, the exact cost :mod:`mcgyvr.availability` caches to avoid. So a
``Cooldown`` never probes on account of a failure — it asks its wrapped
availability the same question it would have asked anyway, and overlays what the
dispatches taught it.

**Why it takes several failures, and why it ends.** Two failure modes bound the
design from either side, and both are worse than doing nothing:

* *Drop a source on its first bad generation* and one truncated reply, one
  transient 502, one model still loading costs the whole remaining ladder on that
  host. So the count must be consecutive and it must be more than one;
  :data:`CONSECUTIVE_FAILURES` is three, ported from local-ai's pool, and a
  success clears the count because "consecutive" is what makes three failures
  evidence rather than an accumulated grudge.
* *Never give it back* and a backend restarting, a model being swapped in, or a
  machine waking turns a transient fault into a permanent one for the rest of the
  run. So the removal expires: :data:`COOLDOWN_S` after the most recent failure
  the source is offered again, with a clean count, because a failure from before a
  served cooldown is not evidence about the dispatch after it.

**Below the seam.** Like :mod:`mcgyvr.availability`, whose place on the ladder
this takes, the module reads :class:`mcgyvr.pool.Endpoint` — one field of it,
``source`` — and so belongs with ``pool``, ``runner``, ``availability`` and
``capacity`` on the below-the-seam list ``tests/test_pool.py`` keeps. It binds
nothing, dispatches nothing, and never sees a URL or a protocol, so re-pointing a
rung remains a config edit.

**What it is keyed on, and what that cannot catch.** A *source*, not a
source-and-model pair — which is what local-ai keys on (``pool.py:712``). The seam
that consumes this (:class:`mcgyvr.pool.SourceProbe`) answers per source name, so
a per-rung record would have nowhere to be reported and :func:`mcgyvr.pool.source_map`
would have to learn something new to read it. The cost is real and worth stating:
one broken *model* on an otherwise healthy host takes the host's other rungs with
it. That trade is the right way round for the fault this exists for — a host whose
generations fail is the common case, and a ladder is cheap to re-climb — but it is
a trade, not a free win.

**What this is not.** It is not a retry policy: it says which sources are worth
offering, never how many attempts a contract gets, which is escalation's. It is not
a circuit breaker across runs — like ``Availability``, one instance is for one run,
and the state dies with it. And it does not decide what counts as a failure. The
dispatcher does, and calls :meth:`Cooldown.record_failure`; a refusal the worker
produced correctly is not this module's business.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from mcgyvr.availability import (
    PROBE_TIMEOUT_S,
    Availability,
    AvailabilityVerdict,
    ProbeFn,
)
from mcgyvr.pool import Endpoint

# How many failures in a row before a source is taken out. Three, from local-ai's
# `pool.py:712-719`. Not one, for the reason in the module docstring; not so many
# that a source which is genuinely broken serves the whole ladder first.
CONSECUTIVE_FAILURES = 3

# How long the source stays out, from its most recent failure. Sixty seconds is
# the same port, and it is chosen against what recovers on its own: a backend
# restart, a model load, a machine waking. Long enough that the ladder does not
# spend the interval re-discovering the fault, short enough that a run outlives it.
COOLDOWN_S = 60.0


@dataclass
class _Record:
    """One source's failure history: how many in a row, and until when it is out.

    ``until`` is a reading of the injected clock, not a duration, so expiry is a
    comparison rather than a countdown that something has to tick. Zero means the
    source has failures against it but has not reached the threshold — it is still
    being offered.
    """

    failures: int = 0
    until: float = 0.0


class Cooldown:
    """Liveness for one run, revised by what dispatches against it did.

    Satisfies :class:`mcgyvr.pool.SourceProbe` structurally, so it goes wherever
    an :class:`~mcgyvr.availability.Availability` goes and :mod:`mcgyvr.pool`
    learns nothing new. Construct one per run and hold it for exactly as long —
    the failure record and the wrapped liveness cache have the same lifetime and
    the same reason for it.

    ``probe`` is passed straight through to the availability this wraps, so a
    caller supplies its own transport (or a stub) the same way it always could.
    ``clock`` is injected for the same reason a probe is: a cooldown asserted by
    sleeping is a slow test that is also flaky. It must be monotonic — the default
    is :func:`time.monotonic` — because a wall clock stepping backwards over an
    NTP correction would hold a source out for longer than it was ever sentenced.
    """

    def __init__(
        self,
        probe: ProbeFn | None = None,
        clock: Callable[[], float] = time.monotonic,
        cooldown_s: float = COOLDOWN_S,
        threshold: int = CONSECUTIVE_FAILURES,
        timeout_s: float = PROBE_TIMEOUT_S,
    ) -> None:
        if cooldown_s <= 0:
            raise ValueError(f"cooldown_s must be positive, got {cooldown_s}")
        if threshold < 2:
            raise ValueError(
                f"threshold must be at least 2, got {threshold}: a source dropped on "
                f"one failure loses the rest of the ladder to a single hiccup"
            )
        self._liveness = Availability(timeout_s=timeout_s, probe=probe)
        self._clock = clock
        self._cooldown_s = cooldown_s
        self._threshold = threshold
        self._records: dict[str, _Record] = {}

    @property
    def verdicts(self) -> Mapping[str, AvailabilityVerdict]:
        """Every liveness verdict reached so far — the wrapped cache, unchanged.

        Delegated rather than reimplemented so anything reporting on probes reads
        the same thing whether it was handed a ``Cooldown`` or an ``Availability``.
        Failures are deliberately absent from it: a verdict is what a probe found,
        and inventing one this module reached by another route would make the two
        indistinguishable in a report.
        """
        return self._liveness.verdicts

    def record_failure(self, source: str) -> None:
        """One dispatch against ``source`` failed.

        The threshold is re-armed on every failure past it, not only on the one
        that crossed it, so the cooldown is measured from the most recent failure.
        A source failing steadily is not handed back while it is still failing.
        """
        record = self._records.setdefault(source, _Record())
        record.failures += 1
        if record.failures >= self._threshold:
            record.until = self._clock() + self._cooldown_s

    def record_success(self, source: str) -> None:
        """One dispatch against ``source`` worked, so the streak is over.

        This is what makes the count *consecutive*. Without it, a source that
        failed twice in the first minute and twice in the tenth would be taken out
        on evidence that was never about the same fault.

        A cooldown already armed is not cancelled. Three consecutive failures
        earn the sentence, and a success arriving during it came from a dispatch
        started *before* those failures — it is not evidence the source
        recovered, and clearing the sentence would let a healthy rung that
        happened to be in flight wipe a broken one's just-earned removal, which
        is the single-host install's form of this defect. The count resets; the
        sentence stands.
        """
        record = self._records.get(source)
        if record is not None and record.until > 0.0:
            record.failures = 0
            return
        self._records.pop(source, None)

    def unavailable(self, endpoints: Sequence[Endpoint]) -> Mapping[str, str]:
        """Which of these sources cannot serve, and why — the pool's seam.

        The union of two facts. A source the probe says is down is down, and that
        answer is given first because it is the more fundamental one: a host that
        is not answering explains its own failures. A source the probe says is live
        but whose dispatches keep failing is *also* unavailable, and its reason
        names the failures — a caller reading a shortened ladder has to be able to
        tell "it kept failing, wait" from "it was never configured" from "the probe
        said it was down", because those want three different responses.
        """
        down = dict(self._liveness.unavailable(endpoints))
        now = self._clock()
        for endpoint in endpoints:
            if endpoint.source in down:
                continue
            cooling = self._cooling(endpoint.source, now)
            if cooling is not None:
                down[endpoint.source] = cooling
        return down

    def _cooling(self, source: str, now: float) -> str | None:
        """Why ``source`` is being held out at ``now``, or ``None`` if it is not.

        Expiry is settled here, on the read, rather than by anything sweeping the
        records: the only moment a cooldown's end matters is when someone asks
        whether the source may be offered. The record is dropped rather than kept
        with its count, so a source that has served its cooldown comes back even
        with the rest of the ladder.
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
