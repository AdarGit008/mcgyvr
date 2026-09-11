#!/usr/bin/env python3
"""R4 — llama.cpp q8_0 vs f16 KV cache answers on the live srv1 unit.

One cold start per (cache dtype, a/b). The concrete dtypes, per the owner's
frame: ``-ctk f16 -ctv f16`` vs ``-ctk q8_0 -ctv q8_0`` (distinct units). The
live Qwen3.6 placement (--n-cpu-moe 30, --parallel 2, -c 16384,
llamacpp:b10644-L3) is held fixed; only the cache dtype moves. Each arm captures
the engine's own ``llama_kv_cache`` line (K/V dtype and MiB) and runs the
257-cell bench-py bundle (greedy) as its own a/b null.

    uv run --no-sync python lcpp_kv_answers.py [prefix...]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import arms
import rig

HOST = "srv1"
OUT = rig.SCR / "results-lcpp-kv-answers.json"
LOGS = rig.SCR / "logs"
LOGS.mkdir(exist_ok=True)

IMAGE = "llamacpp:b10644-L3"
MODEL_BLOB = "/home/adaramir/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf"
PORT = 8080
CONTAINER = "mcgyvr-srv1-Qwen3.6-35B-A3B-UD-IQ3_XXS-8080"

#: The engine line with the dtype letters (group 6/7 = K dtype/MiB, 8/9 = V).
KVSIZE = re.compile(
    r"llama_kv_cache: size =\s+([\d.]+) MiB \(\s*(\d+) cells,\s*(\d+) layers,"
    r"\s*(\d+)/(\d+) seqs\), K \((\w+)\):\s*([\d.]+) MiB,"
    r" V \((\w+)\):\s*([\d.]+) MiB"
)
CTYPES = ("f16", "q8_0")


def make_compose(ctype: str) -> str:
    service = "Qwen3.6-35B-A3B-UD-IQ3_XXS-8080"
    cmd = ["--model", MODEL_BLOB, "--n-cpu-moe", "30", "--parallel", "2",
           "--port", str(PORT), "-b", "512", "-c", "16384", "-fa", "on",
           "-ngl", "99", "-t", "6", "-ub", "512",
           "--chat-template-kwargs", '{"enable_thinking":false}',
           "-ctk", ctype, "-ctv", ctype, "--verbose"]
    doc = {"services": {service: {
        "command": cmd, "container_name": CONTAINER,
        "deploy": {"resources": {"reservations": {"devices": [
            {"capabilities": ["gpu"], "device_ids": ["0"], "driver": "nvidia"}]}}},
        "environment": {"LLAMA_ARG_HOST": "0.0.0.0"},
        "image": IMAGE, "network_mode": "host", "restart": "unless-stopped",
        "volumes": ["/home/adaramir/models/moe:/home/adaramir/models/moe:ro",
                    "/home/adaramir/models/moe:/models:ro"],
    }}}
    path = rig.SCR / f"compose.srv1-r4-{ctype}.yml"
    path.write_text(__import__("yaml").safe_dump(doc, sort_keys=False))
    return path


def parse_kv(log: str) -> dict:
    idx = [m.start() for m in re.finditer(r"load_tensors:.*model buffer size", log)]
    real = log[idx[len(idx) // 2]:] if len(idx) > 1 else log
    matches = list(KVSIZE.finditer(real))
    if not matches:
        return {}
    m = matches[-1]
    return {"kv_line": m.group(0), "size_mib": float(m.group(1)), "cells": int(m.group(2)),
            "layers": int(m.group(3)), "k_dtype": m.group(6), "k_mib": float(m.group(7)),
            "v_dtype": m.group(8), "v_mib": float(m.group(9))}


def served_model() -> str:
    code, body = rig.http_get(HOST, PORT, "/v1/models", timeout=10)
    if code != "200":
        raise SystemExit(f"/v1/models {code}: {body[:200]}")
    doc = json.loads(body)
    return doc["data"][0]["id"]


def bench(model: str, out_dir: str) -> None:
    tunnel = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                               "-N", "-L", f"18004:127.0.0.1:{PORT}", HOST])
    try:
        for _ in range(100):
            code, _ = rig.http_get("127.0.0.1", 18004, "/v1/models", timeout=2)
            if code == "200":
                break
            time.sleep(0.3)
        else:
            raise SystemExit("port-forward to srv1 never answered")
        cmd = [str(rig.PY), "tools/breadth/measure.py", "--endpoint", "http://127.0.0.1:18004",
               "--protocol", "openai", "--model", model, "--tier", "bench-py",
               "--draws", "0", "--out", out_dir]
        with open(LOGS / f"{Path(out_dir).name}.log", "a") as log:
            env = {**os.environ, "PATH": f"{rig.PY.parent}:{os.environ.get('PATH', '')}"}
            rc = subprocess.run(cmd, cwd=rig.REPO, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
        if rc != 0:
            raise SystemExit(f"bench rc={rc}; see logs/{Path(out_dir).name}.log")
    finally:
        tunnel.terminate()
        tunnel.wait(timeout=10)


def done() -> set[str]:
    if not OUT.exists():
        return set()
    return {r["label"] for r in json.loads(OUT.read_text()) if not r.get("failed")}


def arm(ctype: str) -> dict:
    label = f"r4-qwen36-{ctype}"
    compose = make_compose(ctype)
    # both dtypes share the container name, so point last-up at this compose so
    # teardown can identify any orphaned container left by a mid-arm crash
    rig.LOGS.mkdir(exist_ok=True)
    (rig.LOGS / f"last-up-{HOST}.txt").write_text(str(compose))
    rig.teardown(HOST)
    idle = arms._idle(HOST)
    up = arms.start(HOST, compose, label)
    if up["door_rc"] != 0:
        log = rig.engine_log(HOST, CONTAINER, label)
        rig.teardown(HOST)
        return {"label": label, "dtype": ctype, "failed": f"door rc={up['door_rc']}",
                "log_tail": log[-1200:]}
    log = rig.engine_log(HOST, CONTAINER, label)
    model = served_model()
    kv = parse_kv(log)
    after = rig.gpu(HOST)
    row = {"label": label, "dtype": ctype, "model": model, "image": IMAGE,
           "card_used_mib": after["used"], "card_free_mib": after["free"],
           "card_reserved_mib": after["reserved"], **kv}
    for run in ("a", "b"):
        bench_dir = str(rig.SCR / f"bench-{label}-{run}")
        bench(model, bench_dir)
        row[f"bench_{run}_dir"] = f"bench-{label}-{run}"
    rig.teardown(HOST)
    return row


def main() -> None:
    only = sys.argv[1:]
    rows = json.loads(OUT.read_text()) if OUT.exists() else []
    finished = done()
    for ctype in CTYPES:
        label = f"r4-qwen36-{ctype}"
        if label in finished or (only and not any(label.startswith(o) for o in only)):
            continue
        try:
            row = arm(ctype)
        except SystemExit as exc:
            row = {"label": label, "dtype": ctype, "failed": str(exc)}
            try:
                rig.teardown(HOST)
            except SystemExit:
                pass
        rows.append(row)
        OUT.write_text(json.dumps(rows, indent=2))
        print(json.dumps({k: v for k, v in row.items() if not k.startswith("bench_")}), flush=True)


if __name__ == "__main__":
    main()
