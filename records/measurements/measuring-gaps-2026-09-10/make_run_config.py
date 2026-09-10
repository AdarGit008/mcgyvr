#!/usr/bin/env python3
"""Emit every compose, arms JSON and the teardown index for the measuring-gaps run.

Single source of truth translating records/plans/measuring-gaps-2026-09-10.md
into the 15 composes, 5 arms files and the teardown-index the runners consume.
Run once (idempotent): `uv run --no-sync python make_run_config.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOE = "/home/adaramir/models/moe"
L3 = "llamacpp:b10644-L3"
VLLM_IMG = "vllm/vllm-openai@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"


def _llamacpp(
    stem: str,
    host: str,
    port: int,
    *,
    ncmoe: int | None = None,
    ub: int = 512,
    threads: int = 6,
    restart: str = "unless-stopped",
    extra: list[str] | None = None,
    volumes_moe: bool = True,
    chat_kwargs: bool = False,
    load_mode_none: bool = False,
) -> dict:
    cmd: list[str] = []
    if load_mode_none:
        cmd += ["--load-mode", "none"]
    cmd += [
        "--model", f"{MOE}/{stem}.gguf",
    ]
    if ncmoe is not None:
        cmd += ["--n-cpu-moe", str(ncmoe)]
    cmd += [
        "--parallel", "2",
        "--port", str(port),
        "-b", "512",
        "-c", "8192",
        "-fa", "on",
        "-ngl", "99",
        "-t", str(threads),
        "-ub", str(ub),
        "--verbose",
    ]
    if extra:
        cmd += extra
    if chat_kwargs:
        cmd += ["--chat-template-kwargs", '{"enable_thinking":false}']
    vol = [f"{MOE}:{MOE}:ro", f"{MOE}:/models:ro"] if volumes_moe else [
        "/home/adaramir/models:/home/adaramir/models:ro",
        "/home/adaramir/models:/models:ro",
    ]
    svc = stem.split("/")[-1] if "/" in stem else stem
    return {
        "services": {
            f"{svc}-{port}": {
                "command": cmd,
                "container_name": f"mcgyvr-{host}-{svc}-{port}",
                "deploy": {"resources": {"reservations": {"devices": [
                    {"capabilities": ["gpu"], "device_ids": ["0"], "driver": "nvidia"}
                ]}}},
                "environment": {"LLAMA_ARG_HOST": "0.0.0.0"},
                "image": L3,
                "network_mode": "host",
                "restart": restart,
                "volumes": vol,
            }
        }
    }


def _vllm(model: str, host: str, port: int, *, kv_dtype: str | None = None) -> dict:
    svc = model.replace("/", "-")
    cmd = [
        model,
        "--max-model-len", "2048",
        "--max-num-seqs", "128",
        "--port", str(port),
        "--gpu-memory-utilization", "0.90",
        "--dtype", "float16",
    ]
    if kv_dtype == "fp8":
        cmd += ["--kv-cache-dtype", "fp8"]
    return {
        "services": {
            f"{svc}-{port}": {
                "command": cmd,
                "container_name": f"mcgyvr-{host}-{svc}-{port}",
                "deploy": {"resources": {"reservations": {"devices": [
                    {"capabilities": ["gpu"], "device_ids": ["0"], "driver": "nvidia"}
                ]}}},
                "environment": {"HF_HUB_OFFLINE": "1"},
                "image": VLLM_IMG,
                "ipc": "host",
                "network_mode": "host",
                "restart": "unless-stopped",
                "volumes": ["/home/adaramir/.cache/huggingface:/root/.cache/huggingface:ro"],
            }
        }
    }


def _emit(name: str, obj: dict) -> str:
    path = HERE / name
    path.write_text(
        "services:\n" if False else ""  # placeholder, real emit below
    )
    return str(path)


def _dump_yaml(path: Path, obj: dict) -> None:
    """Minimal YAML emitter for the exact shape the door's compose parser expects."""
    import yaml  # pyproject has PyYAML
    path.write_text(yaml.safe_dump(obj, sort_keys=False, default_flow_style=False))


# --- the compose matrix (file -> compose) -----------------------------------

COMPOSES: dict[str, dict] = {}

COMPOSES["compose.srv1-q1-deepseek-f16.yml"] = _llamacpp(
    "deepseek-coder-v2-16b", "srv1", 8080, ncmoe=19)
COMPOSES["compose.srv1-q1-deepseek-q8.yml"] = _llamacpp(
    "deepseek-coder-v2-16b", "srv1", 8080, ncmoe=19,
    extra=["-ctk", "q8_0", "-ctv", "q8_0"])

COMPOSES["compose.srv1-q5-ling.yml"] = _llamacpp(
    "Ling-3.0-tiny-Q4_K_M", "srv1", 8080, ub=512)

for ub in (256, 512, 1024):
    COMPOSES[f"compose.srv1-q3-ling-ub{ub}.yml"] = _llamacpp(
        "Ling-3.0-tiny-Q4_K_M", "srv1", 8080, ub=ub)
for ub in (256, 1024):
    COMPOSES[f"compose.srv1-q3-gemma-ub{ub}.yml"] = _llamacpp(
        "gemma-4-26B-A4B-it-UD-IQ3_XXS", "srv1", 8080, ncmoe=22, ub=ub)
for ub in (256, 1024):
    COMPOSES[f"compose.srv2-q3-80b-ub{ub}.yml"] = _llamacpp(
        "Qwen3-Next-80B-A3B-Instruct-Q3_K_M", "srv2", 8003, ncmoe=35, ub=ub,
        threads=10, restart="no", volumes_moe=False, chat_kwargs=True)
