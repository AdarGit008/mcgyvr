"""Escalation: which family a task climbs to next, what stops it, and what the
acceptance actually rests on.

:mod:`mcgyvr.route` climbs the rungs of one family and names the moment that
family is spent. This module is what happens next. It owns four rules that
:mod:`~mcgyvr.route` deliberately refused, because each of them needs to see
more than one family at once:

**Ascent is a rule, not a model call.** The families a task may enter are the
catalog's own, from the contract's floor upward in declared rank order. They are
computed as a tuple of :class:`~mcgyvr.route.Plan` before anything is dispatched
— :func:`ascent` answers "which families, which rungs, how many attempts, and
what stops it" with no network and no model — so routing is reproducible and
diffable rather than merely deterministic. The same property :mod:`mcgyvr.route`
gives one family, over the whole climb.

**Ascent is monotonic, and structurally so.** :attr:`Ascent.plans` is built by
filtering the catalog's rank-ordered families once, so each family appears
exactly once and ranks strictly increase. Ping-pong between a local rung and an
API rung is not prevented by a check that could be forgotten; there is nowhere
in the shape for it to happen. A floor is a floor in the same way: families
below it are absent from the ascent rather than skipped inside it.

**An idle ladder spills upward, and only when told to.** The policy key
``fanout`` is a knob and ``none`` is its default: every contract of a batch
takes the cheapest rung of its floor family and queues there. Under ``idle``
:attr:`Ascent.next_free_rung` names the cheapest rung *at or above the floor*
with a free slot instead, which is a choice that can cross families — when every
local rung is full the cheapest free rung is a priced api one, so a saturated
local ladder buys capacity rather than waits. That is the whole reason the mode
is opt-in, and it is why the choice is here and not in :mod:`mcgyvr.route`:
the boundary is that nothing there looks past the family it was asked about,
and this is already the view "every family this contract may climb, from its
floor upward". ``full`` spreads *within* a family and stays
:func:`~mcgyvr.route.climb`'s; this module adds nothing to it.

**And the name is acted on, because a mode that changes no dispatch is a false
entry in the published reference.** :func:`escalate` *enters* at the family of
:attr:`Ascent.next_free_rung` — it rebuilds the ascent with that family as its
floor, which is choosing where to begin and not reordering anything, since the
rungs of whichever family is entered are still :func:`~mcgyvr.route.plan`'s own
price order. Within that family the cheapest rung with a free slot is
:func:`~mcgyvr.route.climb`'s to take, under the same ``idle``, so the two seams
answer the two halves of one question and neither restates the other.

**A relief rung is ridden only when the rider's own rung is full, and is never
climbed to.** A relief rung (``relief.yaml``) is another person's unit, lent
through a hub; it may sit above the ceiling of the rider's own ladder or below
its floor, and what it is for is a shorter queue, not more capability. So it is
on no plan — :attr:`Ascent.relief` holds it beside them — and the one place it
is read is the walk ``idle`` already makes: once the first family that has rungs
is full by :meth:`~mcgyvr.capacity.Capacity.judge`'s one definition, a free
relief rung is the entry, ahead of the next family up and so ahead of a priced
api rung. No escalation reaches it, because no plan holds it, and the ceilings
and budgets are the ladder's alone. :func:`escalate` rides it before the climb;
a ride that is not accepted — the hub cannot take the request now, which the
driver reads as a full rung, or the answer failed or the dispatch raised — is
passed over as if it had been full, charged to neither ceiling, and the entry
is decided again without the relief rungs.

**Busy is not a verdict, and the record is the difference.** A rung that
:attr:`~Ascent.next_free_rung` passed over was not tried: it produced no
verdict, spent no attempt and funded no escalation, because
:meth:`~mcgyvr.capacity.Capacity.hold` blocks rather than raising and a queue is
not a failure. So an api rung reached under ``idle`` and an api rung reached by
escalation are the same rung with two different histories — one was chosen
before anything ran, the other was climbed to after something failed — and only
the second says the local family could not do the work. That difference is what
keeps a raised entry off ``max_escalations``: the count is over rungs
that *ran*, so a rung entered at costs nothing until it produces a verdict, and
a contract whose floor family was saturated at the moment it started still has
its whole escalation budget to climb with. :func:`_idle_entry` is where that is
written down.

**Two ceilings bound the task, and they bound different things.**
``max_escalations`` bounds how far the work *climbs* — a cheap rung that fails
and then escalates costs more than starting higher, so the ceiling is on moves,
not on tries. ``max_attempts`` bounds what the task *spends* in total. Neither
charges a decline: a rung that steps aside consumed no attempt, and
charging the move to it would let a ladder of rungs that never ran exhaust a
budget. Unset, ``max_attempts`` is the ladder's own budget, which is a real
bound and is printed by ``mcgyvr pool`` — the field exists so that raising a
rung's ``attempts`` cannot multiply into a task nobody bounded, not to introduce
a number this project has no measurement for.

**A model's output is never accepted on a policy written for a tool.** A
contract's ``verification.policy`` of ``gate_only`` is the whole acceptance bar
in the deterministic family: a tool's output, checked by the gate, is what that
policy describes. The moment work leaves that family the policy is *upgraded* to
require a fresh-context verifier, whatever the contract declared. What the
install can then do about it is a capability question, not a policy one, and
:class:`Assurance` is where the difference is recorded: ``VERIFIED`` is only ever
reached by a verifier that ran and agreed, and an install with no verifier
reaches ``UNVERIFIED`` — accepted on the gate, labelled as exactly that. What
closes the path here is that no acceptance can be *called* verified without
one, and that an available verifier is never skipped.

**Ordering is enforced rather than assumed.** :func:`judge` reads the gate first
and returns before the verifier is so much as named when the gate rejected, so a
deterministically-rejected change costs zero verifier spend. For the same reason
a retry carries :class:`RetryNotes` — the checks that *failed* and nothing else.
Re-reading the passing checks is spend that carries no information, and neither
an observation (a finding the gate deliberately did not reject on) nor an
environment issue (a tool that was not installed) is something the worker did or
can fix.

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
nothing else.

**What is deliberately not here.** Parsing a model's reply into a
:class:`Review` and reviewing the applied diff in fresh context are
:mod:`mcgyvr.verify`'s; this module fixes only *when* a review is asked for and
what follows from each answer. :attr:`Judgement.reviewer_failed` keeps a
reviewer-side failure distinguishable, and it is never charged to the builder:
an unusable review leaves the gate's acceptance standing and labelled
``UNVERIFIED``, exactly as an install with no reviewer is, because what failed
was the review and not the change. It is never ``VERIFIED``. Diagnosing a
ladder that declares its families out of rank order is not here either: the
ascent's order is the catalog's, so an interleaved ladder executes in an order
the config file does not show.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
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
    family_of,
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

    Every terminal outcome is machine-readable rather than prose,
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
    agreed. ``UNVERIFIED`` is a model's output that passed the gate with no
    verdict to satisfy the upgrade — no independent reviewer, review switched
    off, or a reviewer that produced nothing usable — accepted, and labelled.
    """

    DETERMINISTIC = "deterministic"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class Opinion(StrEnum):
    """What a verifier came to.

    Three members, and the third is why it is an enum: a reply that could not be
    read is not a refusal and is certainly not an approval. :mod:`mcgyvr.verify`
    owns turning a model's text into one of these — anchored parsing, no
    substring search, failing closed — and this module owns only what each one
    means for the attempt.
    """

    AGREED = "agreed"
    REFUSED = "refused"
    UNUSABLE = "unusable"


