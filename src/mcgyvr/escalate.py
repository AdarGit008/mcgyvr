"""The climb above the attempt seam: judge one attempt, plan it, spend it.

`judge` turns an attempt's gate result and its reviewer into a `Judgement`;
`ascent` says which families a contract may be carried through and what
that may cost before anything is spent; `escalate` climbs them, charging
every attempt to the configured ceilings, and returns a `Delivered` or the
`Halted` outcome that stopped it, which `disposition` reads to say whether
the work may be handed on. `how_judged` and `reply_judged` state the bar an
acceptance rests on in words.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field, replace
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

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract

    # `deliver.Accepted` is a change bound for delivery — its content,
    # digest and the paths it covers — aliased because `route.Accepted`
    # already names the climb's answer. The two are different values and
    # must not be read for one another.
    from mcgyvr.deliver import Accepted as BoundContent
    from mcgyvr.gate import GateResult
    from mcgyvr.local_pool import SourceMap

GATE_ONLY = "gate_only"
MODEL = "model"

# The two verification policies, cheapest first. `gate_only` accepts a
# change on the deterministic gate alone; `model` adds a fresh-context
# reviewer. A policy this build does not know ranks as `model`, so an
# unknown name can only raise the bar.
_POLICY_RANK: dict[str, int] = {GATE_ONLY: 0, MODEL: 1}


class Outcome(StrEnum):
    """What a task came to, in one word.

    `accepted` is the only one `Delivered` reports. The rest name what
    stopped the climb: a spent ladder, one of the two ceilings, an ascent
    with nothing to run, a ladder that declined throughout, or an
    exception crossing the seam.
    """

    ACCEPTED = "accepted"
    LADDER_SPENT = "ladder_spent"
    ESCALATION_CEILING = "escalation_ceiling"
    ATTEMPT_CEILING = "attempt_ceiling"
    NOTHING_TO_RUN = "nothing_to_run"
    DECLINED_THROUGHOUT = "declined_throughout"
    ERROR = "error"


class Assurance(StrEnum):
    """What accepting a change or a reply rests on.

    `deterministic` is a tool's output accepted on the gate alone,
    `verified` a change a reviewer agreed with, `unverified` a change
    accepted on the gate alone because no usable reviewer was there, and
    `checked`/`unchecked` a reply accepted on its named output checks, or
    with none named.
    """

    DETERMINISTIC = "deterministic"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CHECKED = "checked"
    UNCHECKED = "unchecked"


#: Why a change was accepted without a reviewer, as a sentence rather than a
#: flag: it lands in a judgement's detail, where the user reads it.
NO_REVIEWER = "no reviewer is configured — set `verifier.unit`"


def reply_judged(name: str, checks: Sequence[str]) -> str:
    """Say how a reply — not a change — was accepted.

    A reply is never reviewed, so its bar is the output checks it named,
    or nothing at all when it named none. `name` is the task type as the
    user wrote it.
    """
    if not checks:
        return f"served unchecked: {name} replies are not checked or reviewed."
    return (
        f"accepted on its output checks ({', '.join(checks)}); "
        f"{name} replies are never reviewed."
    )


def how_judged(kind: TaskType) -> str:
    """Say what acceptance of this task type rests on, and how sure it is.

    A tool's output is the deterministic gate; work that judges a change is
    the gate and then a reviewer; a reply is its output checks. Each
    sentence names the `Assurance` the same path would report, so a printed
    bar and a recorded one cannot drift apart.
    """
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
    """What a reviewer said about a change.

    `agreed` and `refused` are verdicts; `unusable` is the absence of one —
    the reviewer could not be asked, or answered something that names no
    outcome.
    """

    AGREED = "agreed"
    REFUSED = "refused"
    UNUSABLE = "unusable"


@dataclass(frozen=True)
class Review:
    """One reviewer's answer about a change, with the sentence it gave.

    The named constructors are the only way to build one, so a verdict is
    never a bare boolean where a `False` would have to mean either "refused"
    or "did not answer".
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
    """What a failed attempt hands the next try.

    `checks` names the checks that failed and `lines` holds one
    model-facing sentence per finding; `text` renders those as a bullet
    list. Nothing that passed is repeated.
    """

    checks: tuple[str, ...]
    lines: tuple[str, ...]

    @classmethod
    def of(cls, gate: GateResult) -> RetryNotes | None:
        """The notes for a gate that rejected a change, or None if it did not.

        Only `findings` count: observations and environment issues are what
        the gate said without refusing, and a retry told to fix them would be
        fixing something that was never held against it.
        """
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
    """What one try came to at the attempt seam.

    `verdict` is what the climb acts on. `accepted` is the change bound for
    delivery when one landed, `assurance` is what accepting it rests on, and
    `policy` is the verification policy it was judged under, with `upgraded`
    saying whether that was raised above the contract's own. `retry` carries
    what a later try must fix, `reviewer_failed` says a reviewer was asked
    and answered nothing usable, and the draw fields are the breadth
    bookkeeping a `Result` carries into the history.
    """

    verdict: Verdict
    accepted: BoundContent | None = None
    assurance: Assurance | None = None
    policy: str = GATE_ONLY
    upgraded: bool = False
    reviewer_failed: bool = False
    retry: RetryNotes | None = None
    detail: str = ""
    #: `draw` is the dispatch this judgement is about, `draws` the breadth
    #: the attempt asked for, and `rows` how many draws left a record.
    draw: int = 0
    draws: int = 1
    rows: int = 1

    def as_result(self) -> Result:
        """This judgement as the `Result` the climb records and returns.

        The retry lines become the result's findings, so the reason a try
        failed travels in the history rather than only in the judgement that
        held it.
        """
        findings = self.retry.lines if self.retry is not None else ()
        return Result(
            verdict=self.verdict,
            detail=self.detail,
            findings=findings,
            draw=self.draw,
            draws=self.draws,
            rows=self.rows,
        )


