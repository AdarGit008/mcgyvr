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
  not an error, nor the same as a source being down. A backend may take its
  parallelism from a unit file and expose no endpoint for it, or decide it per
  model at load time against free VRAM — in which case the width is not even a
  per-machine constant. The declaration stands, and
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

**A width can belong to a rung, not only to a rig.** ``max_parallel`` on a
source describes a machine, and a machine is not what serves a request — a
server process is. The same weights on two rigs are two processes started with
two different slot counts, and one rig serving a small model at sixteen slots
beside a large one at four is two processes on one machine; neither pair is
describable by a single number on the source. So a tier may declare its own
``max_parallel``, and three things follow:

* The rung's number is the bound where it is given, and the source's is the
  fallback where it is not. ``sources.*.max_parallel`` keeps exactly the
  meaning it has always had, so a config that names no rung width is bounded
  today as it was yesterday.
* **A rung's slots are its own, not a share of the source's.** Two rungs on one
  rig are two queues, so a dispatch to the small model cannot consume a slot
  the large model's server would have served; pooling them would bound a thing
  that does not exist. :meth:`in_flight` is therefore asked per rung, and a
  hold on one rung leaves another's count at zero. The slot files are keyed by
  the rung alongside the URL for the same reason — the physical thing being
  protected is one server process, not the host it happens to sit on.
* The three probe rules above apply per rung unchanged, because a rung's width
  is the same kind of claim about the same backend. A probe that predates the
  rung is asked about sources only: it did not answer ``None`` about a rung, it
  was never asked, and inventing an answer on its behalf would confirm a width
  no machine ever stated.

The probe is a *parameter*. Nothing here opens a socket, for the same reason
:mod:`mcgyvr.pool` names :class:`~mcgyvr.pool.SourceProbe` structurally and
builds nothing: who actually asks a rig is #22's, and this module's job is to
know what to do with the answer.

**So a capacity keeps two numbers per source, not one.** A confirmed width
wider than the declared one leaves :attr:`~mcgyvr.pool.Endpoint.max_parallel`
carrying the superseded number, and :meth:`hold` used to refuse exactly that as
a stale config — which made every successful probe unusable: the first dispatch
through a widened source raised, and the disagreement it named had been created
by :meth:`of` rather than by anyone's config. The fix is to stop asking one
number to answer two questions. The **declared** width is what the config said
and what an ``Endpoint`` carries; the **enforced** width is the confirmed one
where a machine answered and the declared one everywhere else. :meth:`hold`
checks the endpoint against the *declared* number — which is that check's real
purpose, catching a capacity and a source map built from two different configs —
and opens slots against the *enforced* one. :attr:`limits` keeps meaning what is
enforced, because that is what its callers read it for: a rung is as wide as the
slots it can actually take, which is what :func:`mcgyvr.escalate.ascent` asks it.
The declaration is :meth:`declared`'s. The two numbers differ only where a probe
widened a source, which makes those sources a *subset* of the confirmed ones and
not the same set: :meth:`confirmed` says a machine answered, and a machine that
answered with exactly the declared width confirmed it without changing it.

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

