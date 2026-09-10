#!/usr/bin/env python3
"""Q3 launch half: one cold start per (arch, -ub); capture the compute buffer + card.

Measures the engine's own ``sched_reserve: CUDA0 compute buffer size`` line plus
the steady card (net of the idle baseline). NO decode — the measurement is the
load-time compute buffer and the residue, which the offline ``scratch_report.py``
recomputes against the ``SCRATCH_AND_CONTEXT_MIB = 768`` bound.

Run from the measuring-gaps directory:
    uv run --no-sync python scratch_curve.py arms-q3-scratch.json
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

#: Card totals (usable), read from the rigs 2026-09-10 — same figures headroom.py
#: uses to turn an arm's `vram_idle_free_mib` into the idle *used* baseline.
CARD_TOTAL_MIB = {"srv1": 5744, "srv2": 11912}

COMPUTE = re.compile(r"sched_reserve:\s+CUDA0 compute buffer size =\s+([\d.]+)")


def teardown(host: str) -> None:
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
            c = index.get(name)
            if c is None:
                raise SystemExit(f"{host}: {name} is up and nothing names it")
            if c not in wanted:
                wanted.append(c)
    for c in wanted:
        rig.door_or_die("down", host, c, f"td-{int(time.time())}")


def compute_buffer_mib(log: str) -> float | None:
    matches = COMPUTE.findall(log)
    if not matches:
        return None
    # The loader runs twice (fit pass then the real one); the last real-pass
    # compute-buffer line is the reservation that actually stands.
    return float(matches[-1])


def arm(spec: dict, index: int) -> dict:
    host, label = spec["host"], f"{spec['label']}-{index}"
    teardown(host)
    rig.balloon_down(host)
    rig.drop_caches(host)
    idle_gpu = rig.gpu(host)  # idle used/free BEFORE launch
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
    log = rig.rig(host, f"docker logs {spec['container']} 2>&1 || true")
    (LOGS / f"{label}.log").write_text(log)  # FULL log; parse off-rig
    after_gpu = rig.gpu(host)
    peak = max((r["vram_used_mib"] for r in rows), default=None)
    idle_used = CARD_TOTAL_MIB[host] - idle_gpu["free"]
    return {
        **spec,
        "label": label,
        "wake_s": wake,
        "vram_peak_used_mib": peak,
        "vram_steady_used_mib": after_gpu["used"],
        "vram_idle_free_mib": idle_gpu["free"],
        "vram_steady_net_mib": after_gpu["used"] - idle_used,
        "compute_buffer_mib": compute_buffer_mib(log),
        "samples": len(rows),
    }


def main() -> None:
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    for spec in ARMS:
        for i in range(1, spec.get("repeats", 1) + 1):
            try:
                results.append(arm(spec, i))
            except SystemExit as exc:
                results.append({**spec, "label": f"{spec['label']}-{i}", "failed": str(exc)})
            OUT.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
