"""``C`` steps once an expert block is on the host, and holds after that.

``C`` is not the same at every placement. On srv2, deepseek-coder-v2-16b
(``records/measurements/measuring-gaps-2026-09-10/`` Q4 and Q6), ``C`` reads
lower at ncmoe 0 than at 13 and 26, which agree. The engine's own ``CUDA0
compute buffer size`` accounts for the difference: it roughly doubles as soon as
one expert is on the host, and is flat after. llama.cpp's op offload copies a
host-stored expert tensor into the device compute buffer for a large batch; with
``--no-op-offload`` the step is gone, and that flag is banned
(``okf/config/llama.cpp.md``).

The invariance tests in ``tests/test_serving_vramfit.py`` (KAT and nemotron)
hold because every one of their placements keeps experts on the host. A probe
reads ``C`` for the placements on its own side of that step, and a probe taken
with every expert on the card under-states every placement that offloads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving import vramfit

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "records" / "measurements" / "measuring-gaps-2026-09-10"
GEOMETRY = REPO / "records" / "measurements" / "ram-headroom-2026-09-09"
MIB = 1024**2


def _deepseek() -> dict[str, Any]:
    loaded = json.loads((GEOMETRY / "deepseek.geometry.json").read_text())
    geometry: dict[str, Any] = loaded[0] if isinstance(loaded, list) else loaded
    return geometry


def _q6_rows() -> list[dict[str, Any]]:
    rows = json.loads((RUN / "results-arms-q6-no-op-offload.json").read_text())
    return [row for row in rows if not row.get("failed")]


def _one(rows: list[dict[str, Any]], ncmoe: int, op_offload: bool) -> dict[str, float]:
    """The arm's ``C`` and compute buffer, identical across its two cold starts."""
    geometry = _deepseek()
    picked = [r for r in rows if r["ncmoe"] == ncmoe and r["op_offload"] is op_offload]
    assert len(picked) == 2, (ncmoe, op_offload, len(picked))
    constants = {
        r["vram_steady_net_mib"] - vramfit.experts_on_card(geometry, ncmoe) / MIB
        for r in picked
    }
    computes = {r["engine"]["cuda0_compute_mib"] for r in picked}
    assert len(constants) == 1 and len(computes) == 1, (constants, computes)
    return {"C": constants.pop(), "compute": computes.pop()}


def test_the_constant_steps_by_the_compute_buffer_when_an_expert_reaches_the_host() -> (
    None
):
    rows = _q6_rows()
    none_on_host = _one(rows, 0, op_offload=True)
    some_on_host = _one(rows, 13, op_offload=True)
    more_on_host = _one(rows, 26, op_offload=True)

    step = some_on_host["C"] - none_on_host["C"]
    buffer_step = some_on_host["compute"] - none_on_host["compute"]
    assert step == pytest.approx(74.0, abs=0.5)
    # The step IS the compute buffer's: 75.38 MiB of it, inside nvidia-smi's
    # whole-MiB reading of the card.
    assert step == pytest.approx(buffer_step, abs=2.0)
    # And it happens once: thirteen more blocks on the host move nothing.
    assert more_on_host["C"] == pytest.approx(some_on_host["C"], abs=1.0)
    assert more_on_host["compute"] == some_on_host["compute"]


def test_without_op_offload_the_constant_does_not_step() -> None:
    rows = _q6_rows()
    probe = _one(rows, 0, op_offload=True)
    for ncmoe in (13, 26):
        off = _one(rows, ncmoe, op_offload=False)
        assert off["compute"] == probe["compute"], ncmoe
        assert off["C"] == pytest.approx(probe["C"], abs=1.0), ncmoe


def test_vramfit_no_longer_says_one_probe_at_any_placement_fixes_the_constant() -> None:
    """The docstring is the rule a caller probes by, so it has to be the true one."""
    module = vramfit.__doc__ or ""
    probe = vramfit.constant_from_probe.__doc__ or ""
    assert "does not move with" not in module
    assert "at any placement" not in module
    assert "op offload" in module
    assert "on the host" in probe, (
        "constant_from_probe must say a probe is taken with an expert on the host"
    )
