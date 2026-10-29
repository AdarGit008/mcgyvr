"""The decode rule a hub plans by is the wire's.

A token reads every weight once, so a device decodes at its memory bandwidth
times an efficiency, fitted on llama.cpp's own Apple-silicon runs
(:data:`hubwire.DECODE_EFFICIENCY`, capped from
:data:`hubwire.HIGH_BANDWIDTH_GBPS` up on the vendor it was fitted on). The
hub plans by milliseconds per GiB of weights
(:func:`hubwire.decode_ms_per_gib`), the product estimates by tokens per
second; both read the one rule here.

Held here: the fitted values and the classes a quantisation name falls in;
the efficiency for each class, under and over the high-bandwidth line, for
the fitted vendor and another; and the milliseconds per GiB that follow,
with no figure for a quantisation the rule was not fitted on or no bandwidth.
Invented devices only.
"""

from __future__ import annotations

import math

import pytest

from mcgyvr import hubwire


def test_the_fitted_values_are_the_rules() -> None:
    assert dict(hubwire.DECODE_EFFICIENCY) == {"8bit": 0.75, "4bit": 0.60}
    assert dict(hubwire.HIGH_BANDWIDTH_EFFICIENCY) == {"8bit": 0.50, "4bit": 0.40}
    assert hubwire.HIGH_BANDWIDTH_GBPS == 800.0
    assert hubwire.FITTED_ON == "apple"
    assert set(hubwire.QUANT_CLASSES) == set(hubwire.DECODE_EFFICIENCY)
    assert set(hubwire.HIGH_BANDWIDTH_EFFICIENCY) == set(hubwire.DECODE_EFFICIENCY)
    assert (hubwire.BYTES_PER_DECIMAL_GB, hubwire.BYTES_PER_GIB) == (1e9, 1 << 30)
    with pytest.raises(TypeError):
        hubwire.DECODE_EFFICIENCY["4bit"] = 1.0  # type: ignore[index]


@pytest.mark.parametrize(
    ("quant", "klass"),
    [
        ("F16", "8bit"),
        ("bf16", "8bit"),
        ("Q8_0", "8bit"),
        ("Q4_K_M", "4bit"),
        ("IQ4_XS", "4bit"),
        ("UD-Q4_K_XL", "4bit"),
        (" q6_k ", "4bit"),
        ("MXFP4", "4bit"),
        ("Q3_K_S", None),
        ("F32", None),
        ("", None),
    ],
)
def test_a_quantisation_falls_in_its_class_by_its_names_start(
    quant: str, klass: str | None
) -> None:
    assert hubwire.quant_class(quant) == klass


@pytest.mark.parametrize(
    ("bandwidth", "quant", "vendor", "efficiency"),
    [
        (400.0, "Q4_K_M", "apple", 0.60),
        (400.0, "Q8_0", "apple", 0.75),
        (799.9, "Q4_0", "apple", 0.60),
        (800.0, "Q4_0", "apple", 0.40),
        (800.0, "F16", "apple", 0.50),
        (1000.0, "Q4_0", "nvidia", 0.60),
        (1000.0, "Q8_0", "nvidia", 0.75),
        (400.0, "Q2_K", "apple", None),
    ],
)
def test_a_device_decodes_at_its_classs_share_capped_where_it_was_seen(
    bandwidth: float, quant: str, vendor: str, efficiency: float | None
) -> None:
    assert hubwire.decode_efficiency(bandwidth, quant, vendor=vendor) == efficiency


def test_the_vendor_is_always_named() -> None:
    """No default: a hub that sees no vendor must say which it means."""
    with pytest.raises(TypeError):
        hubwire.decode_efficiency(900.0, "Q4_0")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        hubwire.decode_ms_per_gib(900.0, "Q4_0")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("kind", "backend", "fitted"),
    [
        (hubwire.RESOURCE_UNIFIED, hubwire.BACKEND_METAL, True),
        (hubwire.RESOURCE_UNIFIED, hubwire.BACKEND_VULKAN, False),
        (hubwire.RESOURCE_GPU, hubwire.BACKEND_METAL, False),
        (hubwire.RESOURCE_GPU, hubwire.BACKEND_CUDA, False),
        (hubwire.RESOURCE_CPU, hubwire.BACKEND_CPU, False),
        (hubwire.RESOURCE_RAM, hubwire.BACKEND_CPU, False),
    ],
)
def test_a_device_is_of_the_fitted_vendor_only_as_a_unified_metal_device(
    kind: str, backend: str, fitted: bool
) -> None:
    assert hubwire.fitted_on(kind, backend) is fitted


def test_a_hub_caps_only_a_fitted_device_by_its_kind_and_backend() -> None:
    """An invented 1000 GB/s unified Metal device takes the ceiling; an
    invented 1000 GB/s CUDA card of the same bandwidth does not."""

    def vendor(kind: str, backend: str) -> str:
        return hubwire.FITTED_ON if hubwire.fitted_on(kind, backend) else backend

    mac = vendor(hubwire.RESOURCE_UNIFIED, hubwire.BACKEND_METAL)
    card = vendor(hubwire.RESOURCE_GPU, hubwire.BACKEND_CUDA)
    assert hubwire.decode_efficiency(1000.0, "Q4_0", vendor=mac) == 0.40
    assert hubwire.decode_efficiency(1000.0, "Q4_0", vendor=card) == 0.60


def test_a_token_takes_a_gib_over_the_bandwidth_it_gets() -> None:
    """An invented 400 GB/s unified device at 4-bit: 0.60 of 400 GB/s reads a
    GiB in 4.47 ms; the bandwidth alone would read it in 2.68."""
    ms = hubwire.decode_ms_per_gib(400.0, "Q4_K_M", vendor=hubwire.FITTED_ON)
    assert ms is not None
    assert math.isclose(ms, 1000 * (1 << 30) / (0.60 * 400.0 * 1e9))
    assert round(ms, 2) == 4.47
    assert round(ms * 0.60, 2) == 2.68


@pytest.mark.parametrize(
    ("bandwidth", "quant", "vendor"),
    [
        (360.0, "Q8_0", "nvidia"),
        (1000.0, "Q4_0", "apple"),
        (1000.0, "Q4_0", "nvidia"),
        (50.0, "F16", "apple"),
    ],
)
def test_the_milliseconds_are_the_efficiencys_for_every_device(
    bandwidth: float, quant: str, vendor: str
) -> None:
    efficiency = hubwire.decode_efficiency(bandwidth, quant, vendor=vendor)
    assert efficiency is not None
    ms = hubwire.decode_ms_per_gib(bandwidth, quant, vendor=vendor)
    gb_per_gib = hubwire.BYTES_PER_GIB / hubwire.BYTES_PER_DECIMAL_GB
    assert ms is not None
    assert math.isclose(ms, 1000 * gb_per_gib / (efficiency * bandwidth))


@pytest.mark.parametrize(
    ("bandwidth", "quant"),
    [(400.0, "Q3_K_M"), (400.0, "F32"), (0.0, "Q4_0"), (-1.0, "Q8_0")],
)
def test_no_milliseconds_without_a_fitted_quantisation_or_a_bandwidth(
    bandwidth: float, quant: str
) -> None:
    assert hubwire.decode_ms_per_gib(bandwidth, quant, vendor=hubwire.FITTED_ON) is None
