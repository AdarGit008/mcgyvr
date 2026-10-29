"""One contract's route through one family's rungs, and the climb that spends it.

:func:`plan` turns a config and a source map into a :class:`Plan`: the family
the contract starts on (or the one a caller names) and that family's usable
rungs as :class:`Step` objects in the order the pool lists them, each carrying
the attempts it may spend and the :class:`Machine` — one source's place in a
:class:`~mcgyvr.capacity.Capacity` — that a slot on it is claimed through. A
rung's family is read through :func:`family_of`, which asks the catalog whether
the unit behind the rung needs a credential, so a plan holds rungs of one family
only: reaching a dearer family is :mod:`mcgyvr.escalate`'s job. A contract that
starts on the deterministic floor is planned as the
:class:`~mcgyvr.deterministic.ToolStep` objects that module binds, and falls
through to rungs only when no tool performs it.

:func:`climb` is the sequencing half. It walks a plan's steps, offering each to
a caller's attempt function up to the attempts that step was planned with, and
stops at the first pass. A declined answer ends that rung's attempts early,
because a rung that stepped aside has not been tried and failed. What comes back
is :class:`Accepted`, or an :class:`Exhausted` carrying both an
:class:`Exhaustion` reason and the :class:`Attempted` history behind it: a spent
family, a family that declined throughout, a plan with no rung, and a climb
whose budget the caller withheld are four different facts about an install, and
are told apart here rather than by reading a sentence.

Fan-out chooses where inside a family a climb starts and nothing else: outside
the api family, ``idle`` and ``full`` take the first rung that has a free slot
rather than the first rung,
a ``claimed`` rung is taken first because the caller already holds its slot, and
no mode reorders a plan or spends fewer attempts than ``none`` would.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from mcgyvr.catalog import Family, catalog

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.local_pool import Rung, SourceMap
    from mcgyvr.notes import FailureNotes


class RouteError(Exception):
    """What this module refuses rather than guesses at.

    A rung name the ladder does not list, a family the catalog does not declare,
    a declared fan-out mode that is not one of :class:`Fanout`, or a plan that
    holds a program where a climb was asked for.
    """


class Verdict(StrEnum):
    """What one attempt came to, and the only three answers routing acts on.

    ``PASSED`` ends the climb and accepts. ``FAILED`` spends the attempt and
    moves to the next one. ``DECLINED`` says the rung is not one that does this
    work: its remaining attempts are not spent and the plan moves on, which is
    what keeps a family that stepped aside distinguishable from one that tried
    and could not.
    """

    PASSED = "passed"
    FAILED = "failed"
    DECLINED = "declined"


class Exhaustion(StrEnum):
    """Why a climb ended without accepting anything.

    ``RUNGS_SPENT`` — the plan's attempts were spent and none passed.
    ``ALL_DECLINED`` — every attempt recorded declined, so nothing was actually
    tried. ``NO_RUNG`` — the plan had no rung to climb, and the plan's own
    ``reason`` says why. ``WITHHELD`` — the caller's ``permit`` refused to fund
    the next attempt, so the climb stopped short of what it was planned to cost.
    """

    RUNGS_SPENT = "rungs_spent"
    ALL_DECLINED = "all_declined"
    NO_RUNG = "no_rung"
    WITHHELD = "withheld"


class Fanout(StrEnum):
    """Where inside a family a climb starts, read from ``ladder.fanout``.

    ``NONE`` starts on the first rung of the plan whether or not it has room.
    ``IDLE`` and ``FULL`` start on the first rung that has a free slot; inside
    one family they are the same rule, and what separates them is reach, which
    is :mod:`mcgyvr.escalate`'s. Neither reorders a plan: a climb that starts
    higher still walks the rungs it passed over, so the spend is unchanged.
    Neither reaches a priced api rung: an api plan is climbed under
    ``NONE``, and only escalation enters the api family.
    """

    NONE = "none"
    IDLE = "idle"
    FULL = "full"


class Machine:
    """One source's place in a :class:`~mcgyvr.capacity.Capacity`, as a rung's machine.

    The source is the unit's name, and every question is answered at that
    source's own bound, so ``free`` is the limit less the load and ``full`` is
    what ``judge`` says with the server's in-flight count beside the local one.
    A source the capacity does not bound answers ``None`` rather than ``0``, so
    "not counted" stays distinguishable from "no room". Two machines are equal,
    and hash alike, when they name the same source: the capacity is how a slot
    is claimed, not part of what a machine is.
    """

    __slots__ = ("_source",)

    def __init__(self, source: str) -> None:
        self._source = source

    def __repr__(self) -> str:
        return "<machine>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Machine):
            return NotImplemented
        return self._source == other._source

    def __hash__(self) -> int:
        return hash(self._source)

    def load(self, capacity: Capacity, rung: str | None = None) -> int | None:
        """What is in flight on the source at the rung's bound.

        ``None`` when the capacity does not bound this source at all, which is
        not the same answer as a load of ``0``.
        """
        if self._source not in capacity.limits:
            return None
        return capacity.load(self._source, rung)

    def free(self, capacity: Capacity, rung: str | None = None) -> int | None:
        """The slots left at the rung's bound: its limit less its load.

        ``None`` when the capacity does not bound this source. The rung name is
        passed on because a rung may be bound narrower than its source, so the
        room to ask about is the rung's and not the source's.
        """
        if self._source not in capacity.limits:
            return None
        return capacity.limit(self._source, rung) - capacity.load(self._source, rung)

    def server(self, capacity: Capacity) -> int | None:
        """How many dispatches the server behind the source reports in flight.

        ``None`` when the capacity holds no way to ask, or does not bound this
        source: a server that was not read is not a server with nothing in
        flight.
        """
        if self._source not in capacity.limits:
            return None
        return capacity.server_busy(self._source)

    def full(
        self, capacity: Capacity, rung: str | None, server: int | None
    ) -> bool | None:
        """Whether the rung's bound is full, given that in-flight count.

        ``server`` is handed in because the caller is what reads it, once, for a
        whole sweep of rungs. ``None`` when the capacity does not bound this
        source, so a caller can tell "unknown" from "full".
        """
        if self._source not in capacity.limits:
            return None
        return capacity.judge(self._source, rung, server).full

    def claim(self, capacity: Capacity, rung: str | None = None) -> None:
        """Reserve one slot at the rung's bound, held until `release`.

        A source the capacity does not bound takes no reservation and is left
        alone, so a claim cannot make a source that counts nothing start
        counting.
        """
        if self._source in capacity.limits:
            capacity.reserve(self._source, rung)

    def release(self, capacity: Capacity, rung: str | None = None) -> None:
        """Give back the slot `claim` took, at the same bound."""
        capacity.release(self._source, rung)


@dataclass(frozen=True)
class Step:
    """One planned rung: what it may spend, and how a slot on it is claimed.

    ``machine`` is left out of equality on purpose. Two steps on the same rung
    with the same budget are the same step, and a machine is how to reach a
    capacity rather than something a plan is. A step with no machine is a rung
    no capacity was made for, and :func:`climb` takes it without claiming.
    """

    rung: Rung
    attempts: int
    machine: Machine | None = field(default=None, compare=False)


class Planned:
    """The steps a plan is made of, in the order they are tried.

    The tuple carries both kinds of step a plan can hold — a ``Step`` to climb
    and a ``ToolStep`` to run — and the properties here separate them, so no
    caller has to match on the union. ``budget`` counts every step's attempts
    and ``climb_budget`` only the rungs', so a program's attempts are never read
    as a climb's spend.
    """

    steps: tuple[Step | ToolStep, ...]

    @property
    def climbable(self) -> tuple[Step, ...]:
        """The steps that are rungs, in planned order."""
        return tuple(step for step in self.steps if isinstance(step, Step))

    @property
    def programs(self) -> tuple[ToolStep, ...]:
        """The steps that are programs: what ``mcgyvr.deterministic`` runs."""
        return tuple(step for step in self.steps if not isinstance(step, Step))

    @property
    def budget(self) -> int:
        """The attempts every step totals, programs included."""
        return sum(step.attempts for step in self.steps)

    @property
    def climb_budget(self) -> int:
        """The attempts the rungs total, which is what a climb can spend."""
        return sum(step.attempts for step in self.climbable)


@dataclass(frozen=True)
class Plan(Planned):
    """One family's route for one contract: the rungs, in the order they are tried.

    ``steps`` follow the ladder's own order whatever ``fanout`` says, because
    fan-out only chooses where a climb starts. ``reason`` is the sentence a plan
    with no steps carries for why it has none, and ``fanout`` is the mode the
    config declared, recorded here so that :func:`climb` need not read the
    config back; an api plan with rungs records ``NONE``, since fan-out never
    chooses a priced rung. ``bool`` and ``len`` both count steps, so a plan is falsy
    exactly when it has nothing to run, and not when it has nothing to climb.
    """

    family: Family
    steps: tuple[Step | ToolStep, ...]
    reason: str = ""
    fanout: Fanout = Fanout.NONE

    def __bool__(self) -> bool:
        return bool(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    @property
    def rungs(self) -> tuple[str, ...]:
        """The names of the plan's rungs, in planned order; programs are left out."""
        return tuple(step.rung.name for step in self.steps if isinstance(step, Step))


