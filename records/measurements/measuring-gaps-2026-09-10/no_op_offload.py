#!/usr/bin/env python3
"""Q6 launch half — does ``--no-op-offload`` take Q4's ``C`` step away, and what does it cost?

Q4 measured ``C`` stepping +74 MiB between ncmoe 0 and 13 on deepseek/srv2, and
the engine's own ``CUDA0 compute buffer size`` stepping 76.13 -> 151.51 MiB
beside it. llama.cpp's op offload copies host-stored expert weights into the
device compute buffer for batches of 32+ tokens; ``--no-op-offload`` turns it
off. One arm = one cold start. Each records the card (steady, before any
request, as Q4 did), the engine's buffer lines, a long-prompt prefill rate
(op offload only engages on a large batch, so a short prompt cannot see it),
a warm decode, and the card again after the workload.

``C`` is not computed here — ``q6_report.py`` recomputes it offline, as
``c_drift_report.py`` does.

Usage:
    cd records/measurements/measuring-gaps-2026-09-10
    uv run --no-sync python no_op_offload.py arms-q6-no-op-offload.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import rig  # same-directory primitives (door, sampler, gpu, drop_caches, balloon)

ARMS = json.loads((rig.SCR / sys.argv[1]).read_text())
OUT = rig.SCR / (os.environ.get("MCG_OUT") or f"results-{Path(sys.argv[1]).stem}.json")
LOGS = rig.SCR / "logs"
LOGS.mkdir(exist_ok=True)

#: Card totals, to turn the arm's own ``vram_idle_free_mib`` into the idle
#: *used* baseline the steady figure is net of (headroom.py:38-39).
CARD_TOTAL_MIB = {"srv1": 5744, "srv2": 11912}

#: ~2k tokens of code: four full ``-ub 512`` batches, far over the 32-token
#: op-offload threshold, and inside the 4096-token slot ``-c 8192 -np 2`` gives.
PREFILL_PROMPT = (
    "def merge(a, b):\n"
    "    out = []\n"
    "    i = j = 0\n"
    "    while i < len(a) and j < len(b):\n"
    "        if a[i] <= b[j]:\n"
    "            out.append(a[i]); i += 1\n"
    "        else:\n"
    "            out.append(b[j]); j += 1\n"
    "    return out + a[i:] + b[j:]\n\n"
) * 30 + "# Explain the function above.\n"


def teardown(host: str) -> None:
    running = rig.rig(host, "docker ps --format '{{.Names}}' | grep '^mcgyvr-' || true")
    if not running.split():
        return
    compose = rig.last_up(host)
    if compose is None:
        raise SystemExit(f"{host}: {running} is up and nothing names its compose")
    rig.door_or_die("down", host, compose, f"td-{int(time.time())}")


def last_float(pattern: str, text: str) -> float | None:
    got = re.findall(pattern, text)
    return float(got[-1]) if got else None


def last_str(pattern: str, text: str) -> str | None:
    got = re.findall(pattern, text)
    return got[-1].strip() if got else None


def buffers(log: str) -> dict:
    """The engine's own buffer lines — the LAST of each, i.e. the real load's."""
    return {
        "cuda0_model_mib": last_float(r"CUDA0 model buffer size =\s+([\d.]+) MiB", log),
        "cpu_mapped_model_mib": last_float(r"CPU_Mapped model buffer size =\s+([\d.]+) MiB", log),
        "cuda0_kv_mib": last_float(r"CUDA0 KV buffer size =\s+([\d.]+) MiB", log),
        "cuda0_compute_mib": last_float(r"CUDA0 compute buffer size =\s+([\d.]+) MiB", log),
        "cuda_host_compute_mib": last_float(r"CUDA_Host compute buffer size =\s+([\d.]+) MiB", log),
        "graph_splits": last_str(r"graph splits = ([^\n]+)", log),
        "sched_copies": last_str(r"sched copies = (\d+)", log),
    }


def prefill(host: str, port: int, samples: int = 3) -> dict | None:
    """One discarded warm-up, then ``samples`` long-prompt prefills, never cached."""
    body = json.dumps(
        {"prompt": PREFILL_PROMPT, "n_predict": 8, "temperature": 0, "cache_prompt": False}
    )
    got = []
    for i in range(samples + 1):
        proc = rig.sh(
            ["curl", "-s", "-m", "900", f"http://{host}:{port}/completion",
             "-H", "Content-Type: application/json", "-d", body],
            timeout=960,
        )
        try:
            t = json.loads(proc.stdout)["timings"]
        except Exception:
            continue
        if i:
            got.append({"prompt_n": t["prompt_n"], "tok_s": t["prompt_per_second"]})
    if not got:
        return None
    return {
        "mean": sum(g["tok_s"] for g in got) / len(got),
        "samples": got,
        "n": len(got),
    }


def arm(spec: dict, index: int) -> dict:
    host, label = spec["host"], f"{spec['label']}-{index}"
    teardown(host)
    rig.balloon_down(host)
    rig.drop_caches(host)
    idle_gpu = rig.gpu(host)  # free BEFORE launch -> idle-used baseline
    rig.sample_start(host)
    proc = rig.door("up", host, spec["compose"], f"{label}-up")
    t1 = time.time()
    if proc.returncode != 0:
        log = rig.rig(host, f"docker logs --tail 40 {spec['container']} 2>&1 || true")
        rig.sample_stop(host, label)
        (LOGS / f"crash-{label}.log").write_text(log)
        raise SystemExit(f"door up rc={proc.returncode}\n{log[-1500:]}")
    rig.note_up(host, spec["compose"])
    wake = rig.wake_from(host, spec["container"], t1)
    time.sleep(2)
    rows = rig.sample_stop(host, label)
    engine_log = rig.rig(host, f"docker logs {spec['container']} 2>&1 || true")
    (LOGS / f"{label}.log").write_text(engine_log)  # FULL log, parse off-rig
    after_gpu = rig.gpu(host)
    peak = max((r["vram_used_mib"] for r in rows), default=None)

    idle_used = CARD_TOTAL_MIB[host] - idle_gpu["free"]
    steady_net = after_gpu["used"] - idle_used

    pf = prefill(host, spec["port"])
    dec = rig.decode_llamacpp_warm(host, spec["port"])
    after_work_gpu = rig.gpu(host)

    return {
        **spec,
        "label": label,
        "wake_s": wake,
        "vram_peak_used_mib": peak,
        "vram_steady_used_mib": after_gpu["used"],
        "vram_idle_free_mib": idle_gpu["free"],
        "vram_steady_net_mib": steady_net,
        "vram_after_work_net_mib": after_work_gpu["used"] - idle_used,
        "samples": len(rows),
        "engine": buffers(engine_log),
        "prefill_tok_s": pf,
        "decode_warm_tok_s": dec,
    }


def main() -> None:
    for host in sorted({s["host"] for s in ARMS}):
        up = rig.rig(host, "docker ps --format '{{.Names}}' | wc -l")
        if up.strip() != "0":
            raise SystemExit(f"ABORT: {host} has {up!r} running containers (expected 0)")
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    try:
        for spec in ARMS:
            for i in range(1, spec.get("repeats", 1) + 1):
                try:
                    results.append(arm(spec, i))
                except SystemExit as exc:
                    results.append({**spec, "label": f"{spec['label']}-{i}", "failed": str(exc)})
                OUT.write_text(json.dumps(results, indent=2) + "\n")
                print(f"[{time.strftime('%H:%M:%S')}] {spec['label']}-{i} done", flush=True)
    finally:
        for host in sorted({s["host"] for s in ARMS}):
            teardown(host)
            left = rig.rig(host, "docker ps --format '{{.Names}}' | wc -l")
            print(f"{host}: {left.strip()} containers running after teardown", flush=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
