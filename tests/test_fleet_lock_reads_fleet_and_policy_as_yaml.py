"""`mcgyvr fleet lock` reads `fleet.yaml` and `policy.yaml`, not JSON only.

RED. ``_fleet_lock`` reads ``--fleet``, ``--evidence`` and ``--policy`` with
``json.loads`` (``src/mcgyvr/cli.py:2723-2727``), so an operator's
``fleet.yaml`` and ``policy.yaml`` — the two files ``mcgyvr.fleet.files``
(``load_fleet`` / ``load_policy``) already parse — never reach the lock. The
intent is ``records/plans/fleet-identity.md`` §2 and §4: the operator authors
the two YAML files, and ``mcgyvr fleet lock`` locks from them. Evidence stays
JSON because a dev run produces it.
"""

from __future__ import annotations

import json
from pathlib import Path

FLEET_YAML = """\
units:
  srv2_7b:
    rig: srv2
    unit_id: unt-7777777777777777777777777777777777777777777777777777777777777777
    engine: vllm
    address: http://srv2:8002
    model: Qwen/Qwen2.5-Coder-7B-Instruct-AWQ
    room_mib: 6800
    kv_cache_memory_bytes: 2147483648
    attention_backend: FLASH_ATTN
    width: 8
    window: 4096
    output_tokens: 1024
    request_timeout_s: 180
rigs:
  srv2:
    rig_id: rig-2222222222222222222222222222222222222222222222222222222222222222
fleets:
  flt-05:
    layout: {srv2: [[srv2_7b, awake]]}
    next: []
"""

POLICY_YAML = "ladder: [srv2_7b]\n"

EVIDENCE = {
    "rigs": {"srv2": {"card_mib": 12000}},
    "combinations": [
        {
            "rig": "srv2",
            "slots": [["srv2_7b", "awake"]],
            "passed": True,
            "overhead_mib": 600,
            "restarts": {"srv2_7b": 0},
            "warm_decode_tok_s": {"srv2_7b": 58.0},
            "baseline_tok_s": {"srv2_7b": 59.0},
            "prefill_tok_s": {"srv2_7b": 1450.0},
            "attention_backend": {"srv2_7b": "FLASH_ATTN"},
            "validated_at": "2026-09-11T10:00:00Z",
        }
    ],
    "moves": [],
}


def test_fleet_lock_reads_fleet_and_policy_as_yaml(tmp_path: Path) -> None:
    fleet = tmp_path / "fleet.yaml"
    fleet.write_text(FLEET_YAML, encoding="utf-8")
    policy = tmp_path / "policy.yaml"
    policy.write_text(POLICY_YAML, encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(EVIDENCE), encoding="utf-8")

    from mcgyvr.cli import main

    refused: object = None
    try:
        code = main(
            [
                "fleet",
                "lock",
                "--fleet",
                str(fleet),
                "--evidence",
                str(evidence),
                "--policy",
                str(policy),
                "--root",
                str(tmp_path),
            ]
        )
    except json.JSONDecodeError as exc:
        code = 99
        refused = exc

    assert code == 0, (
        "mcgyvr must be able to: lock a fleet from fleet.yaml and policy.yaml, "
        f"not only from JSON (got {refused!r})"
    )
    assert (tmp_path / "records" / "fleet" / "flt-05.json").is_file()
