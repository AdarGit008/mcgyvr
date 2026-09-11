"""Prefill is judged like warm decode; CUDA_Host and the backend are only recorded.

RED. ``mcgyvr.fleet.alerts`` does not exist. The intent is
``records/plans/fleet-identity.md`` §5 and §7, as extended by the gaps a
comparison of the serving terms against the plan found (owner, 2026-09-11).

* **Prefill** alerts only below its locked as-run value less tolerance: a slow
  prompt read costs every request's first token, and nothing judged it.
* **CUDA_Host** (llama.cpp's pinned host compute buffer) is recorded beside
  every observation and never alerted. It is a figure of the unit, not of the
  rig: it moves with the KV type, the model, ``-ub`` and the context (for
  example 5.88 to 6.88 MiB for gpt-oss over ``-c 2048`` to ``16384``, the same on
  both rigs, ``records/evidence/2026-09-05-context-decomposition/``), and every
  one of those is in ``unt-``.
* **The attention backend** a vLLM unit reports at start is recorded, stamped
  like any observation, so a figure says which kernel produced it.

Tolerances are placeholders: the rule is pinned, the values are measured on
``red/fleet-identity-measurements``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.test_an_alert_pulls_its_combination_until_it_is_revalidated import (
    APPROVED,
    STAMP,
    UNIT,
    _alerts,
    check,
    rows,
    seen,
)


def test_prefill_alerts_only_below_its_approved_value_less_tolerance(
    tmp_path: Path,
) -> None:
    """Locked at 440 tok/s with a 5% tolerance: 420 holds, 400 alerts."""
    alerts = _alerts()
    assert check(alerts, [seen("prefill_tok_s", 420.0)], tmp_path / "a") == []
    assert check(alerts, [seen("prefill_tok_s", 900.0)], tmp_path / "b") == []
    raised = check(alerts, [seen("prefill_tok_s", 400.0)], tmp_path / "c")
    assert [(a["field"], a["direction"]) for a in raised] == [("prefill_tok_s", "down")]


def test_cuda_host_and_the_attention_backend_are_recorded_and_never_alerted(
    tmp_path: Path,
) -> None:
    """Even a tolerance keyed to CUDA_Host does not make it an alert."""
    alerts = _alerts()
    journal = tmp_path / "journal"
    keyed: dict[str, Any] = {
        UNIT: {
            **APPROVED[UNIT],
            "cuda_host_mib": {"expected": 98.01, "tolerance": {"abs": 1.0}},
        }
    }
    assert check(alerts, [seen("cuda_host_mib", 9999.0)], journal, approved=keyed) == []
    assert "cuda_host_mib" in {row.get("field") for row in rows(journal)}
    filed = alerts.record(journal, STAMP, {"attention_backend": "FLASHINFER"})
    lines = [json.loads(line) for line in Path(filed).read_text().splitlines()]
    backends = [row for row in lines if row.get("attention_backend") == "FLASHINFER"]
    assert backends, lines
    assert all({k: row[k] for k in STAMP} == STAMP for row in backends), backends
