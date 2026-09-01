"""Capacity — how many dispatches a source may have in flight at once (#23).

A source is a machine, and a machine has a finite number of requests it can
serve at a time. That number is declared in the config (``max_parallel``) and
was, until now, carried and not enforced: :mod:`mcgyvr.pool` puts it on every
:class:`~mcgyvr.pool.Endpoint` and says in its own docstring that the semaphore
is this issue's. This is that bound — a semaphore in shape, though since #185
each permit is a host-wide file lock rather than a count in process memory.

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
  system would say so. :class:`Concurrency` reports the one figure a per-source
  record structurally cannot: how many dispatches were in flight *across*
  sources at once, which is the difference between a batch working two rigs
  together and a batch draining them in series (#200).
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

**Where the width comes from.** ``max_parallel`` is a declaration, and a
declaration is a guess: :func:`mcgyvr.initialize.initialize` writes ``1``
because it cannot know whether a backend was started with its parallel-slot
setting on, which is honest and leaves CON-04's measured 8.5x at sixteen
concurrent requests on a batching server unused. Some backends will answer the
question — llama.cpp states its slot count on ``GET /slots`` and
``/props.total_slots`` — so :meth:`Capacity.of` takes an optional
:class:`WidthProbe`, and three rules follow from it:

* A reported width **larger** than the declared one wins. The declaration was a
  guess and the report is a fact, and the fact is the whole return on asking.
* A reported ``None`` is an ordinary answer — "this backend does not say" — and
  not an error, nor the same as a source being down. ollama serves its
  parallelism from ``OLLAMA_NUM_PARALLEL`` in a unit file and exposes no
  endpoint for it; at ``0`` it decides per model at load time against free VRAM,
  so the width is not even a per-machine constant. The declaration stands, and
  :meth:`Capacity.confirmed` reports that it was never confirmed — because a
  number a rig stated and a number an operator typed must not look alike to
  anyone reading a report when only one of the two is evidence.
* A reported width **smaller** than the declared one is refused, not lowered.
  This is the CON-02 paragraph above made visible: quietly correcting the bound
  would leave the config still wrong, the operator still guessing, and the next
  rig still able to serialize a batch in silence. Refusing names the
  disagreement at the one moment both numbers are in hand. It is deliberately
  the same rule as :meth:`Capacity.hold`'s "two answers to one question",
  pointed at the machine rather than at a stale config.

The probe is a *parameter*. Nothing here opens a socket, for the same reason
:mod:`mcgyvr.pool` names :class:`~mcgyvr.pool.SourceProbe` structurally and
builds nothing: who actually asks a rig is #22's, and this module's job is to
know what to do with the answer.

One consequence is not yet resolved and is written down rather than papered
over: a confirmed width wider than the declared one leaves
:attr:`~mcgyvr.pool.Endpoint.max_parallel` carrying the superseded number, which
:meth:`hold` refuses as a stale config. Nothing supplies a real probe yet, so
nothing hits it today; whoever wires #22 must rebuild the source map from the
confirmed widths, or teach ``hold`` that a confirmed width outranks a carried
declaration. Loosening that check speculatively here would weaken the only guard
against two configs, to fix a collision no caller can currently cause.

**The bound is host-wide, not per-process (#185).** The rigs a source names are
shared machines, and this repository's own workflow runs lanes as parallel
worktrees — each its own process. A bound held in process memory is silently
doubled the moment two lanes dispatch at one rig, which is exactly when the
declared number matters. So a slot is not a semaphore permit: it is an
exclusive ``flock`` on one of ``max_parallel`` lock files, keyed by the
endpoint's ``base_url`` — the physical thing being protected, not the name a
config gave it. Any mcgyvr process on this host contending for the same URL
counts against the same files; threads within one process exclude one another
through the very same locks, so there is one mechanism, not an in-process one
with a cross-process patch. What remains per-process is *observation*:
:class:`Usage` reports what this process acquired, waited and peaked at,
because the numbers exist to explain this batch's wall-clock, and the bound —
not the bookkeeping — is what must be shared.

Three consequences are deliberate:

* **A crashed holder cannot strand capacity.** The kernel releases a ``flock``
  when its process dies, however it dies. That is this module's chosen answer
  to "no acquisition may block forever" — chosen over an acquire timeout
  because a long wait behind a deep batch queue is *legitimate* (twenty jobs at
  ``max_parallel: 1`` wait nineteen service times, and a fixed timeout would
  convert normal queueing into spurious failures), and over fail-fast because a
  batch runner's whole job is to queue. A caller that prefers multica's
  claim shape — one winner, losers refused at once, nothing queued — passes
  ``timeout`` to :meth:`Capacity.hold` and gets exactly that. A holder that is
  alive but wedged is not a capacity problem; it is the availability problem
  #141 owns, and the wait it causes is visible in ``waited_seconds``.
* **Slot files are never deleted.** Removing a lock file while a contender
  holds the old inode lets the next opener lock a fresh inode and be granted a
  slot that is already taken — the classic unlink race. The files are tiny,
  they live in the temp directory, and they are reused; cleanliness is not
  worth an over-admission.
* **Sharing is by rendezvous, so the rendezvous must be shared.** The lock
  directory defaults to the system temp directory (per user). Processes that
  resolve different temp directories — a session-scoped ``TMPDIR``, say — are
  bounding different files, honestly and separately; point ``lock_dir``
  somewhere stable when the environment does that. Likewise the bound is per
  host: two *machines* dispatching at one rig are beyond what a file lock can
  see, and nothing here pretends otherwise.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Protocol as TypingProtocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config
    from mcgyvr.pool import Endpoint

# How often a waiter re-tries the slot files while blocked. Coarse enough to
# cost nothing against dispatches measured in seconds to minutes; fine enough
# that a freed slot is taken promptly. The loop is also what makes a long wait
# interruptible, which a bare semaphore acquire was not.
_POLL_SECONDS = 0.02

# Lock-file names keep a readable prefix of the URL for an operator listing the
# directory, and a digest for identity — two URLs that sanitize alike must not
# share a bound by accident.
_SLUG = re.compile(r"[^A-Za-z0-9.-]+")


def _default_lock_dir() -> Path:
    """The per-user rendezvous directory for this host's slot files."""
    return Path(tempfile.gettempdir()) / f"mcgyvr-capacity-{os.getuid()}"


