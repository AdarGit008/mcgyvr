#!/usr/bin/env python3
"""Measure the two srv2 switch moves with wall-clock timings.

Switch A: b-small -> b-big   [[3b,awake],[7b,awake]] -> [[80b,awake]]
Switch B: b-big -> b-small   [[80b,awake]] -> [[3b,awake],[7b,awake]]

Run on srv2. Uses docker compose for the pair and docker run for the 80B.
Reports downtime_s and wake_s (per unit) in the lock's move shape.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

PAIR_COMPOSE = "/home/adaramir/measurements-srv2/compose-pair.yml"
PAIR_PROJECT = "mcgyvr"
C3B = "mcgyvr-srv2-Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001"
C7B = "mcgyvr-srv2-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002"
C80B = "mcgyvr-80b-switch"
MODEL80 = "/home/adaramir/models/moe/Qwen3-Next-80B-A3B-Instruct-Q3_K_M.gguf"


def sh(args, timeout=600):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def health_llama(port, deadline):
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
                if r.read().strip():
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    return False


def health_vllm(port, deadline):
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=5) as r:
                if r.read().strip():
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    return False


def card_idle():
    out = sh(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
    return int(out.stdout.strip())


def wait_idle(deadline):
    while time.time() < deadline:
        if card_idle() <= 2:
            return True
        time.sleep(1)
    return False


def start_80b():
    sh(["docker", "rm", "-f", C80B], timeout=60)
    r = sh(["docker", "run", "-d", "--name", C80B, "--gpus", "all", "--network", "host",
            "-v", "/home/adaramir/models:/models:ro",
            "-v", "/home/adaramir/models:/home/adaramir/models:ro",
            "-e", "LLAMA_ARG_HOST=0.0.0.0", "llamacpp:b10644-L3", "--model", MODEL80,
            "--n-cpu-moe", "36", "--parallel", "4", "--port", "8003",
            "-b", "512", "-c", "16384", "-fa", "on", "-ngl", "99", "-t", "10", "-ub", "512"])
    if r.returncode != 0:
        raise RuntimeError(f"80b start failed: {r.stderr[:500]}")


def pair_up():
    sh(["docker", "compose", "-f", PAIR_COMPOSE, "-p", PAIR_PROJECT, "up", "-d", "--remove-orphans"])


def pair_down():
    sh(["docker", "compose", "-f", PAIR_COMPOSE, "-p", PAIR_PROJECT, "down", "--remove-orphans"])


def main():
    results = {}

    # ---- Switch A: b-small -> b-big ----
    pair_up()
    assert health_vllm(8001, time.time() + 400), "3B never healthy"
    assert health_vllm(8002, time.time() + 400), "7B never healthy"
    t0 = time.time()
    pair_down()
    assert wait_idle(time.time() + 60), "card not idle after pair down"
    t_stopped = time.time()
    t_80_start = time.time()
    start_80b()
    assert health_llama(8003, time.time() + 400), "80B never healthy"
    t_80 = time.time()
    results["b-small->b-big"] = {
        "rig": "srv2",
        "from": [["srv2_3b", "awake"], ["srv2_7b", "awake"]],
        "to": [["srv2_80b", "awake"]],
        "passed": True,
        "downtime_s": round(t_80 - t_stopped, 2),
        "wake_s": {"srv2_80b": round(t_80 - t_80_start, 2)},
        "note": f"stop pair took {round(t_stopped - t0, 2)}s",
    }

    # ---- Switch B: b-big -> b-small ----
    # 80B is still up from switch A
    assert health_llama(8003, time.time() + 60), "80B not healthy for switch B"
    t0 = time.time()
    sh(["docker", "rm", "-f", C80B])
    assert wait_idle(time.time() + 60), "card not idle after 80b stop"
    t_stopped = time.time()
    t_pair_start = time.time()
    pair_up()
    assert health_vllm(8001, time.time() + 400), "3B never healthy (switch B)"
    t_3 = time.time()
    assert health_vllm(8002, time.time() + 400), "7B never healthy (switch B)"
    t_7 = time.time()
    results["b-big->b-small"] = {
        "rig": "srv2",
        "from": [["srv2_80b", "awake"]],
        "to": [["srv2_3b", "awake"], ["srv2_7b", "awake"]],
        "passed": True,
        "downtime_s": round(max(t_3, t_7) - t_stopped, 2),
        "wake_s": {"srv2_3b": round(t_3 - t_pair_start, 2),
                   "srv2_7b": round(t_7 - t_pair_start, 2)},
        "note": f"stop 80B took {round(t_stopped - t0, 2)}s",
    }

    print(json.dumps(results, indent=2, sort_keys=True))
    with open("/home/adaramir/measurements-srv2/switches.json", "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
