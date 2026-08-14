"""The redundancy read's arithmetic (#225).

Like the responsiveness read beside it, a defect here would not crash — it
would publish a number that decides whether 120 more problems get authored.
Three things are worth pinning, each against a computation that shares no code
with the thing it checks:

* **Fisher's p** is what separates "these two cells behave differently" from
  "the counts happen to differ". Checked against an explicit enumeration of the
  label assignments, which is the permutation argument the hypergeometric
  formula is a shortcut for.
* **The correlation** is the whole finding. Checked against series whose answer
  is known by construction, including the two degenerate cases that must return
  zero rather than divide by it.
* **The tranche derivation** decides which row a problem is reported in. A
  problem filed under a tranche it was not authored in would move a mean that
  an authoring decision is read from.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from itertools import combinations
from math import isclose
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


red = _by_path("redundancy", REPO / "tools" / "bench" / "redundancy.py")


def _enumerated_fisher(a: int, b: int, c: int, d: int) -> float:
    """Two-sided p by enumerating every label assignment, sharing no code.

    Lay out ``a + b + c + d`` items, of which ``a + c`` carry the first label.
    Every way of choosing which items land in the first row is equally likely;
    sum the probability of the tables no more likely than the observed one.
    """
    total = a + b + c + d
    items = [1] * (a + c) + [0] * (b + d)
    counts: dict[int, int] = {}
    for chosen in combinations(range(total), a + b):
        picked = sum(items[i] for i in chosen)
        counts[picked] = counts.get(picked, 0) + 1
    ways = sum(counts.values())
    observed = counts[a] / ways
    return sum(v / ways for v in counts.values() if v / ways <= observed + 1e-12)


@pytest.mark.parametrize(
    "table",
    [
        (8, 0, 0, 8),
        (8, 0, 1, 7),
        (0, 8, 5, 3),
        (2, 6, 1, 7),
        (5, 3, 6, 2),
        (0, 8, 0, 8),
        (4, 4, 4, 4),
        (3, 2, 1, 4),
    ],
)
def test_fisher_matches_enumeration(table: tuple[int, int, int, int]) -> None:
    assert isclose(red.fisher(*table), _enumerated_fisher(*table), abs_tol=1e-9)


def test_fisher_is_a_probability() -> None:
    """Never above 1.0 — the observed table is counted once, not twice."""
    for a in range(5):
        for c in range(5):
            assert 0.0 <= red.fisher(a, 4 - a, c, 4 - c) <= 1.0


def test_fisher_on_an_empty_table() -> None:
    assert red.fisher(0, 0, 0, 0) == 1.0


def test_the_separation_that_carries_the_finding() -> None:
    """8/8 against 0/8 must clear the bar; one draw apart must not.

    These are the two real pairs the record leans on. If the first stopped
    being significant the tool would report no differences at all; if the
    second started being significant it would report them everywhere.
    """
    assert red.fisher(8, 0, 0, 8) < 0.05
    assert red.fisher(2, 6, 1, 7) > 0.05


def test_pearson_on_known_series() -> None:
    assert isclose(red.pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]), 1.0, abs_tol=1e-12)
    assert isclose(red.pearson([1.0, 2.0, 3.0], [6.0, 4.0, 2.0]), -1.0, abs_tol=1e-12)


def test_pearson_refuses_to_divide_by_zero() -> None:
    """A constant series has no correlation — it must not raise."""
    assert red.pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) == 0.0
    assert red.pearson([1.0, 2.0, 3.0], [5.0, 5.0, 5.0]) == 0.0
    assert red.pearson([], []) == 0.0
    assert red.pearson([1.0], [2.0]) == 0.0


def test_pearson_ignores_mismatched_series() -> None:
    assert red.pearson([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


@pytest.mark.parametrize(
    "problem_id,expected",
    [
        ("b228-tide-marks", 4),
        ("b267-alias-map", 4),
        ("b268-score-drop", 5),
        ("b307-anything", 5),
        ("b308-half-life", 6),
        ("b468-bracket-depth", 10),
        ("b507-stack-pop", 10),
    ],
)
def test_tranche_boundaries(problem_id: str, expected: int) -> None:
    """b228 opens tranche 4 and every fortieth id opens the next."""
    assert red.tranche_of(problem_id) == expected


def test_problems_before_the_band_have_no_tranche() -> None:
    assert red.tranche_of("b227-earlier") is None
    assert red.tranche_of("b080-brace-fill") is None


def test_unparseable_ids_are_refused_not_guessed() -> None:
    assert red.tranche_of("bxxx-nonsense") is None
    assert red.tranche_of("") is None


def _pp(text: str) -> float:
    return float(text.removesuffix("pp"))


def test_higher_psi_is_worse_not_better() -> None:
    """The counterintuitive direction the sizing table is read for.

    More discordant pairs means more variance in the net the test reads, so a
    higher discordance rate needs a *larger* effect to resolve. Reading this
    backwards would turn ADR-0021's table upside down, and it is the one
    property of the sizing curve that surprises everyone who meets it.
    """
    at = [_pp(red.mde(426, psi)) for psi in red.PSI_CANDIDATES]
    assert at == sorted(at), f"MDE must rise with psi, got {at}"
    assert at[0] < at[-1]


def test_more_swept_cells_resolve_more() -> None:
    """And the axis that is not surprising, pinned so a sign flip is caught."""
    for psi in red.PSI_CANDIDATES:
        series = [_pp(red.mde(cells, psi)) for cells in (298, 426, 852)]
        assert series == sorted(series, reverse=True), f"psi={psi}: {series}"


def test_the_two_figures_the_record_quotes() -> None:
    """ADR-0021's fourth amendment quotes these; a drift here silently rewrites it.

    426 swept cells is 400 authored at the realized 53.2% bench share. The
    second assertion is the coincidence the record names — the withdrawn 8.2pp
    reappearing from a corrected denominator and a plausible psi.
    """
    assert red.mde(426, 0.659) == "11.3pp"
    assert red.mde(426, 0.35) == "8.2pp"


def test_the_withdrawn_reading_against_the_corrected_one() -> None:
    """The amendment's whole subject, as two calls that differ only in denominator.

    The withdrawn reading counted 400 authored problems as 800 cells — both
    arms of every problem, including the ~47% the split sends to a reserve that
    is never swept. The corrected reading counts only the bench half: 426 cells
    at the realized 53.2% share. Same bench, same psi, 3.1pp apart.
    """
    assert red.mde(800, 0.659) == "8.2pp"  # withdrawn: counted the reserve
    assert red.mde(426, 0.659) == "11.3pp"  # corrected: bench half only
    assert _pp(red.mde(426, 0.659)) > _pp(red.mde(800, 0.659))
