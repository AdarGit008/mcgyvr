#!/usr/bin/env python3
"""Project the raw rows into the records the test reads, and derive the summaries.

    derive.py

Reads `raw-srv1.json`, `raw-srv2.json`, `raw-srv2-pinned.json` and `proposal.json`,
plus the four bench run directories. Writes:

- `results-decode.json`, `tolerances.json`
- `results-wake.json`, `wake.json`
- `results-host-ram.json`, `host-ram.json`
- `results-shmem.json`
- `results-fp8.json`, `fp8-quality.json`
- `results-pinned-kv.json`
- `results-headroom.json`

Nothing dispatches and nothing reaches a rig. The rules are the plan's, and
`tests/test_the_numbers_the_fleet_identity_design_waits_on_are_measured.py`
recomputes each derived figure from the projected rows.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

SCR = Path(__file__).resolve().parent
REPO = SCR.parents[2]
sys.path.insert(0, str(REPO / "src"))
from mcgyvr.serving import vramfit  # noqa: E402

GIB = 1 << 30
MIB = 1 << 20
QWEN36 = "Qwen3.6-35B-A3B-UD-IQ3_XXS"
LING = "Ling-3.0-tiny-Q4_K_M"
CODER_3B = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
CODER_7B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
CLASS = {("srv1", QWEN36): "cpu_experts", ("srv1", LING): "llamacpp",
         ("srv2", CODER_3B): "vllm", ("srv2", CODER_7B): "vllm"}


def load(name: str) -> Any:
    path = SCR / name
    return json.loads(path.read_text()) if path.exists() else []


def save(name: str, doc: Any) -> None:
    (SCR / name).write_text(json.dumps(doc, indent=1) + "\n")


def start_of(label: str) -> int:
    return int(label.rsplit("-", 1)[1])


def ok(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if not r.get("failed")]


def only_container(row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    (c, unit), = row["per_unit"].items()
    return c, unit


def samples(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"tok_s": s["tok_s"], "completion_tokens": s["completion_tokens"]} for s in raw]


# --- M1 ----------------------------------------------------------------------


def decode_rows(s1: list[dict[str, Any]], s2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in s1:
        if r.get("arm") not in ("as_run", "baseline"):
            continue
        base = {"rig": r["rig"], "unit": r["unit"], "class": r["class"], "arm": r["arm"],
                "label": r["label"], "start": start_of(r["label"]), "compose": r["compose"]}
        if r.get("no_baseline"):
            out.append({**base, "no_baseline": r["no_baseline"], "ram_need_gib": r["ram_need_gib"],
                        "ram_available_gib": r["ram_available_gib"]})
            continue
        if r.get("failed"):
            continue
        _, unit = only_container(r)
        out.append({**base, "argv": unit["argv"], "swap_total_mib": r["swap_total_mib"],
                    "restart_count": unit["restart_count"], "pswpout_decode": r["pswpout_decode"],
                    "pgmajfault_decode": r["pgmajfault_decode"], "warmup_discarded": r["warmup_discarded"],
                    "samples": samples(r["samples"]), "uptime_since": r["idle"]["uptime_since"]})
    for r in ok(s2):
        if not r["label"].startswith("s2-pair-"):
            continue
        for c, unit in r["per_unit"].items():
            d = r["decode"][c]
            out.append({"rig": "srv2", "unit": unit["model"], "class": "vllm", "arm": r["arm"],
                        "label": r["label"], "start": start_of(r["label"]), "compose": r["compose"],
                        "argv": unit["argv"], "swap_total_mib": r["swap_total_mib"],
                        "restart_count": unit["restart_count"], "pswpout_decode": d["pswpout_decode"],
                        "pgmajfault_decode": d["pgmajfault_decode"], "warmup_discarded": d["warmup_discarded"],
                        "samples": samples(d["samples"]), "uptime_since": r["idle"]["uptime_since"]})
    return out


def tolerances(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def warm(rig: str, unit: str, arm: str) -> list[float]:
        return [s["tok_s"] for r in rows if (r["rig"], r["unit"], r["arm"]) == (rig, unit, arm)
                and "samples" in r for s in r["samples"]]

    worst: dict[str, float] = {}
    per_unit_arm: dict[str, Any] = {}
    for (rig, unit), cls in CLASS.items():
        for arm in ("baseline", "as_run"):
            x = warm(rig, unit, arm)
            if not x:
                continue
            m = statistics.median(x)
            shortfall = max((m - v) / m for v in x)
            per_unit_arm[f"{rig}/{unit}/{arm}"] = {"median_tok_s": m, "shortfall_pct": 100 * shortfall,
                                                   "n": len(x), "min": min(x), "max": max(x)}
            worst[cls] = max(worst.get(cls, 0.0), shortfall)
    classes = {cls: {"tolerance_pct": max(1, math.ceil(100 * w - 1e-9)), "worst_shortfall_pct": 100 * w}
               for cls, w in worst.items()}
    for cls in classes:
        classes[cls]["provisional_pct"] = {"vllm": 3, "llamacpp": 5, "cpu_experts": 15}[cls]
    units = {}
    for (rig, unit), cls in CLASS.items():
        as_run = warm(rig, unit, "as_run")
        base = warm(rig, unit, "baseline")
        if not as_run:
            continue
        entry: dict[str, Any] = {"class": cls, "approved_tok_s": statistics.median(as_run)}
        if base:
            gap = (statistics.median(base) - statistics.median(as_run)) / statistics.median(base)
            entry.update(baseline_tok_s=statistics.median(base), gap_pct=100 * gap,
                         nvme="allowed" if 100 * gap <= classes[cls]["tolerance_pct"] else "not allowed")
        else:
            entry["nvme"] = "no baseline: NVMe required"
        units[f"{rig}/{unit}"] = entry
    return {"rule": "records/plans/fleet-identity-measurements-2026-09-11.md, M1 tolerance rule",
            "classes": classes, "units": units, "per_unit_arm": per_unit_arm}


# --- M2 ----------------------------------------------------------------------


def wake_rows(s1: list[dict[str, Any]], s2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    picked = [r for r in ok(s1) if r.get("arm") == "as_run"]
    picked += [r for r in ok(s2) if r["label"].startswith(("s2-3b-alone-", "s2-7b-alone-"))]
    for r in picked:
        c, unit = only_container(r)
        out.append({"rig": r["rig"], "unit": r.get("unit") or unit["model"], "label": r["label"],
                    "start": start_of(r["label"]), "restart_count": unit["restart_count"],
                    "page_cache_dropped": True, "co_residents": [], "clocks": unit["clocks"],
                    "load_pgmajfault": r["up"]["load_pgmajfault"], "load_pswpout": r["up"]["load_pswpout"],
                    "clock_offset_s": r["idle"]["clock_offset_s"], "uptime_since": r["idle"]["uptime_since"]})
    return out


def wake_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in sorted({(r["rig"], r["unit"]) for r in rows}):
        mine = [r for r in rows if (r["rig"], r["unit"]) == key]
        entry: dict[str, Any] = {"clock": "door_process_s", "n": len(mine)}
        for clock in ("door_process_s", "door_unit_s", "started_at_to_ready_s"):
            x = [r["clocks"][clock] for r in mine]
            m = statistics.median(x)
            entry[clock] = {"median_s": m, "min_s": min(x), "max_s": max(x),
                            "max_deviation_pct": 100 * max(abs(v - m) for v in x) / m}
        entry["median_s"] = entry["door_process_s"]["median_s"]
        entry["waker_over_door_unit_s"] = statistics.median(
            r["clocks"]["door_process_s"] - r["clocks"]["door_unit_s"] for r in mine)
        entry["proposed_cold_tolerance_s"] = max(0.10 * entry["median_s"], 5.0)
        out[f"{key[0]}/{key[1]}"] = entry
    return out


# --- M3 ----------------------------------------------------------------------


def host_ram_rows(s1: list[dict[str, Any]], s2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    picked = [r for r in ok(s1) if r["label"].startswith("s1-3b-vllm-")]
    picked += [r for r in ok(s2) if r["label"].startswith(("s2-3b-alone-", "s2-7b-alone-"))]
    for r in picked:
        c, unit = only_container(r)
        idle = r["idle"]["mem"]["MemAvailable"]
        up = r["mem_up_dropped"]["MemAvailable"]
        out.append({"rig": r["rig"], "unit": unit["model"], "label": r["label"], "start": start_of(r["label"]),
                    "restart_count": unit["restart_count"], "page_cache_dropped_before_both_reads": True,
                    "mem_available_idle_gib": idle, "mem_available_up_gib": up, "cost_gib": idle - up,
                    "process_rss_gib": r["process_rss_gib"][c], "shmem_delta_gib":
                    r["mem_up_dropped"]["Shmem"] - r["idle"]["mem"]["Shmem"],
                    "swap_used_up_gib": r["mem_up_dropped"]["SwapTotal"] - r["mem_up_dropped"]["SwapFree"]})
    return out


# --- M4 ----------------------------------------------------------------------


def shmem_rows(s1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in ok(s1):
        if r.get("arm") not in ("baseline", "shmem") or r.get("no_baseline"):
            continue
        _, unit = only_container(r)
        argv = unit["argv"]
        ncmoe = int(argv[argv.index("--n-cpu-moe") + 1])
        geometry = json.loads((SCR / f"{r['unit']}.geometry.json").read_text())
        spilled = (geometry["bytes_experts"] - vramfit.experts_on_card(geometry, ncmoe)) / GIB
        idle, up = r["idle"]["mem"]["Shmem"], r["mem_up"]["Shmem"]
        out.append({"model": r["unit"], "rig": r["rig"], "n_cpu_moe": ncmoe, "label": r["label"],
                    "load_mode": argv[argv.index("--load-mode") + 1], "swap_total_mib": r["swap_total_mib"],
                    "shmem_idle_gib": idle, "shmem_up_gib": up, "spilled_experts_gib": spilled,
                    "residual_gib": up - idle - spilled})
    return out


# --- M5 ----------------------------------------------------------------------


def fp8_rows(s2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in ok(s2):
        if r.get("arm") not in ("alone", "fp8") or not r["label"].startswith(("s2-7b-alone-", "s2-7b-fp8-")):
            continue
        c, unit = only_container(r)
        m = re.search(r"Using (\w+) attention backend", unit["backend_line"] or "")
        out.append({"rig": "srv2", "unit": unit["model"], "label": r["label"], "start": start_of(r["label"]),
                    "kv_cache_dtype": r["kv_cache_dtype"], "gpu_cc": r["idle"]["gpu"]["cc"],
                    "restart_count": unit["restart_count"], "backend_line": unit["backend_line"],
                    "attention_backend": m.group(1) if m else None, "card_used_mib": r["gpu_up"]["used"],
                    "kv_tokens": unit["kv_tokens"], "samples": samples(r["decode"][c]["samples"]),
                    "free_on_start_line": unit["free_on_start_line"]})
    return out


def fp8_quality() -> dict[str, Any] | None:
    spec = importlib.util.spec_from_file_location("resp", REPO / "tools/bench/responsiveness.py")
    assert spec and spec.loader
    resp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resp)
    runs: dict[str, dict[str, bool]] = {}
    for name in ("bench-7b-auto-a", "bench-7b-auto-b", "bench-7b-fp8-a", "bench-7b-fp8-b"):
        path = SCR / name / "bench-py" / "results.jsonl"
        if not path.exists():
            return None
        runs[name] = {json.loads(line)["task"]: bool(json.loads(line)["passed"])
                      for line in path.read_text().splitlines() if json.loads(line)["arm"] == "greedy"}

    def flips(a: str, b: str) -> int:
        return sum(1 for t in runs[a] if runs[a][t] != runs[b][t])

    n = len(runs["bench-7b-auto-a"])
    null_auto = resp.wilson(flips("bench-7b-auto-a", "bench-7b-auto-b"), n)[1]
    null_fp8 = resp.wilson(flips("bench-7b-fp8-a", "bench-7b-fp8-b"), n)[1]
    contrast = flips("bench-7b-auto-a", "bench-7b-fp8-a")
    bound = 100 * max(null_auto, null_fp8)
    return {"cells": n, "passes": {k: sum(v.values()) for k, v in runs.items()},
            "null_flips": {"auto": flips("bench-7b-auto-a", "bench-7b-auto-b"),
                           "fp8": flips("bench-7b-fp8-a", "bench-7b-fp8-b")},
            "null_bound_pp": {"auto": 100 * null_auto, "fp8": 100 * null_fp8},
            "flips": contrast, "drift_pp": 100 * contrast / n, "bound_pp": bound,
            "verdict": "within null" if 100 * contrast / n <= bound else "outside null",
            "method": "records/evidence/2026-09-03-srv1-kernel-arms/correctness.json (flips vs own-null 95% Wilson upper)"}


# --- M7 ----------------------------------------------------------------------

LLAMA_BUFFERS = {
    "cuda_model": r"load_tensors:\s+CUDA0 model buffer size =\s+([\d.]+)",
    "cuda_kv": r"llama_kv_cache:\s+CUDA0 KV buffer size =\s+([\d.]+)",
    "cuda_compute": r"sched_reserve:\s+CUDA0 compute buffer size =\s+([\d.]+)",
    "cuda_rs": r"llama_memory_recurrent:\s+CUDA0 RS buffer size =\s+([\d.]+)",
}


def llama_context_mib(row: dict[str, Any]) -> dict[str, Any]:
    """Card net of idle, less the named device buffers of the loader's last pass."""
    _, unit = only_container(row)
    txt = (SCR / unit["log"]).read_text(errors="replace")
    idx = [m.start() for m in re.finditer(r"load_tensors:.*model buffer size", txt)]
    real = txt[idx[len(idx) // 2]:] if len(idx) > 1 else txt
    named: dict[str, float] = {}
    for key, pat in LLAMA_BUFFERS.items():
        found = re.findall(pat, real)
        named[key] = (sum(float(x) for x in found) if key == "cuda_kv" else float(found[-1])) if found else 0.0
    net = row["gpu_up"]["used"] - row["idle"]["gpu"]["used"]
    return {"label": row["label"], "card_net_mib": net, "named_mib": named,
            "context_mib": net - sum(named.values())}


def headroom(s1: list[dict[str, Any]], s2: list[dict[str, Any]], pinned: list[dict[str, Any]]) -> dict[str, Any]:
    proposal = load("proposal.json") or {}
    verbose = [llama_context_mib(r) for r in ok(s1) if r.get("arm") == "context"]
    solo = [r for r in ok(pinned) if r["kind"] == "solo"]
    srv1_idle = next(r["idle"]["gpu"] for r in ok(s1) if "idle" in r)
    srv2_idle = next(r["idle"]["gpu"] for r in ok(s2) if "idle" in r)
    rigs = {
        "srv1": {"reserve_mib": srv1_idle["reserved"], "card_total_mib": srv1_idle["total"],
                 "contexts_mib": {QWEN36: max(v["context_mib"] for v in verbose)} if verbose else {},
                 "context_readings": verbose},
        "srv2": {"reserve_mib": srv2_idle["reserved"], "card_total_mib": srv2_idle["total"],
                 "contexts_mib": {u: max(r["context_bytes"] for r in solo if r["unit"] == u) / MIB
                                  for u in (CODER_3B, CODER_7B) if any(r["unit"] == u for r in solo)},
                 "context_readings": [{"label": r["label"], "unit": r["unit"], "context_bytes": r["context_bytes"],
                                       "total_bytes": r["total_bytes"], "peak_process_mib": r["peak_process_mib"],
                                       "non_kv_peak_bytes": r["non_kv_peak_bytes"]} for r in solo]},
    }
    for entry in rigs.values():
        entry["headroom_mib"] = entry["reserve_mib"] + sum(entry["contexts_mib"].values())
    orders = [{"order": r["order"], "start": r["start"], "label": r["label"], "units": r["units"],
               "neighbour_requests_sent": r["neighbour_requests_sent"]}
              for r in ok(pinned) if r["kind"] == "order"]
    return {"rigs": rigs, "srv2_proposal": proposal, "orders": orders}


def main() -> None:
    s1, s2, pinned = load("raw-srv1.json"), load("raw-srv2.json"), load("raw-srv2-pinned.json")
    decode = decode_rows(s1, s2)
    save("results-decode.json", decode)
    save("tolerances.json", tolerances(decode))
    wake = wake_rows(s1, s2)
    save("results-wake.json", wake)
    save("wake.json", wake_summary(wake))
    ram = host_ram_rows(s1, s2)
    save("results-host-ram.json", ram)
    save("host-ram.json", {rig: {"cost_gib": max(r["cost_gib"] for r in ram if r["rig"] == rig),
                                 "n": sum(1 for r in ram if r["rig"] == rig)}
                           for rig in sorted({r["rig"] for r in ram})})
    save("results-shmem.json", shmem_rows(s1))
    save("results-fp8.json", fp8_rows(s2))
    quality = fp8_quality()
    if quality:
        save("fp8-quality.json", quality)
    save("results-pinned-kv.json", [r for r in ok(pinned) if r["kind"] == "pinned_case"])
    if pinned:
        save("results-headroom.json", headroom(s1, s2, pinned))


if __name__ == "__main__":
    main()
