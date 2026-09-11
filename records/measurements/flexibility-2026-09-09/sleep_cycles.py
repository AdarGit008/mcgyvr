"""Q15's second half — what three sleep/wake cycles leave on the card.

Q15's four wake arms landed; the cycles that were to follow each one never ran.
This is those cycles, on fresh cold starts of the same compose, so the wake half
gains four more samples as a side effect.

Three questions, all read **per process** rather than off the card total,
because a card total cannot say which unit a MiB belongs to:

* **What does each unit keep while asleep, and does it grow with cycling?**
  477 and 503 MiB of residual CUDA context are both on record, n=1 each, with
  no mechanism. Three cycles per arm, four arms.
* **Do the derived releases match M6's measured ones?** ``V_awake`` less the
  asleep residual gives 3,582 / 6,582 MiB; M6 measured 3,562 / 6,562 directly —
  a 20 MiB disagreement the size of Q11's margin.
* **Does anything come back wrong?** One decode per unit after every wake.

Per-process attribution maps each ``nvidia-smi`` compute pid to its container
through ``/proc/<pid>/cgroup``, on the rig, so a figure is never assigned to a
unit by guessing from its size.

**The compose is Q15's, unchanged** — including its ``condition:
service_started``, which is why the 3B restarts once on every cold start. The
freeze's ``service_healthy`` never reached this hand-written file, and fixing it
here would make these four cold starts incomparable with Q15's.

Sleeps go through ``POST /sleep?level=2`` on the campaign's own transport, as
M6 did. ``servelib.sleep`` is still asked for level 1 once per arm, to check
the ban fires before any transport is touched.
"""

from __future__ import annotations

import calendar
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/adaramir/claude/mcgyvr/src")

import rig  # noqa: E402
from mcgyvr.serving import servelib  # noqa: E402

HOST = "srv2"
PAIR = str(Path(__file__).resolve().parent / "compose.srv2.sleepmode.yml")
UNITS = {
    "3b": ("mcgyvr-srv2-Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001", 8001,
           "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"),
    "7b": ("mcgyvr-srv2-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002", 8002,
           "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"),
}
ARMS = 4
CYCLES = 3
OUT = rig.SCR / "results-q15-cycles.json"

PER_PROCESS = r"""
for id in $(docker ps -q); do
  echo "C $(docker inspect --format '{{.Id}} {{.Name}}' $id | tr -d /)"
done
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | while IFS=, read pid mem; do
  pid=$(echo $pid | tr -d ' '); mem=$(echo $mem | tr -d ' ')
  echo "P $pid $mem $(tr '\n' ' ' < /proc/$pid/cgroup 2>/dev/null)"
done
"""


def per_unit_card() -> dict[str, int]:
    """Card MiB per unit, attributed by cgroup; an unattributed pid is kept by pid."""
    names: dict[str, str] = {}
    procs: list[tuple[str, int, str]] = []
    for line in rig.rig(HOST, PER_PROCESS).splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "C":
            names[parts[1]] = parts[2]
        elif len(parts) >= 3 and parts[0] == "P":
            procs.append((parts[1], int(parts[2]), " ".join(parts[3:])))
    out: dict[str, int] = {}
    for pid, mem, cgroup in procs:
        owner = next((n for full, n in names.items() if full in cgroup), f"pid-{pid}")
        key = next((k for k, (c, _, _) in UNITS.items() if c == owner), owner)
        out[key] = out.get(key, 0) + mem
    return out


def post(port: int, path: str) -> tuple[str, float]:
    t0 = time.time()
    code, _ = rig.http(HOST, port, path, method="POST", timeout=300)
    return code, round(time.time() - t0, 3)


def is_sleeping(port: int) -> str:
    return rig.http(HOST, port, "/is_sleeping", timeout=20)[1].strip()[:40]


def tok(key: str) -> float | None:
    _, port, model = UNITS[key]
    got = rig.decode_vllm(HOST, port, model)
    return round(got["tok_s"], 2) if got else None


