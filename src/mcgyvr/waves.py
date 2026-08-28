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

    The return value only has to say whether the work landed: it is read as a
    truth value, and a falsy one is asked for a ``reason``. Deliberately no
    narrower than that — the outcome of a real dispatch belongs to whatever
    binds this parameter, and a driver that demanded that type would be
    unusable until it existed.
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
            if outcome:
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


def _reason(outcome: object) -> str:
    """Why an attempt did not land, as the attempt itself put it.

    Read off the outcome rather than invented here: a driver that supplied its
    own wording would hand the re-planner a sentence about the plan when what
    it needs is the one about the work.
    """
    stated = str(getattr(outcome, "reason", "")).strip()
    return stated or "the attempt reported a failure without stating a reason"


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
