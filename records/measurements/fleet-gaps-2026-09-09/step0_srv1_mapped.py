"""Step 0: re-emit srv1 and restart it mapped, and price the mode on the card.

Commit `6a2e80d4` dropped the mode gate from 2.0 to 0.5 GiB, so `emit` now
places srv1's Qwen3.6 **mapped** — the file on disk still carries
`--load-mode none` and `emit --check` exits 4. The owner approved re-emitting
and restarting.

The restart is also the cheapest arm in this campaign for **G1**, the loading
mode's VRAM cost. `emit` writes the *same* `--n-cpu-moe 30` either way — the
only line that moves is `--load-mode none` — so the two launches are a matched
pair on the card, which is the axis nobody has read. A 1 Hz sampler runs across
each load so the **peak** allocation is visible and not only the steady state:
srv2's 80B fails during load on a CUDA allocation, and a steady-state read
cannot see a peak.

Usage: `uv run --no-sync python step0_srv1_mapped.py <arm> [<arm> ...]`
where an arm is `mapped` or `unmapped`; the first `mapped` also re-emits.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import rig

HOST = "srv1"
PORT = 8080
CONTAINER = "mcgyvr-srv1-Qwen3.6-35B-A3B-UD-IQ3_XXS-8080"
LIVE = Path("/home/adaramir/.mcgyvr/config/compose.srv1.yml")
UNMAPPED = rig.SCR / "compose.srv1.unmapped-as-found.yml"
BLOB_GIB = 13211155424 / (1 << 30)  # 12.30 GiB, the file on the rig
SAMPLES = 3


def measure_live(tag: str) -> dict:
    """What the unit that is up right now is holding, and what it decodes at."""
    out = {
        "tag": tag,
        "gpu": rig.gpu(HOST),
        "mem": rig.meminfo(HOST),
        "rates": [],
    }
    rig.decode_llamacpp(HOST, PORT)  # warm-up, discarded
    for _ in range(SAMPLES):
        r = rig.decode_llamacpp(HOST, PORT)
        if r is not None:
            out["rates"].append(r)
    out["mean_tok_s"] = (
        sum(out["rates"]) / len(out["rates"]) if out["rates"] else None
    )
    return out


def arm(mode: str, index: int, emit_first: bool) -> dict:
    label = f"m1-srv1-{mode}-{index}"
    print(f"\n=== {label}", flush=True)
    compose = str(LIVE if mode == "mapped" else UNMAPPED)

    # Tear down whatever is up. Both composes name the same container, so
    # either file finds it -- but use the file that matches what is running.
    up_now = rig.rig(HOST, f"docker ps --format '{{{{.Names}}}}' | grep -c {CONTAINER} || true")
    if up_now.strip() not in ("", "0"):
        prev = rig.rig(HOST, f"docker inspect {CONTAINER} --format '{{{{json .Config.Cmd}}}}'")
        down_compose = UNMAPPED if "--load-mode" in prev else LIVE
        rig.door_or_die("down", HOST, str(down_compose), f"{label}-down")
    rig.balloon_down(HOST)
    rig.drop_caches(HOST)
    idle = rig.meminfo(HOST)
    idle_gpu = rig.gpu(HOST)
    print(f"    idle MemAvailable {idle['MemAvailable']:.2f} GiB, "
          f"card free {idle_gpu['free']} MiB", flush=True)

    if emit_first:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(LIVE, LIVE.with_suffix(f".yml.bak-{stamp}"))
        proc = rig.sh(
            ["uv", "run", "--no-sync", "python", "-m", "mcgyvr.cli", "emit",
             "--out", str(LIVE.parent)],
            timeout=300,
        )
        print("    emit rc=%d\n%s" % (proc.returncode, proc.stdout[-800:]), flush=True)
        if proc.returncode != 0:
            raise SystemExit("emit failed: " + proc.stderr[-2000:])
        shutil.copy2(LIVE, rig.SCR / "compose.srv1.mapped-emitted.yml")

    before_vm = rig.vmstat(HOST)
    rig.sample_start(HOST)
    t0 = time.time()
    rig.door_or_die("up", HOST, compose, f"{label}-up")
    t1 = time.time()
    wake = rig.wake_from(HOST, CONTAINER, t1)
    time.sleep(3)
    rows = rig.sample_stop(HOST, label)
    print(f"    wake {wake:.1f} s   ({len(rows)} samples)", flush=True)

    live = measure_live(label)
    after_vm = rig.vmstat(HOST)
    peak_used = max((r["vram_used_mib"] for r in rows), default=None)
    min_free = min((r["vram_free_mib"] for r in rows), default=None)
    peak_shmem = max((r["shmem_kib"] for r in rows), default=0) / (1 << 20)
    print(f"    card: peak used {peak_used} MiB, min free {min_free} MiB, "
          f"steady used {live['gpu']['used']} MiB", flush=True)
    print(f"    host: peak Shmem {peak_shmem:.2f} GiB, steady Shmem "
          f"{live['mem']['Shmem']:.2f} GiB, avail {live['mem']['MemAvailable']:.2f}",
          flush=True)
    print(f"    decode {live['mean_tok_s']} tok/s  {live['rates']}", flush=True)

    return {
        "label": label,
        "mode": mode,
        "blob_gib": BLOB_GIB,
        "idle_mem": idle,
        "idle_gpu": idle_gpu,
        "wake_s": wake,
        "vram_peak_used_mib": peak_used,
        "vram_min_free_mib": min_free,
        "vram_steady_used_mib": live["gpu"]["used"],
        "vram_steady_free_mib": live["gpu"]["free"],
        "shmem_peak_gib": peak_shmem,
        "shmem_steady_gib": live["mem"]["Shmem"],
        "avail_steady_gib": live["mem"]["MemAvailable"],
        "rates": live["rates"],
        "mean_tok_s": live["mean_tok_s"],
        "pgmajfault_wake": after_vm["pgmajfault"] - before_vm["pgmajfault"],
        "pswpout_wake": after_vm["pswpout"] - before_vm["pswpout"],
        "samples": len(rows),
    }


def main() -> None:
    plan = sys.argv[1:] or ["mapped"]
    out = rig.SCR / "m1-srv1-mode-vram.json"
    results = json.loads(out.read_text()) if out.exists() else []
    seen_mapped = any(r.get("mode") == "mapped" for r in results)
    counts: dict[str, int] = {}
    for spec in plan:
        counts[spec] = counts.get(spec, 0) + 1
        n = counts[spec] + sum(1 for r in results if r.get("mode") == spec)
        try:
            results.append(arm(spec, n, emit_first=(spec == "mapped" and not seen_mapped)))
            seen_mapped = seen_mapped or spec == "mapped"
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)
            results.append({"label": f"m1-srv1-{spec}-{n}", "mode": spec, "failed": str(exc)})
        out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    main()
