#!/usr/bin/env python3
"""R3 — vLLM speed ladder: float16 vs fp8 at the 08-28 shape, n = 1…128.

Reuses the vllmsweep28 method (475 tokens, ignore_eos, temperature 0, one fixed
prompt, concurrency levels 1,2,4,8,16,32,64,128) but through the door: each arm
is a cold start at ``--gpu-memory-utilization 0.9 --max-model-len 1024
--max-num-seqs 128`` with the concrete KV dtype, then serve down. Two cold
starts per (model, dtype). Records agg tok/s, p50, truncated per level.

    uv run --no-sync python vllm_kv_ladder.py [prefix...]
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import subprocess
import sys
import time

import arms
import rig

HOST = "srv2"
PORT = 8002
OUT = rig.SCR / "results-vllm-kv-ladder.json"
LOGS = rig.SCR / "logs"
LOGS.mkdir(exist_ok=True)

IMAGE = "vllm/vllm-openai@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"
MODELS = {
    "r3-15b": "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ",
    "r3-3b": "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ",
    "r3-q34b": "thewimo/Qwen3-4B-AWQ",
    "r3-7b": "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ",
}
DTYPES = ("float16", "fp8")
LEVELS = (1, 2, 4, 8, 16, 32, 64, 128)
NPRED = 475
PROMPT = "Write a Python function that merges two sorted lists."


def make_compose(model: str, dtype: str) -> str:
    service = model.replace("/", "-") + "-8002"
    cmd = ["--model", model, "--port", "8002", "--gpu-memory-utilization", "0.9",
           "--max-model-len", "1024", "--max-num-seqs", "128", "--served-model-name",
           "r3-ladder"]
    if dtype == "fp8":
        cmd += ["--kv-cache-dtype", "fp8"]
    doc = {"services": {service: {
        "command": cmd, "container_name": f"mcgyvr-srv2-{service}",
        "deploy": {"resources": {"reservations": {"devices": [
            {"capabilities": ["gpu"], "device_ids": ["0"], "driver": "nvidia"}]}}},
        "environment": {"HF_HOME": "/root/.cache/huggingface",
                        "VLLM_ATTENTION_BACKEND": "FLASH_ATTN"},
        "image": IMAGE, "network_mode": "host", "restart": "unless-stopped",
        "volumes": ["/home/adaramir/.cache/huggingface:/root/.cache/huggingface"],
    }}}
    path = rig.SCR / f"compose.srv2-{service}-{dtype}-ladder.yml"
    path.write_text(__import__("yaml").safe_dump(doc, sort_keys=False))
    return str(path)


def one_request(port: int) -> tuple[int, float]:
    import urllib.request
    body = json.dumps({"model": "r3-ladder", "prompt": PROMPT, "max_tokens": NPRED,
                       "temperature": 0, "ignore_eos": True}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=3600) as f:
            d = json.load(f)
        return d["usage"]["completion_tokens"], time.time() - t0
    except Exception:
        return 0, time.time() - t0


def ladder(port: int) -> dict:
    out = {}
    # one warm-up request to pin the engine (matches 08-28: post([None], 0))
    one_request(port)
    for n in LEVELS:
        t0 = time.time()
        with cf.ThreadPoolExecutor(max_workers=n) as ex:
            results = list(ex.map(lambda _: one_request(port), range(n)))
        wall = time.time() - t0
        gen = sum(r[0] for r in results)
        if gen == 0:
            out[f"n={n}"] = "ERR"
            break
        short = sum(1 for r in results if r[0] < NPRED)
        lat = sorted(r[1] for r in results)
        out[f"n={n}"] = {"agg_tok_s": round(gen / wall, 1), "p50_s": round(lat[len(lat) // 2], 3),
                         "truncated": f"{short}/{n}", "wall_s": round(wall, 1)}
    return out


def tunnel(port: int):
    p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                          "-N", "-L", f"18006:127.0.0.1:{port}", HOST])
    for _ in range(100):
        code, _ = rig.http_get("127.0.0.1", 18006, "/health", timeout=2)
        if code == "200":
            return p
        time.sleep(0.3)
    p.terminate()
    raise SystemExit("port-forward to srv2 never answered")


def done() -> set[str]:
    if not OUT.exists():
        return set()
    return {r["label"] for r in json.loads(OUT.read_text()) if not r.get("failed")}


def arm(prefix: str, model: str, dtype: str) -> dict:
    label = f"{prefix}-{dtype}"
    compose = make_compose(model, dtype)
    rig.teardown(HOST)
    up = arms.start(HOST, compose, label)
    if up["door_rc"] != 0:
        rig.teardown(HOST)
        return {"label": label, "failed": f"door rc={up['door_rc']}"}
    try:
        t = tunnel(PORT)
    except SystemExit as exc:
        rig.teardown(HOST)
        return {"label": label, "failed": str(exc)}
    try:
        levels = ladder(18006)
    finally:
        t.terminate(); t.wait(timeout=10)
    rig.teardown(HOST)
    return {"label": label, "model": model, "dtype": dtype, "shape": "util=0.9 len=1024 seqs=128",
            "levels": levels}


def main() -> None:
    only = sys.argv[1:]
    rows = json.loads(OUT.read_text()) if OUT.exists() else []
    finished = done()
    for prefix, model in MODELS.items():
        for dtype in DTYPES:
            for cold in (1, 2):
                label = f"{prefix}-{dtype}-c{cold}"
                if label in finished or (only and not any(label.startswith(o) for o in only)):
                    continue
                try:
                    row = arm(prefix, model, dtype)
                    row["label"] = label
                    row["cold"] = cold
                except SystemExit as exc:
                    row = {"label": label, "failed": str(exc)}
                    try:
                        rig.teardown(HOST)
                    except SystemExit:
                        pass
                rows.append(row)
                OUT.write_text(json.dumps(rows, indent=2))
                print(json.dumps({k: v for k, v in row.items() if k != "levels"}), flush=True)


if __name__ == "__main__":
    main()
