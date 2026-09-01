"""This workload is 3:1 prompt:output, and nothing here has ever measured prefill.

Both sweep drivers divide by the same wall — ``agg = gen/wall`` and
``prefill = pin/wall`` — so ``prefill/agg`` is ``ptok/otok`` identically. Verified
to three decimals on every row of the 2026-09-01 A/B. A sentence claiming that
"prefill gains track decode" restates arithmetic, and one was written into
``okf/must-read/touching-engine.md`` and committed before this was noticed.

So a prefill verdict needs ``llama-bench -p N``, which times prompt processing
separately with fixed synthetic token counts, no sampler, no early stop, no HTTP
and no client threads. Two consequences the tests below encode: it must report a
per-repetition spread (``-r 9``; the same build read 55.7 and 86.4 t/s at ``-r 3``
and ``-r 9``), and it must sweep ``-fa 0,1`` because the arch change moves the
flash-attention kernel selection as well as the mat-mul one, and a single
``-fa on`` number cannot tell those apart.
"""

from __future__ import annotations

import pytest

from tests.sweeprows import owed

BENCH = "srv1-llama-bench.tsv"
ARMS = ("L0", "L1", "L2", "L3", "A3")


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no prefill microbenchmark")
def test_prefill_is_timed_separately_and_not_derived_from_the_ladder() -> None:
    sweep = owed(BENCH)
    assert sweep.stamp("TOOL").get("name") == "llama-bench", (
        "a prefill verdict from the sweep driver is a verdict about ptok/otok"
    )
    rows = sweep.levels() or list(sweep.of_kind("BENCH"))
    assert rows, "the microbenchmark recorded nothing"
    for row in rows:
        assert "pp" in row.fields, (
            f"line {row.lineno}: no pp= (prompt-processing) column"
        )
        assert "tg" in row.fields, (
            f"line {row.lineno}: no tg= (token-generation) column"
        )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no prefill microbenchmark")
def test_every_bench_row_reports_its_own_spread_over_at_least_nine_repetitions() -> (
    None
):
    """``-r 3`` and ``-r 9`` on one build read 55.7 and 86.4 t/s. A point estimate
    from three draws is a number, not a measurement."""
    sweep = owed(BENCH)
    for row in sweep.of_kind("BENCH"):
        assert int(row.fields.get("reps", "0")) >= 9, (
            f"line {row.lineno}: {row.fields.get('reps')} repetitions"
        )
        assert "stddev" in row.fields, f"line {row.lineno}: no stddev="


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no prefill microbenchmark")
def test_the_flash_attention_kernel_is_separated_from_the_matmul_kernel() -> None:
    """The arch change moves ``ggml_cuda_get_best_fattn_kernel`` on the same
    ``turing_mma_available`` test that moves MMQ. One number for both attributes
    a gain to whichever the reader already believed in."""
    sweep = owed(BENCH)
    seen: dict[str, set[str]] = {}
    for row in sweep.of_kind("BENCH"):
        seen.setdefault(row.fields.get("arm", "?"), set()).add(
            row.fields.get("fa", "?")
        )
    for arm, flags in seen.items():
        assert flags >= {"0", "1"}, f"{arm} was measured only at -fa {sorted(flags)}"
