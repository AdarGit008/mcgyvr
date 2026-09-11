"""vLLM cold starts: what `--enable-sleep-mode` costs, and what a unit alone costs.

Two questions in one runner, because both are answered by the same arm — a
cold start of a named set of vLLM units, timed from the containers' own
`StartedAt`, followed by a steady-state read of the card and the host and a
decode.

**M5 / O12.** srv2's vLLM units launch without `--enable-sleep-mode` (and
without `VLLM_SERVER_DEV_MODE=1`), so `/sleep` is 404 and sleep cannot fund a
wake on the live ladder. Nobody has priced the flag. Arms alternate
`pair-plain` and `pair-sleep` so the rig's own drift cannot be mistaken for the
flag.

**M4 / T_cold_vllm.** `records/plans/wake-timeout.md` §2.2 budgets a vLLM cold
start as a constant off two points, one of which is a *subtraction across two
campaigns* (168 s pair minus 82 s 7B = 86 s for the 3B, taken a day apart).
`3b-alone` and `7b-alone` are the same figures measured rather than derived.

**M2.** The same arms read `MemAvailable` for each unit alone and for the pair,
which is the only way to find out whether the host-RAM sum `hold_together` now
performs is additive on the one co-resident set this fleet actually runs.
"""

from __future__ import annotations

import calendar
import json
import os
import sys
import time

import rig

HOST = os.environ.get("MCG_HOST", "srv2")
# The container name carries the host, so a unit named here is a unit on
# whichever rig MCG_HOST points at. srv1 has never run vLLM and `r(srv1, vLLM)`
# is the one coefficient in `wake-timeout.md` with no measurement behind it.
UNITS = {
    "3b": (f"mcgyvr-{HOST}-Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001", 8001,
           "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"),
    "7b": (f"mcgyvr-{HOST}-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002", 8002,
           "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"),
}
ARMS = json.loads((rig.SCR / sys.argv[1]).read_text())
OUT = rig.SCR / (os.environ.get("MCG_OUT") or "results-vllm.json")
SAMPLES = 3


def teardown() -> None:
    running = rig.rig(HOST, "docker ps -a --format '{{.Names}}' | grep '^mcgyvr-' || true")
    names = [n for n in running.split() if n]
    if not names:
        return
    index = json.loads((rig.SCR / "teardown-index.json").read_text())
    wanted: list[str] = []
    remembered = rig.last_up(HOST)
    if remembered:
        # The file that started these units, not a file that merely names
        # them: the sleep-mode pair and the production pair share every
        # container name and differ only in argv.
        wanted.append(remembered)
    else:
        for name in names:
            compose = index.get(name)
            if compose is None:
                raise SystemExit(f"{HOST}: {name} is up and nothing names it")
            if compose not in wanted:
                wanted.append(compose)
    for compose in wanted:
        rig.door_or_die("down", HOST, compose, f"td-{int(time.time() * 10) % 10**9}")


def started(container: str) -> float:
    sa = rig.started_at(HOST, container)
    return calendar.timegm(time.strptime(sa[:19], "%Y-%m-%dT%H:%M:%S"))


def arm(spec: dict, index: int) -> dict:
    label = f"{spec['label']}-{index}"
    keys = spec["units"]
    print(f"\n=== {label}  units {keys}", flush=True)
    teardown()
    # A balloon outlives the block that raised it: `wake_rate.py` drops one
    # at the head of every arm and this runner never did, so Q6's 4.92 GiB
    # was still held when Q9 started and the host figure it exists to
    # measure would have been 4.92 GiB short.
    rig.balloon_down(HOST)
    rig.drop_caches(HOST)
    idle_mem, idle_gpu = rig.meminfo(HOST), rig.gpu(HOST)
    print(f"    idle avail {idle_mem['MemAvailable']:.2f} GiB, "
          f"card {idle_gpu['used']} used / {idle_gpu['free']} free MiB", flush=True)

    rig.sample_start(HOST)
    proc = rig.door("up", HOST, spec["compose"], f"{label}-up")
    t1 = time.time()
    if proc.returncode != 0:
        logs = {k: rig.rig(HOST, f"docker logs --tail 30 {UNITS[k][0]} 2>&1 || true")
                for k in keys}
        rig.sample_stop(HOST, label)
        (rig.LOGS / f"crash-{label}.log").write_text(json.dumps(logs, indent=1))
        raise SystemExit(f"door up rc={proc.returncode}; see crash-{label}.log")
    rig.note_up(HOST, spec["compose"])
    starts = {k: started(UNITS[k][0]) for k in keys}
    first = min(starts.values())
    time.sleep(2)
    rows = rig.sample_stop(HOST, label)

    per_unit = {}
    for k in keys:
        container, port, model = UNITS[k]
        code, _ = rig.http(HOST, port, "/is_sleeping")
        rig.decode_vllm(HOST, port, model)  # warm-up, discarded
        got = [rig.decode_vllm(HOST, port, model) for _ in range(SAMPLES)]
        got = [g for g in got if g]
        per_unit[k] = {
            "started_offset_s": starts[k] - first,
            "restart_count": rig.restarts(HOST, container),
            # vLLM says on startup how much of the card it took and how big a
            # KV cache it sized. `--enable-sleep-mode` swaps the allocator, so
            # if the flag moves the card figure these lines say why.
            "engine_lines": rig.rig(
                HOST,
                "docker logs " + container + " 2>&1 | grep -iE "
                "'KV cache size|GPU KV cache|memory profiling|Available KV cache|"
                "model weights take|non-torch memory|PyTorch activation peak' | tail -8 || true",
            ),
            "is_sleeping_http": code,
            "tok_s": [round(g["tok_s"], 2) for g in got],
            "ttft_s": [round(g["ttft_s"], 3) for g in got],
            "mean_tok_s": sum(g["tok_s"] for g in got) / len(got) if got else None,
        }
        print(f"    {k}: /is_sleeping -> {code}   decode {per_unit[k]['mean_tok_s']} "
              f"tok/s {per_unit[k]['tok_s']}", flush=True)

    after_mem, after_gpu = rig.meminfo(HOST), rig.gpu(HOST)
    wake = t1 - first
    peak = max((r["vram_used_mib"] for r in rows), default=None)
    print(f"    wake {wake:.1f} s (door-complete minus earliest StartedAt)   "
          f"card peak {peak} / steady {after_gpu['used']} MiB   "
          f"avail {idle_mem['MemAvailable']:.2f} -> {after_mem['MemAvailable']:.2f} GiB",
          flush=True)
    return {
        **spec,
        "label": label,
        "wake_s": wake,
        "idle_avail_gib": idle_mem["MemAvailable"],
        "avail_after_gib": after_mem["MemAvailable"],
        "ram_cost_gib": idle_mem["MemAvailable"] - after_mem["MemAvailable"],
        "idle_vram_used_mib": idle_gpu["used"],
        "vram_peak_used_mib": peak,
        "vram_steady_used_mib": after_gpu["used"],
        "vram_steady_free_mib": after_gpu["free"],
        "per_unit": per_unit,
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
