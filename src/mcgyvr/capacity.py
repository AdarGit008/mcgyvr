"""Concurrency bounds for the units mcgyvr dispatches at, enforced host-wide.

Every unit the ladder can reach has a width: how many dispatches its backend
will serve at once. A width is made into slots here, and a slot is a ``flock``
on a file in a per-user directory under the temporary directory, so the bound
counts every mcgyvr process on the machine and not only the one that holds it.
:class:`Capacity` is what answers the questions a scheduler asks — what is in
flight on a bound, whether it is full, what a wait has cost — and
:meth:`Capacity.hold` is the block an ordinary dispatch runs inside.
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
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from typing import Protocol as TypingProtocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config
    from mcgyvr.local_pool import Endpoint
    from mcgyvr.pressure import Gauge

# How long a waiter sleeps between rounds of non-blocking attempts at a bound's
# slot files. Polling rather than blocking on one file is what lets a waiter
# scan for whichever slot is free; a wait this short is short enough that a slot
# another process frees is taken up before the dispatch above it notices.
_POLL_SECONDS = 0.02

# Everything in an address that is not a letter, digit, dot or hyphen,
# collapsed into runs, so an address can be part of a slot file's name. Two
# addresses that slug alike are still kept apart by the digest `_slot_stem`
# appends.
_SLUG = re.compile(r"[^A-Za-z0-9.-]+")


def _default_lock_dir() -> Path:
    """The directory holding this user's slot files, in the temporary directory.

    One directory per uid, because the bound is the host's: another user's
    dispatches are held to their own slots, and neither user can write over the
    other's files.
    """
    return Path(tempfile.gettempdir()) / f"mcgyvr-capacity-{os.getuid()}"


@dataclass(frozen=True)
class Fullness:
    """One bound's occupancy: what this capacity counts, and what the server says."""

    #: Dispatches in flight on the bound, plus reservations not yet taken up by
    #: one.
    load: int
    #: Dispatches the backend reports in flight, or `None` where it was not read.
    server: int | None
    #: The bound itself: the most this capacity admits.
    width: int

    @property
    def full(self) -> bool:
        """Whether either count has reached the width, so the next dispatch waits."""
        if self.load >= self.width:
            return True
        return self.server is not None and self.server >= self.width

    @property
    def server_read(self) -> bool:
        return self.server is not None

    @property
    def why(self) -> str:
        """What is occupying the bound, in the words a refusal message wants."""
        server = (
            "the server was not read"
            if self.server is None
            else f"the server has {self.server} in flight"
        )
        return f"{self.load} of {self.width} here; {server}"


def _waiting_key(stem: str) -> str:
    """The gauge key under which waiters on one slot stem are counted."""
    return f"wait.{stem}"


