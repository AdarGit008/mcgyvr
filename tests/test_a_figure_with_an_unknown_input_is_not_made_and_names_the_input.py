"""A figure with an unknown or unfitted input is not made, and names that input.

Unknown is never read as zero or as no: a decode, prefill, cache or fit figure
whose input is missing, of the wrong type or not a finite number, or whose
build, path or width has no public fit, comes back as
:class:`estimate.NoEstimate` with the input named, never as an exception and
never as a figure. Invented inputs only.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from mcgyvr import estimate, hubwire
from tests import machine_shapes
from tests.sizings import machines

CUDA, MATRIX, VECTOR = hubwire.BACKEND_CUDA, hubwire.PATH_MATRIX, hubwire.PATH_VECTOR


@pytest.mark.parametrize(
    ("build", "path", "quant", "named"),
    [
        (hubwire.BACKEND_VULKAN, MATRIX, "Q4_0", "the vulkan build"),
        (hubwire.BACKEND_CPU, VECTOR, "Q4_0", "the cpu build"),
        (CUDA, None, "Q4_0", "compute path on this device is unknown"),
        (CUDA, "other", "Q4_0", "on the other path"),
        (CUDA, MATRIX, "Q8_0", "'Q8_0' (class 8bit)"),
        (CUDA, MATRIX, "Q3_K_M", "'Q3_K_M' (class None)"),
    ],
)
def test_a_decode_with_no_fitted_share_names_what_is_missing(
    build: str, path: str | None, quant: str, named: str
) -> None:
    got = estimate.decode_tps(400.0, 4_000_000_000, quant, build=build, path=path)
    assert isinstance(got, estimate.NoEstimate)
    assert named in got.why


def test_a_decode_with_a_negative_cache_is_not_made() -> None:
    got = estimate.decode_tps(400.0, 4_000_000_000, "Q4_0", cache_bytes=-1)
    assert isinstance(got, estimate.NoEstimate)


@pytest.mark.parametrize(
    ("cache", "named"),
    [
        (None, "not a count of bytes: None"),
        (math.nan, "not a count of bytes: nan"),
        (math.inf, "not a count of bytes: inf"),
        (1.5e9, "not a count of bytes: 1500000000.0"),
        (True, "not a count of bytes: True"),
        ("1000", "not a count of bytes: '1000'"),
        (estimate.NoEstimate("no caching layers"), "is unknown: no caching layers"),
    ],
)
def test_a_decode_with_a_cache_that_is_not_a_byte_count_names_it(
    cache: Any, named: str
) -> None:
    got = estimate.decode_tps(400.0, 4_000_000_000, "Q4_0", cache_bytes=cache)
    assert isinstance(got, estimate.NoEstimate)
    assert "the cache a token reads" in got.why
    assert named in got.why


@pytest.mark.parametrize(
    ("rate", "params", "quant", "build", "path", "named"),
    [
        (100.0, 7_000_000_000, "Q4_0", None, MATRIX, "engine build is unknown"),
        (100.0, 7_000_000_000, "Q4_0", hubwire.BACKEND_METAL, MATRIX, "metal build"),
        (100.0, 7_000_000_000, "Q4_0", hubwire.BACKEND_VULKAN, MATRIX, "vulkan build"),
        (100.0, 7_000_000_000, "Q4_0", CUDA, None, "compute path on this device"),
        (100.0, 7_000_000_000, "Q4_0", CUDA, "other", "on the other path"),
        (100.0, 7_000_000_000, None, CUDA, MATRIX, "quantisation is unknown"),
        (100.0, 7_000_000_000, "Q8_0", CUDA, MATRIX, "'Q8_0' (class 8bit)"),
        (100.0, 7_000_000_000, "F16", CUDA, VECTOR, "'F16' (class 8bit)"),
        (100.0, 7_000_000_000, "Q3_K_M", CUDA, MATRIX, "'Q3_K_M' (class None)"),
        (100.0, 7_000_000_000, "", CUDA, MATRIX, "'' (class None)"),
        (None, 7_000_000_000, "Q4_0", CUDA, MATRIX, "matrix FP16 rate is unknown"),
        (0.0, 7_000_000_000, "Q4_0", CUDA, VECTOR, "FP32 rate is unknown"),
        (math.inf, 7_000_000_000, "Q4_0", CUDA, MATRIX, "rate is unknown: inf"),
        (math.nan, 7_000_000_000, "Q4_0", CUDA, MATRIX, "rate is unknown: nan"),
        (True, 7_000_000_000, "Q4_0", CUDA, MATRIX, "rate is unknown: True"),
        ("100", 7_000_000_000, "Q4_0", CUDA, MATRIX, "rate is unknown: '100'"),
        (100.0, None, "Q4_0", CUDA, MATRIX, "parameter count is unknown"),
        (100.0, 0, "Q4_0", CUDA, MATRIX, "parameter count is unknown"),
        (100.0, True, "Q4_0", CUDA, MATRIX, "parameter count is unknown: True"),
        (100.0, 7e9, "Q4_0", CUDA, MATRIX, "parameter count is unknown: 7000000000.0"),
        (100.0, estimate.NoEstimate("x"), "Q4_0", CUDA, MATRIX, "parameter count"),
    ],
)
def test_a_prefill_with_an_unknown_input_names_it(
    rate: Any,
    params: Any,
    quant: str | None,
    build: str | None,
    path: str | None,
    named: str,
) -> None:
    got = estimate.prefill_tps(rate, params, quant=quant, build=build, path=path)
    assert isinstance(got, estimate.NoEstimate)
    assert named in got.why


def test_a_prefill_at_the_fitted_width_is_a_figure_at_every_4_bit_quant() -> None:
    for quant in ("Q4_0", "Q4_K_M", "IQ4_XS", "Q5_K_M", "Q6_K", "MXFP4"):
        got = estimate.prefill_tps(
            100.0, 7_000_000_000, quant=quant, build=CUDA, path=MATRIX
        )
        assert isinstance(got, estimate.Figure), (quant, got)


@pytest.mark.parametrize(
    ("header", "named"),
    [
        (
            {"params_total": 7_000_000_000, "placeable_blocks": [0, 1]},
            "mixture of experts",
        ),
        (
            {"params_total": 7_000_000_000, "n_expert": 64, "placeable_blocks": [3]},
            "mixture of experts",
        ),
        ({}, "no parameter count"),
        ({"params_total": None}, "no parameter count"),
        ({"params_total": True}, "no parameter count"),
    ],
)
def test_prefill_parameters_are_a_dense_headers_count_or_none(
    header: dict[str, Any], named: str
) -> None:
    got = estimate.prefill_params(header)
    assert isinstance(got, estimate.NoEstimate)
    assert named in got.why


def test_a_dense_headers_parameters_are_all_of_them() -> None:
    assert estimate.prefill_params({"params_total": 7_000_000_000}) == 7_000_000_000
    assert (
        estimate.prefill_params({"params_total": 7_000_000_000, "n_expert": 0})
        == 7_000_000_000
    )


def test_a_header_is_a_mixture_of_experts_by_the_products_one_rule() -> None:
    """``architecture_of`` decides, from the blocks the scan found: an expert
    count a header states beside no placeable block does not make it one."""
    for header in (
        {"params_total": 7_000_000_000, "n_expert": 128, "placeable_blocks": []},
        {"params_total": 7_000_000_000, "n_expert": "128"},
    ):
        assert estimate.prefill_params(header) == 7_000_000_000


@pytest.mark.parametrize(
    ("header", "tokens", "cache_type", "named"),
    [
        ({"kv_layers": []}, 4096, "f16", "no caching layers"),
        ({}, 4096, "f16", "no caching layers"),
        (
            {"kv_layers": [{"layer": 0, "is_swa": False, "k_elems": 1, "v_elems": 1}]},
            4096,
            "q3_k",
            "has no width",
        ),
        (
            {"kv_layers": [{"layer": 0, "is_swa": False, "k_elems": 1, "v_elems": 1}]},
            -1,
            "f16",
            "fewer than 0",
        ),
        (
            {
                "arch": "invented",
                "sliding_window": 512,
                "kv_layers": [{"layer": 0, "is_swa": None, "k_elems": 1, "v_elems": 1}],
            },
            4096,
            "f16",
            "cannot be sized",
        ),
    ],
)
def test_a_cache_figure_with_an_unknown_input_names_it(
    header: dict[str, Any], tokens: int, cache_type: str, named: str
) -> None:
    got = estimate.context_bytes(header, tokens, cache_type=cache_type)
    assert isinstance(got, estimate.NoEstimate)
    assert named in got.why


@pytest.mark.parametrize("tokens", [None, True, 4096.0, math.nan, "4096"])
def test_a_context_that_is_not_a_count_of_tokens_names_it(tokens: Any) -> None:
    header = {"kv_layers": [{"layer": 0, "is_swa": False, "k_elems": 1, "v_elems": 1}]}
    got = estimate.context_bytes(header, tokens)
    assert isinstance(got, estimate.NoEstimate)
    assert f"a count of tokens, not {tokens!r}" in got.why


@pytest.mark.parametrize(
    ("ctx", "slots"), [(None, 1), (True, 1), (4096.0, 1), (4096, None), (4096, "2")]
)
def test_a_fit_with_a_context_or_slots_that_are_not_counts_names_them(
    ctx: Any, slots: Any
) -> None:
    scan = machine_shapes.scan(machines()[0])
    header = {"file": "/models/x.gguf", "size_bytes": 1 << 30, "kv_layers": []}
    got = estimate.line_fit(scan, header, ctx_per_slot=ctx, slots=slots)
    assert isinstance(got, estimate.NoEstimate)
    assert f"not {ctx!r} and {slots!r}" in got.why