def _slot_stem(base_url: str) -> str:
    """A filesystem-safe identity for one rig, derived from its URL.

    Normalized so that trailing-slash and case differences in a config do not
    split one rig into two bounds; digested so that sanitizing cannot merge two
    rigs into one.
    """
    normalized = base_url.strip().rstrip("/").lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    slug = _SLUG.sub("-", normalized).strip("-")[-40:]
    return f"{slug}.{digest}"


class WidthProbe(TypingProtocol):
    """Anything that can ask a source how many requests it will really serve.

    The whole of the width half of #22's surface as this module sees it, and a
    structural type rather than an import so that building a capacity never
    drags in a network stack — the same idiom, for the same reason, as
    :class:`~mcgyvr.pool.SourceProbe`.

    Implementations must not raise. ``None`` is the answer for a backend that
    does not report its parallelism, which is an ordinary state of affairs and
    not a failure; a source that is *down* is :class:`~mcgyvr.pool.SourceProbe`'s
    question and is answered there, in words, as a skipped rung.
    """

    def width(self, source: str) -> int | None:
        """How many requests ``source`` will serve at once, or ``None`` if unsaid."""
        ...


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

    All three numbers are this *process's* observations. The bound itself is
    host-wide, so a wait here may be caused by another process's dispatches —
    that is the bound working, and the wait is still this batch's cost to
    report. No cross-process ledger is kept, because the numbers exist to
    explain this run's wall-clock, not to audit the host.
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


@dataclass(frozen=True)
class Concurrency:
    """How many dispatches this process had in flight at once, across sources.

    :class:`Usage` answers this per source and cannot answer it in total: its
    ``peak`` is keyed by source, so a batch that ran one source three wide and
    then another two wide reports 3 and 2 whether or not the two ever overlapped.
    Those are different runs — one is a batch making progress on two rigs at
    once, the other is a batch draining them in series — and until #200 nothing
    in this module could tell them apart.

    The question became worth asking when #185 made the bound host-wide. Before
    it, "how many dispatches are in flight" was answerable by summing what one
    process knew. Now the interesting figure is how much of the *declared total*
    a batch actually used, and ``peak`` against :attr:`Capacity.total` is that
    figure.

    Per-process, for the same reason :class:`Usage` is: this explains one batch's
    wall-clock. Another process's dispatches count against the same slot files
    and are not counted here.
    """

    peak: int
    """The most dispatches in flight at once, summed across every source."""

    total: int
    """The most that could ever be, if every source were saturated together."""

    @property
    def saturated(self) -> bool:
        """Whether every slot of every source was in use at the same moment."""
        return self.peak >= self.total


