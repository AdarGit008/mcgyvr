"""The fleet identity design approves a fleet on arithmetic no rig has measured yet.

RED. Each test below states what one measurement must establish. Each fails until
the run's record exists under ``records/measurements/fleet-identity-2026-09-11/``
and meets the criterion. The plan that says how each record is taken is
``records/plans/fleet-identity-measurements-2026-09-11.md``. This file is the
authority on the scope and the criteria, and the plan follows it.

Where a test recomputes a figure from the raw rows, the rule is spelled once, here.
A derived record that disagrees with its own rows fails as surely as a missing one.

The eight measurements, each the owner's ruling of 2026-09-11:

M1  warm decode: no-NVMe baseline vs as-run, per unit x rig, and the class tolerances
M2  cold wake per unit x rig, on named clocks
M3  vLLM host RAM per rig
M4  unmapped Shmem as a per-model residual
M5  fp8 KV cache on the RTX 3060: backend, card, decode, answers
M6  ``--kv-cache-memory-bytes``: same size every start, oversized values, start gate
M7  headroom per rig, and resized srv2 shares that pass both start orders
M8  ``gpu_reserve_mib`` across at least two boots per rig
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving import vramfit

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "records" / "measurements" / "fleet-identity-2026-09-11"
MIB = 1 << 20
GIB = 1 << 30

QWEN36 = "Qwen3.6-35B-A3B-UD-IQ3_XXS"
LING = "Ling-3.0-tiny-Q4_K_M"
CODER_3B = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
CODER_7B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
RIGS = ("srv1", "srv2")

#: (rig, unit) -> decode class. The live fleet's three units, plus Ling, which
#: stands in for the llama.cpp class the live fleet has no card-only unit for.
DECODE_UNITS: dict[tuple[str, str], str] = {
    ("srv1", QWEN36): "cpu_experts",
    ("srv1", LING): "llamacpp",
    ("srv2", CODER_3B): "vllm",
    ("srv2", CODER_7B): "vllm",
}
CLASSES = ("vllm", "llamacpp", "cpu_experts")
#: The vLLM units whose host RAM is read, at least one per rig.
HOST_RAM_UNITS = {("srv1", CODER_3B), ("srv2", CODER_3B), ("srv2", CODER_7B)}
#: llama.cpp model -> the ``--n-cpu-moe`` placements its unmapped Shmem is read at.
SHMEM_PLACEMENTS: dict[str, set[int]] = {QWEN36: {30, 32}, LING: {0, 4}}
SHMEM_RESIDUAL_SPREAD_MIB = 16

COLD_STARTS = 3
WARM_SAMPLES = 5
DECODE_TOKENS = 256
#: The refusal gate's margin, ``REFUSAL_RAM_HEADROOM_GB``: a llama.cpp baseline
#: that cannot clear it is not launched with swap off, and says so.
NO_BASELINE_HEADROOM_GIB = 2.0
CLOCKS = ("door_process_s", "door_unit_s", "started_at_to_ready_s")
BENCH_CELLS = 257
PINNED_CASES = ("first_start", "restart", "neighbour_active")
START_GATE_REFUSAL = "is less than desired GPU memory utilization"


def _record(name: str) -> Any:
    path = RUN / name
    if not path.exists():
        pytest.fail(f"not measured yet: {path.relative_to(REPO)}", pytrace=False)
    return json.loads(path.read_text(encoding="utf-8"))


def _key(rig: str, unit: str) -> str:
    return f"{rig}/{unit}"


# --- M1 ----------------------------------------------------------------------


def _warm_samples(
    rows: list[dict[str, Any]], rig: str, unit: str, arm: str
) -> list[float]:
    return [
        float(sample["tok_s"])
        for row in rows
        if row["rig"] == rig
        and row["unit"] == unit
        and row["arm"] == arm
        and "samples" in row
        for sample in row["samples"]
    ]


def _shortfall(samples: list[float]) -> float:
    median = statistics.median(samples)
    return max((median - x) / median for x in samples)


def _class_tolerances_pct(rows: list[dict[str, Any]]) -> dict[str, int]:
    """The rule fixed before the run: the worst single warm sample below its
    unit-and-arm median, over the class's units and both arms, as a percent,
    rounded up to a whole percent, never under 1."""
    worst: dict[str, float] = {}
    for (rig, unit), cls in DECODE_UNITS.items():
        for arm in ("baseline", "as_run"):
            samples = _warm_samples(rows, rig, unit, arm)
            if samples:
                worst[cls] = max(worst.get(cls, 0.0), _shortfall(samples))
    return {cls: max(1, math.ceil(100 * worst[cls] - 1e-9)) for cls in worst}


def test_every_unit_has_a_no_nvme_baseline_and_an_as_run_warm_decode() -> None:
    """M1. Per unit x rig, 3 cold starts with everything in RAM and VRAM (swap
    off, and llama.cpp unmapped), and 3 as the unit really runs (swap as found).
    Each start keeps 5 warm samples of exactly 256 tokens after a discarded
    warm-up. A llama.cpp model whose unmapped need cannot clear the refusal
    margin is recorded as "no baseline: NVMe required", with both figures."""
    rows = _record("results-decode.json")
    for (rig, unit), cls in DECODE_UNITS.items():
        mine = [r for r in rows if r["rig"] == rig and r["unit"] == unit]
        assert mine, f"{_key(rig, unit)}: no decode rows"
        for arm in ("baseline", "as_run"):
            starts = [r for r in mine if r["arm"] == arm]
            refused = [r for r in starts if r.get("no_baseline")]
            if arm == "baseline" and refused:
                no = refused[0]
                assert no["no_baseline"] == "NVMe required"
                assert (
                    no["ram_need_gib"]
                    > no["ram_available_gib"] - NO_BASELINE_HEADROOM_GIB
                )
                continue
            assert len(starts) >= COLD_STARTS, (
                f"{_key(rig, unit)} {arm}: {len(starts)} starts"
            )
            for row in starts:
                where = f"{_key(rig, unit)} {arm} start {row.get('start')}"
                assert row["class"] == cls, where
                assert row["warmup_discarded"] >= 1, where
                assert len(row["samples"]) >= WARM_SAMPLES, where
                assert all(
                    s["completion_tokens"] == DECODE_TOKENS for s in row["samples"]
                ), where
                assert isinstance(row["restart_count"], int), where
                assert isinstance(row["pgmajfault_decode"], int), where
                if arm == "baseline":
                    assert row["swap_total_mib"] == 0, where
                    assert row["pswpout_decode"] == 0, where
                    if cls != "vllm":
                        argv = row["argv"]
                        assert argv[argv.index("--load-mode") + 1] == "none", where
                else:
                    assert row["swap_total_mib"] > 0, where


def test_the_decode_tolerances_follow_the_rule_fixed_before_the_run() -> None:
    """M1. The three class tolerances that replace the survey's provisional
    -3% vLLM, -5% llama.cpp and -15% CPU experts, each recomputed from the rows."""
    rows = _record("results-decode.json")
    recorded = _record("tolerances.json")
    derived = _class_tolerances_pct(rows)
    assert set(derived) == set(CLASSES)
    for cls in CLASSES:
        assert recorded["classes"][cls]["tolerance_pct"] == derived[cls], cls


def test_nvme_is_allowed_only_where_the_as_run_gap_is_inside_its_class_tolerance() -> (
    None
):
    """M1. gap = (median baseline - median as-run) / median baseline. NVMe is
    allowed iff the gap is within the class tolerance, and the approved value is
    the as-run median. A unit with no baseline is approved on its as-run median."""
    rows = _record("results-decode.json")
    recorded = _record("tolerances.json")
    tolerances = _class_tolerances_pct(rows)
    for (rig, unit), cls in DECODE_UNITS.items():
        verdict = recorded["units"][_key(rig, unit)]
        as_run = statistics.median(_warm_samples(rows, rig, unit, "as_run"))
        assert verdict["approved_tok_s"] == pytest.approx(as_run, rel=1e-6)
        baseline = _warm_samples(rows, rig, unit, "baseline")
        if not baseline:
            assert verdict["nvme"] == "no baseline: NVMe required"
            continue
        gap = (statistics.median(baseline) - as_run) / statistics.median(baseline)
        assert verdict["gap_pct"] == pytest.approx(100 * gap, abs=1e-6)
        expected = "allowed" if 100 * gap <= tolerances[cls] else "not allowed"
        assert verdict["nvme"] == expected, _key(rig, unit)


# --- M2 ----------------------------------------------------------------------


def test_every_unit_has_a_cold_wake_on_three_named_clocks() -> None:
    """M2. Per unit x rig, 3 cold starts with the page cache dropped and no
    restart. Each is read on the Waker's clock (the door process), the door's
    per-unit clock, and StartedAt-to-first-200. The summary names the clock the
    design reads and its median. A srv2 unit is started alone, because the live
    pair's ``service_started`` ordering crash-restarts the 3B cold."""
    rows = _record("results-wake.json")
    summary = _record("wake.json")
    for rig, unit in DECODE_UNITS:
        starts = [r for r in rows if r["rig"] == rig and r["unit"] == unit]
        assert len(starts) >= COLD_STARTS, _key(rig, unit)
        for row in starts:
            assert row["restart_count"] == 0
            assert row["page_cache_dropped"] is True
            assert row["co_residents"] == []
            clocks = row["clocks"]
            assert all(clocks[name] > 0 for name in CLOCKS)
            assert clocks["door_process_s"] >= clocks["door_unit_s"]
        entry = summary[_key(rig, unit)]
        assert entry["clock"] == "door_process_s"
        assert entry["n"] == len(starts)
        assert entry["median_s"] == pytest.approx(
            statistics.median(r["clocks"]["door_process_s"] for r in starts)
        )