@dataclass(frozen=True)
class Review:
    """One verifier's answer, built through a named constructor.

    Never assembled from a positional boolean, for the reason
    :mod:`mcgyvr.verify` parses strictly: a reply beginning "Cannot approve"
    read as an approval is the failure this whole path is shaped around, and a
    bare ``True`` is the same mistake one layer down.
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
    ran. ``acceptance`` is an orchestrator-only contract field and a note
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

    There is deliberately no second field: a value the attempt function merely
    happened to be holding is bound to no verdict.
    """

    verdict: Verdict
    accepted: BoundContent | None = None
    assurance: Assurance | None = None
    policy: str = GATE_ONLY
    upgraded: bool = False
    reviewer_failed: bool = False
    retry: RetryNotes | None = None
    detail: str = ""
    #: Which draw the verdict is about, how many were asked for, and how many
    #: left a journal row; see :class:`~mcgyvr.route.Result`.
    draw: int = 0
    draws: int = 1
    rows: int = 1

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
            rows=self.rows,
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
    absent: str = "",
) -> Judgement:
    """Turn a gate run — and, only if it passed, a verifier — into a judgement.

    The ordering is the point and it is structural: ``verifier`` is not
    referenced at all on the rejected path, so a gate failure cannot cost
    verifier spend however the caller supplied one. The gate runs before any
    model is asked for an opinion; this is where that is held.

    ``absent`` is why there is no ``verifier``, in the caller's words, and it
    goes into the judgement's detail: an unverified acceptance that cannot say
    why is the silent kind this label exists to end.
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
        why = absent or "this install has none"
        return Judgement(
            verdict=Verdict.PASSED,
            assurance=Assurance.UNVERIFIED,
            policy=policy,
            upgraded=upgraded,
            detail=(
                f"accepted on the deterministic gate alone: work in the "
                f"{family.name!r} family requires a fresh-context verifier and "
                f"{why}, so the acceptance is labelled unverified rather than "
                f"verified."
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
            # The gate passed, so none of its findings are repeated: the
            # refusal is what failed, and it is what a retry has to act on.
            # What the same reviewer answered to the gate's typed checks goes
            # with it — they are observations elsewhere, but here they are the
            # only reasons a typed refusal has, and they are already paid for.
            retry=_refusal_notes(review, gate),
            detail=f"the verifier refused the change: {review.detail}",
        )
    # The reviewer's fault, never the builder's: the gate accepted this change
    # and nothing has since said otherwise. Failing it would spend the
    # builder's attempt — and climb the ladder — over a review that never
    # happened, so the acceptance stands on the gate and says exactly that.
    return Judgement(
        verdict=Verdict.PASSED,
        assurance=Assurance.UNVERIFIED,
        policy=policy,
        upgraded=upgraded,
        reviewer_failed=True,
        detail=(
            f"accepted on the deterministic gate alone: the verifier produced "
            f"no usable verdict ({review.detail}), so the acceptance is "
            f"labelled unverified rather than verified."
        ),
    )


def _refusal_notes(review: Review, gate: GateResult) -> RetryNotes:
    """What a retry is told after the verifier refused an accepted change.

    The refusal itself, and then the reviewer's answers to the gate's typed
    checks (:attr:`~mcgyvr.gate.GateResult.jev`). Those are the per-file
    reasons a typed verdict does not carry, asked of the same reviewer over the
    same change, so the builder is told what was found without a second
    request being spent to find out.
    """
    reasons = () if gate.jev is None else (*gate.jev.findings, *gate.jev.observations)
    return RetryNotes(
        checks=("verifier", *(("jev",) if reasons else ())),
        lines=(
            f"verifier: {review.detail}",
            *(finding.for_model() for finding in reasons),
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
        raw = config.get("max_attempts")
        return cls(
            escalations=int(config.get("max_escalations", 1)),
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
    answer, and the rule is that nothing above the execution seam learns where
    work runs — a :class:`~mcgyvr.route.Machine` names nothing, and a printed
    entry says a family and a rung, which are the operator's own words.
    """

    family: Family
    rung: str
    machine: Machine = field(repr=False, compare=False)
    capacity: Capacity = field(repr=False, compare=False)
    #: A relief rung, ridden before the climb rather than entered: ``family``
    #: is then the family whose rungs were full, the one it stands in for, and
    #: ``rung`` is on no plan of the ascent.
    relief: bool = False

    def release(self) -> None:
        """Give the reservation back. Never raises, so a ``finally`` is safe.

        :meth:`~mcgyvr.route.Machine.release` is floored rather than checked, so
        this is callable on a path where something has already gone wrong —
        which is the only kind of path that reaches it, since the ordinary one
        hands the reservation to a climb instead.

        Given back on ``rung``, the same name
        :meth:`~mcgyvr.route.Machine.claim` was given, so the reservation is
        returned to the queue it was taken on.
        """
        self.machine.release(self.capacity, self.rung)


