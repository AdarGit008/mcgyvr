#!/usr/bin/env python3
"""R1 + R2 — vLLM KV cache dtype answers: fp8 vs float16, bench-py greedy.

One cold start per (model, dtype, a/b). The concrete dtypes are the owner's
frame: NO "auto" — ``--kv-cache-dtype fp8`` vs ``--kv-cache-dtype float16``
(the model's native dtype, spelled concretely). fp8 and float16 are distinct
units. Each arm captures the attention-backend line, the KV-token line, the
image digest and the steady card, then runs the 257-cell bench-py bundle
(greedy, temperature 0) as its own a/b null — the M5 quality method.

    uv run --no-sync python vllm_kv_answers.py [prefix...]

A prefix argument limits the run to arms whose label starts with it (e.g.
``r1-15b``). Resumable: an arm whose a and b rows are both present is skipped.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import arms
import rig

HOST = "srv2"
OUT = rig.SCR / "results-vllm-kv-answers.json"
LOGS = rig.SCR / "logs"
LOGS.mkdir(exist_ok=True)

IMAGE = "vllm/vllm-openai@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"
PORT = 8002

#: (label, model-id, max_model_len, max_num_seqs, gpu_memory_utilization)
MODELS = [
    ("r1-15b", "Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ", 4096, 8, 0.72),
    ("r1-3b", "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ", 4096, 8, 0.72),
    ("r1-q34b", "thewimo/Qwen3-4B-AWQ", 4096, 8, 0.72),
    ("r2-7b", "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ", 1024, 128, 0.9),
]
DTYPES = ("float16", "fp8")


def container_name(model: str) -> str:
    return f"mcgyvr-srv2-{model.replace('/', '-')}-{PORT}"


def make_compose(model: str, dtype: str, mml: int, mns: int, util: float) -> Path:
    service = model.replace("/", "-")
    cmd = [model, "--max-model-len", str(mml), "--max-num-seqs", str(mns),
           "--port", str(PORT), "--gpu-memory-utilization", f"{util:.2f}",
           "--kv-cache-dtype", dtype]
    doc = {"services": {f"{service}-{PORT}": {
        "command": cmd,
        "container_name": container_name(model),
        "deploy": {"resources": {"reservations": {"devices": [
            {"capabilities": ["gpu"], "device_ids": ["0"], "driver": "nvidia"}]}}},
        "environment": {"HF_HUB_OFFLINE": "1"},
        "image": IMAGE,
        "ipc": "host",
        "network_mode": "host",
        "restart": "unless-stopped",
        "volumes": ["/home/adaramir/.cache/huggingface:/root/.cache/huggingface:ro"],
    }}}
    path = rig.SCR / f"compose.srv2-{service}-{dtype}.yml"
    path.write_text(__import__("yaml").safe_dump(doc, sort_keys=False))
    return path


def bench(model: str, out: Path) -> None:
    tunnel = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                               "-N", "-L", f"18002:127.0.0.1:{PORT}", HOST])
    try:
        for _ in range(100):
            code, _ = rig.http_get("127.0.0.1", 18002, "/v1/models", timeout=2)
            if code == "200":
                break
            time.sleep(0.3)
        else:
            raise SystemExit("port-forward to srv2 never answered")
        cmd = [str(rig.PY), "tools/breadth/measure.py", "--endpoint", "http://127.0.0.1:18002",
               "--protocol", "openai", "--model", model, "--tier", "bench-py",
               "--draws", "0", "--out", str(out)]
        with open(LOGS / f"{out.name}.log", "a") as log:
            env = {**os.environ, "PATH": f"{rig.PY.parent}:{os.environ.get('PATH', '')}"}
            rc = subprocess.run(cmd, cwd=rig.REPO, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
        if rc != 0:
            raise SystemExit(f"bench {out.name} rc={rc}; see logs/{out.name}.log")
    finally:
        tunnel.terminate()
        tunnel.wait(timeout=10)


def digest(host: str) -> str:
    raw = rig.rig(host, f"docker image inspect {IMAGE} -f '{{{{.Id}}}}' 2>/dev/null || true")
    return raw.strip()


def done() -> set[str]:
    if not OUT.exists():
        return set()
    return {r["label"] for r in json.loads(OUT.read_text()) if not r.get("failed")}


def arm(prefix: str, model: str, dtype: str, mml: int, mns: int, util: float) -> dict:
    label = f"{prefix}-{dtype}"
    compose = make_compose(model, dtype, mml, mns, util)
    container = container_name(model)
    rig.teardown(HOST)
    idle = arms._idle(HOST)  # drop_caches + gpu + clock_offset
    up = arms.start(HOST, compose, label)
    if up["door_rc"] != 0:
        log = rig.engine_log(HOST, container, label)
        rig.teardown(HOST)
        return {"label": label, "model": model, "dtype": dtype, "failed": f"door rc={up['door_rc']}",
                "log_tail": log[-1200:]}
    readings = arms.unit_readings(HOST, up, idle["clock_offset_s"], label)
    r = readings[container]
    after = rig.gpu(HOST)
    row = {"label": label, "model": model, "dtype": dtype, "image_digest": digest(HOST),
           "backend_line": r["backend_line"], "kv_tokens": r["kv_tokens"],
           "kv_line": r["kv_line"], "restart_count": r["restart_count"],
           "card_used_mib": after["used"], "card_free_mib": after["free"],
           "card_reserved_mib": after["reserved"]}
    for run in ("a", "b"):
        bench_dir = rig.SCR / f"bench-{label}-{run}"
        bench(model, bench_dir)
        row[f"bench_{run}_dir"] = str(bench_dir.relative_to(rig.SCR))
    rig.teardown(HOST)
    return row


def main() -> None:
    only = sys.argv[1:]
    rows = json.loads(OUT.read_text()) if OUT.exists() else []
    finished = done()
    for prefix, model, mml, mns, util in MODELS:
        for dtype in DTYPES:
            label = f"{prefix}-{dtype}"
            if label in finished or (only and not any(label.startswith(o) for o in only)):
                continue
            try:
                row = arm(prefix, model, dtype, mml, mns, util)
            except SystemExit as exc:
                row = {"label": label, "model": model, "dtype": dtype, "failed": str(exc)}
                try:
                    rig.teardown(HOST)
                except SystemExit:
                    pass
            rows.append(row)
            OUT.write_text(json.dumps(rows, indent=2))
            print(json.dumps({k: v for k, v in row.items() if not k.startswith("bench_")}), flush=True)


if __name__ == "__main__":
    main()
