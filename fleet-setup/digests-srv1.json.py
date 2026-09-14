#!/usr/bin/env python3
"""Compute the srv1 rig_id and the three srv1 unit_ids.

Uses mcgyvr.fleet.ids.digest (prefix + sha256 of a canonical YAML tree). Field
sets follow records/plans/fleet-identity.md §1:

  unt-  unit = H{ engine, image id (sha256:...), weights sha256, argv, env, GPU compute capability }
  rig-  rig  = H{ host, hardware, system }

The argv is the whole resolved launch as actually run on srv1 (long flag forms,
matching the live compose argv in records/evidence/2026-09-09-live-srv1/).
"""

from __future__ import annotations

import json
import sys

from mcgyvr.fleet.ids import digest

IMAGE_ID = "sha256:d869b98f2b7b70a511a0dbd4c0d1cab25faf5919ca1116bd78dff363178e6dd6"
Q36_SHA = "9c964e657212fea1f24905dd7b0a89b82fd807d19fab0b41da14251b07b88fbe"
DEEPSEEK_SHA = "5ff0abeeac1d2dbdd5455c0b49ba3b29a9ce3c1fb181b2eef2e948689d55d046"

rig_fields = {
    "host": "srv1",
    "hardware": {
        "cpu_model": "Intel(R) Core(TM) i5-9600K CPU @ 3.70GHz",
        "cpu_max_mhz": "4600",
        "ram_mt_s": "3600",
        "pl1_uw": "95000000",
        "pl2_uw": "120000000",
        "gpu_name": "NVIDIA GeForce GTX 1660 SUPER",
        "gpu_vram_mib": 6144,
        "gpu_cc": "7.5",
    },
    "system": {
        "driver": "580.178.04",
        "docker": "29.7.2",
        "kernel": "7.0.0-31-generic",
        "os_machine_id": "9f01e96b66e798b2",
    },
}


def unit_fields(weights_sha256, argv):
    return {
        "engine": "llama.cpp",
        "image_id": IMAGE_ID,
        "weights_sha256": weights_sha256,
        "argv": argv,
        "env": {"LLAMA_ARG_HOST": "0.0.0.0"},
        "gpu_cc": "7.5",
    }


UNITS = {
    "srv1_35b_maxctx": {
        "model": "Qwen3.6-35B-A3B-UD-IQ3_XXS",
        "weights_sha256": Q36_SHA,
        "argv": [
            "--model", "/home/adaramir/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf",
            "--n-cpu-moe", "28", "--parallel", "1", "--port", "8080",
            "-b", "512", "-ub", "512", "-c", "32768", "-fa", "on",
            "-ctk", "q8_0", "-ctv", "q8_0", "-ngl", "99", "-t", "6",
        ],
    },
    "srv1_deepseek": {
        "model": "deepseek-coder-v2-16b",
        "weights_sha256": DEEPSEEK_SHA,
        "argv": [
            "--model", "/home/adaramir/models/moe/deepseek-coder-v2-16b.gguf",
            "--n-cpu-moe", "19", "--parallel", "2", "--port", "8080",
            "-b", "512", "-ub", "512", "-c", "8192", "-fa", "on",
            "-ngl", "99", "-t", "6",
        ],
    },
    "srv1_35b_b": {
        "model": "Qwen3.6-35B-A3B-UD-IQ3_XXS",
        "weights_sha256": Q36_SHA,
        "argv": [
            "--model", "/home/adaramir/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf",
            "--n-cpu-moe", "30", "--parallel", "2", "--port", "8080",
            "-b", "512", "-ub", "512", "-c", "16384", "-fa", "on",
            "-ngl", "99", "-t", "6",
        ],
    },
}


def main() -> int:
    rig_id = digest("rig-", rig_fields)
    out = {
        "rig": {"name": "srv1", "rig_id": rig_id, "fields": rig_fields},
        "units": {},
    }
    for name, spec in UNITS.items():
        fields = unit_fields(spec["weights_sha256"], spec["argv"])
        out["units"][name] = {
            "unit_id": digest("unt-", fields),
            "fields": fields,
        }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
