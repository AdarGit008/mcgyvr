"""A figure with an unknown or unfitted input is not made, and names that input.

Unknown is never read as zero or as no: a decode, prefill, cache or fit figure
whose input is missing, or whose build, path or width has no public fit, comes
back as :class:`estimate.NoEstimate` with the input named. Invented inputs only.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import estimate, hubwire

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
    ("rate", "params", "build", "path", "named"),
    [
        (100.0, 7_000_000_000, None, MATRIX, "engine build is unknown"),
        (100.0, 7_000_000_000, hubwire.BACKEND_METAL, MATRIX, "the metal build"),
        (100.0, 7_000_000_000, hubwire.BACKEND_VULKAN, MATRIX, "the vulkan build"),
        (100.0, 7_000_000_000, CUDA, None, "compute path on this device is unknown"),
        (100.0, 7_000_000_000, CUDA, "other", "on the other path"),
        (None, 7_000_000_000, CUDA, MATRIX, "matrix FP16 rate is unknown"),
        (0.0, 7_000_000_000, CUDA, VECTOR, "FP32 rate is unknown"),
        (100.0, None, CUDA, MATRIX, "parameter count is unknown"),
        (100.0, 0, CUDA, MATRIX, "parameter count is unknown"),
    ],
)
def test_a_prefill_with_an_unknown_input_names_it(
    rate: float | None,
    params: int | None,
    build: str | None,
    path: str | None,
    named: str,
) -> None:
    got = estimate.prefill_tps(rate, params, build=build, path=path)
    assert isinstance(got, estimate.NoEstimate)
    assert named in got.why


@pytest.mark.parametrize(
    ("header", "named"),
    [
        ({"params_total": 7_000_000_000, "n_expert": 64}, "mixture of experts"),
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
