"""A bound is declared only under 1% spread, measured twice, inside its scope.

RED. ``mcgyvr.fleet.bounds`` does not exist, and ``vramfit`` still gives
qwen3next the 768 MiB allowance it was measured to exceed. The intent is
``records/plans/fleet-identity.md``, the BOUND/EXPECTED rule (cut-off approved).

The rule, for every memory parameter weighed against the rig it is applied to::

    spread <= 1% of that rig's VRAM or RAM total, and verified (n >= 2, cited,
    inside its scope arch x rig)  -> BOUND: declare the worst, never observe it
    otherwise                     -> EXPECTED: observe it, dev fails loud

``SCRATCH_AND_CONTEXT_MIB = 768`` (``src/mcgyvr/serving/vramfit.py:66``) is why
scope is part of it: a bound verified on four archs, then qwen3next measured
817-829 MiB (``records/measurements/measuring-gaps-2026-09-10/README.md`` Q3). A
bound used outside what verified it admits a cell that OOMs at load.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from tests.red_port.conftest import required

REPO = Path(__file__).resolve().parents[1]


def _bounds() -> Any:
    return required(
        "declare each small, verified, scoped memory parameter once, at its worst",
        lambda: importlib.import_module("mcgyvr.fleet.bounds"),
    )


def test_every_declared_bound_obeys_the_one_percent_rule() -> None:
    bounds = _bounds()
    assert bounds.BOUNDS, "the registry declares nothing"
    for row in bounds.BOUNDS:
        assert row.spread <= 0.01 * row.total, f"{row.name}: spread over 1%"
        assert row.n >= 2, f"{row.name}: verified by fewer than two readings"
        assert (REPO / row.citation).exists(), f"{row.name}: cites {row.citation}"


def test_the_campaign_s_verified_parameters_are_declared_at_their_worst() -> None:
    bounds = _bounds()
    assert bounds.bound("vllm_unit_host_ram_gib", arch=None, rig="srv1") == 2.60
    assert bounds.bound("vllm_unit_host_ram_gib", arch=None, rig="srv2") == 2.95
    assert bounds.bound("vllm_l2_residual_mib", arch=None, rig="srv2") == 234
    assert bounds.bound("vllm_cold_start_overhead_mib", arch=None, rig="srv2") == 20
    assert bounds.bound("c_step_mib", arch="qwen35moe", rig="srv2") == 38
    assert bounds.bound("c_step_mib", arch="deepseek2", rig="srv2") == 74
    assert bounds.bound("scratch_mib", arch="qwen3next", rig="srv2") == 829


def test_the_scratch_allowance_for_qwen3next_is_what_it_measured() -> None:
    """Today 768: a qwen3next cell sized with it clears every gate and can OOM."""
    vramfit = importlib.import_module("mcgyvr.serving.vramfit")
    assert vramfit.allowance_mib({"arch": "qwen3next"}) >= 829


def test_a_bound_outside_its_verified_scope_is_expected() -> None:
    bounds = _bounds()
    assert bounds.classify("c_step_mib", arch="deepseek2", rig="srv2") == "BOUND"
    assert bounds.classify("c_step_mib", arch="deepseek2", rig="srv1") == "EXPECTED"
    assert bounds.classify("c_step_mib", arch="gemma4", rig="srv2") == "EXPECTED"


def test_a_parameter_whose_spread_is_over_one_percent_is_expected() -> None:
    """Unmapped Shmem runs 4-8% over geometry on srv1 (Q7); a started-early 7B
    varies its card by 616 MiB, 5% of srv2's (Q15)."""
    bounds = _bounds()
    assert (
        bounds.classify("unmapped_shmem_over_geometry", arch=None, rig="srv1")
        == "EXPECTED"
    )
    assert bounds.classify("vllm_early_start_card_spread", arch=None, rig="srv2") == (
        "EXPECTED"
    )


def test_an_observation_past_a_bound_is_a_deviation_that_demotes_it() -> None:
    bounds = _bounds()
    within = bounds.judge("scratch_mib", 825.0, arch="qwen3next", rig="srv2")
    past = bounds.judge("scratch_mib", 841.0, arch="qwen3next", rig="srv2")
    assert within is None
    assert past is not None and past.demotes, "a bound an observation beat is no bound"
