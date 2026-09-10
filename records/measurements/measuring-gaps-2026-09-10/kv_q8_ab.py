#!/usr/bin/env python3
"""Q1 — q8_0 KV cache on-rig: does the 17/32 factor hold, and what does it cost?

One arm = one cold start of the srv1 deepseek unit, with or without
``-ctk q8_0 -ctv q8_0`` (the compose already carries the flag; this runner only
launches it through the door and reads the result). The measurement this runner
adds over the generic wake shape is the engine's own ``llama_kv_cache`` line,
parsed off-rig from the full captured log, so the K/V dtype and MiB are the
engine's words, not a recomputation.

Arms come from argv[1] (a JSON list of {host, label, cache_type, compose,
container, port, blob_gib, repeats}). It appends one row per repeat to
``results-q1-kv-q8.json``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import rig

ARMS = json.loads((rig.SCR / sys.argv[1]).read_text())
OUT = rig.SCR / (os.environ.get("MCG_OUT") or f"results-{Path(sys.argv[1]).stem}.json")
LOGS = rig.SCR / "logs"
LOGS.mkdir(exist_ok=True)

#: The engine line, with the dtype letters captured — the generic parse-logs
#: KVSIZE drops the letters, but the dtype IS the answer here, so capture it:
#: group 6/7 = K dtype/MiB, group 8/9 = V dtype/MiB.
KVSIZE = re.compile(
    r"llama_kv_cache: size =\s+([\d.]+) MiB \(\s*(\d+) cells,\s*(\d+) layers,"
    r"\s*(\d+)/(\d+) seqs\), K \((\w+)\):\s*([\d.]+) MiB,"
    r" V \((\w+)\):\s*([\d.]+) MiB"
)


def teardown(host: str) -> None:
    """Bring down whatever is actually up, by the compose that names it."""
    running = rig.rig(host, "docker ps --format '{{.Names}}' | grep '^mcgyvr-' || true")
    names = [n for n in running.split() if n]
    if not names:
        return
    index = json.loads((rig.SCR / "teardown-index.json").read_text())
    wanted: list[str] = []
    remembered = rig.last_up(host)
    if remembered:
        wanted.append(remembered)
    else:
        for name in names:
            compose = index.get(name)
            if compose is None:
                raise SystemExit(
                    f"{host}: {name} is up and no compose in teardown-index.json names it; "
                    "add it rather than killing the container behind the door's back"
                )
            if compose not in wanted:
                wanted.append(compose)
    for compose in wanted:
        stem = Path(compose).parent.name[-20:]
        rig.door_or_die("down", host, compose, f"td-{stem}-{int(time.time())}")


def parse_kv(log: str) -> dict:
    """Parse the engine's KV-cache line from the full captured log.

    The loader runs twice (a fit pass then the real one); split on the LAST
    ``load_tensors: … model buffer size`` occurrence and parse only what follows,
    so the q8_0 dtype read is the real allocation, not the fit pass.
    """
    idx = [m.start() for m in re.finditer(r"load_tensors:.*model buffer size", log)]
    real = log[idx[len(idx) // 2] :] if len(idx) > 1 else log
    got: dict = {}
    matches = list(KVSIZE.finditer(real))
    if matches:
        m = matches[-1]  # single KV cache on deepseek; last is the real pass
        got = {
            "kv_line": m.group(0),
            "size_mib": float(m.group(1)),
            "cells": int(m.group(2)),
            "layers": int(m.group(3)),
            "k_dtype": m.group(6),
            "k_mib": float(m.group(7)),
            "v_dtype": m.group(8),
            "v_mib": float(m.group(9)),
        }
    return got


def arm(spec: dict, index: int) -> dict:
    host, label = spec["host"], f"{spec['label']}-{index}"
    print(f"\n=== {label}  cache_type {spec['cache_type']}  blob {spec['blob_gib']:.2f} GiB", flush=True)
    teardown(host)
    rig.balloon_down(host)
    rig.drop_caches(host)
    idle_gpu = rig.gpu(host)
    print(f"    card free {idle_gpu['free']} MiB", flush=True)

    rig.sample_start(host)
    proc = rig.door("up", host, spec["compose"], f"{label}-up")
    t1 = time.time()
    if proc.returncode != 0:
        log = rig.rig(host, f"docker logs --tail 40 {spec['container']} 2>&1 || true")
        rig.sample_stop(host, label)
        (LOGS / f"crash-{label}.log").write_text(log)
        raise SystemExit(f"door up rc={proc.returncode}; container log tail:\n{log[-1500:]}")
    rig.note_up(host, spec["compose"])
    wake = rig.wake_from(host, spec["container"], t1)
    time.sleep(2)
    rows = rig.sample_stop(host, label)
    engine_log = rig.rig(host, f"docker logs {spec['container']} 2>&1 || true")
    (LOGS / f"{label}.log").write_text(engine_log)  # FULL log, parse off-rig
    cold = rig.decode_llamacpp(host, spec["port"])
    warm = rig.decode_llamacpp_warm(host, spec["port"])
    after_gpu = rig.gpu(host)
    peak = max((r["vram_used_mib"] for r in rows), default=None)
    kv = parse_kv(engine_log)
    warm_mean = warm["mean"] if warm else None
    print(
        f"    wake {wake:.1f} s   decode cold {cold} / warm {warm_mean}   "
        f"card peak {peak} / steady {after_gpu['used']} MiB   "
        f"K ({kv.get('k_dtype')}): {kv.get('k_mib')} MiB, "
        f"V ({kv.get('v_dtype')}): {kv.get('v_mib')} MiB",
        flush=True,
    )
    return {
        **spec,
        "label": label,
        "wake_s": wake,
        "vram_peak_used_mib": peak,
        "vram_steady_used_mib": after_gpu["used"],
        "vram_idle_free_mib": idle_gpu["free"],
        "decode_tok_s": cold,
        "decode_warm": warm,
        "k_mib": kv.get("k_mib"),
        "v_mib": kv.get("v_mib"),
        "k_dtype": kv.get("k_dtype"),
        "v_dtype": kv.get("v_dtype"),
        "kv_line": kv.get("kv_line"),
        "samples": len(rows),
    }


def main() -> None:
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    for spec in ARMS:
        for i in range(1, spec.get("repeats", 1) + 1):
            try:
                results.append(arm(spec, i))
            except SystemExit as exc:
                print(f"    ARM FAILED: {exc}", flush=True)
                results.append({**spec, "label": f"{spec['label']}-{i}", "failed": str(exc)})
            OUT.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
