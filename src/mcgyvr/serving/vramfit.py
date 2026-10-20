"""Per-card VRAM sizing for llama.cpp, from a scanned GGUF geometry.

The card holds two kinds of bytes: a constant, and the expert blocks that
`--n-cpu-moe` leaves on it. The constant is the non-expert weights, the KV and
sliding-window caches, the recurrent state, and an allowance for what the engine
allocates beside them; `experts_on_card` prices the rest block by block.

That split is what a placement search needs, because the expert cost follows a
block index while the constant does not follow the placement. `floor` finds
the fewest host blocks that make a card fit beside the constant, and `predict`
says what the resulting placement holds.

The constant steps once an expert block sits on the host and is flat after
that: llama.cpp's op offload copies a host-stored expert tensor into the device
compute buffer for a large batch, which roughly doubles that buffer relative to
a placement with every expert on the card. A probe therefore describes the
placements on its own side of that step, and one taken with every expert on the
card under-states every placement that offloads.

Every figure here is fitted to what the engine's allocator summary or
`nvidia-smi` printed, never to a share of the file size: expert costs come from
the scan's per-block totals, the sliding split from the checkpoint's declared
per-layer pattern, and a sliding window with no declared pattern is refused
rather than guessed.
"""

from __future__ import annotations

from typing import Any

#: Bytes one cached element costs, by llama.cpp cache type. f32/f16/bf16 are
#: their widths; q8_0 spends 34 bytes on a block of 32 elements (a
#: half-precision scale and offset each), so it is 17/32 of an f16 cache.
CACHE_ELEM_BYTES = {"f32": 4.0, "f16": 2.0, "bf16": 2.0, "q8_0": 34.0 / 32.0}

#: The allowance, in MiB, that `allowance_mib` returns when it has no reading
#: for the architecture it was asked about, or none for the ubatch: what the
#: engine and the driver hold beyond the weights and the caches -- the CUDA
#: context, the compute buffers, and the allocations that move with a batch.
#: The scan cannot state this figure; the engine's own allocator decides it,
#: which is why the architectures in `MEASURED_SCRATCH_MIB` were read off a
#: load on a rig. An unmeasured model is gated on this number rather than on
#: nothing, so its prediction still leaves the card room for what llama.cpp
#: will allocate next to the tensors. It is a default, not a ceiling: no load
#: here was measured against it. The serving sizer adds it to the card
#: constant, so a placement compared with free VRAM is compared against the
#: tensors, the caches they sit in, and this headroom together rather than the
#: tensors alone. A caller that wants the figure for one architecture at one
#: batch asks `allowance_mib`; this constant is only what it returns on a miss,
#: and 768 MiB is that answer, not a measurement of any particular model.
SCRATCH_AND_CONTEXT_MIB = 768

#: The scratch allowance measured on a rig, in MiB, filed under the ubatch it
#: was read at: what that load actually held beyond the weights, the KV cache
#: and the recurrent state that `kv_bytes` and `rs_bytes` predict. Each figure
#: is the gap left by the engine's allocator summary (`--verbose`, whose second
#: loader pass is the real one) cross-checked against `nvidia-smi`, and that
#: gap carries the CUDA context, the compute buffers, and whatever else the
#: engine allocates beside the tensors. It differs by architecture -- the
#: kernels and per-layer buffers are the model's own -- and it grows with the
#: ubatch, which is why a reading is filed under the batch it was taken at as
#: well as under the arch. `allowance_mib` reads this table and nothing else
#: derives from it: a hit returns the measured figure, a miss on the
#: architecture or on the ubatch returns `SCRATCH_AND_CONTEXT_MIB`. Neither the
#: entries nor the gaps between them are averaged or interpolated, because a
#: value computed between two readings would be a guess written down as a
#: measurement; a new placement batch means a new reading. The arch name is the
#: one the scan writes, so `qwen35moe` and `gptoss` are spellings of an
#: architecture family and not of a checkpoint: two quantizations of one arch
#: share a row, since the quant changes the tensors and not the buffers the
#: engine allocates around them. A row says nothing about slots or context:
#: those are in the cache figures, not in the gap. A reading missing for an
#: arch, or for the batch a placement runs at, is a reading to take, not a
#: value to carry over from the neighbouring entry -- keying by ubatch says
#: that the buffer sizes it describes are not interchangeable between
#: batches.
MEASURED_SCRATCH_MIB = {
    "deepseek2": {256: 259.5},
    "gptoss": {256: 302.1},
    "qwen35moe": {256: 302.7, 512: 316.57},
    "nemotron_h_moe": {256: 521.2},
    #: qwen3next's reading is at ubatch 512 (829.0 MiB), not 256 like the rest, so
    #: it is filed under the batch the load actually ran with.
    "qwen3next": {512: 829.0},
}

