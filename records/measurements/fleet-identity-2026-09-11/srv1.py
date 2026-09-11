#!/usr/bin/env python3
"""srv1's arms, in the plan's order: M1, M2, M4 on Qwen3.6 and Ling; M3 on the 3B; M7.

Raw rows go to `raw-srv1.json`, one per cold start. The runner is resumable: an arm
whose label is already in the file with no `failed` key is skipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import arms
import rig

sys.path.insert(0, str(rig.REPO / "src"))
from mcgyvr.serving import RUNTIME_RESIDENT_GB, vramfit  # noqa: E402

HOST = "srv1"
OUT = rig.SCR / "raw-srv1.json"
GIB = 1 << 30
QWEN36 = "Qwen3.6-35B-A3B-UD-IQ3_XXS"
LING = "Ling-3.0-tiny-Q4_K_M"
BLOBS = {QWEN36: "/home/adaramir/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf",
         LING: "/home/adaramir/models/moe/Ling-3.0-tiny-Q4_K_M.gguf"}


def geometry(model: str) -> dict:
    """ggufscan over the blob on the rig (headers only), kept beside the rows."""
    path = rig.SCR / f"{model}.geometry.json"
    if not path.exists():
        scanner = (rig.REPO / "src/mcgyvr/serving/ggufscan.py").read_text()
        proc = rig.subprocess.run(["ssh", "-o", "BatchMode=yes", HOST, f"python3 - {BLOBS[model]}"],
                                  input=scanner, capture_output=True, text=True, timeout=600)
        got = json.loads(proc.stdout)
        assert len(got) == 1 and "error" not in got[0], got
        path.write_text(json.dumps(got[0], indent=1))
    return json.loads(path.read_text())


def need_gib(model: str, n_cpu_moe: int) -> float:
    g = geometry(model)
    return (g["bytes_experts"] - vramfit.experts_on_card(g, n_cpu_moe)) / GIB + RUNTIME_RESIDENT_GB


def done() -> set[str]:
    if not OUT.exists():
        return set()
    return {r["label"] for r in json.loads(OUT.read_text()) if not r.get("failed")}


PLAN = [
    # (label, compose, unit, class, arm, swap, n_cpu_moe for the no-baseline check)
    *[(f"s1-qwen36-as-run-{i}", "compose.srv1-qwen36-as-run.yml", QWEN36, "cpu_experts", "as_run", "on", None) for i in (1, 2, 3)],
    *[(f"s1-qwen36-baseline-{i}", "compose.srv1-qwen36-unmapped.yml", QWEN36, "cpu_experts", "baseline", "off", 30) for i in (1, 2, 3)],
    *[(f"s1-qwen36-unmapped-n32-{i}", "compose.srv1-qwen36-unmapped-n32.yml", QWEN36, "cpu_experts", "shmem", "off", 32) for i in (1, 2)],
    *[(f"s1-ling-as-run-{i}", "compose.srv1-ling-as-run.yml", LING, "llamacpp", "as_run", "on", None) for i in (1, 2, 3)],
    *[(f"s1-ling-baseline-{i}", "compose.srv1-ling-unmapped.yml", LING, "llamacpp", "baseline", "off", 0) for i in (1, 2, 3)],
    *[(f"s1-ling-unmapped-n4-{i}", "compose.srv1-ling-unmapped-n4.yml", LING, "llamacpp", "shmem", "off", 4) for i in (1, 2)],
]


def main() -> None:
    only = set(sys.argv[1:])
    finished = done()
    for label, compose, unit, cls, arm, swap, ncmoe in PLAN:
        if label in finished or (only and not any(label.startswith(o) for o in only)):
            continue
        need = need_gib(unit, ncmoe) if ncmoe is not None else None
        try:
            arms.llama_arm(host=HOST, label=label, compose=rig.SCR / compose, unit=unit, cls=cls,
                           arm=arm, swap=swap, ram_need_gib=need, out=OUT)
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)
    for i in (1, 2, 3):
        label = f"s1-3b-vllm-{i}"
        if label in finished or (only and not any(label.startswith(o) for o in only)):
            continue
        arms.vllm_arm(host=HOST, label=label, compose=rig.SCR / "compose.srv1-3b-vllm.yml",
                      arm="host_ram", swap="on", out=OUT, decode=True)
    for i in (1, 2):
        label = f"s1-qwen36-verbose-{i}"
        if label in finished or (only and not any(label.startswith(o) for o in only)):
            continue
        try:
            arms.llama_arm(host=HOST, label=label, compose=rig.SCR / "compose.srv1-qwen36-verbose.yml",
                           unit=QWEN36, cls="cpu_experts", arm="context", swap="on", out=OUT)
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)


if __name__ == "__main__":
    main()