@dataclass(frozen=True)
class _Found:
    """Where the ``idle`` walk stopped: the family, the rung and its machine.

    ``relief`` marks a relief rung, which is on no plan; ``family`` is then the
    family whose rungs were full.
    """

    family: Family
    rung: str
    machine: Machine
    relief: bool = False


@dataclass(frozen=True)
class Ascent:
    """Every family a task may enter, in order, with what bounds the climb.

    Inspectable before anything is spent, which is the property
    :mod:`mcgyvr.route` gives one family and this extends to the whole climb:
    the families, their rungs, the attempts each is allowed and the two ceilings
    are all decided from the config, the pool and the contract alone.

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
    of comparison; the families, rungs, attempts and ceilings *are* the decision.

    ``relief`` is the relief rungs, one step each, in the order the hub listed
    them, and deliberately not a plan: nothing that walks :attr:`plans` — the
    climb, the budgets, the escalation ceiling — meets one. Only the ``idle``
    walk reads them (:meth:`_entry_rung`).
    """

    floor: Family
    plans: tuple[Plan, ...]
    ceiling: Ceiling
    fanout: Fanout = Fanout.NONE
    capacity: Capacity | None = field(default=None, repr=False, compare=False)
    widths: Mapping[str, int] = field(default_factory=dict, repr=False, compare=False)
    relief: tuple[Step, ...] = ()

    def __bool__(self) -> bool:
        """Whether there is anything here to climb.

        The same question :meth:`__len__` answers, and therefore the same
        answer. Plan truthiness would not do: an ascent whose only non-empty
        plan holds a :class:`~mcgyvr.deterministic.ToolStep` has work and
        nothing to climb, and Python asks ``__bool__`` first and falls back to
        ``__len__``, so disagreeing versions of one question let the guard pass
        while the loop does not run.

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

        A rung, not a step: the cheapest family can hold a program, and a
        program is something to *run* and nothing to *climb*. Counting it here
        would tell a caller the ladder can walk a family whose only step
        :func:`~mcgyvr.route.climb` refuses.
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

        This is the whole of what ``fanout: idle`` decides. The floor
        bounds it and nothing else does: when every cheaper rung is full this
        names a priced api rung rather than wait, which is a spend decision the
        knob makes deliberately and the reason it is opt-in.

        **Never below the floor, structurally.** :attr:`plans` holds only
        families at or above it, so a cheaper rung is not skipped here — there
        is nowhere in the shape for it to be considered, however idle it is.
        Load may not lower a floor.

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

        Both halves are read for the same rung: its load from its
        :class:`~mcgyvr.route.Machine`, its width from :attr:`widths`.
        Comparing one rung's load against another's width reports an idle
        narrow rung as full and spends money climbing past it.

        **A relief rung comes after the rider's own.** Once the first family
        that has rungs is walked and every rung of it is full, the relief rungs
        are walked, in the hub's order, before any family above it: a free one
        is the shortest wait on offer and costs no step of the ladder. They are
        walked once and only there, so a free rung of the rider's own always
        wins, and they are judged full by the same two counts.

        **Free is free by both counts.** A rung is full when this batch's load
        is at its width *or* its server's own busy count is
        (:meth:`~mcgyvr.capacity.Capacity.judge`, the one definition the ladder
        manager reads too): another client's work fills a rung this process's
        counters cannot see. A server that cannot be read leaves the load to
        decide alone. The servers are read before the snapshot below, because
        a read of a machine is not a counter read.

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
        return None if found is None else found.rung

    def reserve_entry(self, *, relief: bool = True) -> Entry | None:
        """The raised entry ``idle`` decides on, with its rung already reserved.

        A free relief rung is an entry too (:attr:`Entry.relief`), and is
        reserved though it raises no family: it is ridden, and a ride holds the
        slot it was chosen for. ``relief=False`` decides as though every relief
        rung were full, which is what :func:`escalate` asks once a ride could
        not go.

        The same question :attr:`next_free_rung` answers, made into a decision:
        the loads are priced against one another and the rung that wins is
        reserved before the lock is given up, so what comes back is a rung this
        caller *holds* rather than a rung it saw free a moment ago. Without it
        every member of a batch reads the same one free api slot and each pays
        for it, which is a funnel priced in money.

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
        found = self._entry_rung(reserve=True, relief=relief)
        if found is None:
            return None
        if not found.relief and not self._raises(found.family):
            return None
        # `_entry_rung` answers None without a capacity, so there is one here,
        # and it is the one the reservation was taken against.
        assert self.capacity is not None
        return Entry(
            family=found.family,
            rung=found.rung,
            machine=found.machine,
            capacity=self.capacity,
            relief=found.relief,
        )

    def _raises(self, family: Family) -> bool:
        """Whether entering ``family`` is a raise rather than the floor itself.

        The one place the comparison is written. Entering the floor family is
        what would have happened anyway, so it is not a decision and buys
        nothing — and it is also the case that must not reserve.
        """
        return family.rank > self.floor.rank

    def _entry_rung(self, *, reserve: bool, relief: bool = True) -> _Found | None:
        """The cheapest free rung at or above the floor, optionally claimed.

        One walk for both callers, because "cheapest rung with a free slot" is
        one question and answering it twice would be two rules to keep in step.
        The rules it walks by are :attr:`next_free_rung`'s and are stated there.

        ``reserve`` decides whether the answer is also a commitment. It is taken
        inside the same :meth:`~mcgyvr.capacity.Capacity.deciding` section the
        loads were read in, which is what makes the read and the claim one
        decision rather than a snapshot another thread can act on first — and it
        is taken through :meth:`~mcgyvr.route.Machine.claim`, so no source name
        crosses the seam here any more than it does anywhere else.

        It is taken *only for a rung that raises the entry*, and never for one in
        the floor family. A reservation on the floor rung would be handed to
        nobody — entering the floor is not a decision, so there is nothing to
        hand it to — and giving it back a moment later, outside the lock, leaves
        a window in which a peer reads a free machine as busy and climbs into a
        dearer family for a slot that was never taken. The rung named is the
        same either way; only the commitment is conditional.

        The family is returned beside the rung because the walk already knows
        which plan it stopped in. Looking it up again afterwards would be a
        second answer to a question this loop had in hand. For a relief rung it
        is the family whose rungs were full, and a relief rung is always
        reserved when ``reserve`` is asked: it is ridden, never "the floor".

        ``relief=False`` walks as though no relief rung were there.
        """
        capacity = self.capacity
        if self.fanout is not Fanout.IDLE or capacity is None:
            return None
        riding = self.relief if relief else ()
        # Each server's own busy count, read before the decision is taken: it is
        # a read of a machine, and nothing slow runs inside `deciding`.
        servers = {
            step.rung.name: step.machine.server(capacity)
            for step in (*(s for p in self.plans for s in p.climbable), *riding)
            if step.machine is not None
        }

        def full(step: Step) -> bool | None:
            # Free by both counts (Capacity.judge): this batch's own load, and
            # the server's busy count, which sees the clients this process does
            # not. `None` is a load that cannot be read.
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
                # The rider's own family is full: the relief rungs, once.
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

    The relief rungs the pool offers ride along as :attr:`Ascent.relief`, one
    attempt each: a ride is an entry, asked once, and what follows it is the
    rider's own ladder.

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
        relief=tuple(
            Step(rung=rung, attempts=1, machine=Machine(rung.name))
            for rung in pool.relief
        ),
    )


