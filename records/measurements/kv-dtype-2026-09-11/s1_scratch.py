#!/usr/bin/env python3
"""S1: the qwen35moe scratch+context at -ub 512, with a -ub 256 control.

One cold start per -ub, the live srv1 Qwen3.6 placement (--n-cpu-moe 30,
--parallel 2, -c 16384, llamacpp:b10644-L3), --verbose so the allocator prints
its named device buffers. The quantity recorded is what
``SCRATCH_AND_CONTEXT_MIB`` / ``MEASURED_SCRATCH_MIB`` bound:

    scratch_context_mib = compute buffer + residue
    residue_mib          = vram_net - (cuda_model + cuda_kv + cuda_rs + cuda_compute)
    vram_net_mib         = steady card used - idle card used

so scratch_context = steady_net - (model + kv + rs) — the compute buffer plus
everything the engine allocates that it never names (CUDA context, scratch).
The method is ``measuring-gaps-2026-09-10`` Q3 (``scratch_curve.py`` +
``scratch_report.py``), which is the same quantity the 2026-09-05
context-decomposition bounded at 768.

    uv run --no-sync python s1_scratch.py
"""

from __future__ import annotations

import json
import re
import sys
import time

import rig

HOST = "srv1"
OUT = rig.SCR / "results-s1-scratch.json"
LOGS = rig.SCR / "logs"
LOGS.mkdir(exist_ok=True)

PATS = {
    "cuda_model": r"load_tensors:\s+CUDA0 model buffer size =\s+([\d.]+)",
    "cuda_kv": r"llama_kv_cache:\s+CUDA0 KV buffer size =\s+([\d.]+)",
    "cuda_rs": r"llama_memory_recurrent:\s+CUDA0 RS buffer size =\s+([\d.]+)",
    "cuda_compute": r"sched_reserve:\s+CUDA0 compute buffer size =\s+([\d.]+)",
}
COMPUTE = re.compile(r"sched_reserve:\s+CUDA0 compute buffer size =\s+([\d.]+)")


def parse_buffers(log: str) -> dict[str, float | None]:
    idx = [m.start() for m in re.finditer(r"load_tensors:.*model buffer size", log)]
    real = log[idx[len(idx) // 2]:] if len(idx) > 1 else log
    out: dict[str, float | None] = {}
    for k, pat in PATS.items():
        m = re.findall(pat, real)
        if k == "cuda_kv":
            out[k] = sum(float(x) for x in m) if m else None
        else:
            out[k] = float(m[-1]) if m else None
    return out


def arm(ub: int) -> dict:
    label = f"s1-qwen36-ub{ub}"
    compose = rig.SCR / f"compose.srv1-s1-ub{ub}.yml"
    rig.teardown(HOST)
    rig.drop_caches(HOST)
    idle = rig.gpu(HOST)
    rig.note_up(HOST, compose)
    proc, seconds, envelope = rig.door("up", HOST, compose, f"{label}-up")
    if proc.returncode != 0:
        log = rig.engine_log(HOST, "mcgyvr-srv1-Qwen3.6-35B-A3B-UD-IQ3_XXS-8080", label)
        return {"label": label, "ub": ub, "failed": f"door rc={proc.returncode}",
                "log": log[-1500:]}
    log = rig.engine_log(HOST, "mcgyvr-srv1-Qwen3.6-35B-A3B-UD-IQ3_XXS-8080", label)
    after = rig.gpu(HOST)
    buffers = parse_buffers(log)
    net = after["used"] - idle["used"]
    if any(buffers.get(k) is None for k in ("cuda_model", "cuda_kv", "cuda_rs", "cuda_compute")):
        raise SystemExit(f"{label}: a required device buffer is missing from the log")
    residue = net - (buffers["cuda_model"] + buffers["cuda_kv"] + buffers["cuda_rs"] + buffers["cuda_compute"])
    scratch_context = buffers["cuda_compute"] + residue
    row = {"label": label, "ub": ub, "idle_used_mib": idle["used"], "steady_used_mib": after["used"],
           "vram_net_mib": round(net, 2), "buffers": {k: round(v, 2) for k, v in buffers.items()},
           "residue_mib": round(residue, 2), "scratch_context_mib": round(scratch_context, 2),
           "door_s": round(seconds, 1)}
    rig.teardown(HOST)
    return row


def main() -> None:
    rows = json.loads(OUT.read_text()) if OUT.exists() else []
    done = {r["label"] for r in rows if not r.get("failed")}
    for ub in (256, 512):
        label = f"s1-qwen36-ub{ub}"
        if label in done:
            continue
        try:
            row = arm(ub)
        except SystemExit as exc:
            row = {"label": label, "ub": ub, "failed": str(exc)}
        rows.append(row)
        OUT.write_text(json.dumps(rows, indent=2))
        print(json.dumps(row))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
