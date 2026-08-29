"""B8 — an attempt that failed, reported as work that landed.

:func:`~mcgyvr.waves.run_waves` decided whether a contract had landed by reading
its attempt's return value as a truth value. Nothing in mcgyvr answers that
question that way. Every terminal outcome here is an object stating its verdict
as ``ok`` — :class:`~mcgyvr.escalate.Delivered` and
:class:`~mcgyvr.escalate.Halted` are the pair a per-contract driver returns,
:class:`~mcgyvr.route.Passed` and :class:`~mcgyvr.route.Exhausted` the pair one
rung down — and each of them is a plain object, so each of them is truthy. That
is deliberate and documented where they are declared: a caller is meant to match
on the answer rather than remember a boolean's polarity. Read as a truth value,
every one of them says the work landed.

So the assertions here are made against the real outcome types rather than
against a stand-in with a convenient ``__bool__``. A spy that spelled failure the
way the wave loop happened to read it would have passed against the defect, which
is how the defect survived a green RED suite in the first place.

Three consequences are asserted separately because they cost different things. A
failure in ``completed`` is a report that is simply wrong. A dependant attempted
against a tree its input was never written into is a rung's tokens spent on a
guaranteed rejection — the spend :mod:`mcgyvr.waves` exists to refuse. And a
re-planner that is never called is the whole re-planning limb of the module,
dead, in the one binding it was written for.

The truthiness the module documented is kept as a fallback and asserted as such:
a driver bound to a bare ``bool`` is a driver this module still has to serve.
"""

from __future__ import annotations

from dataclasses import dataclass

from mcgyvr.catalog import catalog
from mcgyvr.contract import Contract, loads
from mcgyvr.escalate import Assurance, Delivered, Halted, Judgement, Outcome
from mcgyvr.route import Verdict
from mcgyvr.waves import PreviousAttempt, run_waves

