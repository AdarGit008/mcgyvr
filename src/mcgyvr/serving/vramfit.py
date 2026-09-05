"""What a MoE checkpoint will hold on a card, and the lowest ``--n-cpu-moe`` that fits.

**Every term here is either read from the GGUF header or measured on the rig.
None is fitted, and none is a constant carried over from another model.** That
is not stylistic: the predecessor of this module carried ``CUDA_CONTEXT_MIB =
1024`` against a measured 85-147 MiB, ``EXPERT_SHARE = 0.92`` against a measured
0.8416, and a per-block expert cost taken as ``bytes_experts / n_layer`` that is
wrong for nine of ten checkpoints measured. Each was stable, plausible, and
written down once.

The split this module rests on:

``expert weight``
    Exact, per block, from the tensor table. Summed over the blocks actually on
    the card -- never averaged, because the distribution is bimodal wherever the
    quant mix is (Qwen3.6 IQ3_XXS is 262.0 MiB on 37 blocks and 300.0 on three).

``everything else``
    The NON-EXPERT model weights -- which are the largest part of it, 1080.83 of
    2126.00 MiB on KAT -- plus cache, recurrent state, compute scratch, the CUDA
    primary context, and whatever device memory the engine allocates without
    naming. Called ``C`` here. **Measured once, at any placement, because it
    does not move with ``--n-cpu-moe``**: verified at five placements of one
    checkpoint, where every term held to the last printed digit and the
    unnamed remainder held at 144.67 MiB
    net of idle (145.67 raw). That remainder is per-rig -- 144.67
    on srv2 against 97.69 on srv1, both net of the card's idle baseline -- but
    ``C`` itself is per (model, serve config) and subsumes it.

That invariance is the whole trick: one probe fixes ``C`` for every placement,
so the floor follows from arithmetic on the header with nothing left to guess.

The header-derived laws below (:func:`kv_bytes`, :func:`rs_bytes`) are NOT used
to compute the floor -- ``C`` already contains them, measured. They exist to
predict a cell's cost before anything is launched, and to cross-check a probe:
a probe whose ``C`` disagrees with the sum of the engine's own reported buffers
is a probe that measured something other than what it thinks.
"""

from __future__ import annotations

from typing import Any

#: Bytes per cache element by ``--cache-type-k/v``. ``q8_0`` is 34 bytes per
#: 32-element block, so 17/16 of a byte -- verified exactly: a 192.00 MiB f16
#: cache became 102.00 MiB, which is 192 x 17/32.
CACHE_ELEM_BYTES = {"f32": 4.0, "f16": 2.0, "bf16": 2.0, "q8_0": 34.0 / 32.0}

#: The two device terms no GGUF header can supply: the compute buffer and the
#: allocation the engine never names. THE one allowance in a floor derivation,
#: and it lives here because this is the module every caller of that derivation
#: already loads -- the door's placement script and the bench gate both read it
#: from here, so the two cannot come to different conclusions about one card.
#:
#: Measured 255-521 MiB at ``-ub 256`` across two rigs and four checkpoints
#: (deepseek 259.5, gpt-oss 255.1/302.1, Qwen3.6 302.7, nemotron 521.2), and
#: the compute half grows with ``-ub``: the same nemotron reads 517.06 at
#: ``-ub 1024``, for 652. 768 bounds every reading taken, with margin.
#:
#: **Deliberately generous, because it is only ever walked DOWN from.**
#: Over-stating it predicts a floor above the true one, which costs throughput
#: until the walk-down; under-stating it admits a cell that clears every gate
#: and then OOMs at load.
#: -> ``records/evidence/2026-09-05-context-decomposition/``
SCRATCH_AND_CONTEXT_MIB = 768

#: llama.cpp pads the sliding-window cache to a multiple of this. Measured at
#: 256 with flash-attention both on and off, so it is not an FA alignment.
SWA_PAD = 256


