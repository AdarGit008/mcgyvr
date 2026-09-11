"""An alert pulls its combination at once, until a re-validation is committed.

RED. ``mcgyvr.fleet.alerts`` does not exist and ``mcgyvr fleet`` is not a
command. The one predicted-against-observed record mcgyvr keeps is a wake time
under ``/tmp`` (``src/mcgyvr/wake.py:217``, ``:341``). The intent is
``records/plans/fleet-identity.md`` §5 and §7 (owner, 2026-09-10 and
2026-09-11).

* Every observation is filed under the journal, stamped with the fleet, rig,
  combination and unit it was computed for, and nothing goes under ``/tmp``.
* **Judged:**
  - restarts: exactly 0, with no tolerance reaching them;
  - warm decode: downward, against its locked as-run value;
  - llama.cpp card memory: upward;
  - L2 wake time: against its locked value;
  - a switch's downtime: against its dev run.
* **Recorded, never alerted:**
  - swap and major faults, because NVMe use is allowed wherever warm decode
    holds;
  - cold wake, vLLM RAM and Shmem, until they are measured.
* Dev fails on an alert. Live warns once, counts repeats, and **pulls the
  combination at once**: its units stop taking work, requests already running
  finish, and its containers stay up to be inspected, so a pull asks for no
  stop.
* Nothing clears on its own. A pull clears only when the combination's
  validation is re-committed; ``rejudge`` reports and pulls nothing (proposed,
  not ruled: plan §12).
* With every combination pulled, live refuses all work loudly, naming each.

Tolerances are placeholders: the rule is pinned, the values are measured on
``red/fleet-identity-measurements``.
"""

from __future__ import annotations

import importlib
import json
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from tests.red_port.conftest import required

RIG2 = "rig-" + "2" * 64
CMB = "cmb-" + "a" * 64
CMB_OTHER = "cmb-" + "b" * 64
UNIT = "unt-" + "7" * 64
OTHER = "unt-" + "3" * 64
SWITCH = "flt-05 -> flt-02"
RUN_ID = "run-20260911T120000-0a1b2c3d"
LEASE_ID = "lease-0a1b2c3d"
STAMP: dict[str, str] = {
    "fleet": "flt-05",
    "rig_id": RIG2,
    "combination_id": CMB,
    "unit_id": UNIT,
}
#: Placeholder locked values and tolerances, per unit or switch and parameter.
APPROVED: dict[str, dict[str, dict[str, Any]]] = {
    UNIT: {
        "warm_decode_tok_s": {"expected": 30.0, "tolerance": {"pct": 10.0}},
        "card_mib": {"expected": 7000.0, "tolerance": {"abs": 32.0}},
        "l2_wake_s": {"expected": 0.25, "tolerance": {"s": 0.1}},
    },
    SWITCH: {"downtime_s": {"expected": 0.3, "tolerance": {"s": 1.0}}},
}


def _alerts() -> Any:
    return required(
        "judge observations against their locked values, pull a combination on a "
        "live alert, and clear it only on a re-committed validation",
        lambda: importlib.import_module("mcgyvr.fleet.alerts"),
    )


def seen(field: str, observed: float, unit_id: str = UNIT) -> dict[str, Any]:
    return {"unit_id": unit_id, "field": field, "observed": observed}


def check(
    alerts: Any,
    observations: Sequence[Mapping[str, Any]],
    journal: Path,
    *,
    profile: str = "live",
    stamp: Mapping[str, str] = STAMP,
    run_id: str = RUN_ID,
    approved: Mapping[str, Any] = APPROVED,
) -> list[dict[str, Any]]:
    return list(
        alerts.check(
            observations,
            approved=approved,
            profile=profile,
            journal_dir=journal,
            stamp=stamp,
            run_id=run_id,
            lease_id=LEASE_ID,
        )
    )