# The verification policy, and the judge that applies it to one attempt.


def required_policy(contract: Contract, family: Family) -> str:
    """The verification policy work in `family` is actually judged under.

    The contract's declared policy, raised to `model` above the
    deterministic floor: a tool's output can be accepted on the gate alone,
    a model's cannot, so a `gate_only` contract cannot buy a model's change
    the lighter bar. The raise is only upward — a declared `model` is never
    lowered.
    """
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
    """Judge one attempt: the gate first, then a reviewer only where one is owed.

    A gate that rejected the change fails the attempt and carries the failing
    checks as retry notes; no verifier is asked about a change already refused.
    A task type that does not judge a change answers with a reply, and a reply
    is accepted on its own output checks under the policy the contract declared.
    Under `gate_only` the gate is the whole bar. With no verifier seam the
    change is accepted on the gate alone, labelled unverified, and `absent`
    says why. Otherwise the seam is asked once: agreement is `verified`, a
    refusal is a failed attempt carrying what to fix, and an unusable answer is
    neither — the change is accepted unverified, with `reviewer_failed` set.
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

    if not contract.kind.judges_a_change:
        checks = contract.evidence_names
        return Judgement(
            verdict=Verdict.PASSED,
            assurance=Assurance.CHECKED if checks else Assurance.UNCHECKED,
            # A reply is not a change, so no verification policy is applied
            # to it: the contract's own declared policy is reported as it
            # stands.
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
            # A refusal is the builder's failure, so the attempt fails and
            # carries what to fix: the reviewer's sentence, then whatever
            # the non-blocking jev rung saw. The gate passed, so no gate
            # findings are here, and without the jev lines a retry would
            # hear the verifier and nothing else.
            retry=_refusal_notes(review, gate),
            # The detail is the reviewer's own sentence: nothing here
            # invents a reason for a refusal that was stated.
            detail=f"refused by {reviewer or 'the verifier'}: {review.detail}",
        )
    # An unusable review is neither an approval nor the builder's fault:
    # the change is accepted on the gate alone, labelled unverified so a
    # result is never reported as more assured than it is, and flagged so a
    # caller can see that a reviewer was asked and answered nothing usable.
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
    """What a refused change hands the next try.

    The reviewer's sentence comes first, then whatever the non-blocking jev
    rung saw, as findings and observations. The `jev` check is named only
    when that rung saw something, so a refusal with no detail claims no
    more of it than it has.
    """
    reasons = () if gate.jev is None else (*gate.jev.findings, *gate.jev.observations)
    return RetryNotes(
        checks=("verifier", *(("jev",) if reasons else ())),
        lines=(
            f"verifier: {review.detail}",
            *(finding.for_model() for finding in reasons),
        ),
    )


# The ceilings a climb is spent under, and the rung it enters at.


@dataclass(frozen=True)
class Ceiling:
    """The two numbers that bound a task.

    `escalations` is `max_escalations` and `attempts` is `max_attempts`,
    held as `None` when the config leaves it unset — the ladder's own
    budget then bounds the task, so no ceiling here is unbounded.
    """

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
    """A rung claimed for the climb, with its slot already held.

    It names the family and rung the ascent enters at, the machine and
    capacity the claim was taken against, and whether the rung is a relief
    one.
    """

    family: Family
    rung: str
    machine: Machine = field(repr=False, compare=False)
    capacity: Capacity = field(repr=False, compare=False)
    #: `relief` says the rung is a lent one, outside the ladder. Machine and
    #: capacity are out of repr and equality: a printed entry names no
    #: machine, and two claims on the same rung compare equal.
    relief: bool = False

    def release(self) -> None:
        """Give the claim back, so the slot this entry held is free again."""
        self.machine.release(self.capacity, self.rung)


@dataclass(frozen=True)
class _Found:
    """A free rung the entry scan found, before anything is claimed for it.

    It carries the family it was found in, so the ascent can be rebuilt at
    that floor, and whether the rung is a relief one.
    """

    family: Family
    rung: str
    machine: Machine
    relief: bool = False


@dataclass(frozen=True)
class Ascent:
    """The whole climb a contract describes, stated before anything is spent.

    `plans` is one per catalog family from `floor` upward, so the climb is
    monotonic by shape. `ceiling` and `capacity` bound it, `fanout` and
    `widths` are what the entry decision reads, and `relief` holds the lent
    rungs, which are never a step of the ladder.
    """

    floor: Family
    plans: tuple[Plan, ...]
    ceiling: Ceiling
    fanout: Fanout = Fanout.NONE
    capacity: Capacity | None = field(default=None, repr=False, compare=False)
    widths: Mapping[str, int] = field(default_factory=dict, repr=False, compare=False)
    relief: tuple[Step, ...] = ()

    def __bool__(self) -> bool:
        """Whether any family in the ascent offers a rung."""
        return bool(self.runnable)

    def __len__(self) -> int:
        return len(self.runnable)

    @property
    def families(self) -> tuple[Family, ...]:
        """Every family in the ascent, the ones with no rung included."""
        return tuple(p.family for p in self.plans)

    @property
    def runnable(self) -> tuple[Plan, ...]:
        """The plans that offer at least one climbable rung."""
        return tuple(p for p in self.plans if p.climbable)

    @property
    def rungs(self) -> tuple[str, ...]:
        return tuple(name for p in self.plans for name in p.rungs)

    @property
    def ladder_budget(self) -> int:
        """The attempts the ladder's own steps add up to, before any ceiling."""
        return sum(p.climb_budget for p in self.plans)

    @property
    def budget(self) -> int:
        """The attempts the task may actually spend.

        The ladder's own budget, capped by `max_attempts` when the config
        states one. A ceiling can only lower what the ladder offers, never
        raise it.
        """
        if self.ceiling.attempts is None:
            return self.ladder_budget
        return min(self.ladder_budget, self.ceiling.attempts)

    @property
    def most_rungs(self) -> int:
        """How many rungs the ascent can enter under `max_escalations`.

        The entry plus one move per escalation, or every rung the ladder has
        if that is fewer.
        """
        return min(len(self.rungs), self.ceiling.escalations + 1)

    @property
    def next_free_rung(self) -> str | None:
        """The rung the idle fan-out would enter at, or None if nothing is free.

        It names the rung without claiming it, so a caller can ask without
        narrowing a source.
        """
        found = self._entry_rung(reserve=False)
        return None if found is None else found.rung

    def reserve_entry(self, *, relief: bool = True) -> Entry | None:
        """Claim the entry rung's slot, or None when there is no entry to claim.

        Only a rung that raises above the floor, or a relief rung, is worth a
        claim. `relief=False` leaves the lent rungs out of the scan.
        """
        found = self._entry_rung(reserve=True, relief=relief)
        if found is None:
            return None
        if not found.relief and not self._raises(found.family):
            return None
        # Only a rung that raises above the floor is worth a claim, and the
        # scan returned something only because a capacity was there to claim
        # against.
        assert self.capacity is not None
        return Entry(
            family=found.family,
            rung=found.rung,
            machine=found.machine,
            capacity=self.capacity,
            relief=found.relief,
        )

    def _raises(self, family: Family) -> bool:
        """Whether reaching this family is a move above where the climb starts."""
        return family.rank > self.floor.rank

    def _entry_rung(self, *, reserve: bool, relief: bool = True) -> _Found | None:
        """The scan behind `next_free_rung` and `reserve_entry`.

        Only `idle` fan-out with a known capacity can decide an entry: the
        decision needs both the width of a rung and what already holds it.
        The plans are walked in rank order and the first rung with a free
        slot is returned; when `reserve` is set and its family raises above
        the floor, a slot is claimed for it. Relief rungs are offered once,
        and only after the first family with climbable rungs has none free.
        A fullness that cannot be read — no machine, or no declared width —
        ends the walk with None rather than routing around an unknown.
        """
        capacity = self.capacity
        if self.fanout is not Fanout.IDLE or capacity is None:
            return None
        riding = self.relief if relief else ()
        # How busy each source is on the server side, read once under the rung
        # name the full check is asked with.
        servers = {
            step.rung.name: step.machine.server(capacity)
            for step in (*(s for p in self.plans for s in p.climbable), *riding)
            if step.machine is not None
        }

        def full(step: Step) -> bool | None:
            # None is an unknown, not a free slot: with no machine or no
            # declared width nothing can say the rung has room, and the walk
            # stops rather than spend to route around what it cannot read.
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
                # Relief is offered once, and only here: the first family
                # whose rungs are all busy hands the work to a lent rung.
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
        """The reasons the plans with no rung give, joined into one sentence."""
        return " ".join(f"{p.family.name}: {p.reason}" for p in self.plans if p.reason)


