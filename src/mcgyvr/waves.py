"""Running a plan in the order its own contracts state, and re-planning failure.

:func:`~mcgyvr.orchestrator.decompose.decompose` emits contracts and stops. A
set of contracts is a plan, but a plan nothing orders is a list: the order they
arrive in is the order a model thought of them, not a topological sort, so a
multi-step change handed straight to a runner writes against files the step
before it never created.

This module adds no judgement — which work to do is the decomposer's, whether a
change is acceptable is the gate's, which rung to spend is
:mod:`mcgyvr.route`'s. It makes three decisions, and every one of them is about
spend rather than about code:

*Order.* A wave is the pending contracts whose ``depends_on`` have all landed.
The dependency is read off the contract, because that is the only place it is
stated (:mod:`mcgyvr.contract`) and because ordering that is not written down
is ordering that does not exist.

*Refusal.* A contract whose dependency did not land is **not attempted**, and
that is a different outcome from attempting it and failing. Its input was never
written, so the attempt could only produce a rejection — one that costs a
rung's tokens, and that then reads in every record downstream as the worker's
fault rather than as the plan's. The plan was wrong; the record should say so.

*Re-planning.* A failed wave is re-planned, not retried. The re-planner is told
which contracts failed and why, because one told only that "something failed"
re-emits the step that just failed; and what it returns replaces those
contracts rather than joining them, because a wave loop that ran the same
contract again would be a retry loop wearing a plan's clothes. Retrying one
contract on one rung is ``limits.attempts``; carrying it to a dearer rung is
:mod:`mcgyvr.escalate`. Both already exist, and this is neither.

Nothing here touches a repository, a model or the clock. ``attempt`` is an
unbound parameter, the way every expensive step in mcgyvr already is, so a plan
can be driven end to end with no rung configured at all — which is what makes
the ordering above a property of this module rather than of whatever eventually
binds it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Protocol

from mcgyvr.contract import Contract

DEFAULT_MAX_WAVES = 3
"""How many times a plan may be re-planned before the remainder is reported.

