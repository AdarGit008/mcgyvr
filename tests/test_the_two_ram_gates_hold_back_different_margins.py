"""Two gates that fail differently hold back two different RAM margins.

``fit`` asks host RAM two questions in a row:

* the **mode** gate compares the **blob** — every page of it is read at load,
  which is why it predicts *wake* — and decides mmap against ``--load-mode
  none``;
* the **refusal** gate compares the **spilled experts** — the set that stays
  resident while the server serves, which is why it predicts *decode* — and
  decides whether the model runs on this host at all.

``records/measurements/ram-headroom-2026-09-09/`` swept both, three models
across both rigs, mapped, with a locked balloon holding the clearance where it
was wanted and the page cache dropped before every wake.

**The mode gate's margin is small** (``MODE_RAM_HEADROOM_GB``). Against the
blob, wake does not degrade across the clearances the sweep held above zero,
and decode throughput never moved at any clearance; below zero the cost lands
entirely on wake — a bounded, self-announcing, one-off cost on a rung that then
stays up.

**The refusal gate's margin is large** (``REFUSAL_RAM_HEADROOM_GB``). Against
the experts the sweep found a cliff and not a slope: flat down to a small
clearance, and further down a far longer wake, millions of major faults
and pages swapped out, and decode at a fraction of baseline. Three reasons keep
the margin large: the cliff's location between the sampled clearances is
unmeasured; the failure is *silent*, so the unit comes up, gate 7 is green and
every request is served off swap; and the margin is free on this fleet,
refusing nothing that would have run.

So the two gates get two numbers, and this file pins where each one sits by
walking a rig's memory across the threshold rather than by reading the
constants: what an operator gets is the arm, and the arm is the fact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, fit

WINDOW = 4096

GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)

#: srv1's own rung, and the model both sweeps were run on: a 12.304 GiB blob
#: that spills 8.950 GiB of experts at the 29 blocks a 6 GiB card leaves it.
MOE = ModelSpec(
    name="Qwen3.6-35B-A3B-UD-IQ3_XXS",
    vram_gb=0.0,
    ram_gb=0.0,
    disk_gb=0.0,
    geometry=GEOMETRY["Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf"],
)
BLOB_GB = 12.304
EXPERTS_GB = 8.950


def rig(*, ram_gb: float) -> Scan:
    """srv1's card and cores, varying only in memory — the sweep's own axis."""
    return Scan.of(
        host="srv1",
        vram_mib=6144,
        ram_gb=ram_gb,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )


def test_srv1_maps_the_blob_it_is_serving_unmapped_today() -> None:
    """The live case, and the only one on this fleet where the split changes an
    answer: 14.19 GiB of ``MemAvailable`` measured idle on srv1 against a
    12.304 GiB blob. At 2.0 held back that is 14.30 and the rung goes unmapped;
    at 0.5 it maps, which is what the measurement says it should do: at
    production ``vm.swappiness=60`` the trade is gigabytes of reclaimable
    memory for a few seconds of one-off wake on a rung that stays up.
    """
    assert fit(rig(ram_gb=14.19), MOE, ctx_per_slot=WINDOW).load_mode is None


def test_the_mode_gate_holds_back_half_a_gigabyte() -> None:
    """Where the mapping decision flips, walked from either side of it.

    0.5 GiB and not zero: the sweep does not vindicate a bare-blob rule. The
    clearance is measured against the blob and the process needs memory the
    blob does not account for — llama.cpp's own allocations, CUDA host-side
    buffers, container overhead — which is what deepseek's wake cost at
    +0.5 GiB (one sample) is most likely showing.
    """
    assert fit(rig(ram_gb=BLOB_GB + 0.6), MOE, ctx_per_slot=WINDOW).load_mode is None
    assert fit(rig(ram_gb=BLOB_GB + 0.4), MOE, ctx_per_slot=WINDOW).load_mode == "none"


def test_the_refusal_gate_still_holds_back_two() -> None:
    """The gate the sweep did *not* move, pinned so that shrinking one number
    cannot quietly shrink the other. 8.950 GiB of experts on a host with 10.9
    available is 0.05 GiB short of the margin and refused; 11.1 admits it.

    Half a gigabyte would have admitted both, and the arm it admits them onto
    is the one that fails at a fraction of decode without erroring.
    """
    refused = fit(rig(ram_gb=EXPERTS_GB + 1.95), MOE, ctx_per_slot=WINDOW)
    assert not refused.fits
    assert "No loading mode fits this host" in refused.why, refused.why
    admitted = fit(rig(ram_gb=EXPERTS_GB + 2.15), MOE, ctx_per_slot=WINDOW)
    assert admitted.fits
    assert admitted.load_mode == "none"


def test_the_two_gates_are_two_constants() -> None:
    """The split itself, so that a reader merging them back has to delete a
    test that says why they are apart. Imported inside the test so that a
    missing name fails this test alone and not the whole file at collection,
    leaving the arms above to show what they show.
    """
    from mcgyvr.serving import MODE_RAM_HEADROOM_GB, REFUSAL_RAM_HEADROOM_GB

    assert MODE_RAM_HEADROOM_GB == 0.5
    assert REFUSAL_RAM_HEADROOM_GB == 2.0
