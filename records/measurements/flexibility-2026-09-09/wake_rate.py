"""One arm = one cold wake of one llama.cpp unit, timed from `StartedAt`.

`r(host, llama.cpp)` is the coefficient the whole per-unit wake budget rests on
and it is fitted from **two** blobs on srv1 and **one** on srv2
(`records/plans/wake-timeout.md` §4). Two points define a line only if you
already know it goes through the origin, and the two-point fit *with* an
intercept is `r = 0.0728 GiB/s, a = -28.2 s` — unphysical, which is the only
reason the proportional form was chosen. A third and fourth blob decides it.

Each arm: tear down whatever is up on the host, drop the page cache so the wake
is genuinely cold, start the 1 Hz card/RAM sampler, `serve up` through the
door, read the container's own `StartedAt` (UTC, `calendar.timegm`), then one
decode to prove it serves rather than merely answers.

Arms come from a JSON file: host, label, compose, container, port, blob_gib,
and how many repeats.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import rig

ARMS = json.loads((rig.SCR / sys.argv[1]).read_text())
OUT = rig.SCR / (os.environ.get("MCG_OUT") or f"results-{Path(sys.argv[1]).stem}.json")


def teardown(host: str, expect_gone: str | None = None) -> None:
    """Bring down whatever is actually up, by the compose that names it.

    `serve down` names one container; a `down` run with the wrong file leaves
    the other running and gate 7 refuses the next run — correctly. So the file
    is chosen from what `docker ps` says, never from the arm about to start.
    """
    running = rig.rig(host, "docker ps --format '{{.Names}}' | grep '^mcgyvr-' || true")
    names = [n for n in running.split() if n]
    if not names:
        return
    index = json.loads((rig.SCR / "teardown-index.json").read_text())
    wanted: list[str] = []
    remembered = rig.last_up(host)
    if remembered:
        # The file that started these units, not merely a file that names
        # them: the sleep-mode pair and the production pair share every
        # container name and differ only in argv.
        wanted.append(remembered)
    else:
        for name in names:
            compose = index.get(name)
            if compose is None:
                raise SystemExit(
                    f"{host}: {name} is up and no compose in teardown-index.json names it; "
                    "add it rather than killing the container behind the door's back"
                )
            # Co-residents share one file; alternatives do not. Dedupe on the
            # file, so a pair comes down once and two alternatives twice.
            if compose not in wanted:
                wanted.append(compose)
    for compose in wanted:
        stem = Path(compose).parent.name[-20:]
        rig.door_or_die("down", host, compose, f"td-{stem}-{int(time.time())}")
    if expect_gone:
        still = rig.rig(host, f"docker ps --format '{{{{.Names}}}}' | grep -c {expect_gone} || true")
        if still.strip() not in ("", "0"):
            raise SystemExit(f"{host}: {expect_gone} survived the teardown")


def arm(spec: dict, index: int) -> dict:
    host, label = spec["host"], f"{spec['label']}-{index}"
    print(f"\n=== {label}  blob {spec['blob_gib']:.2f} GiB", flush=True)
    teardown(host)
    rig.balloon_down(host)
    if spec.get("balloon_gib"):
        pass  # ballooned after the caches are dropped, below
    rig.drop_caches(host)
    idle_mem, idle_gpu = rig.meminfo(host), rig.gpu(host)
    balloon = "none"
    if spec.get("balloon_gib"):
        balloon = rig.balloon_up(host, spec["balloon_gib"])
        rig.drop_caches(host)
    before_mem, before_vm = rig.meminfo(host), rig.vmstat(host)
    clearance = before_mem["MemAvailable"] - spec["blob_gib"]
    print(f"    idle avail {idle_mem['MemAvailable']:.2f} -> before "
          f"{before_mem['MemAvailable']:.2f} GiB, clearance {clearance:+.2f}, "
          f"card free {idle_gpu['free']} MiB", flush=True)

    rig.sample_start(host)
    proc = rig.door("up", host, spec["compose"], f"{label}-up")
    t1 = time.time()
    if proc.returncode != 0:
        log = rig.rig(host, f"docker logs --tail 40 {spec['container']} 2>&1 || true")
        rows = rig.sample_stop(host, label)
        (rig.LOGS / f"crash-{label}.log").write_text(log)
        raise SystemExit(
            f"door up rc={proc.returncode}; container log tail:\n{log[-1500:]}"
        )
    rig.note_up(host, spec["compose"])
    wake = rig.wake_from(host, spec["container"], t1)
    time.sleep(2)
    rows = rig.sample_stop(host, label)
    rate = rig.decode_llamacpp(host, spec["port"])
    warm = rig.decode_llamacpp_warm(host, spec["port"])
    after_mem, after_vm, after_gpu = rig.meminfo(host), rig.vmstat(host), rig.gpu(host)
    peak = max((r["vram_used_mib"] for r in rows), default=None)
    warm_mean = warm["mean"] if warm else None
    print(f"    wake {wake:.1f} s   {spec['blob_gib'] / wake:.4f} GiB/s   "
          f"decode cold {rate} / warm {warm_mean}   "
          f"card peak {peak} / steady {after_gpu['used']} MiB   "
          f"({len(rows)} samples)", flush=True)
    return {
        **spec,
        "label": label,
        "balloon": balloon,
        "idle_avail_gib": idle_mem["MemAvailable"],
        "avail_before_gib": before_mem["MemAvailable"],
        "clearance_vs_blob_gib": clearance,
        "wake_s": wake,
        "gib_per_s": spec["blob_gib"] / wake,
        "vram_peak_used_mib": peak,
        "vram_steady_used_mib": after_gpu["used"],
        "vram_idle_free_mib": idle_gpu["free"],
        "shmem_steady_gib": after_mem["Shmem"],
        "avail_after_gib": after_mem["MemAvailable"],
        "decode_tok_s": rate,
        "decode_warm": warm,
        "restart_count": rig.restarts(host, spec["container"]),
        "pgmajfault_wake": after_vm["pgmajfault"] - before_vm["pgmajfault"],
        "pswpout_wake": after_vm["pswpout"] - before_vm["pswpout"],
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