CONTRACT = """
id: {id}
task_type: docstring
task: Document the {id} helper.
target: src/pkg/fetch.py
stop_conditions:
  - The helper's behaviour is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

SPENT = "the ladder is spent: 3 attempt(s) and 1 escalation(s), and none landed."


def contract(task_id: str, depends_on: tuple[str, ...] = ()) -> Contract:
    """One valid contract, stating on its own face what it waits for."""
    text = CONTRACT.format(id=task_id)
    if depends_on:
        text += "depends_on:\n" + "".join(f"  - {dep}\n" for dep in depends_on)
    return loads(text)


def halted(detail: str = SPENT) -> Halted:
    """A real terminal failure: ``ok`` is ``False`` and the object is truthy."""
    return Halted(
        outcome=Outcome.LADDER_SPENT,
        entered=(),
        history=(),
        attempts_spent=3,
        escalations=1,
        detail=detail,
    )


def delivered() -> Delivered:
    """A real terminal acceptance, for the runs that have to differ from it.

    ``ok`` is ``True`` and the object is truthy, so it agrees with its own
    truthiness exactly where :func:`halted` disagrees with its. That is the
    whole of what these runs need it to be: the two outcomes are told apart by
    the verdict each states, and a driver that read either off truthiness would
    read both the same way.
    """
    family = catalog().families[0]
    judgement = Judgement(verdict=Verdict.PASSED, assurance=Assurance.DETERMINISTIC)
    return Delivered(
        family=family,
        rung="local",
        assurance=Assurance.DETERMINISTIC,
        judgement=judgement,
        entered=(family,),
        history=(),
        attempts_spent=1,
        escalations=0,
    )


def test_the_outcome_types_this_module_is_driven_by_are_all_truthy() -> None:
    """The premise, asserted rather than assumed.

    If these ever grow a ``__bool__`` the defect below stops being reachable and
    the tests after it would keep passing while holding nothing. Better to have
    the premise fail loudly than to have its tests quietly stop meaning anything.
    """
    assert bool(halted()) is True, "a Halted that is falsy makes these tests vacuous"
    assert halted().ok is False, "a Halted that is ok is not a failure at all"


def test_a_spent_ladder_is_reported_as_a_failure() -> None:
    """The defect itself, on the outcome a per-contract driver actually returns."""
    run = run_waves([contract("write-fetch")], lambda _: halted())

    assert run.failed == (("write-fetch", SPENT),), (
        f"an attempt that did not land was not reported as a failure: {run}"
    )
    assert run.completed == (), (
        f"an attempt that did not land was reported as completed work: {run}"
    )


def test_an_acceptance_and_a_failure_do_not_produce_the_same_run() -> None:
    """What the caller sees: two opposite outcomes, one identical report.

    Asserted on the whole :class:`~mcgyvr.waves.WaveRun` rather than on a field,
    because "a caller cannot tell these apart" is a statement about everything
    the caller is given, not about the one field a narrower test would check.
    """
    plan = [contract("write-fetch")]

    landed = run_waves(plan, lambda _: delivered())
    lost = run_waves(plan, lambda _: halted())

    assert landed != lost, (
        f"a delivered task and a halted one produced the same report: {landed}"
    )


def test_a_run_says_plainly_whether_the_plan_landed() -> None:
    """``ok``, as every other outcome in mcgyvr states it.

    A caller that had to reconstruct this from three tuples would reconstruct it
    differently at each call site, and the polarity of ``not failed`` is exactly
    the thing this codebase declines to make anyone remember.
    """
    plan = (contract("write-fetch"), contract("document-fetch", ("write-fetch",)))

    assert run_waves(plan, lambda _: delivered()).ok is True, (
        "a plan whose every contract landed did not report itself as ok"
    )
    assert run_waves(plan, lambda _: halted()).ok is False, (
        "a plan that failed and left a dependant blocked reported itself as ok"
    )


def test_a_contract_whose_dependency_did_not_land_is_never_attempted() -> None:
    """The spend, not the bookkeeping.

    A failure read as a completion does not merely misreport: it releases the
    dependant into the next wave, where a rung's tokens buy a rejection against
    a tree the input was never written into — and that rejection then reads
    everywhere downstream as the worker's fault rather than the plan's.
    """
    plan = (contract("write-fetch"), contract("document-fetch", ("write-fetch",)))
    attempted: list[str] = []

    def attempt(each: Contract) -> object:
        attempted.append(each.id)
        return halted() if each.id == "write-fetch" else delivered()

    run = run_waves(plan, attempt)

    assert attempted == ["write-fetch"], (
        f"a contract was attempted although its dependency never landed: {attempted}"
    )
    assert [task for task, _ in run.blocked] == ["document-fetch"], (
        f"the dependant of a failed contract was not reported as blocked: {run}"
    )
    assert "write-fetch" in dict(run.blocked)["document-fetch"], (
        f"the blocked reason does not name what was waited on: {run.blocked}"
    )


def test_the_failure_reaches_the_re_planner() -> None:
    """A wave with no failures in it is a wave with nothing to re-plan.

    Read as truthiness, the whole re-planning limb of this module is unreachable
    under the binding it was written for: nothing ever fails, so ``replan`` is
    never called and a failed plan simply reports itself as done.
    """
    told: list[PreviousAttempt] = []

    def replan(previous: PreviousAttempt) -> tuple[Contract, ...]:
        told.append(previous)
        return ()

    run_waves([contract("write-fetch")], lambda _: halted(), replan=replan)

    assert told, "a wave failed and the re-planner was never called"
    assert told[0].failed == (("write-fetch", SPENT),), (
        f"the re-planner was not told which contract failed, or why: {told[0]}"
    )


def test_the_reason_is_the_one_the_outcome_stated() -> None:
    """Whichever word the outcome states it in.

    ``reason`` and ``detail`` are both live spellings in this codebase —
    :class:`~mcgyvr.route.Exhausted` carries a machine-readable ``reason`` and
    prose in ``detail``, :class:`~mcgyvr.escalate.Halted` carries only the prose
    — and a re-planner told "failed without stating a reason" re-emits the step
    that just failed, which is the one thing this module refuses to do.
    """

    @dataclass(frozen=True)
    class Reasoned:
        ok: bool = False
        reason: str = "acceptance command exited 1: two checks failed"
        detail: str = "prose that must not win over the stated reason"

    run = run_waves([contract("write-fetch")], lambda _: Reasoned())
    assert run.failed == (("write-fetch", Reasoned().reason),), (
        f"the reason the attempt stated did not reach the report: {run}"
    )

    prose = run_waves([contract("write-fetch")], lambda _: halted())
    assert prose.failed == (("write-fetch", SPENT),), (
        f"an outcome carrying only prose was reported as reasonless: {prose}"
    )


def test_a_bare_truth_value_still_reads_as_a_truth_value() -> None:
    """The documented fallback, kept.

    An attempt is an unbound parameter and a driver that hands back a bare
    ``bool`` is a driver this module still serves — including the one in
    ``tests/red_port/test_d02_waves.py``. Nothing about reading a stated verdict
    is allowed to cost that.
    """
    assert run_waves([contract("write-fetch")], lambda _: True).completed == (
        "write-fetch",
    ), "a truthy outcome with no stated verdict was not read as work that landed"

    for falsy in (False, None, ""):
        # Bound as a default rather than closed over: the loop variable is the
        # thing under test, and B023 is right that a closure over one is a trap.
        run = run_waves([contract("write-fetch")], lambda _, outcome=falsy: outcome)
        assert [task for task, _ in run.failed] == ["write-fetch"], (
            f"a falsy outcome ({falsy!r}) was not read as a failure: {run}"
        )


def test_a_stated_verdict_outranks_the_objects_truthiness() -> None:
    """Precedence, pinned, because the two can disagree.

    ``ok`` is the field every outcome in this codebase states its verdict in;
    truthiness is what an object has whether it meant to or not. When both are
    present the one that was written down deliberately is the one that counts.
    """

    @dataclass(frozen=True)
    class Insists:
        ok: bool = False

        def __bool__(self) -> bool:
            return True

    run = run_waves([contract("write-fetch")], lambda _: Insists())

    assert [task for task, _ in run.failed] == ["write-fetch"], (
        f"an outcome stating ok=False was read off its truthiness instead: {run}"
    )
