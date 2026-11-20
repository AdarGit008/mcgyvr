"""A decode rule named by its engine build takes that build's fitted share.

The wire's rule (:func:`hubwire.decode_efficiency`, :func:`hubwire.decode_ms_per_gib`)
takes the engine build and its compute path as keywords. Unnamed, or named
Metal, it answers as every caller of the wire is answered today: Apple's shares
and Apple's ceiling. Named CUDA, it takes the share fitted on llama.cpp's CUDA
scoreboard for the path (:data:`hubwire.DECODE_SHARES`), with no ceiling. A
build, path or width with no fit gets no figure, never a borrowed share.
Invented bandwidths only.
"""

from __future__ import annotations

import itertools

import pytest

from mcgyvr import hubwire

BANDWIDTHS = (100.0, 400.0, 799.0, 800.0, 1200.0)
QUANTS = ("F16", "Q8_0", "Q4_0", "Q4_K_M", "IQ4_XS", "Q6_K", "Q3_K_S", "F32", "")
VENDORS = (hubwire.FITTED_ON, "nvidia", "other")


@pytest.mark.parametrize(
    ("bandwidth", "quant", "vendor"),
    list(itertools.product(BANDWIDTHS, QUANTS, VENDORS)),
)
def test_no_build_and_metal_answer_as_every_caller_of_today(
    bandwidth: float, quant: str, vendor: str
) -> None:
    today = hubwire.decode_efficiency(bandwidth, quant, vendor=vendor)
    assert (
        hubwire.decode_efficiency(bandwidth, quant, vendor=vendor, build=None) == today
    )
    metal = hubwire.decode_efficiency(
        bandwidth, quant, vendor=vendor, build=hubwire.BACKEND_METAL
    )
    assert metal == today
    ms = hubwire.decode_ms_per_gib(bandwidth, quant, vendor=vendor)
    assert hubwire.decode_ms_per_gib(bandwidth, quant, vendor=vendor, build=None) == ms


@pytest.mark.parametrize(
    ("path", "share"), [(hubwire.PATH_MATRIX, 0.725), (hubwire.PATH_VECTOR, 0.558)]
)
@pytest.mark.parametrize("quant", ["Q4_0", "Q4_K_M", "IQ4_XS", "Q6_K", "MXFP4"])
@pytest.mark.parametrize("bandwidth", BANDWIDTHS)
def test_cuda_takes_its_paths_share_with_no_ceiling(
    path: str, share: float, quant: str, bandwidth: float
) -> None:
    for vendor in VENDORS:
        got = hubwire.decode_efficiency(
            bandwidth, quant, vendor=vendor, build=hubwire.BACKEND_CUDA, path=path
        )
        assert got == share
        ms = hubwire.decode_ms_per_gib(
            bandwidth, quant, vendor=vendor, build=hubwire.BACKEND_CUDA, path=path
        )
        assert ms == pytest.approx(
            1000 * hubwire.BYTES_PER_GIB / (share * bandwidth * 1e9)
        )


@pytest.mark.parametrize(
    ("build", "path", "quant"),
    [
        (hubwire.BACKEND_CUDA, hubwire.PATH_MATRIX, "Q8_0"),
        (hubwire.BACKEND_CUDA, hubwire.PATH_MATRIX, "F16"),
        (hubwire.BACKEND_CUDA, hubwire.PATH_MATRIX, "Q3_K_M"),
        (hubwire.BACKEND_CUDA, None, "Q4_0"),
        (hubwire.BACKEND_CUDA, "other", "Q4_0"),
        (hubwire.BACKEND_VULKAN, hubwire.PATH_MATRIX, "Q4_0"),
        (hubwire.BACKEND_ROCM, hubwire.PATH_MATRIX, "Q4_0"),
        (hubwire.BACKEND_SYCL, hubwire.PATH_VECTOR, "Q4_0"),
        (hubwire.BACKEND_CPU, hubwire.PATH_VECTOR, "Q4_0"),
    ],
)
def test_a_build_path_or_width_with_no_fit_gets_no_figure(
    build: str, path: str | None, quant: str
) -> None:
    assert (
        hubwire.decode_efficiency(400.0, quant, vendor="nvidia", build=build, path=path)
        is None
    )
    assert (
        hubwire.decode_ms_per_gib(400.0, quant, vendor="nvidia", build=build, path=path)
        is None
    )
    assert hubwire.decode_share(build, path, quant) is None


def test_each_fitted_share_states_its_spread_and_source() -> None:
    for build, paths in hubwire.DECODE_SHARES.items():
        for path, classes in paths.items():
            assert path in hubwire.COMPUTE_PATHS
            for klass, share in classes.items():
                assert klass in hubwire.DECODE_EFFICIENCY, (build, path)
                assert share.low <= share.value <= share.high
                assert share.cards >= 1
                assert share.worst
                assert share.source.startswith("https://")
    with pytest.raises(TypeError):
        hubwire.DECODE_SHARES[hubwire.BACKEND_CUDA] = {}  # type: ignore[index]
