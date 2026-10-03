"""The result file's fields, as a caller reading it would see them.

``RunResult`` is the run's answer as data, and ``as_json`` is the shape the
result file is written in. The fields the prose-aware serving path adds travel
through that serialisation the same way every other field does.
"""

from __future__ import annotations

from mcgyvr.result import RunResult


def test_run_result_serializes_the_answer_field() -> None:
    report = RunResult(
        contract="answer",
        task_type="chat",
        target="answer.txt",
        orchestrator="t",
        answer="The sky is blue.",
    )

    assert report.as_json()["answer"] == "The sky is blue."


def test_run_result_answer_defaults_to_empty_for_a_whole_file_run() -> None:
    report = RunResult(
        contract="impl",
        task_type="function_implementation",
        target="src/pkg/messy.py",
        orchestrator="t",
    )

    assert report.as_json()["answer"] == ""
