#!/usr/bin/env python3
"""Measure the two srv1 switch moves: b-small <-> b-big.

b-small/srv1 = [[srv1_deepseek, awake]]  deepseek-coder-v2-16b, ncmoe 19, np 2, c 8192
b-big/srv1   = [[srv1_35b_b, awake]]     Qwen3.6-35B-A3B,        ncmoe 30, np 2, c 16384

Each move: stop the source (docker rm -f), start the target, record
downtime_s (source-stop -> target-healthy) and wake_s (target-start ->
target-healthy). Tears down at the end. Runs on the rig."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

IMAGE = "llamacpp:b10644-L3"
PORT = 8080

UNITS = {
    "deepseek": {
        "model": "/home/adaramir/models/moe/deepseek-coder-v2-16b.gguf",
        "args": ["--n-cpu-moe", "19", "--parallel", "2", "--port", "8080",
                 "-b", "512", "-ub", "512", "-c", "8192", "-fa", "on",
                 "-ngl", "99", "-t", "6"],
    },
    "35b_b": {
        "model": "/home/adaramir/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf",
        "args": ["--n-cpu-moe", "30", "--parallel", "2", "--port", "8080",
                 "-b", "512", "-ub", "512", "-c", "16384", "-fa", "on",
                 "-ngl", "99", "-t", "6"],
    },
}


def sh(args, timeout=120):
    done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return done.stdout.strip(), done.stderr.strip(), done.returncode


def health():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as r:
            body = r.read().decode("utf-8", "replace").strip()
            return body in ("ok", "OK") or '"status":"ok"' in body
    except (urllib.error.URLError, OSError):
        return False


def start(name):
    unit = UNITS[name]
    cmd = [
        "docker", "run", "-d", "--name", name, "--gpus", "all", "--network", "host",
        "-v", "/home/adaramir/models:/models:ro",
        "-v", "/home/adaramir/models:/home/adaramir/models:ro",
        "-e", "LLAMA_ARG_HOST=0.0.0.0", IMAGE, "--model", unit["model"],
    ] + unit["args"]
    sh(cmd, timeout=60)


def wait_healthy(deadline):
    while time.time() < deadline:
        if health():
            return True
        time.sleep(1.0)
    return False


def move(source, target):
    for n in (source, target):
        sh(["docker", "rm", "-f", n], timeout=60)
    # Bring source up first (the move starts from the awake source).
    start(source)
    if not wait_healthy(time.time() + 600):
        print(json.dumps({"error": f"{source} never became healthy"}))
        sh(["docker", "rm", "-f", source], timeout=60)
        return {"source": source, "target": target, "passed": False, "error": "source unhealthy"}

    t0 = time.monotonic()
    sh(["docker", "rm", "-f", source], timeout=60)
    # Cold target: evict the page cache so the target loads from NVMe, matching
    # the cold-wake methodology the prior-art wake laws were measured under.
    sh(["sudo", "-n", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"], timeout=60)
    start(target)
    t1 = time.monotonic()
    ok = wait_healthy(time.time() + 900)
    t2 = time.monotonic()

    result = {
        "source": source,
        "target": target,
        "passed": ok,
        "downtime_s": round(t2 - t0, 3),
        "wake_s": round(t2 - t1, 3),
        "stop_s": round(t1 - t0, 3),
    }
    sh(["docker", "rm", "-f", target], timeout=60)
    time.sleep(2)
    return result


def main():
    moves = [
        ("deepseek", "35b_b"),   # b-small -> b-big srv1
        ("35b_b", "deepseek"),   # b-big -> b-small srv1
    ]
    out = []
    for source, target in moves:
        out.append(move(source, target))
    print(json.dumps(out, indent=2, sort_keys=True))
    # final teardown / idle check
    sh(["docker", "rm", "-f", "deepseek"], timeout=60)
    sh(["docker", "rm", "-f", "35b_b"], timeout=60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
