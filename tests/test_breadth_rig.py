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

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

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


def _worker(model: str = "test-model") -> Any:
    """A worker that names an endpoint without reaching one."""
    return breadth.bundle.Worker(
        endpoint="http://test:11434",
        protocol=breadth.bundle.Protocol.OPENAI,
        model=model,
        api_key_env=None,
    )


def test_a_chosen_sampled_temperature_reaches_every_sampled_draw() -> None:
    """0.7 is inherited, not measured, so the arm's temperature is an input.

    The greedy anchor stays at 0.0 whatever the sampled arm is set to: the two
    arms answer different questions and only one of them is being varied.
    """
    plan = breadth.draw_plan(3, 0.3)
    assert plan[0] == ("greedy", 0, breadth.GREEDY_TEMPERATURE)
    assert [temperature for _, _, temperature in plan[1:]] == [0.3, 0.3, 0.3]
    assert breadth.draw_plan(2)[1][2] == breadth.SAMPLED_TEMPERATURE


def test_rows_drawn_at_another_temperature_refuse_to_join_the_run(
    tmp_path: Path, live_instruments: types.ModuleType
) -> None:
    """Temperature is identity, not a note: two arms are two experiments.

    Without this a second sweep into the same directory would average draws
    taken at 0.3 and at 0.7 into one distribution, and the manifest would
    describe only whichever ran last.
    """
    invocation = {"started": "2026-08-06T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(
        tmp_path,
        _worker(),
        dict(invocation),
        tier="d1",
        draws=2,
        sampled_temperature=0.7,
    )
    assert json.loads((tmp_path / "run.json").read_text())["sampled_temperature"] == 0.7

    try:
        breadth.record_run(
            tmp_path,
            _worker(),
            dict(invocation),
            tier="d1",
            draws=2,
            sampled_temperature=0.3,
        )
    except breadth.bundle.MeasureError as exc:
        assert "sampled_temperature" in str(exc)
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError("a temperature change was allowed to resume")


def test_a_retired_tier_cannot_have_a_run_recorded_for_it(tmp_path: Path) -> None:
    """#240, at the seam every dispatching path passes through.

    ``record_run`` is where a sweep and a campaign both stake their claim to a
    directory, before the first draw. Refusing here — with the real declaration
    rather than the fixture above — is what makes retirement a property of the
    code instead of something the operator has to remember, and it costs
    nothing but the error: the tier still loads, because its contracts are
    released training material now.
    """
    with pytest.raises(breadth.bundle.instruments.RetiredError, match="tier 'd2'"):
        breadth.record_run(
            tmp_path,
            _worker(),
            {"started": "2026-08-10T00:00:00+00:00", "tasks": ["t01"]},
            tier="d2",
        )
    assert not (tmp_path / "run.json").exists()
    assert breadth.load_tier_tasks("d2"), "a retired tier must still load"


