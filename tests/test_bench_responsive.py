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
import json
import sys
import types
from dataclasses import replace
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

# Every multi-draw cell the repository holds, under the scorer that produced it
# on the day: the contract's acceptance command, alone. Six of the twelve
# (tier, arm, stratum) cells are absent and stay absent — see the coverage test
# below. These are the figures every `psi_draw` this project has quoted was, and
# they are kept rather than replaced so the re-scored column below can be read
# against them.
PSI_DRAW_ACCEPTANCE: dict[tuple[str, str, str], tuple[int, int]] = {
    ("1.5B", "py", "bug_fix+scaffold"): (23, 33),
    ("1.5B", "py", "function_implementation"): (69, 102),
    ("1.5B", "ts", "bug_fix+scaffold"): (19, 33),
    ("1.5B", "ts", "function_implementation"): (67, 102),
    ("7B", "py", "function_implementation+scaffold"): (15, 34),
    ("7B", "ts", "function_implementation+scaffold"): (16, 34),
    ("3B", "py", "function_implementation+scaffold"): (10, 34),
    ("3B", "ts", "function_implementation+scaffold"): (7, 34),
}

# The same draws, re-scored offline under `Gate.run` by
# `tools/bench/gate_rescore.py` (#224 A2, hole 1). This is the column that is
# comparable with `headroom` and `psi` above; the one above is not.
PSI_DRAW_GATE: dict[tuple[str, str, str], tuple[int, int]] = {
    ("1.5B", "py", "bug_fix+scaffold"): (22, 33),
    ("1.5B", "py", "function_implementation"): (32, 102),
    ("1.5B", "ts", "bug_fix+scaffold"): (18, 33),
    ("1.5B", "ts", "function_implementation"): (31, 102),
    ("7B", "py", "function_implementation+scaffold"): (6, 34),
    ("7B", "ts", "function_implementation+scaffold"): (9, 34),
    ("3B", "py", "function_implementation+scaffold"): (1, 34),
    ("3B", "ts", "function_implementation+scaffold"): (4, 34),
}

