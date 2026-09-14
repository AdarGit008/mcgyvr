#!/usr/bin/env python3
"""Measure an already-running vLLM OpenAI server: warm decode, prefill, card,
restarts, attention backend. Run on the rig.

Decode: POST /v1/chat/completions, max_tokens 256, temperature 0, one fixed
message. Prefill: a long prompt, max_tokens 16. Decode tok/s is
completion_tokens / (wall seconds); prefill tok/s is prompt_tokens / TTFT.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request

SHORT = [{"role": "user", "content": "Write a Python function that reverses a singly linked list in place.\n"}]
LONG = (
    "You are a precise software engineer. Explain step by step how to compute "
    "the size in bytes of every expert weight in a GGUF file, then write a "
    "Python function that opens the file, walks the metadata, and prints a "
    "table of tensor name, shape, and byte size for every tensor that has an "
    "expert dimension. Be complete and correct.\n\n"
) * 28


def sh(args, timeout=120):
    done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if done.returncode != 0:
        raise RuntimeError(f"{args!r} exit {done.returncode}: {done.stderr[:2000]}")
    return done.stdout


def post(port, payload, timeout=900):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--prefill-samples", type=int, default=3)
    ap.add_argument("--out", default="/tmp/measure_vllm.json")
    a = ap.parse_args()

    with urllib.request.urlopen(f"http://127.0.0.1:{a.port}/v1/models", timeout=10) as r:
        models = json.loads(r.read().decode())
    model = models["data"][0]["id"]

    # discarded warm-up
    post(a.port, {"model": model, "messages": SHORT, "max_tokens": 64,
                  "temperature": 0, "ignore_eos": False})

    decode = []
    for _ in range(a.samples):
        t0 = time.perf_counter()
        b = post(a.port, {"model": model, "messages": SHORT, "max_tokens": 256,
                          "temperature": 0, "ignore_eos": True})
        dt = time.perf_counter() - t0
        usage = b.get("usage") or {}
        ct = usage.get("completion_tokens", 0)
        decode.append({"completion_tokens": ct, "wall_s": round(dt, 3),
                       "tok_s": round(ct / dt, 3) if dt > 0 else None})

    prefill = []
    for _ in range(a.prefill_samples):
        t0 = time.perf_counter()
        b = post(a.port, {"model": model, "messages": [{"role": "user", "content": LONG}],
                          "max_tokens": 16, "temperature": 0, "ignore_eos": False})
        dt = time.perf_counter() - t0
        usage = b.get("usage") or {}
        pt = usage.get("prompt_tokens", 0)
        prefill.append({"prompt_tokens": pt, "ttft_s": round(dt, 3),
                        "tok_s": round(pt / dt, 3) if dt > 0 else None})

    card = sh(["nvidia-smi", "--query-gpu=memory.used,memory.free,memory.total",
               "--format=csv,noheader,nounits"], timeout=30).strip()
    restarts = sh(["docker", "inspect", "-f", "{{.RestartCount}}", a.container],
                  timeout=30).strip()
    log = sh(["docker", "logs", a.container], timeout=120)
    backend = None
    for line in log.splitlines():
        if "attention_backend" in line or "Attention backend" in line:
            backend = line.strip()[-400:]
            break
    # vLLM v0.26 logs e.g. "Using attention backend: FLASH_ATTN" — capture the token
    for tok in ("FLASH_ATTN", "FLASHINFER", "TRITON_ATTN", "FLASH_ATTENTION"):
        if tok in log:
            backend = tok
            break

    result = {
        "port": a.port, "container": a.container, "model": model,
        "decode": decode, "prefill": prefill, "card": card,
        "restarts": restarts, "attention_backend": backend,
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
