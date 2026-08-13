"""The matrix report, and the two comparisons it refuses to make (#113).

A report is where a number stops being a row and starts being quotable, so the
things worth pinning are the refusals rather than the formatting:

* a cell whose manifest cannot name a model, a rig and a bar gets no rate — a
  pass rate that names nothing is not a result;
* two cells that differ in anything but their condition are not laid beside
  each other. That is the defect #189 shipped, folding a backend change into a
  weights contrast, and the one ADR-0024 closes.

And two absences must be stated rather than defaulted:

* the interaction term is **absent** rather than zero when a single-lever arm is
  missing, because zero is a finding and absence is not;
* the reproducibility bound is **not declared** rather than omitted when no null
  has been measured for this model, tier, bar and build — a delta smaller than
  an undeclared drift is not a small effect, it is an unknown one.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def report() -> Any:
    return _by_path("bench_report_t", REPO / "tools" / "bench" / "report.py")


def _cell(
    tmp_path: Path,
    condition: str,
    passed: int,
    n: int = 10,
    **manifest_overrides: Any,
) -> Path:
    directory = tmp_path / condition
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model": "qwen2.5-coder:1.5b",
        "endpoint": "http://srv2:11434",
        "serving_build": "0.32.5",
        "tier": "bench-py",
        "condition": condition,
        "draws": 0,
        "gate_rungs": ["scope", "secrets", "structured", "adapters", "acceptance"],
    }
    manifest.update(manifest_overrides)
    (directory / "run.json").write_text(json.dumps(manifest))
    rows = [
        {
            "task": f"t{i:03d}",
            "arm": "greedy",
            "draw": 0,
            "passed": i < passed,
            "prompt_tokens": 700,
            "completion_tokens": 150,
            "rejected_by": None if i < passed else "acceptance",
        }
        for i in range(n)
    ]
    (directory / "results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n"
    )
    return directory


# --- what it refuses --------------------------------------------------------


def test_a_cell_that_cannot_name_its_subject_gets_no_rate(
    report: Any, tmp_path: Path
) -> None:
    directory = _cell(tmp_path, "stock", 3)
    manifest = json.loads((directory / "run.json").read_text())
    del manifest["model"]
    (directory / "run.json").write_text(json.dumps(manifest))
    with pytest.raises(report.ReportError, match="model"):
        report.read_cell(directory)


def test_an_unknown_build_is_reported_rather_than_refused(
    report: Any, tmp_path: Path
) -> None:
    """`serving_build()` returns None for an endpoint that will not say, and its
    own docstring calls that "not one this project refuses to measure". So an
    unknown build states itself; what must not happen is two builds in one
    table, which `require_comparable` catches separately.
    """
    text = report.render(
        [report.read_cell(_cell(tmp_path, "stock", 3, serving_build=None))]
    )
    assert "build unknown" in text


def test_cells_from_two_builds_are_not_laid_beside_each_other(
    report: Any, tmp_path: Path
) -> None:
    """ADR-0024's confound: an ollama patch release nothing on disk recorded."""
    cells = [
        report.read_cell(_cell(tmp_path, "stock", 3)),
        report.read_cell(_cell(tmp_path, "planonly", 5, serving_build="0.32.4")),
    ]
    with pytest.raises(report.ReportError, match="serving_build"):
        report.render(cells)


def test_cells_from_two_models_are_not_laid_beside_each_other(
    report: Any, tmp_path: Path
) -> None:
    cells = [
        report.read_cell(_cell(tmp_path, "stock", 3)),
        report.read_cell(_cell(tmp_path, "planonly", 5, model="qwen2.5-coder:7b")),
    ]
    with pytest.raises(report.ReportError, match="model"):
        report.render(cells)


def test_cells_scored_by_different_rungs_are_not_laid_beside_each_other(
    report: Any, tmp_path: Path
) -> None:
    """A pre-#113 run and a gate-scored run measure different things."""
    cells = [
        report.read_cell(_cell(tmp_path, "stock", 3)),
        report.read_cell(_cell(tmp_path, "planonly", 5, gate_rungs=None)),
    ]
    with pytest.raises(report.ReportError, match="gate_rungs"):
        report.render(cells)


