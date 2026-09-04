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

**And the name is acted on, because a mode that changes no dispatch is a false
entry in the published reference.** :func:`escalate` *enters* at the family of
:attr:`Ascent.next_free_rung` — it rebuilds the ascent with that family as its
floor, which is choosing where to begin and not reordering anything, since the
rungs of whichever family is entered are still :func:`~mcgyvr.route.plan`'s own
price order. Within that family the cheapest rung with a free slot is
:func:`~mcgyvr.route.climb`'s to take, under the same ``idle``, so the two seams
answer the two halves of one question and neither restates the other.
Computing the answer and discarding it was the earlier state and it made
``ladder.fanout: idle`` a switch wired to nothing: the schema's ``doc`` told
operators the mode reaches a priced rung rather than waits, and setting it
changed no dispatch at all. The choice is a read and not yet a claim, though:
what a concurrent batch can lose in the window between naming a free rung here
and reserving one down in :func:`~mcgyvr.route.climb` is written down in
:func:`_idle_entry`, with the change in :mod:`mcgyvr.route` that would close it.

**Busy is not a verdict, and the record is the difference.** A rung that
:attr:`~Ascent.next_free_rung` passed over was not tried: it produced no
verdict, spent no attempt and funded no escalation, because
:meth:`~mcgyvr.capacity.Capacity.hold` blocks rather than raising and a queue is
not a failure. So an api rung reached under ``idle`` and an api rung reached by
escalation are the same rung with two different histories — one was chosen
before anything ran, the other was climbed to after something failed — and only
the second says the local family could not do the work. That difference is what
keeps a raised entry off ``budgets.max_escalations``: the count is over rungs
that *ran*, so a rung entered at costs nothing until it produces a verdict, and
a contract whose floor family was saturated at the moment it started still has
its whole escalation budget to climb with. :func:`_idle_entry` is where that is
written down.

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

**How a task ended and what to do about it are two questions.**
:class:`Outcome` answers the first and deliberately not the second, and every
caller that has to decide whether the work may be tried somewhere else would
otherwise re-derive the answer from the outcome's *name* — differently, in each
caller, and silently. :func:`disposition` answers it once per outcome with a
reason a human can act on, and :func:`may_reassign` is the single decision that
reads it together with the budget. The split it draws is the one a caller acts
on: the two ceilings are numbers an operator chose and can raise, so work they
stopped may move; a spent ladder is a statement about what this install can do,
and sending it to a dearer family that does not exist changes the bill and
nothing else. Ported from local-ai's ``REASSIGNABLE`` set, and needed here
before §9's ``main_out_queue`` can exist, because pushing work back for another
orchestrator to take *is* a reassignment and cannot be written against a
taxonomy that does not say which failures are eligible.

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
from typing import TYPE_CHECKING, assert_never