def _widths(config: Config, capacity: Capacity | None) -> Mapping[str, int]:
    """How wide each rung's own server is, keyed by the rung rather than the machine.

    The static half of "has a free slot". A width is a property of how a backend
    was started, so :class:`~mcgyvr.capacity.Capacity` settles it once and this
    reads it once; only the load has to be read at the moment the question is
    asked.

    Each ladder name is a unit's name, and its width is
    :meth:`~mcgyvr.capacity.Capacity.limit`'s answer for that unit: the declared
    ``units.*.width``, or a wider one a probe confirmed. A relief rung's is the
    width the hub gave it.

    Asking :class:`~mcgyvr.route.Machine` how busy it is stays the one way load
    is read.

    A rung this capacity does not bound is absent rather than given
    a guessed width, because an unknown width is not a free slot and
    :attr:`Ascent.next_free_rung` must be able to tell the two apart.
    """
    if capacity is None:
        return {}
    limits = capacity.limits
    return {
        name: capacity.limit(name)
        for name in (*config.ladder.names, *config.relief)
        if name in limits
    }


# --- terminal outcomes -----------------------------------------------------


@dataclass(frozen=True)
class Delivered:
    """A task that ended with a change accepted, and what that rests on.

    The accepted bytes are reached through ``judgement.accepted``, which is a
    binding minted from the tree its gate read. There is no bare content field,
    so no un-gated bytes reach a repository through this record.
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

    A distinct type from :class:`Delivered` for the reason :mod:`mcgyvr.route`
    splits its two: a caller cannot reach for a result that was never produced,
    and the difference reads as a match on the answer rather than as a boolean
    whose polarity has to be remembered.
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
    """An attempt function's own account of the dispatch it died on.

    An attempt that asks its rung for several candidates (``breadth.draws``)
    makes one dispatch per draw and one journal row per dispatch. When it
    raises instead of judging, two facts decide which of those rows the failure
    belongs on, and *only the attempt function holds either*: how many of its
    draws reached a row, and which one it was in when it died. A plain `raise`
    carries neither, and every party downstream can do no better than infer.

    Inference is what this class exists to end. Counting the rows and taking
    the last one as "the dispatch in flight" is false twice over: for a raise
    *after* the draws (a verifier, a cleanup, a gate) it pins the failure on a
    dispatch that answered, and for a draw whose row was lost (an unwritable
    blob store, a torn last line) it shifts every draw down one and lands on
    the dispatch that answered.

    So the raise site says it, in three numbers that are three different
    quantities and never stand in for one another:

    ``draws`` is the breadth the attempt was configured for (``breadth.draws``)
    and means that on every entry there is, whatever the verdict.

    ``rows`` is how many of those draws left a journal row — ``0`` for a raise
    before the first dispatch — and it is what a caller correcting the journal
    iterates. It is never larger than ``draws``, and is smaller when the
    attempt died part-way or when the driver keeps no journal at all: it counts
    what was written, not what was drawn, and a driver holding no ``recording``
    writes nothing whatever it draws.

    ``draw`` is the row the attempt died *in*, or ``None`` when no row of its
    own is the culprit. ``None`` is not one case but two, and ``rows`` tells
    them apart without a third field: ``rows == 0`` is a raise before any
    dispatch, and ``rows > 0`` is a raise past draw ``rows - 1``, which had
    answered and left its row — the gate that judged it, the preparation of the
    next draw, or everything after the last one. That is what lets a reader be
    told where the attempt died rather than only that no dispatch owns it.

    A driver that raises anything else says nothing, and is read as having
    asked for nothing and written nothing.
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
        #: What actually went wrong. This class is an envelope, and the
        #: operator is told what died and not what carried the news.
        self.cause = cause
        #: The breadth the attempt was configured for.
        self.draws = draws
        #: How many of the attempt's draws left a journal row.
        self.rows = rows
        #: The row the attempt died in, or ``None`` for a raise no row owns.
        self.draw = draw