def _slot_stem(base_url: str, rung: str | None = None) -> str:
    """The file-name stem shared by every slot of one address at one rung.

    The address is lowercased and slugged so a file name can be read, then cut
    to a fixed tail and suffixed with a digest of the whole address and rung, so
    two addresses that slug alike still get different files. Units that name one
    address therefore share one set of slot files, which is what makes the bound
    the backend's rather than the config's.
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
    """A probe that answers for a whole unit and has nothing to say per rung."""

    def width(self, source: str) -> int | None:
        """The width this source reports, or `None` where it does not say."""
        ...


class WidthProbe(TypingProtocol):
    """A probe that can answer per rung as well as per unit."""

    def width(self, source: str, rung: str | None = None) -> int | None:
        """The width this source, or this rung of it, reports, or `None`."""
        ...


def _reported(
    probe: WidthProbe | SourceWidthProbe, source: str, rung: str | None
) -> int | None:
    """Ask a probe for a width, tolerating one that takes no rung argument.

    With no rung the probe is asked about the source alone. With a rung, a probe
    whose `width` cannot be called with one is not a failure: it is a probe with
    no per-rung answer, so the answer is `None` rather than a guess.
    """
    if rung is None:
        return probe.width(source)
    try:
        inspect.signature(probe.width).bind(source, rung)
    except (TypeError, ValueError):
        return None
    return cast("WidthProbe", probe).width(source, rung)


class CapacityError(Exception):
    """A capacity that cannot be built, or a unit this capacity does not bound."""


class SlotUnavailableError(CapacityError):
    """A slot was still held when the wait ran out; nothing was admitted."""


# One width to count against: a unit's name, and the rung it was bounded at
# where that rung states a width of its own. `None` is the unit's own width,
# which is also the bound every dispatch that names no rung lands on. Every
# counter and every set of slot files below is kept per bound.
type _Bound = tuple[str, str | None]


class _Claims:
    """One thread's reservations, and how many a dispatch has taken up.

    A node belongs to a thread; :func:`run_batch` hands each worker a child node
    whose `parent` is the node of the thread that submitted the batch, so a
    reservation made before a fan-out is still found inside it. `taken` counts
    the reservations made at a node and `covering` how many of them an in-flight
    dispatch has picked up, so a hold can walk up the parents to the nearest node
    still holding an uncovered reservation on the bound it just acquired.
    """

    __slots__ = ("covering", "parent", "taken")

    def __init__(self, parent: _Claims | None = None) -> None:
        self.parent = parent
        self.taken: dict[_Bound, int] = {}
        self.covering: dict[_Bound, int] = {}


@dataclass(frozen=True)
class RungWidth:
    """A rung that states its own width, and the unit whose slots it uses.

    `source` is the unit the rung runs on; the rung is dispatched at `limit`
    rather than at that unit's width. `confirmed` records whether a machine
    reported the number, rather than the config asserting it.
    """

    source: str
    limit: int
    confirmed: bool = False


@dataclass(frozen=True)
class Usage:
    """What one bound did over the life of a capacity.

    `acquisitions` is how many dispatches took a slot on it, `peak` the most it
    ever had in flight at once, and `waited_seconds` the time dispatches spent
    queueing for it.
    """

    source: str
    limit: int
    acquisitions: int
    peak: int
    waited_seconds: float
    rung: str | None = None

    @property
    def saturated(self) -> bool:
        """Whether the bound was ever actually filled, not merely approached."""
        return self.peak >= self.limit


@dataclass(frozen=True)
class Concurrency:
    """The whole capacity in two figures: the overlap reached, and its ceiling."""

    peak: int
    """The most dispatches in flight at once, summed across every source."""

    total: int
    """The most that could ever be, if every source were saturated together."""

    @property
    def saturated(self) -> bool:
        """Whether every source was saturated in the same instant."""
        return self.peak >= self.total


class Capacity:
    """The bounds one config's units are dispatched within, and their counters.

    A width is enforced with a slot file per slot: a dispatch holds one for as
    long as it holds the unit, and a waiter takes the first slot that is free.
    On top of the slots the capacity keeps what a scheduler needs to decide with
    — what is in flight, what has been reserved, the peak, the time spent
    waiting — and answers whether a bound is full, both from its own counts and
    from what the server reports through `busy`. Nothing here starts a dispatch:
    :meth:`hold` is a block a caller wraps around work of its own.
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
        # Units whose width a machine reported, as opposed to one the config
        # declared. A name with no bound here is refused rather than ignored: a
        # confirmation is a fact about some unit's limit, and this capacity has
        # to know which limit that is before it can hold the fact.
        self._confirmed = frozenset(confirmed)
        unknown = ", ".join(sorted(self._confirmed - set(self._limits)))
        if unknown:
            raise CapacityError(
                f"confirmed width(s) for source(s) {unknown}, which this "
                f"capacity does not bound. A confirmation is a fact about a "
                f"source's limit, so there has to be a limit for it to be about."
            )
        # Slots each unit keeps back for a role, counted apart from the width
        # the ladder is offered: the unit serves `limit + reserved` dispatches
        # and the ladder sees `limit`. A unit this capacity does not bound cannot
        # have a slot reserved on it, and a negative count is not a number of
        # slots.
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
        # The width the config declared for each unit, kept beside the width
        # enforced here because an endpoint carries the declared number and
        # `hold` checks the two agree. A declaration may be above the enforced
        # width only by exactly the slot a role keeps back - never more, since
        # this module widens a bound from a machine's report and never quietly
        # narrows one - and the two numbers may differ only where the machine
        # confirmed the enforced one or where the difference is the role's slot.
        # Anything else is a capacity built from two configs.
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
        # The address each unit answers at, used to key the slot files. A unit
        # with no entry falls back to its own name, which no address shares.
        self._urls = dict(urls or {})
        # Every bound this capacity counts at: a unit's own, which is its width
        # plus whatever part of that width a role keeps back, because the slots
        # are the served ones while the width the ladder is offered is the
        # smaller number; and each declared rung's, at the rung's own limit.
        self._bounds: dict[_Bound, int] = {
            (source, None): limit + self._role_reserved.get(source, 0)
            for source, limit in self._limits.items()
        }
        for name, rung in self._rungs.items():
            self._bounds[(rung.source, name)] = rung.limit
        # The wait a caller of `hold` gets when it names no timeout of its own:
        # in practice the config's task timeout, so a dispatch may queue for as
        # long as its task may run. `None` here waits without a deadline.
        self._queue_timeout = queue_timeout_s
        # Where waiters announce themselves so another process can count them: a
        # card about to sleep asks whether work is queued on it, and a queued
        # dispatch is a reason to stay up. `None` announces nothing and reports
        # `None` rather than an empty queue.
        self._gauge = gauge
        # How to ask a backend how many dispatches it has in flight. `None` is
        # the ordinary case, where no backend is asked at all, and is reported as
        # "the server was not read" rather than as a server with nothing in
        # flight.
        self._busy = busy
        self._lock_dir = lock_dir if lock_dir is not None else _default_lock_dir()
        # One re-entrant lock for every counter below, and the counter it guards
        # first: the dispatches holding a slot on a bound right now. It is
        # re-entrant because `deciding` holds it around a caller's work, and
        # `deciding` is what makes reading a bound and claiming a slot on it one
        # step, so two climbers cannot both see the last slot free and take it.
        self._lock = threading.RLock()
        self._in_use = dict.fromkeys(self._bounds, 0)
        # Slots claimed by `reserve` and not yet given back: demand already
        # committed to, which counts towards the load before its dispatch
        # starts, so the next climber does not read the bound as free.
        self._reserved = dict.fromkeys(self._bounds, 0)
        # How much of `_reserved` an in-flight dispatch has taken up, so the
        # remainder is the only part added to the load and one attempt is never
        # counted as both a claim and a dispatch; and the highest `_in_use` this
        # bound has reached.
        self._covered = dict.fromkeys(self._bounds, 0)
        self._peak = dict.fromkeys(self._bounds, 0)
        # Dispatches holding a slot anywhere in this capacity, and the most there
        # have ever been at once: the pair `concurrency` answers with. A total
        # taken at one instant is not the sum of the per-bound peaks.
        self._in_flight = 0
        self._in_flight_peak = 0
        self._acquisitions = dict.fromkeys(self._bounds, 0)
        self._waited = dict.fromkeys(self._bounds, 0.0)
        # Per-thread state: the slot stems this thread is holding, so a nested
        # dispatch to an address it already holds is refused instead of waiting
        # on itself, and the node of the reservation tree this thread's claims
        # belong to. `run_batch` hands each worker a child of the node held by
        # the thread that submitted the batch.
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
        """Build a capacity from a config, and from a machine where one answers.

        Every unit the ladder and the relief set name is bounded, whether or not
        a ladder rung reaches it, and each starts from the width the config
        declares. A local orchestrator that mcgyvr provisions itself keeps one
        slot back for the role, so the ladder is offered one fewer than the unit
        serves; where the unit states no width it is served at `users`, one per
        user it answers. A probe may widen a declaration, and is then recorded as
        confirming it; a probe reporting less than the declaration is refused,
        because narrowing the bound would leave the config wrong and the rig only
        slow.
        """
        limits: dict[str, int] = {}
        declarations: dict[str, int] = {}
        reserved: dict[str, int] = {}
        confirmed: list[str] = []
        orchestrator_name = config.get("orchestrator.unit")
        # The unit the orchestration role runs on, where the config names one.
        # Looked up in `units` rather than taken on trust, so the role's own
        # attributes — above all whether it needs a credential — can be read
        # before the role is recognised. A name that is not a unit leaves this
        # `None`.
        orchestrator_unit = (
            config.units.get(orchestrator_name) if orchestrator_name else None
        )
        # The role is recognised only where mcgyvr provisions the unit itself,
        # since a hybrid or chat setup reaches its orchestrator elsewhere, and
        # only where the unit needs no credential, since one that does is not a
        # process this config starts. Otherwise the unit is an ordinary rung with
        # no slot kept back.
        role_orchestrator = (
            orchestrator_name
            if config.provisions_local_orchestrator
            and orchestrator_unit is not None
            and not orchestrator_unit.requires_credential
            else None
        )
        users = int(config.get("users", 1))
        # The ladder's units and the relief rungs together: a role may dispatch
        # against a unit no ladder rung names, and a unit with no counter here is
        # a unit whose width is not enforced.
        bounded = {**config.units, **config.relief}
        for name, unit in bounded.items():
            declared = unit.width or 1
            if name == role_orchestrator:
                # The role's unit is served at one slot per user where it states
                # no width, because the serving plan starts it that way; a width
                # it does state is the number it was started with and stands.
                declared = unit.width or users
            declarations[name] = declared
            reported = None if probe is None else _reported(probe, name, None)
            if reported is None:
                # No probe, or a backend that does not report its parallelism:
                # the declaration stands as the bound, and is not confirmed.
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
            # A dispatch may queue for as long as its task may run, so the
            # default wait is the task timeout rather than a queue timeout of
            # its own.
            queue_timeout_s=float(config.get("task_timeout_s")),
            gauge=gauge,
            busy=busy,
        )

    @property
    def limits(self) -> Mapping[str, int]:
        """The width each unit is bounded at, as a copy: the ladder-facing numbers."""
        return dict(self._limits)

    def _bound(self, source: str, rung: str | None) -> _Bound:
        """The bound a dispatch on this source lands on, without checking it exists.

        A rung that states no width of its own falls back to the unit's own
        bound, so the same slot files serve it and only the width differs.
        """
        if rung is not None and (source, rung) in self._bounds:
            return (source, rung)
        return (source, None)

    def limit(self, source: str, rung: str | None = None) -> int:
        """The most this bound admits, or an error naming the units that exist."""
        bound = self._bound(source, rung)
        if bound in self._bounds:
            # A rung is as wide as its own declaration says. The unit's own
            # bound reports the width the ladder is offered, which is one
            # narrower than the served width where a role keeps a slot back.
            if bound[1] is not None:
                return self._bounds[bound]
            return self._limits[bound[0]]
        known = ", ".join(sorted(self._limits)) or "none"
        raise CapacityError(
            f"no declared capacity for unit {source!r}, so there is no "
            f"width to report for it. Known units: {known}"
        )

    def queue(self, source: str, rung: str | None = None) -> str | None:
        """The rung a dispatch here is counted at.

        `None` where the bound is the unit's own.
        """
        return self._bound(source, rung)[1]

    def confirmed(self, source: str, rung: str | None = None) -> bool:
        """Whether a machine, rather than the config, set this bound's width.

        A unit this capacity does not bound is refused rather than answered
        `False`: the question is about a bound, and there is no bound here to
        answer for, which is a different thing from an unconfirmed one.
        """
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
        """The width the config declared for this unit, before any probe widened it.

        Equal to the enforced width where nothing was declared for the unit and
        nothing was reported either.
        """
        self._bounded(source)
        return self._declared[source]

    @property
    def total(self) -> int:
        """The most dispatches this capacity could ever have in flight at once.

        A unit counts at its served width or at the sum of its rungs' widths,
        whichever is greater, and the two are never added: a rung's slots are its
        unit's slots, so a maximum of sums is the real ceiling and a sum of
        maxima is not.
        """
        by_source: dict[str, int] = {}
        for rung in self._rungs.values():
            by_source[rung.source] = by_source.get(rung.source, 0) + rung.limit
        return sum(
            max(self._bounds[(source, None)], by_source.get(source, 0))
            for source in self._limits
        )

    def in_use(self, source: str) -> int:
        """Dispatches holding a slot on this unit's own bound, with no rung named."""
        return self.in_flight(source)

    def in_flight(self, source: str, rung: str | None = None) -> int:
        """Dispatches this process is holding a slot for on this bound.

        The count is this process's own; the slot files are what hold every other
        process on the host to the same bound.
        """
        self._bounded(source)
        with self._lock:
            return self._in_use[self._bound(source, rung)]

    def waiting(self, source: str, rung: str | None = None) -> int | None:
        """How many dispatches are queued for this bound, host-wide.

        Read from the gauge, so the answer covers every process on the machine;
        `None` means nothing could be read, which is not an empty queue.
        """
        self._bounded(source)
        if self._gauge is None:
            return None
        bound = self._bound(source, rung)
        stem = _slot_stem(self._urls.get(source, source), bound[1])
        return self._gauge.count(_waiting_key(stem))

    def queued(self, sources: Iterable[str]) -> int | None:
        """The same count over several units, summed once per set of slot files.

        Units that name one address share their files and are counted once.
        `None` where no gauge is held or any count could not be read, so a caller
        asking whether nothing is queued cannot mistake an unreadable answer for
        an empty one.
        """
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
        """What this bound is carrying: dispatches in flight, plus untouched claims."""
        self._bounded(source)
        bound = self._bound(source, rung)
        with self._lock:
            # A claim already taken up by a dispatch must not be added again on
            # top of it, so only the unclaimed remainder counts. The floor at
            # zero is for a claim released while its dispatch is still in
            # flight, which would otherwise read as negative demand.
            waiting = self._reserved[bound] - self._covered[bound]
            return self._in_use[bound] + max(0, waiting)

    def fullness(self, source: str, rung: str | None = None) -> Fullness:
        """This bound's occupancy, reading the server's own count where it can."""
        return self.judge(source, rung, self.server_busy(source))

    def server_busy(self, source: str) -> int | None:
        """How many dispatches the backend behind this unit reports in flight.

        `None` where no reader was given: a server that was not read is not a
        server with nothing in flight.
        """
        self._bounded(source)
        return None if self._busy is None else self._busy(source)

    def judge(self, source: str, rung: str | None, server: int | None) -> Fullness:
        """Settle fullness for a bound from a server count the caller already read.

        `server` is handed in because a caller sweeping every rung of one unit
        reads that unit's server once rather than once per rung; `None` there
        means it was not read, and is not a count of zero.
        """
        self._bounded(source)
        return Fullness(
            load=self.load(source, rung),
            server=server,
            width=self.limit(source, rung),
        )

    def reserve(self, source: str, rung: str | None = None) -> None:
        """Claim one slot on this bound for a dispatch that has not started yet.

        The claim is demand rather than a slot: it counts towards the load at
        once, so the next climber does not read the bound as free, and no slot
        file is touched until the dispatch itself holds one. It is recorded
        against this thread's claim node, so the dispatch that takes it up can be
        recognised even from a worker thread the batch spreads it to.
        """
        self._bounded(source)
        bound = self._bound(source, rung)
        with self._lock:
            self._reserved[bound] += 1
            mine = self._reservations().taken
            mine[bound] = mine.get(bound, 0) + 1

    def release(self, source: str, rung: str | None = None) -> None:
        """Give back a claim taken by :meth:`reserve`.

        A count already back at zero is left there rather than going negative, so
        an unbalanced release cannot make the bound look emptier than it is.
        """
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
        """Hold one claimed slot for the block, releasing it however the block ends."""
        self.reserve(source, rung)
        try:
            yield
        finally:
            self.release(source, rung)

    @contextmanager
    def deciding(self) -> Iterator[None]:
        """Hold the counters still while a caller reads a bound and acts on it.

        :meth:`judge` and :meth:`reserve` are separate calls, and between them
        another thread could take the last slot a caller had just been told
        about. Anything deciding where to dispatch belongs inside this block.
        """
        with self._lock:
            yield

    def usage(self) -> tuple[Usage, ...]:
        """A record per bound, in the order the bounds were declared.

        A snapshot, not a live view; the waited time is rounded to microseconds.
        """
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
        """The peak overlap reached anywhere, against the ceiling it could reach."""
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
        """Take a slot on this unit for the life of the block.

        The slot is host-wide: a ``flock`` on a file named for the unit's address
        and, where one is named, the rung, so another mcgyvr process on this
        machine waits for it too. The wait is bounded by `timeout`, which
        defaults to this capacity's queue timeout; a wait that runs out raises
        :class:`SlotUnavailableError`. A unit this capacity does not bound, an
        endpoint whose ``max_parallel`` disagrees with the width the config
        declared for it, and a nested dispatch to an address this thread already
        holds are all refused before any slot is touched. While the block runs
        the bound's counts, peak and waited time are kept, and a claim this
        thread already holds on the same bound is marked as taken up instead of
        being counted a second time.
        """
        # A timeout the caller names is a deadline of its own, not a statement
        # about the task. A caller that names none waits for the timeout this
        # capacity was built with, which is how long its task was going to take
        # anyway; `None` there waits without a deadline. A finite wait that runs
        # out is a refusal, never an interruption of a dispatch already admitted.
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
            # A rung that states no width of its own lands on the unit's bound,
            # and takes its width from the ladder-facing number rather than from
            # the served one: the slot a role keeps back is the role's own
            # dispatch, so a rung cannot spend it. Its slots are the unit's, so
            # the width is the only thing the rung narrows.
            limit = self._limits[name]
        where = f"unit {bound[1]!r} of unit {name!r}" if bound[1] else f"unit {name!r}"
        # The address keys the slot files, so the endpoint's own address is used
        # where one was handed in, and the address this capacity was built with -
        # falling back to the unit's name - where only a name was given.
        base_url = (
            endpoint.base_url if endpoint is not None else self._urls.get(name, name)
        )
        # The stem is what identifies the files, so the guard below catches a
        # nested dispatch to this thread's own address, which would wait for a
        # slot the waiter is itself holding.
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
            # Mark the claim this dispatch takes up, where there is one: the
            # nearest node at this bound - this thread's, or one inherited from
            # the thread that submitted its batch - that still holds a claim not
            # yet covered. Only the remainder of the claims counts as load, so an
            # attempt reserved before it started is one unit of load rather than
            # a claim and a dispatch together. A dispatch with no claim to take up
            # covers nothing, and simply counts as itself.
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
            os.close(fd)  # closing the file drops its flock, which frees the slot

    @contextmanager
    def drain(
        self, sources: Iterable[str], *, timeout: float | None = None
    ) -> Iterator[None]:
        """Take every slot of these units for the life of the block.

        All of them, not one: nothing new can start on these units while the
        block runs, which is what makes it safe to put a card down. Units that
        name one address share their files and each file is taken once. A file
        still held by a dispatch elsewhere raises :class:`SlotUnavailableError`
        when `timeout` runs out - `None` waits - and then the block never begins
        and every file already taken is closed on the way out.
        """
        named = sorted(set(sources))
        for source in named:
            self._bounded(source)
        wanted = sorted(
            (bound for bound in self._bounds if bound[0] in set(named)),
            key=lambda bound: (bound[0], bound[1] or ""),
        )
        taken: list[int] = []
        # Two units may name one address, so their slot files are the same files,
        # and a drain asking for both would wait on a lock this process is
        # already holding - with no deadline, forever. This remembers which
        # (stem, index) pairs have been taken so each file is opened once.
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
                os.close(fd)  # every slot goes back, whether the block raised or not

    def _acquire_one(
        self,
        where: str,
        base_url: str,
        rung: str | None,
        index: int,
        timeout: float | None,
    ) -> int:
        """Wait for one named slot to be free and return its file, locked.

        The drain path, which knows which slot of the set it wants: one file is
        opened, its lock retried without blocking, and the descriptor returned
        with the lock held. A wait that runs out raises
        :class:`SlotUnavailableError` and closes the descriptor; a dispatch
        already admitted is never interrupted to make room.
        """
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
        """Take the first free slot of a bound and return its file, locked.

        Every index up to `limit` is tried in turn with a non-blocking ``flock``,
        so the lowest free slot is the one taken and a rung narrower than its
        unit only ever takes from that unit's first slots. With all of them held
        the wait sleeps and tries again until `timeout` runs out, and announces
        itself on the gauge once for as long as it waits, so another process can
        see the queue it would be cutting into.
        """
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
        """Refuse a unit this capacity does not bound, before any counter is read.

        A name missing here means the capacity and the caller's view of the
        ladder were built from different configs, so the error names the units
        that are known rather than answering a count for a bound that does not
        exist.
        """
        if source not in self._limits:
            known = ", ".join(sorted(self._limits)) or "none"
            raise CapacityError(
                f"no declared capacity for unit {source!r} — this capacity and "
                f"the caller's view of the ladder were built from different "
                f"configs. Known units: {known}"
            )

    def _held(self) -> set[str]:
        """The slot stems this thread is holding, made on first use.

        Per thread, because a slot is held by the thread that took it: the guard
        it feeds is whether this thread's own nested dispatch would wait on a
        lock it is itself holding, and other threads' holds are not that.
        """
        stems: set[str] | None = getattr(self._holding, "stems", None)
        if stems is None:
            stems = set()
            self._holding.stems = stems
        return stems

    @contextmanager
    def _inheriting(self, parent: _Claims) -> Iterator[None]:
        """Run the block with a child of `parent` as this thread's claim node.

        A worker thread in :func:`run_batch` gets an empty node of its own whose
        parent is the submitting thread's node, so a claim made before the
        fan-out is found by the dispatch that takes it up on a worker, and a
        claim a worker makes itself is released where it was made. The previous
        node is put back afterwards, since threads are reused by the pool.
        """
        previous = getattr(self._holding, "reserved", None)
        self._holding.reserved = _Claims(parent)
        try:
            yield
        finally:
            self._holding.reserved = previous

    def _reservations(self) -> _Claims:
        """This thread's claim node, made on first use."""
        mine: _Claims | None = getattr(self._holding, "reserved", None)
        if mine is None:
            mine = _Claims()
            self._holding.reserved = mine
        return mine