@dataclass(frozen=True)
class Try:
    """What an attempt function is handed: the rung, this attempt, and what to claim on.

    ``of`` is what the step was planned with and not what is left, so the pair
    reads ``attempt`` of ``of``. ``capacity`` is the one the climb was given and
    is ``None`` where the caller counts no slots.
    """

    rung: Rung
    attempt: int
    of: int
    capacity: Capacity | None = None


@dataclass(frozen=True)
class Result:
    """What an attempt function answers: a verdict, and the detail behind it.

    ``detail`` is the sentence a caller carries into the record; ``findings`` is
    the lines behind a refusal. The breadth fields report the dispatches the
    attempt made, and ``passed``, ``failed`` and ``declined`` are the
    constructors a driver uses, so that breadth is stated in one place instead
    of being spelled out at every call site.
    """

    verdict: Verdict
    detail: str = ""
    #: `findings` is why a failure was refused, one line per reason, and is empty
    #: on anything no gate refused: a passed or a declined result has no gate's
    #: reasons behind it to carry.
    findings: tuple[str, ...] = ()
    #: `notes` is the failure-notes record those lines are rendered from — what
    #: was observed, naming the rung and attempt — and `None` on a try that
    #: left none.
    notes: FailureNotes | None = None
    #: `draws` is the breadth this attempt asked for — from `draws_for`, which is
    #: the rung's `draws` entry over `breadth.draws` — whatever the verdict turned
    #: out to be. `rows` is how many of those draws left a record, so it is
    #: `draws` for a result that saw every candidate it asked for and `0` for one
    #: that declined before dispatching.
    #: `draw` is the draw this result is about, an index into `draws`. A row that
    #: is about no single draw says so by widening the type, which is what
    #: `Attempted.draw` does; the `0` kept here is the first draw and not a
    #: missing one.
    draw: int = 0
    draws: int = 1
    rows: int = 1

    # The three answers a driver gives, each written once so that the breadth is
    # stated in one place: `passed` and `failed` set `rows` to `draws`, because a
    # judged attempt left a row per candidate, and `declined` sets none.
    # None of these decides a verdict — it is the driver that knows what the gate
    # said — and none carries content beside the verdict, because content that
    # travels beside a verdict without being bound to it is how un-gated bytes
    # reach a repository.
    @classmethod
    def passed(cls, detail: str = "", *, draws: int = 1) -> Result:
        return cls(verdict=Verdict.PASSED, detail=detail, draws=draws, rows=draws)

    @classmethod
    def failed(cls, detail: str = "", *, draws: int = 1) -> Result:
        return cls(verdict=Verdict.FAILED, detail=detail, draws=draws, rows=draws)

    @classmethod
    def declined(cls, detail: str = "", *, draws: int = 1) -> Result:
        # A decline answered before dispatch leaves no row of its own: `rows` is
        # `0` while `draws` still says what the attempt asked for. That is what
        # makes a declined try cost nothing — `Exhausted.attempts_spent` does not
        # count it, and neither does a family's escalation count in
        # `mcgyvr.escalate`.
        return cls(verdict=Verdict.DECLINED, detail=detail, draws=draws, rows=0)


