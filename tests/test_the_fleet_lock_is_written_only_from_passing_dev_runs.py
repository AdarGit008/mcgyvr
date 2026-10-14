"""The fleet lock is written only from passing dev runs, and checks what it pins.

``mcgyvr fleet lock`` writes two kinds of file:
- ``records/fleet/<fleet>.json``: the layout's sha256, the fleet's ``next``
  list, and each switch's dev evidence;
- ``records/fleet/rigs/<rig->/<combination>.json``: a combination's
  validation, shared by every fleet that uses it.

Committing them is the approval; live reads them and never writes them. What
the lock checks comes from the fleet file and from dev: a rig's card, and each
combination's overhead (Σ CUDA contexts of its units + driver reserve), are
**measured in dev**, not declared. Locking refuses, naming what failed:

* a combination no dev run passed; a listed switch whose rig move never ran, or
  ran without recording its downtime and start/wake times;
* a combination whose overhead was never measured, or whose units' room plus its
  overhead exceeds the card, an asleep unit's room included;
* a vLLM unit whose KV size is not pinned (``--kv-cache-memory-bytes``);
* a unit whose reply cannot finish inside its request timeout at its validated
  warm decode speed;
* NVMe use (swap, mmap) that costs warm decode more than its tolerance against
  a no-NVMe baseline. A model too big for any no-NVMe run is locked against its
  own value and marked so. The locked value is the as-run figure;
* any restart in a dev validation;
* an outside unit answering at a rig unit's address; a policy ladder naming a
  unit the fleet does not have.

It locks only the combinations a fleet lists, leaves a combination no edit
touched byte for byte, and locks a switch on a rig move another switch already
ran.

The tolerances here are placeholders: these tests pin the rule, never the
number.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.fleetlocks import (
    EVIDENCE,
    FLEET,
    FLT02,
    FLT05,
    _lock,
    combination_files,
    edited,
    write,
)


def test_the_lock_files_each_fleet_and_each_rig_combination_once(
    tmp_path: Path,
) -> None:
    lock = _lock()
    write(lock, tmp_path)
    where = tmp_path / "records" / "fleet"
    for name in ("flt-05", "flt-02"):
        text = (where / f"{name}.json").read_text(encoding="utf-8")
        record = json.loads(text)
        assert re.fullmatch(r"[0-9a-f]{64}", record["layout_sha256"]), record
        assert record["next"] == FLEET["fleets"][name]["next"], record
        assert "downtime_s" in text, f"{name} carries no switch evidence: {text}"
    combinations = combination_files(tmp_path)
    assert len(combinations) == 2, combinations
    records = [json.loads(path.read_text(encoding="utf-8")) for path in combinations]
    assert "api.example.invalid" not in json.dumps(records), (
        "an outside unit is never locked"
    )
    locked = {record["approved"]["box2_7b"]["warm_decode_tok_s"] for record in records}
    assert locked == {58.0, 57.0}, "the locked warm decode is the as-run figure"


def test_a_combination_no_dev_run_passed_is_not_locked(tmp_path: Path) -> None:
    lock = _lock()
    evidence = edited(EVIDENCE)
    evidence["combinations"][0]["passed"] = False
    with pytest.raises(lock.LockRefusedError, match="flt-05"):
        write(lock, tmp_path, evidence=evidence)


def test_a_listed_switch_whose_rig_move_never_ran_is_not_locked(
    tmp_path: Path,
) -> None:
    lock = _lock()
    evidence = edited(EVIDENCE)
    evidence["moves"] = evidence["moves"][1:]
    with pytest.raises(lock.LockRefusedError) as refused:
        write(lock, tmp_path, evidence=evidence)
    said = str(refused.value)
    assert "flt-05" in said and "flt-02" in said, said


def test_a_switch_run_that_recorded_no_times_is_not_locked(tmp_path: Path) -> None:
    lock = _lock()
    evidence = edited(EVIDENCE)
    del evidence["moves"][0]["downtime_s"]
    with pytest.raises(lock.LockRefusedError, match="downtime_s"):
        write(lock, tmp_path, evidence=evidence)


def test_a_combination_whose_overhead_dev_never_measured_is_not_locked(
    tmp_path: Path,
) -> None:
    """Overhead is each combination's own reading, never a rig's: the CUDA
    context differs per card and per engine
    (``mcgyvr-lab/records/plans/fleet-identity.md`` §8)."""
    lock = _lock()
    evidence = edited(EVIDENCE)
    del evidence["combinations"][1]["overhead_mib"]
    with pytest.raises(lock.LockRefusedError, match="overhead"):
        write(lock, tmp_path, evidence=evidence)


def test_every_units_room_plus_overhead_must_fit_its_card_asleep_or_awake(
    tmp_path: Path,
) -> None:
    """9000 + 2800 + 600 = 12400 MiB on a 12000 MiB card: refused for flt-05
    too, where the 3B is asleep, because an asleep unit keeps its room."""
    lock = _lock()
    fleet = edited(FLEET)
    fleet["units"]["box2_7b"]["room_mib"] = 9000
    fleet["fleets"] = {"flt-05": {"layout": {"box2": FLT05}, "next": []}}
    evidence = edited(EVIDENCE)
    evidence["combinations"] = evidence["combinations"][:1]
    evidence["moves"] = []
    with pytest.raises(lock.LockRefusedError) as refused:
        write(lock, tmp_path, fleet=fleet, evidence=evidence)
    said = str(refused.value)
    assert "box2" in said and "overhead" in said, said


def test_a_vllm_unit_whose_kv_size_is_not_pinned_is_not_locked(
    tmp_path: Path,
) -> None:
    lock = _lock()
    fleet = edited(FLEET)
    del fleet["units"]["box2_7b"]["kv_cache_memory_bytes"]
    with pytest.raises(lock.LockRefusedError, match="kv_cache_memory_bytes"):
        write(lock, tmp_path, fleet=fleet)


def test_a_reply_its_unit_cannot_finish_inside_its_timeout_is_not_locked(
    tmp_path: Path,
) -> None:
    """1024 tokens at 5 tok/s is 204.8 s, past a 180 s request timeout."""
    lock = _lock()
    evidence = edited(EVIDENCE)
    for row in evidence["combinations"]:
        row["warm_decode_tok_s"]["box2_7b"] = 5.0
        row["baseline_tok_s"]["box2_7b"] = 5.1
    with pytest.raises(lock.LockRefusedError, match="request_timeout_s"):
        write(lock, tmp_path, evidence=evidence)


def test_nvme_use_is_locked_only_where_warm_decode_holds_against_its_baseline(
    tmp_path: Path,
) -> None:
    """58.4 tok/s with nothing on NVMe, 55 as the combination runs: 5.8% slower,
    past a 3% tolerance."""
    lock = _lock()
    evidence = edited(EVIDENCE)
    evidence["combinations"][0]["warm_decode_tok_s"]["box2_7b"] = 55.0
    with pytest.raises(lock.LockRefusedError) as refused:
        write(lock, tmp_path, evidence=evidence)
    said = str(refused.value)
    assert "box2_7b" in said and "baseline" in said, said


def test_a_model_with_no_no_nvme_run_is_locked_on_its_own_value_and_marked(
    tmp_path: Path,
) -> None:
    lock = _lock()
    evidence = edited(EVIDENCE)
    for row in evidence["combinations"]:
        row["baseline_tok_s"]["box2_7b"] = None
    write(lock, tmp_path, evidence=evidence)
    written = " ".join(
        path.read_text(encoding="utf-8") for path in combination_files(tmp_path)
    )
    assert "no baseline: NVMe required" in written, written


def test_a_restart_in_a_dev_validation_is_not_locked(tmp_path: Path) -> None:
    lock = _lock()
    evidence = edited(EVIDENCE)
    evidence["combinations"][1]["restarts"]["box2_3b"] = 1
    with pytest.raises(lock.LockRefusedError, match="restarts"):
        write(lock, tmp_path, evidence=evidence)


def test_an_outside_unit_may_not_answer_at_a_rig_units_address(
    tmp_path: Path,
) -> None:
    lock = _lock()
    fleet = edited(FLEET)
    fleet["units"]["cloud"]["address"] = "http://box2:8002"
    with pytest.raises(lock.LockRefusedError, match="http://box2:8002"):
        write(lock, tmp_path, fleet=fleet)


def test_a_policy_ladder_naming_a_unit_the_fleet_lacks_is_not_locked(
    tmp_path: Path,
) -> None:
    lock = _lock()
    with pytest.raises(lock.LockRefusedError, match="ghost"):
        write(lock, tmp_path, policy={"ladder": ["box2_3b", "ghost"]})


def test_evidence_for_a_combination_no_fleet_lists_is_not_locked(
    tmp_path: Path,
) -> None:
    lock = _lock()
    evidence = edited(EVIDENCE)
    evidence["combinations"].append(
        {
            **evidence["combinations"][1],
            "slots": [["box2_7b", "asleep"], ["box2_3b", "awake"]],
            "warm_decode_tok_s": {"box2_3b": 105.0},
            "baseline_tok_s": {"box2_3b": 107.0},
        }
    )
    write(lock, tmp_path, evidence=evidence)
    assert len(combination_files(tmp_path)) == 2, combination_files(tmp_path)


def test_editing_one_fleet_leaves_every_other_combination_record_untouched(
    tmp_path: Path,
) -> None:
    """flt-05 frees the 3B's room; flt-02's combination record is not rewritten."""
    lock = _lock()
    write(lock, tmp_path)
    before = {path.name: path.read_bytes() for path in combination_files(tmp_path)}
    freed: list[Any] = [["box2_7b", "awake"], None]
    fleet = edited(FLEET)
    fleet["fleets"]["flt-05"]["layout"]["box2"] = freed
    evidence = edited(EVIDENCE)
    evidence["combinations"][0] = {
        **evidence["combinations"][0],
        "slots": freed,
        "restarts": {"box2_7b": 0},
        "attention_backend": {"box2_7b": "FLASH_ATTN"},
    }
    evidence["moves"] = [
        {
            "rig": "box2",
            "from": freed,
            "to": FLT02,
            "passed": True,
            "downtime_s": 0.4,
            "wake_s": {"box2_3b": 30.0},
        },
        {
            "rig": "box2",
            "from": FLT02,
            "to": freed,
            "passed": True,
            "downtime_s": 0.2,
            "wake_s": {},
        },
    ]
    write(lock, tmp_path, fleet=fleet, evidence=evidence)
    after = {path.name: path.read_bytes() for path in combination_files(tmp_path)}
    common = before.keys() & after.keys()
    assert common, (sorted(before), sorted(after))
    rewritten = sorted(name for name in common if before[name] != after[name])
    assert rewritten == [], f"an edit to flt-05 rewrote {rewritten}"


def test_a_fleet_switch_is_locked_on_a_rig_move_another_switch_ran(
    tmp_path: Path,
) -> None:
    """flt-02 → flt-06 is the same box2 move as flt-02 → flt-05, which ran."""
    lock = _lock()
    fleet = edited(FLEET)
    fleet["fleets"]["flt-06"] = {"layout": {"box2": FLT05}, "next": ["flt-02"]}
    fleet["fleets"]["flt-02"]["next"] = ["flt-05", "flt-06"]
    write(lock, tmp_path, fleet=fleet)
    assert (tmp_path / "records" / "fleet" / "flt-06.json").is_file()


def test_mcgyvr_fleet_lock_is_a_command() -> None:
    from mcgyvr.cli import main

    code: object
    try:
        code = main(["fleet", "lock", "--help"])
    except SystemExit as exited:
        code = exited.code
    assert code == 0, (
        f"mcgyvr must be able to: lock a fleet with `mcgyvr fleet lock` (exit {code})"
    )


def test_the_wake_limit_is_the_validated_wake_plus_its_tolerance() -> None:
    """The limit is the lock's tolerance added to the validated wake, whatever
    that tolerance is; the values are the measurement branch's."""
    lock = _lock()
    assert lock.wake_limit_s(20.0, {"s": 0.5}) == pytest.approx(20.5)
    assert lock.wake_limit_s(0.25, {"s": 0.1}) == pytest.approx(0.35)


def test_the_wake_ratio_in_code_and_the_hand_set_wake_timeout_are_gone() -> None:
    from mcgyvr import wake
    from mcgyvr.config import field_at

    assert not hasattr(wake, "DEVIATION_RATIO"), (
        "a wake is judged against its lock, not a ratio written in code"
    )
    assert field_at("budgets.wake_timeout_s") is None, (
        "the wake limit is derived from the lock, not a budget set by hand"
    )
