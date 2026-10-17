""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, assert_never

from mcgyvr.catalog import Family, TaskType, catalog
from mcgyvr.route import (
    Accepted,
    Attempted,
    Exhaustion,
    Fanout,
    Machine,
    Plan,
    Result,
    RouteError,
    Step,
    Try,
    Verdict,
    attempted,
    climb,
    family_of,
    fanout_of,
    plan,
)

if TYPE_CHECKING:  #
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract

    #
    #he
    #
    #
    #
    from mcgyvr.deliver import Accepted as BoundContent
    from mcgyvr.gate import GateResult
    from mcgyvr.local_pool import SourceMap

GATE_ONLY = "gate_only"
MODEL = "model"

#
#
#
_POLICY_RANK: dict[str, int] = {GATE_ONLY: 0, MODEL: 1}


class Outcome(StrEnum):
    ""

    ACCEPTED = "accepted"
    LADDER_SPENT = "ladder_spent"
    ESCALATION_CEILING = "escalation_ceiling"
    ATTEMPT_CEILING = "attempt_ceiling"
    NOTHING_TO_RUN = "nothing_to_run"
    DECLINED_THROUGHOUT = "declined_throughout"
    ERROR = "error"


class Assurance(StrEnum):
    ""

    DETERMINISTIC = "deterministic"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CHECKED = "checked"
    UNCHECKED = "unchecked"


#
#
NO_REVIEWER = "no reviewer is configured — set `verifier.unit`"


def reply_judged(name: str, checks: Sequence[str]) -> str:
    ""
    if not checks:
        return f"served unchecked: {name} replies are not checked or reviewed."
    return (
        f"accepted on its output checks ({', '.join(checks)}); "
        f"{name} replies are never reviewed."
    )


def how_judged(kind: TaskType) -> str:
    ""
    if kind.deterministic:
        return (
            "a tool's output, accepted on the deterministic gate; assurance "
            f"`{Assurance.DETERMINISTIC}`."
        )
    if kind.judges_a_change:
        return (
            "the deterministic gate, then a fresh-context reviewer: assurance "
            f"`{Assurance.VERIFIED}` when one agrees, `{Assurance.UNVERIFIED}` "
            "when none is configured (set `verifier.unit`) or it cannot be used."
        )
    label = Assurance.CHECKED if kind.evidence_names else Assurance.UNCHECKED
    return f"{reply_judged(kind.name, kind.evidence_names)} (assurance `{label}`)"


class Opinion(StrEnum):
    ""

    AGREED = "agreed"
    REFUSED = "refused"
    UNUSABLE = "unusable"


@dataclass(frozen=True)
class Review:
    ""

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
    ""

    checks: tuple[str, ...]
    lines: tuple[str, ...]

    @classmethod
    def of(cls, gate: GateResult) -> RetryNotes | None:
        ""
        if not gate.findings:
            return None
        return cls(
            checks=tuple(gate.by_check()),
            lines=tuple(f.for_model() for f in gate.findings),
        )

    @property
    def text(self) -> str:
        return "\n".join(f"- {line}" for line in self.lines)


@dataclass(frozen=True)
class Judgement:
    ""

    verdict: Verdict
    accepted: BoundContent | None = None
    assurance: Assurance | None = None
    policy: str = GATE_ONLY
    upgraded: bool = False
    reviewer_failed: bool = False
    retry: RetryNotes | None = None
    detail: str = ""
    #
    #
    draw: int = 0
    draws: int = 1
    rows: int = 1

    def as_result(self) -> Result:
        ""
        findings = self.retry.lines if self.retry is not None else ()
        return Result(
            verdict=self.verdict,
            detail=self.detail,
            findings=findings,
            draw=self.draw,
            draws=self.draws,
            rows=self.rows,
        )


#


def required_policy(contract: Contract, family: Family) -> str:
    ""
    declared = contract.verification.policy
    floor = GATE_ONLY if family.rank == 0 else MODEL
    return declared if _rank(declared) >= _rank(floor) else floor


def _rank(policy: str) -> int:
    return _POLICY_RANK.get(policy, _POLICY_RANK[MODEL])


