#!/usr/bin/env python3
"""Assemble fleet-setup/evidence-srv2.json in the lock's exact shape."""
from __future__ import annotations

import json

EVIDENCE = {
    "rigs": {"srv2": {"card_mib": 12288}},
    "combinations": [
        {
            "rig": "srv2",
            "slots": [["srv2_35b_256k", "awake"]],
            "passed": True,
            "overhead_mib": 490,
            "restarts": {"srv2_35b_256k": 0},
            "warm_decode_tok_s": {"srv2_35b_256k": 48.2},
            "baseline_tok_s": {},
            "prefill_tok_s": {"srv2_35b_256k": 629.8},
            "card_steady_mib": {"srv2_35b_256k": 10597},
            "card_peak_mib": {"srv2_35b_256k": 10597},
            "validated_at": "2026-09-13T21:44:00Z",
            "envelope": "records/measurements/fleet-setup-2026-09-13/srv2/a-solo-running.json",
        },
        {
            "rig": "srv2",
            "slots": [["srv2_3b", "awake"], ["srv2_7b", "awake"]],
            "passed": True,
            "overhead_mib": 610.5,
            "restarts": {"srv2_3b": 0, "srv2_7b": 0},
            "warm_decode_tok_s": {"srv2_3b": 126.7, "srv2_7b": 68.3},
            "baseline_tok_s": {},
            "prefill_tok_s": {"srv2_3b": 11500.0, "srv2_7b": 12059.0},
            "attention_backend": {"srv2_3b": "FLASH_ATTN", "srv2_7b": "FLASH_ATTN"},
            "validated_at": "2026-09-13T21:44:00Z",
            "envelope": "records/measurements/fleet-setup-2026-09-13/srv2/b-small-3b.json",
        },
        {
            "rig": "srv2",
            "slots": [["srv2_80b", "awake"]],
            "passed": True,
            "overhead_mib": 524,
            "restarts": {"srv2_80b": 0},
            "warm_decode_tok_s": {"srv2_80b": 28.4},
            "baseline_tok_s": {},
            "prefill_tok_s": {"srv2_80b": 280.9},
            "card_steady_mib": {"srv2_80b": 11523},
            "card_peak_mib": {"srv2_80b": 11523},
            "validated_at": "2026-09-13T21:44:00Z",
            "envelope": "records/measurements/fleet-setup-2026-09-13/srv2/b-big-80b.json",
        },
    ],
    "moves": [
        {
            "rig": "srv2",
            "from": [["srv2_3b", "awake"], ["srv2_7b", "awake"]],
            "to": [["srv2_80b", "awake"]],
            "passed": True,
            "downtime_s": 70.33,
            "wake_s": {"srv2_80b": 70.33},
        },
        {
            "rig": "srv2",
            "from": [["srv2_80b", "awake"]],
            "to": [["srv2_3b", "awake"], ["srv2_7b", "awake"]],
            "passed": True,
            "downtime_s": 179.57,
            "wake_s": {"srv2_3b": 91.55, "srv2_7b": 179.57},
        },
    ],
}

text = json.dumps(EVIDENCE, indent=2, sort_keys=True) + "\n"
with open(
    "/home/adaramir/pi_agent/projects/mcgyvr-measurements/fleet-setup/evidence-srv2.json",
    "w",
) as f:
    f.write(text)
print(text)