from mcgyvr.catalog import Family, catalog
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
    fanout_of,
    plan,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract

    # Aliased on import, because this module already binds the name `Accepted`
    # to `mcgyvr.route.Accepted` — a *climb outcome*, unrelated to this one. The
    # collision is real and pre-existing; spelling the delivery type differently
    # here is cheaper than renaming either class, and it makes the two
    # distinguishable at every use in this file rather than only at the import.
    from mcgyvr.deliver import Accepted as BoundContent
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
    and these are the seven. The distinctions are the ones a caller has to act
    on differently: work that was accepted, a ladder that was genuinely tried
    and could not, two different ceilings that stopped it early, an install
    that had nothing to run in the first place, a ladder that declined
    throughout, and an exception that crossed the seam before any verdict was
    reached. Prose is carried alongside in ``detail`` for a human; nothing
    branches on it.
    """

    ACCEPTED = "accepted"
    LADDER_SPENT = "ladder_spent"
    ESCALATION_CEILING = "escalation_ceiling"
    ATTEMPT_CEILING = "attempt_ceiling"
    NOTHING_TO_RUN = "nothing_to_run"
    DECLINED_THROUGHOUT = "declined_throughout"
    ERROR = "error"


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

    A fourth exclusion is not this class's to decide and is not applied here:
    the lines are rendered with :meth:`~mcgyvr.gate.findings.Finding.for_model`
    rather than ``str``, so an acceptance finding arrives without the command it
    ran. ``acceptance`` is an orchestrator-only contract field (#94) and a note
    is worker-facing text; rendering with ``str`` put the field the worker view
    excludes into the second prompt of every retried task.
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
            lines=tuple(f.for_model() for f in gate.findings),
        )

    @property
    def text(self) -> str:
        return "\n".join(f"- {line}" for line in self.lines)


@dataclass(frozen=True)
class Judgement:
    """What one attempt came to, and what its acceptance would rest on.

    This is what an attempt function hands the driver, rather than a bare
    :class:`~mcgyvr.route.Result`, because a task-level answer has to say which
    bar was cleared and a routing verdict cannot carry that without
    :mod:`mcgyvr.route` learning what verification is.

    **``accepted`` is the work, and it answers for its own bytes.** It is the
    content read back out of the tree the gate judged
    (:meth:`mcgyvr.deliver.Accepted.read`, which has no parameter to hand
    content through), so a caller cannot be holding one thing while the verdict
    is about another.

    There is deliberately no second field. An earlier ``value: T`` carried
    whatever the attempt function happened to be holding — the worker's reply as
    a string — and nothing bound it to ``verdict``: a step that rewrote the
    *tree* between the write and the gate left it stale, which is the port's
    documented repair loop run as written. It had exactly one reader in the
    repository, a second delivery implementation that wrote it and committed it
    without re-gating. Both are gone, and with them the type parameter that
    existed only to carry it (pattern B).
    """

    verdict: Verdict
    accepted: BoundContent | None = None
    assurance: Assurance | None = None
    policy: str = GATE_ONLY
    upgraded: bool = False
    reviewer_failed: bool = False
    retry: RetryNotes | None = None
    detail: str = ""
    #: Which draw the verdict is about and how many were made; see
    #: :class:`~mcgyvr.route.Result`.
    draw: int = 0
    draws: int = 1

    def as_result(self) -> Result:
        """The routing verdict, for :func:`~mcgyvr.route.climb`, with the findings.

        The finding lines ride along so the climb's record can say *why* a
        rung failed and not only that it did; ``route`` never reads them.
        """
        findings = self.retry.lines if self.retry is not None else ()
        return Result(
            verdict=self.verdict,
            detail=self.detail,
            findings=findings,
            draw=self.draw,
            draws=self.draws,
        )


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


def judge(
    contract: Contract,
    family: Family,
    gate: GateResult,
    *,
    verifier: Callable[[], Review] | None = None,
) -> Judgement:
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
class Entry:
    """A raised entry: the family to climb into, and the rung reserved for it.

    What :meth:`Ascent.reserve_entry` hands back, and it is a *held* thing
    rather than a described one — the reservation exists by the time this
    record does. That is the difference between it and a rung name: a name is a
    reading every member of a batch can take at once, and a reservation is
    something exactly one of them has.

    It therefore carries an obligation, and the type is what makes the
    obligation visible: whoever holds one either hands ``rung`` to
    :func:`~mcgyvr.route.climb` as ``claimed``, which releases it once when that
    rung is done with, or calls :meth:`release` itself. A leaked reservation is
    forever, and it would show that source as busy to every later choice this
    process makes.

    ``machine`` and ``capacity`` are the two halves of giving it back and are
    out of ``repr`` and out of the comparison, for the reason :class:`Ascent`
    gives about both: they are how the answer is acted on and not part of the
    answer, and #20's rule is that nothing above the execution seam learns where
    work runs — a :class:`~mcgyvr.route.Machine` names nothing, and a printed
    entry says a family and a rung, which are the operator's own words.
    """

    family: Family
    rung: str
    machine: Machine = field(repr=False, compare=False)
    capacity: Capacity = field(repr=False, compare=False)

    def release(self) -> None:
        """Give the reservation back. Never raises, so a ``finally`` is safe.

        :meth:`~mcgyvr.route.Machine.release` is floored rather than checked, so
        this is callable on a path where something has already gone wrong —
        which is the only kind of path that reaches it, since the ordinary one
        hands the reservation to a climb instead.

        Given back on ``rung`` and not on the machine alone, because that is the
        queue it was taken on: a rung with a width of its own is a server
        process of its own (#23), and a reservation returned to the rig would
        leave that rung reading as busy for the rest of the run while the rig
        read as one dispatch emptier than it is.
        """
        self.machine.release(self.capacity, self.rung)


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
        """Whether there is anything here to climb.

        The same question :meth:`__len__` answers, and therefore the same
        answer. It was ``any(self.plans)`` — plan truthiness — until the floor
        was bound to a program: an ascent whose only non-empty plan holds a
        :class:`~mcgyvr.deterministic.ToolStep` was then true and empty at once,
        so ``if route:`` entered a climb that ``for p in route.runnable``
        immediately found nothing in. Python asks ``__bool__`` first and falls
        back to ``__len__``, which makes disagreeing versions of one question
        the sharpest kind of trap: the guard passes and the loop does not run.

        "This ascent contains work" is a different and true statement about such
        an ascent, and :attr:`plans` is where it is asked. It is not what a
        caller reaching for truthiness means.
        """
        return bool(self.runnable)

    def __len__(self) -> int:
        return len(self.runnable)

    @property
    def families(self) -> tuple[Family, ...]:
        """Every family in the ascent, floor first — including the empty ones."""
        return tuple(p.family for p in self.plans)

    @property
    def runnable(self) -> tuple[Plan, ...]:
        """The families that actually offer a rung.

        A rung, not a step: since #81 bound the floor, the cheapest family can
        hold a program, and a program is something to *run* and nothing to
        *climb*. Counting it here would tell a caller the ladder can walk a
        family whose only step :func:`~mcgyvr.route.climb` refuses.
        """
        return tuple(p for p in self.plans if p.climbable)

    @property
    def rungs(self) -> tuple[str, ...]:
        return tuple(name for p in self.plans for name in p.rungs)

    @property
    def ladder_budget(self) -> int:
        """The most attempts the configured rungs could spend between them.

        Summed over what each family can *climb*, so the floor's one program
        does not appear: it is spent by :mod:`mcgyvr.deterministic` and never by
        :func:`escalate`, and counting it would give the climb one attempt of
        headroom past the end of the operator's ladder — the ceiling would stop
        a task later than the config it was read from says.

        Not the figure ``mcgyvr pool`` prints, and it never could be. That one
        sums each rung's configured ``attempts`` with no contract in hand; every
        step counted here has already been through
        :func:`~mcgyvr.route.attempts_for`, which takes the lower of the rung's
        budget and the contract's own ``limits.attempts``. The printed number is
        the ladder's ceiling for any task; this is the ceiling for *this* task,
        and where a contract asks for fewer attempts than the ladder offers the
        two differ by design. This is the one that is enforced.
        """
        return sum(p.climb_budget for p in self.plans)

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

        Both halves are read per rung, and they have to be the same half each
        time: a rung with a width of its own is a server process of its own, so
        its load is the load of that process and its width is that process's
        width. Comparing one rung's load against another's width — the rig's
        load against a rung's width, as this did while load was read per source
        — reports a busy rig's idle narrow rung as full and spends money
        climbing past it.

        The load is read here rather than stored when the ascent was built,
        because a reading taken before the batch started is only true until the
        batch starts; this is the closest a caller can get to the moment it acts.

        **One snapshot, and not a commitment.** The whole walk reads its loads
        inside :meth:`~mcgyvr.capacity.Capacity.deciding`, so the rungs are
        priced against one another as they stood at a single moment; without it
        a cheap rung could be read before another thread reserved it and a dear
        one after, and the answer would be "cheapest free" for a ladder that was
        never in that state. Nothing slow runs in there — these are counter
        reads — which is the condition ``deciding`` sets on its borrowers.

        **Reading is all this does.** Naming a rung reserves nothing, so between
        this answer and the moment anything acts on it another thread may take
        the slot it named. That is why it is not the seam a batch enters on:
        :meth:`reserve_entry` answers the same question and *commits* to the
        answer inside the same section, and :func:`_idle_entry` uses that one.
        This one stays because "which rung would an idle ladder offer" is a
        question worth being able to ask without buying anything — ``mcgyvr
        pool`` asks it, and so does every test that pins the rule.
        """
        found = self._entry_rung(reserve=False)
        return None if found is None else found[1]

    def reserve_entry(self) -> Entry | None:
        """The raised entry ``idle`` decides on, with its rung already reserved.

        The same question :attr:`next_free_rung` answers, made into a decision:
        the loads are priced against one another and the rung that wins is
        reserved before the lock is given up, so what comes back is a rung this
        caller *holds* rather than a rung it saw free a moment ago. That is the
        whole of the fix for the window :func:`_idle_entry` used to describe —
        without it every member of a batch reads the same one free api slot and
        each pays for it, which is a funnel priced in money.

        ``None`` whenever there is nothing to raise: every case
        :attr:`next_free_rung` answers ``None`` for, and the case where the
        cheapest free rung is already in the floor family. **Nothing is reserved
        on any of those paths**, which matters as much as the reservation does:
        a reservation taken and given back a moment later would show a free
        machine as busy to whichever peer read it in between, and that peer
        would climb into a dearer family for a slot nobody had taken — the
        phantom-reservation failure, which is the same defect wearing the other
        mask.

        The reservation returned is the caller's until it is handed to
        :func:`~mcgyvr.route.climb` as ``claimed``, which releases it exactly
        once. A caller that does not reach a climb must release it itself;
        :func:`escalate` does that in a ``finally``.
        """
        found = self._entry_rung(reserve=True)
        if found is None:
            return None
        family, rung, machine = found
        if not self._raises(family):
            return None
        # `_entry_rung` answers None without a capacity, so there is one here,
        # and it is the one the reservation was taken against.
        assert self.capacity is not None
        return Entry(family=family, rung=rung, machine=machine, capacity=self.capacity)

    def _raises(self, family: Family) -> bool:
        """Whether entering ``family`` is a raise rather than the floor itself.

        The one place the comparison is written. Entering the floor family is
        what would have happened anyway, so it is not a decision and buys
        nothing — and it is also the case that must not reserve.
        """
        return family.rank > self.floor.rank

    def _entry_rung(self, *, reserve: bool) -> tuple[Family, str, Machine] | None:
        """The cheapest free rung at or above the floor, optionally claimed.

        One walk for both callers, because "cheapest rung with a free slot" is
        one question and answering it twice would be two rules to keep in step.
        The rules it walks by are :attr:`next_free_rung`'s and are stated there.

        ``reserve`` decides whether the answer is also a commitment. It is taken
        inside the same :meth:`~mcgyvr.capacity.Capacity.deciding` section the
        loads were read in, which is what makes the read and the claim one
        decision rather than a snapshot another thread can act on first — and it
        is taken through :meth:`~mcgyvr.route.Machine.claim`, so no source name
        crosses the seam here any more than it does anywhere else (#20).

        It is taken *only for a rung that raises the entry*, and never for one in
        the floor family. A reservation on the floor rung would be handed to
        nobody — entering the floor is not a decision, so there is nothing to
        hand it to — and giving it back a moment later, outside the lock, leaves
        a window in which a peer reads a free machine as busy and climbs into a
        dearer family for a slot that was never taken. The rung named is the
        same either way; only the commitment is conditional.

        The family is returned beside the rung because the walk already knows
        which plan it stopped in. Looking it up again afterwards would be a
        second answer to a question this loop had in hand, and the version of
        this code that did so had to raise for a name it could not find again.
        """
        if self.fanout is not Fanout.IDLE or self.capacity is None:
            return None
        with self.capacity.deciding():
            for each in self.plans:
                for step in each.climbable:
                    machine = step.machine
                    width = self.widths.get(step.rung.name)
                    load = (
                        None
                        if machine is None
                        else machine.load(self.capacity, step.rung.name)
                    )
                    if machine is None or width is None or load is None:
                        return None
                    if load < width:
                        if reserve and self._raises(each.family):
                            machine.claim(self.capacity, step.rung.name)
                        return each.family, step.rung.name, machine
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
    """How wide each rung's own server is, keyed by the rung rather than the machine.

    The static half of "has a free slot". A width is a property of how a backend
    was started, so :class:`~mcgyvr.capacity.Capacity` settles it once and this
    reads it once; only the load has to be read at the moment the question is
    asked.

    The rung's width and not its source's, because a tier may declare one and a
    rung that did is bounded by it. Reading the source's number for such a rung
    would price a free slot on the source's terms — sixteen where the rung will
    admit four, or four where it will admit sixteen — and ``idle`` would either
    queue on a full rung or climb past an empty one. A rung that declares
    nothing is answered with its source's width, which is what
    :meth:`~mcgyvr.capacity.Capacity.limit` falls back to and what
    ``sources.*.max_parallel`` has always meant.

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
        tier.name: capacity.limit(tier.source, tier.name)
        for tier in config.ladder.tiers
        if tier.source in limits
    }


# --- terminal outcomes -----------------------------------------------------


@dataclass(frozen=True)
class Delivered:
    """A task that ended with a change accepted, and what that rests on.

    The accepted bytes are reached through ``judgement.accepted``, which is a
    binding minted from the tree its gate read. There is no bare content field:
    one used to sit here and it was the port's only route for un-gated bytes
    into a repository.
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


class _AttemptError(Exception):
    """An attempt function raised instead of returning a judgement.

    :func:`~mcgyvr.route.climb` lets a raising attempt propagate on purpose —
    an exception is the absence of a verdict, and swallowing it there would
    misreport "this family cannot do the work". This is the seam that turns it
    into a verdict of its own: the rung being driven and the exception are
    carried together so :func:`escalate` can name them in the terminal
    :attr:`Outcome.ERROR` rather than let them escape to a caller that cannot
    tell a dead socket from a bug it owns.

    **It carries no draw, and that is the answer rather than an omission.** An
    attempt that asks its rung for several candidates (``breadth.draws``) makes
    one dispatch per draw, and the exception says nothing about which of them
    was in flight — or whether any had been sent at all, since a sandbox reset,
    a bind or a prompt that will not build all raise before the first one. The
    attempt function is the only party that knows, and it has no way to say it
    through a `raise`. So this seam records the rung and the attempt, which it
    does know, and :func:`escalate` marks the history entry as naming no
    dispatch (``draws=0``) rather than defaulting to the first.
    """

    def __init__(self, rung: str, attempt: int, cause: BaseException) -> None:
        super().__init__(rung)
        self.rung = rung
        self.attempt = attempt
        self.cause = cause


def escalate(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    attempt: Callable[[Try], Judgement],
    *,
    capacity: Capacity | None = None,
    floor: Family | None = None,
) -> Delivered | Halted:
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

    An attempt that raises is not a verdict and is not let escape the seam.
    :func:`~mcgyvr.route.climb` refuses to catch it for exactly that reason;
    here it is caught and recorded as :attr:`Outcome.ERROR` naming the rung,
    so a caller can hand it to :func:`disposition` instead of a traceback.

    Under ``ladder.fanout: idle`` the climb *enters* at the family of the
    cheapest rung with a free slot rather than at the contract's floor, which is
    the whole of what that mode decides across families and the reason it is
    computed here rather than in :mod:`mcgyvr.route`. It is expressed by
    building the ascent a second time with that family as its ``floor``, so a
    raised entry is the same shape as any other floor: the cheaper families are
    *absent* from the ascent rather than skipped inside it, which is what keeps
    "each family is entered at most once" a fact about the shape. Choosing an
    entry family is not reordering a plan — the rungs within whichever family is
    entered stay in the price order :func:`~mcgyvr.route.plan` put them in, and
    which of them a climb starts on is still :func:`~mcgyvr.route.climb`'s.
    See :func:`_idle_entry` for why the raised entry costs no escalation.

    **The entry rung is reserved before it is entered, and handed down.**
    :func:`_idle_entry` claims the rung it names inside the section that priced
    it, and that reservation is passed to the entry family's climb as
    ``claimed`` — so the read and the commitment are one decision, and a batch
    cannot sell one free api slot to every member at once. The reservation is
    given back exactly once: by :func:`~mcgyvr.route.climb`, when that rung is
    done with, on the path that reaches a climb — and by the ``finally`` here on
    every path that does not, because a reservation nobody gives back narrows a
    source for the life of the process.
    """
    route = ascent(config, pool, contract, floor=floor, capacity=capacity)
    entry = _idle_entry(route)
    claimed: str | None = None
    if entry is not None:
        try:
            route = ascent(
                config, pool, contract, floor=entry.family, capacity=capacity
            )
            claimed = _handed_down(route, entry)
        finally:
            # Everything between the reservation and the climb that takes it
            # over: an ascent that raised while being rebuilt, and an ascent
            # rebuilt without the rung the reservation is for. `claimed` is
            # cleared the moment a climb takes it, so it doubles as "still ours".
            if claimed is None:
                entry.release()
    ceiling = route.ceiling
    budget = route.budget

    spent_rungs: list[str] = []
    attempts_spent = 0
    stopped_by: Outcome | None = None
    accepted_judgement: Judgement | None = None
    history: list[Attempted] = []
    entered: list[Family] = []
    # The judged attempts of the climb in progress, kept here as they are
    # judged. `climb` keeps the same list and returns it — unless an attempt
    # raises, when the exception ends the call and the list goes with it. The
    # attempts before the raise dispatched, wrote journal rows and produced
    # findings; a history that dropped them would count them in
    # `attempts_spent` and list them nowhere.
    judged: list[Attempted] = []

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

    def observed(this: Try) -> Result:
        nonlocal attempts_spent, accepted_judgement
        try:
            judgement = attempt(this)
        except Exception as exc:
            # An exception is not a verdict. `climb` lets a raising attempt
            # propagate so it is not misread as "this family cannot do the
            # work"; here is the seam that turns it into a terminal outcome of
            # its own, carrying the rung so the operator knows which tier to
            # fix.
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

    try:
        for each in route.plans:
            if not each.climbable:
                # Not entered, and its reason is kept for the halt detail. The
                # test is `climbable` rather than truthiness because the two
                # stopped agreeing when #81 bound the floor: a deterministic
                # family holding a program is non-empty and still has nothing to
                # climb, so a truthiness guard entered it and `climb` raised
                # `RouteError` — which is not a `RunnerError`, so the mission
                # loop did not catch it and the run ended with earlier contracts
                # already committed.
                continue
            # The reserved rung is on the entry family's plan and on no other,
            # and the entry family is this ascent's floor — so it is handed to
            # the first climb there is, and every rung after it claims its own.
            taking = claimed if claimed in each.rungs else None
            if taking is not None:
                claimed = None
            judged.clear()
            try:
                result = climb(
                    each, observed, capacity=capacity, permit=permit, claimed=taking
                )
            except _AttemptError as raised:
                detail = (
                    f"rung {raised.rung!r} raised "
                    f"{type(raised.cause).__name__}: {raised.cause}"
                )
                # Every attempt judged before the raise, then the raise. The
                # judged ones dispatched and were counted; the raising one is
                # in the history too, because a record that omitted it would
                # show a climb that never touched the rung it died on.
                history.extend(judged)
                history.append(
                    Attempted(
                        rung=raised.rung,
                        attempt=raised.attempt,
                        verdict=Verdict.FAILED,
                        detail=detail,
                        raised=True,
                        # A raise is not a draw, and this entry names none.
                        # `draw`/`draws` say which dispatch of an attempt a
                        # verdict is about and how many were paid for, and both
                        # are facts the exception did not carry: it arrived in
                        # place of a judgement, and nothing here can tell a rung
                        # that died on its second draw from one that died before
                        # it sent the first. The dataclass defaults said "draw 0
                        # of 1", which is not "unknown" but a claim, and the
                        # caller that corrects the journal from this history
                        # believed it — under `breadth.draws > 1` it wrote the
                        # error onto the row of a dispatch that had answered and
                        # left the one that raised uncorrected. Zero draws says
                        # what is true, and the caller holding the rows is the
                        # one that can name the dispatch.
                        draws=0,
                    )
                )
                return Halted(
                    outcome=Outcome.ERROR,
                    entered=tuple(entered),
                    history=tuple(history),
                    attempts_spent=attempts_spent,
                    escalations=max(0, len(spent_rungs) - 1),
                    detail=detail,
                )
            history.extend(result.history)
            if result.history:
                entered.append(each.family)
            if isinstance(result, Accepted):
                assert accepted_judgement is not None  # set by `observed` on PASSED
                return Delivered(
                    family=result.family,
                    rung=result.rung,
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
    finally:
        # Unreachable by the argument above, and kept anyway: the cost of that
        # argument being wrong one day is not a wrong answer, it is a source
        # that reads as busy for the rest of the process.
        if entry is not None and claimed is not None:
            entry.release()

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


def _idle_entry(route: Ascent) -> Entry | None:
    """Which family ``idle`` enters when that is dearer than the floor, and the
    rung it has reserved there.

    ``None`` under every other mode, without a capacity, and whenever the
    cheapest free rung is already in the floor family — three cases in which
    there is nothing to raise, the ascent stands as built, and **nothing is
    reserved**. :meth:`Ascent.reserve_entry` is the single answer this reads;
    the reasons it declines to give one are its own and are not restated here.

    **The read and the commitment are one decision.** They were not, and the
    gap was this function's whole risk: naming a rung reserved nothing, while
    the reservation for the rung a climb takes was made much later inside
    :func:`~mcgyvr.route.climb`'s own
    :meth:`~mcgyvr.capacity.Capacity.deciding` section. In between, every member
    of a batch reaching this point saw the same one free api slot, every one of
    them raised its entry into the priced family, and they then queued on it —
    *paying* for a rung they could have waited out locally for nothing. It was
    the funnel :mod:`mcgyvr.route` describes as narrowed to microseconds and not
    closed, with money rather than throughput as the cost.

    It is closed by reserving the named rung inside the very section that priced
    it, and handing that reservation down: :func:`escalate` passes ``rung`` to
    the entry family's :func:`~mcgyvr.route.climb` as ``claimed``, and that
    climb takes it *without claiming it again*, so the source counts one attempt
    for one dispatch and ``climb``'s existing ``finally`` gives it back exactly
    once. The two failures the older reading feared are the two this shape
    rules out: a double count, because the claim is skipped for exactly that
    rung, and a phantom reservation, because nothing is reserved on any path
    that does not raise the entry.

    **What it does not do is shorten the walk.** An earlier note here proposed
    that ``climb`` drop the rungs cheaper than the claimed one. That is the
    defect ``869bf2a1`` removed, in the other module: a family short of the
    rungs it was dropped runs out of ladder while still holding escalation
    budget nothing has paid for, and that leftover move funds a dispatch into a
    dearer family — it is how ``full`` came to buy an api call the default
    refuses. Fan-out is a scheduling decision and not a spend decision, so the
    claimed rung is popped out of the middle of the walk and every other rung
    stays exactly where it was.

    **A leaked reservation is forever**, so the obligation :class:`Entry`
    carries is discharged on every path: by the climb that takes it over, and
    otherwise by :func:`escalate`'s ``finally``.

    **A raised entry is free, and a climbed one is not.** An escalation is what
    a *failure* buys: ``budgets.max_escalations`` bounds how far work climbs
    after something could not do it, and the record that funds a move is a
    verdict. Entering high because everything cheaper was full is not that.
    Nothing was tried, nothing failed, and the rungs below were passed over
    rather than judged — so charging the entry would let a busy ladder spend a
    budget that only a failure is entitled to spend, and would silently halve
    the ladder of every contract whose floor family happened to be saturated
    when it started. A reservation is not a verdict either: reserving the entry
    rung records nothing about it and buys nothing on it, which is why the
    arithmetic below is untouched by the reservation.

    **The code path that keeps it free.** :func:`escalate` counts moves off
    ``spent_rungs``, which is appended to only in ``observed`` and only for a
    verdict that was not a decline — so it holds rungs that *ran*, never rungs
    that were reached. Raising the entry drops the cheaper families from the
    ascent entirely, so the first rung the climb reaches finds ``spent_rungs``
    empty: ``permit``'s ``moving`` is ``bool(spent_rungs)`` and is therefore
    False for it, and ``escalations`` is ``len(spent_rungs) - 1`` floored at
    zero, which is zero. Nothing has to remember not to charge it, because
    there is nothing in the count for it to be charged against. What the raised
    entry does *not* do is shorten the climb from there: :attr:`Ascent.rungs`
    now holds the entry family's rungs and everything above, so
    :attr:`Ascent.most_rungs` still offers ``max_escalations`` moves from the
    rung work actually starts on.

    The same rule read from the other side: a rung reached by escalation and the
    same rung reached under ``idle`` are one rung with two histories. Only the
    first is preceded by a failure, and only the first is charged.
    """
    return route.reserve_entry()


def _handed_down(route: Ascent, entry: Entry) -> str | None:
    """The rung to hand the entry family's climb, or ``None`` if it is not there.

    The ascent :func:`escalate` climbs is built a second time, with the entry
    family as its floor, and this asks the only question that matters about the
    rebuild: does the plan the climb will be given still offer the rung the
    reservation was taken for. It does, for every ascent built from the same
    config, pool and contract — :func:`ascent` is a function of those three, and
    the entry family's rungs do not depend on which floor was asked for.

    It is asked anyway because the answer decides who owes the release.
    :func:`~mcgyvr.route.climb` cannot give back a reservation for a rung its
    plan does not offer: a :class:`~mcgyvr.route.Machine` is built from the
    rungs of one family, so there is no handle there to release with, and #20's
    rule keeps the source name from being the alternative. ``None`` therefore
    means "still ours", and :func:`escalate` releases it rather than handing
    down a name that would be quietly ignored.
    """
    for each in route.plans:
        if each.family == entry.family:
            return entry.rung if entry.rung in each.rungs else None
    return None


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


# --- what to do next -------------------------------------------------------


@dataclass(frozen=True)
class Disposition:
    """Whether the work behind one outcome may be tried somewhere else, and why.

    Two fields, kept together because either alone is a trap. A bool with no
    reason tells an operator that the work stopped and not what would let it
    continue; prose with no bool is re-read and re-interpreted at every call
    site, which is the thing this axis exists to stop.
    """

    reassignable: bool
    detail: str


def disposition(outcome: Outcome) -> Disposition:
    """What ``outcome`` says about trying this work somewhere else.

    A match over the enum with :func:`~typing.assert_never` beneath it rather
    than a lookup table, so an eighth :class:`Outcome` is a type error where it
    is declared. A taxonomy with a hole in it is worse than no taxonomy: the
    hole is found by a caller, at runtime, on the one path nobody exercised.
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
                    "budgets.max_escalations with rungs of the ascent never "
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


def may_reassign(outcome: Outcome, budget_remaining: int) -> bool:
    """Whether to hand this work on, given the kind of ending and what is left.

    Two inputs, and both have to matter. Deciding on the budget alone is the
    rule this project already had, and it sends work a ladder has already shown
    it cannot do to a dearer family that cannot do it either — the bill is the
    only thing that changes. Deciding on the kind alone spends money nobody
    has: ``reassignable`` says the work *may* move, never that moving it is
    free.
    """
    return disposition(outcome).reassignable and budget_remaining > 0
