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

import dataclasses
import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.runner import Completion, Request, StopReason
from mcgyvr.serving import gatelib
from mcgyvr.worker.reply import ParsedFile


@pytest.fixture(autouse=True)
def _no_rig(monkeypatch: Any) -> None:
    """No test here reaches a rig: the door's transport answers "unreachable".

    ``tools/breadth/measure.py`` reads the card through ``pin.py`` ->
    ``contract.ssh`` -> ``gatelib.ssh``, the one transport, which refuses
    outside a door run. Before the door owned the transport a real ``ssh test``
    simply failed and ``contract.ssh`` recorded the absent reading as ``None``;
    this stub is that same absent host, so the rig tests keep exercising the
    draw plan, the resume and the dispatch-error path and never the transport.
    """

    def unreachable(
        host: str, command: str, timeout: float = 120.0, *, input: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([host, command], 255, "", "unreachable")

    monkeypatch.setattr(gatelib, "ssh", unreachable)


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
        breadth.score,
        "score",
        # Since #113 the rig scores through `Gate.run`, so the seam these rig
        # tests stub is the scorer rather than the acceptance command. They
        # exercise the draw plan, the resume and the dispatch-error path — none
        # of which is about whether a candidate is any good — so the verdict is
        # held at "passed" and the scoring itself is tested in
        # tests/test_bench_score.py.
        lambda task, content, sandbox, gate=None: breadth.score.Verdict(
            passed=True, rejected_by=None, findings=(), environment_issues=()
        ),
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
        breadth.score,
        "score",
        # Since #113 the rig scores through `Gate.run`, so the seam these rig
        # tests stub is the scorer rather than the acceptance command. They
        # exercise the draw plan, the resume and the dispatch-error path — none
        # of which is about whether a candidate is any good — so the verdict is
        # held at "passed" and the scoring itself is tested in
        # tests/test_bench_score.py.
        lambda task, content, sandbox, gate=None: breadth.score.Verdict(
            passed=True, rejected_by=None, findings=(), environment_issues=()
        ),
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
    # Since #113 a rate is not stated without a subject, and a real run
    # directory always carries one — a manifest-less directory gets the refusal
    # instead, which `test_a_rate_is_refused_without_a_subject` pins.
    (tmp_path / "run.json").write_text(
        json.dumps(
            {
                "model": "test-model",
                "endpoint": "http://test:11434",
                "serving_build": "0.0.0",
                "tier": "d1",
                "condition": "stock",
                "draws": 5,
            }
        ),
        encoding="utf-8",
    )
    text = breadth.summarise(rows_path)
    assert "test-model" in text and "single-tier" in text
    assert "greedy" in text and "1/1 pass" in text
    assert "3 tasks" in text and "2 with any pass" in text
    assert "| 0 | 1 | 1/3 |" in text
    assert "| 2 | 1 | 2/3 |" in text
    assert "| none | 1 | — |" in text
    assert "2.0s dispatch + 0.5s acceptance" in text


def test_a_rate_is_refused_without_a_subject(tmp_path: Path) -> None:
    """#113: a pass rate that names no model on no rig names nothing.

    The refusal is the report — completeness and a row count, and no figure
    that could be quoted out of the directory later.
    """
    rows_path = tmp_path / "results.jsonl"
    rows_path.write_text(
        json.dumps({"task": "t", "arm": "greedy", "draw": 0, "passed": True}) + "\n",
        encoding="utf-8",
    )
    text = breadth.summarise(rows_path)
    assert "NO RATE" in text
    assert "model" in text and "endpoint" in text
    assert "pass" not in text.split("NO RATE")[1].split("rows on disk")[0].replace(
        "A pass rate names a model on a rig under a bar or it names nothing", ""
    )


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
        breadth.score,
        "score",
        # Since #113 the rig scores through `Gate.run`, so the seam these rig
        # tests stub is the scorer rather than the acceptance command. They
        # exercise the draw plan, the resume and the dispatch-error path — none
        # of which is about whether a candidate is any good — so the verdict is
        # held at "passed" and the scoring itself is tested in
        # tests/test_bench_score.py.
        lambda task, content, sandbox, gate=None: breadth.score.Verdict(
            passed=True, rejected_by=None, findings=(), environment_issues=()
        ),
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


def _sweep_argv(out: Path, tasks: str, draws: int = 1, tier: str = "d1") -> list[str]:
    return [
        "measure.py",
        "--tier",
        tier,
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


def _scorable_arm(monkeypatch: Any) -> None:
    """Say the JS/TS environment is present, because this is not about it.

    ``main`` refuses to dispatch twice over: on a machine whose Node cannot
    import a ``.ts`` file directly, and on one where a declared rung cannot
    reject. Both refusals are right — twenty red rows from a missing runtime
    look exactly like a model that cannot write the language, and a rate scored
    by fewer rungs than it declares is worse than no rate. Neither is what these
    tests are about: they are about which cells hold an observation, and nothing
    in them scores anything.

    So both are neutralised here, and the second one has to be. **BUILD-05 runs
    the whole suite against the documented bootstrap on a clean checkout**, which
    installs Python tooling and nothing else — so a rig test that needs eslint on
    PATH does not fail on its own subject, it fails the clean-checkout contract.
    The preflight's own behaviour is tested in ``tests/test_bench_score.py``,
    where the toolchain is a declared precondition rather than an accident of the
    machine.
    """
    monkeypatch.setattr(
        breadth.bundle,
        "JSTS",
        dataclasses.replace(breadth.bundle.JSTS, capability=lambda: None),
    )
    monkeypatch.setattr(breadth.score, "require_rungs", lambda tasks, gate=None: None)


def _always_passes(monkeypatch: Any) -> None:
    """Parse and scoring stubbed out: this is about cells, not verdicts.

    The preflight goes with them, and it has to. ``score.require_rungs`` proves
    a rung can *reject* by scoring a deliberately malformed canary — through
    the same ``score.score`` these tests hold at "passed". With the scorer
    stubbed the canary passes by construction, the preflight correctly reports
    an instrument that cannot fail, and ``main`` refuses before dispatching a
    single draw. Stubbing one without the other tests neither.
    """
    monkeypatch.setattr(breadth.score, "require_rungs", lambda tasks, gate=None: None)
    monkeypatch.setattr(
        breadth,
        "parse_reply",
        lambda text, **kwargs: ParsedFile(content="export const x = 1;\n"),
    )
    monkeypatch.setattr(
        breadth.score,
        "score",
        # Since #113 the rig scores through `Gate.run`, so the seam these rig
        # tests stub is the scorer rather than the acceptance command. They
        # exercise the draw plan, the resume and the dispatch-error path — none
        # of which is about whether a candidate is any good — so the verdict is
        # held at "passed" and the scoring itself is tested in
        # tests/test_bench_score.py.
        lambda task, content, sandbox, gate=None: breadth.score.Verdict(
            passed=True, rejected_by=None, findings=(), environment_issues=()
        ),
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
    _scorable_arm(monkeypatch)
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
    _scorable_arm(monkeypatch)
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
    _scorable_arm(monkeypatch)
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


def test_the_condition_the_run_records_is_the_condition_it_dispatched(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """#225, and the cap's test one level on: the two halves must not drift.

    ``--condition`` reached ``measure_task`` and not ``record_run``, so every
    ablated sweep wrote ``"condition": "stock"`` beside rows drawn without a
    scaffold. Nothing failed loudly — the rows were right and the manifest was
    wrong — and the resume refusal written to catch exactly this would have
    waved through a directory holding two renders, because the field it
    compares never carried anything but the default. Eight run directories
    were mislabelled that way before a reader noticed — every ablated cell of
    #225's scaffold experiment, on both models.

    The two assertions are deliberately the pair: what the manifest says, and
    what the worker was actually sent. Either alone is the defect.
    """
    out = tmp_path / "run"
    runner = _CountingRunner()
    _scorable_arm(monkeypatch)
    _always_passes(monkeypatch)
    monkeypatch.setattr(breadth, "runner_for", lambda endpoint: runner)
    # A bench tier, so `record_run` would otherwise refuse a tree that has
    # drifted off the open round (#231 check 3). That refusal has its own
    # tests; this one is about `--condition` reaching the manifest.
    monkeypatch.setattr(
        breadth.product, "require_pinned", lambda *a, **k: ("r-test", "0" * 64)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            *_sweep_argv(out, "b002-option-pairs", tier="bench-ts"),
            "--condition",
            breadth.NO_SCAFFOLD,
        ],
    )
    assert breadth.main() == 0

    recorded = json.loads((out / "run.json").read_text())
    assert recorded["condition"] == breadth.NO_SCAFFOLD

    assert runner.requests, "the fixture must dispatch at least one draw"
    assert all(
        "CURRENT CONTENT" not in request.prompt for request in runner.requests
    ), "the ablated section reached the worker's prompt, or this proves nothing"


def test_rows_drawn_against_another_serving_build_refuse_to_join_the_run(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """ADR-0024: the build that served the draws is identity, not a footnote.

    srv1 and srv2 were on ollama 0.32.4 and 0.32.5 while #225's scaffold
    ablation ran the 3B on one and the 7B on the other, so the campaign's one
    cross-model contrast carried an unrecorded serving difference. A rate is
    quotable against a build or it is not quotable.
    """
    invocation = {"started": "2026-08-11T00:00:00+00:00", "tasks": ["t01"]}
    monkeypatch.setattr(breadth, "serving_build", lambda endpoint: "0.32.4")
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)
    assert json.loads((tmp_path / "run.json").read_text())["serving_build"] == "0.32.4"

    monkeypatch.setattr(breadth, "serving_build", lambda endpoint: "0.32.5")
    try:
        breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)
    except breadth.bundle.MeasureError as exc:
        assert "serving_build" in str(exc)
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError("a build change was allowed to resume")


def test_a_manifest_written_before_the_build_was_recorded_still_resumes(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """Every run directory already on disk predates the field.

    Refusing them would buy nothing — the build they were served by is not
    recoverable from the manifest either way — and would strand exactly the
    sweeps whose rows the campaign still reads. The protection is for runs made
    from here on, so an absent field adopts the current value instead.
    """
    invocation = {"started": "2026-08-11T00:00:00+00:00", "tasks": ["t01"]}
    monkeypatch.setattr(breadth, "serving_build", lambda endpoint: None)
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)
    manifest = tmp_path / "run.json"
    aged = json.loads(manifest.read_text())
    del aged["serving_build"]
    manifest.write_text(json.dumps(aged), encoding="utf-8")

    monkeypatch.setattr(breadth, "serving_build", lambda endpoint: "0.32.5")
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)
    assert json.loads(manifest.read_text())["serving_build"] == "0.32.5"


def test_an_endpoint_that_will_not_name_its_build_records_that_it_did_not(
    monkeypatch: Any,
) -> None:
    """Unknown is a value; a guess is not.

    The probe is best-effort against a host that may not be ollama at all, and
    the failure it must not have is inventing a build for a run that has none.
    """

    def refuses(url: str, timeout: float) -> Any:
        raise OSError("no route to host")

    monkeypatch.setattr(breadth.urllib.request, "urlopen", refuses)
    breadth.serving_build.cache_clear()
    assert breadth.serving_build("http://nowhere.invalid:11434") is None
    breadth.serving_build.cache_clear()


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


# --- the three digests reach the manifest (#285) -----------------------------


def _no_endpoint(monkeypatch: Any) -> None:
    """No ollama here, and the manifest must say so rather than omit the fields.

    All THREE fetchers, because the observed capture (#286) reads Prometheus
    text through its own `_get_text` — a separate function by design, since
    routing `/metrics` through a JSON parser would report "did not answer" for
    an endpoint that answered in the format it documents. Patching only the two
    JSON fetchers left every test in this file making a live `/metrics` call
    while reading as offline.
    """
    monkeypatch.setattr(breadth.identity_module, "_get_json", lambda *a, **k: None)
    monkeypatch.setattr(breadth.identity_module, "_post_json", lambda *a, **k: None)
    monkeypatch.setattr(breadth.observed_module, "_get_text", lambda *a, **k: None)


def test_the_manifest_carries_every_digest_field_or_a_stated_null(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """ADR-0027 D2: absent means "predates the contract", so a fresh run has none.

    A run made from here on writes all six fields. Where the world would not
    answer it writes `null` **and the reason**, because a bare null is a state
    a reader cannot act on — "nobody asked" and "it would not say" are different
    facts about a measurement.
    """
    _no_endpoint(monkeypatch)
    invocation = {"started": "2026-08-17T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(tmp_path, _worker(), invocation, tier="d1", draws=2)
    recorded = json.loads((tmp_path / "run.json").read_text())

    for field in (
        *breadth.identity_module.MODEL_PROBE_FIELDS,
        "prompt_sha256",
        "bar_sha256",
    ):
        assert field in recorded, f"{field} is absent, which claims the run predates it"
    reasons = recorded[breadth.identity_module.REFUSALS]
    for field in breadth.identity_module.MODEL_PROBE_FIELDS:
        assert recorded[field] is None
        assert reasons[field]
    # The bar is asserted on the pairing rather than on the value: `d1` is the
    # JS/TS arm, so it resolves where eslint is installed (CI) and refuses where
    # it is not (a bare checkout). Either is correct; a null with no reason, or
    # a digest with one, is not.
    assert (recorded["bar_sha256"] is None) == ("bar_sha256" in reasons)


def test_the_prompt_digest_is_the_render_and_not_the_system_half(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """The defect, measured: on `bench-py`'s 257 contracts `bundle_sha256` is
    ONE value across `stock`, `norule`, `noscaffold` and `planonly`, because
    every one of those levers edits the user message. Four conditions, one
    digest — so the resume refusal that reads it cannot tell a mislabelled cell
    from a correct one, which is how eight directories were mislabelled.
    """
    _no_endpoint(monkeypatch)
    tasks = breadth.load_tier_tasks("bench-py")
    seen = {}
    for condition in (breadth.STOCK, breadth.NO_SCAFFOLD):
        fields, _ = breadth.content_identity(
            tasks, condition=condition, worker=_worker()
        )
        seen[condition] = fields["prompt_sha256"]
    assert len(set(seen.values())) == 2, (
        "the ablation did not move the prompt digest, which is the one thing "
        "it exists to do"
    )


def test_a_digest_absent_from_an_older_directory_is_adopted_forward(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """`serving_build`'s argument: refusing a resume on a key the directory
    could not have carried is a spurious refusal, not a caught one."""
    _no_endpoint(monkeypatch)
    invocation = {"started": "2026-08-17T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)

    path = tmp_path / "run.json"
    older = json.loads(path.read_text())
    for field in (*breadth.identity_module.MODEL_PROBE_FIELDS, "prompt_sha256"):
        older.pop(field, None)
    path.write_text(json.dumps(older))

    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)
    assert len(json.loads(path.read_text())["invocations"]) == 2


def test_a_digest_that_was_null_and_is_now_answered_refuses_the_resume(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """`null` is not absent, and this is the half of the rule that has teeth.

    A directory whose endpoint would not name its weights holds rows measured
    under weights nobody recorded. Appending rows measured under weights
    somebody did would put both in one denominator, and the manifest would
    describe only the second half.

    Driven by replacing `probe_model` rather than the fetcher under it. Since
    2026-09-06 the probe refuses all four of its fields on every endpoint —
    the surface that answered them went with its backend — so no arrangement of
    HTTP stubs can make one of them go from `null` to answered. What is under
    test is `record_run`'s rule, not how the probe reaches its answer, and the
    probe is the seam that supplies the field; the day a surface carries weights
    identity again, this is where it arrives.
    """
    _no_endpoint(monkeypatch)
    invocation = {"started": "2026-08-17T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)

    monkeypatch.setattr(
        breadth.identity_module,
        "probe_model",
        lambda endpoint, model, **k: (
            {field: None for field in breadth.identity_module.MODEL_PROBE_FIELDS}
            | {"model_sha256": "beef"},
            {},
        ),
    )
    with pytest.raises(breadth.bundle.MeasureError, match="model_sha256"):
        breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)


def test_the_reason_block_is_not_compared_as_identity(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """Two invocations that both failed to reach an endpoint may phrase it
    differently — a timeout on one, a refused connection on the next — and that
    is not a second run. What must agree is what the fields say."""
    _no_endpoint(monkeypatch)
    invocation = {"started": "2026-08-17T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)

    path = tmp_path / "run.json"
    recorded = json.loads(path.read_text())
    recorded[breadth.identity_module.REFUSALS] = {"model_sha256": "phrased otherwise"}
    path.write_text(json.dumps(recorded))

    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)
    assert len(json.loads(path.read_text())["invocations"]) == 2


# --- the second block reaches disk beside the first (#286, ADR-0027 D7) ------


def test_the_observed_block_is_written_beside_the_manifest(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """`record_run` is the seam, so both blocks are written from it or neither.

    The four declared fields are present here for the same reason they are
    present in ``run.json``: absent means "predates the contract" (D2), and a
    run made from here on must never produce one. This endpoint answers nothing,
    so all four are `null` with a reason — which is a measurement, not a gap.
    """
    _no_endpoint(monkeypatch)
    invocation = {"started": "2026-08-17T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)

    path = tmp_path / breadth.observed_module.OBSERVED_FILE
    assert path.is_file(), "run.json was written and the observed block was not"
    # Two captures per directory since #286: `at_open` before the first draw,
    # `at_close` when the sweep finishes and the model is certainly resident.
    recorded = json.loads(path.read_text())
    # A capture carries two labelled SOURCES: `native` is what the endpoint said
    # about itself, `host` is what the serving machine said. They prove
    # different things, so they are never merged.
    block = recorded[breadth.observed_module.CAPTURES][breadth.observed_module.AT_OPEN][
        breadth.observed_module.NATIVE_SOURCE
    ]
    assert block["model"] == "test-model"
    for field in breadth.observed_module.PROBE_SET:
        assert field in block
        assert block[breadth.identity_module.REFUSALS][field]


def test_a_resume_does_not_recapture_the_observed_block(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """It describes the endpoint the rows were STARTED against.

    Recapturing on a resume would restate rows this invocation did not measure,
    and a resume against a materially different server is refused by the keyed
    drift check — which is where a refusal belongs, since nothing compares this
    block.
    """
    _no_endpoint(monkeypatch)
    invocation = {"started": "2026-08-17T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)

    path = tmp_path / breadth.observed_module.OBSERVED_FILE
    before = path.read_text()
    path.write_text(json.dumps({"marked": True}))
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)

    assert json.loads(path.read_text()) == {"marked": True}
    assert before != path.read_text()


def test_nothing_in_the_rig_reads_the_observed_block(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """A guard wired to this block would compare a field nobody admitted.

    Proven by removing it: every path that reads a run directory must behave
    identically whether or not the file is there, because the block it holds is
    comprehensive precisely because it is compared by nothing (D7).
    """
    _no_endpoint(monkeypatch)
    invocation = {"started": "2026-08-17T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)
    (tmp_path / breadth.observed_module.OBSERVED_FILE).unlink()

    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)
    assert len(json.loads((tmp_path / "run.json").read_text())["invocations"]) == 2


# --- the resume check is the contract's, over a declared field set (#287) ----


# One fully populated manifest, every declared field obtained, in the manner of
# `tests/test_bench_identity.py`'s fixture. The parametrised cases below iterate
# `breadth.IDENTITY_FIELDS` itself — never a list written out here — and the
# coverage test holds this dict to the declaration so a field added to the
# runner cannot arrive without a refusal case.
_FULL_MANIFEST: dict[str, Any] = {
    "endpoint": "http://srv2:11434",
    "protocol": "openai",
    "model": "qwen2.5-coder:1.5b",
    "serving_build": "0.32.5",
    "tier": "bench-py",
    "draws": 5,
    "greedy_temperature": 0.0,
    "sampled_temperature": 0.7,
    "max_output_tokens": 768,
    "condition": "stock",
    "gate_rungs": ["scope", "secrets", "structured", "adapters", "acceptance"],
    "gate_semantic": False,
    "mode": "single-tier",
    "bundle_sha256": "aa" * 32,
    "tasks_sha256": {"function_implementation": "bb" * 32},
    "prompt_sha256": "cc" * 32,
    "bar_sha256": "dd" * 32,
    "model_sha256": "ee" * 32,
    "vocabulary_sha256": "ff" * 32,
    "merges_sha256": "ab" * 32,
    "template_sha256": "cd" * 32,
    "round": "r1-commissioning",
    "product_sha256": "ef" * 32,
}


def _mutated(value: Any) -> Any:
    """A different value of the same shape, so the refusal is about identity."""
    if value is None:
        return "now-answered"
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "-other"
    if isinstance(value, list):
        return [*value, "other"]
    assert isinstance(value, dict), f"unhandled shape {type(value)}"
    return {**value, "mutation-probe": "x"}


def test_the_fixture_covers_every_declared_field() -> None:
    """The coverage claim, checked rather than asserted in a docstring."""
    assert set(_FULL_MANIFEST) == set(breadth.IDENTITY_FIELDS), (
        "a field joined IDENTITY_FIELDS with no refusal case below, or left it "
        "while the fixture still carries one"
    )


def test_every_declared_field_is_in_the_contract() -> None:
    """#287 defect 3's regression guard, module half: a runner can never again
    record a field `identity.GROUPS` has not heard of — which is how the bundle
    rig guarded its resume on two fields that appeared nowhere in the module."""
    assert set(breadth.IDENTITY_FIELDS) <= set(breadth.identity_module.RECORDED)


def test_the_manifest_keys_are_exactly_the_declared_field_set(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """#287 defect 1: the checked set was whatever the runner happened to write.

    A freshly assembled bench manifest, minus the two annotations and the
    invocation log, carries the declared fields and nothing else. With this
    green, a field added to `identity.GROUPS` and written by this runner
    without joining its drift set fails here — the declaration, the dict and
    the contract can no longer drift apart silently.
    """
    _no_endpoint(monkeypatch)
    monkeypatch.setattr(
        breadth.product, "require_pinned", lambda *a, **k: ("r-test", "0" * 64)
    )
    breadth.record_run(
        tmp_path,
        _worker(),
        {"started": "2026-08-18T00:00:00+00:00", "tasks": []},
        tier="bench-ts",
        draws=0,
    )
    recorded = json.loads((tmp_path / "run.json").read_text())

    annotations = {
        breadth.identity_module.REFUSALS,
        breadth.identity_module.BAR,
        "invocations",
    }
    assert set(recorded) - annotations == set(breadth.IDENTITY_FIELDS)


@pytest.mark.parametrize("field", sorted(breadth.IDENTITY_FIELDS))
def test_a_field_mutated_in_the_previous_manifest_is_drift(field: str) -> None:
    """One direction of the per-field refusal, off the declaration itself."""
    previous = dict(_FULL_MANIFEST)
    previous[field] = _mutated(previous[field])
    drifted = breadth.identity_module.drift(
        previous, dict(_FULL_MANIFEST), fields=breadth.IDENTITY_FIELDS
    )
    assert drifted == [field]


@pytest.mark.parametrize("field", sorted(breadth.IDENTITY_FIELDS))
def test_a_field_the_resuming_invocation_no_longer_writes_is_drift(
    field: str,
) -> None:
    """#287 defect 2: the old comparison walked only the new dict's keys, so a
    field present in `previous` and no longer written resumed silently and the
    manifest kept a stale value describing rows it did not measure.
    `identity.drift` compares state as well as value, so the direction needs no
    new logic — only a field set that is not derived from the new dict."""
    resumed = dict(_FULL_MANIFEST)
    del resumed[field]
    drifted = breadth.identity_module.drift(
        dict(_FULL_MANIFEST), resumed, fields=breadth.IDENTITY_FIELDS
    )
    assert drifted == [field]


def test_the_drift_verdict_still_arrives_as_the_resume_refusal(
    tmp_path: Path, live_instruments: types.ModuleType, monkeypatch: Any
) -> None:
    """The wiring half: `identity.drift`'s verdict is what `record_run` refuses
    on, with the field named in the error. The per-field cases above prove the
    comparison; this proves the runner asks it."""
    _no_endpoint(monkeypatch)
    invocation = {"started": "2026-08-18T00:00:00+00:00", "tasks": ["t01"]}
    breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)

    path = tmp_path / "run.json"
    recorded = json.loads(path.read_text())
    recorded["condition"] = "planonly"
    path.write_text(json.dumps(recorded), encoding="utf-8")

    with pytest.raises(breadth.bundle.MeasureError, match="condition"):
        breadth.record_run(tmp_path, _worker(), dict(invocation), tier="d1", draws=2)
