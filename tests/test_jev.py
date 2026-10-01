"""The Jev verifier rung: typed questions folded into observations.

The decision seam is stubbed — the properties under test are the question
state built from added lines only, the observation mapping and the
never-reject behaviour, none of which need a live server. The one gate-level
test runs the rung through :class:`~mcgyvr.gate.Gate` with empty adapters, so
no toolchain is exercised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcgyvr.decision import BoolAnswer, Decision, DecisionError, ScoreAnswer
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.jev import CHECK, JevCheck, JevReport, build_state
from mcgyvr.gate.runner import Gate

CONTRACT = "Add retry with backoff to the fetch helper."


def _change(tmp_path: Path, name: str, text: str, added: set[int]) -> ChangeSet:
    """A change set over a real file on disk, with only ``added`` lines added."""
    (tmp_path / name).write_text(text, encoding="utf-8")
    return ChangeSet(
        repo=tmp_path,
        base="HEAD",
        files=(
            FileChange(
                path=name,
                status="A",
                added_lines=frozenset(added),
                is_binary=False,
            ),
        ),
    )


def _yes(state: Any) -> Decision:
    """A decide seam that approves on every question."""
    return Decision(
        answers={
            "satisfies_task": BoolAnswer(
                value=True, probability_true=0.9, confidence=0.8
            ),
            "in_scope": BoolAnswer(value=True, probability_true=0.9, confidence=0.8),
            "regression_risk": ScoreAnswer(
                level=0.0,
                probabilities={"low": 0.9, "medium": 0.1, "high": 0.0},
                confidence=0.8,
            ),
        }
    )


def _no(state: Any) -> Decision:
    return Decision(
        answers={
            "satisfies_task": BoolAnswer(
                value=False, probability_true=0.1, confidence=0.8
            )
        }
    )


def test_a_yes_answer_and_a_low_risk_produce_no_observations(
    tmp_path: Path,
) -> None:
    report = JevCheck(decide=_yes).run(
        _change(tmp_path, "worker.py", "def go():\n    return 1\n", {1, 2}),
        CONTRACT,
    )
    assert report == JevReport()


def test_a_no_answer_is_an_observation_not_a_rejection(tmp_path: Path) -> None:
    report = JevCheck(decide=_no).run(
        _change(tmp_path, "worker.py", "def go():\n    return 1\n", {1, 2}),
        CONTRACT,
    )
    assert report.findings == ()
    assert len(report.observations) == 1
    finding = report.observations[0]
    assert finding.check == CHECK
    assert finding.code == "satisfies_task"
    assert finding.path == "worker.py"
    assert "does not satisfy" in finding.message


def test_an_out_of_scope_answer_is_reported_by_its_question(tmp_path: Path) -> None:
    def decide(state: Any) -> Decision:
        return Decision(
            answers={
                "in_scope": BoolAnswer(
                    value=False, probability_true=0.2, confidence=0.7
                )
            }
        )

    report = JevCheck(decide=decide).run(
        _change(tmp_path, "worker.py", "def go():\n    return 1\n", {1, 2}),
        CONTRACT,
    )
    assert [f.code for f in report.observations] == ["in_scope"]


def test_a_high_regression_risk_is_reported(tmp_path: Path) -> None:
    def decide(state: Any) -> Decision:
        return Decision(
            answers={
                "regression_risk": ScoreAnswer(
                    level=2.0,
                    probabilities={"low": 0.0, "medium": 0.1, "high": 0.9},
                    confidence=0.8,
                )
            }
        )

    report = JevCheck(decide=decide).run(
        _change(tmp_path, "worker.py", "def go():\n    return 1\n", {1, 2}),
        CONTRACT,
    )
    assert [f.code for f in report.observations] == ["regression_risk"]
    assert "high" in report.observations[0].message


def test_only_added_lines_are_judged(tmp_path: Path) -> None:
    """The state the model sees carries the added lines and nothing pre-existing."""
    captured: list[dict[str, Any]] = []

    def decide(state: Any) -> Decision:
        captured.append(state)
        return _yes(state)

    text = "PRE = 1\n\n\ndef go():\n    return 2\n"
    JevCheck(decide=decide).run(_change(tmp_path, "worker.py", text, {4, 5}), CONTRACT)

    state = captured[0]
    assert state["path"] == "worker.py"
    lines = state["added_lines"]
    assert [line["line"] for line in lines] == [4, 5]
    joined = " ".join(line["text"] for line in lines)
    assert "return 2" in joined
    assert "PRE = 1" not in joined


def test_a_change_with_no_added_lines_is_a_no_op(tmp_path: Path) -> None:
    report = JevCheck(decide=_yes).run(
        _change(tmp_path, "worker.py", "def go():\n    return 1\n", set()),
        CONTRACT,
    )
    assert report == JevReport()


def test_a_model_that_cannot_answer_is_an_environment_issue(tmp_path: Path) -> None:
    def decide(state: Any) -> Decision:
        raise DecisionError("no label appeared in top_logprobs")

    report = JevCheck(decide=decide).run(
        _change(tmp_path, "worker.py", "def go():\n    return 1\n", {1, 2}),
        CONTRACT,
    )
    assert report.observations == ()
    assert report.findings == ()
    assert len(report.environment_issues) == 1
    assert "was not judged" in report.environment_issues[0]


def test_blocking_is_off_by_default_and_observations_do_not_reject(
    tmp_path: Path,
) -> None:
    report = JevCheck(decide=_no).run(
        _change(tmp_path, "worker.py", "def go():\n    return 1\n", {1, 2}),
        CONTRACT,
    )
    assert report.findings == ()
    assert len(report.observations) == 1


def test_the_state_serializes_to_the_contract_and_the_added_lines(
    tmp_path: Path,
) -> None:
    change = _change(tmp_path, "worker.py", "def go():\n    return 1\n", {1, 2})
    state = build_state(change, change.files[0], CONTRACT)
    assert state["task"] == CONTRACT
    assert state["path"] == "worker.py"


def test_the_gate_reports_jev_observations_without_rejecting(tmp_path: Path) -> None:
    result = Gate(adapters=()).run(
        _change(tmp_path, "worker.py", "def go():\n    return 1\n", {1, 2}),
        jev=JevCheck(decide=_no),
    )

    assert result.accepted  # an observation is not a rejection
    assert [f.check for f in result.observations] == [CHECK]
    assert result.jev is not None
    assert len(result.jev.observations) == 1
