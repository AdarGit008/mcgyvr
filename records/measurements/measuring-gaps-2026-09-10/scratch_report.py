#!/usr/bin/env python3
"""Q3 offline recompute: named device buffers + residue vs the 768 MiB bound.

Reuses the parse-logs.py PATS (records/evidence/2026-09-05-context-decomposition)
to pull every named buffer out of each captured logs/<label>.log, then computes:

    residue_mib        = vram_steady_net_mib - (cuda_model + cuda_kv + cuda_rs + cuda_compute)
    scratch_context_mib = cuda_compute + residue_mib

`residue` is the allocation the engine never names; `scratch_context` is the
compute buffer plus that residue — exactly what `SCRATCH_AND_CONTEXT_MIB = 768`
bounds. `output`, `host_compute` and `cpu_model` are CUDA_HOST/CPU buffers (host
RAM, not device VRAM), so they are *not* subtracted from the card figure.

Usage:
    uv run --no-sync python scratch_report.py [results-json]     # default results-arms-q3-scratch.json
    MCG_LOGS=/tmp/logs MCG_OUT=/tmp/report.json uv run --no-sync python scratch_report.py /tmp/results.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/adaramir/claude/mcgyvr/src")

from mcgyvr.serving import vramfit  # noqa: E402  (SCRATCH_AND_CONTEXT_MIB)

SCR = Path(__file__).resolve().parent
LOGS = Path(os.environ.get("MCG_LOGS", str(SCR / "logs")))
OUT = Path(os.environ.get("MCG_OUT", str(SCR / "results-q3-scratch-report.json")))
BOUND = vramfit.SCRATCH_AND_CONTEXT_MIB  # 768

# Identical to parse-logs.py:6-16. Device buffers are the `CUDA0` ones; the
# rest are CUDA_HOST / CPU_Mapped (host RAM) and are extracted for the record
# but not subtracted from the card.
PATS = {
    "cuda_model":  r"load_tensors:\s+CUDA0 model buffer size =\s+([\d.]+)",
    "cpu_model":   r"load_tensors:\s+CPU_Mapped model buffer size =\s+([\d.]+)",
    "cuda_kv":     r"llama_kv_cache:\s+CUDA0 KV buffer size =\s+([\d.]+)",
    "cuda_compute": r"sched_reserve:\s+CUDA0 compute buffer size =\s+([\d.]+)",
    "host_compute": r"sched_reserve:\s+CUDA_Host compute buffer size =\s+([\d.]+)",
    "output":      r"llama_context:\s+CUDA_Host\s+output buffer size =\s+([\d.]+)",
    "cuda_rs":     r"llama_memory_recurrent:\s+CUDA0 RS buffer size =\s+([\d.]+)",
}
DEVICE_KEYS = ("cuda_model", "cuda_kv", "cuda_rs", "cuda_compute")


def parse_log(path: Path) -> dict:
    txt = path.read_text(errors="replace")
    # The loader runs twice (a fit pass then the real one). Split on the LAST
    # `load_tensors … model buffer size` occurrence and keep what follows, so the
    # fit pass's zeroed compute/KV lines never leak into the residue.
    idx = [m.start() for m in re.finditer(r"load_tensors:.*model buffer size", txt)]
    real = txt[idx[len(idx) // 2]:] if len(idx) > 1 else txt
    out: dict = {}
    for k, pat in PATS.items():
        m = re.findall(pat, real)
        if k == "cuda_kv":
            # An SWA model creates TWO device KV caches; summing is the only
            # correct reduction.
            out[k] = sum(float(x) for x in m) if m else None
            out["n_kv_caches"] = len(m)
        else:
            out[k] = float(m[-1]) if m else None
    return out


def device_sum(buffers: dict) -> float | None:
    if any(buffers.get(k) is None for k in ("cuda_model", "cuda_kv", "cuda_compute")):
        return None  # a required device buffer is missing from the log
    return sum(buffers.get(k) or 0.0 for k in DEVICE_KEYS)


def main() -> None:
    results_path = Path(sys.argv[1]) if len(sys.argv) > 1 else SCR / "results-arms-q3-scratch.json"
    rows = json.loads(results_path.read_text())

    cells: list[dict] = []
    for row in rows:
        if row.get("failed") or row.get("vram_steady_net_mib") is None:
            continue
        label = row["label"]
        log_path = LOGS / f"{label}.log"
        if not log_path.exists():
            cells.append({**row, "error": f"missing log {log_path.name}"})
            continue
        buffers = parse_log(log_path)
        dev = device_sum(buffers)
        net = float(row["vram_steady_net_mib"])
        residue = (net - dev) if dev is not None else None
        compute = buffers.get("cuda_compute")
        scratch_context = (compute + residue) if (compute is not None and residue is not None) else None
        cells.append({
            "label": label,
            "host": row["host"],
            "arch": row["arch"],
            "ub": row["ub"],
            "vram_steady_net_mib": net,
            "buffers": buffers,
            "residue_mib": residue,
            "scratch_context_mib": scratch_context,
        })

    # per-(arch, ub) means across the two reps
    grouped: dict[tuple[str, int], list[dict]] = {}
    for c in cells:
        if c.get("scratch_context_mib") is not None:
            grouped.setdefault((c["arch"], c["ub"]), []).append(c)

    table: list[dict] = []
    for (arch, ub), grp in sorted(grouped.items()):
        comp = sum(c["buffers"]["cuda_compute"] for c in grp) / len(grp)
        res = sum(c["residue_mib"] for c in grp) / len(grp)
        sc = sum(c["scratch_context_mib"] for c in grp) / len(grp)
        table.append({
            "arch": arch,
            "ub": ub,
            "n": len(grp),
            "compute_buffer_mib": round(comp, 2),
            "residue_mib": round(res, 2),
            "scratch_context_mib": round(sc, 2),
            "exceeds_768": round(sc, 2) > BOUND,
        })

    # -ub growth on the cheap arch
    ling = [t for t in table if t["arch"] == "bailingmoe3"]
    ling.sort(key=lambda t: t["ub"])
    growth = {}
    for t in ling:
        growth[str(t["ub"])] = t["scratch_context_mib"]
    if 256 in growth and 1024 in growth:
        growth["delta_256_to_1024"] = round(growth["1024"] - growth["256"], 2)

    # which of the three NEW archs clears or exceeds the bound
    arch_summary = {}
    for arch in sorted({t["arch"] for t in table}):
        worst = max(t["scratch_context_mib"] for t in table if t["arch"] == arch)
        arch_summary[arch] = {
            "max_scratch_context_mib": round(worst, 2),
            "exceeds_768": round(worst, 2) > BOUND,
        }

    report = {
        "bound_mib": BOUND,
        "cells": table,
        "ub_growth_bailingmoe3": growth,
        "arch_summary": arch_summary,
    }
    OUT.write_text(json.dumps(report, indent=2))

    print(f"\n=== compute-scratch / activation curve vs {BOUND} MiB bound")
    print(f"{'arch':<14} {'ub':>5} {'n':>2} {'compute':>9} {'residue':>9} {'scratch+ctx':>12}  exceeds")
    for t in table:
        mark = "  YES" if t["exceeds_768"] else ""
        print(f"{t['arch']:<14} {t['ub']:>5} {t['n']:>2} "
              f"{t['compute_buffer_mib']:>9.2f} {t['residue_mib']:>9.2f} "
              f"{t['scratch_context_mib']:>12.2f}{mark}")
    print("\n-ub growth on bailingmoe3:", growth)
    for arch, s in arch_summary.items():
        print(f"  {arch:<14} worst scratch+ctx {s['max_scratch_context_mib']:.2f} MiB -> "
              f"{'EXCEEDS' if s['exceeds_768'] else 'clears'} {BOUND}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
