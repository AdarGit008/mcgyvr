"""Offline invariants over #121's breadth instrument.

The sweep itself needs a worker; none of this does. What is checkable without
one is whether the *instrument* observes the thing it claims to:

* **No early exit.** The whole point of the measurement is the index
  distribution, and production behaviour (stop at the first gate pass) would
  truncate every observation at its own answer. If a passing first draw ended
  the task, the rows would show a distribution concentrated at zero because
  the instrument put it there.
* **The arms are what the record says they are.** The greedy anchor at
  temperature 0.0, every sampled draw at the sampled temperature, everything
  ``quality_sensitive`` — a drift here re-labels one experiment as another.
* **The index arithmetic refuses partial observations.** "No pass in N" is
  only a fact about a task whose N draws were all recorded and none lost to
  dispatch errors; a truncated task silently counted would bias the exact
  number the issue exists to measure.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

from mcgyvr.runner import Completion, Request, StopReason
from mcgyvr.worker.reply import ParsedFile

REPO = Path(__file__).resolve().parent.parent


def _breadth() -> types.ModuleType:
    """The rig, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "breadth_measure", REPO / "tools" / "breadth" / "measure.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


breadth = _breadth()


class _CountingRunner:
    """A runner whose replies always parse, recording every request."""

    def __init__(self) -> None:
        self.requests: list[Request] = []

    def generate(self, model: str, request: Request) -> Completion:
        self.requests.append(request)
        return Completion(
            text="```ts\nexport const x = 1;\n```",
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model=model,
            source="test",
            protocol=breadth.bundle.Protocol.OPENAI,
            max_output_tokens=breadth.MAX_OUTPUT_TOKENS,
            latency_s=0.01,
            input_tokens=10,
            output_tokens=5,
        )


def _measure_one(
    tmp_path: Path, monkeypatch: Any, runner: _CountingRunner
) -> list[dict[str, object]]:
    """One task through the rig, acceptance stubbed to always pass."""
    task = breadth.bundle.load_tasks(["t01"])[0]
    monkeypatch.setattr(
        breadth,
        "parse_reply",
        lambda text, **kwargs: ParsedFile(content="export const x = 1;\n"),
    )
    monkeypatch.setattr(
        breadth.bundle,
        "run_acceptance",
        lambda task, content, workdir: breadth.bundle.Acceptance(True, ""),
    )
    rows: list[dict[str, object]] = breadth.measure_task(
        task, runner, "test-model", tmp_path / "work", tmp_path / "cand", set()
    )
    return rows


