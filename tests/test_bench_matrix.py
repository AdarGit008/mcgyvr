"""The condition matrix's rules, and the arithmetic the report reads off it (#113).

The matrix is data, so nothing here checks that a particular cell exists — that
is the data's business and it will change. What is pinned is the three things a
defect in would be silent:

* **The slot rule.** Two levers writing the same field give a cell whose result
  depends on which ran last. That is not a condition, it is a bug with a name,
  and a measurement taken under it would look exactly like a real one.
* **The baseline is byte-identical to no cell at all.** Every effect the bench
  reports is measured against ``stock``. If routing the baseline through the
  matrix perturbed the dispatch, every historical run would silently stop being
  comparable to every new one.
* **The interaction term is absent, not zero, when a part is missing.** A
  missing single-lever arm means the subtraction cannot be done; returning 0.0
  would publish "these levers are additive" as a finding.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

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
def matrix() -> types.ModuleType:
    return _by_path("bench_matrix_t", REPO / "tools" / "bench" / "matrix.py")


@pytest.fixture(scope="module")
def measure() -> types.ModuleType:
    return _by_path("breadth_measure_t", REPO / "tools" / "breadth" / "measure.py")


def _write(tmp_path: Path, body: dict[str, object]) -> Path:
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(body))
    return path


# --- the declared matrix loads and means what it says ----------------------


def test_the_declared_matrix_loads(matrix: types.ModuleType) -> None:
    loaded = matrix.load()
    assert loaded.cells
    assert loaded.baseline.is_baseline
    for cell in loaded.cells.values():
        for lever in cell.levers:
            assert lever.stage in matrix.STAGES


def test_every_lever_is_reachable_from_some_cell(matrix: types.ModuleType) -> None:
    """A declared lever no cell names is a knob nothing can turn."""
    loaded = matrix.load()
    named = {lever.id for cell in loaded.cells.values() for lever in cell.levers}
    assert named == set(loaded.levers)


# --- the slot rule ---------------------------------------------------------


def test_two_levers_writing_one_slot_are_refused(
    matrix: types.ModuleType, tmp_path: Path
) -> None:
    path = _write(
        tmp_path,
        {
            "levers": {
                "a": {"stage": "contract", "slot": "target_content"},
                "b": {"stage": "contract", "slot": "target_content"},
            },
            "cells": [
                {"id": "base", "levers": []},
                {"id": "both", "levers": ["a", "b"]},
            ],
        },
    )
    with pytest.raises(matrix.MatrixError, match="order"):
        matrix.load(path)


def test_levers_writing_different_slots_compose(
    matrix: types.ModuleType, tmp_path: Path
) -> None:
    path = _write(
        tmp_path,
        {
            "levers": {
                "a": {"stage": "contract", "slot": "target_content"},
                "b": {"stage": "message", "slot": "output_section"},
            },
            "cells": [
                {"id": "base", "levers": []},
                {"id": "both", "levers": ["a", "b"]},
            ],
        },
    )
    assert len(matrix.load(path).cell("both").levers) == 2


def test_exactly_one_baseline_is_required(
    matrix: types.ModuleType, tmp_path: Path
) -> None:
    two = _write(
        tmp_path,
        {"levers": {}, "cells": [{"id": "x", "levers": []}, {"id": "y", "levers": []}]},
    )
    with pytest.raises(matrix.MatrixError, match="exactly one"):
        matrix.load(two)


def test_a_cell_naming_an_undeclared_lever_is_refused(
    matrix: types.ModuleType, tmp_path: Path
) -> None:
    path = _write(
        tmp_path,
        {
            "levers": {},
            "cells": [
                {"id": "base", "levers": []},
                {"id": "x", "levers": ["ghost"]},
            ],
        },
    )
    with pytest.raises(matrix.MatrixError, match="undeclared"):
        matrix.load(path)


# --- the baseline is untouched --------------------------------------------


def test_baseline_render_is_byte_identical_to_plain_assembly(
    measure: types.ModuleType,
) -> None:
    """Routing `stock` through the matrix must change nothing at all."""
    from mcgyvr.worker.prompt import build_prompt

    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    plain = build_prompt(task.contract)
    through = measure.render_for("stock", measure.ablate(task.contract, "stock"))
    assert through.user == plain.user
    assert through.system == plain.system
    assert through.tokens == plain.tokens


# --- the message stage ------------------------------------------------------


def test_norule_removes_only_the_output_section(measure: types.ModuleType) -> None:
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    base = measure.render_for("stock", measure.ablate(task.contract, "stock"))
    ablated = measure.render_for("norule", measure.ablate(task.contract, "norule"))

    dropped = [p for p in base.user.split("\n\n") if p.startswith("OUTPUT: ")]
    assert len(dropped) == 1
    kept = [p for p in base.user.split("\n\n") if not p.startswith("OUTPUT: ")]
    assert ablated.user == "\n\n".join(kept)


def test_the_message_stage_recosts_the_prompt(measure: types.ModuleType) -> None:
    """An ablation that removes text must not be priced as free."""
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    base = measure.render_for("stock", measure.ablate(task.contract, "stock"))
    ablated = measure.render_for("norule", measure.ablate(task.contract, "norule"))
    assert ablated.tokens < base.tokens


def test_stripping_an_absent_output_section_is_an_error(
    matrix: types.ModuleType,
) -> None:
    """A no-op ablation dilutes a paired test rather than contributing to it."""
    with pytest.raises(matrix.MatrixError, match="no-op"):
        matrix.strip_output_section("TASK: do a thing\n\nTARGET: x.py\n")


def test_output_is_matched_at_a_paragraph_boundary(
    matrix: types.ModuleType,
) -> None:
    """A task description mentioning the word must survive the ablation."""
    message = (
        "TASK: describe what the OUTPUT: label means\n\n"
        "OUTPUT: Reply with the complete new content.\n"
    )
    assert matrix.strip_output_section(message).startswith("TASK: describe")
    assert "OUTPUT: Reply" not in matrix.strip_output_section(message)


# --- the interaction term ---------------------------------------------------


def test_interaction_subtracts_the_singles(matrix: types.ModuleType) -> None:
    loaded = matrix.load()
    rate = {"stock": 0.30, "planonly": 0.20, "norule": 0.24, "planonly+norule": 0.18}
    term = matrix.interaction(loaded, "planonly+norule", rate)
    assert term is not None
    # combined -0.12, singles -0.10 and -0.06, so the pair overlapped by +0.04.
    assert term.combined == pytest.approx(-0.12)
    assert term.term == pytest.approx(0.04)
    assert not term.additive


def test_interaction_is_none_when_a_single_is_missing(
    matrix: types.ModuleType,
) -> None:
    loaded = matrix.load()
    rate = {"stock": 0.30, "planonly": 0.20, "planonly+norule": 0.18}
    assert matrix.interaction(loaded, "planonly+norule", rate) is None


def test_interaction_is_none_for_a_single_lever_cell(
    matrix: types.ModuleType,
) -> None:
    loaded = matrix.load()
    rate = {"stock": 0.30, "planonly": 0.20}
    assert matrix.interaction(loaded, "planonly", rate) is None


def test_additive_levers_report_a_zero_term(matrix: types.ModuleType) -> None:
    loaded = matrix.load()
    rate = {"stock": 0.30, "planonly": 0.20, "norule": 0.25, "planonly+norule": 0.15}
    term = matrix.interaction(loaded, "planonly+norule", rate)
    assert term is not None and term.additive
