"""``vramfit`` against what the rigs actually did, on 2026-09-04.

**Every expected value here was printed by llama.cpp or read from
``nvidia-smi``, never computed by the code under test.** The buffer figures come
from the engine's own allocator summary (``--verbose``; the loader runs twice
and only the second pass is real), and the placement outcomes from launches that
loaded or refused on the rig.

This suite exists because the module it tests replaced four constants that were
each stable, plausible, and wrong -- ``CUDA_CONTEXT_MIB = 1024`` against a
measured 85-147 MiB, and a per-block expert cost of ``bytes_experts / n_layer``
that is wrong for nine of ten checkpoints measured. A law with no
measurement behind it is how that happened, so each law below is pinned to the
rig reading it claims to describe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving import vramfit

MIB = 1024**2
GEOMETRY = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text()
)


def g(name: str) -> dict[str, Any]:
    geometry: dict[str, Any] = GEOMETRY[name]
    return geometry


def gpt_oss_measured_rows(n_swa: int = 12) -> list[dict[str, Any]]:
    """gpt-oss's cache split as the ENGINE reported it, because the header will not.

    gpt-oss declares ``attention.sliding_window = 128`` and no per-layer
    ``sliding_window_pattern``, so nothing in the file says which layers slide
    and :func:`vramfit.kv_bytes` refuses the geometry outright. It is refused
    rather than guessed because an alternating assumption is wrong for two of
    the three split checkpoints in this store (gemma4 slides 25 of 30,
    cohere2moe 36 of 49) and both of those escape it only by declaring a
    pattern -- leaving the assumption exercised on this one file alone.

    The engine names the split. 2026-09-05, srv2, ``-c 16384 -np 8``::

        llama_kv_cache_iswa: creating non-SWA KV cache, size = 2048 cells
        llama_kv_cache: size = 384.00 MiB ( 2048 cells, 12 layers, 8/8 seqs)
        llama_kv_cache_iswa: creating     SWA KV cache, size =  512 cells
        llama_kv_cache: size =  96.00 MiB (  512 cells, 12 layers, 8/8 seqs)

    Twelve of each. WHICH twelve is stated by neither the header nor the log,
    and does not need to be: every gpt-oss layer is the same width, so the
    bytes follow from the count alone. The assert below is what makes that
    safe -- if a future gpt-oss conversion stops being uniform, a count stops
    being enough and this helper fails instead of quietly inventing an
    assignment again.

    -> ``records/evidence/2026-09-05-context-decomposition/srv2-gpt-oss-20b-MXFP4/``
    """
    rows = [dict(r) for r in g("gpt-oss-20b-MXFP4.gguf")["kv_layers"]]
    widths = {(r["k_elems"], r["v_elems"]) for r in rows}
    assert len(widths) == 1, (
        "gpt-oss's layers are no longer uniform in width, so the measured "
        f"COUNT no longer determines the bytes: {widths}"
    )
    for i, row in enumerate(rows):
        row["is_swa"] = i < n_swa
    return rows


# --- the header-derived laws --------------------------------------------------


@pytest.mark.parametrize(
    "model,n_ctx,expected_mib,why",
    [
        # `full_attention_interval = 4`: 10 of 40 layers cache. Reading
        # block_count instead over-predicts by 4x.
        ("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf", 8192, 160.00, "qwen35moe, 10 of 40 cache"),
        ("Qwen3.6-35B-A3B-UD-IQ2_M.gguf", 8192, 160.00, "same geometry, other quant"),
        # Every layer caches, and K is WIDER than V (192 vs 128 head length).
        # Assuming they match understates this by 20%.
        ("deepseek-coder-v2-16b.gguf", 8192, 2160.00, "deepseek2, K 3072 + V 2048"),
        # `head_count_kv` is a 52-entry ARRAY with 6 non-zero. No interval can
        # express that, and this checkpoint's interval is null.
        (
            "nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf",
            8192,
            48.00,
            "nemotron_h_moe, 6 caching layers by array",
        ),
        # Exactly linear in the total context.
        ("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf", 16384, 320.00, "twice the context"),
    ],
)
def test_kv_matches_the_engines_own_figure(
    model: str, n_ctx: int, expected_mib: float, why: str
) -> None:
    got = vramfit.kv_bytes(g(model), n_ctx, n_seq_max=8)["total"] / MIB
    assert got == pytest.approx(expected_mib, abs=0.01), why


def test_parallel_does_not_move_the_non_swa_cache() -> None:
    """``-c`` is the TOTAL; slots divide a fixed pool rather than each claiming one.

    Measured on gpt-oss at ``-c 8192``: 1024 cells x 8 seqs, 2048 x 4, and
    8192 x 1 unified all allocate the same 192.00 MiB. A gate that multiplies
    the cache by ``--parallel`` refuses cells that fit.
    """
    geom = g("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf")
    sizes = {vramfit.kv_bytes(geom, 8192, n_seq_max=n)["total"] for n in (1, 4, 8)}
    assert len(sizes) == 1
    assert sizes.pop() / MIB == pytest.approx(160.00, abs=0.01)


@pytest.mark.parametrize(
    "n_ubatch,swa_cells,swa_mib",
    # PAD256(n_swa x seqs + n_ubatch), capped at n_ctx_seq = 1024.
    # 128x8+128 = 1152 -> 1280 -> capped 1024;  +256 = 1280 -> capped;
    # measured cell counts: 256, 512, 768, 1024.
    [(128, 256, 48.00), (256, 512, 96.00), (512, 768, 144.00), (1024, 1024, 192.00)],
)
def test_the_sliding_window_cache_grows_with_ubatch(
    n_ubatch: int, swa_cells: int, swa_mib: float
) -> None:
    """The one cache that scales with batch size, and the reason gpt-oss looked odd.

    A reader that keeps only the last ``CUDA0 KV buffer size`` line sees this
    half and misses the fixed 192.00 MiB non-SWA half entirely -- which is
    exactly how gpt-oss acquired a spurious 190 MiB "model-specific anomaly".
    """
    out = vramfit.kv_bytes(
        g("gpt-oss-20b-MXFP4.gguf"),
        8192,
        n_seq_max=8,
        n_ubatch=n_ubatch,
        layers=gpt_oss_measured_rows(),
    )
    assert out["swa"] / MIB == pytest.approx(swa_mib, abs=0.01)
    assert out["non_swa"] / MIB == pytest.approx(192.00, abs=0.01)


@pytest.mark.parametrize(
    "model,n_seq,s_mib,r_mib",
    [
        # R is 4.7% of the buffer here and 3.5% on nemotron. A gate modelling
        # only S understates every hybrid.
        ("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf", 8, 480.00, 22.50),
        ("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf", 4, 240.00, 11.25),
        ("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf", 1, 60.00, 2.81),
        ("nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf", 8, 368.00, 12.94),
    ],
)
def test_recurrent_state_includes_the_conv_term(
    model: str, n_seq: int, s_mib: float, r_mib: float
) -> None:
    out = vramfit.rs_bytes(g(model), n_seq_max=n_seq)
    assert out["s"] / MIB == pytest.approx(s_mib, abs=0.01)
    assert out["r"] / MIB == pytest.approx(r_mib, abs=0.02)


def test_cache_dtype_scales_exactly() -> None:
    """``q8_0`` is 34 bytes per 32 elements: measured 192.00 -> 102.00 MiB."""
    geom = g("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf")
    f16 = vramfit.kv_bytes(geom, 8192, n_seq_max=8)["total"]
    q8 = vramfit.kv_bytes(
        geom, 8192, n_seq_max=8, cache_type_k="q8_0", cache_type_v="q8_0"
    )["total"]
    assert q8 / f16 == pytest.approx(17 / 32, rel=1e-6)


# --- placement ----------------------------------------------------------------


def test_per_block_expert_bytes_are_bimodal_so_the_mean_is_not_a_block() -> None:
    """The error that put a predicted floor three steps above the measured one.

    ``bytes_experts / n_layer`` matches no block in this file: it is 262.0 MiB
    on 37 blocks and 300.0 on three, and the mean lands at 264.85.
    """
    geom = g("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf")
    sizes = sorted({round(v / MIB, 1) for v in geom["expert_bytes_by_block"].values()})
    assert sizes == [262.0, 300.0]
    mean = geom["bytes_experts"] / geom["n_layer"] / MIB
    assert round(mean, 2) == 264.85
    assert mean not in sizes


def test_a_multi_token_prediction_block_is_never_placed() -> None:
    """It carries expert tensors and ``--n-cpu-moe`` does not move it.

    Proof from the rig: at ``ncmoe 8`` the card held 8896.00 MiB of experts,
    which is 32 x 278.0 exactly -- blocks 8..39, with block 40 absent.
    """
    geom = g("KAT-Coder-V2.5-Dev_Q2_K-AllGPU.gguf")
    assert geom["nextn_blocks"] == [40]
    assert geom["n_placeable"] == 40
    assert geom["expert_layers"] == 41
    assert vramfit.experts_on_card(geom, 8) / MIB == pytest.approx(8896.00, abs=0.5)


def test_nemotron_declares_more_blocks_than_carry_experts() -> None:
    """52 blocks, 23 with experts: dividing by ``n_layer`` is wrong by 2.26x."""
    geom = g("nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf")
    assert geom["n_layer"] == 52
    assert geom["n_placeable"] == 23


@pytest.mark.parametrize(
    "model,probe_ncmoe,probe_used_mib,idle_mib,free_mib,expect_floor,ran,ran_used_mib,refused",
    [
        # srv1, L3 image, c=8192 np=8 ub=512. Probe at ncmoe 34 read 4276 MiB.
        # The rig then loaded at 29 (4/4, used 5584) and refused at 28 (6/6).
        ("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf", 34, 4276, 17, 5727, 29, 29, 5584, 28),
        # srv2, stock. Probe at max offload read 2127 MiB. The rig walked down
        # to 5 (used 11857) and refused at 4. The predecessor said 8.
        ("KAT-Coder-V2.5-Dev_Q2_K-AllGPU.gguf", 41, 2127, 1, 11911, 5, 5, 11857, 4),
    ],
)
def test_floor_from_one_probe_matches_the_rig(
    model: str,
    probe_ncmoe: int,
    probe_used_mib: int,
    idle_mib: int,
    free_mib: int,
    expect_floor: int,
    ran: int,
    ran_used_mib: int,
    refused: int,
) -> None:
    geom = g(model)
    c = vramfit.constant_from_probe(
        geom, probe_ncmoe, (probe_used_mib - idle_mib) * MIB
    )
    got = vramfit.floor(geom, free_mib * MIB, c)
    assert got == expect_floor
    # Not `predict(floor) <= free < predict(floor-1)`: that follows from the
    # definition of `floor` and would pass against any C at all. Check the
    # predicted card occupancy against what nvidia-smi actually read at that
    # placement, which is a number `floor` never saw.
    # abs=3.0, not 1.0. `nvidia-smi` reports whole MiB, and the probe is
    # sampled once after the load settles rather than at the load's peak: an
    # independent re-read of the Qwen3.6 probe gave 4274 where this fixture
    # records 4276. Both errors land in `C` and then in every prediction made
    # from it, so the tolerance has to cover the reading, not just the
    # arithmetic. Sampling at ~100 ms through the load and keeping the maximum
    # would remove it; that is a change to how the probe is taken.
    assert vramfit.predict(geom, ran, c) / MIB == pytest.approx(
        ran_used_mib - idle_mib, abs=3.0
    )


def test_the_constant_does_not_move_with_placement() -> None:
    """Measured at five placements of one checkpoint: 145.67 MiB every time.

    This invariance is what makes a single probe sufficient. It was briefly
    believed false -- an artifact of dividing expert bytes by ``n_layer`` and
    counting a block the knob never places.
    """
    geom = g("KAT-Coder-V2.5-Dev_Q2_K-AllGPU.gguf")
    used = {41: 2127, 8: 11023, 7: 11301, 6: 11579, 5: 11857}
    constants = {
        n: vramfit.constant_from_probe(geom, n, (u - 1) * MIB) / MIB
        for n, u in used.items()
    }
    spread = max(constants.values()) - min(constants.values())
    assert spread < 1.0, constants


def test_a_model_too_big_for_the_host_has_no_floor() -> None:
    """``None``, not a placement -- no offload rescues it."""
    geom = g("Qwen3-Next-80B-A3B-Instruct-Q3_K_M.gguf")
    assert vramfit.floor(geom, 1 * MIB, 100 * MIB) is None


# --- regressions from the round-2 review ---------------------------------------


@pytest.mark.parametrize(
    "model,n_ctx,expected_mib,why",
    [
        # Two head counts and two key widths in one file: 5 full layers at
        # head_kv 2 x 512, 25 sliding at head_kv 8 x key_length_swa 256.
        # `max(head_count_kv)` with a single key_length predicted 3840.00.
        ("gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf", 8192, 1760.00, "gemma4 5/25 split"),
        # 13 full and 36 sliding on a 1-in-4 pattern; an assumed 1:1 split
        # gives the right total only while both caches sit at the cap.
        ("North-Mini-Code-1.0-IQ2_M.gguf", 8192, 784.00, "cohere2moe at the cap"),
        # Same model with the cap unbound -- where the split stops hiding.
        # The 1:1 assumption predicted 4872.00 here.
        ("North-Mini-Code-1.0-IQ2_M.gguf", 65536, 4256.00, "cohere2moe, cap free"),
        # MLA absorbs V: the engine prints `V (f16): 0.00 MiB`. Counting a V
        # cache predicted 66.00.
        ("Ling-3.0-tiny-Q4_K_M.gguf", 8192, 54.00, "bailingmoe3 caches no V"),
    ],
)
def test_kv_for_the_layouts_that_broke_a_scalar_summary(
    model: str, n_ctx: int, expected_mib: float, why: str
) -> None:
    got = vramfit.kv_bytes(g(model), n_ctx, n_seq_max=8, n_ubatch=512)["total"] / MIB
    assert got == pytest.approx(expected_mib, abs=0.01), why


@pytest.mark.parametrize(
    "n_ctx,n_seq_max,engine_n_ctx",
    # Measured on srv1, 28-layer dense model. `-c` is a request: llama.cpp pads
    # the per-sequence context up to 256 and rewrites the total to match, so a
    # 0.1% change in the request can move the allocation by 25%.
    [
        (8192, 8, 8192),
        (8000, 8, 8192),
        (8200, 8, 10240),
        (9000, 8, 10240),
        (8192, 5, 8960),
    ],
)
def test_context_is_padded_up_not_divided(
    n_ctx: int, n_seq_max: int, engine_n_ctx: int
) -> None:
    assert vramfit.context_per_sequence(n_ctx, n_seq_max) * n_seq_max == engine_n_ctx


def test_a_recurrent_model_with_no_state_keys_raises() -> None:
    """Silence here loses 154.12 MiB and looks exactly like a non-recurrent model.

    ``bailingmoe3`` states its state under ``kda.*`` rather than ``ssm.*``. The
    scanner translates it; if it ever stops, this must fail loudly rather than
    return zero.
    """
    geom = dict(g("Ling-3.0-tiny-Q4_K_M.gguf"))
    assert geom["n_recurrent"] == 18
    assert vramfit.rs_bytes(geom, n_seq_max=8)["s"] / MIB == pytest.approx(
        144.00, abs=0.01
    )
    geom["ssm_inner_size"] = None
    with pytest.raises(ValueError, match="recurrent blocks"):
        vramfit.rs_bytes(geom, n_seq_max=8)


def test_sliding_layer_split_comes_from_the_declared_pattern() -> None:
    """13/36 and 5/25 -- an alternating assumption is wrong for both."""
    splits = {}
    for name in (
        "North-Mini-Code-1.0-IQ2_M.gguf",
        "gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf",
    ):
        rows = g(name)["kv_layers"]
        assert all(r["is_swa"] is not None for r in rows)
        swa = sum(1 for r in rows if r["is_swa"])
        splits[name] = (len(rows) - swa, swa)
    assert splits["North-Mini-Code-1.0-IQ2_M.gguf"] == (13, 36)
    assert splits["gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf"] == (5, 25)


@pytest.mark.parametrize("model", ["gpt-oss-20b-MXFP4.gguf", "4b-Q4_K_M.gguf"])
def test_an_undeclared_sliding_split_is_refused_not_guessed(model: str) -> None:
    """The last fitted constant, removed: ``l % 2 == 0`` used to answer here.

    Both of these declare a sliding window and no pattern. The assumption they
    used to receive was right for them and wrong as a rule -- and it was right
    for them only because their layers are uniform in width, which is the one
    condition under which a wrong assignment cannot show up in the bytes. A
    checkpoint that is undeclared, not 1:1 AND not uniform would have been
    sized confidently and wrongly, with nothing in the output marking the
    guess. Refusing turns that into a request for the measurement.
    """
    geom = g(model)
    assert geom["sliding_window"]
    assert geom["swa_pattern_from"] is None
    with pytest.raises(ValueError, match="no per-layer sliding_window_pattern"):
        vramfit.kv_bytes(geom, 8192, n_seq_max=8)


@pytest.mark.parametrize(
    "n_ctx,total_mib,non_swa_mib,swa_mib",
    # Measured 2026-09-05 on srv2, `-np 8 -ub 256`, summing BOTH device caches
    # -- the figure a `tail -1` reader never saw. Three loads per context, all
    # byte-identical, and srv1 read the same buffers.
    [
        (2048, 96.00, 48.00, 48.00),
        (4096, 192.00, 96.00, 96.00),
        (8192, 288.00, 192.00, 96.00),
        (16384, 480.00, 384.00, 96.00),
    ],
)
def test_both_swa_caches_against_the_engines_own_totals(
    n_ctx: int, total_mib: float, non_swa_mib: float, swa_mib: float
) -> None:
    """The SWA cache stops growing; the full one does not. Both are on the card.

    At ``-c 16384`` the non-SWA cache holds 2048 cells and the SWA cache 512 --
    the window has bound and the second cache is flat from ``-c 8192`` on. A
    reader that kept one line saw 96.00 MiB at every context and charged the
    other 384.00 to the CUDA context, which then appeared to grow with
    ``-c`` and made the constant look context-dependent when it is not.
    """
    out = vramfit.kv_bytes(
        g("gpt-oss-20b-MXFP4.gguf"),
        n_ctx,
        n_seq_max=8,
        n_ubatch=256,
        layers=gpt_oss_measured_rows(),
    )
    assert out["non_swa"] / MIB == pytest.approx(non_swa_mib, abs=0.01)
    assert out["swa"] / MIB == pytest.approx(swa_mib, abs=0.01)
    assert out["total"] / MIB == pytest.approx(total_mib, abs=0.01)


def test_a_dense_model_has_no_experts_to_place() -> None:
    geom: dict[str, Any] = {"expert_bytes_by_block": {}, "placeable_blocks": []}
    assert vramfit.experts_on_card(geom, 0) == 0
    assert vramfit.floor(geom, 10 * MIB, 5 * MIB) == 0
    assert vramfit.floor(geom, 1 * MIB, 5 * MIB) is None


# --- regressions from the round-3 review ---------------------------------------


@pytest.mark.parametrize(
    "n_cpu_moe,expected_mib,why",
    [
        # nemotron's expert blocks are 1,3,6,8,...,51 -- neither starting at 0
        # nor contiguous. Slicing the placeable LIST at position N instead of
        # selecting blocks with index >= N said 0 MiB here; the engine's own
        # model buffer moved by 4110.76.
        (40, 4110.75, "positional slice said 0"),
        (21, 9591.75, "positional slice said 1370.25"),
        (52, 0.0, "max offload: every expert block index is below 52"),
    ],
)
def test_experts_are_selected_by_block_index_not_list_position(
    n_cpu_moe: int, expected_mib: float, why: str
) -> None:
    geom = g("nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf")
    got = vramfit.experts_on_card(geom, n_cpu_moe) / MIB
    assert got == pytest.approx(expected_mib, abs=0.01), why


def test_a_dense_leading_block_means_the_first_step_moves_nothing() -> None:
    """``deepseek2`` block 0 carries no experts, so ``--n-cpu-moe 1`` is a no-op.

    Measured: ``CUDA0 model buffer size`` is 8376.27 MiB at both 0 and 1, and
    drops by exactly one block at 2. The positional slice booked a 297.00 MiB
    move at the first step.
    """
    geom = g("deepseek-coder-v2-16b.gguf")
    at = [vramfit.experts_on_card(geom, n) / MIB for n in (0, 1, 2)]
    assert at[0] == at[1] == pytest.approx(7722.00, abs=0.01)
    assert at[2] == pytest.approx(7425.00, abs=0.01)


def test_the_nemotron_floor_the_positional_slice_got_wrong() -> None:
    """Floor 21, not 9. The rig loads at 21 using 11801 MiB and refuses at 20."""
    geom = g("nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf")
    c = vramfit.constant_from_probe(geom, 52, (2211 - 1) * MIB)
    assert vramfit.floor(geom, 11911 * MIB, c) == 21
    assert vramfit.predict(geom, 21, c) / MIB == pytest.approx(11801, abs=3.0)
    assert vramfit.predict(geom, 20, c) > 11911 * MIB


def test_the_constant_holds_across_non_contiguous_placements() -> None:
    """The invariance claim, on the model whose layout broke the old sum.

    Measured VRAM at three placements spanning 9.6 GB of expert weight. The
    positional slice made ``C`` swing 8219.75 MiB and appear to disprove its
    own headline claim.
    """
    geom = g("nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf")
    used = {52: 2211, 40: 6321, 21: 11801}
    constants = [
        vramfit.constant_from_probe(geom, n, (u - 1) * MIB) / MIB
        for n, u in used.items()
    ]
    assert max(constants) - min(constants) < 3.0, constants


@pytest.mark.parametrize(
    "n_ctx,n_seq_max,engine_n_ctx_seq",
    # `-c 8193 -np 8`: the quotient 1024 is already 256-aligned, so truncating
    # returns it unchanged while the engine rounds the remainder up to 1280.
    [(8192, 8, 1024), (8193, 8, 1280), (8448, 8, 1280), (16385, 8, 2304)],
)
def test_context_rounds_the_remainder_up(
    n_ctx: int, n_seq_max: int, engine_n_ctx_seq: int
) -> None:
    assert vramfit.context_per_sequence(n_ctx, n_seq_max) == engine_n_ctx_seq


def test_zero_slots_raises_rather_than_dividing() -> None:
    with pytest.raises(ValueError, match="n_seq_max"):
        vramfit.context_per_sequence(8192, 0)


@pytest.mark.parametrize(
    "n_ubatch,swa_mib",
    # Unified: the window is claimed once for all sequences, so the padded
    # count is already the total. Capping against the per-sequence context and
    # multiplying by the slots again gave 192.00 for both of these.
    [(512, 36.00), (128, 30.00)],
)
def test_a_unified_cache_is_sized_once_not_per_slot(
    n_ubatch: int, swa_mib: float
) -> None:
    out = vramfit.kv_bytes(
        g("gpt-oss-20b-MXFP4.gguf"),
        8192,
        n_seq_max=8,
        n_ubatch=n_ubatch,
        kv_unified=True,
        layers=gpt_oss_measured_rows(),
    )
    assert out["non_swa"] / MIB == pytest.approx(192.00, abs=0.01)
    assert out["swa"] / MIB == pytest.approx(swa_mib, abs=0.01)


def test_the_non_unified_law_holds_where_the_cap_does_not_bind() -> None:
    """``-c 65536``: both caches free of the cap, so the split cannot hide."""
    out = vramfit.kv_bytes(
        g("gpt-oss-20b-MXFP4.gguf"),
        65536,
        n_seq_max=8,
        layers=gpt_oss_measured_rows(),
    )
    assert out["non_swa"] / MIB == pytest.approx(1536.00, abs=0.01)
    assert out["swa"] / MIB == pytest.approx(144.00, abs=0.01)


def test_mla_is_read_from_the_header_not_inferred_from_arithmetic() -> None:
    """``key_length_mla`` is the key llama.cpp reads; the identity is a cross-check.

    ``deepseek2`` declares ``kv_lora_rank`` too but is an older conversion that
    caches K and V outright, so a test based on the presence of that key alone
    would wrongly zero its 864.00 MiB V cache.
    """
    ling = g("Ling-3.0-tiny-Q4_K_M.gguf")
    deepseek = g("deepseek-coder-v2-16b.gguf")
    assert ling["mla_absorbed_v"] and ling["key_length_mla"] == 192
    assert not deepseek["mla_absorbed_v"]
    assert all(r["v_elems"] == 0 for r in ling["kv_layers"])
    assert all(r["v_elems"] == 2048 for r in deepseek["kv_layers"])
    # the two signals agree on every checkpoint measured; disagreement is the
    # interesting case and is recorded rather than resolved
    for name, geom in GEOMETRY.items():
        assert geom["mla_absorbed_v"] == geom["mla_by_identity"], name