def judge(
    contract: Contract,
    family: Family,
    gate: GateResult,
    *,
    verifier: Callable[[], Review] | None = None,
    absent: str = "",
    reviewer: str = "",
) -> Judgement:
    ""
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

    if not contract.kind.judges_a_change:
        checks = contract.evidence_names
        return Judgement(
            verdict=Verdict.PASSED,
            assurance=Assurance.CHECKED if checks else Assurance.UNCHECKED,
            #
            #
            policy=contract.verification.policy,
            upgraded=False,
            detail=reply_judged(contract.task_type, checks),
        )

    if policy == GATE_ONLY:
        return Judgement(
            verdict=Verdict.PASSED,
            assurance=Assurance.DETERMINISTIC,
            policy=policy,
            upgraded=upgraded,
            detail=(
                "accepted on the deterministic gate, which is the whole bar a "
                "`gate_only` contract describes for a tool's output."
            ),
        )

    if verifier is None:
        why = absent or NO_REVIEWER
        return Judgement(
            verdict=Verdict.PASSED,
            assurance=Assurance.UNVERIFIED,
            policy=policy,
            upgraded=upgraded,
            detail=(
                f"unverified: {why}; accepted on the deterministic gate alone, "
                f"where work in the {family.name!r} family is reviewed when a "
                f"reviewer is available."
            ),
        )

    review = verifier()
    if review.opinion is Opinion.AGREED:
        return Judgement(
            verdict=Verdict.PASSED,
            assurance=Assurance.VERIFIED,
            policy=policy,
            upgraded=upgraded,
            detail=(
                f"verified by {reviewer or 'the reviewer'}: "
                f"{review.detail or 'it agreed with the applied change.'}"
            ),
        )
    if review.opinion is Opinion.REFUSED:
        return Judgement(
            verdict=Verdict.FAILED,
            policy=policy,
            upgraded=upgraded,
            #
            #
            #
            #he
            #
            retry=_refusal_notes(review, gate),
            #
            #
            detail=f"refused by {reviewer or 'the verifier'}: {review.detail}",
        )
    #
    #
    #ever
    #
    return Judgement(
        verdict=Verdict.PASSED,
        assurance=Assurance.UNVERIFIED,
        policy=policy,
        upgraded=upgraded,
        reviewer_failed=True,
        detail=(
            f"unverified: the verifier produced no usable verdict "
            f"({review.detail}); accepted on the deterministic gate alone."
        ),
    )


def _refusal_notes(review: Review, gate: GateResult) -> RetryNotes:
    ""
    reasons = () if gate.jev is None else (*gate.jev.findings, *gate.jev.observations)
    return RetryNotes(
        checks=("verifier", *(("jev",) if reasons else ())),
        lines=(
            f"verifier: {review.detail}",
            *(finding.for_model() for finding in reasons),
        ),
    )


#


@dataclass(frozen=True)
class Ceiling:
    ""

    escalations: int
    attempts: int | None = None

    @classmethod
    def of(cls, config: Config) -> Ceiling:
        raw = config.get("max_attempts")
        return cls(
            escalations=int(config.get("max_escalations", 1)),
            attempts=None if raw is None else int(raw),
        )


@dataclass(frozen=True)
class Entry:
    ""

    family: Family
    rung: str
    machine: Machine = field(repr=False, compare=False)
    capacity: Capacity = field(repr=False, compare=False)
    #
    #
    #
    relief: bool = False

    def release(self) -> None:
        ""
        self.machine.release(self.capacity, self.rung)


@dataclass(frozen=True)
class _Found:
    ""

    family: Family
    rung: str
    machine: Machine
    relief: bool = False