#: Cell granule llama.cpp pads the sliding-window cache to: the engine rounds
#: its SWA cell count up to a multiple of 256, so a partial chunk costs a whole.
SWA_PAD = 256


def _pad(value: int, to: int) -> int:
    return -(-value // to) * to


def context_per_sequence(n_ctx: int, n_seq_max: int) -> int:
    """Cells per sequence: `n_ctx` divided by `n_seq_max`, rounded up to 256."""
    if n_seq_max <= 0:
        raise ValueError("n_seq_max must be positive")
    # `-c` is the total across sequences, not one sequence's context: llama.cpp
    # divides it, rounds each sequence up to 256 cells, and rewrites the total to
    # slots x per-sequence cells, so the allocation can exceed the request.
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
    """Bytes the KV caches take for `n_ctx` of total context over `n_seq_max` sequences.

    `rows` is `geometry["kv_layers"]` unless a caller passes `layers`, which lets a
    shard size only the blocks it holds. Each row states its `k_elems`, its
    `v_elems`, and whether it slides; those widths are priced at `cache_type_k` and
    `cache_type_v` per element and summed into a full-attention total and a
    sliding-window total.

    Cells come from `context_per_sequence` per sequence, or from `n_ctx` once when
    `kv_unified`, since the total is divided rather than multiplied; the
    per-sequence widths are then summed across the sequences. The sliding rows are
    charged the window plus `n_ubatch` tokens in flight, padded to `SWA_PAD` and
    capped at the per-sequence cell count, since that cache only ever holds a window
    and a batch -- while `swa_full`, or a geometry that declares no `sliding_window`,
    charges them the full context like any other layer.

    Returns `total`, `non_swa` and `swa` in bytes, `cells_swa` as the sliding cell
    count left after the cap (0 when no row slides), and `n_ctx_seq` as the
    per-sequence cell count every cell total is capped against.

    A sliding-capable geometry whose rows leave `is_swa` unstated raises
    `ValueError`: the split decides the bytes, and it is read from the checkpoint's
    pattern or from the engine's own cache lines, never assumed."""
    rows = geometry["kv_layers"] if layers is None else layers

    # Every row must state whether it slides. A checkpoint can declare
    # `attention.sliding_window` and no `sliding_window_pattern`, and then the
    # file says that some layers slide without saying which; `is_swa` is None and
    # the cache cannot be sized from the scan. The two caches are not sized alike
    # -- the full one per sequence over the whole context, the sliding one over
    # the window plus a batch -- so the bytes depend on which layers fall on which
    # side. An alternating guess is right only for a checkpoint whose layers are
    # all one width, where a wrong assignment cannot show up in the sum, and wrong
    # for the mixed ones. Refusing here is the point: llama.cpp prints its own
    # `llama_kv_cache_iswa: creating non-SWA/SWA KV cache` cell counts at load,
    # and the message names that measurement and `layers=`, so a caller can read
    # the split and pass the rows back instead of accepting a number built on a
    # guess. That keeps the bytes a measurement wherever the split is genuinely
    # unknown, and costs only a re-read of the load log where it is not: the
    # engine states the split it chose, so the caller can hand the rows back.
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

    # `-c` is a total, not a slot's context. Unified KV shares one cache across
    # the sequences, so `n_ctx` cells are the whole allocation and no per-sequence
    # multiplier applies; otherwise each sequence is charged its own padded cells.
    if kv_unified:
        cells_full, seq_factor = n_ctx, 1
    else:
        cells_full, seq_factor = context_per_sequence(n_ctx, n_seq_max), n_seq_max

    window = geometry.get("sliding_window")
    if swa_full or not window:
        cells_swa = cells_full
    else:
        # The sliding cache need hold only the window, plus one batch of tokens in
        # flight. Unified, the window is claimed once for every sequence together, so
        # the count is against the total; otherwise it is claimed per sequence and
        # multiplied by `seq_factor` below, padded to the engine's granule, capped.
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
    """Bytes the recurrent state takes for `n_seq_max` sequences, or zeros if dense.

    `s` is the state proper: `ssm_inner_size` x `ssm_state_size` per recurrent
    block per sequence, at four bytes an element. `r` is the convolution term the
    kernel keeps beside it: `conv_kernel - 1` taps of the inner size plus two
    group-scaled state vectors, per block per sequence, likewise at four bytes.

    Both scale with the sequence count. `recurrent_layers_on_device` lets a shard
    charge only the recurrent blocks it holds, defaulting to all of them.

    A geometry that claims recurrent blocks but states no state size raises
    `ValueError`: returning zero there would look exactly like a dense model and
    would hide an allocation the launch is about to make."""
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
    """Expert bytes the card keeps at `--n-cpu-moe n_cpu_moe`.

    Blocks are selected by their block index, not by their position in the
    placeable list: every placeable block whose index is at least `n_cpu_moe`
    keeps its experts on the device. That makes a checkpoint whose expert blocks
    are non-contiguous or do not start at 0 come out right, and makes the first
    offload step a no-op when block 0 carries no experts. Multi-token-prediction
    blocks are not in `placeable_blocks` and are not counted here."""
    by_block = geometry["expert_bytes_by_block"]
    floor_index = max(0, n_cpu_moe)
    return sum(
        int(by_block[str(b)]) for b in geometry["placeable_blocks"] if b >= floor_index
    )


def mtp_head_bytes(geometry: dict[str, Any]) -> int:
    """Expert bytes carried by the multi-token-prediction head blocks.

    `--n-cpu-moe` never moves these, because they are not in `placeable_blocks`, so
    their expert tensors are charged to the card whatever the placement."""
    by_block = geometry["expert_bytes_by_block"]
    return sum(int(by_block[str(b)]) for b in geometry.get("nextn_blocks") or ())


def floor(geometry: dict[str, Any], free_bytes: int, constant: int) -> int | None:
    """The fewest host blocks that make the card fit, or `None` if none does.

    Walks `n_cpu_moe` from 0 upward and returns the first value whose `constant`
    plus `experts_on_card` fits `free_bytes`, so the answer leaves the most experts
    on the device that still fit. The walk stops at `len(placeable_blocks)`, and
    `None` says no count in that range fits: the card is too small at every
    placement searched, and there is nothing to return."""
    n = len(geometry["placeable_blocks"])
    for n_cpu_moe in range(0, n + 1):
        if constant + experts_on_card(geometry, n_cpu_moe) <= free_bytes:
            return n_cpu_moe
    return None


def predict(geometry: dict[str, Any], n_cpu_moe: int, constant: int) -> int:
    """Predicted card bytes at `--n-cpu-moe n_cpu_moe`.

    `constant` plus the expert blocks that placement leaves on the device."""
    return constant + experts_on_card(geometry, n_cpu_moe)


def allowance_mib(geometry: dict[str, Any], *, n_ubatch: int = 512) -> float:
    """The scratch allowance in MiB for `geometry`'s arch at `n_ubatch`.

    Returns the measured reading from `MEASURED_SCRATCH_MIB` when that architecture
    has one for that ubatch, and `SCRATCH_AND_CONTEXT_MIB` when it has none -- for
    the arch or for the batch. A miss falls back rather than interpolating, so the
    answer is either a reading or a stated default."""
    readings = MEASURED_SCRATCH_MIB.get(str(geometry.get("arch")))
    if readings is None:
        return SCRATCH_AND_CONTEXT_MIB
    return readings.get(n_ubatch, SCRATCH_AND_CONTEXT_MIB)
