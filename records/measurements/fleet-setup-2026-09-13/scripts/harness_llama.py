#!/usr/bin/env python3
"""Measure a llama.cpp server in docker: warm decode (short ctx), prefill
(long prompt), card, mem, swap, restarts.

Runs on the rig. Starts a container, waits for health, then:
  * one discarded warm-up (short prompt, n_predict 64);
  * N decode samples (short prompt, n_predict N_PREDICT) -> predicted_per_second;
  * M prefill samples (long prompt, n_predict 16)     -> prompt_per_second.
Reads nvidia-smi / meminfo / vmstat deltas / container restart count.

Exit 0 prints a JSON result. Exit 1 on failure. The container is NOT torn
down here: the caller tears it down so a failure leaves it inspectable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

SHORT_PROMPT = (
    "Write a Python function that reverses a singly linked list in place.\n"
)
LONG_PROMPT = (
    "You are a precise software engineer. Explain step by step how to compute "
    "the size in bytes of every expert weight in a GGUF file, then write a "
    "Python function that opens the file, walks the metadata, and prints a "
    "table of tensor name, shape, and byte size for every tensor that has an "
    "expert dimension. Be complete and correct.\n\n"
)
LONG_PROMPT = (LONG_PROMPT * 28).strip()


def sh(args: list[str], timeout: int = 120) -> str:
    done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if done.returncode != 0:
        raise RuntimeError(f"{args!r} exit {done.returncode}: {done.stderr[:2000]}")
    return done.stdout


def get(path: str, timeout: int = 10) -> str:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{PORT}{path}", timeout=timeout
    ) as resp:
        return resp.read().decode("utf-8")


def post(path: str, payload: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def read_vmstat() -> dict:
    out = sh(["grep", "-E", "^(pswpout|pgmajfault|pgpgin|pgpgout) ", "/proc/vmstat"])
    d = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            d[parts[0]] = int(parts[1])
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--n-predict", type=int, default=256)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--prefill-samples", type=int, default=3)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    global PORT
    PORT = a.port

    cmd = [
        "docker", "run", "-d", "--name", a.name,
        "--gpus", "all", "--network", "host",
        "-v", "/home/adaramir/models:/models:ro",
        "-v", "/home/adaramir/models:/home/adaramir/models:ro",
    ]
    for e in a.env:
        cmd += ["-e", e]
    cmd += ["-e", "LLAMA_ARG_HOST=0.0.0.0", a.image, "--model", a.model]
    cmd += [x for x in a.args if x and x != "--"]
    sh(cmd, timeout=60)

    deadline = time.time() + 600
    health = ""
    while time.time() < deadline:
        try:
            health = get("/health", timeout=5)
            if health.strip() in ("ok", "OK") or '"status":"ok"' in health:
                break
        except (urllib.error.URLError, OSError):
            time.sleep(2.0)
    else:
        raise RuntimeError("server never became healthy")

    vmstat_before = read_vmstat()

    # Discarded warm-up.
    try:
        post("/completion", {"prompt": SHORT_PROMPT, "n_predict": 64, "temperature": 0})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"warm-up failed {exc.code}: {body[:2000]}")

    decode = []
    for _ in range(a.samples):
        body = post(
            "/completion",
            {
                "prompt": SHORT_PROMPT,
                "n_predict": a.n_predict,
                "temperature": 0,
                "cache_prompt": False,
            },
            timeout=900,
        )
        t = body.get("timings") or {}
        decode.append(
            {
                "prompt_n": t.get("prompt_n"),
                "predicted_n": t.get("predicted_n"),
                "predicted_per_second": t.get("predicted_per_second"),
            }
        )

    prefill = []
    for _ in range(a.prefill_samples):
        body = post(
            "/completion",
            {
                "prompt": LONG_PROMPT,
                "n_predict": 16,
                "temperature": 0,
                "cache_prompt": False,
            },
            timeout=900,
        )
        t = body.get("timings") or {}
        prefill.append(
            {
                "prompt_n": t.get("prompt_n"),
                "prompt_ms": t.get("prompt_ms"),
                "prompt_per_second": t.get("prompt_per_second"),
            }
        )

    def read_card() -> str:
        return sh(
            [
                "nvidia-smi", "--query-gpu=memory.used,memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            timeout=30,
        ).strip()

    def read_mem() -> dict:
        out = sh(["grep", "-E", "^(MemTotal|MemAvailable|SwapTotal|SwapFree):", "/proc/meminfo"])
        d = {}
        for line in out.splitlines():
            k, v = line.split(":", 1)
            d[k.strip()] = int(v.strip().split()[0])  # KiB
        return d

    vmstat_after = read_vmstat()
    vmstat_delta = {
        k: vmstat_after.get(k, 0) - vmstat_before.get(k, 0) for k in vmstat_before
    }

    restarts = sh(
        ["docker", "inspect", "-f", "{{.RestartCount}}", a.name], timeout=30
    ).strip()

    result = {
        "container": a.name,
        "image": a.image,
        "model": a.model,
        "args": a.args,
        "env": a.env,
        "port": a.port,
        "n_predict": a.n_predict,
        "samples": a.samples,
        "decode": decode,
        "prefill": prefill,
        "card": read_card(),
        "mem_kib": read_mem(),
        "vmstat_delta": vmstat_delta,
        "restarts": restarts,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
