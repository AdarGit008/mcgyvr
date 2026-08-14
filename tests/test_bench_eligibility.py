"""The eligible set for the capacity levers, and the headroom that bounds it.

Issue: `#266 <https://github.com/AdarGit008/mcgyvr/issues/266>`_.

These freeze a finding rather than a preference. #266 asks whether the bench's
material can carry a scaffold manipulation at all; the answer is computed from
the corpus and the committed runs, and it is pinned here so that a corpus change
which alters it fails the build instead of quietly re-opening a closed question.

Removing an entry is how a fix is proved — the same convention
``tests/test_four_lenses.py`` uses for the audit's allowlists.
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


# `tools/` is not a package, so the rigs are loaded by path — the convention
# `tests/test_bench_rounds.py` established for the same reason.
eligibility = _by_path(
    "bench_eligibility_t", REPO / "tools" / "bench" / "eligibility.py"
)

# The corpus, per arm. Both arms are generated from one campaign and are
# identical in composition; a divergence here is a corpus defect, not a fixture
# that needs updating.
EXPECTED_STRATA = {
    ("bug_fix", True): 59,
    ("function_implementation", False): 164,
    ("function_implementation", True): 34,
}

# The committed pair the finding was derived from. ``ceiling`` is what ``m``
# could arithmetically have reached on the eligible set — the count of cells
# passing under either condition — and ADR-0019's wall is ``m >= 6``.
_7B = ("bench-null-gate-7b-a-2026-08-14", "bench-control-norule-7b-2026-08-14")
_15B = ("bench-null-gate-15b-a-2026-08-13", "bench-control-norule-15b-2026-08-13")

ELIGIBLE_CEILING = {
    (*_7B, "py"): 1,
    (*_7B, "ts"): 4,
    (*_15B, "py"): 2,
    (*_15B, "ts"): 2,
}

WALL = 6


@pytest.mark.parametrize("arm", eligibility.ARMS)
def test_the_corpus_composition_is_what_the_eligibility_finding_assumed(
    arm: str,
) -> None:
    counts: dict[tuple[str, bool], int] = {}
    for kind, has in eligibility.strata(arm).values():
        counts[(kind, has)] = counts.get((kind, has), 0) + 1
    assert counts == EXPECTED_STRATA


@pytest.mark.parametrize("arm", eligibility.ARMS)
def test_the_capacity_levers_are_live_on_the_scaffolded_implementations_only(
    arm: str,
) -> None:
    live = eligibility.eligible(arm)
    assert len(live) == EXPECTED_STRATA[("function_implementation", True)]
    assert all(
        eligibility.strata(arm)[task] == ("function_implementation", True)
        for task in live
    )


@pytest.mark.parametrize(("pair", "ceiling"), sorted(ELIGIBLE_CEILING.items()))
def test_the_eligible_set_cannot_reach_the_decidability_wall(
    pair: tuple[str, str, str], ceiling: int
) -> None:
    """No effect size makes a scaffold ablation readable on this material.

    A cell that passes under neither condition is concordant whatever the lever
    does, so the count that pass under *either* is an upper bound on ``m``. On
    every committed (tier x arm) cell that bound sits far below ADR-0019's wall,
    which is a finding about the corpus rather than about the lever.
    """
    stock_dir, ablated_dir, arm = pair
    measured = eligibility.headroom(
        eligibility.greedy(RUNS / stock_dir, arm),
        eligibility.greedy(RUNS / ablated_dir, arm),
        eligibility.eligible(arm),
    )
    assert measured["ceiling"] == ceiling
    assert measured["ceiling"] < WALL


def test_the_responsive_stratum_is_bug_fix_and_the_levers_cannot_touch_it() -> None:
    """Where the headroom actually is, and why it is out of the levers' reach.

    ``matrix.json`` rules ``bug_fix`` ineligible for both capacity levers — its
    ``target_content`` is the buggy file the task exists to fix. That is the one
    stratum with room to move at the 7B, so the material constraint and the
    eligibility rule point in opposite directions.
    """
    stock = eligibility.greedy(RUNS / "bench-null-gate-7b-a-2026-08-14", "py")
    by_stratum = eligibility.strata("py")
    bug_fix = {t for t, s in by_stratum.items() if s[0] == "bug_fix"}
    scaffolded = eligibility.eligible("py")
    bug_fix_rate = sum(stock[t] for t in bug_fix) / len(bug_fix)
    scaffold_rate = sum(stock[t] for t in scaffolded) / len(scaffolded)
    assert bug_fix_rate > 0.5
    assert scaffold_rate < 0.05
    assert not (bug_fix & scaffolded)
