"""§4 — `max_waves` bounds re-planning, not the depth of a correct plan.

The pressure test's T1-E found that :func:`~mcgyvr.waves.run_waves` read
``max_waves`` as a bound on *total waves*: a correct, failure-free plan whose
dependency chain is deeper than the default of 3 was silently truncated, and its
tail reported ``blocked`` as if it had been waiting on something. The
``DEFAULT_MAX_WAVES`` docstring states the opposite — "how many times a plan may
be re-planned before the remainder is reported" — and the rationale is spend:
each wave that re-plans pays the decomposer. A wave that simply runs the next
ready contract pays nothing, so there is no reason to cap it.

Three assertions, one for each half of the defect:

* a failure-free chain deeper than the default runs to completion, with no
  re-planner attached at all (nothing can be spending the decomposer);
* the re-planner is what ``max_waves`` bounds — a plan that keeps failing is
  re-planned exactly ``max_waves`` times, then the remainder is reported;
* when that budget runs out, a contract whose dependency *failed* is reported
  with the accurate reason ("did not land"), never "not reached" — because no
  number of further waves would have run it.
"""

from __future__ import annotations

from mcgyvr.contract import Contract, loads
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


def contract(task_id: str, depends_on: tuple[str, ...] = ()) -> Contract:
    """One valid contract, stating on its own face what it waits for."""
    text = CONTRACT.format(id=task_id)
    if depends_on:
        text += "depends_on:\n" + "".join(f"  - {dep}\n" for dep in depends_on)
    return loads(text)


def chain(ids: list[str]) -> list[Contract]:
    """A linear dependency chain: each contract waits on the one before it."""
    out: list[Contract] = []
    for i, task_id in enumerate(ids):
        out.append(contract(task_id, depends_on=tuple(ids[:i])))
    return out


def test_a_failure_free_plan_deeper_than_the_default_is_not_truncated() -> None:
    """A correct 10-deep chain runs all ten, with the default ``max_waves``.

    No ``replan`` is supplied, so nothing can be spending the decomposer — the
    rationale the bound is documented under cannot apply, and truncating the
    tail here was the defect.
    """
    plan = chain([f"step-{i}" for i in range(10)])

    run = run_waves(plan, lambda _: True)

    assert run.completed == tuple(f"step-{i}" for i in range(10)), (
        f"a correct plan was truncated: completed {run.completed}, "
        f"blocked {run.blocked}"
    )
    assert run.blocked == (), (
        f"nothing was waiting on anything, yet the tail was reported blocked: "
        f"{run.blocked}"
    )
    assert run.waves == 10, f"a 10-deep chain should take 10 waves, not {run.waves}"


def test_the_re_planner_is_what_max_waves_bounds() -> None:
    """A plan that keeps failing is re-planned exactly ``max_waves`` times.

    Every attempt fails, so every wave has a failure to re-plan around. The
    bound is on the re-planner, not on the waves: with ``max_waves=2`` the
    re-planner is called twice, and the remainder is then reported rather than
    run.
    """
    calls: list[PreviousAttempt] = []

    def replan(previous: PreviousAttempt) -> tuple[Contract, ...]:
        calls.append(previous)
        # Re-plan the single failed contract as a fresh id each time, so the
        # loop keeps having a failure to re-plan around until the budget ends.
        return (contract(f"attempt-{len(calls)}"),)

    run = run_waves(
        [contract("attempt-0")], lambda _: False, replan=replan, max_waves=2
    )

    assert len(calls) == 2, (
        f"the re-planner should be called max_waves times, not {len(calls)}"
    )
    assert len(run.failed) == 3, (
        f"three attempts were run (initial + two re-plans), so three failed: "
        f"{run.failed}"
    )


def test_a_contract_whose_dependency_failed_is_not_reported_not_reached() -> None:
    """Budget exhausted or not, a failed dependency means "can never run".

    The pressure test's T1-E also caught the message: when the budget ran out,
    *every* still-pending contract was labelled "not reached" — including one
    whose dependency had failed and could therefore never run at any budget.
    The accurate reason is the one the ``not ready`` path already produces.

    ``b`` waits on a failed ``a`` and so can never run; ``c`` waits on ``b``
    and was merely not reached. The two reasons must differ.
    """
    a = contract("a")
    b = contract("b", depends_on=("a",))
    c = contract("c", depends_on=("b",))
    calls = 0

    def replan(previous: PreviousAttempt) -> tuple[Contract, ...]:
        nonlocal calls
        calls += 1
        return (contract(f"fresh-{calls}"),)

    def attempt(each: Contract) -> bool:
        # Every attempted contract fails, so every wave re-plans until the
        # budget ends and the tail is reported.
        return False

    run = run_waves([a, b, c], attempt, replan=replan, max_waves=1)

    reasons = dict(run.blocked)
    assert "did not land" in reasons.get("b", ""), (
        f"a contract whose input never landed was not told so: {reasons}"
    )
    assert "not reached" in reasons.get("c", ""), (
        f"a contract that merely was not reached was not told so: {reasons}"
    )
    assert "not reached" not in reasons.get("b", ""), (
        f"a contract that can never run was reported as merely unreached: {reasons}"
    )
