"""A run writes down what happened, so the ordering question can be answered later.

Which rung should have gone first is a research question, and research needs
rows: which rung ran, on which machine, how long it took, what the verdict was.
The record states facts and holds no opinion -- a column naming the rung that
*should* have run would be this file answering the question it exists to defer.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcgyvr.record import Attempt, write_record

REQUIRED = {
    "rung",
    "host",
    "model",
    "unit",
    "wall_clock_s",
    "verdict",
    "attempts_charged",
}


def attempt(**overrides: object) -> Attempt:
    row: dict[str, object] = {
        "rung": "local_moe",
        "host": "desktop-1",
        "model": "qwen3-coder-30b",
        "unit": "desktop-1/qwen3-coder-30b/llama.cpp",
        "wall_clock_s": 12.5,
        "verdict": "FAILED",
        "attempts_charged": 1,
    }
    row.update(overrides)
    # A dict of mixed-type overrides can't be matched field-by-field against
    # Attempt's distinct str/float/int params; the house pattern (see
    # test_orchestrator_decompose.py) accepts that here.
    return Attempt(**row)  # type: ignore[arg-type]


def rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_each_attempt_records_rung_host_and_wall_clock(tmp_path: Path) -> None:
    path = write_record((attempt(),), root=tmp_path)
    assert rows(path)[0].keys() >= REQUIRED


def test_a_declined_rung_is_recorded_and_charged_to_nothing(tmp_path: Path) -> None:
    path = write_record(
        (attempt(verdict="DECLINED", attempts_charged=0),), root=tmp_path
    )
    row = rows(path)[0]
    assert row["verdict"] == "DECLINED"
    assert row["attempts_charged"] == 0


def test_the_record_names_the_serving_unit_the_rung_ran_on(tmp_path: Path) -> None:
    assert rows(write_record((attempt(),), root=tmp_path))[0]["unit"]


def test_attempts_are_written_in_the_order_they_happened(tmp_path: Path) -> None:
    path = write_record((attempt(rung="a"), attempt(rung="b")), root=tmp_path)
    assert [row["rung"] for row in rows(path)] == ["a", "b"]


def test_the_record_holds_no_ordering_opinion(tmp_path: Path) -> None:
    row = rows(write_record((attempt(),), root=tmp_path))[0]
    assert "rank" not in row
    assert "should_have_used" not in row


def test_a_record_is_appended_not_rewritten(tmp_path: Path) -> None:
    path = write_record((attempt(rung="a"),), root=tmp_path)
    write_record((attempt(rung="b"),), root=tmp_path, run_id=path.stem)
    assert [row["rung"] for row in rows(path)] == ["a", "b"]


def test_two_runs_do_not_share_a_file(tmp_path: Path) -> None:
    first = write_record((attempt(),), root=tmp_path)
    second = write_record((attempt(),), root=tmp_path)
    assert first != second
