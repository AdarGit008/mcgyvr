"""The rate card, and the property that makes it a rate and not a total (#289).

``reproducibility.json``'s ``matching`` prose priced a null at "about 40
minutes" — one constant for every cell — beside a ``1.47pp`` bound that had the
same shape and the same defect. The card replaces the constant. These tests
hold it to three things:

* it **re-derives** from the runs on disk, so a committed record cannot drift
  from the measurement it claims to be;
* it is keyed on both axes, because the gate does not scale with the model and
  a card keyed on ``model`` alone would mis-price every ``ts`` cell;
* the prose it replaced no longer states a competing constant.

The last one is the one that would rot silently. A record that supersedes a
figure while the figure stays quotable somewhere else has not superseded it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
CARD = REPO / "tools" / "bench" / "rate-card.json"
REPRODUCIBILITY = REPO / "tools" / "bench" / "reproducibility.json"


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ratecard() -> Any:
    return _by_path("bench_ratecard_t", REPO / "tools" / "bench" / "ratecard.py")


@pytest.fixture(scope="module")
def card() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(CARD.read_text(encoding="utf-8"))
    return loaded


def test_the_committed_card_re_derives_from_the_runs(
    ratecard: Any, card: dict[str, Any]
) -> None:
    """A stale record is the failure mode; deriving on demand is the fix."""
    assert card["cells"] == ratecard.derive(), (
        "tools/bench/rate-card.json disagrees with tools/bench/ratecard.py's "
        "derivation — re-generate the record or explain which runs moved"
    )


def test_every_declared_bound_is_priced(card: dict[str, Any]) -> None:
    """A cell with a bound and no price is a cell nobody can budget a re-run for."""
    bounds = json.loads(REPRODUCIBILITY.read_text(encoding="utf-8"))["bounds"]
    assert [(b["model"], b["tier"]) for b in bounds] == [
        (c["model"], c["tier"]) for c in card["cells"]
    ]


def test_the_rate_is_the_sum_of_its_two_parts(card: dict[str, Any]) -> None:
    for cell in card["cells"]:
        assert cell["total_s"] == pytest.approx(
            cell["generation_s"] + cell["gate_s"], abs=1e-4
        )


def test_the_formula_recovers_the_pair_totals(
    ratecard: Any, card: dict[str, Any]
) -> None:
    """minutes = 2 * n * rate / 60 — the r1 pairs at n = 257, to the tenth."""
    expected = {
        ("qwen2.5-coder:1.5b", "bench-py"): 16.2,
        ("qwen2.5-coder:1.5b", "bench-ts"): 32.1,
        ("qwen2.5-coder:7b", "bench-py"): 29.5,
        ("qwen2.5-coder:7b", "bench-ts"): 48.7,
    }
    for cell in card["cells"]:
        got = ratecard.minutes(cell["total_s"], 257)
        assert got == pytest.approx(expected[(cell["model"], cell["tier"])], abs=0.1)


def test_the_gate_does_not_scale_with_the_model_and_the_card_can_show_it(
    card: dict[str, Any],
) -> None:
    """The reason the card is keyed on two axes rather than one.

    On ``bench-py`` the gate costs the same at both models — a linter does not
    read the model's output size. Generation does scale. A card keyed on
    ``model`` alone could not represent that, and would carry the ``py`` gate
    cost into every ``ts`` cell.
    """
    by_key = {(c["model"], c["tier"]): c for c in card["cells"]}
    small = by_key[("qwen2.5-coder:1.5b", "bench-py")]
    large = by_key[("qwen2.5-coder:7b", "bench-py")]

    assert small["gate_s"] == pytest.approx(large["gate_s"], abs=0.05), (
        "the py gate moved with the model — the card's two-axis justification "
        "no longer holds and its why_two_axes note needs re-measuring"
    )
    assert large["generation_s"] > 1.5 * small["generation_s"]

    for model in ("qwen2.5-coder:1.5b", "qwen2.5-coder:7b"):
        assert (
            by_key[(model, "bench-ts")]["gate_s"]
            > 5 * by_key[(model, "bench-py")]["gate_s"]
        ), "the ts gate collapsed toward the py gate; the arms no longer differ"


def test_the_superseded_constant_is_gone_from_the_prose() -> None:
    """A replaced figure that stays quotable somewhere else was not replaced."""
    matching = json.loads(REPRODUCIBILITY.read_text(encoding="utf-8"))["matching"]
    assert "40 minutes" not in matching, (
        "reproducibility.json still prices a null at a flat 40 minutes. The "
        "rate card measured that constant at 2.5x too high for the cheapest "
        "cell and 18% too low for the dearest — point the prose at the card"
    )
    assert "rate-card.json" in matching, (
        "the prose no longer states the old constant but names no replacement, "
        "so a reader asking what a null costs has nowhere to go"
    )
