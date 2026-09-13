"""The lock pins each combination's own overhead, card peak, backend and prefill.

RED. ``mcgyvr.fleet.lock`` does not exist. The intent is
``records/plans/fleet-identity.md`` §4, §5 and §8, as extended by the gaps a
comparison of the serving terms against the plan found (owner, 2026-09-11).

* **Overhead is a combination's, not a rig's.** The CUDA context differs per
  card and per engine: llama.cpp on srv1's GTX 1660 SUPER read 115.69 MiB where
  srv2's RTX 3060 read 146.69 for the same model and ``-ub``, though on two
  images (``records/evidence/2026-09-04-srv1-ncmoe-floor/srv1-buffer-probe.tsv:6``,
  ``srv2-buffer-probe.tsv:5``), and vLLM's driver and context, on one image,
  read 470 MiB on srv1 and 491 on srv2
  (``archive/docs/archive/decisions/0039-a-serving-memory-declaration-is-bytes-not-a-fraction-of-the-card.md:229-231``).
  A combination's dev run measures the contexts of exactly its units on
  exactly its card, so the fit uses that reading and nothing pooled.
* **A llama.cpp unit is locked on its measured card peak.** Its room must hold
  the highest reading across the load and the requests, and the 2.0 GB guessed
  for a model with no geometry (``DEFAULT_HEADROOM_GB``,
  ``src/mcgyvr/serving/__init__.py:553``) never stands in for that reading.
* **A vLLM unit pins its attention backend** (``--attention-backend``, which
  v0.26.0 resolves: ``records/evidence/2026-08-24-config-sweep/srv2-1.5B.jsonl:38``),
  and the lock files the backend the dev run reported. The card decides what is
  valid: srv1 (cc 7.5) reports ``TRITON_ATTN``
  (``records/evidence/2026-08-31-inventory/board3-srv1-off1v1.log:25``), srv2
  ``FLASH_ATTN`` (``records/evidence/2026-08-24-resolved-config/srv2-startup.log:22``),
  and ``FLASHINFER`` under an fp8 KV cache (``srv2-1.5B.jsonl:12``).
* **Prefill is locked as run**, beside warm decode, so a live run has a value
  to judge it against.

Tolerances and figures here are placeholders: the rule is pinned, the values
are measured on ``red/fleet-identity-measurements``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.test_the_fleet_lock_is_written_only_from_passing_dev_runs import (
    EVIDENCE,
    FLEET,
    RIG2,
    TOLERANCES,
    _lock,
    combination_files,
    edited,
    write,
)

RIG1 = "rig-" + "1" * 64
UQ36 = "unt-" + "6" * 64
#: srv1 serving Qwen3.6-35B-A3B from llama.cpp, one room slot.
FLT11: list[Any] = [["srv1_q36", "awake"]]

FLEET_SRV1: dict[str, Any] = {
    "rigs": {"srv1": {"rig_id": RIG1}},
    "units": {
        "srv1_q36": {
            "rig": "srv1",
            "unit_id": UQ36,
            "engine": "llama.cpp",
            "address": "http://srv1:8080",
            "room_mib": 5200,
            "width": 2,
            "window": 8192,
            "output_tokens": 1024,
            "request_timeout_s": 180.0,
        },
    },
    "fleets": {"flt-11": {"layout": {"srv1": FLT11}, "next": []}},
}

EVIDENCE_SRV1: dict[str, Any] = {
    "rigs": {"srv1": {"card_mib": 5726}},
    "combinations": [
        {
            "rig": "srv1",
            "slots": FLT11,
            "passed": True,
            "overhead_mib": 400,
            "restarts": {"srv1_q36": 0},
            "warm_decode_tok_s": {"srv1_q36": 21.0},
            "baseline_tok_s": {"srv1_q36": 21.5},
            "prefill_tok_s": {"srv1_q36": 95.9},
            "card_steady_mib": {"srv1_q36": 5124},
            "card_peak_mib": {"srv1_q36": 5150},
            "validated_at": "2026-09-11T11:00:00Z",
            "envelope": "records/evidence/2026-09-11-fleet-srv1/flt-11",
        },
    ],
    "moves": [],
}


def write_srv1(lock: Any, root: Path, evidence: dict[str, Any]) -> Any:
    return lock.write(
        root,
        FLEET_SRV1,
        evidence,
        policy={"ladder": ["srv1_q36"]},
        tolerances=TOLERANCES,
    )


def approved(root: Path, rig_id: str) -> list[dict[str, Any]]:
    where = root / "records" / "fleet" / "rigs" / rig_id
    return [
        json.loads(path.read_text(encoding="utf-8"))["approved"]
        for path in sorted(where.glob("cmb-*.json"))
    ]


def test_a_combination_is_fitted_with_its_own_overhead(tmp_path: Path) -> None:
    """6800 + 2800 + 2500 = 12100 MiB on a 12000 MiB card is refused for the
    combination whose dev run read 2500, whichever of the two it is; at 2400 it
    fits exactly, and each record keeps its own reading."""
    lock = _lock()
    for heavy, fleet in ((0, "flt-05"), (1, "flt-02")):
        evidence = edited(EVIDENCE)
        evidence["combinations"][heavy]["overhead_mib"] = 2500
        with pytest.raises(lock.LockRefusedError) as refused:
            write(lock, tmp_path / f"heavy-{heavy}", evidence=evidence)
        said = str(refused.value)
        assert "overhead" in said and fleet in said, said
    evidence = edited(EVIDENCE)
    evidence["combinations"][1]["overhead_mib"] = 2400
    write(lock, tmp_path / "fits", evidence=evidence)
    readings = [
        json.loads(path.read_text(encoding="utf-8"))["overhead_mib"]
        for path in combination_files(tmp_path / "fits")
    ]
    assert sorted(readings) == [600, 2400], readings


def test_a_llama_cpp_unit_is_locked_on_its_measured_card_peak_and_never_without_one(
    tmp_path: Path,
) -> None:
    lock = _lock()
    write_srv1(lock, tmp_path / "measured", EVIDENCE_SRV1)
    records = approved(tmp_path / "measured", RIG1)
    assert [r["srv1_q36"]["card_steady_mib"] for r in records] == [5124], records
    assert [r["srv1_q36"]["card_peak_mib"] for r in records] == [5150], records
    evidence = edited(EVIDENCE_SRV1)
    del evidence["combinations"][0]["card_peak_mib"]
    with pytest.raises(lock.LockRefusedError) as refused:
        write_srv1(lock, tmp_path / "guessed", evidence)
    said = str(refused.value)
    assert "srv1_q36" in said and "card_peak_mib" in said, said


def test_a_llama_cpp_unit_whose_card_peak_exceeds_its_room_is_not_locked(
    tmp_path: Path,
) -> None:
    """A room below the peak lets a neighbour's start fail or the unit OOM."""
    lock = _lock()
    evidence = edited(EVIDENCE_SRV1)
    evidence["combinations"][0]["card_peak_mib"]["srv1_q36"] = 5230
    with pytest.raises(lock.LockRefusedError) as refused:
        write_srv1(lock, tmp_path, evidence)
    said = str(refused.value)
    assert "srv1_q36" in said and "room" in said, said