@dataclass(frozen=True)
class Ascent:
    ""

    floor: Family
    plans: tuple[Plan, ...]
    ceiling: Ceiling
    fanout: Fanout = Fanout.NONE
    capacity: Capacity | None = field(default=None, repr=False, compare=False)
    widths: Mapping[str, int] = field(default_factory=dict, repr=False, compare=False)
    relief: tuple[Step, ...] = ()

    def __bool__(self) -> bool:
        ""
        return bool(self.runnable)

    def __len__(self) -> int:
        return len(self.runnable)

    @property
    def families(self) -> tuple[Family, ...]:
        ""
        return tuple(p.family for p in self.plans)

    @property
    def runnable(self) -> tuple[Plan, ...]:
        ""
        return tuple(p for p in self.plans if p.climbable)

    @property
    def rungs(self) -> tuple[str, ...]:
        return tuple(name for p in self.plans for name in p.rungs)

    @property
    def ladder_budget(self) -> int:
        ""
        return sum(p.climb_budget for p in self.plans)

    @property
    def budget(self) -> int:
        ""
        if self.ceiling.attempts is None:
            return self.ladder_budget
        return min(self.ladder_budget, self.ceiling.attempts)

    @property
    def most_rungs(self) -> int:
        ""
        return min(len(self.rungs), self.ceiling.escalations + 1)

    @property
    def next_free_rung(self) -> str | None:
        ""
        found = self._entry_rung(reserve=False)
        return None if found is None else found.rung

    def reserve_entry(self, *, relief: bool = True) -> Entry | None:
        ""
        found = self._entry_rung(reserve=True, relief=relief)
        if found is None:
            return None
        if not found.relief and not self._raises(found.family):
            return None
        #
        #
        assert self.capacity is not None
        return Entry(
            family=found.family,
            rung=found.rung,
            machine=found.machine,
            capacity=self.capacity,
            relief=found.relief,
        )

    def _raises(self, family: Family) -> bool:
        ""
        return family.rank > self.floor.rank

    def _entry_rung(self, *, reserve: bool, relief: bool = True) -> _Found | None:
        ""
        capacity = self.capacity
        if self.fanout is not Fanout.IDLE or capacity is None:
            return None
        riding = self.relief if relief else ()
        #
        #
        servers = {
            step.rung.name: step.machine.server(capacity)
            for step in (*(s for p in self.plans for s in p.climbable), *riding)
            if step.machine is not None
        }

        def full(step: Step) -> bool | None:
            #
            #
            #
            if step.machine is None or self.widths.get(step.rung.name) is None:
                return None
            return step.machine.full(
                capacity, step.rung.name, servers.get(step.rung.name)
            )

        offered = not riding
        with capacity.deciding():
            for each in self.plans:
                for step in each.climbable:
                    said = full(step)
                    if said is None or step.machine is None:
                        return None
                    if not said:
                        if reserve and self._raises(each.family):
                            step.machine.claim(capacity, step.rung.name)
                        return _Found(each.family, step.rung.name, step.machine)
                if offered or not each.climbable:
                    continue
                #
                offered = True
                for step in riding:
                    said = full(step)
                    if said is None or step.machine is None:
                        return None
                    if not said:
                        if reserve:
                            step.machine.claim(capacity, step.rung.name)
                        return _Found(
                            each.family, step.rung.name, step.machine, relief=True
                        )
        return None

    @property
    def reason(self) -> str:
        ""
        return " ".join(f"{p.family.name}: {p.reason}" for p in self.plans if p.reason)


def ascent(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    floor: Family | None = None,
    capacity: Capacity | None = None,
) -> Ascent:
    ""
    known = catalog()
    start = floor if floor is not None else contract.kind.starts_on
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
        relief=tuple(
            Step(rung=rung, attempts=1, machine=Machine(rung.name))
            for rung in pool.relief
        ),
    )


def _widths(config: Config, capacity: Capacity | None) -> Mapping[str, int]:
    ""
    if capacity is None:
        return {}
    limits = capacity.limits
    return {
        name: capacity.limit(name)
        for name in (*config.ladder.names, *config.relief)
        if name in limits
    }


#


@dataclass(frozen=True)
class Delivered:
    ""

    family: Family
    rung: str
    assurance: Assurance
    judgement: Judgement
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
        ""
        return self.assurance is Assurance.VERIFIED


@dataclass(frozen=True)
class Halted:
    ""

    outcome: Outcome
    entered: tuple[Family, ...]
    history: tuple[Attempted, ...]
    attempts_spent: int
    escalations: int
    detail: str = ""

    @property
    def ok(self) -> bool:
        return False


class DispatchRaisedError(Exception):
    ""

    def __init__(
        self,
        cause: BaseException,
        *,
        draws: int,
        rows: int,
        draw: int | None = None,
    ) -> None:
        super().__init__(str(cause))
        #
        #
        self.cause = cause
        #
        self.draws = draws
        #
        self.rows = rows
        #
        self.draw = draw