@dataclass(frozen=True)
class Attempted:
    """One try as it is recorded: which rung, which attempt there, and what it came to.

    ``detail``, ``findings``, ``notes``, ``draw``, ``draws`` and ``rows`` are
    copied out of the ``Result`` the attempt function answered, so a record can
    be read without the live result it came from. ``draw`` is ``int | None`` here where
    ``Result.draw`` is a bare ``int``, because a try that ended in an exception
    may be about no single draw at all. ``raised`` marks the row
    ``mcgyvr.escalate`` builds from such an exception: it reads ``FAILED`` with
    the cause in ``detail``, and the flag is what keeps "the gate said no" apart
    from "the machinery broke".
    """

    rung: str
    attempt: int
    verdict: Verdict
    detail: str = ""
    findings: tuple[str, ...] = ()
    #: `notes` is the failure-notes record behind `findings`, copied out of the
    #: `Result`, and `None` on a try that left none.
    notes: FailureNotes | None = None
    #: `draw` is the draw this try is about — an index into `draws` — and is
    #: `int | None` here where `Result.draw` is a bare `int`, because a try that
    #: raised may be about no single draw: `escalate` records `None` there.
    #: `0` is the field's default and means the first draw, so `None` is the only
    #: way to say "no particular one". Which draw a raise happened in is what
    #: `rows` says: it counts the draws that left a row, so the raise came at
    #: draw `rows - 1` or later, and with `rows` of `0` it came before anything
    #: was sent.
    draw: int | None = 0
    #: `draws` is the breadth the try asked for, whatever it came to: this
    #: rung's `draws` entry over `breadth.draws`, read by `draws_for`.
    draws: int = 1
    #: `rows` is how many of those draws left a row of their own: `draws`, unless
    #: the attempt raised part-way. It is `0` for a decline and `0` for a raise
    #: that happened before anything was sent, which is what `raised` is there to
    #: tell apart.
    rows: int = 1
    #: `raised` is set on a row built from an exception rather than from a
    #: `Result`: the row reads `FAILED` with the cause in `detail`, and no gate
    #: ever saw it. It is the one field here that is about the machinery instead
    #: of about the work.
    raised: bool = False
    #: `relief` is `True` when the rung is one lent through a hub rather than
    #: a step of the ladder. `model` and `address` name the unit that served
    #: the try, so a relief attempt can be read as the borrowed machine it
    #: actually ran on. A relief try is recorded like any other; it charges
    #: the budget only when it passes.
    relief: bool = False
    model: str = ""
    address: str = ""