def _pad(value: int, to: int) -> int:
    return -(-value // to) * to


def context_per_sequence(n_ctx: int, n_seq_max: int) -> int:
    """What each slot actually gets, which is not ``n_ctx / n_seq_max``.

    llama.cpp pads the per-sequence context UP to a multiple of 256 and then
    rewrites the total to match, so ``-c`` is a request and not a setting. Its
    own warning says "rounding down", which is the opposite of what it does.
    Measured on a 28-layer dense model at ``--parallel 8``: ``-c 8000`` yields
    8192 and ``-c 8200`` yields **10240**, a 25% jump from a 0.1% change in the
    request. At ``--parallel 5``, ``-c 8192`` yields 8960.

    This matters here because ``MIN_CTX_PER_SLOT`` is 987 -- not a multiple of
    256 -- so a cell declaring ``ctx_per_slot 987 x parallel 8`` asks for 7896
    and is given 8192, and a predictor that divides instead of padding
    under-counts its cache by 3.6%.
    """
    if n_seq_max <= 0:
        raise ValueError("n_seq_max must be positive; llama.cpp defaults it to 4")
    # ceil, not truncate. The two agree except when `n_ctx` does not divide by
    # `n_seq_max` AND the quotient is already 256-aligned -- `-c 8193 -np 8`
    # yields 1280 on the rig and 1024 by truncation, a 20% under-count.
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
    """Cache bytes on the device, summed over the layers that actually cache.

    **Per layer, because no scalar summary survives this store.** ``gemma4``
    caches five layers at 1024 elements and slides twenty-five at 2048 -- two
    head counts and two key widths in one file. ``bailingmoe3`` absorbs V into
    a compressed KV and allocates no V cache at all. K and V are weighed
    separately for the same reason: ``deepseek2`` carries a 192-wide key
    against a 128-wide value, and treating them as equal overstates it by 20%.

    **Sliding-window checkpoints allocate two caches** over disjoint layer
    sets, sized independently -- the full one at the per-sequence context, the
    sliding one at ``PAD256(n_swa x seqs + n_ubatch)`` capped there. Which
    layers slide is read from ``sliding_window_pattern`` where declared: the
    split is 12/12 on gpt-oss, 13/36 on cohere2moe and 5/25 on gemma4, so
    assuming an alternating pattern is wrong for two of the three.

    The sliding cache is the only term here that grows with ``n_ubatch``, and
    the only one that shrinks with ``--parallel``.
    """
    rows = geometry["kv_layers"] if layers is None else layers

    # **Refuse an undeclared sliding-window split rather than assume one.** A
    # checkpoint that declares `attention.sliding_window` without the per-layer
    # `sliding_window_pattern` does not say WHICH layers slide, and the answer
    # is not derivable from the header. An alternating assumption stood here
    # and is wrong for two of the three split checkpoints measured (gemma4
    # slides 25 of 30, cohere2moe 36 of 49); it survived only because both of
    # those declare a pattern, leaving it exercised on the one file whose
    # sliding and full layers are the same width and where it therefore cannot
    # be caught. Sizing a cache from an invented split is the failure this
    # module exists to end -- the number would be confident, plausible and
    # unfalsifiable, and a floor derived from it puts a cell through the gate
    # that then OOMs at load.
    #
    # The split is observable, so this is a request for a measurement and not a
    # dead end: llama.cpp names the layer count of each cache it creates.
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

    # Unified: one cache shared by every sequence, sized against the whole
    # context and neither divided nor multiplied by the slot count.
    # Non-unified: a per-sequence cache, so per-sequence size times slots.
    if kv_unified:
        cells_full, seq_factor = n_ctx, 1
    else:
        cells_full, seq_factor = context_per_sequence(n_ctx, n_seq_max), n_seq_max

    window = geometry.get("sliding_window")
    if swa_full or not window:
        cells_swa = cells_full
    else:
        # Under a unified cache the window is claimed once for all sequences,
        # so `n_swa x seqs + n_ubatch` is already the TOTAL cell count. Capping
        # that against the per-sequence context and then multiplying by the
        # slots again overstated it by 5.3x.
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
    """Recurrent-state bytes on the device: the SSM state plus the conv state.

    ``S`` is the term everyone finds -- ``d_inner x d_state x 4 B`` per layer
    per sequence. ``R``, the convolution state, is the one that gets dropped:
    ``(d_conv - 1) x (d_inner + 2 x n_group x d_state) x 4 B``, worth 4.7% of
    the buffer on ``qwen35moe`` and 3.5% on ``nemotron_h_moe``.

    Charged per SEQUENCE rather than per token, so ``--parallel`` is the
    expensive axis for these architectures while ``-c`` is free. That is the
    exact reverse of ``deepseek2``, where the cache scales with context and
    slots cost nothing, so an intuition formed on one does not transfer.

    **Raises rather than returning zero when a recurrent model states no state
    parameters.** ``bailingmoe3`` describes its state under ``kda.*`` instead of
    ``ssm.*``; a guard that returns zero there silently loses 154.12 MiB and
    makes a missing header indistinguishable from a model that has no state.
    """
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
    """Expert bytes the card holds at ``--n-cpu-moe N``.

    **``N`` is a block INDEX, not a count of expert-bearing blocks.** llama.cpp
    emits tensor overrides matching ``blk.0`` through ``blk.(N-1)``, so a block
    whose index is below ``N`` goes to the CPU whether or not it carries
    experts, and one above it stays on the card. Taking the ``N``-th *placeable*
    block instead gives the same set only when expert blocks start at zero and
    run contiguously -- which fails on four of the eleven checkpoints measured,
    worst on ``nemotron_h_moe``, whose expert blocks are ``1,3,6,8,10,...,51``.

    What the positional reading cost, against the engine's own ``CUDA0 model
    buffer size``: at ``--n-cpu-moe 40`` nemotron holds 4110.75 MiB of experts
    and the positional sum said 0 -- a third of srv2's card. Its floor came out
    9 where the rig loads at 21 and refuses at 20, i.e. a cell that clears the
    gate and then OOMs at load, which is the single outcome the gate exists to
    prevent. On ``deepseek2``, whose block 0 is dense, ``--n-cpu-moe 1`` moves
    nothing at all while the positional sum booked a 297.00 MiB move.

    Clamps at zero, as the engine does: a negative ``N`` places everything.
    """
    by_block = geometry["expert_bytes_by_block"]
    floor_index = max(0, n_cpu_moe)
    return sum(
        int(by_block[str(b)]) for b in geometry["placeable_blocks"] if b >= floor_index
    )


def constant_from_probe(
    geometry: dict[str, Any], n_cpu_moe: int, vram_used_bytes: int
) -> int:
    """``C``: everything on the card that is not expert weight, from one launch.

    Subtracting the expert weight the placement implies from what the driver
    says the card holds. What remains is cache, recurrent state, compute
    scratch, the CUDA primary context and any device allocation the engine never
    prints -- as one lump, which is all a placement decision needs.

    **Pass ``vram_used_bytes`` net of the card's idle baseline.** ``memory.used``
    is card-wide; srv1 idles at 17 MiB and srv2 at 1 MiB, and letting that ride
    along puts a 16 MiB rig difference into a number that has nothing to do with
    either rig.
    """
    return vram_used_bytes - experts_on_card(geometry, n_cpu_moe)


def floor(geometry: dict[str, Any], free_bytes: int, constant: int) -> int | None:
    """The lowest ``--n-cpu-moe`` whose expert weight still fits beside ``C``.

    Walks placements from most-on-card to least and returns the first that fits,
    rather than dividing headroom by a per-block average: with a bimodal block
    distribution the two disagree, and the division is what put a predicted
    floor three steps above the measured one.

    ``None`` when even full offload does not fit. That means ``C`` alone
    exceeds the card: the non-expert weights, cache and scratch do not fit
    before a single expert block is placed. It is a statement about the CARD,
    not the host -- whether host RAM can hold the offloaded experts is a
    separate question this function never sees.
    """
    n = len(geometry["placeable_blocks"])
    for n_cpu_moe in range(0, n + 1):
        if constant + experts_on_card(geometry, n_cpu_moe) <= free_bytes:
            return n_cpu_moe
    return None


def predict(geometry: dict[str, Any], n_cpu_moe: int, constant: int) -> int:
    """Card bytes at a placement: the probe's constant plus that placement's experts."""
    return constant + experts_on_card(geometry, n_cpu_moe)