class _AttemptError(Exception):
    ""

    def __init__(self, rung: str, attempt: int, cause: BaseException) -> None:
        stated = cause if isinstance(cause, DispatchRaisedError) else None
        super().__init__(rung)
        self.rung = rung
        self.attempt = attempt
        self.cause = stated.cause if stated is not None else cause
        self.draws = stated.draws if stated is not None else 0
        self.rows = stated.rows if stated is not None else 0
        self.draw = stated.draw if stated is not None else None


def escalate(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    attempt: Callable[[Try], Judgement],
    *,
    capacity: Capacity | None = None,
    floor: Family | None = None,
    wake_hook: Callable[[Contract], str | None] | None = None,
    presence: Callable[[str], AbstractContextManager[object]] | None = None,
) -> Delivered | Halted:
    ""
    route = ascent(config, pool, contract, floor=floor, capacity=capacity)
    entry = _idle_entry(route)
    #
    #
    riding: Entry | None = None
    if entry is not None and entry.relief:
        riding, entry = entry, None
    claimed: str | None = None
    if entry is not None:
        route, claimed = _entered(config, pool, contract, capacity, entry)
    ceiling = route.ceiling
    budget = route.budget

    spent_rungs: list[str] = []
    attempts_spent = 0
    stopped_by: Outcome | None = None
    accepted_judgement: Judgement | None = None
    history: list[Attempted] = []
    entered: list[Family] = []
    #
    #pt
    #
    #
    #
    #
    judged: list[Attempted] = []

    def permit(step: Step, number: int) -> bool:
        nonlocal stopped_by
        if attempts_spent >= budget:
            stopped_by = Outcome.ATTEMPT_CEILING
            return False
        #
        #
        #dy
        #
        #
        moving = step.rung.name not in spent_rungs and bool(spent_rungs)
        if moving and len(spent_rungs) > ceiling.escalations:
            stopped_by = Outcome.ESCALATION_CEILING
            return False
        return True

    def observed(this: Try) -> Result:
        nonlocal attempts_spent, accepted_judgement
        #
        #
        climbed = (
            presence is not None
            and bool(spent_rungs)
            and this.rung.name != spent_rungs[0]
        )
        try:
            with (
                presence(this.rung.name)
                if presence is not None and climbed
                else nullcontext()
            ):
                judgement = attempt(this)
        except Exception as exc:
            #
            #
            #
            #
            #
            raise _AttemptError(this.rung.name, this.attempt, exc) from exc
        if judgement.verdict is not Verdict.DECLINED:
            attempts_spent += 1
            if this.rung.name not in spent_rungs:
                spent_rungs.append(this.rung.name)
        if judgement.verdict is Verdict.PASSED:
            accepted_judgement = judgement
        result = judgement.as_result()
        judged.append(attempted(this.rung.name, this.attempt, result))
        return result

    def rode(this: Try) -> Result:
        ""
        nonlocal attempts_spent, accepted_judgement
        try:
            judgement = attempt(this)
        except Exception as exc:
            raise _AttemptError(this.rung.name, this.attempt, exc) from exc
        if judgement.verdict is Verdict.PASSED:
            attempts_spent += 1
            accepted_judgement = judgement
        return judgement.as_result()

    def raised_to_halted(raised: _AttemptError) -> Halted:
        ""
        history.extend(judged)
        history.append(_raised_attempt(raised))
        return Halted(
            outcome=Outcome.ERROR,
            entered=tuple(entered),
            history=tuple(history),
            attempts_spent=attempts_spent,
            escalations=max(0, len(spent_rungs) - 1),
            detail=history[-1].detail,
        )

    def finish_accepted(family: Family, rung: str) -> Delivered:
        assert accepted_judgement is not None  #
        return Delivered(
            family=family,
            rung=rung,
            #
            #
            #
            assurance=accepted_judgement.assurance or Assurance.UNVERIFIED,
            judgement=accepted_judgement,
            entered=tuple(entered),
            history=tuple(history),
            attempts_spent=attempts_spent,
            escalations=max(0, len(spent_rungs) - 1),
        )

    try:
        if riding is not None:
            ride = _ride(config, route, riding)
            held, riding = riding.rung, None
            try:
                ridden = climb(
                    ride, rode, capacity=capacity, permit=permit, claimed=held
                )
            except _AttemptError as raised:
                #
                history.append(_raised_attempt(raised))
            else:
                history.extend(ridden.history)
                if isinstance(ridden, Accepted):
                    return finish_accepted(ridden.family, ridden.rung)
            #
            #
            #
            entry = route.reserve_entry(relief=False)
            if entry is not None:
                route, claimed = _entered(config, pool, contract, capacity, entry)
                ceiling, budget = route.ceiling, route.budget
        for index, each in enumerate(route.plans):
            if not each.climbable:
                #
                #
                #
                #
                #
                continue
            #
            #to
            #
            taking = claimed if claimed in each.rungs else None
            if taking is not None:
                claimed = None
            judged.clear()
            try:
                result = climb(
                    each, observed, capacity=capacity, permit=permit, claimed=taking
                )
            except _AttemptError as raised:
                return raised_to_halted(raised)
            history.extend(result.history)
            if result.history:
                entered.append(each.family)
            if isinstance(result, Accepted):
                return finish_accepted(result.family, result.rung)
            if result.reason is Exhaustion.WITHHELD:
                break
            #
            #
            #
            #
            #he
            #
            if wake_hook is not None and _next_is_api(route.plans, index):
                woken = wake_hook(contract)
                if woken is not None:
                    extra = _single_rung_plan(
                        config, pool, contract, woken, each.family
                    )
                    if extra is not None:
                        judged.clear()
                        try:
                            extra_result = climb(
                                extra, observed, capacity=capacity, permit=permit
                            )
                        except _AttemptError as raised:
                            return raised_to_halted(raised)
                        history.extend(extra_result.history)
                        if extra_result.history:
                            entered.append(extra.family)
                        if isinstance(extra_result, Accepted):
                            return finish_accepted(
                                extra_result.family, extra_result.rung
                            )
    finally:
        #
        #
        #
        if entry is not None and claimed is not None:
            entry.release()
        if riding is not None:
            riding.release()

    escalations = max(0, len(spent_rungs) - 1)
    outcome = stopped_by or _spent_outcome(history, attempts_spent)
    return Halted(
        outcome=outcome,
        entered=tuple(entered),
        history=tuple(history),
        attempts_spent=attempts_spent,
        escalations=escalations,
        detail=_halt_detail(
            outcome, route, attempts_spent, escalations, tuple(entered)
        ),
    )


