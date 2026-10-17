""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#
#
#
CACHE_ELEM_BYTES = {"f32": 4.0, "f16": 2.0, "bf16": 2.0, "q8_0": 34.0 / 32.0}

#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
SCRATCH_AND_CONTEXT_MIB = 768

#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
MEASURED_SCRATCH_MIB = {
    "deepseek2": {256: 259.5},
    "gptoss": {256: 302.1},
    "qwen35moe": {256: 302.7, 512: 316.57},
    "nemotron_h_moe": {256: 521.2},
    #
    #
    "qwen3next": {512: 829.0},
}

#
#
SWA_PAD = 256


def _pad(value: int, to: int) -> int:
    return -(-value // to) * to


def context_per_sequence(n_ctx: int, n_seq_max: int) -> int:
    ""
    if n_seq_max <= 0:
        raise ValueError("n_seq_max must be positive")
    #
    #
    #
    return _pad(-(-n_ctx // n_seq_max), 256)


def kv_bytes(
    geometry: dict[str, Any],
    n_ctx: int,
    *,
    n_seq_max: int = 1,
    n_ubatch: int = 512,
    cache_type_k: str = "f16",
    cache_type_v: str = "f16",
    swa_full: bool = False,
    kv_unified: bool = False,
    layers: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    ""
    rows = geometry["kv_layers"] if layers is None else layers

    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    unknown = [r["layer"] for r in rows if r.get("is_swa") is None]
    if unknown:
        raise ValueError(
            f"{geometry.get('arch')} declares sliding_window "
            f"{geometry.get('sliding_window')} but no per-layer "
            f"sliding_window_pattern, so which of layers {unknown[0]}..."
            f"{unknown[-1]} slide is unknown and the cache cannot be sized. "
            "Read the split from the engine's own "
            "`llama_kv_cache_iswa: creating non-SWA/SWA KV cache` lines and "
            "pass the rows as kv_bytes(layers=...)"
        )

    b_k = CACHE_ELEM_BYTES[cache_type_k]
    b_v = CACHE_ELEM_BYTES[cache_type_v]

    def width(row: dict[str, Any]) -> float:
        return float(row["k_elems"]) * b_k + float(row["v_elems"]) * b_v

    full = sum(width(r) for r in rows if not r["is_swa"])
    swa = sum(width(r) for r in rows if r["is_swa"])

    #
    #
    #
    if kv_unified:
        cells_full, seq_factor = n_ctx, 1
    else:
        cells_full, seq_factor = context_per_sequence(n_ctx, n_seq_max), n_seq_max

    window = geometry.get("sliding_window")
    if swa_full or not window:
        cells_swa = cells_full
    else:
        #
        #
        #
        #
        want = int(window) * (n_seq_max if kv_unified else 1) + n_ubatch
        cells_swa = min(cells_full, _pad(want, SWA_PAD))

    non_swa_bytes = int(cells_full * seq_factor * full)
    swa_bytes = int(cells_swa * seq_factor * swa)
    return {
        "total": non_swa_bytes + swa_bytes,
        "non_swa": non_swa_bytes,
        "swa": swa_bytes,
        "n_ctx_seq": cells_full,
        "cells_swa": cells_swa if swa else 0,
    }


def rs_bytes(
    geometry: dict[str, Any],
    *,
    n_seq_max: int,
    recurrent_layers_on_device: int | None = None,
) -> dict[str, int]:
    ""
    layers = geometry.get("n_recurrent", 0)
    if recurrent_layers_on_device is not None:
        layers = recurrent_layers_on_device
    if not layers:
        return {"total": 0, "s": 0, "r": 0}
    inner = geometry.get("ssm_inner_size")
    state = geometry.get("ssm_state_size")
    if not (inner and state):
        raise ValueError(
            f"{geometry.get('arch')} has {layers} recurrent blocks but states no "
            "state size; returning zero here would hide a real allocation"
        )
    conv = geometry.get("ssm_conv_kernel") or 0
    groups = geometry.get("ssm_group_count") or 0
    s = n_seq_max * layers * inner * state * 4
    r = n_seq_max * layers * max(0, conv - 1) * (inner + 2 * groups * state) * 4
    return {"total": s + r, "s": s, "r": r}


def experts_on_card(geometry: dict[str, Any], n_cpu_moe: int) -> int:
    ""
    by_block = geometry["expert_bytes_by_block"]
    floor_index = max(0, n_cpu_moe)
    return sum(
        int(by_block[str(b)]) for b in geometry["placeable_blocks"] if b >= floor_index
    )


def mtp_head_bytes(geometry: dict[str, Any]) -> int:
    ""
    by_block = geometry["expert_bytes_by_block"]
    return sum(int(by_block[str(b)]) for b in geometry.get("nextn_blocks") or ())


def constant_from_probe(
    geometry: dict[str, Any], n_cpu_moe: int, vram_used_bytes: int
) -> int:
    ""
    return vram_used_bytes - experts_on_card(geometry, n_cpu_moe)


def floor(geometry: dict[str, Any], free_bytes: int, constant: int) -> int | None:
    ""
    n = len(geometry["placeable_blocks"])
    for n_cpu_moe in range(0, n + 1):
        if constant + experts_on_card(geometry, n_cpu_moe) <= free_bytes:
            return n_cpu_moe
    return None


def predict(geometry: dict[str, Any], n_cpu_moe: int, constant: int) -> int:
    ""
    return constant + experts_on_card(geometry, n_cpu_moe)


@dataclass(frozen=True)
class Placement:
    ""

    predicted_mib: float
    allowance_mib: float

    @property
    def required_mib(self) -> float:
        ""
        return self.predicted_mib + self.allowance_mib


def allowance_mib(geometry: dict[str, Any], *, n_ubatch: int = 512) -> float:
    ""
    readings = MEASURED_SCRATCH_MIB.get(str(geometry.get("arch")))
    if readings is None:
        return SCRATCH_AND_CONTEXT_MIB
    return readings.get(n_ubatch, SCRATCH_AND_CONTEXT_MIB)


def explain(
    geometry: dict[str, Any],
    *,
    n_cpu_moe: int,
    slots: int,
    ctx_per_slot: int,
    n_ubatch: int = 512,
    speculative: str = "none",
) -> Placement:
    ""
    kv = kv_bytes(geometry, ctx_per_slot * slots, n_seq_max=slots, n_ubatch=n_ubatch)
    rs = rs_bytes(geometry, n_seq_max=slots)
    predicted = (
        int(geometry["bytes_nonexpert"])
        + kv["total"]
        + rs["total"]
        + experts_on_card(geometry, n_cpu_moe)
        + (mtp_head_bytes(geometry) if speculative == "mtp" else 0)
    )
    return Placement(
        predicted_mib=predicted / (1 << 20),
        allowance_mib=allowance_mib(geometry, n_ubatch=n_ubatch),
    )