# --- what it states ---------------------------------------------------------


def test_the_report_names_model_rig_and_bar(report: Any, tmp_path: Path) -> None:
    text = report.render([report.read_cell(_cell(tmp_path, "stock", 3))])
    assert "qwen2.5-coder:1.5b" in text
    assert "srv2" in text
    assert "0.32.5" in text
    assert "Gate.run" in text


def test_every_figure_declares_single_tier(report: Any, tmp_path: Path) -> None:
    """With escalation live a floor failure is rescued and the floor is invisible."""
    text = report.render([report.read_cell(_cell(tmp_path, "stock", 3))])
    assert "single-tier" in text


def test_both_outcome_axes_are_reported(report: Any, tmp_path: Path) -> None:
    """Pass rate alone cannot rank levers — ADR-0018's two axes."""
    text = report.render([report.read_cell(_cell(tmp_path, "stock", 3))])
    assert "prompt" in text and "completion" in text
    assert "700" in text and "150" in text


def test_a_run_with_no_baseline_states_no_contrast(report: Any, tmp_path: Path) -> None:
    text = report.render([report.read_cell(_cell(tmp_path, "planonly", 5))])
    assert "No baseline cell" in text


# --- the interaction term ---------------------------------------------------


def test_the_interaction_term_is_stated_for_a_multi_lever_cell(
    report: Any, tmp_path: Path
) -> None:
    """stock 3/10, planonly 2/10, norule 4/10, combined 2/10.

    Singles are -10pp and +10pp, summing to zero; combined is -10pp, so the
    interaction is -10pp — the levers overlap on this set.
    """
    cells = [
        report.read_cell(_cell(tmp_path, "stock", 3)),
        report.read_cell(_cell(tmp_path, "planonly", 2)),
        report.read_cell(_cell(tmp_path, "norule", 4)),
        report.read_cell(_cell(tmp_path, "planonly+norule", 2)),
    ]
    text = report.render(cells)
    assert "## Interaction" in text
    assert "interaction -10.0pp" in text
    assert "overlapping" in text


def test_the_interaction_term_is_absent_when_a_single_is_missing(
    report: Any, tmp_path: Path
) -> None:
    """A gap in the matrix is not evidence that two levers are additive."""
    cells = [
        report.read_cell(_cell(tmp_path, "stock", 3)),
        report.read_cell(_cell(tmp_path, "planonly", 2)),
        report.read_cell(_cell(tmp_path, "planonly+norule", 2)),
    ]
    text = report.render(cells)
    assert "not stated" in text
    assert "not evidence" in text


# --- the reproducibility bound ----------------------------------------------


def _bound(**overrides: Any) -> dict[str, Any]:
    entry = {
        "model": "qwen2.5-coder:1.5b",
        "tier": "bench-py",
        "gate_rungs": ["scope", "secrets", "structured", "adapters", "acceptance"],
        "serving_build": "0.32.5",
        "bound_pp": 2.0,
        "flips": 1,
        "cells": 514,
        "runs": ["bench-null-a-2026-08-12", "bench-null-b-2026-08-12"],
        "issue": 231,
        "measured": "2026-08-12",
    }
    entry.update(overrides)
    return entry


def _declare(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *bounds: Any
) -> None:
    path = tmp_path / "reproducibility.json"
    path.write_text(json.dumps({"bounds": list(bounds)}))
    monkeypatch.setattr(report, "REPRO_FILE", path)


def test_the_declaration_this_repository_ships_loads(report: Any) -> None:
    """Whatever is declared, it is declared in a shape the report can read."""
    report.load_bounds()