def _raised_attempt(raised: _AttemptError) -> Attempted:
    ""
    return Attempted(
        rung=raised.rung,
        attempt=raised.attempt,
        verdict=Verdict.FAILED,
        detail=(
            f"rung {raised.rung!r} raised {type(raised.cause).__name__}: {raised.cause}"
        ),
        raised=True,
        draw=raised.draw,
        draws=raised.draws,
        rows=raised.rows,
    )


def _entered(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    capacity: Capacity | None,
    entry: Entry,
) -> tuple[Ascent, str | None]:
    ""
    claimed: str | None = None
    try:
        route = ascent(config, pool, contract, floor=entry.family, capacity=capacity)
        claimed = _handed_down(route, entry)
    finally:
        #
        #
        if claimed is None:
            entry.release()
    return route, claimed


def _ride(config: Config, route: Ascent, riding: Entry) -> Plan:
    ""
    step = next(step for step in route.relief if step.rung.name == riding.rung)
    return Plan(family=family_of(config, riding.rung), steps=(step,))


def _idle_entry(route: Ascent) -> Entry | None:
    ""
    return route.reserve_entry()


def _handed_down(route: Ascent, entry: Entry) -> str | None:
    ""
    for each in route.plans:
        if each.family == entry.family:
            return entry.rung if entry.rung in each.rungs else None
    return None


def _next_is_api(plans: tuple[Plan, ...], index: int) -> bool:
    ""
    if index + 1 >= len(plans):
        return False
    return plans[index + 1].family.name == "api"


def _single_rung_plan(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    rung: str,
    family: Family,
) -> Plan | None:
    ""
    full = plan(config, pool, contract, family=family)
    for step in full.climbable:
        if step.rung.name == rung:
            return Plan(family=family, steps=(step,), fanout=Fanout.NONE)
    return None


