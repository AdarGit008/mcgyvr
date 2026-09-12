#!/usr/bin/env python3
"""srv2's unpinned arms: M1 on the live pair, M2/M3 on each unit alone, M5 fp8 and quality.

Raw rows go to `raw-srv2.json`, one per cold start, and the runner can be resumed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import arms
import rig

HOST = "srv2"
OUT = rig.SCR / "raw-srv2.json"
CODER_7B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"


def done() -> set[str]:
    if not OUT.exists():
        return set()
    return {r["label"] for r in json.loads(OUT.read_text()) if not r.get("failed")}


def wanted(label: str) -> bool:
    only = sys.argv[1:]
    return (not only or any(label.startswith(o) for o in only)) and label not in done()


def bench(name: str) -> None:
    """Greedy bench-py, 257 cells, against the 7B that is up now.

    Through a local port-forward, as `srv1-correct-2026-09-03-*` ran: the bench's
    card sampler reads a non-local endpoint's host over ssh, which only the door
    may open, and it does not sample a localhost endpoint.
    """
    out = rig.SCR / name
    tunnel = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                               "-N", "-L", "18002:127.0.0.1:8002", HOST])
    try:
        for _ in range(50):
            code, _ = rig.http_get("127.0.0.1", 18002, "/v1/models", timeout=2)
            if code == "200":
                break
            time.sleep(0.2)
        else:
            raise SystemExit("port-forward to srv2:8002 never answered")
        cmd = [str(rig.PY), "tools/breadth/measure.py", "--endpoint", "http://127.0.0.1:18002",
               "--protocol", "openai", "--model", CODER_7B, "--tier", "bench-py",
               "--draws", "0", "--out", str(out)]
        print(f"    bench {name}", flush=True)
        with open(rig.LOGS / f"{name}.log", "a") as log:
            # Acceptance runs `python accept.py`, so the venv must lead PATH, as `uv run` does.
            env = {**os.environ, "PATH": f"{rig.PY.parent}:{os.environ.get('PATH', '')}"}
            rc = subprocess.run(cmd, cwd=rig.REPO, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
        if rc != 0:
            raise SystemExit(f"bench {name} rc={rc}; see logs/{name}.log")
    finally:
        tunnel.terminate()
        tunnel.wait(timeout=10)


def main() -> None:
    for arm, swap in (("as_run", "on"), ("baseline", "off")):
        for i in (1, 2, 3):
            label = f"s2-pair-{arm}-{i}"
            if wanted(label):
                arms.vllm_arm(host=HOST, label=label, compose=rig.SCR / "compose.srv2-pair-as-run.yml",
                              arm=arm, swap=swap, out=OUT)
    for unit in ("3b", "7b"):
        for i in (1, 2, 3):
            label = f"s2-{unit}-alone-{i}"
            if wanted(label):
                arms.vllm_arm(host=HOST, label=label, compose=rig.SCR / f"compose.srv2-{unit}-alone.yml",
                              arm="alone", swap="on", out=OUT, extra={"kv_cache_dtype": "auto"})
    for i in (1, 2, 3):
        label = f"s2-7b-fp8-{i}"
        if wanted(label):
            arms.vllm_arm(host=HOST, label=label, compose=rig.SCR / "compose.srv2-7b-fp8.yml",
                          arm="fp8", swap="on", out=OUT, extra={"kv_cache_dtype": "fp8"})
    for dtype, compose in (("auto", "compose.srv2-7b-alone.yml"), ("fp8", "compose.srv2-7b-fp8.yml")):
        label = f"s2-7b-{dtype}-quality"
        if not wanted(label):
            continue
        row = arms.vllm_arm(host=HOST, label=label, compose=rig.SCR / compose, arm="quality",
                            swap="on", out=OUT, decode=False, keep_up=True,
                            extra={"kv_cache_dtype": dtype, "failed": "bench not finished"})
        try:
            if "up" in row and row["up"]["door_rc"] == 0:
                for run in ("a", "b"):
                    # measure.py resumes a directory it already started, so a rerun
                    # refills missing cells rather than duplicating finished ones.
                    bench(f"bench-7b-{dtype}-{run}")
                rows = json.loads(OUT.read_text())
                for r in rows:
                    if r["label"] == label and r.get("failed") == "bench not finished":
                        r.pop("failed")
                OUT.write_text(json.dumps(rows, indent=1))
        finally:
            rig.teardown(HOST)


if __name__ == "__main__":
    main()
