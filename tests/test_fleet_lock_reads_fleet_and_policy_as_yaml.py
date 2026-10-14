"""`mcgyvr fleet lock` reads `fleet.yaml` and `policy.yaml`, not JSON only."""

from __future__ import annotations

import json
from pathlib import Path

from tests.fleetlocks import FLEET_YAML
from tests.fleetlocks import YAML_EVIDENCE as EVIDENCE

POLICY_YAML = "ladder: [box2_7b]\n"


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
    assert (tmp_path / "lock" / "flt-05.json").is_file()
