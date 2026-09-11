"""One constant priced two gates that fail differently. It is two constants now.

``fit`` asks host RAM two questions in a row and, until 2026-09-09, held the
same 2.0 GiB back from both:

* the **mode** gate compares the **blob** — every page of it is read at load,
  which is why it predicts *wake* — and decides mmap against ``--load-mode
  none``;
* the **refusal** gate compares the **spilled experts** — the set that stays
  resident while the server serves, which is why it predicts *decode* — and
  decides whether the model runs on this host at all.

``records/measurements/ram-headroom-2026-09-09/`` swept both, three models
across both rigs, mapped, with a locked balloon holding the clearance where it
was wanted and the page cache dropped before every wake.

**The mode gate's margin was four times too large.** Nothing degrades between
+2.0 and +0.5 GiB of clearance against the blob — 140.8 s against 139.9 s on
srv1's Qwen3.6, 102.9 s against 103.7 s on srv2's 80B — and across all nine arms
decode throughput never moved at any clearance. Below zero the cost is real,
reproducible and lands entirely on wake: +19% (n=3, alternating), +36% on
deepseek, +5% on the 80B. A bounded, self-announcing, one-off cost on a rung
that then stays up.

**The refusal gate's margin stays where it is.** Swept the same day against the
experts rather than the blob it is a cliff and not a slope: flat on every axis
to +0.55 GiB, and one GiB further down a 385 s wake, 2.3 M major faults, 2.2 M
pages swapped out and decode at 32% of baseline. Three reasons to keep 2.0 that
are measured rather than inherited — the cliff's location is unmeasured, it
being somewhere in the 1.5 GiB nobody sampled between +0.55 and -0.97; the
failure is *silent*, so the unit comes up, gate 7 is green and every request is
served off swap; and the margin is free on this fleet, admitting Qwen3.6's
9.2 GiB of experts and KAT's 11.8 alike, refusing nothing that would have run.

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
    at 0.5 it maps, which is what the measurement says it should do — unmapped
    132.9 s against mapped 139.6 s over three alternating pairs at production
    ``vm.swappiness=60``, so the trade is 8.4 GiB of reclaimable memory for
    6.7 s of one-off wake on a rung that stays up.
    """
    assert fit(rig(ram_gb=14.19), MOE, ctx_per_slot=WINDOW).load_mode is None


def test_the_mode_gate_holds_back_half_a_gigabyte() -> None:
    """Where the mapping decision flips, walked from either side of it.

    0.5 GiB and not zero: the sweep does not vindicate a bare-blob rule. The
    clearance is measured against the blob and the process needs memory the
    blob does not account for — llama.cpp's own allocations, CUDA host-side
    buffers, container overhead — which is what deepseek paying +10.7% at
    +0.5 GiB (n=1) is most likely showing.
    """
    assert fit(rig(ram_gb=BLOB_GB + 0.6), MOE, ctx_per_slot=WINDOW).load_mode is None
    assert fit(rig(ram_gb=BLOB_GB + 0.4), MOE, ctx_per_slot=WINDOW).load_mode == "none"


def test_the_refusal_gate_still_holds_back_two() -> None:
    """The gate the sweep did *not* move, pinned so that shrinking one number
    cannot quietly shrink the other. 8.950 GiB of experts on a host with 10.9
    available is 0.05 GiB short of the margin and refused; 11.1 admits it.

    Half a gigabyte would have admitted both, and the arm it admits them onto
    is the one that fails at 32% of decode without erroring.
    """
    refused = fit(rig(ram_gb=EXPERTS_GB + 1.95), MOE, ctx_per_slot=WINDOW)
    assert not refused.fits
    assert "No loading mode fits this host" in refused.why, refused.why
    admitted = fit(rig(ram_gb=EXPERTS_GB + 2.15), MOE, ctx_per_slot=WINDOW)
    assert admitted.fits
    assert admitted.load_mode == "none"


def test_the_two_gates_are_two_constants() -> None:
    """The split itself, so that a later reader merging them back has to delete
    a test that says why they are apart. Imported inside the test because a
    module-level import of a name that does not exist yet fails a whole file at
    collection, and the RED that matters here is the one the arms above show.
    """
    from mcgyvr.serving import MODE_RAM_HEADROOM_GB, REFUSAL_RAM_HEADROOM_GB

    assert MODE_RAM_HEADROOM_GB == 0.5
    assert REFUSAL_RAM_HEADROOM_GB == 2.0