def note(steps: list[dict], step: str, **kw: object) -> dict:
    g, m = rig.gpu(HOST), rig.meminfo(HOST)
    row = {
        "step": step,
        "card_used_mib": g["used"],
        "card_free_mib": g["free"],
        "per_unit_mib": per_unit_card(),
        "avail_gib": round(m["MemAvailable"], 3),
        "sleeping": {k: is_sleeping(p) for k, (_, p, _) in UNITS.items()},
        **kw,
    }
    steps.append(row)
    print(f"    [{step:11s}] card {g['used']:5d} used / {g['free']:5d} free   "
          f"per-unit {row['per_unit_mib']}   avail {row['avail_gib']:.2f}G   "
          f"sleeping {row['sleeping']}   "
          + " ".join(f"{k}={v}" for k, v in kw.items()), flush=True)
    return row


def teardown() -> None:
    running = rig.rig(HOST, "docker ps -a --format '{{.Names}}' | grep '^mcgyvr-' || true")
    if not running.strip():
        return
    compose = rig.last_up(HOST)
    if not compose:
        raise SystemExit(f"{HOST}: {running.split()} are up and nothing names their file")
    rig.door_or_die("down", HOST, compose, f"q15ctd-{int(time.time() * 10) % 10**9}")


def started(container: str) -> float:
    sa = rig.started_at(HOST, container)
    return calendar.timegm(time.strptime(sa[:19], "%Y-%m-%dT%H:%M:%S"))


def arm(i: int) -> dict:
    label = f"q15c-sleepmode-{i}"
    print(f"\n=== {label}", flush=True)
    teardown()
    rig.balloon_down(HOST)
    rig.drop_caches(HOST)

    rig.sample_start(HOST)
    proc = rig.door("up", HOST, PAIR, f"{label}-up")
    t_done = time.time()
    rows = rig.sample_stop(HOST, label)
    if proc.returncode != 0:
        raise SystemExit(f"door up rc={proc.returncode}\n{proc.stderr[-800:]}")
    rig.note_up(HOST, PAIR)
    starts = {k: started(c) for k, (c, _, _) in UNITS.items()}
    restarts = {k: rig.restarts(HOST, c) for k, (c, _, _) in UNITS.items()}

    banned = None
    try:
        servelib.sleep(HOST, UNITS["3b"][1], level=1)
    except servelib.SleepLevelError as exc:
        banned = str(exc)[:160]
    if banned is None:
        raise SystemExit("a level-1 sleep was NOT refused; the ban is not holding")

    steps: list[dict] = []
    note(steps, "serving-0", decode={k: tok(k) for k in UNITS})
    cycles = []
    for c in range(1, CYCLES + 1):
        slept = {k: post(p, "/sleep?level=2") for k, (_, p, _) in UNITS.items()}
        time.sleep(3)
        asleep = note(steps, f"asleep-{c}",
                      sleep_s={k: v[1] for k, v in slept.items()},
                      sleep_http={k: v[0] for k, v in slept.items()})
        woke = {k: post(p, "/wake_up") for k, (_, p, _) in UNITS.items()}
        time.sleep(3)
        awake = note(steps, f"serving-{c}",
                     wake_s={k: v[1] for k, v in woke.items()},
                     wake_http={k: v[0] for k, v in woke.items()},
                     decode={k: tok(k) for k in UNITS})
        cycles.append({
            "cycle": c,
            "asleep_mib": asleep["per_unit_mib"],
            "serving_mib": awake["per_unit_mib"],
            "released_mib": {
                k: awake["per_unit_mib"].get(k, 0) - asleep["per_unit_mib"].get(k, 0)
                for k in UNITS
            },
            "sleep_s": {k: v[1] for k, v in slept.items()},
            "wake_s": {k: v[1] for k, v in woke.items()},
        })

    return {
        "label": label,
        "wake_s": t_done - min(starts.values()),
        "started_offset_s": {k: v - min(starts.values()) for k, v in starts.items()},
        "restart_count": restarts,
        "vram_peak_used_mib": max((r["vram_used_mib"] for r in rows), default=None),
        "level_one_refused": banned,
        "cycles": cycles,
        "steps": steps,
    }


def main() -> None:
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    for i in range(1, ARMS + 1):
        try:
            results.append(arm(i))
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)
            results.append({"label": f"q15c-sleepmode-{i}", "failed": str(exc)})
        OUT.write_text(json.dumps(results, indent=2))
    teardown()
    print(f"\nwrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
