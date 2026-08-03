"""Capacity — how many dispatches a source may have in flight at once (#23).

A source is a machine, and a machine has a finite number of requests it can
serve at a time. That number is declared in the config (``max_parallel``) and
was, until now, carried and not enforced: :mod:`mcgyvr.pool` puts it on every
:class:`~mcgyvr.pool.Endpoint` and says in its own docstring that the semaphore
is this issue's. This is the semaphore.

Four decisions shape it, and the first is the one the acceptance turns on:

* **Capacity is per source, and it is acquired around the dispatch — not around
  the task.** A ladder of four rungs on one machine is four names for one card,
  so the bound has to be keyed by the source rather than the rung or the model.
  And because a slot is held only for the length of one request, a task that
  escalates from a local rung to an API rung holds the local source's slot while
  it is talking to the local source and not a moment longer. "Escalation does not
  leak or double-count capacity" is therefore a property of *where* the
  acquisition sits, not of bookkeeping that has to be kept right — there is no
  per-task ledger to get wrong, because a task never owns a slot.
* **A bound nobody can see is indistinguishable from no bound.** :class:`Usage`
  reports, per source, how many acquisitions there were, the peak concurrency
  actually reached, and how long callers spent *waiting* for a slot. The last is
  the one an operator needs: a source whose wait time dominates its service time
  is a declared capacity that is throttling the batch, and nothing else in the
  system would say so.
* **A nested acquisition of the same source raises rather than deadlocks.** At
  ``max_parallel: 1`` — the default :mod:`mcgyvr.initialize` writes — a job that
  dispatched to a source from inside a dispatch to that same source would block
  forever against itself, with no output and no traceback. That is the worst
  failure this module could have, so it is detected and named.
* **The unit of a batch is a job, not a contract.** Executing a contract means
  choosing a rung, assembling a prompt, parsing a reply and escalating on
  failure, which are #24's and #25's. What #23 owes them is a bounded way to run
  many things at once; supplying a contract loop here would be inventing the
  escalation policy #24 exists to decide.

**CON-02, which is why a number here is not a promise.** The capability table
measured same-model concurrency at 1.6-3.1x *with the backend's parallel-slot
setting enabled*, and recorded that a single-slot server serializes the requests
rather than refusing them. So a source declared ``max_parallel: 4`` in front of a
single-slot backend will accept four dispatches, run them one after another, and
look from here exactly like a source that is merely slow. This module enforces
the declaration; it cannot enforce the server. :func:`mcgyvr.propose.propose`
says so where an operator will read it, and :attr:`Usage.waited_seconds` is where
the symptom shows up afterwards.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config
    from mcgyvr.pool import Endpoint


class CapacityError(Exception):
    """A slot could not be taken, and running unbounded would be worse."""


@dataclass(frozen=True)
class Usage:
    """What one source's capacity was actually used for.

    ``peak`` is the highest number of dispatches observed in flight at once, so
    a peak below the limit means the batch never had enough work to saturate the
    source and a peak equal to it means the limit was reached — which is the
    difference between "capacity is fine" and "capacity is the ceiling".
    ``waited_seconds`` is the total time callers spent blocked on a slot, summed
    across threads; it is the cost of the limit, stated rather than implied.
    """

    source: str
    limit: int
    acquisitions: int
    peak: int
    waited_seconds: float

    @property
    def saturated(self) -> bool:
        """Whether every slot was in use at once at some point."""
        return self.peak >= self.limit


class Capacity:
    """Per-source semaphores, and the record of what they cost.

    Built from a :class:`~mcgyvr.config.Config` with :meth:`of`, so the limits
    enforced are the ones the operator declared and there is no second place a
    capacity can be written down. Safe to share across threads; that is the
    entire point of it.
    """

    def __init__(self, limits: Mapping[str, int]) -> None:
        for source, limit in limits.items():
            if limit < 1:
                raise CapacityError(
                    f"source {source!r} declares max_parallel={limit}, which "
                    f"would admit no dispatch at all. The config schema floors "
                    f"it at 1; a source that should not be used belongs out of "
                    f"the ladder, not at zero capacity."
                )
        self._limits = dict(limits)
        self._slots = {
            source: threading.BoundedSemaphore(limit)
            for source, limit in self._limits.items()
        }
        self._lock = threading.Lock()
        self._in_use = dict.fromkeys(self._limits, 0)
        self._peak = dict.fromkeys(self._limits, 0)
        self._acquisitions = dict.fromkeys(self._limits, 0)
        self._waited = dict.fromkeys(self._limits, 0.0)
        # Which sources *this* thread is currently holding. Thread-local rather
        # than shared, because the question it answers is "would this caller
        # block against itself", which is a per-thread question.
        self._holding = threading.local()

    @classmethod
    def of(cls, config: Config) -> Capacity:
        """The capacities this config declares, for every source it declares.

        Every source, not only the ones the ladder currently uses: a role
        binding (orchestrator, verifier) dispatches against a source that need
        not appear in any tier, and a capacity that did not cover it would raise
        at the moment it was first used.
        """
        return cls(
            {name: source.max_parallel for name, source in config.sources.items()}
        )

    @property
    def limits(self) -> Mapping[str, int]:
        """The declared capacity of each source."""
        return dict(self._limits)

    @property
    def total(self) -> int:
        """The most dispatches that could ever be in flight across all sources."""
        return sum(self._limits.values())

    def in_use(self, source: str) -> int:
        """How many slots of ``source`` are held right now."""
        with self._lock:
            return self._in_use[source]

    def usage(self) -> tuple[Usage, ...]:
        """What each source's capacity was used for, in declared order."""
        with self._lock:
            return tuple(
                Usage(
                    source=source,
                    limit=limit,
                    acquisitions=self._acquisitions[source],
                    peak=self._peak[source],
                    waited_seconds=round(self._waited[source], 6),
                )
                for source, limit in self._limits.items()
            )

    @contextmanager
    def hold(self, endpoint: Endpoint) -> Iterator[None]:
        """Hold one of ``endpoint``'s source's slots for the body of the block.

        Blocks until a slot is free. The slot is released on the way out however
        the body leaves — a backend that times out or refuses must not cost the
        source a slot for the rest of the run, which is the leak the acceptance
        names.

        Raises :class:`CapacityError` rather than proceeding when the source is
        one this capacity does not know, when the endpoint's declared
        ``max_parallel`` disagrees with the one being enforced (both of which
        mean the capacity and the source map were built from different configs),
        or when the calling thread already holds this source.
        """
        source = endpoint.source
        slot = self._slots.get(source)
        if slot is None:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for source {source!r} — this capacity and "
                f"the source map it is bounding were built from different "
                f"configs. Known sources: {known}"
            )
        if endpoint.max_parallel != self._limits[source]:
            raise CapacityError(
                f"source {source!r} is bounded at {self._limits[source]} here "
                f"but the endpoint declares max_parallel="
                f"{endpoint.max_parallel}. Two answers to one question means one "
                f"of them is from a stale config; rebuild both from the same one."
            )
        held = self._held()
        if source in held:
            raise CapacityError(
                f"this thread already holds a slot on source {source!r}. A "
                f"nested dispatch to the same source waits for a slot the waiter "
                f"is itself holding, so at the default max_parallel=1 it would "
                f"deadlock silently. Finish the outer dispatch first."
            )

        started = time.monotonic()
        slot.acquire()
        waited = time.monotonic() - started
        held.add(source)
        with self._lock:
            self._acquisitions[source] += 1
            self._waited[source] += waited
            self._in_use[source] += 1
            self._peak[source] = max(self._peak[source], self._in_use[source])
        try:
            yield
        finally:
            with self._lock:
                self._in_use[source] -= 1
            held.discard(source)
            slot.release()

    def _held(self) -> set[str]:
        """The sources this thread holds, created on first use per thread."""
        sources: set[str] | None = getattr(self._holding, "sources", None)
        if sources is None:
            sources = set()
            self._holding.sources = sources
        return sources


