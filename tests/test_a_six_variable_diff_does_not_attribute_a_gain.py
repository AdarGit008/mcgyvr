""" "The arch spoof is worth 1.7x" is a sentence about one variable, measured
across six.

``Dockerfile.nomma-dp4a`` differs from ``ghcr.io/ggml-org/llama.cpp:server-cuda-b10644``
in the CUDA architecture list (the hypothesis), ``GGML_CUDA_FORCE_MMQ``,
``GGML_NATIVE``, ``GGML_CPU_ALL_VARIANTS`` + ``GGML_BACKEND_DL``, the CUDA
toolkit and cuBLAS that ship in the base image, and the linker flags. The CPU
ones are first-order for every ``--n-cpu-moe`` cell, where the expert GEMMs run
on a core-limited 6-thread CPU.

So the run builds a ladder, each rung moving one thing, and the external stock
image is an anchor for "what stock means to a user" rather than the control for a
mechanism claim.

======  ==============================  ==========  =====  ==========================
build   CMAKE_CUDA_ARCHITECTURES        FORCE_MMQ   patch  isolates
======  ==============================  ==========  =====  ==========================
L0      75-real;75-virtual              OFF         no     local-build baseline
L1      75-real;75-virtual              ON          no     FORCE_MMQ alone
L2      61-virtual;80-virtual           ON          no     the arch spoof (= v2)
L3      61-virtual;80-virtual           ON          yes    the ship candidate (= v3)
L4      75-real;75-virtual, NATIVE=ON   OFF         no     the CPU build flags alone
======  ==============================  ==========  =====  ==========================

And the mechanism is checkable statically, at zero rig cost: if ``mma.sync`` is
still present on the selected paths in L2/L3, or absent from L0/L1, then no
throughput number can be attributed to removing it and the campaign is over
before it starts.
"""

from __future__ import annotations

import pytest

from tests.sweeprows import RUN, artifact

BEHAVIOUR = "run tools/runs/srv1-build-ladder.sh"
LADDER = RUN / "srv1-build-ladder.tsv"
RUNGS = ("L0", "L1", "L2", "L3", "L4")


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — build ladder unbuilt")
def test_every_rung_of_the_ladder_was_built_and_measured() -> None:
    sweep = artifact(LADDER, BEHAVIOUR)
    built = {s.get("arm") for s in sweep.stamps("BUILD")}
    assert set(RUNGS) <= built, f"no build stamp for {sorted(set(RUNGS) - built)}"
    measured = {r.fields.get("arm") for r in sweep.of_kind("BENCH")}
    assert set(RUNGS) <= measured, f"no measurement for {sorted(set(RUNGS) - measured)}"


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — build ladder unbuilt")
def test_each_rung_differs_from_its_neighbour_in_exactly_one_declared_variable() -> (
    None
):
    keys = (
        "cuda_architectures",
        "force_mmq",
        "ggml_native",
        "cpu_all_variants",
        "patched",
    )
    sweep = artifact(LADDER, BEHAVIOUR)
    stamps = {s["arm"]: s for s in sweep.stamps("BUILD") if "arm" in s}
    for lower, upper in (("L0", "L1"), ("L1", "L2"), ("L2", "L3")):
        assert lower in stamps and upper in stamps, f"{lower} or {upper} was not built"
        moved = [k for k in keys if stamps[lower].get(k) != stamps[upper].get(k)]
        assert len(moved) == 1, (
            f"{lower} -> {upper} moved {moved}. A rung that moves two things "
            "attributes nothing, which is the defect this ladder exists to fix."
        )


@pytest.mark.xfail(strict=True, reason="2026-09-02: owed — no cuobjdump check")
def test_the_mechanism_is_confirmed_in_the_binary_before_any_throughput_is_quoted() -> (
    None
):
    """``cuobjdump`` on the built libraries. Free, and it can end the campaign
    early: an arch list that did not actually remove the tensor-core paths makes
    every downstream number unattributable."""
    sweep = artifact(LADDER, BEHAVIOUR)
    kernels = {s["arm"]: s for s in sweep.stamps("KERNELS") if "arm" in s}
    for rung in ("L0", "L1"):
        assert kernels.get(rung, {}).get("tensor_core_instructions") == "present", (
            f"{rung} compiles for sm_75 and should contain HMMA/IMMA; it does not, "
            "so the baseline is not what it claims to be"
        )
    for rung in ("L2", "L3"):
        assert kernels.get(rung, {}).get("tensor_core_instructions") == "absent", (
            f"{rung} still contains tensor-core instructions on the selected "
            "paths. The arch spoof did not take, and no gain measured against it "
            "can be attributed to removing them."
        )
