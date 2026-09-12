"""One cold start of a llama.cpp or vLLM compose, and everything read around it.

An arm returns one raw row. `derive.py` projects the raw rows into the shapes the
test reads (`results-decode.json`, `results-wake.json` and the others), so a record
never carries a figure that its raw row does not.

Every arm does the same things:

1. empties the rig through the door;
2. sets swap as the arm asks;
3. drops the page cache;
4. reads the idle rig;
5. starts the units through the door, with a per-unit ready poller running;
6. reads the loaded rig, the engine log and the warm decode;
7. empties the rig again;
8. puts swap back on.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import yaml

import rig

KV_TOKENS = re.compile(r"GPU KV cache size: ([\d,]+) tokens")
BACKEND = re.compile(r"Using \w+ attention backend out of potential backends.*")
INIT_FREE = re.compile(r"Initial free memory ([\d.]+) GiB, reserved ([\d.]+) GiB memory for KV Cache")
FREE_ON_START = re.compile(r"Free memory on device \(([\d.]+)/([\d.]+) GiB\) on startup")
SNAPSHOT = re.compile(r"worker init memory snapshot: MemorySnapshot\((.*)\)")
START_GATE = re.compile(r".*is less than desired GPU memory utilization.*")


def services(compose: Path) -> list[dict[str, Any]]:
    doc = yaml.safe_load(compose.read_text(encoding="utf-8"))
    out = []
    for name, block in doc["services"].items():
        cmd = block["command"]
        model = cmd[cmd.index("--model") + 1] if "--model" in cmd else cmd[0]
        out.append({"service": name, "container": block["container_name"],
                    "port": int(cmd[cmd.index("--port") + 1]), "argv": list(cmd),
                    "image": block["image"], "model": model,
                    "depends_on": sorted((block.get("depends_on") or {}).keys())})
    return out


def append(out: Path, row: dict[str, Any]) -> None:
    rows = json.loads(out.read_text()) if out.exists() else []
    rows.append(row)
    out.write_text(json.dumps(rows, indent=1))


def _set_swap(host: str, swap: str) -> None:
    if swap == "off":
        rig.swapoff(host)
    elif rig.swap_total_mib(host) == 0:
        rig.swapon(host)


def _idle(host: str) -> dict[str, Any]:
    rig.drop_caches(host)
    return {"uptime_since": rig.uptime_since(host), "gpu": rig.gpu(host),
            "gpu_apps": rig.gpu_apps(host), "mem": rig.meminfo(host),
            "vm": rig.vmstat(host), "swap_total_mib": rig.swap_total_mib(host),
            "clock_offset_s": rig.clock_offset(host)}


def start(host: str, compose: Path, label: str) -> dict[str, Any]:
    """Door up with the ready poller running; returns the up-side readings."""
    units = services(compose)
    rig.sample_start(host)
    with rig.ReadyPoller(host, {u["container"]: u["port"] for u in units}) as poller:
        proc, door_s, envelope = rig.door("up", host, compose, f"{label}-up")
        if proc.returncode == 0:
            deadline = time.time() + 10
            while len(poller.ready) < len(units) and time.time() < deadline:
                time.sleep(0.2)
    rig.note_up(host, compose)
    load_rows = rig.sample_stop(host, f"{label}-load")
    return {"door_rc": proc.returncode, "door_process_s": door_s, "envelope": envelope,
            "ready_local": dict(poller.ready), "load_samples": len(load_rows),
            "load_peak_used_mib": max((r["vram_used_mib"] for r in load_rows), default=None),
            "load_pswpout": (load_rows[-1]["pswpout"] - load_rows[0]["pswpout"]) if load_rows else None,
            "load_pgmajfault": (load_rows[-1]["pgmajfault"] - load_rows[0]["pgmajfault"]) if load_rows else None,
            "units": units}


def unit_readings(host: str, up: dict[str, Any], offset: float, label: str) -> dict[str, dict[str, Any]]:
    """Per container: restarts, the three clocks, and the engine log's lines."""
    out: dict[str, dict[str, Any]] = {}
    door_units = {u["container"]: u for u in ((up["envelope"] or {}).get("units") or [])}
    for u in up["units"]:
        c = u["container"]
        log = rig.engine_log(host, c, f"{label}-{u['service']}")
        row: dict[str, Any] = {"restart_count": rig.restarts(host, c), "argv": u["argv"],
                               "model": u["model"], "port": u["port"], "log": f"logs/{label}-{u['service']}.log"}
        try:
            st = rig.started_at(host, c)
        except SystemExit:
            st = None
        ready = up["ready_local"].get(c)
        row["clocks"] = {
            "door_process_s": up["door_process_s"],
            "door_unit_s": (door_units.get(c) or {}).get("seconds"),
            "started_at_to_ready_s": (ready + offset - st) if (ready and st) else None,
        }
        row["healthy"] = bool((door_units.get(c) or {}).get("healthy"))
        m = KV_TOKENS.search(log)
        row["kv_tokens"] = int(m.group(1).replace(",", "")) if m else None
        m = BACKEND.search(log)
        row["backend_line"] = m.group(0) if m else None
        m = INIT_FREE.search(log)
        row["kv_line"] = m.group(0) if m else None
        row["init_free_gib"] = float(m.group(1)) if m else None
        m = FREE_ON_START.search(log)
        row["free_on_start_line"] = m.group(0) if m else None
        m = SNAPSHOT.search(log)
        row["init_snapshot"] = m.group(1) if m else None
        m = START_GATE.search(log)
        row["start_gate_line"] = m.group(0) if m else None
        oom = re.search(r".*(CUDA out of memory|OutOfMemoryError|No available memory for the cache blocks).*", log)
        row["oom_line"] = oom.group(0) if oom else None
        out[c] = row
    return out


