"""Routing: which rung a contract is tried on, and when a family is spent (#24).

The ladder is ordered cheapest to dearest in two nested ways. *Families* —
deterministic tools, then local models, then API models (ADR-0001 boundary 3) —
are the coarse order, and they are declared in the catalog with a rank. *Rungs*
are the fine order inside a family, and they are whatever the operator wrote in
the config. This module walks the fine order. It does not walk the coarse one.

**That split is the acceptance criterion, not a stylistic preference.** #24 owns
climbing rungs within one family and naming the moment that family is spent;
#43 owns what happens next, because crossing from local to API is a spend
decision with its own rules — ascent is monotonic, a global ceiling bounds the
task, and a contract that declared no verification is upgraded the moment it
leaves the deterministic family. Splitting those two rules across two modules
would mean neither module could be read on its own, so the boundary here is
hard: nothing in this file ever looks at a family other than the one it was
asked about, and :func:`plan` returns an empty plan naming its reason rather
than quietly reaching for a dearer rung. #43's task-wide ceiling reaches in as
a *predicate* (:func:`climb`'s ``permit``) for the same reason the attempt
function is one — a budget that spans families cannot be computed here, and a
module that took the number instead of the question would be holding half of a
rule it cannot see the other half of.

**A plan is inspectable before anything is spent.** :func:`plan` answers "which
rungs, in what order, with how many attempts each" without dispatching, which is
what makes routing reproducible rather than merely deterministic: the decision
can be printed, diffed and asserted on. :func:`climb` then executes a plan
against an attempt function the caller supplies. Nothing here assembles a
prompt, applies a diff or runs a gate — those are #25's, #43's and E5's, and a
routing module that did them could not be tested without a model.

**Attempts are policy, and the default is to escalate rather than retry.** Two
numbers meet: the rung's own ``attempts`` (``config.ladder.tiers[].attempts``,
default 1) and the contract's ``limits.attempts``, whose schema calls it a hard
ceiling on one execution. The lower wins, so an operator lowering a rung's
budget is obeyed and a contract lowering its own is obeyed, and neither can
raise the other. The default of 1 means a failed attempt escalates: a retry
re-runs the same model on the same input, and the figure this rule was
inherited with — worker-tier remediation rescued 2 of 35 failures — says that is
usually spend without a result. **That figure is inherited from local-ai and has
not been re-verified here** (ADR-0004, and #152 is where it gets settled), which
is why it argues for a default rather than being quoted as a measurement of
mcgyvr.

**The deterministic family gets exactly one attempt, and it is not on the
ladder.** A tool fails identically on retry, so a second attempt is spend with a
known-in-advance result; :func:`attempts_for` returns 1 for it whatever the
config says. But no configuration can put a rung in that family: a rung's family
comes from whether its *source* needs a credential
(:meth:`~mcgyvr.catalog.Catalog.family_of`), and the deterministic tier binds no
source because it is a program, not a model. So :func:`plan` for the
deterministic family is empty by construction today, and says so in words. #81
is the tier itself; when it lands it supplies the step, and the budget rule here
already covers it.

**Declining is not failing.** An attempt may answer that this rung cannot do
this contract at all — #81's rule, and the reason it exists is that a
deterministic tool emitting a plausible-but-wrong edit is far more expensive
than one that steps aside. A decline moves to the next rung without spending an
attempt and without being recorded as a failure, which is why
:class:`Exhaustion` distinguishes a family whose rungs all declined from one
whose attempts were spent.

**Fan-out breaks a tie inside a family; it never reorders the ladder.**
``ladder.fanout`` is the knob and ``none`` is its default, which is this
module as it was: a batch of contracts sharing a task type shares a floor
family, so every one of them takes the cheapest rung and queues there while a
peer serving the same model sits idle — and raising ``max_parallel`` does not
fix that, it widens the rig that was already the only one being used. Under
``full`` :func:`climb` starts on the *least-loaded* rung of the plan instead of
the first. :func:`plan` still orders by price and nothing may make it do
otherwise, because price order is what a ladder means and a plan that put a
busy rung last would be deciding, from inside one family, that load outranks
price. A tie goes to the cheaper rung, so ``full`` on an idle ladder is
``none`` on an idle ladder exactly, and preferring a free peer that serves the
same model costs nothing that could be called an escalation.

``idle`` is not honoured here, and reads as ``none`` from inside this file.
Its choice is the cheapest rung *at or above the floor* with a free slot, which
may be a priced api rung — a spend decision that crosses families, and #24's
boundary is that nothing here looks at a family other than the one it was asked
about. :func:`mcgyvr.escalate.ascent` already holds the view that mode needs.
And busy is never a verdict: a rung this module passed over for a free peer was
not tried and did not fail, so no amount of load can fund an escalation.

**What is deliberately not here.** Risk floors raising where work may start are
#16's; this module reads the type's floor from the catalog and applies nothing
on top of it. Draws per rung — trying a rung twice at temperature and taking the
first candidate the gate accepts — are #119's and ADR-0008's, and are a
different axis from attempts: a draw is a fresh sample, an attempt is a retry
after a verdict. Grouping the ladder by family discards the operator's
cross-family ordering, which is only visible in a ladder that interleaves
families (a local rung written below an API one); nothing depends on that today
because nothing here crosses families, and #153 records it against #43, which is
where it first becomes observable.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from mcgyvr.catalog import Family, catalog

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.pool import Rung, SourceMap


class RouteError(Exception):
    """A route could not be planned from the inputs given."""


class Verdict(StrEnum):
    """What one attempt on one rung came to.

    Three outcomes, and the third is the one that carries information the other
    two cannot. ``FAILED`` means the rung tried and did not produce an
    acceptable change; ``DECLINED`` means it did not try, because the contract
    is not work of a kind it can do. A caller that collapsed the two would spend
    a rung's budget on rungs that never ran.
    """

    PASSED = "passed"
    FAILED = "failed"
    DECLINED = "declined"


class Exhaustion(StrEnum):
    """Why a family ended without an accepted result.

    Machine-readable because #24 requires family exhaustion to be
    distinguishable from every other failure, and because the cases want
    different responses: spent attempts are a real signal that this family is
    not up to the work, universal declines say nothing about the family's
    ability at all, and no rung at all is a configuration fact.

    ``WITHHELD`` is the fourth and is not about the family: a caller's budget
    guard refused to fund the next attempt, so the family says nothing about
    itself because it was not allowed to finish. It is kept distinct for the
    same reason the other three are — a family stopped by someone else's
    ceiling must not read like one that was tried and could not.
    """

    RUNGS_SPENT = "rungs_spent"
    ALL_DECLINED = "all_declined"
    NO_RUNG = "no_rung"
    WITHHELD = "withheld"


class Fanout(StrEnum):
    """How a batch of contracts spreads over the rungs it may run on.

    The three modes of ``ladder.fanout``, mirrored here as an enum so that a
    plan carries a decided value rather than a string a caller has to remember
    the spellings of. It is a knob and not a behaviour because the right answer
    is a property of the machines: two interchangeable rigs should share a
    batch, and a throughput rig feeding an intelligence rig must not, since the
    second is sized to drain the first's failure tail.

    Only ``FULL`` changes anything in this module. ``IDLE``'s choice may cross
    from the floor family into a priced one, which is #43's to make and not
    #24's, so it is carried and not acted on here — see the module docstring.
    """

    NONE = "none"
    IDLE = "idle"
    FULL = "full"


# How many attempts this process currently has in flight on each source, by
# source name. Module state, deliberately, and it is the smallest thing that
# makes ``full`` mean anything. :meth:`~mcgyvr.capacity.Capacity.in_use` counts
# slots that have been *granted*, and every member of a batch chooses its rung
# before any of them has been granted one — so six climbs reading only that
# number would read six zeroes, all choose the cheapest rung, and queue on it,
# which is the funnel the knob exists to end. Counting an attempt from the
# moment it is chosen rather than from the moment it is admitted is what makes
# the spread a fact instead of a race between threads. It is keyed by source
# name and not by :class:`Machine`, because every contract of a batch plans
# separately and would otherwise count its own machines and nobody else's.
_in_flight: dict[str, int] = {}
_in_flight_lock = threading.Lock()


class Machine:
    """What a rung runs on, as a question rather than as a name (#20).

    Load is a property of the machine and of nothing else: two rungs bound to
    one source are two names for one queue, so a fan-out that compared rungs
    would "spread" a batch across a single box. But a plan is a thing that gets
    printed, and #20's rule is that nothing above the execution seam learns
    where work runs — a :class:`~mcgyvr.pool.Rung` says a name and a model and
    deliberately nothing else, which is what lets a rung be re-pointed at
    another machine without anything above noticing.

    Both hold if the plan carries the *question* instead of the answer, which is
    the same move :func:`climb` makes with ``permit`` and with its attempt
    function. The source name stays private, this renders as ``<machine>``
    wherever a plan is printed, and the only thing anyone above can do with one
    is ask how busy it is. Rungs sharing a source share an instance, so "same
    box" is answerable without anyone being told which box.
    """

    __slots__ = ("_source",)

    def __init__(self, source: str) -> None:
        self._source = source

    def __repr__(self) -> str:
        return "<machine>"

    def load(self, capacity: Capacity) -> int | None:
        """How busy this machine is, or ``None`` if this capacity cannot say.

        The greater of the slots ``capacity`` has granted and the attempts this
        process has started on it, because neither alone is the load: granted
        under-reports a batch that is mid-choice, which is exactly when this is
        asked, and started misses every dispatch that did not come through
        :func:`climb` — another process's share of the same host-wide slot files
        included (#185).

        ``None`` when the capacity does not bound this source at all, which is a
        capacity and a plan built from different configs; it is an ordinary
        answer here rather than an error, because the caller's response is to
        keep price order rather than to fail a climb over a number nobody asked
        for. A caller about to *act* on the answer reads it under
        :data:`_in_flight_lock`, as :func:`_claim_next` does, because choosing
        and claiming have to be one decision.
        """
        if self._source not in capacity.limits:
            return None
        return max(capacity.in_use(self._source), _in_flight.get(self._source, 0))

    def claim(self) -> None:
        """Count one more attempt in flight here. Called under the module lock."""
        _in_flight[self._source] = _in_flight.get(self._source, 0) + 1

    def release(self) -> None:
        """Stop counting one. Called under the module lock, always in a finally."""
        left = _in_flight.get(self._source, 0) - 1
        if left > 0:
            _in_flight[self._source] = left
        else:
            _in_flight.pop(self._source, None)


@dataclass(frozen=True)
class Step:
    """One rung of a plan, with the number of attempts it is allowed.

    ``machine`` is what the rung runs on, as a :class:`Machine` — a thing that
    answers "how busy" and names nothing. ``None`` for a step nobody bound to a
    machine, which is a step no load can be read for and which is therefore
    taken in price order whatever the fan-out mode says.
    """

    rung: Rung
    attempts: int
    machine: Machine | None = None


@dataclass(frozen=True)
class Plan:
    """The rungs of one family a contract may be tried on, cheapest first.

    Empty is an ordinary answer rather than an error: a keyless install
    planning an ``api`` family has no rungs, and so does every plan for the
    deterministic family. ``reason`` says which, in words, so that a caller
    reporting "nothing ran" can say why without inspecting the config itself.

    ``fanout`` is the mode the ladder was configured with, carried on the plan
    so that :func:`climb` can honour it without being handed a
    :class:`~mcgyvr.config.Config`. It says nothing about the order of
    ``steps``, which is price order under every mode — only about which of them
    a climb starts on.
    """

    family: Family
    steps: tuple[Step, ...]
    reason: str = ""
    fanout: Fanout = Fanout.NONE

    def __bool__(self) -> bool:
        return bool(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    @property
    def rungs(self) -> tuple[str, ...]:
        """The rung names in the order they would be tried."""
        return tuple(step.rung.name for step in self.steps)

    @property
    def budget(self) -> int:
        """The most attempts this plan could spend before the family is spent."""
        return sum(step.attempts for step in self.steps)


@dataclass(frozen=True)
class Try:
    """What an attempt function is handed: a rung, its place in the budget, and
    the capacity it must dispatch under.

    ``capacity`` is passed through to every attempt rather than captured once by
    the caller because :func:`~mcgyvr.runner.dispatch` is unbounded by default —
    a ladder walk that threaded a capacity into the first rung and not the rest
    would enforce a source's limit on some of its dispatches, which is the same
    as not enforcing it. ``None`` is a legitimate value for a single task
    running alone; :func:`~mcgyvr.capacity.run_batch` is where it stops being.
    """

    rung: Rung
    attempt: int
    of: int
    capacity: Capacity | None = None


@dataclass(frozen=True)
class Result[T]:
    """What an attempt function reports back.

    Built through :meth:`passed`, :meth:`failed` or :meth:`declined` rather than
    by hand, so that a verdict is always chosen deliberately — a positional
    boolean is exactly how "cannot approve" comes to mean approved.
    """

    verdict: Verdict
    value: T | None = None
    detail: str = ""

    @classmethod
    def passed(cls, value: T, detail: str = "") -> Result[T]:
        return cls(verdict=Verdict.PASSED, value=value, detail=detail)

    @classmethod
    def failed(cls, detail: str = "") -> Result[T]:
        return cls(verdict=Verdict.FAILED, detail=detail)

    @classmethod
    def declined(cls, detail: str = "") -> Result[T]:
        return cls(verdict=Verdict.DECLINED, detail=detail)


@dataclass(frozen=True)
class Attempted:
    """One entry in the record of what a climb actually did.

    Kept for every rung touched, including the ones that declined, because a
    climb that reported only its failures would make a family that was never
    tried look like one that was tried and could not.
    """

    rung: str
    attempt: int
    verdict: Verdict
    detail: str = ""


@dataclass(frozen=True)
class Accepted[T]:
    """A climb that ended with a rung producing an acceptable result.

    ``value`` is whatever the attempt function handed back — this module never
    inspects it, which is what keeps routing testable without a model.
    """

    family: Family
    rung: str
    value: T | None
    history: tuple[Attempted, ...]

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class Exhausted:
    """A climb that ended with the family spent, and why.

    This is the named outcome #24 asks for. It is a distinct type rather than a
    flag on a shared one so that a caller cannot reach for a result that was
    never produced, and so that escalation (#43) reads as a match on the answer
    rather than as a boolean it has to remember the polarity of.
    """

    family: Family
    reason: Exhaustion
    history: tuple[Attempted, ...]
    detail: str = ""

    @property
    def ok(self) -> bool:
        return False

    @property
    def attempts_spent(self) -> int:
        """How many attempts were actually consumed — declines are not attempts."""
        return sum(1 for a in self.history if a.verdict is not Verdict.DECLINED)


# --- the family view of a configured ladder --------------------------------


def family_of(config: Config, rung: str) -> Family:
    """Which family the rung named ``rung`` belongs to.

    Resolved through the config's tier binding and the catalog's one rule, so
    this module never restates what a family *is*. Raises rather than guessing
    for an unknown rung: a caller asking about a name the ladder does not offer
    has a bug, not a routing question.
    """
    tier = config.ladder.get(rung)
    if tier is None:
        offered = ", ".join(t.name for t in config.ladder.tiers) or "none"
        raise RouteError(f"no rung named {rung!r} in the ladder. Offered: {offered}")
    return catalog().family_of(config.sources[tier.source])


def by_family(config: Config, pool: SourceMap) -> Mapping[Family, tuple[Rung, ...]]:
    """The usable rungs grouped by family, cheapest family first.

    Every declared family is a key, including the ones with no rungs — an empty
    tuple is the answer to "what can this install run locally", and it is a
    different answer from the family not existing. Within a family the rungs
    keep the order the operator wrote them in, because that is the ladder.

    Only rungs the pool is offering appear: a rung skipped for a missing
    credential or an unreachable source is not something to route work to, and
    :class:`~mcgyvr.pool.SourceMap` has already recorded why it is absent.
    """
    known = catalog()
    grouped: dict[Family, list[Rung]] = {f: [] for f in known.families}
    for rung in pool.rungs:
        grouped[family_of(config, rung.name)].append(rung)
    return {family: tuple(rungs) for family, rungs in grouped.items()}


def attempts_for(family: Family, configured: int, contract: Contract) -> int:
    """How many attempts one rung of ``family`` gets for ``contract``.

    The lower of the rung's configured budget and the contract's declared
    ceiling, except in the deterministic family, which gets exactly one whatever
    either says. That exception is not a special case being carved out — a tool
    is a program, so its second attempt is its first attempt again, and a budget
    that permitted it would be describing spend nobody could benefit from.
    """
    if family.rank == 0:
        return 1
    return min(configured, contract.limits.attempts)


def plan(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    family: Family | None = None,
    capacity: Capacity | None = None,
) -> Plan:
    """The rungs of one family this contract may be tried on, in order.

    ``family`` defaults to the contract's type floor from the catalog — where
    work of this type may *begin*. It is deliberately not adjusted here when the
    floor's family has no rungs: satisfying a floor with a dearer family is an
    ascent, ascent is #43's, and doing it quietly here would put half of "each
    family is entered at most once" in a module that cannot see the other half.
    An install whose floor family is empty gets an empty plan that names the
    situation, which is the input #43 acts on.

    ``capacity`` is accepted and changes nothing, which is the point of its
    being accepted at all. A caller holding one reaches for this seam first, and
    the guarantee worth being able to state at it is that the ladder it gets
    back is the same ladder: load may break a tie between rungs, and it may
    never rewrite the order they are written in. The load-aware choice is
    :func:`climb`'s instead, for a reason beyond tidiness — load read here would
    be a reading from before the batch started, and the only moment it is true
    is the moment an attempt is about to be made. What this function does carry
    is the *mode*, so that a climb can honour ``ladder.fanout`` without being
    handed a whole config.
    """
    chosen = family if family is not None else contract.type.starts_on
    rungs = by_family(config, pool).get(chosen)
    if rungs is None:  # a Family from another catalog than the one loaded here
        raise RouteError(f"{chosen.name!r} is not a family of the loaded catalog")
    mode = fanout_of(config)
    if not rungs:
        return Plan(
            family=chosen,
            steps=(),
            reason=_why_empty(config, chosen, pool),
            fanout=mode,
        )

    machines = _machines(config, rungs)
    steps = tuple(
        Step(
            rung=rung,
            attempts=attempts_for(
                chosen, _configured_attempts(config, rung.name), contract
            ),
            machine=machines[rung.name],
        )
        for rung in rungs
    )
    return Plan(family=chosen, steps=steps, fanout=mode)


def fanout_of(config: Config) -> Fanout:
    """The configured fan-out mode, as a decided value rather than a string.

    Raises rather than falling back to the default for a mode nobody declared:
    the schema's ``choices`` already refuse an unknown one at parse, so reaching
    this means a config was assembled by hand, and quietly routing it as ``none``
    would answer a question about spreading a batch by not spreading it.
    """
    declared = config.ladder.fanout
    try:
        return Fanout(declared)
    except ValueError as exc:
        offered = ", ".join(m.value for m in Fanout)
        raise RouteError(
            f"{declared!r} is not a fan-out mode. Offered: {offered}"
        ) from exc


def _configured_attempts(config: Config, rung: str) -> int:
    tier = config.ladder.get(rung)
    if tier is None:  # unreachable: the rung came from the pool, which came from here
        raise RouteError(f"no rung named {rung!r} in the ladder")
    return tier.attempts


def _machines(config: Config, rungs: tuple[Rung, ...]) -> Mapping[str, Machine]:
    """One :class:`Machine` per source, shared by every rung bound to it.

    Shared on purpose: a ladder with two rungs on one box is one queue, and
    handing each rung its own machine would let a fan-out "spread" a batch
    across a box it never left.
    """
    made: dict[str, Machine] = {}
    by_rung: dict[str, Machine] = {}
    for rung in rungs:
        tier = config.ladder.get(rung.name)
        if tier is None:  # unreachable: the rung came from the pool, from here
            raise RouteError(f"no rung named {rung.name!r} in the ladder")
        by_rung[rung.name] = made.setdefault(tier.source, Machine(tier.source))
    return by_rung


def _why_empty(config: Config, family: Family, pool: SourceMap) -> str:
    """Why a family offers nothing, in the terms that make it actionable.

    The deterministic family is empty for a structural reason that no config
    edit will change, so saying "no rung is bound to it" would send an operator
    to the wrong file. Every other family is empty either because nothing was
    bound to it or because what was bound could not be offered, and the pool
    already holds the reason for the second case.

    Only *this family's* skipped rungs are quoted. A local rung that was skipped
    says nothing about why the api family is empty, and offering it as the
    explanation would send someone to fix a source that was never the problem.
    """
    if family.rank == 0:
        return (
            "the deterministic family binds no rung: it is tools, not a model on "
            "a source. Its executor is the deterministic tier (#81), which is not "
            "reached through the ladder."
        )
    mine = [s for s in pool.skipped if family_of(config, s.name) == family]
    if mine:
        why = "; ".join(f"{s.name}: {s.reason}" for s in mine)
        return (
            f"every rung of the {family.name!r} family was skipped ({why}), so "
            f"this is a configuration or availability problem rather than an "
            f"empty ladder."
        )
    return (
        f"no configured rung is in the {family.name!r} family — bind one to a "
        f"source that "
        + ("declares an api_key_env" if family.name == "api" else "needs no credential")
        + "."
    )


# --- which rung a climb takes next -----------------------------------------


def _next_index(remaining: list[Step], mode: Fanout, capacity: Capacity | None) -> int:
    """Which of the rungs still untried to take next: the first, unless ``full``.

    Under every mode but ``full`` this is ``0`` — the cheapest rung still
    standing, byte for byte the order this module has always walked. Under
    ``full`` it is the least-loaded of them, and a tie is broken by price
    because ``min`` returns the first minimum: on an idle ladder every rung ties
    at zero, so ``full`` there is ``none`` there and nothing was reordered by
    load that load had nothing to say about.

    Falls back to price order when the loads cannot all be read — no capacity to
    read them from, a step bound to no machine, or a machine this capacity does
    not bound. A partial view would order the ladder by which rungs a capacity
    happened to know about, which is not a fact about load at all.
    """
    if mode is not Fanout.FULL or capacity is None:
        return 0
    loads: list[int] = []
    for step in remaining:
        load = None if step.machine is None else step.machine.load(capacity)
        if load is None:
            return 0
        loads.append(load)
    return min(range(len(loads)), key=loads.__getitem__)


def _claim_next(remaining: list[Step], mode: Fanout, capacity: Capacity | None) -> Step:
    """Take the next step off ``remaining`` and count it as in flight.

    Choosing and counting are one decision and so happen under one lock: a
    climb that read the loads, released the lock and only then said which rung
    it had taken would leave a window in which every member of a batch reads
    the same zeroes — the funnel again, narrowed to microseconds but not closed.
    """
    with _in_flight_lock:
        step = remaining.pop(_next_index(remaining, mode, capacity))
        if step.machine is not None:
            step.machine.claim()
    return step


def _release(machine: Machine | None) -> None:
    """Stop counting an attempt that has ended, however it ended."""
    if machine is None:
        return
    with _in_flight_lock:
        machine.release()


# --- executing a plan ------------------------------------------------------


def climb[T](
    plan: Plan,
    attempt: Callable[[Try], Result[T]],
    *,
    capacity: Capacity | None = None,
    permit: Callable[[Step, int], bool] | None = None,
) -> Accepted[T] | Exhausted:
    """Try each rung of ``plan`` in turn until one passes or the family is spent.

    ``attempt`` is the caller's — it is what actually assembles a prompt,
    dispatches, applies and gates, none of which is routing. Keeping it a
    parameter is what lets every rule in this module be asserted without a
    model, a backend or a sandbox, and it is the same move
    :func:`~mcgyvr.capacity.run_batch` makes with a job.

    ``permit`` is the caller's too, and for the same reason. It is asked before
    each attempt is funded and ends the climb when it answers no. A task-wide
    ceiling spans families, so it cannot be computed from a plan — but neither
    may it live here, because #24's boundary is that nothing in this module
    looks past the family it was asked about. A predicate keeps both true: the
    caller knows what its budget means and this module never does, exactly as
    it never knows what an attempt does. The refusal is reported as
    :attr:`Exhaustion.WITHHELD`, which says the family did not finish rather
    than that it failed; naming *whose* ceiling stopped it is the caller's, and
    :mod:`mcgyvr.escalate` is where that happens.

    An attempt that raises is not caught. A verdict is a judgement the attempt
    function made; an exception is one it could not make, and swallowing it into
    an exhaustion would report "this family cannot do the work" when what
    happened was a bug or a dead socket. :func:`~mcgyvr.capacity.run_batch`
    already turns a raising job into a named failure beside its neighbours,
    which is the right place for that to happen.

    ``capacity`` is also what makes ``full`` fan-out possible, and this is the
    only place in the module load is read. Under :attr:`Fanout.FULL` each rung
    is taken in order of how busy its machine is rather than off the top of the
    plan; under every other mode the walk is the plan's own order, unchanged.
    Either way *every* rung is walked, each keeps its own budget, and ``permit``
    is asked before each attempt — fan-out decides which rung is tried first,
    never how many may be tried. Nor can it fail one: a rung passed over for a
    free peer produces no verdict and no history entry, so a busy ladder cannot
    fund an escalation the way a failing one does.
    """
    history: list[Attempted] = []
    if not plan.steps:
        return Exhausted(
            family=plan.family,
            reason=Exhaustion.NO_RUNG,
            history=(),
            detail=plan.reason,
        )

    remaining = list(plan.steps)
    while remaining:
        step = _claim_next(remaining, plan.fanout, capacity)
        try:
            for number in range(1, step.attempts + 1):
                if permit is not None and not permit(step, number):
                    return Exhausted(
                        family=plan.family,
                        reason=Exhaustion.WITHHELD,
                        history=tuple(history),
                        detail=(
                            f"the climb stopped at {step.rung.name!r} attempt "
                            f"{number}: the caller's budget did not fund it."
                        ),
                    )
                result = attempt(
                    Try(
                        rung=step.rung,
                        attempt=number,
                        of=step.attempts,
                        capacity=capacity,
                    )
                )
                history.append(
                    Attempted(
                        rung=step.rung.name,
                        attempt=number,
                        verdict=result.verdict,
                        detail=result.detail,
                    )
                )
                if result.verdict is Verdict.PASSED:
                    return Accepted(
                        family=plan.family,
                        rung=step.rung.name,
                        value=result.value,
                        history=tuple(history),
                    )
                if result.verdict is Verdict.DECLINED:
                    # A decline is about the contract, not about this attempt,
                    # so trying the same rung again would ask a question already
                    # answered. It costs the rung's remaining budget nothing.
                    break
        finally:
            # However this rung ended — passed, declined, withheld, spent or
            # raised — it is no longer in flight, and a count that leaked would
            # make the machine look busy to every later climb in this process.
            _release(step.machine)

    declined_only = all(a.verdict is Verdict.DECLINED for a in history)
    return Exhausted(
        family=plan.family,
        reason=Exhaustion.ALL_DECLINED if declined_only else Exhaustion.RUNGS_SPENT,
        history=tuple(history),
        detail=_exhausted_detail(plan, history, declined_only),
    )


def _exhausted_detail(plan: Plan, history: list[Attempted], declined_only: bool) -> str:
    """One sentence saying what was tried, for a caller reporting upward."""
    rungs = ", ".join(plan.rungs)
    if declined_only:
        return (
            f"every rung of the {plan.family.name!r} family declined this "
            f"contract ({rungs}); no attempt was spent."
        )
    spent = sum(1 for a in history if a.verdict is not Verdict.DECLINED)
    return (
        f"the {plan.family.name!r} family is spent: {spent} attempt(s) across "
        f"{rungs} and none produced an acceptable result."
    )