@dataclass(frozen=True)
class Outcome[T]:
    """What one job of a batch produced, or the exception it raised instead.

    A failing job does not sink the batch, for the same reason a refused
    proposal does not sink a decomposition: a batch of twenty contracts where
    one endpoint hiccuped should return nineteen results and one named failure,
    not a traceback and nothing. ``ok`` is what a caller must consult, so a
    failure cannot be mistaken for a ``None`` result.
    """

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
    """Run ``jobs`` concurrently, bounded by ``capacity``, results in input order.

    Each job is handed the capacity it must dispatch under. Passing it rather
    than letting a job close over one is deliberate: a job that dispatches
    without holding a slot silently breaks the only guarantee this module
    offers, and the signature is the one place that can put the thing it needs
    into its hand.

    ``workers`` defaults to :attr:`Capacity.total` — the most dispatches that
    could ever be in flight. More threads than that cannot make anything run
    sooner; they can only queue on a semaphore, at the price of a stack each.
    A caller whose jobs do substantial work *between* dispatches (applying a
    diff, running a gate) may reasonably want more, which is why it is a
    parameter rather than a constant.

    Returns one :class:`Outcome` per job, in the order the jobs were given,
    whatever order they finished in — a batch whose results were ordered by
    completion would be reproducible only on a quiet machine.
    """
    if not jobs:
        return ()
    limit = workers if workers is not None else capacity.total
    if limit < 1:
        raise CapacityError(f"workers={limit} would run nothing; ask for at least 1")

    with ThreadPoolExecutor(max_workers=limit) as pool:
        futures = [pool.submit(job, capacity) for job in jobs]
        outcomes: list[Outcome[T]] = []
        for index, future in enumerate(futures):
            error = future.exception()
            if error is None:
                outcomes.append(Outcome(index=index, value=future.result()))
            elif isinstance(error, Exception):
                outcomes.append(Outcome(index=index, error=error))
            else:
                # KeyboardInterrupt and SystemExit are not a job's failure to
                # report; swallowing one into an Outcome would make Ctrl-C look
                # like a bad contract.
                raise error
    return tuple(outcomes)