def teardown_and_restore(host: str, swap: str) -> None:
    rig.teardown(host)
    if swap == "off":
        rig.swapon(host)


def llama_arm(*, host: str, label: str, compose: Path, unit: str, cls: str, arm: str,
              swap: str, ram_need_gib: float | None = None, out: Path) -> dict[str, Any]:
    print(f"\n=== {label}  {unit}  arm={arm} swap={swap}", flush=True)
    rig.teardown(host)
    _set_swap(host, "on")
    idle = _idle(host)
    base = {"label": label, "rig": host, "unit": unit, "class": cls, "arm": arm,
            "engine": "llamacpp", "compose": compose.name, "t": time.time()}
    if ram_need_gib is not None:
        avail = idle["mem"]["MemAvailable"]
        base.update(ram_need_gib=ram_need_gib, ram_available_gib=avail)
        if ram_need_gib > avail - 2.0:
            row = {**base, "no_baseline": "NVMe required"}
            append(out, row)
            print(f"    no baseline: need {ram_need_gib:.2f} vs available {avail:.2f} GiB", flush=True)
            return row
    _set_swap(host, swap)
    idle = _idle(host)
    try:
        up = start(host, compose, label)
        if up["door_rc"] != 0:
            readings = unit_readings(host, up, idle["clock_offset_s"], label)
            row = {**base, "failed": f"door up rc={up['door_rc']}", "idle": idle, "up": up, "per_unit": readings}
            append(out, row)
            raise SystemExit(f"{label}: door up rc={up['door_rc']}")
        mem_up = rig.meminfo(host)
        gpu_up = rig.gpu(host)
        apps_up = rig.gpu_apps(host)
        readings = unit_readings(host, up, idle["clock_offset_s"], label)
        port = up["units"][0]["port"]
        vm0 = rig.vmstat(host)
        samples, discarded = rig.warm_decode(rig.decode_llamacpp, host, port)
        vm1 = rig.vmstat(host)
        container = up["units"][0]["container"]
        row = {**base, "idle": idle, "up": up, "per_unit": readings,
               "mem_up": mem_up, "gpu_up": gpu_up, "gpu_apps_up": apps_up,
               "swap_total_mib": rig.swap_total_mib(host),
               "process_rss_gib": rig.process_rss_gib(host, container),
               "samples": samples, "warmup_discarded": discarded,
               "pswpout_decode": vm1["pswpout"] - vm0["pswpout"],
               "pgmajfault_decode": vm1["pgmajfault"] - vm0["pgmajfault"],
               "restart_count_after_decode": rig.restarts(host, container)}
        append(out, row)
        rates = [round(s["tok_s"], 2) for s in samples]
        print(f"    wake {readings[container]['clocks']}  decode {rates}  "
              f"shmem {mem_up['Shmem'] - idle['mem']['Shmem']:.3f} GiB  restarts {readings[container]['restart_count']}",
              flush=True)
        return row
    finally:
        teardown_and_restore(host, swap)


