#!/usr/bin/env python3
"""Q6 offline recompute — ``C`` with op offload on and off, deepseek/srv2.

Reads ``results-arms-q6-no-op-offload.json`` and recomputes ``C`` per arm as
``c_drift_report.py`` does (``C = measured_net − experts_on_card``), probed
at the same-day ncmoe 0 arm. Op offload cannot act at ncmoe 0 — no expert
lives on the host — so that one probe serves both sides.

Usage:
    cd records/measurements/measuring-gaps-2026-09-10
    uv run --no-sync python q6_report.py [results-json]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/home/adaramir/claude/mcgyvr/src")

from mcgyvr.serving import vramfit  # noqa: E402

SCR = Path(__file__).resolve().parent
MIB = 1024 * 1024
#: ``c_drift_report.py`` names this file under this checkout, where it is not;
#: the one scan on disk is in the fleet-id checkout.
GEOM_PATH = (
    Path("/home/adaramir/claude/mcgyvr-fleet-id/records/measurements")
    / "ram-headroom-2026-09-09"
    / "deepseek.geometry.json"
)


def mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def main() -> None:
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else SCR / "results-arms-q6-no-op-offload.json"
    geom = json.loads(GEOM_PATH.read_text())
    geom = geom[0] if isinstance(geom, list) else geom
    rows = json.loads(in_path.read_text())
    failed = [r["label"] for r in rows if r.get("failed")]
    rows = [r for r in rows if not r.get("failed")]

    groups: dict[tuple[int, bool], list[dict]] = defaultdict(list)
    for r in rows:
        r["C_mib"] = r["vram_steady_net_mib"] - vramfit.experts_on_card(geom, r["ncmoe"]) / MIB
        groups[(r["ncmoe"], r["op_offload"])].append(r)

    probe = mean([r["C_mib"] for r in groups.get((0, True), [])])
    table = []
    for (ncmoe, op), rs in sorted(groups.items()):
        c = mean([r["C_mib"] for r in rs])
        table.append({
            "ncmoe": ncmoe,
            "op_offload": op,
            "n": len(rs),
            "compute_buffer_mib": sorted({r["engine"]["cuda0_compute_mib"] for r in rs}),
            "graph_splits": sorted({r["engine"]["graph_splits"] for r in rs}),
            "steady_net_mib": sorted({r["vram_steady_net_mib"] for r in rs}),
            "after_work_net_mib": sorted({r["vram_after_work_net_mib"] for r in rs}),
            "C_mib": c,
            "C_drift_vs_n0_mib": None if probe is None or c is None else c - probe,
            "prefill_tok_s": mean([(r["prefill_tok_s"] or {}).get("mean") for r in rs]),
            "prefill_prompt_n": sorted({s["prompt_n"] for r in rs for s in (r["prefill_tok_s"] or {}).get("samples", [])}),
            "decode_tok_s": mean([(r["decode_warm_tok_s"] or {}).get("mean") for r in rs]),
        })

    report = {"geometry": str(GEOM_PATH), "C_probe_n0_mib": probe, "failed": failed, "groups": table}
    out_path = in_path.with_name(in_path.stem + "-report.json")
    out_path.write_text(json.dumps(report, indent=2) + "\n")

    print(f"C probe (ncmoe 0, same day) = {probe}")
    print(f"{'ncmoe':>5} {'op':>5} {'n':>2} {'compute':>10} {'C drift':>8} {'prefill':>8} {'decode':>7}  splits")
    for t in table:
        drift = t["C_drift_vs_n0_mib"]
        print(f"{t['ncmoe']:>5} {str(t['op_offload']):>5} {t['n']:>2} "
              f"{','.join(f'{x:.2f}' for x in t['compute_buffer_mib']):>10} "
              f"{'' if drift is None else f'{drift:+.2f}':>8} "
              f"{t['prefill_tok_s'] or 0:8.1f} {t['decode_tok_s'] or 0:7.2f}  {t['graph_splits']}")
    if failed:
        print(f"FAILED arms: {failed}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
