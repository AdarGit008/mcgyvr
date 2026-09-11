#!/usr/bin/env python3
"""Q4 offline recompute — the ``C`` spread across deepseek/srv2 ncmoe 0/13/26.

Reads the measured rows ``c_drift_deepseek.py`` left in
``results-arms-q4-c-drift.json`` and recomputes ``C`` per arm exactly as
``headroom.py`` does: ``C = measured_net − experts_on_card(geometry, ncmoe)``.
The probe is the lowest placement (ncmoe 0) — the one a floor search reaches
first — and every other arm is predicted from it via ``vramfit.predict``.

The answer is the **C spread** across the 0→26 span:
  * ~0 MiB        → ``C`` holds per-arch (deepseek's KV-dominated C does not drift)
  * ~+30 MiB      → the per-block drift is universal (+38 MiB / 33 blocks ≈
                     +1.15 MiB/block, ~+30 MiB over 26 blocks)

Usage:
    cd records/measurements/measuring-gaps-2026-09-10
    uv run --no-sync python c_drift_report.py [results-json]   # default: results-arms-q4-c-drift.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from mcgyvr.serving import vramfit  # noqa: E402

SCR = Path(__file__).resolve().parent
MIB = 1024 * 1024

#: The scan in this tree, so the report reruns from any clone of it.
GEOM_PATH = SCR.parent / "ram-headroom-2026-09-09" / "deepseek.geometry.json"
SPAN_BLOCKS = 26  # deepseek placeable_blocks = [1..26]; ncmoe 0 -> 26 moves 25 of 26


def load_geometry(path: Path) -> dict:
    g = json.loads(path.read_text())
    return g[0] if isinstance(g, list) else g


def main() -> None:
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (SCR / "results-arms-q4-c-drift.json")
    geom = load_geometry(GEOM_PATH)
    rows = [r for r in json.loads(in_path.read_text()) if not r.get("failed")]

    arms = []
    for r in rows:
        ncmoe = int(r.get("ncmoe", 0))
        net = r.get("vram_steady_net_mib")
        if net is None:
            idle_used = {"srv1": 5744, "srv2": 11912}[r["host"]] - r["vram_idle_free_mib"]
            net = r["vram_steady_used_mib"] - idle_used
        experts_mib = vramfit.experts_on_card(geom, ncmoe) / MIB
        arms.append(
            {
                "label": r["label"],
                "ncmoe": ncmoe,
                "measured_net_mib": net,
                "experts_mib": experts_mib,
                "C_mib": net - experts_mib,
            }
        )

    if not arms:
        print(f"no rows in {in_path}")
        return

    probe = min(arms, key=lambda a: a["ncmoe"])
    c_ref = int(round(probe["C_mib"] * MIB))

    for a in arms:
        predicted = vramfit.predict(geom, a["ncmoe"], c_ref) / MIB
        a["predicted_mib"] = predicted
        a["residual_mib"] = a["measured_net_mib"] - predicted

    c_vals = [a["C_mib"] for a in arms]
    spread = max(c_vals) - min(c_vals)
    per_block = spread / SPAN_BLOCKS

    report = {
        "geometry": str(GEOM_PATH),
        "probe_arm": probe["label"],
        "probe_ncmoe": probe["ncmoe"],
        "C_probe_mib": probe["C_mib"],
        "C_min_mib": min(c_vals),
        "C_max_mib": max(c_vals),
        "C_spread_mib": spread,
        "per_block_drift_mib": per_block,
        "span_blocks": SPAN_BLOCKS,
        "arms": arms,
    }
    out_path = in_path.with_name(in_path.stem + "-report.json")
    out_path.write_text(json.dumps(report, indent=2) + "\n")

    print(f"\n=== deepseek-coder-v2-16b / srv2  (ncmoe 0 -> 26)")
    print(f"    C probed at ncmoe {probe['ncmoe']} = {probe['C_mib']:.2f} MiB;"
          f" C spans {min(c_vals):.2f}..{max(c_vals):.2f} ({spread:.2f} MiB)")
    for a in sorted(arms, key=lambda a: (a["ncmoe"], a["label"])):
        print(f"    ncmoe {a['ncmoe']:>2}  {a['label']:<22} "
              f"C {a['C_mib']:8.2f}  predicted {a['predicted_mib']:8.2f}  "
              f"residual {a['residual_mib']:+8.2f} MiB")
    print(f"\nC SPREAD over {SPAN_BLOCKS}-block span: {spread:+.2f} MiB"
          f"  (per-block {per_block:+.2f} MiB)")
    if abs(spread) < 1.0:
        print("=> C holds at ~0: per-arch (deepseek's KV-dominated C does not drift)")
    else:
        print("=> C drifts: the per-block drift is universal")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
