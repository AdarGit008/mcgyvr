#!/usr/bin/env python3
"""Ubatch-boundary probe — does ``-ub`` clamp to ``-b``, and what moves?

Q3's "``-ub 1024``" rows ran at ``-ub 512`` because llama.cpp clamps the
physical (micro) batch to the logical batch. This runner pins the boundary on
one llama.cpp unit (deepseek-coder-v2-16b, srv2, all layers on card): ``-b 512``
held fixed while ``-ub`` sweeps {128, 256, 512, 1024, 2048}. One arm = one cold
start. Each records the engine's *reported* ``n_ubatch`` and the buffer lines
(``CUDA0 compute buffer size``, ``CUDA0 KV buffer size``) that Q3 tracked.

Usage:
    cd records/measurements/measuring-gaps-2026-09-10
    uv run --no-sync python ub_boundary.py arms-ub-boundary.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import rig  # same-directory primitives (door, gpu, drop_caches, balloon)

ARMS = json.loads((rig.SCR / sys.argv[1]).read_text())
OUT = rig.SCR / (os.environ.get("MCG_OUT") or f"results-{Path(sys.argv[1]).stem}.json")
LOGS = rig.SCR / "logs"
LOGS.mkdir(exist_ok=True)

CARD_TOTAL_MIB = {"srv2": 11912}


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


def last_int(pattern: str, text: str) -> int | None:
    got = re.findall(pattern, text)
    return int(got[-1]) if got else None


def parse(log: str) -> dict:
    """The reported ubatch/batch and the buffer lines Q3 measured."""
    return {
        "n_ubatch": last_int(r"n_ubatch\s*=\s*(\d+)", log),
        "n_batch": last_int(r"\bn_batch\s*=\s*(\d+)", log),
        "cuda0_compute_mib": last_float(r"CUDA0 compute buffer size =\s+([\d.]+) MiB", log),
        "cuda0_kv_mib": last_float(r"CUDA0 KV buffer size =\s+([\d.]+) MiB", log),
        "cuda0_model_mib": last_float(r"CUDA0 model buffer size =\s+([\d.]+) MiB", log),
        "kv_cache_line": (re.findall(r"llama_kv_cache:[^\n]*", log) or [None])[-1],
    }


def arm(spec: dict, index: int) -> dict:
    host, label = spec["host"], f"{spec['label']}-{index}"
    teardown(host)
    rig.balloon_down(host)
    rig.drop_caches(host)
    idle_gpu = rig.gpu(host)
    proc = rig.door("up", host, spec["compose"], f"{label}-up")
    t1 = time.time()
    if proc.returncode != 0:
        log = rig.rig(host, f"docker logs --tail 40 {spec['container']} 2>&1 || true")
        (LOGS / f"crash-{label}.log").write_text(log)
        raise SystemExit(f"door up rc={proc.returncode}\n{log[-1500:]}")
    rig.note_up(host, spec["compose"])
    wake = rig.wake_from(host, spec["container"], t1)
    time.sleep(2)
    engine_log = rig.rig(host, f"docker logs {spec['container']} 2>&1 || true")
    (LOGS / f"{label}.log").write_text(engine_log)
    after_gpu = rig.gpu(host)
    idle_used = CARD_TOTAL_MIB[host] - idle_gpu["free"]
    parsed = parse(engine_log)
    return {
        **spec,
        "label": label,
        "wake_s": wake,
        "vram_idle_free_mib": idle_gpu["free"],
        "vram_steady_net_mib": after_gpu["used"] - idle_used,
        "engine": parsed,
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
