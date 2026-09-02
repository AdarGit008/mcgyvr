"""Invariants over the paired-power arithmetic ADR-0019 runs on.

This module decides #231's fitness verdict and #225's size, so the properties
that matter are the ones that would silently mis-size the bench:

* **The exact test is exact.** ``exact_p`` is checked against the McNemar
  p-values CLM-0017 published from an independent implementation, and against a
  brute-force critical value over every small ``m``. A drift here re-labels an
  unresolvable contrast as a null.
* **The m >= 6 wall holds.** It is the finding the ADR's headline table rests
  on: below six discordant pairs no split reaches alpha, so no effect of any
  size is detectable. An off-by-one makes eleven unresolvable contrasts look
  like ten.
* **The normal branch agrees with the exact one.** ``EXACT_M_LIMIT`` trades
  exactness for affordability at large ``m``; if the two branches disagreed at
  the crossover the sizing table would have a seam in it.
* **Monotonicity.** More tasks, or a larger effect, can never resolve less.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import types
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def _mde() -> types.ModuleType:
    """The power module, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "power_mde", REPO / "tools" / "power" / "mde.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["power_mde"] = module
    spec.loader.exec_module(module)
    return module


# Any rather than ModuleType: the crossover test rebinds ``EXACT_M_LIMIT``, and
# a module object has no statically known attributes to rebind.
M: Any = _mde()


def _brute_exact_p(b: int, c: int) -> float:
    """The textbook form, which overflows above m ~ 1000 and is fine below it."""
    m = b + c
    if m == 0:
        return 1.0
    k = min(b, c)
    # 2.0**m, not 2**m: int.__pow__ with a non-literal exponent is typed Any.
    return min(1.0, 2.0 * sum(math.comb(m, i) for i in range(k + 1)) / 2.0**m)


def test_exact_p_matches_published_mcnemar_figures() -> None:
    """CLM-0017 arm B, computed elsewhere and recorded as 0.45 / 0.12 / 0.07."""
    assert round(M.exact_p(5, 2), 2) == 0.45
    assert round(M.exact_p(4, 0), 2) == 0.12
    assert round(M.exact_p(7, 1), 2) == 0.07


def test_exact_p_matches_brute_force_over_small_tables() -> None:
    for b in range(30):
        for c in range(30):
            assert math.isclose(M.exact_p(b, c), _brute_exact_p(b, c), rel_tol=1e-9)


def test_exact_p_survives_the_range_that_overflows_the_naive_form() -> None:
    """comb(m, i) / 2**m stops converting to float around m = 1000."""
    assert 0.0 < M.exact_p(1200, 1200) <= 1.0
    assert M.exact_p(2000, 1500) < 0.05


def test_no_effect_is_detectable_below_six_discordant_pairs() -> None:
    """The wall the ADR's headline table rests on."""
    for m in range(M.MIN_DISCORDANT):
        assert M.critical_k(m) is None
        # The most extreme split possible still cannot reach alpha.
        assert M.exact_p(m, 0) >= M.ALPHA
    assert M.critical_k(M.MIN_DISCORDANT) is not None
    assert M.exact_p(M.MIN_DISCORDANT, 0) < M.ALPHA


def test_critical_k_matches_brute_force() -> None:
    for m in range(80):
        brute = None
        for k in range(m // 2 + 1):
            if _brute_exact_p(m - k, k) < M.ALPHA:
                brute = k
        assert M.critical_k(m) == brute, m


def test_normal_branch_agrees_with_the_exact_sum_at_the_crossover() -> None:
    """EXACT_M_LIMIT must not put a seam in the sizing table."""
    original = M.EXACT_M_LIMIT
    try:
        cases = ((1500, 0.20, 0.05), (3000, 0.20, 0.05), (900, 0.35, 0.08))
        for n, psi, delta in cases:
            M.EXACT_M_LIMIT = 10**9
            M.critical_k.cache_clear()
            exact = M.exact_power(n, psi, delta)
            M.EXACT_M_LIMIT = original
            M.critical_k.cache_clear()
            approx = M.exact_power(n, psi, delta)
            assert abs(exact - approx) < 1e-4, (n, psi, delta, exact, approx)
    finally:
        M.EXACT_M_LIMIT = original
        M.critical_k.cache_clear()


def test_power_is_monotone_in_n_and_in_effect() -> None:
    prev = -1.0
    for n in (50, 100, 200, 400, 800):
        power = M.exact_power(n, 0.20, 0.05)
        assert power >= prev
        prev = power
    prev = -1.0
    for delta in (0.02, 0.04, 0.06, 0.08, 0.10):
        power = M.exact_power(300, 0.20, delta)
        assert power >= prev
        prev = power


def test_effect_can_never_exceed_the_discordance_rate() -> None:
    """psi >= |delta| by construction; asking otherwise is not a small effect."""
    assert M.exact_power(100, 0.10, 0.20) == 0.0
    assert M.required_n(0.20, 0.10) is None


def test_twenty_tasks_resolve_nothing_across_the_measured_psi_range() -> None:
    """The ADR's claim about every bundle instrument this repository owns."""
    for psi in (0.05, 0.10, 0.20, 0.25, 0.35):
        assert M.detectable_delta(20, psi) is None


def test_detectable_delta_is_quantised_to_whole_tasks() -> None:
    for n in (100, 200, 400):
        delta = M.detectable_delta(n, 0.20)
        assert delta is not None
        assert math.isclose(delta * n, round(delta * n))


def test_required_n_and_detectable_delta_agree() -> None:
    """The two directions of one question must not disagree."""
    for psi in (0.10, 0.20, 0.35):
        for delta in (0.05, 0.10):
            n = M.required_n(delta, psi)
            assert n is not None
            assert M.exact_power(n, psi, delta) >= M.POWER
            assert M.exact_power(n - 1, psi, delta) < M.POWER


def test_humaneval_sizing_reproduces_the_published_figure() -> None:
    """n=164 at a 10% discordance rate resolves +6.9pp — the prior-art anchor.

    Recorded in ``archive/docs/adoption-bar-prior-art-2026-08-10.md``: an independent
    source states 6.9 points for HumanEval at the same alpha, power and
    disagreement rate. Quantised here to whole items out of 164.
    """
    delta = M.detectable_delta(164, 0.10)
    assert delta is not None
    assert 0.060 <= delta <= 0.075


def test_contrast_reads_the_discordance_structure_off_a_measured_table() -> None:
    """CLM-0012's c0->c2 arm: +1 task net, and unresolvable at any split."""
    k = M.Contrast("jsts c0->c2", n=20, gained=3, lost=2)
    assert k.discordant == 5
    assert k.net == 1
    assert math.isclose(k.psi, 0.25)
    assert math.isclose(k.delta, 0.05)
    assert k.p_value == 1.0
    assert not k.can_ever_reject


def test_contrast_can_ever_reject_turns_on_at_six() -> None:
    assert not M.Contrast("five", n=20, gained=5, lost=0).can_ever_reject
    assert M.Contrast("six", n=20, gained=6, lost=0).can_ever_reject
