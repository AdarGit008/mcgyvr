"""A decode estimate is bandwidth over the bytes a token reads, and says so.

Before a unit of a model has been measured, its decode speed is estimated as
the device's memory bandwidth over the weight bytes one token reads, at the
share of the bandwidth the quantisation's class states, never more than the
class's high-bandwidth share from the high-bandwidth line up on the vendor the
shares were fitted on. The shares are the ones the published fit states. The
estimate names itself and its basis; a quantisation the rule was not fitted to
gets none, and a measured speed replaces the estimate. The devices and models
are invented.
"""

from __future__ import annotations

import pytest

from mcgyvr import estimate
from mcgyvr.hubwire import FIGURE_KINDS

GIB = 1 << 30
#: An invented dense model's file: 3.56 GiB.
MODEL_BYTES = int(3.56 * GIB)


def by_rule(bandwidth: float, model_bytes: int, klass: str, vendor: str) -> float:
    eff = estimate.DECODE_EFFICIENCY[klass]
    if vendor == estimate.FITTED_ON and bandwidth >= estimate.HIGH_BANDWIDTH_GBPS:
        eff = min(eff, estimate.HIGH_BANDWIDTH_EFFICIENCY[klass])
    return eff * bandwidth / (model_bytes / 1e9)


def test_the_shares_are_the_published_fits() -> None:
    """llama.cpp discussion 4167's Apple-silicon runs, as the module's comment
    derives them: 0.75 and 0.60 under the 8-bit and 4-bit medians, and from
    800 GB/s up 0.50 and 0.40."""
    assert dict(estimate.DECODE_EFFICIENCY) == {"8bit": 0.75, "4bit": 0.60}
    assert dict(estimate.HIGH_BANDWIDTH_EFFICIENCY) == {"8bit": 0.50, "4bit": 0.40}
    assert estimate.HIGH_BANDWIDTH_GBPS == 800.0
    assert estimate.FITTED_ON == "apple"


def test_a_4_bit_model_on_a_400_gbps_device_is_the_4_bit_share_over_its_size() -> None:
    got = estimate.decode_tps(400.0, MODEL_BYTES, "Q4_0")
    assert isinstance(got, estimate.Figure)
    assert got.value == pytest.approx(
        estimate.DECODE_EFFICIENCY["4bit"] * 400.0 / (MODEL_BYTES / 1e9)
    )
    assert got.figure == "estimate" and got.figure in FIGURE_KINDS
    assert "400 GB/s" in got.basis and "read per token" in got.basis


def test_a_file_of_3_82_decimal_gb_on_400_gbps_is_0_60_of_400_over_3_82() -> None:
    got = estimate.decode_tps(400.0, 3_820_000_000, "Q4_0")
    assert isinstance(got, estimate.Figure)
    assert got.value == pytest.approx(0.60 * 400 / 3.82)


@pytest.mark.parametrize(
    ("quant", "klass"),
    [
        ("F16", "8bit"),
        ("BF16", "8bit"),
        ("Q8_0", "8bit"),
        ("Q4_0", "4bit"),
        ("q4_K_M", "4bit"),
        ("UD-Q4_K_XL", "4bit"),
        ("IQ4_XS", "4bit"),
        ("MXFP4", "4bit"),
        ("Q5_K_M", "4bit"),
        ("Q6_K", "4bit"),
    ],
)
@pytest.mark.parametrize("bandwidth", [100.0, 799.0, 800.0, 1500.0])
@pytest.mark.parametrize("vendor", ["apple", "nvidia"])
def test_each_quantisation_decodes_at_its_class_share(
    quant: str, klass: str, bandwidth: float, vendor: str
) -> None:
    got = estimate.decode_tps(bandwidth, MODEL_BYTES, quant, vendor=vendor)
    assert isinstance(got, estimate.Figure)
    assert got.value == pytest.approx(by_rule(bandwidth, MODEL_BYTES, klass, vendor))
    fitted_elsewhere = "fitted on Apple silicon" in got.basis
    assert fitted_elsewhere == (vendor != estimate.FITTED_ON)


@pytest.mark.parametrize("quant", ["Q3_K_M", "Q2_K", "IQ2_XS", "AWQ-4bit", "F32", ""])
def test_a_quantisation_the_rule_was_not_fitted_to_gets_no_estimate(quant: str) -> None:
    got = estimate.decode_tps(400.0, MODEL_BYTES, quant)
    assert isinstance(got, estimate.NoEstimate)
    assert "no decode estimate" in got.why


@pytest.mark.parametrize(("bandwidth", "size"), [(0.0, MODEL_BYTES), (400.0, 0)])
def test_no_bandwidth_or_no_size_gets_no_estimate(bandwidth: float, size: int) -> None:
    assert isinstance(estimate.decode_tps(bandwidth, size, "Q4_0"), estimate.NoEstimate)


def test_a_mixture_of_experts_reads_its_shared_weights_and_the_experts_it_uses() -> (
    None
):
    geometry = {
        "n_expert": 16,
        "n_expert_used": 2,
        "bytes_experts": 16 * GIB,
        "bytes_nonexpert": GIB,
    }
    assert estimate.token_bytes(17 * GIB, geometry) == GIB + 16 * GIB * 2 // 16
    assert estimate.token_bytes(17 * GIB, None) == 17 * GIB
    assert estimate.token_bytes(17 * GIB, {"n_expert": 0}) == 17 * GIB


def test_a_reading_replaces_the_estimate_and_names_where_it_was_taken() -> None:
    guess = estimate.decode_tps(400.0, MODEL_BYTES, "Q4_0")
    measured = estimate.prefer(12.5, guess, where="box-1.example")
    assert isinstance(measured, estimate.Figure)
    assert (measured.value, measured.figure) == (12.5, "reading")
    assert "box-1.example" in measured.basis
    assert estimate.prefer(None, guess) is guess


def test_an_estimate_from_an_unverified_row_says_so() -> None:
    got = estimate.decode_tps(400.0, MODEL_BYTES, "Q4_0", verified=False)
    assert isinstance(got, estimate.Figure)
    assert got.figure == "estimate" and not got.verified


def test_a_figure_is_only_an_estimate_or_a_reading() -> None:
    with pytest.raises(ValueError, match="figure"):
        estimate.Figure(1.0, "guess", "invented")
