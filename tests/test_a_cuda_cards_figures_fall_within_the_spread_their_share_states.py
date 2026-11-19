"""A CUDA card's decode and prefill figures fall within the spread their share states.

Public rows of llama.cpp's CUDA scoreboard (discussion 15013: Llama 2 7B at Q4_0,
"llama 7B Q4_0 3.56 GiB 6.74 B", tg128 and pp512 per card) against the figures
the product makes for the same card from the shipped hardware table alone: its
bandwidth for decode, its rate on the build's path for prefill. Each measured
speed lies between the figure scaled to the share's lowest card and to its
highest, the spread the share states. The rows include each path's card furthest
from its median.
"""

from __future__ import annotations

import pytest

from mcgyvr import estimate, hardware_table, hubwire

URL = "https://github.com/ggml-org/llama.cpp/discussions/15013"
FILE_BYTES = int(3.56 * 2**30)
PARAMS = 6_740_000_000

#: (table row, compute path, pp512, tg128) as the page states them.
ROWS = [
    ("nvidia-rtx-4090", hubwire.PATH_MATRIX, 11992.70, 186.21),
    ("nvidia-rtx-3060-12gb", hubwire.PATH_MATRIX, 2137.50, 75.57),
    ("nvidia-rtx-2060-super", hubwire.PATH_MATRIX, 1420.24, 60.04),
    ("nvidia-gtx-1080-ti", hubwire.PATH_VECTOR, 1084.41, 62.49),
    ("nvidia-gtx-1660", hubwire.PATH_VECTOR, 148.91, 41.35),
]


def _rate(row: hardware_table.Row, path: str) -> float:
    if path == hubwire.PATH_MATRIX:
        rates = row.cell("compute.matrix_rates").value
        assert isinstance(rates, dict)
        return float(rates["fp16"])
    return float(row.cell("compute.fp32_tflops").value)


def _within(measured: float, figure: float, share: hubwire.FittedShare) -> bool:
    return (
        figure * share.low / share.value
        <= measured
        <= figure * share.high / share.value
    )


@pytest.mark.parametrize(("row_id", "path", "pp", "tg"), ROWS, ids=[r[0] for r in ROWS])
def test_the_measured_speeds_lie_within_the_shares_spread(
    row_id: str, path: str, pp: float, tg: float
) -> None:
    row = hardware_table.shipped_table().row(row_id)
    assert row is not None
    bandwidth = float(row.cell("memory.bandwidth_gbps").value)
    decode = estimate.decode_tps(
        bandwidth, FILE_BYTES, "Q4_0", build=hubwire.BACKEND_CUDA, path=path
    )
    assert isinstance(decode, estimate.Figure)
    share = hubwire.decode_share(hubwire.BACKEND_CUDA, path, "Q4_0")
    assert share is not None
    assert _within(tg, decode.value, share)
    assert URL in decode.basis
    assert f"the cuda share on the {path} path" in decode.basis

    prefill = estimate.prefill_tps(
        _rate(row, path), PARAMS, build=hubwire.BACKEND_CUDA, path=path
    )
    assert isinstance(prefill, estimate.Figure)
    assert prefill.figure == hubwire.FIGURE_ESTIMATE
    assert _within(
        pp, prefill.value, estimate.PREFILL_SHARES[hubwire.BACKEND_CUDA][path]
    )
    assert estimate.PATH_RATES[path] in prefill.basis


def test_a_prefill_figure_is_the_share_of_the_rate_over_two_operations_each() -> None:
    share = estimate.PREFILL_SHARES[hubwire.BACKEND_CUDA][hubwire.PATH_MATRIX]
    got = estimate.prefill_tps(
        100.0, 7_000_000_000, build=hubwire.BACKEND_CUDA, path=hubwire.PATH_MATRIX
    )
    assert isinstance(got, estimate.Figure)
    assert got.value == pytest.approx(share.value * 100e12 / (2 * 7e9))
