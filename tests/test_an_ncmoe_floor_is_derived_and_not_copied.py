"""The ``--n-cpu-moe`` floor is VRAM-bound, so each arm has its own.

``okf/config/llama.cpp.md`` said the floor was bounded by host RAM until
2026-09-01, when srv2's floor was measured at 6 against an archive that had been
running 24-99 — a 3-12x misplacement worth ~2.4x. The correction matters here
because each arm in this campaign carries different VRAM overhead: a Vulkan
build's allocator is not a CUDA build's, and a PTX-only build's context is not a
SASS build's. A floor copied between arms is not a floor.

Two rules. The derivation states its own inputs and the arithmetic reproduces
from them. And the floor is established by a recorded refusal one step below it,
retried, because a launch near the memory edge is a 1-in-3 coin flip and two
REFUSED rows on 2026-09-01 turned out to be a dangling HF-blob symlink read as a
capability limit.
"""

from __future__ import annotations

from itertools import combinations

import pytest

from tests.sweeprows import owed

FLOOR = "srv1-ncmoe-floor.tsv"
INPUTS = (
    "usable_mib",
    "cuda_ctx_mib",
    "nonexpert_mib",
    "kv_mib",
    "expert_total_mib",
    "n_layers",
)


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no per-arm floor")
def test_each_arm_derives_its_floor_from_its_own_numbers() -> None:
    sweep = owed(FLOOR)
    stamps = {s["arm"]: s for s in sweep.stamps("FLOOR") if "arm" in s}
    assert len(stamps) >= 2, f"floors derived for only {sorted(stamps)}"
    for arm, stamp in stamps.items():
        for field in (*INPUTS, "predicted", "measured"):
            assert stamp.get(field), f"{arm}: the derivation states no {field}"
        budget = (
            float(stamp["usable_mib"])
            - float(stamp["cuda_ctx_mib"])
            - float(stamp["nonexpert_mib"])
            - float(stamp["kv_mib"])
        )
        resident = budget / float(stamp["expert_total_mib"])
        predicted = (1 - resident) * float(stamp["n_layers"])
        assert abs(predicted - float(stamp["predicted"])) <= 1.0, (
            f"{arm}: the stamped inputs give {predicted:.1f}, the stamp claims "
            f"{stamp['predicted']}. Both weight terms come from the tensor "
            "table, never from the file size."
        )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no per-arm floor")
def test_two_arms_reporting_one_floor_did_not_reach_it_from_one_set_of_numbers() -> (
    None
):
    sweep = owed(FLOOR)
    stamps = {s["arm"]: s for s in sweep.stamps("FLOOR") if "arm" in s}
    for a, b in combinations(sorted(stamps), 2):
        if stamps[a].get("measured") != stamps[b].get("measured"):
            continue
        assert tuple(stamps[a].get(k) for k in INPUTS) != tuple(
            stamps[b].get(k) for k in INPUTS
        ), (
            f"{a} and {b} report the same floor from byte-identical inputs. The "
            "floor is VRAM-bound and these arms have different VRAM overhead; "
            "identical inputs means one was copied."
        )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no per-arm floor")
def test_the_refusal_below_the_floor_is_the_measurement() -> None:
    sweep = owed(FLOOR)
    refusals = sweep.of_kind("REFUSED")
    assert refusals, "no cell was run below the predicted floor, so no edge was found"
    for row in refusals:
        assert int(row.fields.get("tries", "1")) >= 3, (
            f"line {row.lineno}: believed after {row.fields.get('tries')} "
            "attempt(s); a launch near the memory edge is a 1-in-3 coin flip"
        )
        assert len(" ".join(row.tail)) > 40, (
            f"line {row.lineno}: refused with no reason recorded"
        )