def test_an_undeclared_bound_is_stated_rather_than_omitted(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _declare(report, monkeypatch, tmp_path)
    text = report.render([report.read_cell(_cell(tmp_path, "stock", 3))])
    assert "reproducibility: **not declared**" in text
    assert "#231" in text
    assert "unqualified" in text


def test_a_declared_bound_names_the_two_runs_it_came_from(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _declare(report, monkeypatch, tmp_path, _bound())
    text = report.render([report.read_cell(_cell(tmp_path, "stock", 3))])
    assert "reproducibility: **±2.0pp**" in text
    assert "bench-null-a-2026-08-12" in text
    assert "1 of 514 paired cells" in text


def test_a_delta_inside_the_bound_is_marked_as_the_instrument(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """30/100 against 31/100 is +1.0pp, and two identical runs move 2.0pp."""
    _declare(report, monkeypatch, tmp_path, _bound())
    cells = [
        report.read_cell(_cell(tmp_path, "stock", 30, n=100)),
        report.read_cell(_cell(tmp_path, "planonly", 31, n=100)),
    ]
    text = report.render(cells)
    assert "+1.0pp†" in text
    assert "the contrast is the instrument and not the lever" in text


def test_a_delta_outside_the_bound_is_left_unmarked(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _declare(report, monkeypatch, tmp_path, _bound())
    cells = [
        report.read_cell(_cell(tmp_path, "stock", 30, n=100)),
        report.read_cell(_cell(tmp_path, "planonly", 40, n=100)),
    ]
    text = report.render(cells)
    assert "+10.0pp |" in text
    assert "pp†" not in text
    assert "inside the declared reproducibility bound" not in text


def test_a_null_measured_under_a_different_bar_does_not_describe_this_run(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A bar that scores differently produces a different null."""
    _declare(report, monkeypatch, tmp_path, _bound(gate_rungs=["acceptance"]))
    text = report.render([report.read_cell(_cell(tmp_path, "stock", 3))])
    assert "not declared" in text
    assert "gate_rungs" in text


def test_a_null_measured_on_a_different_build_does_not_describe_this_run(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR-0024: an ollama patch release moved results and nothing recorded it."""
    _declare(report, monkeypatch, tmp_path, _bound(serving_build="0.32.4"))
    text = report.render([report.read_cell(_cell(tmp_path, "stock", 3))])
    assert "not declared" in text
    assert "serving_build" in text


def test_a_null_from_another_tier_is_not_borrowed(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR-0019 D2: measured per target tier, and it does not transfer."""
    _declare(report, monkeypatch, tmp_path, _bound(tier="bench-ts"))
    text = report.render([report.read_cell(_cell(tmp_path, "stock", 3))])
    assert "no null has been measured" in text


def test_a_bound_that_cannot_be_re_derived_is_refused(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = _bound()
    del entry["runs"]
    _declare(report, monkeypatch, tmp_path, entry)
    with pytest.raises(report.ReportError, match="runs"):
        report.load_bounds()


def test_the_interaction_term_is_not_marked_against_a_single_contrast_bound(
    report: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A difference of differences carries the drift of every arm inside it."""
    _declare(report, monkeypatch, tmp_path, _bound())
    cells = [
        report.read_cell(_cell(tmp_path, "stock", 30, n=100)),
        report.read_cell(_cell(tmp_path, "planonly", 20, n=100)),
        report.read_cell(_cell(tmp_path, "norule", 40, n=100)),
        report.read_cell(_cell(tmp_path, "planonly+norule", 20, n=100)),
    ]
    text = report.render(cells)
    assert "floor on its noise rather than a bound on it" in text
    assert "interaction -10.0pp" in text


def test_additive_levers_are_named_as_such(report: Any, tmp_path: Path) -> None:
    """stock 3, planonly 2 (-10pp), norule 4 (+10pp), combined 3 (0pp)."""
    cells = [
        report.read_cell(_cell(tmp_path, "stock", 3)),
        report.read_cell(_cell(tmp_path, "planonly", 2)),
        report.read_cell(_cell(tmp_path, "norule", 4)),
        report.read_cell(_cell(tmp_path, "planonly+norule", 3)),
    ]
    text = report.render(cells)
    assert "additive on this set" in text
