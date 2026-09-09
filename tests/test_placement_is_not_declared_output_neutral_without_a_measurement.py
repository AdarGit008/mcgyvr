"""The repo asserted in code that moving experts between CPU and GPU cannot change
a token. On 2026-09-02 it was tested, and it is false: 9 of 257 verdicts moved
between ``ncmoe=0`` and ``ncmoe=99`` on one build, against a 1.47pp own-null
bound. The fiat is retired (ADR-0041); the tests below hold the retirement and
keep the measurement's xfail.

Until 2026-09-03 ``tools/bench/serving/fingerprint.py`` put ``n_gpu_layers``,
``n_cpu_moe``, ``threads`` and ``mmap`` in the operational key set, with the
reasoning:

    Placement and parallelism: WHERE a tensor is computed, not WHAT is emitted.
    ... None of them alters the token distribution, so none belongs in the
    semantic pin -- and putting them there would declare two cells of one model
    at two offload settings "incomparable on output", which is exactly the
    comparison this campaign exists to make.

That fiat is load-bearing. The 2026-09-01 finding that srv2's ``--n-cpu-moe``
floor is 6 rather than 24-99, worth ~2.4x, is a claim that a placement change
bought speed and cost nothing — and "cost nothing" is the untested half.

The same tree records backend numerics alone moving a greedy delta by 2.6pp, and
records an ollama-bundled server silently running on CPU with ``-ngl`` ignored.
So the assumption is not obviously safe, and the instrument to test it already
exists: ``tools/breadth/measure.py`` against each endpoint, paired through
``tools/bench/null.py``, which separates sampler drift (different bytes) from
acceptance drift (same bytes, different verdict).

Ling-3.0-tiny is the subject because it fits entirely on the 6 GB card at
``ncmoe=0`` and survived a 60-minute soak at ``ncmoe=99`` — the one MoE cell on
srv1 that is safe to drive.
"""

from __future__ import annotations

import importlib.util
import json
from typing import Any

import pytest

from tests.sweeprows import REPO, RUN

FINGERPRINT = REPO / "tools" / "bench" / "serving" / "fingerprint.py"
PLACEMENT = RUN / "placement-null.json"


def _fingerprint() -> Any:
    spec = importlib.util.spec_from_file_location("serving_fingerprint", FINGERPRINT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_fiat_is_retired_and_placement_is_semantic() -> None:
    """Measured 2026-09-02: 9 of 257 cells changed verdict between ``ncmoe=0``
    and ``ncmoe=99`` on one build, against a 1.47pp own-null bound. So
    ``n_cpu_moe`` changes what is emitted, and the declaration that placement
    cannot is gone from the code — for all four keys it covered, because the
    argument was one argument and it is false for the one value measured. A
    placement key is semantic until a placement null on that build shows it
    neutral (ADR-0041)."""
    source = FINGERPRINT.read_text(encoding="utf-8")
    assert "None of them alters the token" not in source, (
        "fingerprint.py still declares placement output-neutral; the "
        "2026-09-02 measurement says otherwise"
    )
    fp = _fingerprint()
    for key in ("n_cpu_moe", "n_gpu_layers", "threads", "mmap"):
        assert key in fp.SEMANTIC, f"{key} is not semantic"
        assert key not in fp.OPERATIONAL, f"{key} is still operational"
    resident = fp.fingerprint({"model": "ling-3.0-tiny", "n_cpu_moe": 0})
    offloaded = fp.fingerprint({"model": "ling-3.0-tiny", "n_cpu_moe": 99})
    assert (
        resident["serving_semantic_sha256"] != offloaded["serving_semantic_sha256"]
    ), "two placements of one model still share a semantic digest"


def test_the_llamacpp_backend_no_longer_calls_the_gap_a_classification() -> None:
    """The engine cannot read ``-ngl``/``--n-cpu-moe``/``-t`` from ``/props``,
    so they stay ``uncovered_by_digest`` — a reading gap, stated as one, not
    a claim that the shared classifier lacks them."""
    source = (
        REPO / "tools" / "bench" / "serving" / "backends" / "llamacpp.py"
    ).read_text(encoding="utf-8")
    assert "none is in the shared fingerprint's SEMANTIC set" not in source
    assert (
        "none of them is in the fingerprint's SEMANTIC or OPERATIONAL set" not in source
    )
    assert "ADR-0041" in source


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-09-02: measured (records/evidence/2026-09-02-srv1-kernel-arms/"
        "placement-null.json): 9 of 257 cells changed verdict between ncmoe=0 "
        "and ncmoe=99 on L3 / Ling-3.0-tiny, 3.50pp against the arm's own 1.47pp "
        "null bound (0 self-null flips). Placement is not output-neutral at this "
        "bound; fingerprint.py's fiat is falsified, not owed"
    ),
)
def test_two_offload_settings_of_one_model_are_shown_to_agree() -> None:
    result = json.loads(PLACEMENT.read_text(encoding="utf-8"))
    assert result["model"] and result["tier"], "the null names no model or tier"
    assert {result["run_a"]["n_cpu_moe"], result["run_b"]["n_cpu_moe"]} == {0, 99}, (
        "the pair must be the same checkpoint fully resident and fully offloaded"
    )
    assert result["run_a"]["serving_build"] == result["run_b"]["serving_build"], (
        "two builds and two placements is two variables"
    )
    assert result["flips"] == 0, (
        f"{result['flips']} cell(s) changed verdict when the experts moved between "
        "CPU and GPU. fingerprint.py declares that impossible, and the ncmoe "
        "floor programme is built on it."
    )
    assert result["acceptance_drift"] == 0, (
        "identical bytes scored differently — the gate is unstable, and no "
        "placement conclusion can be drawn through it"
    )


def test_the_bound_this_is_judged_against_was_measured_on_this_build() -> None:
    """``tools/bench/reproducibility.json`` keys a bound on model, tier,
    gate_rungs, serving_build and cells. The patched image is a new
    ``serving_build``, so no committed bound covers it — the run must measure its
    own null first and say so, rather than borrowing 1.47pp measured elsewhere."""
    result = json.loads(PLACEMENT.read_text(encoding="utf-8"))
    declared = json.loads(
        (REPO / "tools" / "bench" / "reproducibility.json").read_text(encoding="utf-8")
    )
    builds = {b["serving_build"] for b in declared["bounds"]}
    run_build = result["run_a"]["serving_build"]
    bound_build = result["bound"]["serving_build"]
    assert bound_build == run_build, (
        f"the null is judged against a bound measured on {bound_build!r} while "
        f"the run used {run_build!r}. Committed bounds cover {sorted(builds)}."
    )
    assert result["bound"]["cells"] == result["cells"], (
        "a rate keyed on everything but its own denominator transfers to subsets "
        "it never saw"
    )