def test_the_cli_refuses_a_retired_tier_before_it_resolves_a_worker(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """The operator's version of the same refusal, and it costs no tokens."""
    monkeypatch.setattr(
        sys, "argv", ["measure.py", "--tier", "d1", "--out", str(tmp_path / "run")]
    )
    assert breadth.main() == 2
    assert "retired by #240" in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


def test_the_repaired_task_moves_the_contract_and_never_the_acceptance() -> None:
    """d1r/t20 repairs a defect: the acceptance asserted a declared-unstated case.

    d1's t20 says repeated-key handling "is not stated" and its accept.mjs
    asserts last-wins, so a worker that stopped where the contract told it to
    was scored as failing — t20 passed 0 of 144 draws across ten model-runs.
    The repair states the rule the acceptance already demanded. The invariant
    that keeps it a repair rather than a different task: the acceptance file is
    untouched, byte for byte. Moving the test to meet the workers would be
    lowering the bar; moving the contract to meet the test is telling the truth.
    """
    original = REPO / "tools" / "bundle" / "tasks" / "t20"
    repaired = REPO / "tools" / "breadth" / "tasks" / "d1r" / "t20"
    assert (repaired / "accept.mjs").read_bytes() == (
        original / "accept.mjs"
    ).read_bytes()
    assert (repaired / "reference.ts").read_bytes() == (
        original / "reference.ts"
    ).read_bytes()

    before = breadth.bundle.load_tasks(["t20"])[0].contract
    after = breadth.load_tier_tasks("d1r", ["t20"])[0].contract
    assert any("not stated" in c and "repeated" in c for c in before.stop_conditions)
    assert not any("repeated" in c for c in after.stop_conditions)
    assert after.stop_conditions, "a bug_fix contract still needs its residue"
    assert "last occurrence" in after.task and "last occurrence" not in before.task


def test_variant_tiers_are_not_rungs_of_the_ladder() -> None:
    """The campaign climbs TIERS; a repaired variant must never be climbed into."""
    assert "d1r" not in breadth.TIERS
    assert "d1r" in breadth.VARIANT_TIERS
    assert breadth.load_tier_tasks("d1r")[0].id == "t20"


def _selectivity() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "breadth_selectivity", REPO / "tools" / "breadth" / "selectivity.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_thinning_drops_assertions_and_never_the_setup() -> None:
    """A thin checker must still be a runnable file, or it measures nothing.

    Dropping a fixture along with the assertions would make the weak arm fail
    for a reason that has nothing to do with how much the checker can see.
    """
    selectivity = _selectivity()
    for task in breadth.bundle.load_tasks():
        source = task.accept.read_text(encoding="utf-8")
        total = selectivity.count_assertions(source)
        assert total > 0, f"{task.id} declares no assertion to thin"
        assert selectivity.thin(source, total) == source
        for keep in (1, max(1, total // 2), total):
            thinned = selectivity.thin(source, keep)
            assert selectivity.count_assertions(thinned) == keep
            assert "import assert" in thinned
            assert f'from "./{breadth.bundle.JSTS.solution}"' in thinned
            assert thinned.count("\n") <= source.count("\n")


def test_thinning_keeps_the_authors_order() -> None:
    """Strength s keeps the FIRST s assertions: early cases, not a sample."""
    selectivity = _selectivity()
    task = breadth.bundle.load_tasks(["t20"])[0]
    source = task.accept.read_text(encoding="utf-8")
    one = selectivity.thin(source, 1)
    assert "first pair" in one
    assert "__proto__ must be stored" not in one


def test_the_cap_the_run_records_is_the_cap_the_worker_was_sent(
    tmp_path: Path, monkeypatch: Any, live_instruments: types.ModuleType
) -> None:
    """#216: the cap is a parameter now, and the two halves must not drift.

    Before #212 the cap was a module constant read independently by the
    dispatch path and by ``record_run``. Nothing held them together, so a
    change to one would have produced a manifest that misreported the
    experiment it sat beside — and #212 spent a lane on refusal rates that
    turned out to describe the instrument. A record that lies about its own
    cap is the same failure one level down.
    """
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
    breadth.measure_task(
        task,
        runner,
        "test-model",
        tmp_path / "work",
        tmp_path / "cand",
        set(),
        plan=breadth.draw_plan(1),
        max_output_tokens=2048,
    )
    assert runner.requests, "the fixture must dispatch at least one draw"
    assert all(request.max_output_tokens == 2048 for request in runner.requests)

    breadth.record_run(
        tmp_path,
        _worker(),
        {"started": "2026-08-08T00:00:00+00:00", "tasks": ["t01"]},
        tier="d1",
        draws=1,
        max_output_tokens=2048,
    )
    recorded = json.loads((tmp_path / "run.json").read_text())
    assert recorded["max_output_tokens"] == 2048
    assert recorded["max_output_tokens"] == runner.requests[0].max_output_tokens


def test_rows_drawn_under_another_cap_refuse_to_join_the_run(
    tmp_path: Path, live_instruments: types.ModuleType
) -> None:
    """A cap change is a new experiment, exactly as a temperature change is.

    Truncation is the outcome the cap decides, so averaging draws taken at 768
    with draws taken at 2048 would mix two different refusal rates into one
    number and the manifest would name only the last.
    """
    invocation = {"started": "2026-08-08T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(
        tmp_path, _worker(), dict(invocation), tier="d1", draws=2, max_output_tokens=768
    )
    try:
        breadth.record_run(
            tmp_path,
            _worker(),
            dict(invocation),
            tier="d1",
            draws=2,
            max_output_tokens=2048,
        )
    except breadth.bundle.MeasureError as exc:
        assert "max_output_tokens" in str(exc)
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError("a cap change was allowed to resume")


# --- #217: a dispatch error occupies its cell, so a resume can never fill it ---


class _DeadRunner:
    """A backend that has gone away — every draw fails below the model."""

    def generate(self, model: str, request: Request) -> Completion:
        raise breadth.RunnerError(
            "could not reach http://test:11434/v1/chat/completions within 120s"
        )


def _sweep_argv(out: Path, tasks: str, draws: int = 1) -> list[str]:
    return [
        "measure.py",
        "--tier",
        "d1",
        "--tasks",
        tasks,
        "--out",
        str(out),
        "--endpoint",
        "http://test:11434",
        "--protocol",
        "openai",
        "--model",
        "test-model",
        "--draws",
        str(draws),
    ]


def _always_passes(monkeypatch: Any) -> None:
    """Parse and acceptance stubbed out: this is about cells, not verdicts."""
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


def test_a_dispatch_error_does_not_fill_the_cell_it_occupies(tmp_path: Path) -> None:
    """The defect itself, at the function that had it.

    ``done_keys`` counted any row as a recorded cell, so the row that says
    "this draw reached no worker" was indistinguishable from one that says
    what the worker replied — and a resume skipped it forever.
    """
    rows_path = tmp_path / "results.jsonl"
    rows_path.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in [
                {"task": "t01", "arm": "greedy", "draw": 0, "passed": True},
                {
                    "task": "t01",
                    "arm": "sampled",
                    "draw": 0,
                    "passed": False,
                    "dispatch_error": "TransportError: could not reach",
                },
            ]
        ),
        encoding="utf-8",
    )
    assert breadth.done_keys(rows_path) == {("t01", "greedy", 0)}


def test_the_backend_going_away_stops_the_run_and_the_directory_says_so(
    tmp_path: Path, monkeypatch: Any, capsys: Any, live_instruments: types.ModuleType
) -> None:
    """#217's third question, answered as a run-level circuit breaker.

    51 consecutive tasks of identical 120s timeouts cost five hours to learn
    one fact. The breaker stops at three, which cannot fire on a healthy
    backend because it needs *every* draw of three consecutive tasks to fail
    below the model. What it must not do is hide the shortfall: the run exits
    non-zero, ``run.json`` names the cells nobody observed, and the summary
    says so before it says anything a reader might quote.
    """
    out = tmp_path / "run"
    monkeypatch.setattr(breadth, "runner_for", lambda endpoint: _DeadRunner())
    monkeypatch.setattr(sys, "argv", _sweep_argv(out, "t01,t02,t03,t04,t05"))

    assert breadth.main() == 1
    assert "the backend went away at task t03" in capsys.readouterr().err

    rows = breadth.read_rows(out / "results.jsonl")
    assert len(rows) == 6, "three tasks x (greedy + one sampled), then it stopped"
    assert all(row.get("dispatch_error") for row in rows)

    completeness = json.loads((out / "run.json").read_text())["completeness"]
    assert completeness == {
        "expected": 10,
        "recorded": 0,
        "missing": 10,
        "complete": False,
        "missing_cells": sorted(
            f"t0{n}/{arm}/0" for n in range(1, 6) for arm in ("greedy", "sampled")
        ),
    }
    assert (out / "summary.md").read_text().startswith("**INCOMPLETE — 10 cell(s)")


def test_the_identical_command_refills_what_the_outage_lost(
    tmp_path: Path, monkeypatch: Any, capsys: Any, live_instruments: types.ModuleType
) -> None:
    """The acceptance criterion, end to end and by the same command twice.

    Before this, the second run printed ``resuming: N draws already recorded``
    and dispatched nothing — the hole was permanent at exit 0 with the
    expected line count. The displaced rows are not discarded to achieve it:
    they are kept verbatim in a sidecar and the rewrite is recorded against
    the invocation that did it.
    """
    out = tmp_path / "run"
    argv = _sweep_argv(out, "t01,t02")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(breadth, "runner_for", lambda endpoint: _DeadRunner())
    assert breadth.main() == 1
    capsys.readouterr()

    # The identical command, against a backend that has come back.
    monkeypatch.setattr(breadth, "runner_for", lambda endpoint: _CountingRunner())
    _always_passes(monkeypatch)
    assert breadth.main() == 0
    assert "retrying 4 draw(s) that reached no worker" in capsys.readouterr().err

    rows = breadth.read_rows(out / "results.jsonl")
    assert len(rows) == 4, "one row per cell — no cell carries two"
    assert not any(row.get("dispatch_error") for row in rows)
    assert {(row["task"], row["arm"], row["draw"]) for row in rows} == {
        (task, arm, 0) for task in ("t01", "t02") for arm in ("greedy", "sampled")
    }

    sidecar = out / breadth.DISPATCH_ERROR_SIDECAR.format(n=1)
    assert len(breadth.read_rows(sidecar)) == 4, "the lost draws are kept, not dropped"

    recorded = json.loads((out / "run.json").read_text())
    assert recorded["completeness"]["complete"] is True
    assert recorded["invocations"][1]["retried_dispatch_errors"] == 4
    assert recorded["invocations"][1]["quarantined_to"] == sidecar.name
    assert "retried_dispatch_errors" not in recorded["invocations"][0]
    assert (
        (out / "summary.md")
        .read_text()
        .startswith("complete: an observation reached every cell.")
    )


def test_the_quarantine_is_what_keeps_the_pin_join_total(
    tmp_path: Path, monkeypatch: Any, live_instruments: types.ModuleType
) -> None:
    """Acceptance: ``pin.py``'s (task, arm, draw) join survives the mechanism.

    It survives because a dispatch error writes no candidate file, so no
    capture ever pointed at a row the quarantine removes. The rejected
    mechanism is the interesting half: ``_join_candidate`` returns the *first*
    matching row, and a dispatch-error row carries no ``stop_reason`` — so
    last-row-wins would not merely mis-join, it would take the corpus down
    with a ``KeyError`` where every other provenance failure raises a
    diagnosable ``PinError``.
    """
    spec = importlib.util.spec_from_file_location(
        "replies_pin", REPO / "tools" / "replies" / "pin.py"
    )
    assert spec is not None and spec.loader is not None
    pin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pin)

    out = tmp_path / "run"
    argv = _sweep_argv(out, "t01")
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(breadth, "runner_for", lambda endpoint: _DeadRunner())
    assert breadth.main() == 1
    assert not list(out.glob("candidates/*/*.txt")), "a lost draw captures nothing"

    monkeypatch.setattr(breadth, "runner_for", lambda endpoint: _CountingRunner())
    _always_passes(monkeypatch)
    assert breadth.main() == 0

    rows = breadth.read_rows(out / "results.jsonl")
    captures = sorted(out.glob("candidates/*/*.txt"))
    assert captures, "the refilled cells captured their replies"
    for path in captures:
        joined = pin._join_candidate(path, rows)
        assert joined["stop_reason"]
        assert joined["row_sha"] == hashlib.sha256(path.read_bytes()).hexdigest()

    # And the shape the quarantine prevented: the error row, matched first.
    displaced = breadth.read_rows(out / breadth.DISPATCH_ERROR_SIDECAR.format(n=1))
    with pytest.raises(KeyError):
        pin._join_candidate(captures[0], displaced + rows)


def test_a_run_directory_this_rig_did_not_write_is_not_judged(tmp_path: Path) -> None:
    """ "Complete" and "unanswerable" are different verdicts.

    The bundle rig's runs are shaped by condition rather than by draw, so its
    manifests imply no cell grid. Returning ``[]`` for one would report it
    complete, which is a claim nothing here is entitled to make.
    """
    (tmp_path / "run.json").write_text(
        json.dumps({"model": "m", "conditions_sha256": {"c0": "x"}}), encoding="utf-8"
    )
    assert breadth.missing_cells(tmp_path) is None
    assert breadth.missing_cells(tmp_path / "absent") is None


def test_a_task_the_resume_skipped_never_advances_the_breaker() -> None:
    """No rows is not the same fact as no observations.

    A resumed run walks every task and returns nothing for the ones already
    filled; counting those toward the dead streak would abort a healthy resume
    three tasks in.
    """
    assert breadth.task_lost_every_draw([]) is False
    assert breadth.task_lost_every_draw([{"passed": True}]) is False
    assert breadth.task_lost_every_draw([{"dispatch_error": "down"}]) is True
    assert (
        breadth.task_lost_every_draw([{"dispatch_error": "down"}, {"passed": False}])
        is False
    )