def test_a_vllm_unit_whose_attention_backend_is_not_pinned_is_not_locked(
    tmp_path: Path,
) -> None:
    lock = _lock()
    fleet = edited(FLEET)
    del fleet["units"]["srv2_7b"]["attention_backend"]
    with pytest.raises(lock.LockRefusedError) as refused:
        write(lock, tmp_path, fleet=fleet)
    said = str(refused.value)
    assert "srv2_7b" in said and "attention_backend" in said, said


def test_the_lock_files_the_reported_backend_and_refuses_one_the_unit_did_not_pin(
    tmp_path: Path,
) -> None:
    lock = _lock()
    write(lock, tmp_path / "as-pinned")
    records = approved(tmp_path / "as-pinned", RIG2)
    reported = {r["srv2_7b"]["attention_backend"] for r in records}
    assert reported == {"FLASH_ATTN"}, records
    evidence = edited(EVIDENCE)
    evidence["combinations"][1]["attention_backend"]["srv2_3b"] = "TRITON_ATTN"
    with pytest.raises(lock.LockRefusedError) as refused:
        write(lock, tmp_path / "fell-back", evidence=evidence)
    said = str(refused.value)
    for word in ("srv2_3b", "TRITON_ATTN", "FLASH_ATTN"):
        assert word in said, f"{word!r} missing from {said!r}"


def test_prefill_is_locked_as_run_and_a_run_that_recorded_none_is_not_locked(
    tmp_path: Path,
) -> None:
    lock = _lock()
    write(lock, tmp_path / "recorded")
    assert len(combination_files(tmp_path / "recorded")) == 2
    locked = {
        r["srv2_7b"]["prefill_tok_s"] for r in approved(tmp_path / "recorded", RIG2)
    }
    assert locked == {1450.0, 1420.0}, "the locked prefill is the as-run figure"
    evidence = edited(EVIDENCE)
    del evidence["combinations"][1]["prefill_tok_s"]["srv2_3b"]
    with pytest.raises(lock.LockRefusedError) as refused:
        write(lock, tmp_path / "unrecorded", evidence=evidence)
    said = str(refused.value)
    assert "srv2_3b" in said and "prefill_tok_s" in said, said
