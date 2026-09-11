#!/usr/bin/env python3
"""Q4 launch half — does ``C`` drift with ``--n-cpu-moe`` on deepseek/srv2?

One arm = one cold start of ``compose.srv2-q4-deepseek-n<N>.yml`` at a single
``--n-cpu-moe`` placement. This runner records the *measured* card side only
(steady net of idle, plus the peak sampler trace); it deliberately does NOT
compute ``C`` — ``c_drift_report.py`` recomputes that offline from the geometry
and ``vramfit``, exactly as ``headroom.py`` does, so the probe (ncmoe 0) fixes
``C`` and every other placement is predicted from it.

Usage:
    cd records/measurements/measuring-gaps-2026-09-10
    uv run --no-sync python c_drift_deepseek.py arms-q4-c-drift.json
"""
from __future__ import annotations

import json
import os
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

    return {
        **spec,
        "label": label,
        "wake_s": wake,
        "vram_peak_used_mib": peak,
        "vram_steady_used_mib": after_gpu["used"],
        "vram_idle_free_mib": idle_gpu["free"],
        "vram_steady_net_mib": steady_net,
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
            OUT.write_text(json.dumps(results, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
