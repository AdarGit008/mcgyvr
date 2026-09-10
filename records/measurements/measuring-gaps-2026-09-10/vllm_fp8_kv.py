"""Q2 — vLLM fp8 KV: the actual pool on the refused cell, and the margin.

A vLLM cold-start A/B with `--kv-cache-dtype` toggled by the compose (fp16
control vs fp8). One model (`thewimo/Qwen3-4B-AWQ`, the "q34b" of the vLLM
records), n=2 each side. Every arm reads the engine's own pool lines from the
full container log:

    GPU KV cache size: N tokens
    Maximum concurrency for <N> tokens per request: <X.xx>x

plus the steady card and one warm decode — because fp8 KV is **not free**: on
Ampere it swaps FLASH_ATTN for FLASHINFER, and the decode figure must not be
attributed to the pool alone (`okf/must-read/touching-engine.md`).

Model on `vllm_arms.py`; arms JSON (argv[1]) is
`records/measurements/measuring-gaps-2026-09-10/arms-q2-vllm-fp8.json`.

A launch near the memory edge fails intermittently (one in three on a
verified-empty card); retry once before recording a failure.
"""

from __future__ import annotations

import calendar
import json
import os
import re
import sys
import time

import rig

ARMS = json.loads((rig.SCR / sys.argv[1]).read_text())
OUT = rig.SCR / (os.environ.get("MCG_OUT") or "results-q2-vllm-fp8.json")
#: Warm decode: one discarded warm-up, then this many measured samples whose
#: mean is recorded as `tok_s` / `ttft_s` (the plan's "one warm decode").
DECODE_SAMPLES = 3

#: The two lines vLLM prints at startup that state the pool and its concurrency.
POOL_RE = re.compile(
    r"GPU KV cache size: [\d,]+ tokens"
    r"|Maximum concurrency for [\d,]+ tokens per request: [\d.]+x"
)
KV_TOK_RE = re.compile(r"GPU KV cache size: ([\d,]+) tokens")
MAXCONC_RE = re.compile(
    r"Maximum concurrency for [\d,]+ tokens per request: ([\d.]+)x"
)


def teardown(host: str) -> None:
    running = rig.rig(
        host, "docker ps -a --format '{{.Names}}' | grep '^mcgyvr-' || true"
    )
    names = [n for n in running.split() if n]
    if not names:
        return
    index = json.loads((rig.SCR / "teardown-index.json").read_text())
    wanted: list[str] = []
    remembered = rig.last_up(host)
    if remembered:
        # The file that started these units, not a file that merely names
        # them: two composes can name the same container with different argv.
        wanted.append(remembered)
    else:
        for name in names:
            compose = index.get(name)
            if compose is None:
                raise SystemExit(f"{host}: {name} is up and nothing names it")
            if compose not in wanted:
                wanted.append(compose)
    for compose in wanted:
        rig.door_or_die("down", host, compose, f"td-{int(time.time() * 10) % 10**9}")


def started(host: str, container: str) -> float:
    sa = rig.started_at(host, container)
    return calendar.timegm(time.strptime(sa[:19], "%Y-%m-%dT%H:%M:%S"))


def arm(spec: dict, index: int) -> dict:
    label = f"{spec['label']}-{index}"
    host = spec["host"]
    container = spec["container"]
    port = spec["port"]
    model = spec["model"]
    print(f"\n=== {label}  {model}  kv={spec['kv_dtype']}", flush=True)

    teardown(host)
    # A balloon outlives the block that raised it; drop it at the head of
    # every arm so a stale 4.9 GiB never rides into a host figure.
    rig.balloon_down(host)
    rig.drop_caches(host)
    idle_mem, idle_gpu = rig.meminfo(host), rig.gpu(host)
    print(f"    idle avail {idle_mem['MemAvailable']:.2f} GiB, "
          f"card {idle_gpu['used']} used / {idle_gpu['free']} free MiB", flush=True)

    rig.sample_start(host)
    proc = rig.door("up", host, spec["compose"], f"{label}-up")
    t1 = time.time()
    if proc.returncode != 0:
        # Near the memory edge the first launch is a coin flip — retry once
        # before believing the refusal (vllm.md: "retry before believing a
        # refusal").
        rig.sample_stop(host, label)
        print("    door up failed; retrying once", flush=True)
        teardown(host)
        rig.sample_start(host)
        proc = rig.door("up", host, spec["compose"], f"{label}-up-retry")
        t1 = time.time()
        if proc.returncode != 0:
            log = rig.rig(host, f"docker logs {container} 2>&1 || true")
            rig.sample_stop(host, label)
            (rig.LOGS / f"crash-{label}.log").write_text(log)
            raise SystemExit(f"door up rc={proc.returncode}; see crash-{label}.log")
    rig.note_up(host, spec["compose"])
    st = started(host, container)
    time.sleep(2)
    rows = rig.sample_stop(host, label)

    # Full container log off-rig, then parse the pool lines locally — never
    # `grep | tail -1` on the rig.
    log = rig.rig(host, f"docker logs {container} 2>&1 || true")
    (rig.LOGS / f"{label}.log").write_text(log)

    m1 = KV_TOK_RE.search(log)
    m2 = MAXCONC_RE.search(log)
    kv_tokens = int(m1.group(1).replace(",", "")) if m1 else None
    maxconc = float(m2.group(1)) if m2 else None
    pool_lines = POOL_RE.findall(log)

    # Warm decode: one discarded warm-up, then the mean of the samples.
    rig.decode_vllm(host, port, model)  # discarded warm-up
    got = [rig.decode_vllm(host, port, model) for _ in range(DECODE_SAMPLES)]
    got = [g for g in got if g]
    tok_s = sum(g["tok_s"] for g in got) / len(got) if got else None
    ttft_s = sum(g["ttft_s"] for g in got) / len(got) if got else None

    after_mem, after_gpu = rig.meminfo(host), rig.gpu(host)
    wake = t1 - st
    peak = max((r["vram_used_mib"] for r in rows), default=None)
    print(f"    wake {wake:.1f} s  pool {kv_tokens} tok  maxconc {maxconc}  "
          f"card {after_gpu['used']} MiB  decode {tok_s} tok/s", flush=True)
    return {
        **spec,
        "label": label,
        "wake_s": wake,
        "vram_peak_used_mib": peak,
        "vram_steady_used_mib": after_gpu["used"],
        "vram_idle_free_mib": idle_gpu["free"],
        "kv_tokens": kv_tokens,
        "maxconc": maxconc,
        "pool_lines": pool_lines,
        "tok_s": round(tok_s, 2) if tok_s is not None else None,
        "ttft_s": round(ttft_s, 3) if ttft_s is not None else None,
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
                results.append({**spec, "label": f"{spec['label']}-{i}",
                                "failed": str(exc)})
            OUT.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