def attempted(rung: str, attempt: int, result: Result) -> Attempted:
    """The record row for one try, copied out of the `Result` it came to.

    `raised` keeps its default: a `Result` is what an attempt function answered,
    so the row made from one is a judgement and not a raise.
    """
    return Attempted(
        rung=rung,
        attempt=attempt,
        verdict=result.verdict,
        detail=result.detail,
        findings=result.findings,
        notes=result.notes,
        draw=result.draw,
        draws=result.draws,
        rows=result.rows,
    )


@dataclass(frozen=True)
class Accepted:
    """A climb that passed: the family, the rung that passed, and every try made.

    ``history`` is in the order the tries were made, across every rung the climb
    took before that one, so the accepted try is its last row. ``ok`` is what
    makes this and ``Exhausted`` one answer to a caller asking whether the work
    was done.
    """

    family: Family
    rung: str
    history: tuple[Attempted, ...]

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class Exhausted:
    """A climb that ended without a pass, and the fact that says which ending it was.

    ``reason`` is the ``Exhaustion`` that distinguishes the endings, ``history``
    every try that was made — empty when the plan had no rung to climb — and
    ``detail`` the sentence a report shows. ``ok`` is ``False``, so it reads as
    the other half of ``Accepted`` to a caller that only wants to know whether
    the work is done.
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
        """The tries that cost something: every row whose verdict was not a decline.

        A declined attempt is a rung saying this work is not its kind, not the
        work being tried and failing, so counting it would make a family that
        stepped aside look like one that could not do the work.
        """
        return sum(1 for a in self.history if a.verdict is not Verdict.DECLINED)


# Which family a rung is in. A family is a fact about the unit a rung names —
# whether it needs a credential — and not a field anywhere in the ladder, so the
# question is answered by resolving the name and asking the catalog. Relief is
# resolved first because a relief rung the ladder does not name is never a step
# of it; one the ladder names is a unit of the dispatch and resolves either way.


def family_of(config: Config, rung: str) -> Family:
    """The catalog family of the rung of that name.

    A relief rung resolves through ``config.relief``, which holds the lent unit
    itself; a ladder rung through ``config.ladder`` and the unit that name points
    at. A name in neither raises ``RouteError`` listing what the ladder does
    offer, rather than reading as some default family.
    """
    lent = config.relief.get(rung)
    if lent is not None:
        return catalog().family_of(lent)
    name = config.ladder.get(rung)
    if name is None:
        offered = ", ".join(config.ladder.names) or "none"
        raise RouteError(f"no rung named {rung!r} in the ladder. Offered: {offered}")
    return catalog().family_of(config.units[name])


def by_family(config: Config, pool: SourceMap) -> Mapping[Family, tuple[Rung, ...]]:
    """The pool's usable rungs, grouped by the family each one is in.

    Every family the catalog declares is a key, so a caller asking about one gets
    ``()`` and not a ``KeyError`` — which is what lets :func:`plan` say why a
    family is empty instead of that it is unknown. Order inside a family is the
    pool's, which is the ladder's own. The floor is always empty here: no unit is
    ever in it, since the family is decided by whether the unit needs a
    credential.
    """
    known = catalog()
    grouped: dict[Family, list[Rung]] = {f: [] for f in known.families}
    for rung in pool.rungs:
        grouped[family_of(config, rung.name)].append(rung)
    return {family: tuple(rungs) for family, rungs in grouped.items()}


def attempts_for(family: Family, configured: int, contract: Contract) -> int:
    """How many attempts one rung of that family may spend.

    The floor is pinned to ``1`` whatever the config says, because a tool fails
    identically on a retry and there is no rung to climb. Above it the answer is
    the configured number capped by the contract's own ``limits.attempts``, so a
    contract can ask for less than the config allows and never for more.
    """
    return capped_attempts(family, configured, contract.limits.attempts)


def capped_attempts(family: Family, configured: int, limit: int) -> int:
    """:func:`attempts_for` with the contract's ``limits.attempts`` given as `limit`."""
    if family.rank == 0:
        return 1
    return min(configured, limit)