A bound rather than a convergence check: each wave that re-plans spends the
decomposer, so a plan that is not getting closer has to stop costing something.
What is left over is reported by name, never retried quietly.
"""


class Attempt(Protocol):
    """Running one contract, however it is run.

    The return value only has to say whether the work landed, and there are
    three ways it may say so: an ``ok`` attribute, the field named for its type
    in :data:`VERDICTS`, or — for a bare value whose truth *is* its content — its
    own truth value. One that did not land is asked for a ``reason``.
    Deliberately no narrower than that — the outcome of a real dispatch belongs
    to whatever binds this parameter, and a driver that demanded that type would
    be unusable until it existed.

    Reading a stated verdict first is what makes that width real rather than
    nominal, because **not one terminal outcome in mcgyvr defines** ``__bool__``.
    That is on purpose and it is the codebase's policy: a caller is meant to
    match on the answer rather than remember a boolean's polarity. Every one of
    them is therefore true whatever it says, so truthiness alone reports a spent
    ladder as an accepted change and a refused delivery as a commit — which is
    not a misreading a driver can be left to notice on its own.

    They do not all state it in one word, and assuming they did is how six of
    them stayed misread after the first fix. :class:`~mcgyvr.escalate.Delivered`,
    :class:`~mcgyvr.escalate.Halted`, :class:`~mcgyvr.route.Accepted`,
    :class:`~mcgyvr.route.Exhausted` and
    :class:`~mcgyvr.sandbox.base.CommandResult` say ``ok``; six more say
    ``committed``, ``completed``, ``accepted`` or ``changed``, and those are
    :data:`VERDICTS`. An outcome that says none of them is refused rather than
    guessed at — see :func:`_landed`.
    """

    def __call__(self, contract: Contract, /) -> object: ...


class Replan(Protocol):
    """Planning the work that failed, again, knowing how it failed."""

    def __call__(self, previous: PreviousAttempt, /) -> Sequence[Contract]: ...


@dataclass(frozen=True)
class PreviousAttempt:
    """What the last wave did, as the re-planner is told it.

    Both halves are load-bearing and they are different halves: ``completed``
    is work that is already in the tree and must not be planned a second time,
    ``failed`` is work that has to be planned *differently*. A re-planner given
    only the failures repeats work that is already done; given only the
    completions it re-plans blind and re-emits what just failed.

    :meth:`__str__` is the block a model re-planner is handed. The fields are
    here as well so that a deterministic one does not have to parse the prose
    back out of it.
    """

    completed: tuple[str, ...] = ()
    failed: tuple[tuple[str, str], ...] = ()

    def __str__(self) -> str:
        completed = "\n".join(f"  - {done}" for done in self.completed) or "  (none)"
        failed = (
            "\n".join(f"  - {task}: {reason}" for task, reason in self.failed)
            or "  (none)"
        )
        return (
            f"PREVIOUS ATTEMPT RESULTS:\n"
            f"Completed:\n{completed}\n"
            f"Failed:\n{failed}\n\n"
            f"The completed work is already in the tree: do not plan it again. "
            f"Re-plan only what failed, and only as work a different plan would "
            f"do differently — the same contract a second time is a retry, and "
            f"the retries this work was owed have already been spent."
        )


@dataclass(frozen=True)
class WaveRun:
    """What running a plan did, in the three outcomes that are not the same.

    ``failed`` is attempted-and-rejected; ``blocked`` is never attempted, and
    the reason names what it was waiting for. Keeping them apart is the whole
    point of the run: they cost different amounts and mean different things,
    and a report that merged them would say a worker failed when no worker was
    ever asked.

    A contract that failed stays in ``failed`` even when a re-planned contract
    later did its job, because this run cannot know that it did — the
    replacement has its own id, and deciding that one contract stood in for
    another is a judgement, not a fact a driver holds.
    """

    completed: tuple[str, ...] = ()
    failed: tuple[tuple[str, str], ...] = ()
    blocked: tuple[tuple[str, str], ...] = ()
    waves: int = 0

    @property
    def ok(self) -> bool:
        """Whether the plan is done: nothing failed, and nothing is still waiting.

        Stated here for the reason every other outcome in mcgyvr states it
        (:attr:`~mcgyvr.escalate.Delivered.ok`,
        :attr:`~mcgyvr.route.Accepted.ok`)
        rather than left to be worked out of three tuples at each call site,
        where it would be worked out differently each time. A plan with nothing
        in it is ok vacuously: no work was asked for, so none is outstanding.
        """
        return not self.failed and not self.blocked


def run_waves(
    contracts: Iterable[Contract],
    attempt: Attempt,
    *,
    replan: Replan | None = None,
    max_waves: int = DEFAULT_MAX_WAVES,
) -> WaveRun:
    """Run ``contracts`` in the order their dependencies require.

    Each wave attempts every pending contract whose ``depends_on`` have all
    landed, in the order the contracts were given. A wave with no ready
    contract is the end of the run: everything still pending is waiting on
    something that will never arrive — a dependency that failed, an id no
    contract in this plan carries, or a cycle — and is reported as blocked
    rather than attempted.

    ``replan`` is what makes a failed wave worth having. It is handed the
    completions and the failures of the wave that just ran and returns the
    contracts to try instead; anything it returns under an id that has already
    landed, failed or is still pending is dropped, so a re-planner cannot turn
    the loop into a retry of the contract it was asked to replace. Without one,
    a failure simply ends the branch of the plan that depended on it.

    Two contracts under one id are one contract, and the first is kept: an id
    is the join key every record, dependency and report downstream is written
    against, so a plan cannot hold two of them however it was assembled.

    Never raises for a failed plan: a run where everything failed is a
    :class:`WaveRun` naming each failure, which is the difference between "this
    plan did not work" and a traceback.
    """
    pending: dict[str, Contract] = {}
    for contract in contracts:
        pending.setdefault(contract.id, contract)

    completed: list[str] = []
    landed: set[str] = set()
    failed: dict[str, str] = {}
    blocked: dict[str, str] = {}
    waves = 0

    while pending and waves < max_waves:
        waves += 1
        ready = [c for c in pending.values() if landed.issuperset(c.depends_on)]
        if not ready:
            blocked.update(
                (task, _blocked_reason(contract, landed, pending, failed))
                for task, contract in pending.items()
            )
            pending.clear()
            break

        fell_over: dict[str, str] = {}
        for contract in ready:
            outcome = attempt(contract)
            del pending[contract.id]
            if _landed(outcome):
                completed.append(contract.id)
                landed.add(contract.id)
            else:
                fell_over[contract.id] = _reason(outcome)
        failed.update(fell_over)

        if fell_over and replan is not None and waves < max_waves:
            previous = PreviousAttempt(tuple(completed), tuple(fell_over.items()))
            for fresh in replan(previous):
                if fresh.id in landed or fresh.id in failed or fresh.id in pending:
                    continue
                pending[fresh.id] = fresh

    # A plan that ran out of waves has not failed and has not been refused: it
    # was not reached. Said in those words, because "would this have worked
    # with one more wave" is the question a shorter sentence would hide.
    blocked.update(
        (task, f"not reached: the run stopped after {waves} of {max_waves} waves")
        for task in pending
    )

    return WaveRun(
        completed=tuple(completed),
        failed=tuple(failed.items()),
        blocked=tuple(blocked.items()),
        waves=waves,
    )


VERDICTS: Mapping[str, str] = MappingProxyType(
    {
        "mcgyvr.cleanup.Cleanup": "accepted",
        "mcgyvr.consensus.Consensus": "accepted",
        "mcgyvr.deliver.Delivery": "committed",
        "mcgyvr.gate.runner.GateResult": "accepted",
        "mcgyvr.pending.Resumed": "completed",
        "mcgyvr.repair.RepairOutcome": "changed",
    }
)
"""Where an outcome states its verdict, for the types that do not say ``ok``.

