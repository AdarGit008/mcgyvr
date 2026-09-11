"""Two llama.cpp MoE units on one host: is host RAM additive?

`hold_together` sums host RAM per host as of commit `6a2e80d4`, and the
docstring says so itself: *"it is not measured: nothing on this fleet has run
two llama.cpp MoE units co-resident on one host"*. This runs them.

Both units are launched `--load-mode none` with every expert block off the
card, because that is the only arm in which a unit *allocates* host memory
rather than asking the kernel to cache a blob. Two mapped units share one page
cache and their blobs are not additive in any interesting sense; two unmapped
units hold two disjoint `Shmem` allocations, and whether those sum is the
question.

Three arms: each alone, then both. The additivity test is

    Shmem(both)  ==  Shmem(a alone) + Shmem(b alone)   ?

read against the same idle baseline, with the page cache dropped before each.
"""

from __future__ import annotations

import json
import sys
import time

import rig

HOST = "srv2"
D = str(rig.SCR)
ARMS = [
    {"label": "m2-deepseek-alone", "compose": f"{D}/compose.srv2.m2-deepseek-coder-v2-16b-8080.yml",
     "units": [("mcgyvr-srv2-deepseek-coder-v2-16b-8080", 8080)], "experts_gib": 7.54},
    {"label": "m2-qwen36-alone", "compose": f"{D}/compose.srv2.m2-Qwen3.6-35B-A3B-UD-IQ3_XXS-8081.yml",
     "units": [("mcgyvr-srv2-Qwen3.6-35B-A3B-UD-IQ3_XXS-8081", 8081)], "experts_gib": 10.35},
    {"label": "m2-both", "compose": f"{D}/compose.srv2.m2-both.yml",
     "units": [("mcgyvr-srv2-deepseek-coder-v2-16b-8080", 8080),
               ("mcgyvr-srv2-Qwen3.6-35B-A3B-UD-IQ3_XXS-8081", 8081)],
     "experts_gib": 7.54 + 10.35},
]
OUT = rig.SCR / "m2-coresidency.json"


def teardown() -> None:
    running = rig.rig(HOST, "docker ps --format '{{.Names}}' | grep '^mcgyvr-' || true")
    if not running.strip():
        return
    remembered = rig.last_up(HOST)
    if not remembered:
        raise SystemExit(f"{HOST}: {running!r} is up and nothing remembers its compose")
    rig.door_or_die("down", HOST, remembered, f"m2td-{int(time.time()) % 10**6}")


def arm(spec: dict) -> dict:
    label = spec["label"]
    print(f"\n=== {label}", flush=True)
    teardown()
    rig.balloon_down(HOST)
    rig.drop_caches(HOST)
    idle = rig.meminfo(HOST)
    idle_gpu = rig.gpu(HOST)
    print(f"    idle avail {idle['MemAvailable']:.2f} GiB  Shmem {idle['Shmem']:.2f}  "
          f"card {idle_gpu['used']} used", flush=True)
    t0 = time.time()
    # The previous campaign used these same labels on this same date, and
    # gate 5 is write-once: a RUN_ID minted before is refused, correctly.
    proc = rig.door("up", HOST, spec["compose"], f"{label}-up-{int(time.time()) % 10**6}")
    t1 = time.time()
    if proc.returncode != 0:
        logs = {c: rig.rig(HOST, f"docker logs --tail 30 {c} 2>&1 || true")
                for c, _ in spec["units"]}
        (rig.LOGS / f"crash-{label}.log").write_text(json.dumps(logs, indent=1))
        raise SystemExit(f"door up rc={proc.returncode}; see crash-{label}.log")
    rig.note_up(HOST, spec["compose"])
    wake = rig.wake_from(HOST, spec["units"][0][0], t1)
    after = rig.meminfo(HOST)
    gpu = rig.gpu(HOST)
    rates = {}
    for container, port in spec["units"]:
        rates[port] = rig.decode_llamacpp(HOST, port)
    print(f"    wake {wake:.1f} s   avail {idle['MemAvailable']:.2f} -> "
          f"{after['MemAvailable']:.2f}   Shmem {idle['Shmem']:.2f} -> {after['Shmem']:.2f}   "
          f"card {gpu['used']} MiB   decode {rates}", flush=True)
    return {
        **{k: v for k, v in spec.items() if k != "units"},
        "containers": [c for c, _ in spec["units"]],
        "idle_avail_gib": idle["MemAvailable"],
        "idle_shmem_gib": idle["Shmem"],
        "after_avail_gib": after["MemAvailable"],
        "after_shmem_gib": after["Shmem"],
        "shmem_delta_gib": after["Shmem"] - idle["Shmem"],
        "avail_delta_gib": idle["MemAvailable"] - after["MemAvailable"],
        "vram_used_mib": gpu["used"],
        "vram_free_mib": gpu["free"],
        "wake_s": wake,
        "door_wall_s": t1 - t0,
        "decode_tok_s": rates,
    }


def main() -> None:
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    only = sys.argv[1:] or None
    for spec in ARMS:
        if only and spec["label"] not in only:
            continue
        try:
            results.append(arm(spec))
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)
            results.append({"label": spec["label"], "failed": str(exc)})
        OUT.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
