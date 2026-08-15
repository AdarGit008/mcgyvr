"""The responsive fraction per (model + bar) x stratum, pinned.

Issue: `#224 <https://github.com/AdarGit008/mcgyvr/issues/224>`_, the first item
of its 2026-08-14 amendment. These freeze a measurement rather than a
preference: the fractions below are derived from committed runs, and #243's
record is four quoted figures that survived until someone re-derived them by
hand. A corpus or run change that moves them fails the build instead of quietly
re-describing the bench.

Removing an entry is how a fix is proved — the convention
``tests/test_bench_eligibility.py`` and ``tests/test_four_lenses.py`` use.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "records" / "measurements"


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# `tools/` is not a package, so the rig is loaded by path.
responsive = _by_path("bench_responsive_t", REPO / "tools" / "bench" / "responsive.py")

# (tier, arm, stratum) -> (k, n), gate-scored off the committed `norule`
# contrasts. `headroom` is the count passing under either condition — an upper
# bound on `m`; `psi`'s numerator is `m` itself.
HEADROOM: dict[tuple[str, str, str], tuple[int, int]] = {
    ("1.5B", "py", "bug_fix+scaffold"): (14, 59),
    ("1.5B", "py", "function_implementation"): (10, 164),
    ("1.5B", "py", "function_implementation+scaffold"): (2, 34),
    ("1.5B", "ts", "bug_fix+scaffold"): (11, 59),
    ("1.5B", "ts", "function_implementation"): (22, 164),
    ("1.5B", "ts", "function_implementation+scaffold"): (2, 34),
    ("7B", "py", "bug_fix+scaffold"): (36, 59),
    ("7B", "py", "function_implementation"): (36, 164),
    ("7B", "py", "function_implementation+scaffold"): (1, 34),
    ("7B", "ts", "bug_fix+scaffold"): (31, 59),
    ("7B", "ts", "function_implementation"): (23, 164),
    ("7B", "ts", "function_implementation+scaffold"): (4, 34),
}

PSI: dict[tuple[str, str, str], tuple[int, int]] = {
    ("1.5B", "py", "bug_fix+scaffold"): (6, 59),
    ("1.5B", "py", "function_implementation"): (7, 164),
    ("1.5B", "py", "function_implementation+scaffold"): (1, 34),
    ("1.5B", "ts", "bug_fix+scaffold"): (3, 59),
    ("1.5B", "ts", "function_implementation"): (22, 164),
    ("1.5B", "ts", "function_implementation+scaffold"): (1, 34),
    ("7B", "py", "bug_fix+scaffold"): (7, 59),
    ("7B", "py", "function_implementation"): (7, 164),
    ("7B", "py", "function_implementation+scaffold"): (1, 34),
    ("7B", "ts", "bug_fix+scaffold"): (2, 59),
    ("7B", "ts", "function_implementation"): (7, 164),
    ("7B", "ts", "function_implementation+scaffold"): (1, 34),
}

# Every multi-draw cell the repository holds. Six of the twelve (tier, arm,
# stratum) cells are absent and stay absent — see the coverage test below.
PSI_DRAW: dict[tuple[str, str, str], tuple[int, int]] = {
    ("1.5B", "py", "bug_fix+scaffold"): (23, 33),
    ("1.5B", "py", "function_implementation"): (69, 102),
    ("1.5B", "ts", "bug_fix+scaffold"): (19, 33),
    ("1.5B", "ts", "function_implementation"): (67, 102),
    ("7B", "py", "function_implementation+scaffold"): (15, 34),
    ("7B", "ts", "function_implementation+scaffold"): (16, 34),
    ("3B", "py", "function_implementation+scaffold"): (10, 34),
    ("3B", "ts", "function_implementation+scaffold"): (7, 34),
}

# What no committed run can answer today, over the two tiers #224 owes a band
# for. These are the sweeps A2 is scoped from; an entry disappears when one is
# run, and never because the table was tidied.
COVERAGE_GAPS = {
    ("1.5B", "py", "function_implementation+scaffold", "psi_draw"),
    ("1.5B", "ts", "function_implementation+scaffold", "psi_draw"),
    ("7B", "py", "bug_fix+scaffold", "psi_draw"),
    ("7B", "py", "function_implementation", "psi_draw"),
    ("7B", "ts", "bug_fix+scaffold", "psi_draw"),
    ("7B", "ts", "function_implementation", "psi_draw"),
}

# Cells whose acceptance command never ran under either condition, because a
# pre-acceptance rung rejected first. An upper bound on what a zero-token
# formatting pass could recover, not a claim any would then pass.
NEVER_REACHED_ACCEPTANCE: dict[tuple[str, str, str], int] = {
    ("1.5B", "py", "bug_fix+scaffold"): 18,
    ("1.5B", "py", "function_implementation"): 127,
    ("1.5B", "py", "function_implementation+scaffold"): 23,
    ("1.5B", "ts", "bug_fix+scaffold"): 13,
    ("1.5B", "ts", "function_implementation"): 126,
    ("1.5B", "ts", "function_implementation+scaffold"): 13,
    ("7B", "py", "bug_fix+scaffold"): 13,
    ("7B", "py", "function_implementation"): 110,
    ("7B", "py", "function_implementation+scaffold"): 27,
    ("7B", "ts", "bug_fix+scaffold"): 18,
    ("7B", "ts", "function_implementation"): 133,
    ("7B", "ts", "function_implementation+scaffold"): 15,
}


def _measured(observable: str) -> dict[tuple[str, str, str], tuple[int, int]]:
    return {
        (row.tier, row.arm, row.stratum): (row.k, row.n)
        for row in responsive.derive()
        if row.observable == observable and not row.pooled
    }


@pytest.mark.parametrize(("key", "expected"), sorted(HEADROOM.items()))
def test_headroom_per_model_bar_and_stratum(
    key: tuple[str, str, str], expected: tuple[int, int]
) -> None:
    assert _measured(responsive.HEADROOM)[key] == expected


@pytest.mark.parametrize(("key", "expected"), sorted(PSI.items()))
def test_psi_per_model_bar_and_stratum(
    key: tuple[str, str, str], expected: tuple[int, int]
) -> None:
    assert _measured(responsive.PSI)[key] == expected


@pytest.mark.parametrize(("key", "expected"), sorted(PSI_DRAW.items()))
def test_psi_draw_per_model_bar_and_stratum(
    key: tuple[str, str, str], expected: tuple[int, int]
) -> None:
    assert _measured(responsive.PSI_DRAW)[key] == expected


def test_the_three_observables_are_the_only_ones_reported() -> None:
    """No fourth number sneaks into the same column as these three."""
    assert {row.observable for row in responsive.derive()} == {
        responsive.HEADROOM,
        responsive.PSI,
        responsive.PSI_DRAW,
    }


def test_psi_draw_is_never_described_as_a_bound() -> None:
    """``responsiveness.py``'s caveat, preserved rather than paraphrased away.

    Its docstring is explicit that ``psi_draw`` is not ``psi`` and is not a
    bound in either direction. The figures here are two to ten times the
    gate-scored headroom on the same tier, so a reader who loses that sentence
    reads the most optimistic number in the table as a ceiling.
    """
    stated = responsive.BOUNDS[responsive.PSI_DRAW].lower()
    assert "not" in stated and "bound" in stated
    text = "\n".join(responsive.report()).lower()
    assert "not a bound in either direction" in text


def test_no_row_is_pooled_across_tiers_or_arms() -> None:
    """ADR-0019 D2 and ADR-0026, carried from ``resolution.py`` unchanged.

    Every row names exactly one tier and one arm, and the only aggregate row is
    the arm-level one, which is labelled so it cannot be quoted as the bench's
    resolution.
    """
    for row in responsive.derive():
        assert row.tier in {"1.5B", "3B", "7B"}
        assert row.arm in responsive.ARMS
    aggregates = {row.stratum for row in responsive.derive() if row.pooled}
    assert aggregates == {responsive.ARM_ROW}
    assert "not the bench's resolution" in responsive.ARM_ROW


def test_the_coverage_gaps_are_what_a2_must_close() -> None:
    assert set(responsive.coverage_gaps(responsive.derive())) == COVERAGE_GAPS


@pytest.mark.parametrize(("key", "expected"), sorted(NEVER_REACHED_ACCEPTANCE.items()))
def test_cells_whose_acceptance_never_ran(
    key: tuple[str, str, str], expected: int
) -> None:
    """The reconciliation between the three observables, pinned.

    On ``function_implementation`` — the largest stratum, 164 of 257 — between
    67% and 81% of cells were rejected by a pre-acceptance rung under *both*
    conditions, at both tiers, on both bars. A keep-or-retire verdict read off
    ``headroom`` alone would therefore retire the stratum for a reason that is
    not the material's difficulty.
    """
    tier, arm, stratum = key
    contrast = next(c for c in responsive.CONTRASTS if c.tier == tier)
    assert responsive.never_reached_acceptance(contrast)[(arm, stratum)] == expected


def test_no_multi_draw_run_is_scored_by_the_bench_bar() -> None:
    """Hole two, asserted rather than described.

    #224's acceptance requires every band figure to be scored through
    ``Gate.run``. Every committed multi-draw run predates that scorer — its rows
    carry no ``rejected_by`` — so no ``psi_draw`` figure here meets it. This
    fails when a gate-scored multi-draw run lands, which is the point.
    """
    for run in responsive.DRAW_RUNS:
        assert run.bar == "acceptance only"
        for arm in responsive.ARMS:
            path = RUNS / run.run / f"bench-{arm}" / "results.jsonl"
            first = next(line for line in path.read_text(encoding="utf-8").splitlines())
            assert "rejected_by" not in first
    for contrast in responsive.CONTRASTS:
        assert contrast.bar == "Gate.run"
        for arm in responsive.ARMS:
            path = RUNS / contrast.stock / f"bench-{arm}" / "results.jsonl"
            first = next(line for line in path.read_text(encoding="utf-8").splitlines())
            assert "rejected_by" in first


def test_the_scorer_gap_is_the_size_of_the_disagreement() -> None:
    """Why ``psi_draw`` and ``headroom`` differ by an order of magnitude.

    On the same 135 cells, at the same tier, the acceptance proxy passes 55
    greedy where ``Gate.run`` passes 18. The gap between the two observables is
    therefore mostly the bar, not the material — which is the finding, and the
    reason the two must never be averaged.
    """
    eligibility = _by_path(
        "bench_eligibility_rt", REPO / "tools" / "bench" / "eligibility.py"
    )
    responsiveness = _by_path(
        "bench_responsiveness_rt", REPO / "tools" / "bench" / "responsiveness.py"
    )
    built = responsiveness.cells(RUNS / "f1-responsiveness-15b-2026-08-11", 8)
    shared = sorted(task for (arm, task) in built if arm == "py")
    gate = eligibility.greedy(RUNS / "bench-null-gate-15b-a-2026-08-13", "py")
    assert len(shared) == 135
    assert sum(built[("py", t)]["greedy"] for t in shared) == 55
    assert sum(gate[t] for t in shared) == 18