def _spent_outcome(history: list[Attempted], attempts_spent: int) -> Outcome:
    if not history:
        return Outcome.NOTHING_TO_RUN
    if attempts_spent == 0:
        return Outcome.DECLINED_THROUGHOUT
    return Outcome.LADDER_SPENT


def _halt_detail(
    outcome: Outcome,
    route: Ascent,
    attempts_spent: int,
    escalations: int,
    entered: tuple[Family, ...],
) -> str:
    ""
    ran = entered or tuple(p.family for p in route.plans if p.climbable)
    climbed = ", ".join(dict.fromkeys(f.name for f in ran or route.families))
    if outcome is Outcome.NOTHING_TO_RUN:
        return (
            f"no family from {route.floor.name!r} upward offers a rung. {route.reason}"
        )
    if outcome is Outcome.ATTEMPT_CEILING:
        source = (
            "max_attempts"
            if route.ceiling.attempts is not None
            else "the ladder's own budget"
        )
        return (
            f"the task stopped at its attempt ceiling of {route.budget} "
            f"({source}); {escalations} escalation(s) across {climbed}."
        )
    if outcome is Outcome.ESCALATION_CEILING:
        return (
            f"the task stopped at max_escalations "
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


#


@dataclass(frozen=True)
class Disposition:
    ""

    reassignable: bool
    detail: str


def disposition(outcome: Outcome) -> Disposition:
    ""
    match outcome:
        case Outcome.ACCEPTED:
            return Disposition(
                reassignable=False,
                detail=(
                    "accepted: the change landed, so there is no work to move. "
                    "Reassigning here buys a second answer to a question that "
                    "already has one."
                ),
            )
        case Outcome.ESCALATION_CEILING:
            return Disposition(
                reassignable=True,
                detail=(
                    "escalation_ceiling: the climb stopped at "
                    "max_escalations with rungs of the ascent never "
                    "entered, so nothing here says the ladder cannot do the "
                    "work — only that it was not allowed to try. Raise the "
                    "ceiling, or hand the contract to someone who can pay for "
                    "the moves."
                ),
            )
        case Outcome.ATTEMPT_CEILING:
            return Disposition(
                reassignable=True,
                detail=(
                    "attempt_ceiling: the task stopped at what it may spend, "
                    "which bounds the bill and not the ladder's ability. The "
                    "same contract may be attempted again against a budget "
                    "that can pay for it."
                ),
            )
        case Outcome.LADDER_SPENT:
            return Disposition(
                reassignable=False,
                detail=(
                    "ladder_spent: every rung this install offers was tried "
                    "and none produced an acceptable change, so there is no "
                    "dearer family left to send the work to. The remedy is to "
                    "bind a dearer rung or to narrow the contract — raising a "
                    "number changes what it costs to fail, not whether it "
                    "fails."
                ),
            )
        case Outcome.NOTHING_TO_RUN:
            return Disposition(
                reassignable=False,
                detail=(
                    "nothing_to_run: no family from the contract's floor "
                    "upward offers a rung, so the pool stopped this and not "
                    "the work. Until a rung is bound — a config line, a "
                    "credential — moving the contract only relocates the same "
                    "answer."
                ),
            )
        case Outcome.DECLINED_THROUGHOUT:
            return Disposition(
                reassignable=False,
                detail=(
                    "declined_throughout: every rung of every family stepped "
                    "aside without spending an attempt, so no rung of this "
                    "ladder claims the contract. Nothing dearer is being "
                    "withheld; what is missing is a rung that accepts this "
                    "work, or a contract the bound rungs recognise."
                ),
            )
        case Outcome.ERROR:
            return Disposition(
                reassignable=True,
                detail=(
                    "error: an exception crossed the seam before any verdict "
                    "was reached, so the ladder was never given a chance to "
                    "answer. The failure is in the attempt machinery, not in "
                    "the work — address the cause and retry, or hand it to "
                    "another orchestrator."
                ),
            )
        case _:  #
            assert_never(outcome)


def may_reassign(outcome: Outcome, budget_remaining: int) -> bool:
    ""
    return disposition(outcome).reassignable and budget_remaining > 0