class _AttemptError(Exception):
    """An attempt function raised instead of returning a judgement.

    :func:`~mcgyvr.route.climb` lets a raising attempt propagate on purpose —
    an exception is the absence of a verdict, and swallowing it there would
    misreport "this family cannot do the work". This is the seam that turns it
    into a verdict of its own: the rung being driven and the exception are
    carried together so :func:`escalate` can name them in the terminal
    :attr:`Outcome.ERROR` rather than let them escape to a caller that cannot
    tell a dead socket from a bug it owns.

    **The draw comes from the raise site or not at all.** A driver that wrapped
    its failure in :class:`DispatchRaisedError` has stated the breadth it asked
    for, how many of its dispatches left a row and which one it died in; this
    seam unwraps it, so ``cause`` is the failure itself and the envelope is
    never what the operator reads. A driver that raised anything else has said
    nothing, and nothing is what is recorded: no breadth, no rows and no draw.
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
    """Climb the ascent until something is accepted or a rule ends the task.

    ``attempt`` is the caller's, as it is one level down: it assembles a
    prompt, dispatches, applies, gates and calls :func:`judge`. Keeping it a
    parameter is what lets every rule here be asserted without a model, a
    backend or a sandbox.

    ``wake_hook`` is the fleet-manager seam: a caller-supplied judgment that
    is consulted once, when a resident family is spent and the next family up
    is the api family. It names an asleep smarter rung to wake and route to
    before the api is entered, or ``None`` to escalate as today. It is asked
    only at that boundary, never before a family has actually been tried, and
    never while a cheaper move is still on the ladder — the judgment costs a
    model call, and paying it before a family is spent would charge every task
    for an answer the climb may not need. ``None`` disables the seam entirely,
    which is the ordinary install that did not ask for a fleet manager.

    ``presence`` is the seam a ladder manager reads pressure through: a
    caller-supplied context manager made per rung, which an attempt runs inside
    when — and only when — it *climbed*: it is on a rung other than the one the
    first attempt was spent on, reached after attempts were spent there. That is
    the evidence a manager wants, tasks that outgrew a cheaper rung and are now
    working on this one, and it is marked for the length of the attempt under the
    rung's name. An attempt on the first rung is not, a rung reached past a
    decline is not (a decline spends nothing, so nothing was tried below it), and
    a raised entry under ``fanout: idle`` is not: nothing failed to put work
    there, which is the same reason it is free of an escalation (see
    :func:`_idle_entry`). The marking is the caller's to make best-effort — a
    gauge must never fail the work it watches — and an exception raised by the
    attempt leaves the presence the way a verdict does. ``None`` is exactly the
    climb that has no such caller.

    Both ceilings are enforced through :func:`~mcgyvr.route.climb`'s ``permit``
    rather than by trimming the plan, because a decline costs nothing and a
    trimmed plan would have charged for it in advance. What is spent is counted
    as it happens: an attempt that was declined adds nothing to either count,
    so a ladder of rungs that all step aside is walked in full at no cost.

    An attempt that raises is not a verdict and is not let escape the seam.
    :func:`~mcgyvr.route.climb` refuses to catch it for exactly that reason;
    here it is caught and recorded as :attr:`Outcome.ERROR` naming the rung,
    so a caller can hand it to :func:`disposition` instead of a traceback.

    Under ``fanout: idle`` the climb *enters* at the family of the
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
    # A relief rung is ridden before the climb, not entered: its reservation is
    # held here until the ride's climb takes it over.
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
        # Reached after attempts were spent on a cheaper rung: a climb. Read
        # before the attempt, because the attempt is what adds to `spent_rungs`.
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
            # An exception is not a verdict. `climb` lets a raising attempt
            # propagate so it is not misread as "this family cannot do the
            # work"; here is the seam that turns it into a terminal outcome of
            # its own, carrying the rung so the operator knows which unit to
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

    def rode(this: Try) -> Result:
        """``observed`` for a ride, which spends nothing unless it is accepted.

        A ride is not a step of the ladder, so a ride that fails charges
        neither ceiling: it adds nothing to ``spent_rungs`` and nothing to
        ``attempts_spent``, and the request goes back to the rider's own
        ladder with its whole budget. Only an accepted ride is counted, as
        the attempt that did the work. A raise is still carried out as
        :class:`_AttemptError`, so it is recorded the way any raise is.
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

    def raised_to_halted(raised: _AttemptError) -> Halted:
        """The one shape an attempt that raised takes, whichever plan it was in."""
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
        assert accepted_judgement is not None  # set by `observed` on PASSED
        return Delivered(
            family=family,
            rung=rung,
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

    try:
        if riding is not None:
            ride = _ride(config, route, riding)
            held, riding = riding.rung, None
            try:
                ridden = climb(
                    ride, rode, capacity=capacity, permit=permit, claimed=held
                )
            except _AttemptError as raised:
                # A ride whose dispatch died went nowhere: recorded, uncharged.
                history.append(_raised_attempt(raised))
            else:
                history.extend(ridden.history)
                if isinstance(ridden, Accepted):
                    return finish_accepted(ridden.family, ridden.rung)
            # As if every relief rung were full: the entry is decided again
            # without them, and the climb is the rider's own from here, with
            # every attempt and escalation it had.
            entry = route.reserve_entry(relief=False)
            if entry is not None:
                route, claimed = _entered(config, pool, contract, capacity, entry)
                ceiling, budget = route.ceiling, route.budget
        for index, each in enumerate(route.plans):
            if not each.climbable:
                # Not entered, and its reason is kept for the halt detail. The
                # test is `climbable` rather than truthiness because the two
                # disagree: a deterministic family holding a program is
                # non-empty and still has nothing to climb, and `climb` raises
                # `RouteError` for it.
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
                return raised_to_halted(raised)
            history.extend(result.history)
            if result.history:
                entered.append(each.family)
            if isinstance(result, Accepted):
                return finish_accepted(result.family, result.rung)
            if result.reason is Exhaustion.WITHHELD:
                break
            # The fleet-manager seam: a resident family spent, the api family
            # next. Ask once whether an asleep smarter rung should be woken and
            # routed to before the api is entered, and climb it if so. Nothing
            # is consulted on the way *up* within a family or across any other
            # boundary — the judgment costs a model call, and it is only the
            # api crossing that is worth paying it for.
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
        # Unreachable by the argument above, and kept anyway: the cost of that
        # argument being wrong one day is not a wrong answer, it is a source
        # that reads as busy for the rest of the process.
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
        detail=_halt_detail(outcome, route, attempts_spent, escalations),
    )


def _raised_attempt(raised: _AttemptError) -> Attempted:
    """The history entry of an attempt that raised instead of judging."""
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
    """The ascent rebuilt with ``entry``'s family as its floor, and the rung to
    hand its first climb.

    The reservation is given back here on every path that does not hand it
    down: an ascent that raised while being rebuilt, and one rebuilt without
    the rung the reservation is for (:func:`_handed_down`). The rung returned
    is the caller's to hand to a climb, or to release.
    """
    claimed: str | None = None
    try:
        route = ascent(config, pool, contract, floor=entry.family, capacity=capacity)
        claimed = _handed_down(route, entry)
    finally:
        # `claimed` is cleared the moment a climb takes it, so it doubles as
        # "still ours".
        if claimed is None:
            entry.release()
    return route, claimed


def _ride(config: Config, route: Ascent, riding: Entry) -> Plan:
    """A one-step plan for the relief rung ``riding`` reserved.

    Its family is the catalog's for that rung (:func:`~mcgyvr.route.family_of`):
    the cost class an answer from it is reported in. It is a plan of its own and
    on no list of the ascent's, so the climb that takes it gives back its
    reservation and ends, and nothing after it counts it as a family entered.
    """
    step = next(step for step in route.relief if step.rung.name == riding.rung)
    return Plan(family=family_of(config, riding.rung), steps=(step,))


def _idle_entry(route: Ascent) -> Entry | None:
    """Which family ``idle`` enters when that is dearer than the floor, and the
    rung it has reserved there.

    ``None`` under every other mode, without a capacity, and whenever the
    cheapest free rung is already in the floor family — three cases in which
    there is nothing to raise, the ascent stands as built, and **nothing is
    reserved**. :meth:`Ascent.reserve_entry` is the single answer this reads;
    the reasons it declines to give one are its own and are not restated here.

    **The read and the commitment are one decision.** A name alone reserves
    nothing: every member of a batch reaching this point would see the same one
    free api slot, raise its entry into the priced family and then queue on it —
    *paying* for a rung it could have waited out locally for nothing.

    So the named rung is reserved inside the very section that priced it, and
    the reservation is handed down: :func:`escalate` passes ``rung`` to the
    entry family's :func:`~mcgyvr.route.climb` as ``claimed``, and that climb
    takes it *without claiming it again*, so one attempt is counted for one
    dispatch and ``climb``'s ``finally`` gives it back exactly once. Two
    failures are ruled out by this shape: a double count, because the claim is
    skipped for exactly that rung, and a phantom reservation, because nothing
    is reserved on any path that does not raise the entry.

    **What it does not do is shorten the walk.** A family short of the rungs
    cheaper than the claimed one would run out of ladder while still holding
    escalation budget nothing has paid for, and that leftover move would fund a
    dispatch into a dearer family. Fan-out is a scheduling decision and not a
    spend decision, so the claimed rung is popped out of the middle of the walk
    and every other rung stays exactly where it was.

    **A leaked reservation is forever**, so the obligation :class:`Entry`
    carries is discharged on every path: by the climb that takes it over, and
    otherwise by :func:`escalate`'s ``finally``.

    **A raised entry is free, and a climbed one is not.** An escalation is what
    a *failure* buys: ``max_escalations`` bounds how far work climbs
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
    rungs of one family, so there is no handle there to release with, and the seam's
    rule keeps the source name from being the alternative. ``None`` therefore
    means "still ours", and :func:`escalate` releases it rather than handing
    down a name that would be quietly ignored.
    """
    for each in route.plans:
        if each.family == entry.family:
            return entry.rung if entry.rung in each.rungs else None
    return None


def _next_is_api(plans: tuple[Plan, ...], index: int) -> bool:
    """Whether the plan after ``index`` is the api family — the climb's next stop.

    The fleet-manager seam fires only here: a resident family spent, and the
    next family up is the api. Nothing earlier on the walk crosses this line,
    so the judgment is never paid before a family has actually been tried.
    """
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
    """A one-rung plan for ``rung``, cut out of the family it belongs to.

    Reuses :func:`mcgyvr.route.plan` so the step carries the same attempts and
    machine the family's own climb would have used — the hook routes, it does
    not re-declare budget. ``None`` when ``rung`` is not on that family's plan,
    a hook naming a rung the ladder does not offer.
    """
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