def rows(journal: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in journal.rglob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_every_observation_is_filed_under_the_journal_by_what_it_was_computed_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alerts = _alerts()
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    journal = tmp_path / "journal"
    first = alerts.record(journal, STAMP, {"card_mib": 7544})
    second = alerts.record(journal, STAMP, {"card_mib": 7546})
    assert first == second and Path(first).is_relative_to(journal)
    where = Path(first).relative_to(journal).as_posix()
    assert CMB in where and UNIT in where, where
    filed = [json.loads(line) for line in Path(first).read_text().splitlines()]
    assert [row["card_mib"] for row in filed] == [7544, 7546]
    assert all({k: row[k] for k in STAMP} == STAMP for row in filed), filed
    assert list(scratch.iterdir()) == []


def test_a_dev_run_with_an_alert_fails(tmp_path: Path) -> None:
    alerts = _alerts()
    with pytest.raises(alerts.AlertError, match="restarts"):
        check(alerts, [seen("restarts", 1)], tmp_path / "journal", profile="dev")


def test_a_single_restart_alerts_however_loose_everything_else(
    tmp_path: Path,
) -> None:
    """Even a tolerance keyed to restarts does not reach them."""
    alerts = _alerts()
    loose = {
        UNIT: {
            "warm_decode_tok_s": {"expected": 30.0, "tolerance": {"pct": 1000.0}},
            "card_mib": {"expected": 7000.0, "tolerance": {"abs": 1.0e9}},
            "restarts": {"expected": 0, "tolerance": {"abs": 5}},
        }
    }
    assert (
        check(alerts, [seen("restarts", 0)], tmp_path / "quiet", approved=loose) == []
    )
    raised = check(alerts, [seen("restarts", 1)], tmp_path / "journal", approved=loose)
    assert [alert["field"] for alert in raised] == ["restarts"]


def test_warm_decode_alerts_only_below_its_approved_value_less_tolerance(
    tmp_path: Path,
) -> None:
    alerts = _alerts()
    assert check(alerts, [seen("warm_decode_tok_s", 29.0)], tmp_path / "a") == []
    assert check(alerts, [seen("warm_decode_tok_s", 40.0)], tmp_path / "b") == []
    raised = check(alerts, [seen("warm_decode_tok_s", 26.0)], tmp_path / "c")
    assert [(a["field"], a["direction"]) for a in raised] == [
        ("warm_decode_tok_s", "down")
    ]


def test_card_memory_alerts_only_above_its_approved_value_plus_tolerance(
    tmp_path: Path,
) -> None:
    alerts = _alerts()
    assert check(alerts, [seen("card_mib", 7020.0)], tmp_path / "a") == []
    assert check(alerts, [seen("card_mib", 6000.0)], tmp_path / "b") == []
    raised = check(alerts, [seen("card_mib", 7040.0)], tmp_path / "c")
    assert [(a["field"], a["direction"]) for a in raised] == [("card_mib", "up")]


def test_swap_and_major_faults_are_recorded_and_never_alerted(
    tmp_path: Path,
) -> None:
    alerts = _alerts()
    journal = tmp_path / "journal"
    paging = [
        seen("swap_out_pages", 565534),
        seen("swap_in_pages", 1200),
        seen("major_faults", 188000),
    ]
    assert check(alerts, paging, journal) == []
    filed = {row.get("field") for row in rows(journal)}
    assert {"swap_out_pages", "swap_in_pages", "major_faults"} <= filed, filed


def test_cold_wake_vllm_ram_and_shmem_are_recorded_until_measured_and_l2_wake_is_judged(
    tmp_path: Path,
) -> None:
    alerts = _alerts()
    journal = tmp_path / "journal"
    unmeasured = [
        seen("cold_wake_s", 999.0),
        seen("vllm_ram_gib", 99.0),
        seen("shmem_mib", 99999.0),
    ]
    assert check(alerts, unmeasured, journal) == []
    filed = {row.get("field") for row in rows(journal)}
    assert {"cold_wake_s", "vllm_ram_gib", "shmem_mib"} <= filed, filed
    raised = check(alerts, [seen("l2_wake_s", 0.5)], tmp_path / "l2")
    assert [(a["field"], a["direction"]) for a in raised] == [("l2_wake_s", "up")]


def test_a_live_switch_slower_than_its_dev_run_alerts_naming_the_switch(
    tmp_path: Path,
) -> None:
    alerts = _alerts()
    within = {"switch": SWITCH, "field": "downtime_s", "observed": 1.2}
    assert check(alerts, [within], tmp_path / "a") == []
    slower = {"switch": SWITCH, "field": "downtime_s", "observed": 5.0}
    raised = check(alerts, [slower], tmp_path / "b")
    assert [(a["switch"], a["field"]) for a in raised] == [(SWITCH, "downtime_s")]


def test_a_live_alert_pulls_its_combination_at_once_and_its_units_stop_routing(
    tmp_path: Path,
) -> None:
    alerts = _alerts()
    journal, lock_root = tmp_path / "journal", tmp_path / "repo"
    raised = check(alerts, [seen("warm_decode_tok_s", 20.0)], journal)
    assert not any(a.get("action") in {"stop", "down", "clean"} for a in raised), (
        "a pull leaves its containers up for inspection"
    )
    assert set(alerts.pulled(journal, lock_root)) == {CMB}
    units = {UNIT: CMB, OTHER: CMB_OTHER}
    assert list(alerts.routable(units, journal, lock_root)) == [OTHER]


def test_a_pull_clears_only_when_its_validation_is_recommitted(
    tmp_path: Path,
) -> None:
    alerts = _alerts()
    journal, lock_root = tmp_path / "journal", tmp_path / "repo"
    check(alerts, [seen("warm_decode_tok_s", 20.0)], journal)
    check(alerts, [seen("warm_decode_tok_s", 30.0)], journal, run_id="run-later")
    assert set(alerts.pulled(journal, lock_root)) == {CMB}, (
        "a clean reading later does not clear a pull"
    )
    record = lock_root / "records" / "fleet" / "rigs" / RIG2 / f"{CMB}.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"validated_at": "2000-01-01T00:00:00Z"}))
    assert set(alerts.pulled(journal, lock_root)) == {CMB}, (
        "a validation older than the alert does not clear it"
    )
    record.write_text(json.dumps({"validated_at": "2999-01-01T00:00:00Z"}))
    assert dict(alerts.pulled(journal, lock_root)) == {}


def test_with_every_combination_pulled_live_refuses_all_work_naming_each(
    tmp_path: Path,
) -> None:
    alerts = _alerts()
    journal, lock_root = tmp_path / "journal", tmp_path / "repo"
    check(alerts, [seen("restarts", 1)], journal)
    other = {**STAMP, "combination_id": CMB_OTHER, "unit_id": OTHER}
    check(alerts, [seen("restarts", 1, OTHER)], journal, stamp=other)
    with pytest.raises(alerts.AllPulledError) as refused:
        alerts.routable({UNIT: CMB, OTHER: CMB_OTHER}, journal, lock_root)
    said = str(refused.value)
    assert CMB in said and CMB_OTHER in said, said


def test_a_repeated_alert_warns_once_and_is_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two runs, not one: what was said is the journal's memory, not a process's."""
    alerts = _alerts()
    journal, lock_root = tmp_path / "journal", tmp_path / "repo"
    check(alerts, [seen("warm_decode_tok_s", 20.0)], journal, run_id="run-a")
    first = capsys.readouterr().err
    again = check(alerts, [seen("warm_decode_tok_s", 21.0)], journal, run_id="run-b")
    repeated = capsys.readouterr().err
    assert "warm_decode_tok_s" in first
    assert [a["field"] for a in again] == ["warm_decode_tok_s"], "a repeat is judged"
    assert "warm_decode_tok_s" not in repeated, f"warned again: {repeated}"
    counts = {
        (entry["unit_id"], entry["field"]): entry["count"]
        for entry in alerts.pulled(journal, lock_root)[CMB]
    }
    assert counts == {(UNIT, "warm_decode_tok_s"): 2}


def test_rejudging_reports_what_a_tighter_tolerance_finds_and_pulls_nothing(
    tmp_path: Path,
) -> None:
    alerts = _alerts()
    journal, lock_root = tmp_path / "journal", tmp_path / "repo"
    assert check(alerts, [seen("warm_decode_tok_s", 28.0)], journal) == []
    tighter = {UNIT: {**APPROVED[UNIT]}}
    tighter[UNIT]["warm_decode_tok_s"] = {"expected": 30.0, "tolerance": {"pct": 5.0}}
    found = alerts.rejudge(journal, CMB, tighter)
    assert [(f["unit_id"], f["field"]) for f in found] == [(UNIT, "warm_decode_tok_s")]
    assert dict(alerts.pulled(journal, lock_root)) == {}, "rejudge only reports"


def test_the_operator_reads_a_live_alert_on_stderr_and_from_mcgyvr_fleet_alerts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run's own output carries no alert: that channel is the caller's, and
    the caller never sees a fleet, a rig or a unit."""
    from mcgyvr.cli import main

    alerts = _alerts()
    journal = tmp_path / "journal"
    check(alerts, [seen("warm_decode_tok_s", 20.0)], journal)
    out, err = capsys.readouterr()
    assert out == "", out
    warned = [line for line in err.splitlines() if line.startswith("warning:")]
    assert len(warned) == 1, err
    for word in ("warm_decode_tok_s", "flt-05", "mcgyvr fleet alerts"):
        assert word in warned[0], f"{word!r} missing from {warned[0]!r}"
    try:
        code = main(["fleet", "alerts", "--journal", str(journal)])
    except SystemExit as exited:
        pytest.fail(
            "mcgyvr must be able to: list pulled combinations with "
            f"`mcgyvr fleet alerts`\n  argparse exited {exited.code}",
            pytrace=False,
        )
    listed = capsys.readouterr().out
    assert code == 0
    for word in (CMB, UNIT, "warm_decode_tok_s"):
        assert word in listed, f"{word!r} missing from {listed!r}"