Six entries because six is how many there are, and written down because the
alternative was assuming there were none. ``ok`` is the convention and this is
the exception list; both are read before anything falls back to a truth value.

Keyed by qualified name rather than by the class so that this module keeps
importing nothing but a contract. An outcome's type belongs to whatever binds
:class:`Attempt` — delivery, recovery, repair, cleanup, consensus, the gate —
and importing six modules to learn six field names would make ordering a plan
depend on every lever that can execute one, which is the coupling this module
was written without.

The table is not a best effort. An outcome type in neither it nor the ``ok``
convention is refused by :func:`_landed` rather than guessed at, so the day it
falls behind is a named failure in a report and never a quiet completion; and a
field renamed out from under an entry reads the same way, because a name that no
longer resolves states no verdict either.
"""

_UNSTATED = object()
"""Not the same as an outcome that stated its verdict and stated it falsely.

A default that could itself be an outcome would collapse the two, and the
distinction is the whole of :func:`_landed`: one of them is a verdict to be
believed, the other is an object that has not answered the question.
"""


def _verdict(outcome: object) -> object:
    """What ``outcome`` says about its own work, or :data:`_UNSTATED`.

    Three readings in the order they were written down deliberately. ``ok`` is
    the convention, so it outranks everything — including a type in
    :data:`VERDICTS` that later grows one, which is how a type leaves this table
    without anything here changing. :data:`VERDICTS` is the stated exception.
    Truthiness comes last and only from a bare value (:func:`_is_a_bare_value`).
    """
    stated: object = getattr(outcome, "ok", _UNSTATED)
    if stated is not _UNSTATED:
        return stated
    named = VERDICTS.get(_named(outcome))
    if named is not None:
        return getattr(outcome, named, _UNSTATED)
    if _is_a_bare_value(outcome):
        return bool(outcome)
    return _UNSTATED


def _is_a_bare_value(outcome: object) -> bool:
    """Whether truthiness is the whole of what this value has to say.

    Two conditions, and both are needed. It has to be a **builtin** — ``True``,
    ``None``, ``""``, ``()`` have no verdict to state anywhere, so their truth
    value *is* their content and reading it is reading what they mean, while
    anything with a type of its own is asked where its verdict is instead. And
    its type has to **say** what its truth value is, by defining ``__bool__`` or
    ``__len__``: a bare :class:`object` is a builtin that defines neither, so it
    is true for no reason at all, which is the accident this whole function
    exists to keep out.

    The narrower line was chosen after the wider one was tried. "It defines
    ``__bool__`` or ``__len__``, so its truthiness was deliberate" reads well and
    is false in this codebase: :class:`~mcgyvr.consensus.Consensus` defines
    ``__len__`` as *the number of draws*, so a best-of-three whose winner the
    gate rejected is three, and three is true. A truth value that was written
    down on purpose can still be a statement about something other than the
    verdict — and every misreading in this module has been exactly that. So a
    class states its verdict in ``ok`` or in :data:`VERDICTS`, or it is not read.

    This is what keeps the documented fallback honest rather than merely alive:
    a driver handing back a bare ``bool`` is still served, and everything else is
    asked to say what it means.
    """
    kind = type(outcome)
    return kind.__module__ == "builtins" and any(
        "__bool__" in each.__dict__ or "__len__" in each.__dict__
        for each in kind.__mro__
    )


def _landed(outcome: object) -> bool:
    """Whether an attempt says its work landed, in whichever way it says it.

    Never inferred. An outcome that states no verdict any of the three readings
    can find is reported as a failure naming itself (:func:`_unreadable`),
    because the only other default is "landed" and a wrong "landed" is the
    expensive one: it releases the dependants into the next wave, where a rung's
    tokens buy a rejection against a tree their input was never written into —
    the exact spend this module exists to refuse.

    A failure rather than a raised exception, for the reason this function is
    reached at all: waves run contracts that commit, and a driver that aborted
    mid-plan on a type it did not recognise would leave earlier work in the tree
    and no report saying what happened to the rest.
    """
    stated = _verdict(outcome)
    return stated is not _UNSTATED and bool(stated)


def _named(outcome: object) -> str:
    """The outcome's type, as :data:`VERDICTS` keys it and a report names it."""
    kind = type(outcome)
    return f"{kind.__module__}.{kind.__qualname__}"