@dataclass(frozen=True)
class Outcome[T]:
    """What one job of a batch did: the value it returned, or the error it raised.

    `index` is the job's position in the sequence that was submitted, since the
    order futures complete in is not the order they were asked in.
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
    """Run jobs against one capacity, one to a thread, and collect what each did.

    `workers` defaults to the capacity's total, so no more threads are started
    than there could be slots to fill - any beyond that would only queue on a
    semaphore at a stack each. Every job is handed the same capacity, and the
    submitting thread's claims are inherited by the workers, so a slot reserved
    before the batch is taken up by the dispatch that uses it rather than counted
    twice. A job that raises is returned as a failed :class:`Outcome` and the
    rest still run; anything that is not an ``Exception`` - an interrupt above
    all - is raised rather than recorded as a job's failure.
    """
    if not jobs:
        return ()
    limit = workers if workers is not None else capacity.total
    if limit < 1:
        raise CapacityError(f"workers={limit} would run nothing; ask for at least 1")

    # The submitting thread's claim node, captured before any worker starts: each
    # worker runs inside a child of it, which is what lets a dispatch on a worker
    # thread take up a claim made here instead of reading it as demand with no
    # dispatcher.
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
                # Not a job's failure but an interrupt or an exit: it is raised,
                # so the executor's shutdown waits for the other jobs and no
                # caller can read it as one malformed contract among good ones.
                raise error
    return tuple(outcomes)