def ascent(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    floor: Family | None = None,
    capacity: Capacity | None = None,
) -> Ascent:
    """Build the ascent for a contract before any of it is spent.

    Every catalog family from `floor` — the contract's own starting family
    unless one is given — upward gets a plan, and the ceilings, fan-out
    mode and relief rungs are read from the config and the pool. Raises
    `RouteError` when the floor is not a family of the loaded catalog.
    """
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
    """How many slots each configured rung and relief rung has.

    Read once from the capacity so the entry decision does not ask per
    step. A rung the capacity says nothing about is left out, and without a
    capacity there are no widths at all.
    """
    if capacity is None:
        return {}
    limits = capacity.limits
    return {
        name: capacity.limit(name)
        for name in (*config.ladder.names, *config.relief)
        if name in limits
    }


# The two shapes a finished task takes, and what each of them carries.


@dataclass(frozen=True)
class Delivered:
    """A task that ended in an accepted change.

    It names the family and rung that produced it, what the acceptance
    rests on, the judgement that accepted it, the families entered, every
    attempt in order, and what the climb cost. `ok` is always true and
    `outcome` is always `accepted`.
    """

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
        """Whether a reviewer agreed with the change, rather than the gate alone."""
        return self.assurance is Assurance.VERIFIED


@dataclass(frozen=True)
class Halted:
    """A task that ended without an accepted change.

    `outcome` is what stopped it and `detail` says so in a sentence.
    `entered` and `history` record every family and attempt the task got
    through, and the two counts are what it spent. `ok` is always false.
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


class DispatchRaisedError(Exception):
    """An exception that crossed a dispatch, with the draw it belongs to.

    The attempt seam raises this so a failure is not mistaken for a
    verdict: the cause travels intact, with the breadth the attempt asked
    for, the draws that left a record, and which of them raised.
    """

    def __init__(
        self,
        cause: BaseException,
        *,
        draws: int,
        rows: int,
        draw: int | None = None,
    ) -> None:
        super().__init__(str(cause))
        #: The exception itself, kept so an attempt record can name its type
        #: in the sentence it reports.
        self.cause = cause
        #: The breadth this attempt asked for: independent dispatches of one try.
        self.draws = draws
        #: How many of those draws left a journal row: 0 when none did.
        self.rows = rows
        #: Which draw raised, or None when no single dispatch caused it.
        self.draw = draw


class _AttemptError(Exception):
    """An attempt that raised, tagged with where it happened.

    The rung and attempt number say where, and a `DispatchRaisedError` is
    unwrapped here so the cause and its draw counts arrive without an extra
    layer. An exception that crossed no dispatch is counted as no draws at
    all.
    """

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
    """Climb the ascent until a change is accepted or a ceiling stops it.

    `attempt` is the seam that makes one try and answers with a
    `Judgement`. A decline spends nothing and moves the climb on; any other
    verdict charges an attempt and records the rung that charged it. A rung
    entered after another has charged is an escalation, and `max_escalations`
    bounds how many of those the climb may make, while every attempt is
    charged to `max_attempts` or the ladder's own budget.

    A relief rung claimed as the entry is ridden first, as a one-step plan
    of its own, and the climb is then rebuilt at the family whose rung was
    claimed: the plans are walked in rank order, a family with no rung is
    passed over, and the first accepted judgement returns `Delivered`.
    `wake_hook` is asked before the api family is paid for, and a rung it
    names is tried first. `presence` marks a rung as climbed on for the
    duration of an attempt above the entry rung. Capacity claims are given
    back on every path, and an exception from the seam ends the task as
    `Outcome.ERROR` rather than as a failed attempt.
    """
    route = ascent(config, pool, contract, floor=floor, capacity=capacity)
    entry = _idle_entry(route)
    # A relief rung claimed as the entry is ridden on its own, before the
    # ladder: it is not a step of the ascent, so it cannot be one of the
    # plans below.
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
    # Every attempt made during the family now being climbed. `climb` builds
    # its own history and returns it, except when an attempt raises — then
    # nothing comes back, so the attempts already made are recorded here and
    # handed to the halt with the one that raised. Cleared once per family,
    # and again before the woken rung, so none is counted twice.
    judged: list[Attempted] = []

    def permit(step: Step, number: int) -> bool:
        nonlocal stopped_by
        if attempts_spent >= budget:
            stopped_by = Outcome.ATTEMPT_CEILING
            return False
        # A step is a move when some rung has already spent and this one has
        # not: the first rung to spend is the entry, and each rung entered
        # after it is an escalation. Only a non-declined verdict charges an
        # attempt, so a rung that stepped aside stays out of `spent_rungs`,
        # and the ceiling counts rungs that charged rather than rungs tried.
        moving = step.rung.name not in spent_rungs and bool(spent_rungs)
        if moving and len(spent_rungs) > ceiling.escalations:
            stopped_by = Outcome.ESCALATION_CEILING
            return False
        return True

    def observed(this: Try) -> Result:
        nonlocal attempts_spent, accepted_judgement
        # A rung is marked as climbed only once the climb has spent on
        # another rung: the entry is not climbed, and takes no marker.
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
            # Any exception from the seam ends the task as an error rather
            # than being read as a failed attempt: the raise is tagged with
            # the rung and attempt number it came from, and `_AttemptError`
            # unwraps a `DispatchRaisedError` so the cause and its draw
            # counts survive without an extra layer.
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
        """Make one try on the relief rung the task rides.

        A relief rung is not a step of the ladder: no budget counts it, so
        only a pass charges an attempt, and it is never a move in the
        escalation arithmetic.
        """
        nonlocal attempts_spent, accepted_judgement
        try:
            judgement = attempt(this)
        except Exception as exc:
            raise _AttemptError(this.rung.name, this.attempt, exc) from exc
        if judgement.verdict is Verdict.PASSED:
            attempts_spent += 1
            accepted_judgement = judgement
        return judgement.as_result()

    def _unit_of(rung: str) -> tuple[str, str, bool]:
        """The model, address and relief flag of the unit `rung` names."""
        unit = config.units.get(rung) or config.relief.get(rung)
        if unit is None:
            return "", "", False
        return unit.served_model or unit.model or "", unit.address or "", unit.relief

    def recorded() -> tuple[Attempted, ...]:
        """The history, each try stamped with the unit that served it.

        A relief rung is recorded like any other try, but `relief` is `True`
        and it charges the budget only when it passes: the record carries it,
        the spend does not.
        """
        rows: list[Attempted] = []
        for row in history:
            model, address, relief = _unit_of(row.rung)
            rows.append(replace(row, relief=relief, model=model, address=address))
        return tuple(rows)

    def raised_to_halted(raised: _AttemptError, family: Family) -> Halted:
        """Build the halt for an attempt that raised.

        The attempts this family already made are added — `climb` never
        returned its history — and the raised one after them, so the record
        reaches the try that ended the task. The raising family is entered
        too, so `entered` and `history` name the same families.
        """
        history.extend(judged)
        history.append(_raised_attempt(raised))
        if family not in entered:
            entered.append(family)
        return Halted(
            outcome=Outcome.ERROR,
            entered=tuple(entered),
            history=recorded(),
            attempts_spent=attempts_spent,
            escalations=max(0, len(spent_rungs) - 1),
            detail=history[-1].detail,
        )

    def finish_accepted(family: Family, rung: str) -> Delivered:
        assert accepted_judgement is not None  # Only `PASSED` returns `Accepted`.
        return Delivered(
            family=family,
            rung=rung,
            # `Accepted` is returned only for a `PASSED` judgement, and a
            # judgement that named no bar is reported unverified rather than
            # defaulted to the more assured reading.
            assurance=accepted_judgement.assurance or Assurance.UNVERIFIED,
            judgement=accepted_judgement,
            entered=tuple(entered),
            history=recorded(),
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
                # The raise is recorded and the ladder is entered anyway: a
                # relief rung that raises does not end the task.
                history.append(_raised_attempt(raised))
            else:
                history.extend(ridden.history)
                if isinstance(ridden, Accepted):
                    return finish_accepted(ridden.family, ridden.rung)
            # Whatever the ride came to, the ladder is entered now. The
            # ascent is rebuilt at the family whose rung was claimed, so the
            # ride is not re-entered, no relief rung is offered a second time,
            # and the ceilings and budget are read again from the ascent that
            # will actually be climbed.
            entry = route.reserve_entry(relief=False)
            if entry is not None:
                route, claimed = _entered(config, pool, contract, capacity, entry)
                ceiling, budget = route.ceiling, route.budget
        for index, each in enumerate(route.plans):
            if not each.climbable:
                # A family that offers no rung costs nothing and is passed
                # over: its reason stays on the plan and is told if nothing
                # runs at all. Neither ceiling is charged for it, and the
                # families above may still offer a rung.
                continue
            # The claim taken at the entry decision is handed down to the
            # climb of the family that lists it, so its first step starts in
            # a slot already held; a claim this plan cannot name is not used.
            taking = claimed if claimed in each.rungs else None
            if taking is not None:
                claimed = None
            judged.clear()
            try:
                result = climb(
                    each, observed, capacity=capacity, permit=permit, claimed=taking
                )
            except _AttemptError as raised:
                return raised_to_halted(raised, each.family)
            history.extend(result.history)
            if result.history:
                entered.append(each.family)
            if isinstance(result, Accepted):
                return finish_accepted(result.family, result.rung)
            if result.reason is Exhaustion.WITHHELD:
                break
            # Before the dearest family is paid for, the hook is asked
            # whether a resident rung should be woken to try this contract
            # first. A rung it names is climbed now as a one-step plan in the
            # family that just spent, and a pass there ends the task without
            # reaching the api family. A hook that names nothing, or a rung
            # this contract's plan does not offer, leaves the ascent as it is.
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
                            return raised_to_halted(raised, extra.family)
                        history.extend(extra_result.history)
                        if extra_result.history and extra.family not in entered:
                            entered.append(extra.family)
                        if isinstance(extra_result, Accepted):
                            return finish_accepted(
                                extra_result.family, extra_result.rung
                            )
    finally:
        # Every claim made before the climb is given back here, on every
        # path: a reservation leaked by an entry decision narrows a source
        # for the rest of the process.
        if entry is not None and claimed is not None:
            entry.release()
        if riding is not None:
            riding.release()

    escalations = max(0, len(spent_rungs) - 1)
    outcome = stopped_by or _spent_outcome(history)
    return Halted(
        outcome=outcome,
        entered=tuple(entered),
        history=recorded(),
        attempts_spent=attempts_spent,
        escalations=escalations,
        detail=_halt_detail(
            outcome, route, attempts_spent, escalations, tuple(entered)
        ),
    )


def _raised_attempt(raised: _AttemptError) -> Attempted:
    """Record an attempt that raised as a failed `Attempted`.

    The detail names the exception's type and message, and the draw fields
    say how much of the breadth was dispatched before it raised.
    """
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
    """Rebuild the ascent at the claimed family and hand the claim down to it.

    Returns the ascent to climb and the rung whose slot is already held, or
    None when the rebuilt ascent no longer offers that rung.
    """
    claimed: str | None = None
    try:
        route = ascent(config, pool, contract, floor=entry.family, capacity=capacity)
        claimed = _handed_down(route, entry)
    finally:
        # A claim the rebuilt ascent cannot name is released here: nobody
        # downstream can give back a reservation for a rung it cannot see.
        if claimed is None:
            entry.release()
    return route, claimed


def _ride(config: Config, route: Ascent, riding: Entry) -> Plan:
    """The one-step plan for a relief rung, in the family it is lent to."""
    step = next(step for step in route.relief if step.rung.name == riding.rung)
    return Plan(family=family_of(config, riding.rung), steps=(step,))


def _idle_entry(route: Ascent) -> Entry | None:
    """The entry the idle fan-out reserves for this ascent, if there is one."""
    return route.reserve_entry()


def _handed_down(route: Ascent, entry: Entry) -> str | None:
    """The rung to hand down, or None when the rebuilt plan no longer offers it."""
    for each in route.plans:
        if each.family == entry.family:
            return entry.rung if entry.rung in each.rungs else None
    return None


def _next_is_api(plans: tuple[Plan, ...], index: int) -> bool:
    """Whether the family after `index` is the api one — the dearest to reach."""
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
    """A plan holding only the named rung of `family`, or None.

    The rung is looked up in that family's own plan, so a rung this
    contract does not offer yields nothing. The plan holds the one step and
    no fan-out: a woken rung is climbed on its own.
    """
    full = plan(config, pool, contract, family=family)
    for step in full.climbable:
        if step.rung.name == rung:
            return Plan(family=family, steps=(step,), fanout=Fanout.NONE)
    return None


def _spent_outcome(history: list[Attempted]) -> Outcome:
    """Classify a spent ladder from what happened, not from the budget.

    `attempts_spent` is a budget counter and deliberately leaves free tries
    uncounted — a relief rung that failed or declined costs nothing — so it
    cannot say whether any rung actually tried. `history` can: a task whose
    only rows are declines stepped aside throughout, while any failed
    verdict means something tried and was rejected. A raised row is neither
    a decline nor a spent attempt, so it is skipped here exactly the way
    `attempts_spent` skips it.
    """
    if not history:
        return Outcome.NOTHING_TO_RUN
    tried = [a for a in history if not a.raised]
    if not tried or all(a.verdict is Verdict.DECLINED for a in tried):
        return Outcome.DECLINED_THROUGHOUT
    return Outcome.LADDER_SPENT


def _halt_detail(
    outcome: Outcome,
    route: Ascent,
    attempts_spent: int,
    escalations: int,
    entered: tuple[Family, ...],
) -> str:
    """The sentence a halted task carries, saying why it stopped.

    The families it names are the ones that ran, or — when none did — the
    ones that offered a rung. Each outcome gets its own account: nothing to
    run, an attempt ceiling, an escalation ceiling, declines throughout, or
    a spent ladder.
    """
    ran = entered or tuple(p.family for p in route.plans if p.climbable)
    climbed = ", ".join(dict.fromkeys(f.name for f in ran or route.families))
    if outcome is Outcome.NOTHING_TO_RUN:
        return (
            f"no family from {route.floor.name!r} upward offers a rung. {route.reason}"
        )
    if outcome is Outcome.ATTEMPT_CEILING:
        source = (
            "max_attempts"
            if (
                route.ceiling.attempts is not None
                and route.ceiling.attempts < route.ladder_budget
            )
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


def redundant_relief(config: Config) -> tuple[str, ...]:
    """Sentences naming relief rungs that duplicate a unit you already serve.

    A relief rung whose address is one of your own units, or whose
    `served_model` is a model your own ladder already serves, re-sends to
    what you already have: riding it cannot help, so a run says so instead
    of letting the user discover it from the journal.
    """
    notes: list[str] = []
    for name, unit in config.relief.items():
        for own, other in config.units.items():
            if unit.address and unit.address == other.address:
                notes.append(
                    f"relief rung {name!r} is the same unit as your own "
                    f"{own!r} ({unit.address}) — riding it re-sends to the "
                    f"unit you already have, so it will not help."
                )
                break
            if unit.served_model and unit.served_model == other.model:
                notes.append(
                    f"relief rung {name!r} serves model {unit.served_model!r}, "
                    f"which your own {own!r} already serves — riding it will "
                    f"not help."
                )
                break
    return tuple(notes)


# What a halted outcome means for the work: whether it may be handed on.


@dataclass(frozen=True)
class Disposition:
    """Whether a halted task's work may be handed to another orchestrator, and why."""

    reassignable: bool
    detail: str


def disposition(outcome: Outcome) -> Disposition:
    """The disposition for one outcome: whether to reassign, and why.

    Accepted work has no question left to answer, a spent or empty ladder
    and a ladder that declined throughout would give the same answer
    elsewhere, and the two ceilings and an error settled nothing about the
    work — those are the ones worth handing on.
    """
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
        case _:  # pragma: no cover - unreachable while the match is exhaustive
            assert_never(outcome)