# The answer to "how much of the gap was the scorer", per stratum: the share of
# the `psi_draw`-to-`headroom` distance that closed when both were put on one
# bar. Pinned because it is the figure #224 A2 exists to produce, and because
# it has no single value — the spread across these six is the finding.
SCORER_SHARE: dict[tuple[str, str, str], int] = {
    ("1.5B", "py", "bug_fix+scaffold"): 7,
    ("1.5B", "py", "function_implementation"): 59,
    ("1.5B", "ts", "bug_fix+scaffold"): 8,
    ("1.5B", "ts", "function_implementation"): 68,
    ("7B", "py", "function_implementation+scaffold"): 64,
    ("7B", "ts", "function_implementation+scaffold"): 58,
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


def _measured(
    observable: str, bar: str | None = None
) -> dict[tuple[str, str, str], tuple[int, int]]:
    """The derived rows for one observable, keyed by (tier, arm, stratum).

    ``bar`` became necessary when the same draws started being reported under
    two scorers: without it this collapsed two rows onto one key and silently
    kept whichever came last, which is exactly the confusion #224 A2 exists to
    end.
    """
    return {
        (row.tier, row.arm, row.stratum): (row.k, row.n)
        for row in responsive.derive()
        if row.observable == observable
        and not row.pooled
        and (bar is None or row.bar == bar)
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


@pytest.mark.parametrize(("key", "expected"), sorted(PSI_DRAW_ACCEPTANCE.items()))
def test_psi_draw_per_model_bar_and_stratum_under_the_scorer_of_the_day(
    key: tuple[str, str, str], expected: tuple[int, int]
) -> None:
    """The acceptance-only reading, kept so the re-scored one can be read against it."""
    assert _measured(responsive.PSI_DRAW, responsive.ACCEPTANCE_BAR)[key] == expected


@pytest.mark.parametrize(("key", "expected"), sorted(PSI_DRAW_GATE.items()))
def test_psi_draw_per_model_bar_and_stratum_under_the_bench_bar(
    key: tuple[str, str, str], expected: tuple[int, int]
) -> None:
    """The same draws under ``Gate.run`` — the column comparable with ``headroom``."""
    assert _measured(responsive.PSI_DRAW, responsive.GATE_BAR)[key] == expected


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


def test_every_multi_draw_run_now_carries_both_bars() -> None:
    """Hole one, closed — and the closing kept honest at both ends.

    This test previously asserted that *no* multi-draw run was gate-scored, and
    said it should fail when one landed. One has, so it now asserts the two
    facts that replaced it:

    * the run's own ``results.jsonl`` is **still** acceptance-scored and still
      carries no ``rejected_by``. The record of what was measured on the day was
      not rewritten, which is `regrade.py`'s doctrine and `gate_rescore.py`'s;
    * a ``gate-rescore.jsonl`` sits beside it whose rows **do** carry
      ``rejected_by``, so the same draws are readable under the bench's bar.

    A re-score that had edited the original in place would satisfy the second
    assertion and fail the first, which is why both are here.
    """
    for run in responsive.DRAW_RUNS:
        for arm in responsive.ARMS:
            cell = RUNS / run.run / f"bench-{arm}"
            original = (cell / "results.jsonl").read_text(encoding="utf-8")
            assert "rejected_by" not in original.splitlines()[0]

            rescored = cell / "gate-rescore.jsonl"
            assert rescored.is_file(), f"{cell} has no gate re-score"
            assert "rejected_by" in rescored.read_text(encoding="utf-8").splitlines()[0]
    for contrast in responsive.CONTRASTS:
        assert contrast.bar == "Gate.run"
        for arm in responsive.ARMS:
            path = RUNS / contrast.stock / f"bench-{arm}" / "results.jsonl"
            first = next(line for line in path.read_text(encoding="utf-8").splitlines())
            assert "rejected_by" in first


@pytest.mark.parametrize(("key", "expected"), sorted(SCORER_SHARE.items()))
def test_the_share_of_the_gap_that_was_the_scorer(
    key: tuple[str, str, str], expected: int
) -> None:
    """The direct answer, per stratum — and it is six answers, not one.

    On `bug_fix+scaffold` the scorer explains 7-8% of the distance between
    `psi_draw` and `headroom`; on `function_implementation` and
    `function_implementation+scaffold` it explains 58-68%. A pooled figure would
    land between two clusters that share no members, which is ADR-0026's
    heterogeneity objection in one table.
    """
    measured = {
        (row["tier"], row["arm"], row["stratum"]): row
        for row in responsive.scorer_effect()
        if row["scorer_share"] is not None
    }
    assert round(100 * measured[key]["scorer_share"]) == expected


def test_the_gap_survives_on_every_stratum_that_can_be_compared() -> None:
    """The finding that reverses today's earlier record.

    The 2026-08-15 session record states the gap is "almost entirely the
    scorer, not the material". Measured, it is not: after both observables are
    put on one bar `psi_draw` still runs between 2.2x and 6.0x `headroom` on
    every stratum where the two can be compared. The scorer was a large part of
    the gap and nowhere near all of it, so the two remain different quantities.
    """
    after = [
        row["gap_after"]
        for row in responsive.scorer_effect()
        if row["gap_after"] is not None
    ]
    assert len(after) == 6
    assert min(after) > 2.0, "the gap closed somewhere — re-read the record"
    assert 2.2 <= min(after) <= 2.3
    assert 5.9 <= max(after) <= 6.1


def test_a_psi_draw_with_no_passing_draw_is_not_reported_as_a_number() -> None:
    """Zero has two causes here and the number cannot tell them apart.

    Either the cells were drawn repeatedly and never moved — a fact about the
    material — or nothing in the stratum passed at all, in which case every cell
    is pinned-fail by arithmetic and `psi_draw` is a restatement of the pass
    rate. Under `Gate.run` the second is reachable: five of the six re-scored
    ablation condition directories fall to zero or near-zero passes. A row with
    no passing draw must therefore not print a fraction, and must not count as
    coverage.
    """
    dead = responsive.Row(
        tier="7B",
        arm="py",
        stratum="function_implementation+scaffold",
        observable=responsive.PSI_DRAW,
        k=0,
        n=34,
        stratum_size=34,
        source="fixture",
        bar=responsive.GATE_BAR,
        caveat="hand-built",
        passing_draws=0,
    )
    assert dead.readable is False
    assert "unreadable" in responsive._row(dead)
    assert "0.0%" not in responsive._row(dead)
    # And it leaves the cell counted as a gap rather than as an answer.
    assert (
        "7B",
        "py",
        "function_implementation+scaffold",
        responsive.PSI_DRAW,
    ) in set(responsive.coverage_gaps((dead,)))

    alive = replace(dead, k=6, passing_draws=15)
    assert alive.readable is True
    assert "17.6%" in responsive._row(alive)


def test_every_gate_scored_psi_draw_row_has_a_passing_draw_behind_it() -> None:
    """The readability rule, applied to the material actually committed.

    None of the three multi-draw runs is driven all the way to zero, so every
    figure in the table is readable. This is asserted rather than assumed
    because the rule above only protects a reader if something checks that the
    rows it is applied to were measured, not hand-waved.
    """
    for row in responsive.derive():
        if row.observable == responsive.PSI_DRAW and row.bar == responsive.GATE_BAR:
            assert row.passing_draws, f"{row.tier}/{row.arm}/{row.stratum} has none"
            assert row.readable


def test_a_gate_rescore_names_the_bar_and_the_material_it_ran_over() -> None:
    """Every re-score is usable as evidence later, or it is not evidence now.

    The summary beside each re-scored run has to name the five rungs, the mode
    and the pinned product revision (#231 checks 3 and 6), the acceptance-script
    digests, and a content digest of the run it read — otherwise a reader
    holding the figure cannot reproduce it, and #243's record is four quoted
    figures that survived until someone re-derived them by hand.
    """
    for run in responsive.DRAW_RUNS:
        for arm in responsive.ARMS:
            summary = json.loads(
                (RUNS / run.run / f"bench-{arm}" / "gate-rescore.json").read_text(
                    encoding="utf-8"
                )
            )
            assert summary["gate_rungs"] == [
                "scope",
                "secrets",
                "structured",
                "adapters",
                "acceptance",
            ]
            assert summary["gate_semantic"] is False
            assert summary["round"] and len(summary["product_sha256"]) == 64
            assert summary["mode"] == "single-tier"
            assert len(summary["source_sha256"]["results.jsonl"]) == 64
            assert len(summary["source_sha256"]["candidates"]) == 64
            assert summary["checkers_sha256"]
            # A rung that never fired across thousands of candidates would mean
            # the bar was narrower than the label. These runs exercise the
            # adapter rungs and acceptance, and the counts say so.
            assert summary["rejected_by"]


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