def vllm_arm(*, host: str, label: str, compose: Path, arm: str, swap: str, out: Path,
             decode: bool = True, extra: dict[str, Any] | None = None,
             keep_up: bool = False) -> dict[str, Any]:
    print(f"\n=== {label}  {compose.name}  arm={arm} swap={swap}", flush=True)
    rig.teardown(host)
    _set_swap(host, swap)
    idle = _idle(host)
    base = {"label": label, "rig": host, "arm": arm, "engine": "vllm",
            "compose": compose.name, "t": time.time(), **(extra or {})}
    up = start(host, compose, label)
    try:
        readings = unit_readings(host, up, idle["clock_offset_s"], label)
        if up["door_rc"] != 0:
            row = {**base, "failed": f"door up rc={up['door_rc']}", "idle": idle, "up": up, "per_unit": readings}
            append(out, row)
            print(f"    door up rc={up['door_rc']}: " + json.dumps(
                {c: (r["start_gate_line"] or r["oom_line"]) for c, r in readings.items()})[:600], flush=True)
            return row
        mem_up = rig.meminfo(host)
        gpu_up = rig.gpu(host)
        apps_up = rig.gpu_apps(host)
        decodes: dict[str, Any] = {}
        if decode:
            for u in up["units"]:
                vm0 = rig.vmstat(host)
                samples, discarded = rig.warm_decode(rig.decode_vllm, host, u["port"], u["model"])
                vm1 = rig.vmstat(host)
                decodes[u["container"]] = {
                    "samples": samples, "warmup_discarded": discarded,
                    "pswpout_decode": vm1["pswpout"] - vm0["pswpout"],
                    "pgmajfault_decode": vm1["pgmajfault"] - vm0["pgmajfault"],
                }
        rig.drop_caches(host)
        mem_up_dropped = rig.meminfo(host)
        row = {**base, "idle": idle, "up": up, "per_unit": readings, "mem_up": mem_up,
               "mem_up_dropped": mem_up_dropped, "gpu_up": gpu_up, "gpu_apps_up": apps_up,
               "swap_total_mib": rig.swap_total_mib(host), "decode": decodes,
               "process_rss_gib": {u["container"]: rig.process_rss_gib(host, u["container"]) for u in up["units"]},
               "restart_count_after_decode": {u["container"]: rig.restarts(host, u["container"]) for u in up["units"]}}
        append(out, row)
        for c, r in readings.items():
            rates = [round(s["tok_s"], 1) for s in (decodes.get(c) or {}).get("samples", [])]
            print(f"    {c}: clocks {r['clocks']} kv {r['kv_tokens']} restarts {r['restart_count']} "
                  f"decode {rates} backend {r['backend_line'] and r['backend_line'][:40]}", flush=True)
        print(f"    RAM cost {idle['mem']['MemAvailable'] - mem_up_dropped['MemAvailable']:.3f} GiB, card {gpu_up['used']} MiB",
              flush=True)
        return row
    finally:
        if not keep_up:
            teardown_and_restore(host, swap)
