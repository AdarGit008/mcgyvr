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
source because it is a program, not a model. So :func:`plan` for that family
answers from the task type instead (#81, :mod:`mcgyvr.deterministic`), and what
it returns is a program — which is why a plan's steps are two types and why
:attr:`Plan.climbable` exists. A caller that read ``bool(plan)`` as "there is
something to climb" was right only while the floor was empty; it holds work and
nothing climbable now, and :func:`climb` refuses the difference by name.

**Declining is not failing.** An attempt may answer that this rung cannot do
this contract at all — #81's rule, and the reason it exists is that a
deterministic tool emitting a plausible-but-wrong edit is far more expensive
than one that steps aside. A decline moves to the next rung without spending an
attempt and without being recorded as a failure, which is why
:class:`Exhaustion` distinguishes a family whose rungs all declined from one
whose attempts were spent.

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

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from mcgyvr.catalog import Family, catalog

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.deterministic import ToolStep
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


@dataclass(frozen=True)
class Step:
    """One rung of a plan, with the number of attempts it is allowed."""

    rung: Rung
    attempts: int


class Planned:
    """Reading a tuple of steps as rungs and as programs, in one place.

    Two types carry ``tuple[Step | ToolStep, ...]`` — :class:`Plan`, which is one
    family's answer, and :class:`~mcgyvr.deterministic.Routed`, which is the
    floor router's — and every question worth asking about that tuple is the
    same question for both. It is stated here once because the alternative was
    tried: ``Plan`` gained :attr:`climbable` when #81 bound the floor, ``Routed``
    did not, and a caller holding the second had truthiness and nothing else —
    which is precisely the misreading :attr:`climbable` was added to end.

    A plain base rather than a dataclass one: it holds no field, only the four
    readings of the field its subclasses declare, and a dataclass base would put
    ``steps`` in both constructors' signatures from a class that cannot supply
    one.
    """

    steps: tuple[Step | ToolStep, ...]

    @property
    def climbable(self) -> tuple[Step, ...]:
        """The steps :func:`climb` can run: rungs, never programs.

        The question every reader of a plan actually has, asked once here rather
        than by each of them. ``bool(plan)`` answers "is there anything here",
        which was the same question only while the floor was empty by
        construction; since #81 bound it, a family can hold work and hold
        nothing to climb, and a caller that kept using truthiness would enter a
        family whose only step :func:`climb` refuses.
        """
        return tuple(step for step in self.steps if isinstance(step, Step))

    @property
    def programs(self) -> tuple[ToolStep, ...]:
        """The steps that are a program rather than a rung.

        The complement of :attr:`climbable`, and named so that a caller refusing
        one can say which program it was holding rather than only that the plan
        was the wrong shape.
        """
        return tuple(step for step in self.steps if not isinstance(step, Step))

    @property
    def budget(self) -> int:
        """The most attempts these steps could spend between them."""
        return sum(step.attempts for step in self.steps)

    @property
    def climb_budget(self) -> int:
        """The most attempts :func:`climb` could spend on these steps.

        Distinct from :attr:`budget` because a program's single attempt is spent
        by :mod:`mcgyvr.deterministic` and never by the ladder. A caller
        budgeting a climb wants this one; a caller reporting what the family
        costs in total wants :attr:`budget`. Collapsing them would hand the
        climb an attempt of headroom the operator's ladder does not offer.
        """
        return sum(step.attempts for step in self.climbable)


@dataclass(frozen=True)
class Plan(Planned):
    """What one family would run for a contract, cheapest first.

    Empty is an ordinary answer rather than an error: a keyless install
    planning an ``api`` family has no rungs. ``reason`` says which, in words, so
    that a caller reporting "nothing ran" can say why without inspecting the
    config itself.

    A step is a :class:`Step` — a rung a runner dispatches against — or, on the
    deterministic floor, a :class:`~mcgyvr.deterministic.ToolStep`, which is a
    program and has no rung to name. The two are deliberately different types
    rather than one with an optional field: fitting a tool into ``Step`` would
    mean inventing a rung name :meth:`~mcgyvr.pool.SourceMap.bind` cannot
    honour, and every caller that reads ``rung`` would have to learn that it
    sometimes means nothing.
    """

    family: Family
    steps: tuple[Step | ToolStep, ...]
    reason: str = ""

    def __bool__(self) -> bool:
        return bool(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    @property
    def rungs(self) -> tuple[str, ...]:
        """The rung names in the order they would be tried.

        A deterministic step contributes nothing here rather than a placeholder:
        it has no rung, and a name invented for it would be a name no source map
        could bind and no ladder entry could configure.
        """
        return tuple(step.rung.name for step in self.steps if isinstance(step, Step))


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
class Result:
    """What an attempt function reports back.

    Built through :meth:`passed`, :meth:`failed` or :meth:`declined` rather than
    by hand, so that a verdict is always chosen deliberately — a positional
    boolean is exactly how "cannot approve" comes to mean approved.
    """

    verdict: Verdict
    detail: str = ""

    @classmethod
    def passed(cls, detail: str = "") -> Result:
        return cls(verdict=Verdict.PASSED, detail=detail)

    @classmethod
    def failed(cls, detail: str = "") -> Result:
        return cls(verdict=Verdict.FAILED, detail=detail)

    @classmethod
    def declined(cls, detail: str = "") -> Result:
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
class Accepted:
    """A climb that ended with a rung producing an acceptable result.

    Names which rung and what it took to get there, and carries nothing the
    attempt produced. It used to carry a ``value`` this module never inspected,
    which is what kept routing testable without a model — the testability came
    from not inspecting it, not from holding it, and the caller that needs the
    accepted bytes reads them off the :class:`~mcgyvr.escalate.Judgement` that
    bound them to a tree.
    """

    family: Family
    rung: str
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
) -> Plan:
    """The rungs of one family this contract may be tried on, in order.

    ``family`` defaults to the contract's type floor from the catalog — where
    work of this type may *begin*. It is deliberately not adjusted here when the
    floor's family has no rungs: satisfying a floor with a dearer family is an
    ascent, ascent is #43's, and doing it quietly here would put half of "each
    family is entered at most once" in a module that cannot see the other half.
    An install whose floor family is empty gets an empty plan that names the
    situation, which is the input #43 acts on.
    """
    chosen = family if family is not None else contract.type.starts_on
    rungs = by_family(config, pool).get(chosen)
    if rungs is None:  # a Family from another catalog than the one loaded here
        raise RouteError(f"{chosen.name!r} is not a family of the loaded catalog")

    if chosen.rank == 0:
        # The deterministic floor is planned from the task type, not from the
        # ladder: it binds no rung because its executor is a program, and until
        # this branch existed every `starts_on: deterministic` type planned
        # nothing at all — a model call for work a tool does for free. Imported
        # here rather than at module scope because `mcgyvr.deterministic` reads
        # `attempts_for` from this module; at module scope that is a cycle.
        from mcgyvr.deterministic import tool_steps

        tools = tool_steps(contract)
        if tools:
            return Plan(family=chosen, steps=tools)

    if not rungs:
        return Plan(family=chosen, steps=(), reason=_why_empty(config, chosen, pool))

    steps = tuple(
        Step(
            rung=rung,
            attempts=attempts_for(
                chosen, _configured_attempts(config, rung.name), contract
            ),
        )
        for rung in rungs
    )
    return Plan(family=chosen, steps=steps)


def _configured_attempts(config: Config, rung: str) -> int:
    tier = config.ladder.get(rung)
    if tier is None:  # unreachable: the rung came from the pool, which came from here
        raise RouteError(f"no rung named {rung!r} in the ladder")
    return tier.attempts


def _why_empty(config: Config, family: Family, pool: SourceMap) -> str:
    """Why a family offers nothing, in the terms that make it actionable.

    The deterministic family is empty for a reason no config edit will change,
    so saying "no rung is bound to it" would send an operator to the wrong file.
    It is also, since the floor was bound, a much narrower case than it was:
    :func:`plan` reaches this branch only when no program is bound for the
    contract's type on its target, not merely because the family holds no rung.
    Every other family is empty either because nothing was bound to it or
    because what was bound could not be offered, and the pool already holds the
    reason for the second case.

    Only *this family's* skipped rungs are quoted. A local rung that was skipped
    says nothing about why the api family is empty, and offering it as the
    explanation would send someone to fix a source that was never the problem.
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


# --- executing a plan ------------------------------------------------------


def climb(
    plan: Plan,
    attempt: Callable[[Try], Result],
    *,
    capacity: Capacity | None = None,
    permit: Callable[[Step, int], bool] | None = None,
) -> Accepted | Exhausted:
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
    """
    history: list[Attempted] = []
    if not plan.steps:
        return Exhausted(
            family=plan.family,
            reason=Exhaustion.NO_RUNG,
            history=(),
            detail=plan.reason,
        )

    # A tool is not climbed. Every shape this loop hands out — `Try`, `permit`'s
    # argument, an `Attempted` row — is named after a rung, and a deterministic
    # step has none: it is a program, executed by :mod:`mcgyvr.deterministic`.
    # Refusing here rather than skipping keeps that a visible routing error
    # instead of a plan that reports having run and spent nothing.
    #
    # The refusal is for a caller that reached for the wrong function, so it is
    # not something a walk of the ascent should ever meet: `Plan.climbable` is
    # what a caller asks before handing a plan over, and #43 asks it.
    steps = plan.climbable
    if plan.programs:
        named = ", ".join(sorted({step.tool.task_type for step in plan.programs}))
        raise RouteError(
            f"the {plan.family.name!r} plan is a program, not a rung, so it is "
            f"not climbed: run it through `mcgyvr.deterministic` instead "
            f"({named})."
        )

    for step in steps:
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
                    history=tuple(history),
                )
            if result.verdict is Verdict.DECLINED:
                # A decline is about the contract, not about this attempt, so
                # trying the same rung again would ask a question already
                # answered. It costs the rung's remaining budget nothing.
                break

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