# --- M3 ----------------------------------------------------------------------


def test_vllm_host_ram_is_measured_on_each_rig() -> None:
    """M3. What one vLLM unit costs in host RAM: MemAvailable idle less
    MemAvailable with the unit healthy, the page cache dropped before both reads.
    3 cold starts per unit, and a per-rig figure that is the largest row."""
    rows = _record("results-host-ram.json")
    summary = _record("host-ram.json")
    for rig, unit in HOST_RAM_UNITS:
        starts = [r for r in rows if r["rig"] == rig and r["unit"] == unit]
        assert len(starts) >= COLD_STARTS, _key(rig, unit)
        for row in starts:
            assert row["restart_count"] == 0
            assert row["page_cache_dropped_before_both_reads"] is True
            assert row["cost_gib"] == pytest.approx(
                row["mem_available_idle_gib"] - row["mem_available_up_gib"]
            )
            assert row["process_rss_gib"] > 0
    for rig in RIGS:
        mine = [r["cost_gib"] for r in rows if r["rig"] == rig]
        assert summary[rig]["cost_gib"] == pytest.approx(max(mine)), rig


# --- M4 ----------------------------------------------------------------------


def test_unmapped_shmem_is_one_residual_per_model() -> None:
    """M4. Unmapped (``--load-mode none``, swap off), Shmem with the unit up less
    Shmem idle, less the experts the tensor table spills at that placement, is a
    per-model residual. It is recomputed here from the geometry, and it spreads
    by no more than 16 MiB across starts and placements."""
    rows = _record("results-shmem.json")
    for model, placements in SHMEM_PLACEMENTS.items():
        geometry = _record(f"{model}.geometry.json")
        residuals: list[float] = []
        for n_cpu_moe in placements:
            starts = [
                r for r in rows if r["model"] == model and r["n_cpu_moe"] == n_cpu_moe
            ]
            assert len(starts) >= 2, f"{model} at --n-cpu-moe {n_cpu_moe}"
            spilled = (
                geometry["bytes_experts"] - vramfit.experts_on_card(geometry, n_cpu_moe)
            ) / GIB
            for row in starts:
                assert row["load_mode"] == "none"
                assert row["swap_total_mib"] == 0
                residual = row["shmem_up_gib"] - row["shmem_idle_gib"] - spilled
                assert row["residual_gib"] == pytest.approx(residual, abs=1e-6)
                residuals.append(residual)
        spread_mib = (max(residuals) - min(residuals)) * 1024
        assert spread_mib <= SHMEM_RESIDUAL_SPREAD_MIB, f"{model}: {spread_mib:.1f} MiB"


