#!/usr/bin/env python3
"""The --n-cpu-moe floor, from the geometry and the card that was just read.

DERIVED, THEN WALKED DOWN TO — never trusted as a measurement. One allowance
remains in the arithmetic (compute buffer plus the allocation the engine never
names), so this is a prediction. The refusal is the measurement: run one cell
below the floor on purpose and it names the true edge, and retry any refusal
three times before believing it, because a launch near the memory edge is a
1-in-3 coin flip.

IT REFUSES RATHER THAN GUESSING. A checkpoint that declares a sliding window
without the per-layer pattern does not say which layers slide, and the split is
not derivable from the header. Inventing one is how the constants this module
replaced came to be written, so an unsizable cache stops the run here — where
it costs nothing — instead of at load, where it costs the rig night.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcgyvr.serving import vramfit
from mcgyvr.serving.gatelib import door_required, export, need, refuse


def main() -> int:
    door_required("the placement")
    # The allowance is vramfit's, not this script's: the bench gate derives the
    # same floor from the same number, and two copies that drifted would have
    # the door and the gate disagree about one card.
    scratch_mib = vramfit.SCRATCH_AND_CONTEXT_MIB

    geometry = json.loads(Path(need("RUN_GEOMETRY_JSON")).read_text(encoding="utf-8"))
    scan = json.loads(Path(need("RUN_SCAN_JSON")).read_text(encoding="utf-8"))
    free_mib = int(scan["gpu"]["free_mib"])
    slots = int(need("RUN_PARALLEL"))
    # `-c` is the TOTAL across slots, not the per-slot window: measured
    # 2026-09-05, -c 8192 gives the same cache at -np 8, -np 4 and -np 1.
    n_ctx = int(need("RUN_CTX_PER_SLOT")) * slots
    n_ubatch = int(need("RUN_UBATCH"))

    placeable = list(geometry.get("placeable_blocks") or [])
    if not placeable:
        placement = {
            "derived": True,
            "dense": True,
            "why": "no expert tensors: nothing for --n-cpu-moe to move",
            "floor_n_cpu_moe": 0,
        }
    else:
        try:
            kv = vramfit.kv_bytes(geometry, n_ctx, n_seq_max=slots, n_ubatch=n_ubatch)
            rs = vramfit.rs_bytes(geometry, n_seq_max=slots)
        except ValueError as error:
            refuse(
                f"the cache cannot be sized for {need('RUN_MODEL')}: {error}. "
                "Nothing is placed from an invented split"
            )
        constant = (
            int(geometry.get("bytes_nonexpert") or 0)
            + kv["total"]
            + rs["total"]
            + scratch_mib * 1024**2
        )
        floor_n = vramfit.floor(geometry, free_mib * 1024**2, constant)
        if floor_n is None:
            refuse(
                f"{need('RUN_MODEL')} does not fit {need('RUN_HOST')}'s card "
                f"({free_mib} MiB free) even with every expert block off it: "
                f"the non-expert weights, cache and scratch alone want "
                f"{constant / 1024**2:.0f} MiB. This is the CARD being too "
                "small, not the config being wrong"
            )
        on_card = vramfit.experts_on_card(geometry, floor_n)
        placement = {
            "derived": True,
            "dense": False,
            "floor_n_cpu_moe": floor_n,
            "n_placeable": len(placeable),
            "blocks_on_card": len([b for b in placeable if b >= floor_n]),
            "kv_mib": round(kv["total"] / 1024**2, 1),
            "kv_swa_mib": round(kv["swa"] / 1024**2, 1),
            "n_ctx_seq": kv["n_ctx_seq"],
            "state_mib": round(rs["total"] / 1024**2, 1),
            "nonexpert_mib": round(
                int(geometry.get("bytes_nonexpert") or 0) / 1024**2, 1
            ),
            "scratch_allowance_mib": scratch_mib,
            "constant_mib": round(constant / 1024**2, 1),
            "experts_on_card_mib": round(on_card / 1024**2, 1),
            "predicted_card_mib": round((constant + on_card) / 1024**2, 1),
            "card_free_mib": free_mib,
        }
    placement.update(
        host=need("RUN_HOST"),
        model=need("RUN_MODEL"),
        run_id=need("RUN_ID"),
        n_ctx_total=n_ctx,
        parallel=slots,
        n_ubatch=n_ubatch,
    )

    out = Path(need("RUN_OUT_DIR")) / "placement.json"
    out.write_text(
        json.dumps(placement, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    export("RUN_PLACEMENT_JSON", out)
    if placement.get("dense"):
        print("data-30-placement: dense checkpoint, nothing to place")
    else:
        print(
            f"data-30-placement: floor --n-cpu-moe "
            f"{placement['floor_n_cpu_moe']} of {placement['n_placeable']} "
            f"placeable, predicting {placement['predicted_card_mib']:.0f} of "
            f"{free_mib} MiB free (derived — walk down to it)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
