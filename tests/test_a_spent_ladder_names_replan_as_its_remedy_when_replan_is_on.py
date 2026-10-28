"""A spent ladder names re-planning as its remedy when re-planning is on.

`ladder_spent` used to end the work: no dearer family is left, and the only
remedies it named were to bind a dearer rung or narrow the contract by hand.
With `max_replans` above zero the contract goes back to the orchestrator with
its failure notes instead, so its disposition says so, and a single `mcgyvr
direct` that comes to `ladder_spent` notes on its result how the work goes on.
With `max_replans: 0` both say what they said before.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr.cli.commands.run import _report_climb
from mcgyvr.config import MAX_REPLANS_DEFAULT, SCHEMA
from mcgyvr.contract import Contract
from mcgyvr.escalate import Halted, Outcome, disposition
from mcgyvr.result import RunResult
from mcgyvr.scope import Scope

CONTRACT = Contract(
    id="code-rename",
    task_type="code",
    task="Rename rec_to_map to pairs_of.",
    target="pkg/codec.py",
    scope=Scope.of(["pkg/codec.py"], []),
)


def test_max_replans_is_a_documented_key_that_defaults_to_one() -> None:
    (field,) = [f for f in SCHEMA if f.name == "max_replans"]

    assert MAX_REPLANS_DEFAULT == 1
    assert field.default == MAX_REPLANS_DEFAULT
    assert field.min_value == 0
    assert "re-plan" in field.doc


def test_with_replan_on_the_spent_ladder_goes_back_to_the_orchestrator() -> None:
    on = disposition(Outcome.LADDER_SPENT, replans=1)

    assert "ladder_spent" in on.detail
    assert "max_replans" in on.detail
    assert "orchestrator" in on.detail
    assert "failure notes" in on.detail


def test_with_replan_off_the_spent_ladder_says_what_it_said() -> None:
    assert disposition(Outcome.LADDER_SPENT, replans=0) == disposition(
        Outcome.LADDER_SPENT
    )
    assert "max_replans" not in disposition(Outcome.LADDER_SPENT).detail


def halted(outcome: Outcome) -> Halted:
    return Halted(
        outcome=outcome, entered=(), history=(), attempts_spent=3, escalations=2
    )


def report_of(outcome: Outcome, replans: int) -> RunResult:
    report = RunResult(
        contract=CONTRACT.id, task_type="code", target=CONTRACT.target, session="o"
    )
    code = _report_climb(
        argparse.Namespace(),
        CONTRACT,
        cast(Any, None),
        Path("."),
        halted(outcome),
        None,
        report,
        replans=replans,
    )
    assert code == 1
    return report


def test_a_single_run_that_spent_its_ladder_notes_the_replan(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = report_of(Outcome.LADDER_SPENT, replans=1)

    assert report.outcome == "ladder_spent"
    (note,) = [n for n in report.notes if "replan" in n]
    assert "`mcgyvr PROMPT`" in note
    assert "`mcgyvr direct` stops here" in note
    assert note in capsys.readouterr().err


def test_no_replan_note_when_replan_is_off_or_the_climb_stopped_otherwise() -> None:
    assert not [n for n in report_of(Outcome.LADDER_SPENT, 0).notes if "replan" in n]
    assert not [n for n in report_of(Outcome.ATTEMPT_CEILING, 1).notes if "replan" in n]
