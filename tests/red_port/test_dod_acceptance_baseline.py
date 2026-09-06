"""The evidence a contract carries is checked against the tree before it is spent.

``Acceptance`` has two lists with opposite baseline expectations, and the schema
states both. ``acceptance`` commands "must also pass on the *unchanged* tree (the
preflight refuses a suite that is already red)". ``demonstration`` commands are
"the `failing_test_first` evidence": each "must FAIL on the unchanged tree and
pass after the change".

``Acceptance.precondition`` is the method that establishes both. It has no caller
anywhere in the product, in the tools, or in the tests. Only ``run`` is called,
and ``run``'s own docstring reasons from a baseline nobody took: "they failed at
baseline, so one still failing is ...".

Two silent failures follow. A ``bug_fix`` whose demonstration was already passing
— a wrong ``-k`` filter, a test that was never red — is judged by running it
after the change, seeing green, and reporting the bug fixed; nothing was proved
and the result file cannot say so. And a contract whose acceptance suite was
already broken charges the model for the tree's fault, which is the exact thing
the preflight exists to prevent.

What must be observably true: a run refuses, before spending a rung, when the
evidence it was handed cannot signal — a demonstration that does not fail on the
unchanged tree, or an acceptance command that does not pass on it. The refusal
must name which command and which direction, because the operator's next move
differs completely between the two.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.red_port.conftest import required

#: Distinct texts per list: one command may not appear in both, and the
#: contract validator says so before this check is ever reached.
PASSES = "python3 -c 'import sys; sys.exit(0)'"
ALSO_PASSES = "python3 -c 'import sys; sys.exit(0)  # regression'"
FAILS = "python3 -c 'import sys; sys.exit(1)'"
ALSO_FAILS = "python3 -c 'import sys; sys.exit(1)  # regression'"

BUG_FIX = """
id: fix-chunk-remainder
task_type: bug_fix
task: chunk drops the final short group; keep it.
target: src/pkg/fetch.py
interface: "def fetch(url: str) -> str"
stop_conditions:
  - The demonstrating test does not fail on the current code.
demonstration: ["{demonstration}"]
acceptance: ["{acceptance}"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/pkg/**"]
"""


def _contract(*, demonstration: str, acceptance: str) -> Any:
    from mcgyvr.contract import loads

    return loads(BUG_FIX.format(demonstration=demonstration, acceptance=acceptance))


def _baseline(contract: Any, repo: Path) -> Any:
    """The refusal a run must reach before it spends anything."""
    check = required(
        "refuse a contract whose evidence cannot signal — a demonstration that "
        "already passes, or an acceptance command that is already red — before "
        "a rung is spent",
        lambda: (
            __import__(
                "mcgyvr.gate.preflight", fromlist=["check_evidence_baseline"]
            ).check_evidence_baseline
        ),
    )
    return check(contract, repo=repo)


def test_a_demonstration_that_already_passes_is_refused(repo: Path) -> None:
    """The `bug_fix` that proves nothing.

    A demonstration is the one command whose *failure* is the evidence. One that
    passes on the unchanged tree cannot distinguish a fix from a no-op, and a run
    that accepts on it reports a bug fixed that was never demonstrated.
    """
    issue = _baseline(_contract(demonstration=PASSES, acceptance=ALSO_PASSES), repo)
    assert issue is not None, (
        "a demonstration passing on the unchanged tree must refuse: it is the "
        "failing_test_first evidence and it did not fail"
    )
    assert "demonstration" in issue.message, (
        f"the refusal must say which list is wrong: {issue.message}"
    )


def test_an_acceptance_suite_already_red_is_refused(repo: Path) -> None:
    """The opposite direction, and the opposite next move.

    An acceptance command failing before the model touched anything charges the
    model for the tree. The operator fixes the tree; they do not rewrite the
    contract, which is what the other refusal asks for.
    """
    issue = _baseline(_contract(demonstration=FAILS, acceptance=ALSO_FAILS), repo)
    assert issue is not None, (
        "an acceptance command already failing must refuse before a rung is spent"
    )
    assert "acceptance" in issue.message, (
        f"the refusal must say which list is wrong: {issue.message}"
    )


def test_evidence_that_signals_is_not_refused(repo: Path) -> None:
    """The shape the schema describes must pass, or the check is a wall.

    A demonstration that fails on the unchanged tree and an acceptance suite that
    passes on it is exactly the contract the documentation asks for.
    """
    assert _baseline(_contract(demonstration=FAILS, acceptance=PASSES), repo) is None
