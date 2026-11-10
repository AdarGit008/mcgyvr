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

What a card holds beside its tensors, how a cache's cells are counted and how
the parts add up are the per-card fit law in `mcgyvr.hubwire`, which the hub's
planner sizes with too; this module prices a scanned geometry's rows for it.

Every figure here is fitted to what the engine's allocator summary or
`nvidia-smi` printed, never to a share of the file size: expert costs come from
the scan's per-block totals, the sliding split from the checkpoint's declared
per-layer pattern, and a sliding window with no declared pattern is refused
rather than guessed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal, TypeGuard

from mcgyvr import hubwire
from mcgyvr.serving import ggufscan

#: The cache types llama.cpp accepts for `-ctk`/`-ctv`, by the names it reads
#: them by: `kv_cache_types` in llama.cpp's common/arg.cpp (F32, F16, BF16, Q8_0,
#: Q4_0, Q4_1, IQ4_NL, Q5_0, Q5_1). The scanner's type table also holds weight
#: types the engine refuses as a cache type, so the widths below are that table
#: filtered to these names.
LLAMACPP_CACHE_TYPES: tuple[str, ...] = (
    "f32",
    "f16",
    "bf16",
    "q8_0",
    "q4_0",
    "q4_1",
    "iq4_nl",
    "q5_0",
    "q5_1",
)

_GGML_TYPE_ID = {name.lower(): type_id for type_id, name in ggufscan.NAME.items()}

#: Bytes one cached element costs, by llama.cpp cache type: the scanner's block
#: bytes over its block elements (`ggufscan.T`), so f16 is 2 and q8_0, 34 bytes a
#: block of 32 elements (a half-precision scale each), 17/32 of an f16 cache.
CACHE_ELEM_BYTES = {
    name: ggufscan.T[_GGML_TYPE_ID[name]][1] / ggufscan.T[_GGML_TYPE_ID[name]][0]
    for name in LLAMACPP_CACHE_TYPES
}

#: The measured scratch readings, the backend they were read under and the cache
#: pad are the per-card fit law's (`mcgyvr.hubwire`), which the hub's planner
#: computes from too; named here for the sizer's callers.
MEASURED_SCRATCH_MIB = hubwire.MEASURED_SCRATCH_MIB
MEASURED_SCRATCH_BACKEND = hubwire.MEASURED_SCRATCH_BACKEND
SWA_PAD = hubwire.CACHE_PAD_CELLS
context_per_sequence = hubwire.context_per_sequence


def _count(value: object) -> TypeGuard[int | float]:
    """Whether a row's element count is a number (an int, or a float as a geometry
    read back from JSON may carry), never a bool."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def cache_bytes_per_token(
    rows: Iterable[Mapping[str, Any]],
    *,
    cache_type_k: str,
    cache_type_v: str,
    only: Literal["full", "sliding"] | None = None,
) -> float:
    """Bytes one cell of context costs over the caching layers `rows`, at
    `cache_type_k` and `cache_type_v`: each row's `k_elems` and `v_elems` priced
    at `CACHE_ELEM_BYTES` an element and summed.

    `only` picks the sliding treatment: None charges every row (the figure the
    shipped catalog and a rig's hello state, every layer a full-context layer),
    "full" only the rows that do not slide and "sliding" only those that do --
    the two sums `kv_bytes` multiplies by its own cell counts, the window being
    cells and not tokens. A cache type with no width, a row whose element
    counts are not numbers, and a row whose `is_swa` is unstated when `only`
    asks which side it falls on each raise `ValueError`."""
    for cache_type in (cache_type_k, cache_type_v):
        if cache_type not in CACHE_ELEM_BYTES:
            raise ValueError(
                f"cache type {cache_type!r} has no width; llama.cpp takes "
                f"{', '.join(LLAMACPP_CACHE_TYPES)}"
            )
    b_k = CACHE_ELEM_BYTES[cache_type_k]
    b_v = CACHE_ELEM_BYTES[cache_type_v]
    total = 0.0
    for row in rows:
        k, v = row.get("k_elems"), row.get("v_elems")
        if not _count(k) or not _count(v):
            raise ValueError(f"layer {row.get('layer')} states no k/v element counts")
        if only is not None:
            swa = row.get("is_swa")
            if swa is None:
                raise ValueError(f"layer {row.get('layer')} does not say if it slides")
            if bool(swa) != (only == "sliding"):
                continue
        total += float(k) * b_k + float(v) * b_v
    return total


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

    full, swa = (
        cache_bytes_per_token(
            rows, cache_type_k=cache_type_k, cache_type_v=cache_type_v, only=side
        )
        for side in ("full", "sliding")
    )

    return hubwire.cache_bytes(
        full,
        n_ctx,
        n_seq_max=n_seq_max,
        sliding_bytes_per_token=swa,
        sliding_window=geometry.get("sliding_window"),
        n_ubatch=n_ubatch,
        swa_full=swa_full,
        kv_unified=kv_unified,
    )


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


def widest_layer_f16_bytes(geometry: Mapping[str, Any]) -> int:
    """The bytes one cell costs in an f16 copy of the widest caching layer's K
    and V: what the compute buffer's context-growing law charges per cell
    (`hubwire.compute_buffer_bytes`). 0 when no row states its widths."""
    widths = [0.0]
    for row in geometry.get("kv_layers") or ():
        try:
            widths.append(
                cache_bytes_per_token([row], cache_type_k="f16", cache_type_v="f16")
            )
        except ValueError:
            continue
    return int(max(widths))


def allowance(
    geometry: Mapping[str, Any],
    *,
    n_ctx: int,
    n_seq_max: int = 1,
    n_ubatch: int = 512,
    backend: str = MEASURED_SCRATCH_BACKEND,
    unified: bool = False,
) -> hubwire.Allowance:
    """What one card holding (part of) `geometry` is charged beside its weights,
    caches and state at `-c n_ctx` over `n_seq_max` sequences: the measured
    reading for its arch at `n_ubatch` on `backend`, else the context-growing
    law (`hubwire.card_allowance`). Charged the same on one card and on each
    card of a split."""
    return hubwire.card_allowance(
        str(geometry["arch"]) if geometry.get("arch") else None,
        cells=hubwire.cache_cells(n_ctx, n_seq_max),
        n_ubatch=n_ubatch,
        backend=backend,
        unified=unified,
        layer_f16_bytes_per_token=widest_layer_f16_bytes(geometry),
    )
