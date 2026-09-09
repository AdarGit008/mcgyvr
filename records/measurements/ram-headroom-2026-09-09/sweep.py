"""Price the RAM headroom: hold a mapped model fixed and vary the clearance.

One arm = one (model, clearance) pair. The model, its window and its offload are
whatever `emit` chose; the only thing that moves between arms is how much host
RAM a locked balloon is holding, which sets

    clearance = idle MemAvailable - blob

The page cache is dropped before every wake, so each wake is genuinely cold and
the wake times are comparable. Thrash is read off `pgmajfault` during decode
rather than off tok/s: the rig's own throughput drift is ~5% and the fault
counter is not noisy at all.
"""

from __future__ import annotations

import calendar
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/home/adaramir/claude/mcgyvr")
SCR = Path(__file__).resolve().parent
PROMPT = "Write a Python function that merges two sorted lists."
SAMPLES = 3

ARMS_FILE = os.environ.get("MCG_ARMS", "arms.json")
ARMS = json.loads((SCR / ARMS_FILE).read_text())


def sh(cmd: list[str], timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def rig(host: str, script: str, timeout: int = 300) -> str:
    out = sh(["ssh", "-o", "BatchMode=yes", host, script], timeout=timeout)
    return out.stdout.strip()


def meminfo(host: str) -> dict[str, float]:
    raw = rig(host, "cat /proc/meminfo")
    got = {}
    for line in raw.splitlines():
        k, _, v = line.partition(":")
        if k in ("MemTotal", "MemAvailable", "Cached", "Shmem", "SwapFree", "SwapTotal"):
            got[k] = int(v.split()[0]) / (1 << 20)
    return got


def vmstat(host: str) -> dict[str, int]:
    raw = rig(host, "cat /proc/vmstat")
    got = {}
    for line in raw.splitlines():
        k, _, v = line.partition(" ")
        if k in ("pgmajfault", "pswpin", "pswpout", "pgpgin", "pgscan_kswapd", "pgsteal_kswapd"):
            got[k] = int(v)
    return got


def drop_caches(host: str) -> None:
    rig(host, "sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'; sleep 2")


def balloon_down(host: str) -> None:
    rig(host, "sudo pkill -f /tmp/balloon.py; sleep 2; true")


def balloon_up(host: str, gib: float) -> str:
    if gib <= 0.05:
        return "none"
    rig(
        host,
        f"sudo nohup python3 /tmp/balloon.py {gib:.2f} > /tmp/balloon.log 2>&1 &"
        " sleep 1; true",
    )
    for _ in range(120):
        log = rig(host, "cat /tmp/balloon.log 2>/dev/null; true")
        if "READY" in log:
            return log.replace("\n", " | ")
        time.sleep(1)
    raise SystemExit(f"{host}: balloon of {gib:.2f} GiB never reported READY")


def door(direction: str, host: str, compose: str, suffix: str) -> None:
    ev = REPO / "records" / "evidence" / f"2026-09-09-live-{host}"
    stale = ev / f"serve-{direction}.json"
    if stale.exists():
        stale.rename(ev / f"serve-{direction}-{suffix}.json")
    proc = sh(
        [
            "uv", "run", "--no-sync", "python", "-m", "mcgyvr.serving.run",
            "serve", direction, "--host", host, "--compose", compose,
            "--suffix", suffix,
        ],
        timeout=1800,
    )
    (SCR / "logs" / f"door-{direction}-{suffix}.log").write_text(
        proc.stdout + "\n--- stderr ---\n" + proc.stderr
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"DOOR FAILED {direction}/{suffix} rc={proc.returncode}\n"
            + proc.stdout[-1500:] + proc.stderr[-1500:]
        )


def started_at(host: str, container: str) -> str:
    return rig(host, f"docker inspect {container} --format '{{{{.State.StartedAt}}}}'")


def decode(host: str, port: int, label: str) -> float | None:
    body = json.dumps(
        {"prompt": PROMPT, "n_predict": 160, "temperature": 0, "cache_prompt": False}
    )
    proc = sh(
        ["curl", "-s", "-m", "900", f"http://{host}:{port}/completion",
         "-H", "Content-Type: application/json", "-d", body],
        timeout=960,
    )
    try:
        return json.loads(proc.stdout)["timings"]["predicted_per_second"]
    except Exception:
        print(f"    {label}: no timings ({proc.stdout[:120]!r})", flush=True)
        return None


def run_arm(arm: dict) -> dict:
    host, label = arm["host"], arm["label"]
    print(f"\n=== {label}  (balloon {arm['balloon_gib']:.2f} GiB, "
          f"target clearance {arm['clearance_gib']:+.2f} GiB)", flush=True)

    # Tear down with the compose of whatever is actually up, not this arm's.
    # Two models alternating on one port are two container names, and a `down`
    # that names the wrong one leaves the other running -- which gate 7 refuses,
    # correctly: a run that leaves a container it did not name is not green.
    door("down", host, arm.get("down_compose", arm["compose"]), f"{label}-down")
    balloon_down(host)
    drop_caches(host)
    idle = meminfo(host)
    print(f"    idle MemAvailable {idle['MemAvailable']:.2f} GiB", flush=True)

    bl = balloon_up(host, arm["balloon_gib"])
    drop_caches(host)
    before_mem = meminfo(host)
    before_vm = vmstat(host)
    clearance = before_mem["MemAvailable"] - arm["blob_gib"]
    print(f"    balloon: {bl}", flush=True)
    print(f"    MemAvailable {before_mem['MemAvailable']:.2f} GiB "
          f"-> actual clearance {clearance:+.2f} GiB", flush=True)

    t0 = time.time()
    door("up", host, arm["compose"], f"{label}-up")
    t1 = time.time()
    sa = started_at(host, arm["container"])
    try:
        # StartedAt is UTC; mktime would read it as local time and add the offset.
        start_epoch = calendar.timegm(time.strptime(sa[:19], "%Y-%m-%dT%H:%M:%S"))
        wake = t1 - start_epoch
    except Exception:
        wake = t1 - t0
    print(f"    wake {wake:.1f} s  (StartedAt {sa})", flush=True)

    decode(host, arm["port"], "warm-up (discarded)")
    mid_vm = vmstat(host)
    rates = []
    for i in range(SAMPLES):
        r = decode(host, arm["port"], f"sample {i + 1}")
        if r is not None:
            rates.append(r)
            print(f"    sample {i + 1}: {r:.2f} tok/s", flush=True)
    after_vm = vmstat(host)
    after_mem = meminfo(host)
    # The balloon is oom_score_adj 1000, so a host that ran out took it and not
    # the model. That is the safe outcome and a void arm: the clearance the arm
    # claims to have measured stopped being true partway through.
    alive = rig(host, "pgrep -x python3 -a | grep -c balloon.py || true").strip()
    balloon_alive = alive not in ("", "0")
    if arm["balloon_gib"] > 0.05 and not balloon_alive:
        print("    BALLOON DIED — arm is void, the host reclaimed it", flush=True)

    faults = after_vm["pgmajfault"] - mid_vm["pgmajfault"]
    swapin = after_vm["pswpin"] - mid_vm["pswpin"]
    print(f"    decode majfaults {faults}   swapin {swapin}   "
          f"swapout {after_vm['pswpout'] - mid_vm['pswpout']}   "
          f"wake swapin {mid_vm['pswpin'] - before_vm['pswpin']}   "
          f"balloon {'alive' if balloon_alive else 'GONE'}   "
          f"mean {sum(rates) / len(rates) if rates else float('nan'):.2f} tok/s",
          flush=True)

    return {
        **arm,
        "idle_avail_gib": idle["MemAvailable"],
        "avail_before_gib": before_mem["MemAvailable"],
        "actual_clearance_gib": clearance,
        "wake_s": wake,
        "started_at": sa,
        "rates": rates,
        "mean_tok_s": sum(rates) / len(rates) if rates else None,
        "majfault_wake": mid_vm["pgmajfault"] - before_vm["pgmajfault"],
        "majfault_decode": faults,
        "pswpin_wake": mid_vm["pswpin"] - before_vm["pswpin"],
        "pswpout_wake": mid_vm["pswpout"] - before_vm["pswpout"],
        "pswpin_decode": swapin,
        "pswpout_decode": after_vm["pswpout"] - mid_vm["pswpout"],
        "balloon_alive": balloon_alive,
        "mem_after": after_mem,
    }


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    results = []
    out = SCR / "logs" / f"sweep-results-{ARMS_FILE}"
    for arm in ARMS:
        if only and not arm["label"].startswith(only):
            continue
        try:
            results.append(run_arm(arm))
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)
            results.append({**arm, "failed": str(exc)})
        out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    main()
