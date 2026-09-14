#!/usr/bin/env python3
"""Compute srv2 rig_id and unit_ids via mcgyvr.fleet.ids.digest.

Field structures follow records/plans/fleet-identity.md §1:
  unt- = H{ engine, image id (sha256:...), weights sha256, argv, env, gpu_cc }
  rig- = H{ host, hardware, system }
gpu_reserve_mib is dropped from the rig name (§12). The exact fields hashed
are written beside each digest so the coordinator can reproduce them.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/home/adaramir/pi_agent/projects/mcgyvr-measurements/src")

from mcgyvr.fleet.ids import digest  # noqa: E402

RIG_FIELDS = {
    "host": "srv2",
    "hardware": {
        "cpu_model": "Intel(R)_Core(TM)_i9-10900F_CPU_@_2.80GHz",
        "cpu_max_mhz": "5200",
        "ram_mt_s": "2933",
        "pl1_uw": "65000000",
        "pl2_uw": "0",
        "gpu_name": "NVIDIA_GeForce_RTX_3060",
        "gpu_vram_mib": "12288",
        "gpu_cc": "8.6",
    },
    "system": {
        "os_machine_id": "6d5d8f1f2bfa5f96",
        "kernel": "7.0.0-31-generic",
        "driver": "595.91.07",
        "docker": "29.7.2",
    },
}

VLLM_IMAGE = "sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"
LIDENBURG_IMAGE = "sha256:9a61823266917162c9611f110df1ea24f116909d10cb3804641db184fcd95b63"
MAINLINE_IMAGE = "sha256:d869b98f2b7b70a511a0dbd4c0d1cab25faf5919ca1116bd78dff363178e6dd6"

UNITS = {
    "srv2_35b_256k": {
        "engine": "llama.cpp",
        "image": LIDENBURG_IMAGE,
        "weights": "9c964e657212fea1f24905dd7b0a89b82fd807d19fab0b41da14251b07b88fbe",
        "argv": [
            "--model", "/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf",
            "-np", "1", "-c", "262144", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0",
            "-ngl", "99", "-t", "11", "--cpu-moe", "--mmap", "--jinja",
        ],
        "env": {
            "GGML_EXPERT_CACHE_MAX": "120",
            "GGML_EXPERT_RAM_CACHE_MAX": "256",
            "GGML_OP_OFFLOAD_MIN_BATCH": "1",
            "LLAMA_ARG_HOST": "0.0.0.0",
        },
        "gpu_cc": "8.6",
    },
    "srv2_3b": {
        "engine": "vllm",
        "image": VLLM_IMAGE,
        "weights": "fdc5c9234a78abd3e602c6981080c389afffc31572b7b8577eafe34317b11bf6",
        "argv": [
            "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ",
            "--max-model-len", "4096", "--max-num-seqs", "8", "--port", "8001",
            "--gpu-memory-utilization", "0.30",
            "--kv-cache-memory-bytes", "1207959552",
        ],
        "env": {"HF_HUB_OFFLINE": "1", "VLLM_LOGGING_LEVEL": "DEBUG"},
        "gpu_cc": "8.6",
    },
    "srv2_7b": {
        "engine": "vllm",
        "image": VLLM_IMAGE,
        "weights": "89cf456ec46c7b5528833c3f9e652f1128b71a190dbda3a1205f8375d576b0b3",
        "argv": [
            "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ",
            "--max-model-len", "4096", "--max-num-seqs", "8", "--port", "8002",
            "--gpu-memory-utilization", "0.68",
            "--kv-cache-memory-bytes", "1879048192",
        ],
        "env": {"HF_HUB_OFFLINE": "1", "VLLM_LOGGING_LEVEL": "DEBUG"},
        "gpu_cc": "8.6",
    },
    "srv2_80b": {
        "engine": "llama.cpp",
        "image": MAINLINE_IMAGE,
        "weights": "7705e294047a8c285b5f86556bef81e12bc9309988a9ad7e806e81cb730a86ee",
        "argv": [
            "--model", "/home/adaramir/models/moe/Qwen3-Next-80B-A3B-Instruct-Q3_K_M.gguf",
            "--n-cpu-moe", "36", "--parallel", "4", "--port", "8003",
            "-b", "512", "-c", "16384", "-fa", "on", "-ngl", "99", "-t", "10", "-ub", "512",
        ],
        "env": {"LLAMA_ARG_HOST": "0.0.0.0"},
        "gpu_cc": "8.6",
    },
}


def main() -> int:
    out: dict = {
        "rig": {
            "name": "srv2",
            "rig_id": digest("rig-", RIG_FIELDS),
            "fields": RIG_FIELDS,
        },
        "units": {},
    }
    for name, fields in UNITS.items():
        out["units"][name] = {
            "unit_id": digest("unt-", fields),
            "fields": fields,
        }
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    with open(
        "/home/adaramir/pi_agent/projects/mcgyvr-measurements/fleet-setup/digests-srv2.json",
        "w",
    ) as f:
        f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