def plan(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    family: Family | None = None,
    capacity: Capacity | None = None,
) -> Plan:
    """The plan for one contract on one family.

    ``family`` defaults to the family the contract starts on; a family the
    catalog does not declare raises ``RouteError``. The floor is planned as the
    ``ToolStep`` objects ``mcgyvr.deterministic`` binds for the contract, if it
    binds any, because a program is run and not climbed; a floor with no program
    falls through to its rungs, which are always empty here, and so to the
    sentence :func:`_why_empty` writes. Above the floor there is one ``Step`` per
    usable rung, in the pool's order, each carrying the attempts
    :func:`attempts_for` allows and the ``Machine`` for the unit behind it.
    ``capacity`` is taken and not read: a plan names machines, and it is
    :func:`climb` that claims their slots.
    """
    chosen = family if family is not None else contract.kind.starts_on
    rungs = by_family(config, pool).get(chosen)
    if rungs is None:  # Not a family the catalog declares, so there is no floor.
        raise RouteError(f"{chosen.name!r} is not a family of the loaded catalog")

    mode = fanout_of(config)

    if chosen.rank == 0:
        # The floor runs tools and not a model on a source, so it is planned by
        # the module that binds them — imported here and not at the top, since
        # that module imports this one. A plan that comes back with programs is
        # finished: the floor has no rung for a climb to fall back on.
        from mcgyvr.deterministic import tool_steps

        tools = tool_steps(contract)
        if tools:
            return Plan(family=chosen, steps=tools)

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
    # Fan-out has no say inside the api family: a climb that reaches it
    # takes its priced rungs in ladder order, never a dearer free one first.
    return Plan(
        family=chosen, steps=steps, fanout=Fanout.NONE if priced(chosen) else mode
    )


def priced(family: Family) -> bool:
    """Whether `family` is the api one, whose rungs need a credential and cost."""
    return family.name == "api"