def test_every_draw_runs_even_when_the_first_passes(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A pass never ends the task: 1 greedy + DRAWS sampled rows, always."""
    runner = _CountingRunner()
    rows = _measure_one(tmp_path, monkeypatch, runner)
    assert len(rows) == 1 + breadth.DRAWS
    assert len(runner.requests) == 1 + breadth.DRAWS
    assert all(row["passed"] for row in rows)


def test_arms_carry_their_temperatures(tmp_path: Path, monkeypatch: Any) -> None:
    runner = _CountingRunner()
    rows = _measure_one(tmp_path, monkeypatch, runner)
    assert runner.requests[0].temperature == breadth.GREEDY_TEMPERATURE
    assert all(
        request.temperature == breadth.SAMPLED_TEMPERATURE
        for request in runner.requests[1:]
    )
    assert all(request.quality_sensitive for request in runner.requests)
    assert [row["arm"] for row in rows] == ["greedy"] + ["sampled"] * breadth.DRAWS
    assert [row["draw"] for row in rows] == [0, *range(breadth.DRAWS)]


def test_candidates_are_kept_even_when_the_parser_refuses(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A refused reply is still corpus: the raw text lands beside the rows."""
    from mcgyvr.worker.reply import ReplyError

    runner = _CountingRunner()
    task = breadth.bundle.load_tasks(["t01"])[0]
    monkeypatch.setattr(
        breadth,
        "parse_reply",
        lambda text, **kwargs: ReplyError(code="refused", message="no"),
    )
    rows = breadth.measure_task(
        task, runner, "test-model", tmp_path / "work", tmp_path / "cand", set()
    )
    assert all(row["parse_error"] == "refused" for row in rows)
    assert all(not row["passed"] for row in rows)
    kept = sorted(p.name for p in (tmp_path / "cand" / task.id).iterdir())
    assert kept == sorted(f"{arm}-{draw}.txt" for arm, draw, _ in breadth.draw_plan())


def test_resume_skips_recorded_draws(tmp_path: Path, monkeypatch: Any) -> None:
    rows_path = tmp_path / "results.jsonl"
    recorded = [
        {"task": "t01", "arm": "greedy", "draw": 0},
        {"task": "t01", "arm": "sampled", "draw": 2},
    ]
    rows_path.write_text(
        "".join(json.dumps(row) + "\n" for row in recorded), encoding="utf-8"
    )
    already = breadth.done_keys(rows_path)
    assert already == {
        ("t01", "greedy", 0),
        ("t01", "sampled", 2),
    }
    runner = _CountingRunner()
    task = breadth.bundle.load_tasks(["t01"])[0]
    monkeypatch.setattr(
        breadth,
        "parse_reply",
        lambda text, **kwargs: ParsedFile(content="export const x = 1;\n"),
    )
    monkeypatch.setattr(
        breadth.bundle,
        "run_acceptance",
        lambda task, content, workdir: breadth.bundle.Acceptance(True, ""),
    )
    rows = breadth.measure_task(
        task, runner, "test-model", tmp_path / "work", tmp_path / "cand", already
    )
    assert len(rows) == breadth.DRAWS - 1  # 4 sampled draws remain
    assert {(row["arm"], row["draw"]) for row in rows} == {
        ("sampled", 0),
        ("sampled", 1),
        ("sampled", 3),
        ("sampled", 4),
    }


def _sampled_rows(task: str, outcomes: list[bool | None]) -> list[dict[str, Any]]:
    """Rows for one task's sampled arm; ``None`` marks a dispatch error."""
    rows: list[dict[str, Any]] = []
    for draw, outcome in enumerate(outcomes):
        row: dict[str, Any] = {"task": task, "arm": "sampled", "draw": draw}
        if outcome is None:
            row |= {"passed": False, "dispatch_error": "RunnerError: down"}
        else:
            row |= {"passed": outcome}
        rows.append(row)
    return rows


def test_first_pass_indices_and_their_refusals() -> None:
    rows: list[dict[str, Any]] = []
    rows += _sampled_rows("t-first", [True, True, False, False, False])
    rows += _sampled_rows("t-late", [False, False, False, True, False])
    rows += _sampled_rows("t-never", [False, False, False, False, False])
    rows += _sampled_rows("t-errored", [False, None, False, False, True])
    rows += _sampled_rows("t-partial", [False, True])
    rows.append({"task": "t-first", "arm": "greedy", "draw": 0, "passed": False})

    indices = breadth.first_pass_indices(rows)
    assert indices == {"t-first": 0, "t-late": 3, "t-never": None}


def test_summarise_reports_the_distribution(tmp_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    rows += _sampled_rows("t-first", [True, False, False, False, False])
    rows += _sampled_rows("t-late", [False, False, True, False, False])
    rows += _sampled_rows("t-never", [False] * 5)
    for row in rows:
        row |= {"latency_s": 2.0, "acceptance_s": 0.5}
    rows.append({"task": "t-first", "arm": "greedy", "draw": 0, "passed": True})
    rows_path = tmp_path / "results.jsonl"
    rows_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    text = breadth.summarise(rows_path)
    assert "greedy" in text and "1/1 pass" in text
    assert "3 tasks" in text and "2 with any pass" in text
    assert "| 0 | 1 | 1/3 |" in text
    assert "| 2 | 1 | 2/3 |" in text
    assert "| none | 1 | — |" in text
    assert "2.0s dispatch + 0.5s acceptance" in text