class Capacity:
    """Per-source, host-wide slot files, and this process's record of their cost.

    Built from a :class:`~mcgyvr.config.Config` with :meth:`of`, so the limits
    enforced are the ones the operator declared and there is no second place a
    capacity can be written down. Safe to share across threads — and shared
    with every other mcgyvr process on this host by construction, since a slot
    is a ``flock`` on a file both can see (#185). ``lock_dir`` exists for
    callers that need a rendezvous other than the per-user temp directory;
    tests use it for isolation.
    """

    def __init__(
        self,
        limits: Mapping[str, int],
        *,
        lock_dir: Path | None = None,
        confirmed: Iterable[str] = (),
    ) -> None:
        for source, limit in limits.items():
            if limit < 1:
                raise CapacityError(
                    f"source {source!r} declares max_parallel={limit}, which "
                    f"would admit no dispatch at all. The config schema floors "
                    f"it at 1; a source that should not be used belongs out of "
                    f"the ladder, not at zero capacity."
                )
        self._limits = dict(limits)
        # Which of those numbers a machine stated rather than an operator
        # guessed. Kept beside the limits and not inside them because it is not
        # a bound — nothing enforces it — but it is the difference between a
        # capacity report that is evidence and one that is a restatement of the
        # config; see :meth:`confirmed`. Empty by default, so a capacity built
        # by hand claims nothing it was not told.
        self._confirmed = frozenset(confirmed)
        unknown = ", ".join(sorted(self._confirmed - set(self._limits)))
        if unknown:
            raise CapacityError(
                f"confirmed width(s) for source(s) {unknown}, which this "
                f"capacity does not bound. A confirmation is a fact about a "
                f"source's limit, so there has to be a limit for it to be about."
            )
        self._lock_dir = lock_dir if lock_dir is not None else _default_lock_dir()
        self._lock = threading.Lock()
        self._in_use = dict.fromkeys(self._limits, 0)
        self._peak = dict.fromkeys(self._limits, 0)
        # Tracked alongside the per-source peaks rather than derived from them:
        # a maximum of sums is not the sum of maxima, and it is the moment two
        # sources were busy *together* that the per-source dict cannot hold.
        self._in_flight = 0
        self._in_flight_peak = 0
        self._acquisitions = dict.fromkeys(self._limits, 0)
        self._waited = dict.fromkeys(self._limits, 0.0)
        # Which sources *this* thread is currently holding. Thread-local rather
        # than shared, because the question it answers is "would this caller
        # block against itself", which is a per-thread question.
        self._holding = threading.local()

    @classmethod
    def of(cls, config: Config, *, probe: WidthProbe | None = None) -> Capacity:
        """The capacities this config declares, checked against ``probe`` if given.

        Every source, not only the ones the ladder currently uses: a role
        binding (orchestrator, verifier) dispatches against a source that need
        not appear in any tier, and a capacity that did not cover it would raise
        at the moment it was first used.

        Without a probe every width is the declared one and nothing is
        confirmed — the behaviour this had before there was anything to ask, and
        still the ordinary case, since ollama does not report its parallelism at
        all. With one, the module docstring's three rules apply: a larger report
        wins, ``None`` leaves the declaration standing and unconfirmed, and a
        smaller report raises rather than silently lowering the bound.

        The probe is asked once, here, rather than at each :meth:`hold`. A width
        is a property of how the backend was started, so re-asking it per
        dispatch would spend a round trip on a number that does not move, and —
        worse — would let the bound change underneath a batch that is already
        queued against it.
        """
        limits: dict[str, int] = {}
        confirmed: list[str] = []
        for name, source in config.sources.items():
            declared = source.max_parallel
            reported = None if probe is None else probe.width(name)
            if reported is None:
                # Nobody asked, or the backend does not say. Two different
                # reasons, one state of knowledge, and neither is evidence.
                limits[name] = declared
                continue
            if reported < declared:
                raise CapacityError(
                    f"source {name!r} declares {declared} but reports "
                    f"{reported}. Two answers to one question, and this time the "
                    f"machine gave one of them, so the config is the one that is "
                    f"wrong. Enforcing the declaration would not make the rig "
                    f"wider: a backend handed more concurrent requests than it "
                    f"has slots serializes them rather than refusing, so the "
                    f"over-declaration would show up as a rig that is merely "
                    f"slow and never as a config that is merely wrong. Declare "
                    f"{reported}, or start the backend with {declared} slots."
                )
            limits[name] = reported
            confirmed.append(name)
        return cls(limits, confirmed=confirmed)

    @property
    def limits(self) -> Mapping[str, int]:
        """The enforced capacity of each source.

        The declared number, or the reported one where a probe stated a wider
        width. Which of the two a given source got is :meth:`confirmed`'s
        question, deliberately not answerable from this mapping: a bound is a
        bound whatever its provenance, and a caller enforcing one should not
        have to care where it came from.
        """
        return dict(self._limits)

    def confirmed(self, source: str) -> bool:
        """Whether ``source``'s width was reported by the machine or assumed.

        The difference is evidence. A width a rig stated is a fact about that
        rig; a width taken from ``max_parallel`` is what an operator guessed
        when they wrote the config — or what
        :func:`mcgyvr.initialize.initialize` guessed on their behalf, which is
        always ``1``. A report showing "4" without saying which kind of 4 it is
        invites planning against a number nobody checked, so the two are kept
        apart here rather than in whatever renders them.

        A source the probe answered ``None`` for and a source there was no probe
        for are both unconfirmed. "The backend does not say" and "nobody asked"
        are different reasons for the same state of knowledge, and this method
        reports the state of knowledge.
        """
        if source not in self._limits:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for source {source!r}, so there is "
                f"nothing about it to have confirmed. Answering False here "
                f"would claim this capacity knows the source and merely could "
                f"not confirm its width. Known sources: {known}"
            )
        return source in self._confirmed

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

    def concurrency(self) -> Concurrency:
        """How much of the declared total this process ever had in flight at once.

        Separate from :meth:`usage` rather than a field on it because it is not
        a per-source fact and there is nowhere honest to put it in a per-source
        record. Summing ``Usage.peak`` across sources would over-report: those
        maxima can have occurred at different moments, and the whole point of
        this number is the moment they coincided.
        """
        with self._lock:
            return Concurrency(peak=self._in_flight_peak, total=self.total)

    @contextmanager
    def hold(
        self, endpoint: Endpoint, *, timeout: float | None = None
    ) -> Iterator[None]:
        """Hold one of ``endpoint``'s source's slots for the body of the block.

        The slot is an exclusive lock on one of ``max_parallel`` files keyed by
        the endpoint's ``base_url``, so it excludes every thread of every
        mcgyvr process on this host, not only this one (#185). With the default
        ``timeout=None`` this blocks until a slot frees — a deep batch queue is
        a legitimate wait, and a crashed holder's locks are released by the
        kernel, so the wait cannot be for a slot nobody can give back. A
        finite ``timeout`` turns the acquisition into a claim: try for that
        long, then raise :class:`CapacityError` naming the source — pass ``0``
        for one attempt with no queueing at all, multica's shape.

        The slot is released on the way out however the body leaves — a backend
        that times out or refuses must not cost the source a slot for the rest
        of the run, which is the leak the acceptance names.

        Raises :class:`CapacityError` rather than proceeding when the source is
        one this capacity does not know, when the endpoint's declared
        ``max_parallel`` disagrees with the one being enforced (both of which
        mean the capacity and the source map were built from different configs),
        or when the calling thread already holds this source.
        """
        source = endpoint.source
        limit = self._limits.get(source)
        if limit is None:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for source {source!r} — this capacity and "
                f"the source map it is bounding were built from different "
                f"configs. Known sources: {known}"
            )
        if endpoint.max_parallel != limit:
            raise CapacityError(
                f"source {source!r} is bounded at {limit} here "
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
        fd = self._acquire_slot(source, endpoint.base_url, limit, timeout)
        waited = time.monotonic() - started
        held.add(source)
        with self._lock:
            self._acquisitions[source] += 1
            self._waited[source] += waited
            self._in_use[source] += 1
            self._peak[source] = max(self._peak[source], self._in_use[source])
            self._in_flight += 1
            self._in_flight_peak = max(self._in_flight_peak, self._in_flight)
        try:
            yield
        finally:
            with self._lock:
                self._in_use[source] -= 1
                self._in_flight -= 1
            held.discard(source)
            os.close(fd)  # closing the descriptor is what releases the flock

    def _acquire_slot(
        self, source: str, base_url: str, limit: int, timeout: float | None
    ) -> int:
        """Take an exclusive lock on any free slot file, or raise at the deadline.

        Each attempt sweeps every slot index non-blockingly; a full sweep with
        no free slot means the rig is at its declared capacity *host-wide*, and
        the waiter sleeps briefly and sweeps again. The files are created on
        first use and never deleted — see the module docstring for the unlink
        race that rule prevents.
        """
        directory = self._lock_dir
        directory.mkdir(parents=True, exist_ok=True)
        stem = _slot_stem(base_url)
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            for index in range(limit):
                fd = os.open(directory / f"{stem}.{index}.slot", os.O_RDWR | os.O_CREAT)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    os.close(fd)
                    continue
                return fd
            if deadline is not None and time.monotonic() >= deadline:
                raise CapacityError(
                    f"source {source!r} has all {limit} declared slot(s) in use "
                    f"host-wide and none freed within {timeout}s. The bound "
                    f"counts every mcgyvr process on this host; a longer or "
                    f"absent timeout queues instead of refusing."
                )
            time.sleep(_POLL_SECONDS)

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
