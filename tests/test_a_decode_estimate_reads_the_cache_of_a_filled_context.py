"""A decode estimate reads the cache of a filled context beside the weights.

A token decoded after ``n`` tokens of context reads the weights in use and the
cache of those ``n`` tokens, so ``cache_bytes`` adds to the bytes a token reads.
The cache figure is the fit law's own for one sequence
(:func:`estimate.context_bytes`, through :func:`vramfit.kv_bytes`), at the cache
type given. With none, the figure is today's to the byte.

The term is checked against the one public row found, and its basis says so:
llama-bench on an NVIDIA Thor, Qwen3-Coder-30B-A3B at Q8_0 with flash attention
and an f16 cache (llama.cpp discussion 16578), "tg32 | 44.26" on an empty
context down to "tg32 @ d32768 | 26.92". Its geometry is the model's public
``config.json``: 48 layers, 4 KV heads of 128, 128 experts with 8 in use, each
2048 x 768 x 3. The term reads the fall to 8k within 2% and reads slow beyond:
9% at 16k, 13% at 32k, the figures :data:`estimate.CACHE_TERM_CHECK` states.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import estimate
from mcgyvr.serving import vramfit

LAYERS = 48
#: 4 KV heads of 128 elements, for K and for V.
KV_ELEMS = 4 * 128
FILE_BYTES = int(30.25 * 2**30)
#: The experts' parameters, at Q8_0's 34 bytes a block of 32.
EXPERT_BYTES = int(LAYERS * 128 * 3 * 2048 * 768 * 34 / 32)
#: (context, tg32) as the page states them.
MEASURED = [(0, 44.26), (4096, 39.46), (8192, 36.88), (16384, 33.55), (32768, 26.92)]


def _header(*, sliding: bool = False) -> dict[str, Any]:
    return {
        "file": "/models/public-row.gguf",
        "size_bytes": FILE_BYTES,
        "arch": "qwen3moe",
        "n_expert": 128,
        "n_expert_used": 8,
        "bytes_experts": EXPERT_BYTES,
        "bytes_nonexpert": FILE_BYTES - EXPERT_BYTES,
        "sliding_window": 1024 if sliding else None,
        "kv_layers": [
            {
                "layer": layer,
                "is_swa": sliding and layer % 2 == 0,
                "k_elems": KV_ELEMS,
                "v_elems": KV_ELEMS,
            }
            for layer in range(LAYERS)
        ],
    }


@pytest.mark.parametrize("tokens", [0, 1, 255, 256, 4096, 32768])
@pytest.mark.parametrize("cache_type", ["f16", "q8_0", "q4_0"])
@pytest.mark.parametrize("sliding", [False, True])
def test_the_cache_figure_is_the_fit_laws_for_one_sequence(
    tokens: int, cache_type: str, sliding: bool
) -> None:
    header = _header(sliding=sliding)
    got = estimate.context_bytes(header, tokens, cache_type=cache_type)
    law = vramfit.kv_bytes(
        dict(header),
        tokens,
        n_seq_max=1,
        cache_type_k=cache_type,
        cache_type_v=cache_type,
    )["total"]
    assert got == law


def test_no_cache_is_todays_figure_to_the_byte() -> None:
    for quant in ("Q4_0", "Q8_0", "F16"):
        today = estimate.decode_tps(400.0, 4_000_000_000, quant)
        assert estimate.decode_tps(400.0, 4_000_000_000, quant, cache_bytes=0) == today


def test_the_cache_adds_to_the_bytes_a_token_reads_and_says_what_checked_it() -> None:
    weights, cache = 4_000_000_000, 1_000_000_000
    got = estimate.decode_tps(400.0, weights, "Q4_0", cache_bytes=cache)
    assert isinstance(got, estimate.Figure)
    eff = estimate.DECODE_EFFICIENCY["4bit"]
    assert got.value == pytest.approx(eff * 400.0 / 5.0)
    assert "4.00 GB of weights and 1.00 GB of cache" in got.basis
    assert estimate.CACHE_TERM_CHECK in got.basis
    assert "discussions/16578" in got.basis
    assert "9% at 16k tokens and 13% at 32k" in got.basis


def test_the_public_row_falls_as_the_term_says_to_8k_and_slower_after() -> None:
    header = _header()
    weights = estimate.token_bytes(FILE_BYTES, header)
    empty = estimate.decode_tps(273.0, weights, "Q8_0")
    assert isinstance(empty, estimate.Figure)
    gaps = {}
    for tokens, measured in MEASURED:
        cache = estimate.context_bytes(header, tokens)
        assert isinstance(cache, int)
        filled = estimate.decode_tps(273.0, weights, "Q8_0", cache_bytes=cache)
        assert isinstance(filled, estimate.Figure)
        predicted = MEASURED[0][1] * filled.value / empty.value
        gaps[tokens] = predicted / measured - 1
    assert all(abs(gaps[tokens]) < 0.02 for tokens in (0, 4096, 8192)), gaps
    assert -0.10 < gaps[16384] < -0.08, gaps
    assert -0.14 < gaps[32768] < -0.12, gaps