for n in (0, 13, 26):
    COMPOSES[f"compose.srv2-q4-deepseek-n{n}.yml"] = _llamacpp(
        "deepseek-coder-v2-16b", "srv2", 8080, ncmoe=n, threads=10, restart="no")

COMPOSES["compose.srv2-q2-q34b-fp16.yml"] = _vllm("thewimo/Qwen3-4B-AWQ", "srv2", 8001)
COMPOSES["compose.srv2-q2-q34b-fp8.yml"] = _vllm(
    "thewimo/Qwen3-4B-AWQ", "srv2", 8001, kv_dtype="fp8")

# --- arms JSON (file -> list of specs) --------------------------------------

P = str(HERE)
ARMS: dict[str, list[dict]] = {}

ARMS["arms-q1-kv-q8.json"] = [
    {"host": "srv1", "label": "q1-deepseek-f16", "cache_type": "f16",
     "blob_gib": 8.29, "port": 8080, "repeats": 2,
     "container": "mcgyvr-srv1-deepseek-coder-v2-16b-8080",
     "compose": f"{P}/compose.srv1-q1-deepseek-f16.yml"},
    {"host": "srv1", "label": "q1-deepseek-q8", "cache_type": "q8_0",
     "blob_gib": 8.29, "port": 8080, "repeats": 2,
     "container": "mcgyvr-srv1-deepseek-coder-v2-16b-8080",
     "compose": f"{P}/compose.srv1-q1-deepseek-q8.yml"},
]

ARMS["arms-q2-vllm-fp8.json"] = [
    {"host": "srv2", "label": "q2-q34b-fp16", "model": "thewimo/Qwen3-4B-AWQ",
     "kv_dtype": "fp16", "port": 8001, "repeats": 2, "units": 1,
     "container": "mcgyvr-srv2-thewimo-Qwen3-4B-AWQ-8001",
     "compose": f"{P}/compose.srv2-q2-q34b-fp16.yml"},
    {"host": "srv2", "label": "q2-q34b-fp8", "model": "thewimo/Qwen3-4B-AWQ",
     "kv_dtype": "fp8", "port": 8001, "repeats": 2, "units": 1,
     "container": "mcgyvr-srv2-thewimo-Qwen3-4B-AWQ-8001",
     "compose": f"{P}/compose.srv2-q2-q34b-fp8.yml"},
]

ARMS["arms-q3-scratch.json"] = (
    [{"host": "srv1", "label": f"q3-ling-ub{ub}", "arch": "bailingmoe3", "ub": ub,
      "blob_gib": 4.58, "port": 8080, "repeats": 2,
      "container": "mcgyvr-srv1-Ling-3.0-tiny-Q4_K_M-8080",
      "compose": f"{P}/compose.srv1-q3-ling-ub{ub}.yml"} for ub in (256, 512, 1024)]
    + [{"host": "srv1", "label": f"q3-gemma-ub{ub}", "arch": "gemma4", "ub": ub,
        "blob_gib": 10.63, "port": 8080, "repeats": 2,
        "container": "mcgyvr-srv1-gemma-4-26B-A4B-it-UD-IQ3_XXS-8080",
        "compose": f"{P}/compose.srv1-q3-gemma-ub{ub}.yml"} for ub in (256, 1024)]
    + [{"host": "srv2", "label": f"q3-80b-ub{ub}", "arch": "qwen3next", "ub": ub,
        "blob_gib": 35.67, "port": 8003, "repeats": 2,
        "container": "mcgyvr-srv2-Qwen3-Next-80B-A3B-Instruct-Q3_K_M-8003",
        "compose": f"{P}/compose.srv2-q3-80b-ub{ub}.yml"} for ub in (256, 1024)]
)

ARMS["arms-q4-c-drift.json"] = [
    {"host": "srv2", "label": f"q4-deepseek-n{n}", "ncmoe": n,
     "blob_gib": 8.29, "port": 8080, "repeats": 2,
     "container": "mcgyvr-srv2-deepseek-coder-v2-16b-8080",
     "compose": f"{P}/compose.srv2-q4-deepseek-n{n}.yml"} for n in (0, 13, 26)
]

ARMS["arms-q5-mla.json"] = [
    {"host": "srv1", "label": "q5-ling", "arch": "bailingmoe3",
     "blob_gib": 4.58, "port": 8080, "repeats": 2,
     "container": "mcgyvr-srv1-Ling-3.0-tiny-Q4_K_M-8080",
     "compose": f"{P}/compose.srv1-q5-ling.yml"},
]

# --- emit --------------------------------------------------------------------

for name, obj in COMPOSES.items():
    _dump_yaml(HERE / name, obj)
for name, specs in ARMS.items():
    (HERE / name).write_text(json.dumps(specs, indent=2) + "\n")

# teardown index: one entry per distinct container name (last-up is authoritative
# at runtime; this is the fallback for anything note_up has not recorded).
index: dict[str, str] = {}
for name, specs in ARMS.items():
    for s in specs:
        index.setdefault(s["container"], s["compose"])
# also register the live containers so teardown can stop them by name if needed
(HERE / "teardown-index.json").write_text(json.dumps(index, indent=2) + "\n")

print(f"wrote {len(COMPOSES)} composes, {len(ARMS)} arms files, "
      f"teardown-index with {len(index)} entries")
for name in sorted(COMPOSES):
    print("  compose:", name)
for name in sorted(ARMS):
    print("  arms:", name, f"({len(ARMS[name])} specs)")