def _unreadable(outcome: object) -> str:
    """Why an outcome could not be read, and what would make it readable.

    Both halves, because this sentence is the whole of the loudness: it is what
    an operator sees in ``failed`` on the day a new outcome type reaches a wave
    loop that has never heard of it, and "something went wrong" would send them
    to the worker rather than to this table.
    """
    return (
        f"the attempt returned {_named(outcome)}, which states no verdict this "
        f"driver can read: it carries no 'ok', is not named in "
        f"mcgyvr.waves.VERDICTS, and defines no truth value of its own. Read as "
        f"a failure rather than guessed at — the guess would be 'landed', for "
        f"every outcome of that type and whatever it actually said."
    )


def _reason(outcome: object) -> str:
    """Why an attempt did not land, as the attempt itself put it.

    Read off the outcome rather than invented here: a driver that supplied its
    own wording would hand the re-planner a sentence about the plan when what
    it needs is the one about the work. Two spellings because both are live —
    :class:`~mcgyvr.route.Exhausted` carries a machine-readable ``reason`` with
    the prose beside it in ``detail``, :class:`~mcgyvr.escalate.Halted` carries
    only the prose.

    Prose outranks a code, which is the one thing the first version of this got
    backwards: ``Exhausted.reason`` is an :class:`~enum.Enum` member, so asking
    for ``reason`` first reported ``rungs_spent`` and dropped the sentence
    sitting beside it. An enum is machine-readable, which is a virtue in a field
    and not in a paragraph handed to a model re-planner — and one told nothing
    but a token re-emits the step that just failed. The code is still used when
    it is all there is.

    An outcome nobody can read gets :func:`_unreadable` instead of its own
    words, however many it carries: whatever it says about the work, the fact
    that reaches the operator first has to be that this driver could not read it.
    """
    if _verdict(outcome) is _UNSTATED:
        return _unreadable(outcome)
    coded = ""
    for spelling in ("reason", "detail"):
        stated = getattr(outcome, spelling, "")
        if isinstance(stated, Enum):
            coded = coded or str(stated.value).strip()
            continue
        prose = str(stated).strip()
        if prose:
            return prose
    return coded or "the attempt reported a failure without stating a reason"


def _blocked_reason(
    contract: Contract,
    landed: set[str],
    pending: Mapping[str, Contract],
    failed: Mapping[str, str],
) -> str:
    """Why a contract was never attempted, naming what it was waiting for.

    Three sentences rather than one, because the three cases have three
    different fixes: an id no contract in the plan carries is a plan that was
    written wrong and could never have run; a dependency that was attempted and
    did not land is a plan whose next step has nothing to build on; and a
    dependency still pending when nothing at all can run is a cycle, which no
    number of further waves resolves.
    """
    missing = [need for need in contract.depends_on if need not in landed]
    unknown = [need for need in missing if need not in pending and need not in failed]
    if unknown:
        return (
            f"not attempted: no contract in this plan carries "
            f"{', '.join(unknown)}, so nothing could ever satisfy it"
        )
    named = ", ".join(missing)
    if all(need in pending for need in missing):
        return (
            f"not attempted: waiting on {named}, which is waiting too — a cycle, "
            f"or a chain standing behind one"
        )
    return (
        f"not attempted: {named} did not land, and a contract whose input was "
        f"never written can only be rejected"
    )
