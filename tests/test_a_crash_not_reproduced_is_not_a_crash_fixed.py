"""A patched build surviving proves nothing unless the unpatched one is recorded
dying, on the same boot, in the same session.

The defect: ``get_mmvq_mmid_max_batch`` branches on the raw runtime ``cc`` (750,
Turing) while the device kernel's ``__launch_bounds__`` are baked from
``__CUDA_ARCH__`` (610, Pascal, because the build ships only ``61-virtual`` PTX).
The host hands out a batch the compiled kernel cannot launch, and llama.cpp
aborts with ``CUDA error: invalid argument`` inside
``ggml_cuda_mul_mat_vec_q``. ``get_device_table_id`` 148 lines above in the same
file already reads the compiled arch; this function was missed.

It is a batch-size boundary, so the run must locate the boundary rather than
poke n=8 — show the unpatched build's window and show the patched one crossing
it clean. And "clean" needs a denominator: 0 failures in 60 trials bounds the
failure rate at 5%; 30 trials only reaches 10%. One clean run bounds nothing,
which is exactly what ``touching-rigs.md`` already records about the 12-minute
offload run that "did not reproduce".
"""

from __future__ import annotations

import pytest

from tests.sweeprows import owed

SLOTS = "srv1-moe-slots.tsv"
CRASH_MARKS = ("ggml_cuda_mul_mat_vec_q", "invalid argument")
MIN_TRIALS = 60


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no re-crash on this boot")
def test_the_unpatched_build_crashes_and_the_log_says_why() -> None:
    sweep = owed(SLOTS)
    crashes = [r for r in sweep.of_kind("CRASH") if r.fields.get("arm") == "L2"]
    assert crashes, "L2 (the unpatched arm) has no recorded crash on this boot"
    for row in crashes:
        reason = " ".join(row.tail) + " " + row.fields.get("reason", "")
        for mark in CRASH_MARKS:
            assert mark in reason, (
                f"line {row.lineno}: the reason does not contain {mark!r}: "
                f"{reason[:160]!r}. A bare ERR says a cell produced no tokens; it "
                "does not say the kernel died, and this run exists to say so."
            )
        failed, total = row.frac("http_000")
        assert failed == total, f"line {row.lineno}: {failed}/{total} returned 000"


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — crash boundary unlocated")
def test_the_boundary_is_located_rather_than_poked() -> None:
    sweep = owed(SLOTS)
    widths = {
        int(r.fields["n"])
        for r in sweep.of_kind("CRASH")
        if r.fields.get("arm") == "L2"
    }
    widths |= {
        r.n for r in sweep.levels() if r.fields.get("arm") == "L2" and r.n is not None
    }
    assert widths >= set(range(1, 13)), (
        f"L2 was measured at n={sorted(widths)}. The defect is a batch-size "
        "boundary; a single width shows a symptom, not an edge."
    )
    stamp = sweep.stamp("BOUNDARY")
    assert stamp.get("arm") == "L2" and stamp.get("first_failing_n"), (
        "no ### BOUNDARY names the first width at which the unpatched build fails"
    )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — patched build unsoaked")
def test_the_patched_build_survives_the_widths_that_kill_the_unpatched_one() -> None:
    sweep = owed(SLOTS)
    killed = {
        (r.cell, int(r.fields["n"]))
        for r in sweep.of_kind("CRASH")
        if r.fields.get("arm") == "L2"
    }
    assert killed, "no L2 crash, so this assertion has no cells to make"
    for cell, width in sorted(killed):
        clean = [
            r
            for r in sweep.levels()
            if r.fields.get("arm") == "L3" and r.cell == cell and r.n == width
        ]
        assert clean, f"L3 was never measured at {cell} n={width} — the cell L2 dies on"
        trials = sum(int(r.fields.get("trials", "1")) for r in clean)
        assert trials >= MIN_TRIALS, (
            f"{cell} n={width}: {trials} trial(s). 0 failures in 60 bounds the "
            f"failure rate at 5%; {trials} bounds it at "
            f"{300 // max(trials, 1)}% at best."
        )
        for row in clean:
            assert row.frac("failed")[0] == 0 and row.num("otok") > 1


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — one MoE checkpoint only")
def test_two_moe_checkpoints_with_different_expert_geometry_are_driven() -> None:
    """The failing kernel dispatches on expert ids, and the batch limit is
    per-quant-type. One checkpoint shows one window."""
    sweep = owed(SLOTS)
    cells = {r.cell for r in sweep.rows if r.kind in ("CRASH",) or r.n is not None}
    assert len(cells) >= 2, f"only {sorted(cells)} was driven"
