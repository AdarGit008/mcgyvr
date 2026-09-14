#!/usr/bin/env python3
"""Measure an already-running llama.cpp server: warm decode + prefill + card +
mem + swap + restarts. Run on the rig; the container must already be up."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

SHORT_PROMPT = "Write a Python function that reverses a singly linked list in place.\n"
LONG_PROMPT = (
    "You are a precise software engineer. Explain step by step how to compute "
    "the size in bytes of every expert weight in a GGUF file, then write a "
    "Python function that opens the file, walks the metadata, and prints a "
    "table of tensor name, shape, and byte size for every tensor that has an "
    "expert dimension. Be complete and correct.\n\n"
)
LONG_PROMPT = (LONG_PROMPT * 28).strip()


def sh(args, timeout=120):
    done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if done.returncode != 0:
        raise RuntimeError(f"{args!r} exit {done.returncode}: {done.stderr[:2000]}")
    return done.stdout


def post(port, path, payload, timeout=900):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def read_vmstat():
    out = sh(["grep", "-E", "^(pswpout|pgmajfault|pgpgin|pgpgout) ", "/proc/vmstat"])
    d = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 2:
            d[p[0]] = int(p[1])
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--container", required=True)
    ap.add_argument("--n-predict", type=int, default=256)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--prefill-samples", type=int, default=3)
    ap.add_argument("--out", default="/tmp/measure_running.json")
    a = ap.parse_args()

    # health
    import time
    with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/health", timeout=10) as r:
        r.read()

    vm_before = read_vmstat()
    post(a.port, "/completion", {"prompt": SHORT_PROMPT, "n_predict": 64, "temperature": 0})

    decode = []
    for _ in range(a.samples):
        b = post(a.port, "/completion", {
            "prompt": SHORT_PROMPT, "n_predict": a.n_predict,
            "temperature": 0, "cache_prompt": False,
        })
        t = b.get("timings") or {}
        decode.append({
            "prompt_n": t.get("prompt_n"),
            "predicted_n": t.get("predicted_n"),
            "predicted_per_second": t.get("predicted_per_second"),
        })

    prefill = []
    for _ in range(a.prefill_samples):
        b = post(a.port, "/completion", {
            "prompt": LONG_PROMPT, "n_predict": 16,
            "temperature": 0, "cache_prompt": False,
        })
        t = b.get("timings") or {}
        prefill.append({
            "prompt_n": t.get("prompt_n"),
            "prompt_ms": t.get("prompt_ms"),
            "prompt_per_second": t.get("prompt_per_second"),
        })

    vm_after = read_vmstat()
    card = sh(["nvidia-smi", "--query-gpu=memory.used,memory.free,memory.total",
               "--format=csv,noheader,nounits"], timeout=30).strip()
    mem = {}
    for line in sh(["grep", "-E", "^(MemTotal|MemAvailable|SwapTotal|SwapFree):",
                    "/proc/meminfo"]).splitlines():
        k, v = line.split(":", 1)
        mem[k.strip()] = int(v.strip().split()[0])
    restarts = sh(["docker", "inspect", "-f", "{{.RestartCount}}", a.container],
                  timeout=30).strip()

    result = {
        "container": a.container,
        "port": a.port,
        "decode": decode,
        "prefill": prefill,
        "card": card,
        "mem_kib": mem,
        "vmstat_delta": {k: vm_after.get(k, 0) - vm_before.get(k, 0) for k in vm_before},
        "restarts": restarts,
    }
    with open(a.out, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
