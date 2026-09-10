#!/usr/bin/env python3
"""Q5 — MLA absorbed-V: capture the engine's own ``V (f16): 0.00 MiB`` line.

One arm = one cold start of Ling-3.0-tiny Q4_K_M (``bailingmoe3``). The whole
measurement is the verbatim ``llama_kv_cache: size = ...`` line the engine
prints at load: for an MLA absorbed-V checkpoint it must read ``V (f16):
0.00 MiB`` — V absent, not merely small. The steady card is captured beside it
and, best-effort, cross-checked against ``vramfit.predict`` (whose law already
uses ``v_elems = 0``).

Decode is intentionally NOT taken: the door's own ``/v1/models`` +
``/is_sleeping`` probe during ``serve up`` already proves the unit serves, and
the KV decomposition line is printed during init, not at first decode.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import rig

# vramfit lives in src/; the run directory is not a package.
sys.path.insert(0, "/home/adaramir/claude/mcgyvr/src")

ARMS = json.loads((rig.SCR / sys.argv[1]).read_text())
OUT = rig.SCR / (os.environ.get("MCG_OUT") or f"results-{Path(sys.argv[1]).stem}.json")

CARD_TOTAL_MIB = {"srv1": 5744, "srv2": 11912}
MIB = 1024 * 1024

# Ling-3.0-tiny Q4_K_M geometry (arch `bailingmoe3`). The emit file is a JSON
# LIST; element [0] is the geometry dict.
LING_GEOM = Path(
    "/home/adaramir/claude/mcgyvr/records/measurements/flexibility-2026-09-09/"
    "emit/srv1-Ling-3.0-tiny-Q4_K_M/Ling-3.0-tiny-Q4_K_M.geometry.json"
)


def teardown(host: str) -> None:
    """Bring down whatever is up, by the compose that actually named it."""
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
                    f"{host}: {name} is up and no compose in teardown-index.json "
                    "names it; add it rather than killing the container behind "
                    "the door's back"
                )
            if compose not in wanted:
                wanted.append(compose)
    for compose in wanted:
        stem = Path(compose).parent.name[-20:]
        rig.door_or_die("down", host, compose, f"td-{stem}-{int(time.time())}")


def parse_kv_lines(log: str) -> list[dict]:
    """Every ``llama_kv_cache: size = ...`` line, verbatim + parsed.

    bailingmoe3 is not a sliding-window checkpoint, so there is exactly one real
    line — but the loader can print it during its fit pass too, and an SWA model
    prints two. Collect every occurrence and let the report pick; the LAST one
    is the real allocation.
    """
    out: list[dict] = []
    for line in log.splitlines():
        if "llama_kv_cache: size =" not in line:
            continue
        sm = re.search(r"size =\s*([\d.]+)\s*MiB", line)
        km = re.search(r"K \((\w+)\):\s*([\d.]+)", line)
        vm = re.search(r"V \((\w+)\):\s*([\d.]+)", line)
        out.append(
            {
                "verbatim": line.strip(),
                "size_mib": float(sm.group(1)) if sm else None,
                "k_dtype": km.group(1) if km else None,
                "k_mib": float(km.group(2)) if km else None,
                "v_dtype": vm.group(1) if vm else None,
                "v_mib": float(vm.group(2)) if vm else None,
            }
        )
    return out


def cross_check(steady_net_mib: float) -> tuple[float | None, float | None]:
    """Best-effort: steady card (net of idle) against ``vramfit.predict``.

    ``constant_from_probe`` derives ``C`` from this same reading, so ``predict``
    with that ``C`` reproduces the reading exactly — the delta here is a
    self-consistency check (and a smoke test that ``experts_on_card`` resolves
    for the arch), NOT an independent verification. The independent signal is
    the ``kv_line``/``v_mib`` above. Never blocks the primary capture.
    """
    try:
        from mcgyvr.serving import vramfit

        g = json.loads(LING_GEOM.read_text())
        g = g[0] if isinstance(g, list) else g
        net_bytes = int(round(steady_net_mib * MIB))
        c = vramfit.constant_from_probe(g, 0, net_bytes)
        predicted_mib = vramfit.predict(g, 0, c) / MIB
        return predicted_mib, steady_net_mib - predicted_mib
    except Exception as exc:  # noqa: BLE001 - best-effort, never blocks the arm
        print(f"    cross-check skipped: {exc}", flush=True)
        return None, None


def arm(spec: dict, index: int) -> dict:
    host, label = spec["host"], f"{spec['label']}-{index}"
    print(f"\n=== {label}", flush=True)
    teardown(host)
    rig.balloon_down(host)
    rig.drop_caches(host)
    idle_gpu = rig.gpu(host)
    idle_used = CARD_TOTAL_MIB[host] - idle_gpu["free"]

    rig.sample_start(host)
    proc = rig.door("up", host, spec["compose"], f"{label}-up")
    t1 = time.time()
    if proc.returncode != 0:
        log = rig.rig(host, f"docker logs --tail 40 {spec['container']} 2>&1 || true")
        rig.sample_stop(host, label)
        (rig.LOGS / f"crash-{label}.log").write_text(log)
        raise SystemExit(f"door up rc={proc.returncode}\n{log[-1500:]}")
    rig.note_up(host, spec["compose"])
    wake = rig.wake_from(host, spec["container"], t1)
    time.sleep(2)
    rows = rig.sample_stop(host, label)

    engine_log = rig.rig(host, f"docker logs {spec['container']} 2>&1 || true")
    (rig.LOGS / f"{label}.log").write_text(engine_log)  # FULL log, parse off-rig

    after_gpu = rig.gpu(host)
    peak = max((r["vram_used_mib"] for r in rows), default=None)
    steady_net = after_gpu["used"] - idle_used

    kv_parts = parse_kv_lines(engine_log)
    last = kv_parts[-1] if kv_parts else {}
    predicted_mib, predicted_delta_mib = cross_check(steady_net)

    print(
        f"    wake {wake:.1f}s  card peak {peak}/steady {after_gpu['used']} MiB "
        f"(net {steady_net})  KV lines {len(kv_parts)}  V={last.get('v_mib')}",
        flush=True,
    )
    return {
        **spec,
        "label": label,
        "wake_s": wake,
        "vram_peak_used_mib": peak,
        "vram_steady_used_mib": after_gpu["used"],
        "vram_idle_free_mib": idle_gpu["free"],
        "vram_steady_net_mib": steady_net,
        "k_mib": last.get("k_mib"),
        "v_mib": last.get("v_mib"),
        "k_dtype": last.get("k_dtype"),
        "v_dtype": last.get("v_dtype"),
        "kv_line": last.get("verbatim"),
        "kv_lines": kv_parts,
        "predicted_mib": predicted_mib,
        "predicted_delta_mib": predicted_delta_mib,
        "restart_count": rig.restarts(host, spec["container"]),
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