def fanout_of(config: Config) -> Fanout:
    """The fan-out mode the config declares, as a ``Fanout``.

    A value that is not one of the modes raises ``RouteError`` naming the ones
    there are, rather than falling back to ``none``: a config that says
    something this code does not know is a config whose author meant something
    by it.
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
    if config.ladder.get(rung) is None:
        # Only ladder rungs are planned, so a name missing from the ladder here
        # is a step built from something other than the pool.
        raise RouteError(f"no rung named {rung!r} in the ladder")
    attempts = config.get("attempts") or {}
    return int(attempts.get(rung, 1))


def draws_for(config: Config, rung: str) -> int:
    """How many candidates one attempt on that rung may ask for.

    This rung's entry under ``draws`` over the ``breadth.draws`` default, so a
    per-unit routing decision can widen one rung without moving the breadth of
    the whole run.
    """
    overrides = config.get("draws") or {}
    return int(overrides.get(rung, config.get("breadth.draws", 1)))


def _machines(config: Config, rungs: tuple[Rung, ...]) -> Mapping[str, Machine]:
    """One ``Machine`` per planned rung name, keyed by that name.

    A rung the ladder does not list raises ``RouteError``: every planned rung
    came from the pool's ladder rungs, so a name missing here means the pool and
    the config disagree about the ladder. The machines are made per plan and
    shared within it, which is all they are — a source name and nothing that
    outlives the plan.
    """
    made: dict[str, Machine] = {}
    by_rung: dict[str, Machine] = {}
    for rung in rungs:
        if config.ladder.get(rung.name) is None:
            # Not reachable from the pool, which lists ladder rungs only, so the
            # plan and the config are reading two different ladders here.
            raise RouteError(f"no rung named {rung.name!r} in the ladder")
        by_rung[rung.name] = made.setdefault(rung.name, Machine(rung.name))
    return by_rung


def _why_empty(config: Config, family: Family, pool: SourceMap) -> str:
    """The sentence an empty plan carries for why it has no steps.

    Three different absences, said differently because they are fixed
    differently: the floor has no program bound for this contract's task type on
    this target; a family whose rungs were all skipped is a configuration or
    availability problem, and names each skip; and a family with no rung
    configured at all says which kind of source to bind — one that declares an
    ``api_key_env`` for the api family, one that needs no credential for the
    rest.
    """
    if family.rank == 0:
        return (
            "the deterministic family runs tools, not a model on a source, and no "
            "tool is bound for this contract's task type on this target. It binds "
            "no rung either, so there is no ladder entry to configure: what is "
            "missing is a program for the type, not a source for a rung."
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


# Taking a step: choosing which rung of a plan to try next, and holding the slot
# it was chosen on. The choice and the claim happen under one hold of the lock,
# because a free slot read outside the lock it is claimed under is a slot another
# climb can take in between.


def _next_index(remaining: list[Step], mode: Fanout, capacity: Capacity) -> int:
    """The index in ``remaining`` of the step to take under that mode.

    ``NONE`` takes the head. ``IDLE`` and ``FULL`` take the first step whose
    machine has a free slot; a step with no machine, or whose source the capacity
    does not bound, takes the head instead, since nothing can be said about its
    room. Falling back to the head rather than skipping it is what keeps fan-out
    from turning a loaded ladder into a shorter one.
    """
    if mode is Fanout.NONE:
        return 0
    for index, step in enumerate(remaining):
        slots = (
            None
            if step.machine is None
            else step.machine.free(capacity, step.rung.name)
        )
        if slots is None:
            return 0
        if slots > 0:
            return index
    return 0


def _standing(remaining: list[Step], claimed: str | None) -> int | None:
    """The index in ``remaining`` of the rung the caller already holds a slot on.

    ``None`` when the caller claims nothing, or when that rung has already been
    taken; the mode then chooses.
    """
    if claimed is None:
        return None
    for index, step in enumerate(remaining):
        if step.rung.name == claimed:
            return index
    return None


def _claim_next(
    remaining: list[Step],
    mode: Fanout,
    capacity: Capacity | None,
    claimed: str | None = None,
) -> Step:
    """The next step to take, removed from ``remaining``, with its slot claimed.

    A caller's ``claimed`` rung is taken first and without a further claim,
    because that slot is already held — it is what an entry reserved before the
    climb is handed down as. Everything else is chosen by :func:`_next_index` and
    claimed as it is taken. With no capacity the head is taken and nothing is
    reserved, since there is nothing to count.
    """
    if capacity is None:
        return remaining.pop(0)
    with capacity.deciding():
        held = _standing(remaining, claimed)
        if held is not None:
            return remaining.pop(held)
        step = remaining.pop(_next_index(remaining, mode, capacity))
        if step.machine is not None:
            step.machine.claim(capacity, step.rung.name)
    return step


def _release(step: Step, capacity: Capacity | None) -> None:
    """Give back the slot the step was taken on.

    A step with no machine, or a climb given no capacity, holds nothing, so both
    are a no-op.
    """
    if step.machine is None or capacity is None:
        return
    step.machine.release(capacity, step.rung.name)


# The climb itself: the sequencing and the budget, with every dispatch left to
# the attempt function a caller passes in. Nothing here calls a model.


def climb(
    plan: Plan,
    attempt: Callable[[Try], Result],
    *,
    capacity: Capacity | None = None,
    permit: Callable[[Step, int], bool] | None = None,
    claimed: str | None = None,
) -> Accepted | Exhausted:
    """Climb one plan, offering each rung to ``attempt`` until something passes.

    Steps are taken in the plan's order, except that fan-out and a caller's
    ``claimed`` rung may choose where the climb starts; a step taken is removed,
    so a climb that starts higher still spends the attempts of the rungs it
    passed over. Each step offers ``attempt`` a ``Try`` for attempt ``1`` up to
    what the step was planned with, and the first ``PASSED`` returns ``Accepted``
    with the whole history. A ``FAILED`` spends that attempt and carries on; a
    ``DECLINED`` ends the step's attempts there, because a rung stepping aside is
    not a rung that failed. ``permit`` is asked before every attempt, and
    answering ``False`` returns ``WITHHELD`` rather than pretending the budget
    was there.

    ``capacity`` is what slots are claimed from, held for the length of one step,
    so two climbs on one machine cannot take the same last slot. ``claimed``
    names a rung whose slot the caller already holds — a reservation made before
    the climb — and is preferred, so that slot is used instead of a second one
    taken. A plan that is a program raises ``RouteError``: those belong to
    ``mcgyvr.deterministic``, and nothing here runs one. An exception from
    ``attempt`` is not caught: the slot is released on the way out and the
    exception propagates, so the rows this climb had already recorded are not
    returned with it.
    """
    history: list[Attempted] = []
    if not plan.steps:
        return Exhausted(
            family=plan.family,
            reason=Exhaustion.NO_RUNG,
            history=(),
            detail=plan.reason,
        )

    # Nothing is taken before the plan is answered: an empty plan is a NO_RUNG
    # carrying the plan's own sentence, and no attempt has been made at that
    # point, so its history is empty and says nothing about the ladder — the
    # plan's `reason` is what explains the absence.
    # A plan holding a program is refused outright, naming the operations it
    # holds, and that check comes after the empty one because an empty plan has
    # no operation to name.
    # What is left is rungs, so `climbable` is the whole of it.
    steps = plan.climbable
    if plan.programs:
        named = ", ".join(sorted({step.tool.operation for step in plan.programs}))
        raise RouteError(
            f"the {plan.family.name!r} plan is a program, not a rung, so it is "
            f"not climbed: run it through `mcgyvr.deterministic` instead "
            f"({named})."
        )

    remaining = list(steps)
    # `remaining` is a list and not a tuple because a step is taken by removing
    # it: the order tried is the order popped, and no step can be taken twice.
    # The mode decides the first choice only; after that the plan's own order is
    # kept, which is why `choosing` is reset to NONE below.
    choosing = plan.fanout
    # The caller's claimed rung is preferred for that first choice alone: it is a
    # slot already held, so `holding` is dropped once one step has been taken and
    # every later step claims its own.
    holding = claimed
    while remaining:
        step = _claim_next(remaining, choosing, capacity, holding)
        choosing = Fanout.NONE
        holding = None
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
                history.append(attempted(step.rung.name, number, result))
                if result.verdict is Verdict.PASSED:
                    return Accepted(
                        family=plan.family,
                        rung=step.rung.name,
                        history=tuple(history),
                    )
                if result.verdict is Verdict.DECLINED:
                    # A decline ends this rung's attempts: the rest are not
                    # spent, because the rung is saying the work is not its kind
                    # rather than that this try went wrong.
                    break
        finally:
            # Released whatever the step came to, a raise from `attempt`
            # included: a slot held past its step would be capacity nobody can
            # send to. A decline leaves through the `break` above and arrives
            # here as well.
            _release(step, capacity)

    declined_only = all(a.verdict is Verdict.DECLINED for a in history)
    return Exhausted(
        family=plan.family,
        reason=Exhaustion.ALL_DECLINED if declined_only else Exhaustion.RUNGS_SPENT,
        history=tuple(history),
        detail=_exhausted_detail(plan, history, declined_only),
    )


def _exhausted_detail(plan: Plan, history: list[Attempted], declined_only: bool) -> str:
    """The sentence an exhausted climb carries, naming what it tried.

    ``declined_only`` decides which fact is the true one: a family that declined
    throughout spent nothing and says so, while a family that spent attempts
    names how many, across which rungs. The rungs are listed in the order they
    were first tried and once each, so a rung tried three times appears once.
    """
    tried = tuple(dict.fromkeys(a.rung for a in history))
    rungs = ", ".join(tried)
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
