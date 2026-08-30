"""Escalation: which family a task climbs to next, what stops it, and what the
acceptance actually rests on (#43).

:mod:`mcgyvr.route` climbs the rungs of one family and names the moment that
family is spent. This module is what happens next. It owns four rules that
:mod:`~mcgyvr.route` deliberately refused, because each of them needs to see
more than one family at once:

**Ascent is a rule, not a model call.** The families a task may enter are the
catalog's own, from the contract's floor upward in declared rank order. They are
computed as a tuple of :class:`~mcgyvr.route.Plan` before anything is dispatched
— :func:`ascent` answers "which families, which rungs, how many attempts, and
what stops it" with no network and no model — so routing is reproducible and
diffable rather than merely deterministic. The same property #24 gave one
family, over the whole climb.

**Ascent is monotonic, and structurally so.** :attr:`Ascent.plans` is built by
filtering the catalog's rank-ordered families once, so each family appears
exactly once and ranks strictly increase. Ping-pong between a local rung and an
API rung is not prevented by a check that could be forgotten; there is nowhere
in the shape for it to happen. A floor is a floor in the same way: families
below it are absent from the ascent rather than skipped inside it.

**An idle ladder spills upward, and only when told to.** ``ladder.fanout``
is a knob and ``none`` is its default, which is this module as it was: every
contract of a batch takes the cheapest rung of its floor family and queues
there. Under ``idle`` :attr:`Ascent.next_free_rung` names the cheapest rung *at
or above the floor* with a free slot instead, which is a choice that can cross
families — when every local rung is full the cheapest free rung is a priced api
one, so a saturated local ladder buys capacity rather than waits. That is the
whole reason the mode is opt-in, and it is why the choice is here and not in
:mod:`mcgyvr.route`: #24's boundary is that nothing there looks past the family
it was asked about, and this is already the view "every family this contract
may climb, from its floor upward". ``full`` spreads *within* a family and stays
:func:`~mcgyvr.route.climb`'s; this module adds nothing to it.

**Busy is not a verdict, and the record is the difference.** A rung that
:attr:`~Ascent.next_free_rung` passed over was not tried: it produced no
verdict, spent no attempt and funded no escalation, because
:meth:`~mcgyvr.capacity.Capacity.hold` blocks rather than raising and a queue is
not a failure. So an api rung reached under ``idle`` and an api rung reached by
escalation are the same rung with two different histories — one was chosen
before anything ran, the other was climbed to after something failed — and only
the second says the local family could not do the work.

**Two ceilings bound the task, and they bound different things.**
``budgets.max_escalations`` bounds how far the work *climbs* — a cheap rung that
fails and then escalates costs more than starting higher, so the ceiling is on
moves, not on tries. ``budgets.max_attempts`` bounds what the task *spends* in
total. Neither charges a decline: a rung that steps aside (#81) consumed no
attempt, and charging the move to it would let a ladder of rungs that never ran
exhaust a budget. Unset, ``max_attempts`` is the ladder's own budget, which is a
real bound and is printed by ``mcgyvr pool`` — the field exists so that raising
a rung's ``attempts`` cannot multiply into a task nobody bounded, not to
introduce a number this project has no measurement for.

**A model's output is never accepted on a policy written for a tool.** A
contract's ``verification.policy`` of ``gate_only`` is the whole acceptance bar
in the deterministic family: a tool's output, checked by the gate, is what that
policy describes. The moment work leaves that family the policy is *upgraded* to
require a fresh-context verifier, whatever the contract declared. What the
install can then do about it is a capability question, not a policy one, and
:class:`Assurance` is where the difference is recorded: ``VERIFIED`` is only ever
reached by a verifier that ran and agreed, and an install with no verifier
reaches ``UNVERIFIED`` — accepted on the gate, labelled as exactly that. That is
E6's third first-class configuration and #44 is where it becomes a thing the
user is told; what closes the path here is that no acceptance can be *called*
verified without one, and that an available verifier is never skipped.

**Ordering is enforced rather than assumed.** :func:`judge` reads the gate
first and returns before the verifier is so much as named when the gate
rejected, so a deterministically-rejected change costs zero verifier spend. #32
stated that ordering; nothing held it. For the same reason a retry carries
:class:`RetryNotes` — the checks that *failed* and nothing else. Re-reading the
passing checks is spend that carries no information, and neither an observation
(a finding the gate deliberately did not reject on) nor an environment issue (a
tool that was not installed) is something the worker did or can fix.

**What is deliberately not here.** Parsing a model's reply into a
:class:`Review` is #41's; this module fixes only *when* one is asked for and
what follows from each answer. Reviewing the applied diff in fresh context is
#42's, and so is the rule that a reviewer-side failure is never charged to the
builder — :attr:`Judgement.reviewer_failed` keeps that case distinguishable, but
an unusable review still ends the attempt here, because not accepting is the
only answer this module is entitled to give. Telling the user what an
``UNVERIFIED`` acceptance means is #44's. Whether a ladder that declares its
families out of rank order should be diagnosed is #153's, and this module is
what makes that observable: the ascent's order is the catalog's, so an
interleaved ladder executes in an order the config file does not show.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from mcgyvr.catalog import Family, catalog
from mcgyvr.route import (
    Accepted,
    Attempted,
    Exhaustion,
    Fanout,
    Plan,
    Result,
    RouteError,
    Step,
    Try,
    Verdict,
    climb,
    fanout_of,
    plan,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.gate import GateResult
    from mcgyvr.pool import SourceMap

GATE_ONLY = "gate_only"
MODEL = "model"

# The verification policies, cheapest first. Ordering them is what makes an
# upgrade expressible as "never lower than", so that a contract already asking
# for a verifier keeps it in the deterministic family too.
_POLICY_RANK: dict[str, int] = {GATE_ONLY: 0, MODEL: 1}


class Outcome(StrEnum):
    """How a task ended, in one machine-readable word.

    #43 asks that every terminal outcome be machine-readable rather than prose,
    and these are the five. The distinctions are the ones a caller has to act
    on differently: work that was accepted, a ladder that was genuinely tried
    and could not, two different ceilings that stopped it early, and an install
    that had nothing to run in the first place. Prose is carried alongside in
    ``detail`` for a human; nothing branches on it.
    """

    ACCEPTED = "accepted"
    LADDER_SPENT = "ladder_spent"
    ESCALATION_CEILING = "escalation_ceiling"
    ATTEMPT_CEILING = "attempt_ceiling"
    NOTHING_TO_RUN = "nothing_to_run"
    DECLINED_THROUGHOUT = "declined_throughout"


class Assurance(StrEnum):
    """What an acceptance actually rests on.

    Not a quality score — a statement of which bar was cleared, so that a
    result is never reported as more assured than it is. ``DETERMINISTIC`` is a
    tool's output through the gate, which is what a ``gate_only`` contract
    describes. ``VERIFIED`` is reachable only by a verifier that ran and
    agreed. ``UNVERIFIED`` is a model's output that passed the gate in an
    install with no verifier to satisfy the upgrade — accepted, and labelled.
    """

    DETERMINISTIC = "deterministic"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class Opinion(StrEnum):
    """What a verifier came to.

    Three members, and the third is why it is an enum: a reply that could not
    be read is not a refusal and is certainly not an approval. #41 owns turning
    a model's text into one of these — anchored parsing, no substring search,
    failing closed — and this module owns only what each one means for the
    attempt.
    """

    AGREED = "agreed"
    REFUSED = "refused"
    UNUSABLE = "unusable"


@dataclass(frozen=True)
class Review:
    """One verifier's answer, built through a named constructor.

    Never assembled from a positional boolean, for the reason #41 exists: a
    reply beginning "Cannot approve" read as an approval is the failure this
    whole path is shaped around, and a bare ``True`` is the same mistake one
    layer down.
    """

    opinion: Opinion
    detail: str = ""

    @classmethod
    def agreed(cls, detail: str = "") -> Review:
        return cls(opinion=Opinion.AGREED, detail=detail)

    @classmethod
    def refused(cls, detail: str = "") -> Review:
        return cls(opinion=Opinion.REFUSED, detail=detail)

    @classmethod
    def unusable(cls, detail: str = "") -> Review:
        return cls(opinion=Opinion.UNUSABLE, detail=detail)


@dataclass(frozen=True)
class RetryNotes:
    """The failing checks from one attempt, and nothing else.

    A retry prompt that repeated the gate's full output would spend tokens
    telling a worker what it already got right. Three things are excluded on
    purpose and each for its own reason: checks that produced no finding did
    not fail; observations are findings the gate deliberately did not reject on
    (:attr:`~mcgyvr.gate.GateResult.observations`), so quoting them would ask
    for changes that were never required; and an environment issue is a tool
    that was not installed, which is not something the worker did or can fix.
    """

    checks: tuple[str, ...]
    lines: tuple[str, ...]

    @classmethod
    def of(cls, gate: GateResult) -> RetryNotes | None:
        """The notes for a rejected gate run, or ``None`` if nothing failed."""
        if not gate.findings:
            return None
        return cls(
            checks=tuple(gate.by_check()),
            lines=tuple(str(f) for f in gate.findings),
        )

    @property
    def text(self) -> str:
        return "\n".join(f"- {line}" for line in self.lines)


@dataclass(frozen=True)
class Judgement[T]:
    """What one attempt came to, and what its acceptance would rest on.

    This is what an attempt function hands the driver, rather than a bare
    :class:`~mcgyvr.route.Result`, because a task-level answer has to say which
    bar was cleared and a routing verdict cannot carry that without
    :mod:`mcgyvr.route` learning what verification is.
    """

    verdict: Verdict
    value: T | None = None
    assurance: Assurance | None = None
    policy: str = GATE_ONLY
    upgraded: bool = False
    reviewer_failed: bool = False
    retry: RetryNotes | None = None
    detail: str = ""

    def as_result(self) -> Result[T]:
        """The routing verdict alone, for :func:`~mcgyvr.route.climb`."""
        return Result(verdict=self.verdict, value=self.value, detail=self.detail)


# --- policy ----------------------------------------------------------------


def required_policy(contract: Contract, family: Family) -> str:
    """The verification policy that actually applies in ``family``.

    Never lower than the contract declared, and never ``gate_only`` outside the
    deterministic family. The upgrade is unconditional because the contract's
    declaration was written about a tool: leaving it in force once a model is
    doing the work would accept a model's output on a warrant that was never
    about a model.
    """
    declared = contract.verification.policy
    floor = GATE_ONLY if family.rank == 0 else MODEL
    return declared if _rank(declared) >= _rank(floor) else floor


def _rank(policy: str) -> int:
    return _POLICY_RANK.get(policy, _POLICY_RANK[MODEL])


def judge[T](
    contract: Contract,
    family: Family,
    gate: GateResult,
    value: T | None = None,
    *,
    verifier: Callable[[], Review] | None = None,
) -> Judgement[T]:
    """Turn a gate run — and, only if it passed, a verifier — into a judgement.

    The ordering is the point and it is structural: ``verifier`` is not
    referenced at all on the rejected path, so a gate failure cannot cost
    verifier spend however the caller supplied one. #32 stated that the gate
    runs "before any model is asked for an opinion"; this is where it is held.
    """
    policy = required_policy(contract, family)
    upgraded = policy != contract.verification.policy

    if not gate.accepted:
        return Judgement(
            verdict=Verdict.FAILED,
            policy=policy,
            upgraded=upgraded,
            retry=RetryNotes.of(gate),
            detail=(
                f"the gate rejected the change on "
                f"{', '.join(gate.by_check()) or 'no named check'}; "
                f"no verifier was asked."
            ),
        )

    if policy == GATE_ONLY:
        return Judgement(
            verdict=Verdict.PASSED,
            value=value,
            assurance=Assurance.DETERMINISTIC,
            policy=policy,
            upgraded=upgraded,
            detail=(
                "accepted on the deterministic gate, which is the whole bar a "
                "`gate_only` contract describes for a tool's output."
            ),
        )

    if verifier is None:
        return Judgement(
            verdict=Verdict.PASSED,
            value=value,
            assurance=Assurance.UNVERIFIED,
            policy=policy,
            upgraded=upgraded,
            detail=(
                f"accepted on the deterministic gate alone: work in the "
                f"{family.name!r} family requires a fresh-context verifier and "
                f"this install has none, so the acceptance is labelled "
                f"unverified rather than verified (#44)."
            ),
        )

    review = verifier()
    if review.opinion is Opinion.AGREED:
        return Judgement(
            verdict=Verdict.PASSED,
            value=value,
            assurance=Assurance.VERIFIED,
            policy=policy,
            upgraded=upgraded,
            detail=review.detail or "the verifier agreed with the applied change.",
        )
    if review.opinion is Opinion.REFUSED:
        return Judgement(
            verdict=Verdict.FAILED,
            policy=policy,
            upgraded=upgraded,
            # The gate passed, so there is nothing of its to repeat: the
            # refusal is the whole of what failed, and it is what a retry has
            # to act on.
            retry=RetryNotes(
                checks=("verifier",), lines=(f"verifier: {review.detail}",)
            ),
            detail=f"the verifier refused the change: {review.detail}",
        )
    return Judgement(
        verdict=Verdict.FAILED,
        policy=policy,
        upgraded=upgraded,
        reviewer_failed=True,
        detail=(
            f"the verifier produced no usable verdict ({review.detail}), so the "
            f"change is not accepted. Charging this to the builder rather than "
            f"to the reviewer is #42's to settle."
        ),
    )


# --- the ceilings ----------------------------------------------------------


@dataclass(frozen=True)
class Ceiling:
    """What bounds one task, read off the config once.

    ``attempts`` of ``None`` is not "unbounded": it means the bound is the
    ladder's own budget, which :attr:`Ascent.budget` computes and
    ``mcgyvr pool`` prints. Making the unset case mean "no independent ceiling"
    rather than a number keeps this project from shipping a default it has no
    measurement behind, and keeps two knobs from silently overriding each
    other — an operator who raises ``max_escalations`` does not want a ceiling
    they never set cutting the climb back.
    """

    escalations: int
    attempts: int | None = None

    @classmethod
    def of(cls, config: Config) -> Ceiling:
        raw = config.get("budgets.max_attempts")
        return cls(
            escalations=int(config.get("budgets.max_escalations", 1)),
            attempts=None if raw is None else int(raw),
        )


@dataclass(frozen=True)
class Ascent:
    """Every family a task may enter, in order, with what bounds the climb.

    Inspectable before anything is spent, which is the property #24 gave one
    family and this extends to the whole climb: the families, their rungs, the
    attempts each is allowed and the two ceilings are all decided from the
    config, the pool and the contract alone.

    ``fanout`` is the configured mode, carried the way
    :attr:`~mcgyvr.route.Plan.fanout` carries it, so that an ascent can answer
    where an idle ladder would send work without being handed a
    :class:`~mcgyvr.config.Config` again.

    ``capacity`` and ``widths`` are the two halves of "has a free slot", and
    they are split because they change at different rates. A width is a
    property of how a backend was started and :class:`~mcgyvr.capacity.Capacity`
    settles it once, so it is read when the ascent is built; load is only true
    at the moment it is asked for, so it is read then. Neither is part of the
    decision this record holds — two ascents that differ only in which capacity
    they were handed are the same ascent — so both stay out of ``repr`` and out
    of comparison, and the families, rungs, attempts and ceilings that *are* the
    decision print exactly as they did before.
    """

    floor: Family
    plans: tuple[Plan, ...]
    ceiling: Ceiling
    fanout: Fanout = Fanout.NONE
    capacity: Capacity | None = field(default=None, repr=False, compare=False)
    widths: Mapping[str, int] = field(default_factory=dict, repr=False, compare=False)

    def __bool__(self) -> bool:
        return any(self.plans)

    def __len__(self) -> int:
        return len(self.runnable)

    @property
    def families(self) -> tuple[Family, ...]:
        """Every family in the ascent, floor first — including the empty ones."""
        return tuple(p.family for p in self.plans)

    @property
    def runnable(self) -> tuple[Plan, ...]:
        """The families that actually offer a rung."""
        return tuple(p for p in self.plans if p)

    @property
    def rungs(self) -> tuple[str, ...]:
        return tuple(name for p in self.plans for name in p.rungs)

    @property
    def ladder_budget(self) -> int:
        """The most attempts the configured rungs could spend between them."""
        return sum(p.budget for p in self.plans)

    @property
    def budget(self) -> int:
        """The most attempts this task may spend, ceilings included."""
        if self.ceiling.attempts is None:
            return self.ladder_budget
        return min(self.ladder_budget, self.ceiling.attempts)

    @property
    def most_rungs(self) -> int:
        """The most rungs this task may spend on, the escalation ceiling included."""
        return min(len(self.rungs), self.ceiling.escalations + 1)

    @property
    def next_free_rung(self) -> str | None:
        """The cheapest rung at or above the floor with a free slot, under ``idle``.

        This is the whole of what ``ladder.fanout: idle`` decides. The floor
        bounds it and nothing else does: when every cheaper rung is full this
        names a priced api rung rather than wait, which is a spend decision the
        knob makes deliberately and the reason it is opt-in.

        **Never below the floor, structurally.** :attr:`plans` holds only
        families at or above it, so a cheaper rung is not skipped here — there
        is nowhere in the shape for it to be considered, however idle it is.
        Risk raises a floor (#16) and load may not lower it.

        **Nothing is spent naming a rung.** A rung passed over here was not
        tried, so it reached no verdict, consumed no attempt and funded no
        escalation; a rung named here was chosen before anything ran, which is
        what makes it different from the same rung climbed to after a failure.

        ``None`` means "no answer, keep price order", which is ``none``'s
        behaviour and never an error. It is the answer in four cases: the mode
        is not ``idle`` — the question belongs to the operator who asked for it,
        and answering it under a mode that declined it would offer a decision
        nobody wanted; no capacity was handed in, so there is no load to read;
        every rung at or above the floor is full, and waiting is then the only
        honest answer; or a rung's load could not be read at all.

        That last case stops the walk rather than stepping over the rung.
        "Cheapest free" is only knowable if every cheaper rung could be priced,
        so answering past an unreadable one would spend money to route around
        ignorance — and an unknown belongs on the cheap side. A load is
        unreadable when a step is bound to no machine, or when the capacity in
        hand does not bound that machine, which is a capacity and a plan built
        from different configs.

        The load is read here rather than stored when the ascent was built,
        because a reading taken before the batch started is only true until the
        batch starts; this is the closest a caller can get to the moment it acts.
        """
        if self.fanout is not Fanout.IDLE or self.capacity is None:
            return None
        for each in self.plans:
            for step in each.steps:
                width = self.widths.get(step.rung.name)
                load = (
                    None if step.machine is None else step.machine.load(self.capacity)
                )
                if width is None or load is None:
                    return None
                if load < width:
                    return step.rung.name
        return None

    @property
    def reason(self) -> str:
        """Why nothing can run, in the words each family gave for being empty."""
        return " ".join(f"{p.family.name}: {p.reason}" for p in self.plans if p.reason)


def ascent(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    floor: Family | None = None,
    capacity: Capacity | None = None,
) -> Ascent:
    """The families this contract may climb, from its floor upward.

    ``floor`` defaults to the contract's type floor. Families cheaper than it
    are absent rather than skipped, and each family appears once in strictly
    increasing rank — which is what makes "entered at most once" a fact about
    the shape rather than a rule something has to remember to apply.

    ``capacity`` changes none of that: the families, their rungs and both
    ceilings are what they were without one, and every mode's ladder is the same
    ladder. What it adds is a question the ascent can then answer —
    :attr:`Ascent.next_free_rung`, which is ``idle``'s choice and which crosses
    families, so it belongs to the view that spans them rather than to
    :func:`~mcgyvr.route.plan`. It is passed down to each plan as well, at the
    seam that documents accepting one and doing nothing with it.
    """
    known = catalog()
    start = floor if floor is not None else contract.type.starts_on
    if start not in known.families:
        raise RouteError(f"{start.name!r} is not a family of the loaded catalog")
    return Ascent(
        floor=start,
        plans=tuple(
            plan(config, pool, contract, family=family, capacity=capacity)
            for family in known.families
            if family.rank >= start.rank
        ),
        ceiling=Ceiling.of(config),
        fanout=fanout_of(config),
        capacity=capacity,
        widths=_widths(config, capacity),
    )


def _widths(config: Config, capacity: Capacity | None) -> Mapping[str, int]:
    """How wide each rung's machine is, keyed by the rung rather than the machine.

    The static half of "has a free slot". A width is a property of how a backend
    was started, so :class:`~mcgyvr.capacity.Capacity` settles it once and this
    reads it once; only the load has to be read at the moment the question is
    asked.

    The source name is read inside this function and does not leave it: #20's
    rule is that nothing above the execution seam learns where work runs, and a
    width keyed by a rung is a fact about the ladder rather than about a host.
    Asking :class:`~mcgyvr.route.Machine` how busy it is stays the one way load
    is read, for the same reason.

    A rung whose source this capacity does not bound is absent rather than given
    a guessed width, because an unknown width is not a free slot and
    :attr:`Ascent.next_free_rung` must be able to tell the two apart.
    """
    if capacity is None:
        return {}
    limits = capacity.limits
    return {
        tier.name: limits[tier.source]
        for tier in config.ladder.tiers
        if tier.source in limits
    }


# --- terminal outcomes -----------------------------------------------------


@dataclass(frozen=True)
class Delivered[T]:
    """A task that ended with a change accepted, and what that rests on."""

    family: Family
    rung: str
    value: T | None
    assurance: Assurance
    judgement: Judgement[T]
    entered: tuple[Family, ...]
    history: tuple[Attempted, ...]
    attempts_spent: int
    escalations: int

    @property
    def ok(self) -> bool:
        return True

    @property
    def outcome(self) -> Outcome:
        return Outcome.ACCEPTED

    @property
    def verified(self) -> bool:
        """Whether a verifier ran and agreed — never inferred from acceptance."""
        return self.assurance is Assurance.VERIFIED


@dataclass(frozen=True)
class Halted:
    """A task that ended without an accepted change, and which rule ended it.

    A distinct type from :class:`Delivered` for the reason #24 split its two:
    a caller cannot reach for a result that was never produced, and the
    difference reads as a match on the answer rather than as a boolean whose
    polarity has to be remembered.
    """

    outcome: Outcome
    entered: tuple[Family, ...]
    history: tuple[Attempted, ...]
    attempts_spent: int
    escalations: int
    detail: str = ""

    @property
    def ok(self) -> bool:
        return False


def escalate[T](
    config: Config,
    pool: SourceMap,
    contract: Contract,
    attempt: Callable[[Try], Judgement[T]],
    *,
    capacity: Capacity | None = None,
    floor: Family | None = None,
) -> Delivered[T] | Halted:
    """Climb the ascent until something is accepted or a rule ends the task.

    ``attempt`` is the caller's, as it is one level down: it assembles a
    prompt, dispatches, applies, gates and calls :func:`judge`. Keeping it a
    parameter is what lets every rule here be asserted without a model, a
    backend or a sandbox.

    Both ceilings are enforced through :func:`~mcgyvr.route.climb`'s ``permit``
    rather than by trimming the plan, because a decline costs nothing and a
    trimmed plan would have charged for it in advance. What is spent is counted
    as it happens: an attempt that was declined adds nothing to either count,
    so a ladder of rungs that all step aside is walked in full at no cost.
    """
    route = ascent(config, pool, contract, floor=floor, capacity=capacity)
    ceiling = route.ceiling
    budget = route.budget

    spent_rungs: list[str] = []
    attempts_spent = 0
    stopped_by: Outcome | None = None
    accepted_judgement: Judgement[T] | None = None
    history: list[Attempted] = []
    entered: list[Family] = []

    def permit(step: Step, number: int) -> bool:
        nonlocal stopped_by
        if attempts_spent >= budget:
            stopped_by = Outcome.ATTEMPT_CEILING
            return False
        # Entering a rung nothing has been spent on yet is the escalation, and
        # it is charged here rather than on arrival at a family: a move inside
        # a family costs what a move across one costs — the attempts already
        # spent below it. A rung that declined is not in ``spent_rungs``, so
        # moving past it is free.
        moving = step.rung.name not in spent_rungs and bool(spent_rungs)
        if moving and len(spent_rungs) > ceiling.escalations:
            stopped_by = Outcome.ESCALATION_CEILING
            return False
        return True

    def observed(this: Try) -> Result[T]:
        nonlocal attempts_spent, accepted_judgement
        judgement = attempt(this)
        if judgement.verdict is not Verdict.DECLINED:
            attempts_spent += 1
            if this.rung.name not in spent_rungs:
                spent_rungs.append(this.rung.name)
        if judgement.verdict is Verdict.PASSED:
            accepted_judgement = judgement
        return judgement.as_result()

    for each in route.plans:
        if not each:
            continue  # an empty family is not entered; its reason is kept
        result = climb(each, observed, capacity=capacity, permit=permit)
        history.extend(result.history)
        if result.history:
            entered.append(each.family)
        if isinstance(result, Accepted):
            assert accepted_judgement is not None  # set by `observed` on PASSED
            return Delivered(
                family=result.family,
                rung=result.rung,
                value=result.value,
                # An attempt that passed without saying what its acceptance
                # rests on is read as unverified. Defaulting the other way is
                # how a result comes to be reported as more assured than it is.
                assurance=accepted_judgement.assurance or Assurance.UNVERIFIED,
                judgement=accepted_judgement,
                entered=tuple(entered),
                history=tuple(history),
                attempts_spent=attempts_spent,
                escalations=max(0, len(spent_rungs) - 1),
            )
        if result.reason is Exhaustion.WITHHELD:
            break

    escalations = max(0, len(spent_rungs) - 1)
    outcome = stopped_by or _spent_outcome(history, attempts_spent)
    return Halted(
        outcome=outcome,
        entered=tuple(entered),
        history=tuple(history),
        attempts_spent=attempts_spent,
        escalations=escalations,
        detail=_halt_detail(outcome, route, attempts_spent, escalations),
    )


def _spent_outcome(history: list[Attempted], attempts_spent: int) -> Outcome:
    if not history:
        return Outcome.NOTHING_TO_RUN
    if attempts_spent == 0:
        return Outcome.DECLINED_THROUGHOUT
    return Outcome.LADDER_SPENT


def _halt_detail(
    outcome: Outcome, route: Ascent, attempts_spent: int, escalations: int
) -> str:
    """One sentence naming the rule that ended the task, in its own terms."""
    climbed = ", ".join(f.name for f in route.families)
    if outcome is Outcome.NOTHING_TO_RUN:
        return (
            f"no family from {route.floor.name!r} upward offers a rung. {route.reason}"
        )
    if outcome is Outcome.ATTEMPT_CEILING:
        source = (
            "budgets.max_attempts"
            if route.ceiling.attempts is not None
            else "the ladder's own budget"
        )
        return (
            f"the task stopped at its attempt ceiling of {route.budget} "
            f"({source}); {escalations} escalation(s) across {climbed}."
        )
    if outcome is Outcome.ESCALATION_CEILING:
        return (
            f"the task stopped at budgets.max_escalations "
            f"({route.ceiling.escalations}), having spent {attempts_spent} "
            f"attempt(s) on {route.most_rungs} rung(s) of {climbed}."
        )
    if outcome is Outcome.DECLINED_THROUGHOUT:
        return (
            f"every rung of {climbed} declined this contract; no attempt was "
            f"spent, so this says nothing about what the ladder can do."
        )
    return (
        f"the ladder is spent: {attempts_spent} attempt(s) and {escalations} "
        f"escalation(s) across {climbed}, and none produced an acceptable change."
    )
