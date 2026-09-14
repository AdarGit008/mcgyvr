#!/usr/bin/env python3
"""Measure a llama.cpp unit's CUDA context (card usage beyond named buffers).

Starts llama-server with --verbose, waits for health, parses the named device
buffer lines (CUDA0 model, KV, compute), reads steady card, and prints
context = steady_card_used - idle_used - (model + KV + compute on CUDA0).

Run on the rig. Tears the container down at the end.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request


def sh(args, timeout=120):
    done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if done.returncode != 0:
        raise RuntimeError(f"{args!r} exit {done.returncode}: {done.stderr[:2000]}")
    return (done.stdout or "") + (done.stderr or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--docker-opt", action="append", default=[])
    ap.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    idle = sh(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]).strip()
    try:
        idle_mib = int(idle.split()[0])
    except (ValueError, IndexError):
        idle_mib = int(idle)

    cmd = ["docker", "run", "-d", "--name", a.name, "--gpus", "all", "--network", "host"]
    for o in a.docker_opt:
        cmd += [o]
    cmd += ["-v", "/home/adaramir/models:/models:ro",
            "-v", "/home/adaramir/models:/home/adaramir/models:ro"]
    for e in a.env:
        cmd += ["-e", e]
    cmd += ["-e", "LLAMA_ARG_HOST=0.0.0.0", a.image, "--model", a.model]
    cmd += [x for x in a.args if x and x != "--"]
    cmd += ["--verbose"]
    sh(cmd, timeout=60)

    deadline = time.time() + 600
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/health", timeout=5) as r:
                if r.read().strip():
                    break
        except (urllib.error.URLError, OSError):
            time.sleep(2.0)
    else:
        raise RuntimeError("never healthy")

    log = sh(["docker", "logs", a.name], timeout=60)
    card = sh(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]).strip()

    def last_mib(pattern):
        found = re.findall(pattern, log)
        if not found:
            return None
        return float(found[-1])

    # Second-pass lines carry the real sizes (the first pass is the fit probe).
    model = last_mib(r"CUDA0 model buffer size =\s*([0-9.]+) MiB")
    kv = last_mib(r"llama_kv_cache: size =\s*([0-9.]+) MiB")
    compute = last_mib(r"CUDA0 compute buffer size =\s*([0-9.]+) MiB")

    steady_mib = float(card.split()[0])
    named = sum(x for x in (model, kv, compute) if x is not None)
    context = steady_mib - idle_mib - named

    result = {
        "container": a.name,
        "idle_used_mib": idle_mib,
        "steady_used_mib": steady_mib,
        "cuda0_model_mib": model,
        "cuda0_kv_mib": kv,
        "cuda0_compute_mib": compute,
        "named_sum_mib": round(named, 2),
        "context_mib": round(context, 2),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    sh(["docker", "rm", "-f", a.name], timeout=60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