# --- M5 ----------------------------------------------------------------------


def _bench(name: str) -> dict[str, bool]:
    path = RUN / name / "bench-py" / "results.jsonl"
    if not path.exists():
        pytest.fail(f"not measured yet: {path.relative_to(REPO)}", pytrace=False)
    verdicts: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["arm"] == "greedy":
            verdicts[row["task"]] = bool(row["passed"])
    return verdicts


def _wilson_upper(k: int, n: int) -> float:
    spec = importlib.util.spec_from_file_location(
        "bench_responsiveness", REPO / "tools" / "bench" / "responsiveness.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    upper: float = module.wilson(k, n)[1]
    return upper


def _flips(a: dict[str, bool], b: dict[str, bool]) -> int:
    return sum(1 for task in a if a[task] != b[task])


def test_fp8_kv_on_the_rtx_3060_names_its_backend_card_decode_and_answers() -> None:
    """M5. The live 7B alone on srv2 (cc 8.6), ``--kv-cache-dtype auto`` against
    ``fp8``, 3 cold starts each. Each start records the attention backend from
    vLLM's own log line, the card, the KV tokens and warm decode. fp8 does not
    select FLASH_ATTN on sm_86 (the v0.26.0 selector). Answers are compared with
    greedy bench-py, run twice per dtype, against each dtype's own a/b null bound."""
    rows = _record("results-fp8.json")
    backend = re.compile(r"Using (\w+) attention backend out of potential backends")
    chosen: dict[str, set[str]] = {}
    for dtype in ("auto", "fp8"):
        starts = [r for r in rows if r["kv_cache_dtype"] == dtype]
        assert len(starts) >= COLD_STARTS, dtype
        for row in starts:
            assert row["rig"] == "srv2" and row["unit"] == CODER_7B
            assert row["gpu_cc"] == "8.6"
            assert row["restart_count"] == 0
            found = backend.search(row["backend_line"])
            assert found, row["backend_line"]
            assert row["attention_backend"] == found.group(1)
            chosen.setdefault(dtype, set()).add(found.group(1))
            assert row["card_used_mib"] > 0
            assert row["kv_tokens"] > 0
            assert len(row["samples"]) >= WARM_SAMPLES
            assert all(s["completion_tokens"] == DECODE_TOKENS for s in row["samples"])
    assert "FLASH_ATTN" not in chosen["fp8"]

    runs = {
        name: _bench(name)
        for name in (
            "bench-7b-auto-a",
            "bench-7b-auto-b",
            "bench-7b-fp8-a",
            "bench-7b-fp8-b",
        )
    }
    assert all(len(v) == BENCH_CELLS for v in runs.values())
    null_auto = _wilson_upper(
        _flips(runs["bench-7b-auto-a"], runs["bench-7b-auto-b"]), BENCH_CELLS
    )
    null_fp8 = _wilson_upper(
        _flips(runs["bench-7b-fp8-a"], runs["bench-7b-fp8-b"]), BENCH_CELLS
    )
    contrast = _flips(runs["bench-7b-auto-a"], runs["bench-7b-fp8-a"])
    quality = _record("fp8-quality.json")
    assert quality["flips"] == contrast
    assert quality["bound_pp"] == pytest.approx(100 * max(null_auto, null_fp8))
    within = 100 * contrast / BENCH_CELLS <= 100 * max(null_auto, null_fp8)
    assert quality["verdict"] == ("within null" if within else "outside null")


# --- M6 ----------------------------------------------------------------------


def test_a_pinned_kv_keeps_its_size_on_restart_and_beside_a_busy_neighbour() -> None:
    """M6. With ``--kv-cache-memory-bytes`` set, the logged KV size is identical
    on a first start, on a docker restart that keeps the container's writable
    layer, and on a start while the neighbouring unit serves a saturating load."""
    rows = _record("results-pinned-kv.json")
    for unit in (CODER_3B, CODER_7B):
        cases = {
            r["case"]: r
            for r in rows
            if r["unit"] == unit and r["case"] in PINNED_CASES
        }
        assert set(cases) == set(PINNED_CASES), unit
        assert len({c["kv_cache_memory_bytes"] for c in cases.values()}) == 1
        assert len({c["kv_tokens"] for c in cases.values()}) == 1, unit
        assert all("reserved" in c["kv_line"] for c in cases.values())
        assert cases["first_start"]["restart_count"] == 0
        assert cases["restart"]["restart_count"] >= 1
        assert cases["neighbour_active"]["neighbour_under_load"] is True


def test_an_oversized_pinned_kv_runs_past_its_share_and_fails_past_the_card() -> None:
    """M6. A pinned size that takes the unit past its share but not past free
    memory serves, because the pinned path "does not respect the
    gpu_memory_utilization config".
    A pinned size above the card's free memory fails at start and never shrinks."""
    rows = {r["case"]: r for r in _record("results-pinned-kv.json")}
    over_share = rows["oversized_share"]
    assert over_share["outcome"] == "served"
    # The pinned size plus what the unit holds beside its KV passes the room: the
    # unit's own peak under load is past it, and it still served.
    assert over_share["peak_process_mib"] * MIB > over_share["room_bytes"]
    over_card = rows["oversized_card"]
    assert over_card["outcome"] == "failed_at_start"
    assert over_card["kv_cache_memory_bytes"] > over_card["free_at_start_bytes"]
    assert over_card["error_line"]


def test_the_start_gate_still_refuses_a_pinned_unit_that_free_memory_cannot_hold() -> (
    None
):
    """M6. The start gate (free >= ceil(total x util)) runs before the pinned path,
    so a pinned unit whose share free memory cannot hold is refused."""
    row = {r["case"]: r for r in _record("results-pinned-kv.json")}["start_gate"]
    assert row["outcome"] == "failed_at_start"
    assert START_GATE_REFUSAL in row["error_line"]


# --- M7 ----------------------------------------------------------------------


def test_headroom_is_reserve_plus_contexts_and_srv2_shares_pass_both_orders() -> None:
    """M7. Per rig, headroom = the card reserve + every unit's CUDA context. On
    srv2, the proposed shares and pinned KV satisfy
    sum(ceil(share x T)) + sum(contexts) <= T, where T is the total vLLM reads.
    The pair started in either order comes up with no restart, the pinned size it
    was given, and every unit's peak under load inside its room plus context."""
    record = _record("results-headroom.json")
    for rig in RIGS:
        entry = record["rigs"][rig]
        assert entry["reserve_mib"] > 0
        assert entry["contexts_mib"] and all(
            v > 0 for v in entry["contexts_mib"].values()
        )
        assert entry["headroom_mib"] == pytest.approx(
            entry["reserve_mib"] + sum(entry["contexts_mib"].values())
        )

    proposal = record["srv2_proposal"]
    total = proposal["torch_total_bytes"]
    rooms = {u: math.ceil(proposal["shares"][u] * total) for u in (CODER_3B, CODER_7B)}
    contexts = {u: proposal["contexts_bytes"][u] for u in (CODER_3B, CODER_7B)}
    assert sum(rooms.values()) + sum(contexts.values()) <= total
    assert (
        total / MIB + record["rigs"]["srv2"]["reserve_mib"]
        <= record["rigs"]["srv2"]["card_total_mib"]
    )

    for order in ("3b_first", "7b_first"):
        starts = [r for r in record["orders"] if r["order"] == order]
        assert len(starts) >= 2, order
        for row in starts:
            for unit in (CODER_3B, CODER_7B):
                got = row["units"][unit]
                assert got["healthy"] is True, (order, unit)
                assert got["restart_count"] == 0, (order, unit)
                assert (
                    got["kv_cache_memory_bytes"]
                    == proposal["kv_cache_memory_bytes"][unit]
                )
                assert got["peak_process_mib"] * MIB <= rooms[unit] + contexts[unit]


# --- M8 ----------------------------------------------------------------------


def test_the_card_reserve_is_read_idle_on_at_least_two_boots_per_rig() -> None:
    """M8. ``gpu_reserve_mib`` is read with nothing on the card, on at least two
    boots per rig named by their ``uptime_since``, with the same card and driver.
    Gate 2 compares the reserve with ``hosts.json`` literally, so a reserve that
    moves between boots refuses every door run until the declaration moves."""
    rows = _record("results-reserve.json")
    for rig in RIGS:
        mine = [r for r in rows if r["rig"] == rig and r["gpu_procs"] == "none"]
        assert len({r["uptime_since"] for r in mine}) >= 2, rig
        assert len({(r["gpu_name"], r["driver"]) for r in mine}) == 1, rig
        assert all(isinstance(r["gpu_reserve_mib"], int) for r in mine)