**Reservations, or the count that exists before a slot does (#24).**
:meth:`in_use` counts slots this capacity has *granted*, and there is an earlier
moment that matters to whoever is spreading a batch over several rigs: every
member of a batch chooses its rung before any of them has been granted anything,
so climbs reading only the granted count read zeroes, all choose the cheapest
rung, and queue on it — the funnel ``ladder.fanout`` exists to end. An attempt is
therefore counted from the moment it is *chosen*: :meth:`reserve` on the way in,
:meth:`release` on the way out, :meth:`reserving` for the callers whose
reservation is a block, :meth:`load` for granted and reserved together, and
:meth:`deciding` for a caller that must read several sources and reserve one of
them as a single decision.

The count lives here, per instance, rather than in the module that chooses
rungs, for the reason a process-global counter always eventually gives: keyed by
source name across every capacity in the process, two configs that merely share
the name ``srv1`` pool their counts, and a batch under one of them reads a
machine as busy because of unrelated work under the other. This capacity's
reservations are what this capacity counts.

They are counted per *bound* and not per rig, which is the same distinction the
widths above draw: a rung with a width of its own is a server process of its
own, so charging its choices to the rig would make every sibling rung read as
busy the moment one of them was chosen — the funnel again, one level down. A
reservation is a claim against the queue the slot will be taken from, so it is
keyed the way the slots are, by :meth:`_bound`'s one decision and never by a
caller's guess.

And they are exactly as narrow as that sounds: this process, this capacity, the
choices it was told about. Another mcgyvr process contending for the same slot
files is not counted here. That is not a gap to be closed — the *bound* is the
flock and is shared; this is bookkeeping for spreading the choices one batch is
making, and it only has to be right about those.

**A hold that never reserved is still load, so the two counts are added and
made not to overlap.** Most holds do not come through a reservation:
:func:`mcgyvr.runner.dispatch` and :func:`~mcgyvr.runner.dispatch_role` take a
slot directly, so a verifier occupies a rig without anything having chosen a
rung for it. :meth:`load` is therefore ``in_use + reserved``, and the double
count that sum invites is removed at its source rather than papered over: when
:meth:`hold` grants a slot to a thread that already holds a reservation for that
source, the reservation is *consumed* for as long as the slot is held, so the
one dispatch is counted once — as a slot — and is counted as a reservation again
when the slot goes back. ``max(in_use, reserved)`` was the earlier rule and it
is only right when every hold was reserved first: a verifier holding one slot of
a two-wide rig while a routed climb has reserved the same rig and is between
attempts reads as a load of 1, and a caller computing ``width - load`` then aims
a third dispatch at a rig with nothing free, where it blocks in :meth:`hold`.

Consuming the reservation is keyed by *thread*, which is what makes "the same
dispatch" answerable at all: a reservation is taken by the caller that chooses a
rung (:func:`mcgyvr.route.climb` does, under :meth:`deciding`) and the slot for
it is taken by that same caller on that same thread. A thread cannot hold one
source twice — :meth:`hold` refuses that as a deadlock — so one reservation
covers at most one slot at a time, and a hold on a thread that reserved nothing
consumes nothing and counts in full.
"""

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
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
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


def _slot_stem(base_url: str, rung: str | None = None) -> str:
    """A filesystem-safe identity for one served thing, derived from its URL.

    Normalized so that trailing-slash and case differences in a config do not
    split one rig into two bounds; digested so that sanitizing cannot merge two
    rigs into one.

    A rung names a server process rather than a host, so it joins the identity
    where it is given — a rung's slots are not the source's (see the module
    docstring), and two bounds sharing a file would be one bound. Absent a
    rung the value is unchanged, so an existing bound keeps the files it has.
    """
    normalized = base_url.strip().rstrip("/").lower()
    slug = _SLUG.sub("-", normalized).strip("-")[-40:]
    if rung is not None:
        tidied = rung.strip().lower()
        normalized = f"{normalized}#{tidied}"
        slug = f"{slug}.{_SLUG.sub('-', tidied).strip('-')[-24:]}"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{slug}.{digest}"


class SourceWidthProbe(TypingProtocol):
    """A probe that answers about a source and knows nothing of rungs.

    The shape this module asked for before a width could belong to a rung, kept
    because probes written against it are not wrong — a backend that reports one
    number for the machine is still reporting a fact. It is accepted wherever
    :class:`WidthProbe` is, and simply never asked the rung question.
    """

    def width(self, source: str) -> int | None:
        """How many requests ``source`` will serve at once, or ``None`` if unsaid."""
        ...


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

    ``rung`` is optional on both sides: it defaults to ``None`` so that a probe
    written for the whole source stays a valid one, and it is passed only to a
    probe whose signature accepts it, because a probe that cannot be asked about
    a rung has not answered about it.
    """

    def width(self, source: str, rung: str | None = None) -> int | None:
        """How many requests ``source`` serves at once, for ``rung`` if given."""
        ...


def _reported(
    probe: WidthProbe | SourceWidthProbe, source: str, rung: str | None
) -> int | None:
    """Ask ``probe`` about one bound, without assuming it has heard of rungs.

    The arity is inspected rather than guessed at through a ``TypeError``,
    which would swallow a genuine one raised inside a probe that does take a
    rung and report it as "this backend does not say" — the one answer that
    must never be manufactured, since it is what leaves a declaration standing.
    """
    if rung is None:
        return probe.width(source)
    try:
        inspect.signature(probe.width).bind(source, rung)
    except (TypeError, ValueError):
        return None
    return cast("WidthProbe", probe).width(source, rung)


class CapacityError(Exception):
    """A slot could not be taken, and running unbounded would be worse."""


class SlotUnavailableError(CapacityError):
    """Every slot of a bound was busy for as long as the caller would wait.

    A fact about right now, and the only :class:`CapacityError` a caller may
    reasonably route *around*: the rung is full, so a climb that walks past it
    to one with room has lost nothing — no verdict was produced, no attempt
    spent, no escalation funded. Every other member of this class is two
    configs disagreeing, which must be named rather than declined around, and
    that is why this is a subclass and not a flag on the message.
    """


# One bound: a source, and the rung whose own server process it bounds when the
# rung declared a width of its own. ``None`` is the source's own bound — what
# every dispatch that names no rung is held against — rather than a missing
# value, which is why it is in the key and not a separate mapping.
type _Bound = tuple[str, str | None]


@dataclass(frozen=True)
class RungWidth:
    """One rung's own width, and whether a machine stated it.

    Carried as a record rather than as a bare number because the two facts
    travel together everywhere: a width without its provenance is the exact
    confusion :meth:`Capacity.confirmed` exists to prevent, one rung at a time.
    ``source`` is here because a bound is only meaningful against the rig it
    bounds — the rung name alone would let a capacity be built for a rung whose
    source it does not know.
    """

    source: str
    limit: int
    confirmed: bool = False


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

    ``rung`` names the rung when the row is a rung's own bound and is ``None``
    for the source's. A rung that declared its own width is a separate queue on
    the same rig (see the module docstring), so folding its acquisitions into
    the source's row would report a saturation that no single server ever
    reached — and a report is the one place that must not.
    """

    source: str
    limit: int
    acquisitions: int
    peak: int
    waited_seconds: float
    rung: str | None = None

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
        declared: Mapping[str, int] | None = None,
        rungs: Mapping[str, RungWidth] | None = None,
        urls: Mapping[str, str] | None = None,
        queue_timeout_s: float | None = None,
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
        # What the config said, for the sources where that is not what is
        # enforced. Only a probe can separate the two — nothing else may widen a
        # bound — so a source whose two numbers differ is always a confirmed
        # one, but not the other way round: a probe reporting exactly the
        # declared width confirms it and widens nothing, and an unconfirmed
        # source always declares what it enforces. Kept because an
        # `Endpoint` carries the declaration, and :meth:`hold` has to be able to
        # check the number it was handed against the number of the same kind.
        self._declared = dict(self._limits)
        for source, width in dict(declared or {}).items():
            enforced = self._limits.get(source)
            if enforced is None:
                raise CapacityError(
                    f"a declared width for source {source!r}, which this capacity "
                    f"does not bound. A declaration and a bound are two numbers "
                    f"about one source, so there has to be a source."
                )
            if width < 1:
                raise CapacityError(
                    f"source {source!r} declares max_parallel={width}, which the "
                    f"config schema floors at 1. A capacity cannot be built from "
                    f"a declaration no config could have written."
                )
            if width > enforced:
                raise CapacityError(
                    f"source {source!r} declares {width} but is bounded at "
                    f"{enforced}. A width is only ever widened from its "
                    f"declaration and never narrowed — :meth:`of` refuses a "
                    f"machine reporting less rather than quietly lowering the "
                    f"bound — so a bound under the declaration is not something "
                    f"this module can have produced."
                )
            if width != enforced and source not in self._confirmed:
                raise CapacityError(
                    f"source {source!r} declares {width} and is bounded at "
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
                    f"rung {name!r} declares max_parallel={rung.limit}, which "
                    f"would admit no dispatch at all. The config schema floors "
                    f"it at 1; a rung that should not be used belongs out of "
                    f"the ladder, not at zero capacity."
                )
            if rung.source not in self._limits:
                raise CapacityError(
                    f"rung {name!r} bounds source {rung.source!r}, which this "
                    f"capacity does not bound. A rung's width is a width of the "
                    f"rig it runs on, so the rig has to be one this capacity "
                    f"knows."
                )
        # Where each source answers, so that a dispatch naming a source rather
        # than an endpoint still locks the files that rig's URL identifies.
        # Absent — a capacity built by hand from limits alone — the name is the
        # only identity there is, and two configs naming one rig differently
        # bound it separately, honestly and visibly.
        self._urls = dict(urls or {})
        # Every bound this capacity enforces, sources in declared order and
        # then the rungs that declared a width of their own. One mapping rather
        # than two because everything below — slots, peaks, waits, reservations,
        # the report — is per bound, and a rung's bound is not a special case of
        # a source's.
        self._bounds: dict[_Bound, int] = {
            (source, None): limit for source, limit in self._limits.items()
        }
        for name, rung in self._rungs.items():
            self._bounds[(rung.source, name)] = rung.limit
        # How long a :meth:`hold` that names no timeout of its own will wait.
        # ``None`` is the blocking default this class was written with, which
        # is right for a batch inside one process. :meth:`of` sets it from
        # ``budgets.task_timeout_s``, so a run driven from the command line is
        # bounded by the same ceiling that bounds the rest of its task: a wait
        # nobody is going to end is a command with no output and no end, and
        # that ceiling had no reader anywhere in the product before this.
        self._queue_timeout = queue_timeout_s
        self._lock_dir = lock_dir if lock_dir is not None else _default_lock_dir()
        # Re-entrant because :meth:`deciding` lends this lock to a caller, and a
        # caller inside it reads :meth:`load` and calls :meth:`reserve`, which
        # take it again. One lock and not two: the loads a decision is made from
        # are the counters a hold updates, and a second lock over the same
        # numbers would be a second answer to when they are consistent.
        self._lock = threading.RLock()
        self._in_use = dict.fromkeys(self._bounds, 0)
        # Attempts that have chosen this bound but have not been granted a slot
        # yet — the module docstring's reservations. Zero for every bound rather
        # than absent, so a read is a lookup and never a default. Per bound and
        # not per source, because a reservation is a claim against the queue the
        # slot will be taken from: charging a rung's choice to the rig would
        # make every sibling rung of that rig read as busy the moment one of
        # them was chosen, which is the funnel the knob exists to end wearing a
        # different name.
        self._reserved = dict.fromkeys(self._bounds, 0)
        # Of the slots granted, how many are a reservation being spent rather
        # than a second dispatch. Subtracted in :meth:`load` so that granted and
        # reserved can be added without counting one attempt twice; see the
        # module docstring for why the sum, and not the greater of the two, is
        # what a caller computing `width - load` needs.
        self._covered = dict.fromkeys(self._bounds, 0)
        self._peak = dict.fromkeys(self._bounds, 0)
        # Tracked alongside the per-source peaks rather than derived from them:
        # a maximum of sums is not the sum of maxima, and it is the moment two
        # sources were busy *together* that the per-source dict cannot hold.
        self._in_flight = 0
        self._in_flight_peak = 0
        self._acquisitions = dict.fromkeys(self._bounds, 0)
        self._waited = dict.fromkeys(self._bounds, 0.0)
        # Which bounds *this* thread is currently holding, which reservations
        # it took and has not given back, and which of its holds are spending
        # one of them. Thread-local rather than shared, because all three
        # questions are per-thread: "would this caller block against itself",
        # and "is this slot the one this caller reserved" — a reservation and
        # the slot it was taken for are always the same thread's.
        self._holding = threading.local()

    @classmethod
    def of(
        cls,
        config: Config,
        *,
        probe: WidthProbe | SourceWidthProbe | None = None,
        root: Path | None = None,
    ) -> Capacity:
        """The capacities this config declares, checked against ``probe`` if given.

        Every source, not only the ones the ladder currently uses: a role
        binding (orchestrator, verifier) dispatches against a source that need
        not appear in any tier, and a capacity that did not cover it would raise
        at the moment it was first used.

        Without a probe every width is the declared one and nothing is
        confirmed — the behaviour this had before there was anything to ask, and
        still the ordinary case for a backend that does not report its
        parallelism. With one, the module docstring's three rules apply: a larger report
        wins, ``None`` leaves the declaration standing and unconfirmed, and a
        smaller report raises rather than silently lowering the bound.

        The probe is asked once, here, rather than at each :meth:`hold`. A width
        is a property of how the backend was started, so re-asking it per
        dispatch would spend a round trip on a number that does not move, and —
        worse — would let the bound change underneath a batch that is already
        queued against it.

        Either way the config's own number is kept as the source's declaration,
        which is what makes a widened bound dispatchable: the endpoints a
        :class:`~mcgyvr.pool.SourceMap` built from this same config carry that
        number, and :meth:`hold` checks them against it. Rebuilding the source
        map from the confirmed widths would work too, and would be one more
        thing every caller who probes has to remember to do.

        Every tier is asked as well as every source, whether or not it declared
        a width: a rung that inherits the source's number still has a server
        process of its own, and that process is the thing a probe can speak
        about. What it answers is measured against the number that would
        otherwise apply — the rung's if it declared one, the source's if it did
        not — by the same three rules, so a rung is neither silently narrowed
        nor left at a guess a machine has already contradicted.

        ``root`` is the directory the slot files live in — :class:`Capacity`'s
        ``lock_dir``, named for what it is to a caller building from a config:
        the rendezvous every mcgyvr process on this host must agree on. Omitted,
        it is the per-user temp directory, which is the agreement by default.
        """
        limits: dict[str, int] = {}
        declarations: dict[str, int] = {}
        confirmed: list[str] = []
        for name, source in config.sources.items():
            declared = source.max_parallel
            declarations[name] = declared
            reported = None if probe is None else _reported(probe, name, None)
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

        rungs: dict[str, RungWidth] = {}
        for tier in config.ladder.tiers:
            # What the *config* wrote for this rung: its own number, or its
            # source's declared one where it wrote none. The declaration and not
            # the enforced width, because the enforced width may already have
            # been widened by this very probe, and a rung's report is then being
            # measured against a number nobody wrote. One rig running a wide
            # process behind one rung and a narrow one behind another is a
            # coherent thing to run — it is the arrangement per-rung widths
            # exist for — and inheriting the widest process's report as the
            # narrow rung's written width refused it at startup, with a remedy
            # ("declare 4 on the rung") that would not have helped, since the
            # rung had declared nothing to be wrong about.
            declared = (
                tier.max_parallel
                if tier.max_parallel is not None
                else config.sources[tier.source].max_parallel
            )
            reported = (
                None if probe is None else _reported(probe, tier.source, tier.name)
            )
            if reported is None:
                # No rung bound at all where the rung declared none: falling back
                # to the source is the *absence* of a second queue, not a copy of
                # the first one. A copy would double the rig's admitted width.
                if tier.max_parallel is not None:
                    rungs[tier.name] = RungWidth(
                        source=tier.source, limit=tier.max_parallel
                    )
                continue
            if reported < declared:
                raise CapacityError(
                    f"rung {tier.name!r} on source {tier.source!r} is written "
                    f"for {declared} but reports {reported}. Two answers to one "
                    f"question, and the machine gave one of them, so the config "
                    f"is the one that is wrong. Enforcing the written width "
                    f"would not make the server wider: a backend handed more "
                    f"concurrent requests than it has slots serializes them "
                    f"rather than refusing, so the over-declaration would show "
                    f"up as a rung that is merely slow and never as a config "
                    f"that is merely wrong. Declare {reported} on the rung, or "
                    f"start its backend with {declared} slots."
                )
            rungs[tier.name] = RungWidth(
                source=tier.source, limit=reported, confirmed=True
            )

        return cls(
            limits,
            lock_dir=root,
            confirmed=confirmed,
            declared=declarations,
            rungs=rungs,
            urls={name: source.base_url for name, source in config.sources.items()},
            # A task may not wait for a slot longer than it may take in total.
            queue_timeout_s=float(config.get("budgets.task_timeout_s")),
        )

    @property
    def limits(self) -> Mapping[str, int]:
        """The enforced capacity of each source.

        The declared number, or the reported one where a probe stated a wider
        width. Which of the two a given source got is :meth:`confirmed`'s
        question, deliberately not answerable from this mapping: a bound is a
        bound whatever its provenance, and a caller enforcing one should not
        have to care where it came from.

        Enforced, not declared, because every caller reads this to find out how
        much of a source it may use — how many slots there are to take, how wide
        a rung is. The config's own number, which is the one an
        :class:`~mcgyvr.pool.Endpoint` carries, is :meth:`declared`'s.
        """
        return dict(self._limits)

    def _bound(self, source: str, rung: str | None) -> _Bound:
        """Which bound a dispatch to ``source`` on ``rung`` is held against.

        The fallback lives here, in one place, so that every question about a
        rung — its width, its provenance, its slots, its in-flight count — is
        answered by the same rung-or-source decision. A rung that declared no
        width of its own is not a bound this capacity has; it is a name for the
        source's, which is precisely what "the source's value remains the
        default" means.
        """
        if rung is not None and (source, rung) in self._bounds:
            return (source, rung)
        return (source, None)

    def limit(self, source: str, rung: str | None = None) -> int:
        """The width enforced for ``source``, or for ``rung`` where it has its own.

        The one place the fallback is spelled out for a caller: a rung that
        declared a width is bounded by it, and a rung that did not is bounded by
        its source's, which is the number ``sources.*.max_parallel`` has always
        meant. A rung this capacity has never heard of is answered with its
        source's width rather than refused, because an unknown rung name is a
        dispatch that named no width, not a dispatch to an unknown rig.
        """
        limit = self._bounds.get(self._bound(source, rung))
        if limit is None:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for source {source!r}, so there is no "
                f"width to report for it. Known sources: {known}"
            )
        return limit

    def queue(self, source: str, rung: str | None = None) -> str | None:
        """Which queue a dispatch to ``source`` on ``rung`` would actually join.

        The rung's name where the rung has a bound of its own — a second server
        process on that rig, with slot files of its own — and ``None`` where it
        does not, because a rung that inherits its source's width is another
        name for the source's queue and not a queue beside it.

        It exists for callers that count work they are *about* to dispatch:
        :mod:`mcgyvr.route` keys its in-flight tally by the queue a chosen rung
        will join, and a tally keyed any other way would either spread a batch
        across a queue that does not exist or charge one rung's attempts to a
        sibling's. Asking here is what keeps that answer the same one
        :meth:`hold` acts on — the fallback is decided in one place (see
        :meth:`_bound`) rather than guessed at from widths that may coincide.
        """
        return self._bound(source, rung)[1]

    def confirmed(self, source: str, rung: str | None = None) -> bool:
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

        Asked about a rung, it reports that rung's own provenance, which is not
        its source's: a rig may state the width of the server behind one rung
        and say nothing about the one behind another, and a report that borrowed
        the answer would call a guess evidence.
        """
        if source not in self._limits:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for source {source!r}, so there is "
                f"nothing about it to have confirmed. Answering False here "
                f"would claim this capacity knows the source and merely could "
                f"not confirm its width. Known sources: {known}"
            )
        bound = self._bound(source, rung)
        if bound[1] is not None:
            return self._rungs[bound[1]].confirmed
        return source in self._confirmed

    def declared(self, source: str) -> int:
        """What ``source``'s config declared, whatever is now enforced for it.

        The number an :class:`~mcgyvr.pool.Endpoint` carries, which is why
        :meth:`hold` checks an endpoint against this one rather than against the
        bound: an endpoint built from the same config as this capacity states
        the declaration whether or not a probe has since widened the bound, and
        an endpoint that states something else came from a different config —
        which is the only thing that check was ever able to catch.

        Equal to ``limits[source]`` except where a machine reported a *wider*
        width, which makes the sources where the two numbers differ a subset of
        the confirmed ones rather than the same set. :meth:`confirmed` says a
        machine answered, and :meth:`of` confirms a source whenever the probe
        answered at all — including when the report equalled the declaration —
        so a confirmed source can have one number here and not two. A caller
        reading ``confirmed`` as "the widened-versus-declared distinction
        applies to this source" is therefore wrong for every source the probe
        agreed with; the way to ask that question is to compare the two numbers.

        A report and a guess that happen to agree are still two different kinds
        of fact, which is why the confirmation is kept for a source this method
        answers the same as ``limits`` — that difference is :meth:`confirmed`'s
        to report, not this one's.
        """
        self._bounded(source)
        return self._declared[source]

    @property
    def total(self) -> int:
        """The most dispatches that could ever be in flight across every rig.

        Counted per rig rather than per bound, because a rung's own width
        *overrides* its source's — that is what ``ladder.tiers.*.max_parallel``
        is documented to do — and a superseded number is not a queue. Summing
        every bound counted it as one anyway: a rig whose source line says 1 and
        whose rung says 16 reported 17, and :func:`run_batch` sized its pool at
        seventeen threads for a rig that will admit sixteen.

        The rung bounds of one rig *do* add up between themselves: each is a
        server process of its own with slot files of its own, so two rungs at 8
        are sixteen dispatches. What may not be added on top is the source
        number they replaced, so each rig contributes the greater of its own
        declared width and what its rungs declare between them. Where no rung
        declares a width this is the sum of the source widths, unchanged.
        """
        by_source: dict[str, int] = {}
        for rung in self._rungs.values():
            by_source[rung.source] = by_source.get(rung.source, 0) + rung.limit
        return sum(
            max(limit, by_source.get(source, 0))
            for source, limit in self._limits.items()
        )

    def in_use(self, source: str) -> int:
        """How many of ``source``'s own slots are held right now."""
        return self.in_flight(source)

    def in_flight(self, source: str, rung: str | None = None) -> int:
        """How many slots of ``source`` — or of ``rung`` — are held right now.

        Per rung where the rung has a width of its own, so a hold on one rung
        leaves another's count at zero. That is not bookkeeping precision, it is
        the fact: the two rungs are two server processes, and the second one is
        idle.

        Refuses a source this capacity does not bound, in :meth:`_bounded`'s
        words and not with a bare ``KeyError``: a caller here is holding a view
        of the ladder built from another config, which is the same mistake
        :meth:`load`, :meth:`declared` and :meth:`confirmed` name, and one
        reader raising a different exception for it would leave that mistake
        unhandled wherever the others are caught.
        """
        self._bounded(source)
        with self._lock:
            return self._in_use[self._bound(source, rung)]

    def load(self, source: str, rung: str | None = None) -> int:
        """How busy ``source`` — or ``rung`` — is: slots granted plus reserved.

        Their sum, because a load has to count every dispatch aimed at the
        source and the two counts hold different ones. Granted alone
        under-reports a batch that is still choosing, which is exactly when this
        gets asked; reserved alone misses every dispatch that never went through
        a caller that reserves, which is most of them —
        :func:`mcgyvr.runner.dispatch` and
        :func:`~mcgyvr.runner.dispatch_role` take a slot directly, so a verifier
        occupies a rig without anything having chosen a rung for it.

        Adding them is honest because the overlap is removed where it is
        created rather than here: :meth:`hold` consumes the reserving thread's
        reservation for as long as it holds the slot, so a reserved attempt that
        has been admitted is counted once, as a slot. ``max(in_use, reserved)``
        was the earlier rule and it under-counts whenever both kinds of hold are
        on one source — a verifier holding one slot of a two-wide rig while a
        routed climb has reserved it and is between attempts reads as 1, and a
        caller computing ``width - load`` sends a third dispatch at a rig with
        nothing free.

        This process and this capacity, and nothing else. Another mcgyvr
        process contending for the same slot files is not counted here and is
        not meant to be: the bound it contends for is the lock file, while this
        number exists to spread the choices *this* batch is making.

        Read per bound and never per rig, for the same reason
        :meth:`in_flight` is: a rung that declared a width of its own is a
        second server process on that box, so its granted slots and its
        reservations are its own and a sibling rung's are not. A load that
        pooled them would report a rig's busiest rung as every rung's load, and
        an ``idle`` climb would buy a priced rung to route around a local one
        that was empty.
        """
        self._bounded(source)
        bound = self._bound(source, rung)
        with self._lock:
            # Floored rather than subtracted straight, so that a reservation
            # given back by a thread that is still holding the slot it covered
            # cannot read as *less* load than the slot alone. The counters
            # cannot say a bound is emptier than what is provably held.
            waiting = self._reserved[bound] - self._covered[bound]
            return self._in_use[bound] + max(0, waiting)

    def reserve(self, source: str, rung: str | None = None) -> None:
        """Count one attempt as headed for that bound, before it has a slot.

        Every reserve needs a :meth:`release`, on every path — see
        :meth:`reserving` for the shape that cannot forget one. A caller
        choosing between sources reserves inside :meth:`deciding`, or two
        threads read the same loads before either of them has counted anything
        and make the same choice from them.

        Raises for a source this capacity does not bound rather than counting it
        anyway: a reservation is a claim against a bound, and there is no bound
        here to claim. A caller that may be holding a plan from another config
        asks ``source in capacity.limits`` first — the same question
        :meth:`load` is guarded by, and the answer is a fact about the two
        configs rather than about the source.

        The reserving thread is remembered as well as the count, because
        :meth:`hold` has to be able to tell a slot taken *for* a reservation
        from a second dispatch — see the module docstring. That is the only use
        of it: the count :meth:`load` reads is the shared one, and a reservation
        is not owned by the thread that took it in any sense a caller can see.

        ``rung`` selects the rung's own bound where the rung declared a width,
        and is otherwise the source's, by :meth:`_bound`'s one decision: the
        tally has to be keyed the way the slots will be, or a choice counted
        against the rig would be spent against a rung and the two would never
        cancel.
        """
        self._bounded(source)
        bound = self._bound(source, rung)
        with self._lock:
            self._reserved[bound] += 1
            mine = self._reservations()
            mine[bound] = mine.get(bound, 0) + 1

    def release(self, source: str, rung: str | None = None) -> None:
        """Stop counting one attempt on that bound. Never raises.

        Callable from a ``finally`` on every path, which is what keeps the count
        right when an attempt raises — and a leaked reservation is forever, so
        it would show a machine as busy to every later choice this process
        makes. Nothing about a bookkeeping mistake is worth an exception raised
        *while another one is unwinding*, so a release with no reservation
        behind it is floored at zero rather than going negative, and a source
        this capacity does not bound is ignored rather than named.

        A release from a thread that never reserved is floored the same way, and
        forgets nothing about the thread that did: the per-thread record exists
        only so that a hold can recognise its own reservation, and an unmatched
        release is already a mistake being tolerated rather than a state to keep
        books for.
        """
        bound = self._bound(source, rung)
        with self._lock:
            mine = self._reservations()
            held = mine.get(bound, 0)
            if held > 0:
                mine[bound] = held - 1
            current = self._reserved.get(bound, 0)
            if current > 0:
                self._reserved[bound] = current - 1

    @contextmanager
    def reserving(self, source: str, rung: str | None = None) -> Iterator[None]:
        """Reserve that bound for the body of the block, and release it after.

        The shape for a caller whose reservation is scoped to a block, and the
        one to prefer, since the release is then structural rather than
        remembered. A caller whose reservation is made inside a :meth:`deciding`
        section and given back much later — a ladder walk that picks a rung
        under the lock and frees it when that rung is finished with — cannot use
        a block and reserves and releases by hand.
        """
        self.reserve(source, rung)
        try:
            yield
        finally:
            self.release(source, rung)

    @contextmanager
    def deciding(self) -> Iterator[None]:
        """Hold the bookkeeping lock, so a read and a reserve are one decision.

        Reading several sources' :meth:`load` and reserving the least busy of
        them is two operations and one decision. Left apart, every member of a
        batch reads the same zeroes before any of them has reserved anything and
        they all choose the same source — the funnel narrowed to microseconds
        rather than closed. Inside this block no load can move under the caller.

        The lock is re-entrant, so :meth:`load`, :meth:`reserve` and
        :meth:`release` are all callable within it, and a caller needs no lock
        of its own. Nothing *slow* may be called within it: this is the same
        lock :meth:`hold` keeps its counters under, so a block that dispatched —
        or took a slot — inside it would stop every other thread's bookkeeping
        for the length of a request.
        """
        with self._lock:
            yield

    def usage(self) -> tuple[Usage, ...]:
        """What each bound was used for: sources in declared order, then rungs."""
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
        self,
        source: Endpoint | str,
        *,
        rung: str | None = None,
        timeout: float | None = None,
    ) -> Iterator[None]:
        """Hold one of that source's — or that rung's — slots for the block's body.

        ``source`` is an :class:`~mcgyvr.pool.Endpoint` where the caller has one,
        which is the dispatch path: the endpoint carries the declared width, so
        the two configs can be checked against each other at the one moment both
        are in hand. A bare source name is for a caller that has resolved no
        endpoint yet and is asking about capacity itself; it is checked against
        nothing, because there is nothing to check it against.

        ``rung`` selects the rung's own bound where the rung declared a width,
        and is otherwise ignored: a rung that inherits its source's number is
        held against its source's slots, not against a second pool of the same
        size (see the module docstring).

        The slot is an exclusive lock on one of ``max_parallel`` files keyed by
        the source's ``base_url``, so it excludes every thread of every
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

        There are as many slot files as the *enforced* width, so a source a
        probe widened dispatches that much wider — while the endpoint is checked
        against the width its config *declared*, which is the number an endpoint
        carries. Comparing it against the enforced one instead would refuse
        every dispatch through a source a probe had just widened, and blame a
        stale config for a disagreement :meth:`of` had itself created.

        Raises :class:`CapacityError` rather than proceeding when the source is
        one this capacity does not know, when the endpoint's ``max_parallel``
        disagrees with what this capacity's config declared for that source
        (both of which mean the capacity and the source map were built from
        different configs), or when the calling thread already holds this bound.
        """
        # ``None`` asks for this capacity's own bound, which is what a config
        # declared; ``0`` is still "try once, do not queue" and every other
        # number is still the caller's. Compared against ``None`` and not for
        # truth, or a caller asking for no queueing at all would silently get
        # the configured wait instead.
        if timeout is None:
            timeout = self._queue_timeout
        endpoint = None if isinstance(source, str) else source
        name = source if isinstance(source, str) else source.source
        if name not in self._limits:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for source {name!r} — this capacity and "
                f"the source map it is bounding were built from different "
                f"configs. Known sources: {known}"
            )
        declared = self._declared[name]
        if endpoint is not None and endpoint.max_parallel != declared:
            widened = (
                ""
                if self._limits[name] == declared
                else (
                    f" (A probe widened this source to {self._limits[name]}, "
                    f"which is what is enforced; an endpoint still carries the "
                    f"declared number, so {declared} is what it has to agree "
                    f"with.)"
                )
            )
            raise CapacityError(
                f"source {name!r} is bounded at {declared} here "
                f"but the endpoint declares max_parallel="
                f"{endpoint.max_parallel}. Two answers to one question means one "
                f"of them is from a stale config; rebuild both from the same "
                f"one.{widened}"
            )
        bound = self._bound(name, rung)
        limit = self._bounds[bound]
        where = (
            f"rung {bound[1]!r} of source {name!r}" if bound[1] else f"source {name!r}"
        )
        held = self._held()
        if bound in held:
            raise CapacityError(
                f"this thread already holds a slot on {where}. A "
                f"nested dispatch to it waits for a slot the waiter "
                f"is itself holding, so at the default max_parallel=1 it would "
                f"deadlock silently. Finish the outer dispatch first."
            )

        # The rig's URL where one is known, and the source's name where it is
        # not: a capacity built from limits alone has no other identity to key
        # the files by, and inventing one would be inventing a rendezvous.
        base_url = (
            endpoint.base_url if endpoint is not None else self._urls.get(name, name)
        )
        started = time.monotonic()
        fd = self._acquire_slot(where, base_url, bound[1], limit, timeout)
        waited = time.monotonic() - started
        held.add(bound)
        with self._lock:
            self._acquisitions[bound] += 1
            self._waited[bound] += waited
            self._in_use[bound] += 1
            self._peak[bound] = max(self._peak[bound], self._in_use[bound])
            self._in_flight += 1
            self._in_flight_peak = max(self._in_flight_peak, self._in_flight)
            # This is the dispatch the reservation was taken for, if this
            # thread took one: it chose the rung and is now being admitted to
            # it. Counting the reservation as spent for the length of the hold
            # is what lets :meth:`load` add granted and reserved without
            # counting this dispatch twice — and it is given back on the way
            # out, because a climb between two attempts on one rung has still
            # chosen that rung. The guard above means this thread holds no
            # other slot on this bound, so one reservation covers one slot.
            covering = self._reservations().get(bound, 0) > 0
            if covering:
                self._covered[bound] += 1
        try:
            yield
        finally:
            with self._lock:
                self._in_use[bound] -= 1
                self._in_flight -= 1
                if covering:
                    self._covered[bound] -= 1
            held.discard(bound)
            os.close(fd)  # closing the descriptor is what releases the flock

    def _acquire_slot(
        self,
        where: str,
        base_url: str,
        rung: str | None,
        limit: int,
        timeout: float | None,
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
        stem = _slot_stem(base_url, rung)
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
                raise SlotUnavailableError(
                    f"{where} has all {limit} declared slot(s) in use "
                    f"host-wide and none freed within {timeout}s. The bound "
                    f"counts every mcgyvr process on this host; a longer or "
                    f"absent timeout queues instead of refusing."
                )
            time.sleep(_POLL_SECONDS)

    def _bounded(self, source: str) -> None:
        """Refuse a source this capacity does not bound, by name.

        Shared by the readers and by :meth:`reserve` so that all of them refuse
        an unknown source the same way and in the same words. The answer is
        never a zero or a ``None``: those would say this capacity knows the
        source and has nothing to report about it, when what happened is that
        the caller is holding a view of the ladder built from another config.
        """
        if source not in self._limits:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for source {source!r} — this capacity and "
                f"the caller's view of the ladder were built from different "
                f"configs. Known sources: {known}"
            )

    def _held(self) -> set[_Bound]:
        """The bounds this thread holds, created on first use per thread."""
        bounds: set[_Bound] | None = getattr(self._holding, "bounds", None)
        if bounds is None:
            bounds = set()
            self._holding.bounds = bounds
        return bounds

    def _reservations(self) -> dict[_Bound, int]:
        """The reservations this thread took and has not released, by bound.

        Beside :meth:`_held` and in the same thread-local for the same reason:
        both answer a question about the caller rather than about the source.
        Keyed by bound and not by source for the same reason ``_reserved`` is —
        a hold recognises its own reservation only if the two were counted
        against the same queue. This one is read only by :meth:`hold`, to
        recognise the reservation the slot it is granting was taken for; the
        count that anyone can *see* is the shared ``_reserved``, which this is a
        per-thread breakdown of and never a second opinion about.
        """
        mine: dict[_Bound, int] | None = getattr(self._holding, "reserved", None)
        if mine is None:
            mine = {}
            self._holding.reserved = mine
        return mine


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
