"""A parameter past its approved tolerance alerts the operator once and flags its shape.

RED. ``mcgyvr.fleet.alerts`` does not exist and ``mcgyvr fleet`` is not a
command. The one predicted-against-observed alert mcgyvr has is a wake's:
``Wake.deviation`` (``src/mcgyvr/wake.py:187``) against a tolerance written in
code, ``DEVIATION_RATIO = 1.5`` (``src/mcgyvr/wake.py:98``), remembered under
``/tmp`` (``src/mcgyvr/wake.py:217``, ``:341``) and printed on every deviation
(``:437``). The intent is ``records/plans/fleet-identity.md``: ID-3 (a tolerance
is not hashed, lives in the approval record, and changing it re-judges what was
recorded), §3 (what is EXPECTED), §4 "On deviation", §5 (approval carries the
tolerances) and P6.

Owner's rulings, 2026-09-10: an alert for each parameter or bucket; dev fails
loud; live warns, records, keeps serving and flags the shape for re-validation;
the orchestrator never sees a config or a backend, so an alert is the
operator's to read and never a request to the caller. Tolerance values are
researched separately and none is stated here: every figure in ``COVERED`` is a
placeholder, and the mechanism reads whatever the approval record holds.

Buckets, from §3 and the OBSERVE step of §4::

    bucket          parameter                       alerts when observed is
    card_memory     card_mib                        above expected + tolerance
    host_ram        ram_mib, shmem_mib              above expected + tolerance
    paging          swap_out_pages, swap_in_pages,  above expected + tolerance
                    major_faults
    process_health  restarts                        not 0; no tolerance (§11)
    speed           warm_decode_tok_s               below expected - tolerance
                    wake_s                          either side (wake.py:91-97)

A tolerance is ``{"abs": x}`` in the parameter's unit or ``{"pct": p}`` of what
was expected, keyed by a parameter or by its bucket, and a parameter's own
overrides its bucket's. Approval refuses a parameter nothing covers and a key
that names nothing a tolerance can loosen.

Reused, not restated: ``mcgyvr.fleet.observe.act`` stays the one place a
deviation raises on dev and warns on live, and ``observe.record`` the one writer
under the journal keyed by rig shape and unit
(``tests/test_a_deviation_fails_a_dev_run_and_warns_a_live_one.py``), whose
``field`` key an alert keeps; ``ts`` is the journal's wall clock
(``src/mcgyvr/telemetry.py:752``); ``lease_id`` is the door's
(``src/mcgyvr/serving/gatelib.py:405``); the warning is the ``warning:`` line
(``src/mcgyvr/wake.py:437``, ``src/mcgyvr/cli.py:2108``). A BOUND has no
tolerance: past it is ``bounds.judge``'s deviation
(``tests/test_a_bound_is_small_verified_and_scoped.py``).
"""

from __future__ import annotations

import importlib
import json
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from tests.red_port.conftest import required
from tests.test_a_live_run_is_an_approved_fleet_shape_or_nothing import BASE, CFG

FSH = "fsh-" + "f" * 64
RSH = "rsh-" + "2" * 64
RSH_QUIET = "rsh-" + "3" * 64
UNIT = "unt-" + "7" * 64
RUN_ID = "run-20260910T120000-0a1b2c3d"
LEASE_ID = "lease-0a1b2c3d"
PASSED = {RSH: {"passed": True, "envelope": "records/evidence/x/validation"}}

#: Every bucket a tolerance may loosen, each at a placeholder figure (§11).
COVERED: dict[str, dict[str, float]] = {
    "card_memory": {"pct": 10.0},
    "host_ram": {"pct": 10.0},
    "paging": {"pct": 10.0},
    "speed": {"pct": 10.0},
}

BUCKETS = {
    "card_mib": "card_memory",
    "ram_mib": "host_ram",
    "shmem_mib": "host_ram",
    "swap_out_pages": "paging",
    "swap_in_pages": "paging",
    "major_faults": "paging",
    "restarts": "process_health",
    "warm_decode_tok_s": "speed",
    "wake_s": "speed",
}


def _alerts(behavior: str) -> Any:
    return required(behavior, lambda: importlib.import_module("mcgyvr.fleet.alerts"))


def _fleet_shape(behavior: str) -> Any:
    return required(
        behavior, lambda: importlib.import_module("mcgyvr.fleet.fleet_shape")
    )


def unit(n: int) -> str:
    return "unt-" + f"{n:x}" * 64


def seen(
    field: str, expected: float, observed: float, unit_id: str = UNIT
) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "field": field,
        "expected": expected,
        "observed": observed,
    }


def live(
    alerts: Any,
    observations: Sequence[Mapping[str, Any]],
    journal: Path,
    tolerances: Mapping[str, Mapping[str, float]] = COVERED,
    *,
    rig_shape_id: str = RSH,
    run_id: str = RUN_ID,
) -> list[dict[str, Any]]:
    """One OBSERVE step of a live run under an approved fleet shape."""
    return list(
        alerts.check(
            observations,
            tolerances=tolerances,
            profile="live",
            journal_dir=journal,
            fleet_shape_id=FSH,
            rig_shape_id=rig_shape_id,
            run_id=run_id,
            lease_id=LEASE_ID,
        )
    )


def test_every_observed_parameter_sits_in_one_bucket() -> None:
    alerts = _alerts(
        "group every observed parameter into one bucket a tolerance can name"
    )
    assert {name: alerts.PARAMETERS[name].bucket for name in BUCKETS} == BUCKETS
    assert not set(alerts.PARAMETERS) & set(BUCKETS.values()), (
        "a parameter named like a bucket makes a tolerance key ambiguous"
    )


def test_each_parameter_alerts_only_on_the_side_that_harms(tmp_path: Path) -> None:
    """Memory and paging up, decode down, a wake either way.

    A wake faster than predicted usually loaded something other than what was
    asked (``src/mcgyvr/wake.py:91-97``), so it alerts too; a decode faster than
    expected does not.
    """
    alerts = _alerts(
        "alert memory and paging only upward, decode only downward, a wake both ways"
    )
    raised = live(
        alerts,
        [
            seen("card_mib", 1000, 1200, unit(1)),
            seen("card_mib", 1000, 800, unit(2)),
            seen("shmem_mib", 1000, 1200, unit(3)),
            seen("shmem_mib", 1000, 800, unit(4)),
            seen("swap_in_pages", 0, 40, unit(5)),
            seen("warm_decode_tok_s", 30.0, 20.0, unit(6)),
            seen("warm_decode_tok_s", 30.0, 40.0, unit(7)),
            seen("wake_s", 10.0, 20.0, unit(8)),
            seen("wake_s", 10.0, 5.0, unit(9)),
        ],
        tmp_path / "journal",
    )
    assert sorted((a["unit_id"], a["field"], a["direction"]) for a in raised) == [
        (unit(1), "card_mib", "up"),
        (unit(3), "shmem_mib", "up"),
        (unit(5), "swap_in_pages", "up"),
        (unit(6), "warm_decode_tok_s", "down"),
        (unit(8), "wake_s", "up"),
        (unit(9), "wake_s", "down"),
    ]


def test_a_single_restart_alerts_live_and_fails_dev_however_loose_the_rest(
    tmp_path: Path,
) -> None:
    """Restarts are exactly 0 (plan §11): no tolerance reaches them."""
    alerts = _alerts("hold restarts at exactly zero, outside every tolerance")
    loose = {bucket: {"pct": 1000.0} for bucket in COVERED}
    assert live(alerts, [seen("restarts", 0, 0)], tmp_path / "quiet", loose) == []
    raised = live(alerts, [seen("restarts", 0, 1)], tmp_path / "journal", loose)
    assert [(a["field"], a["bucket"]) for a in raised] == [
        ("restarts", "process_health")
    ]
    observe = required(
        "act on a deviation by profile, and file observations under the journal",
        lambda: importlib.import_module("mcgyvr.fleet.observe"),
    )
    with pytest.raises(observe.DeviationError, match="restarts"):
        alerts.check(
            [seen("restarts", 0, 1)],
            tolerances=loose,
            profile="dev",
            journal_dir=tmp_path / "dev",
            fleet_shape_id=None,
            rig_shape_id=RSH,
            run_id=RUN_ID,
            lease_id=LEASE_ID,
        )


def test_a_parameters_own_tolerance_overrides_its_buckets(tmp_path: Path) -> None:
    alerts = _alerts("let a parameter's own tolerance override its bucket's")
    raised = live(
        alerts,
        [seen("shmem_mib", 1000, 1050, unit(1)), seen("ram_mib", 1000, 1050, unit(2))],
        tmp_path / "journal",
        {**COVERED, "shmem_mib": {"pct": 2.0}},
    )
    assert [(a["field"], a["tolerance"]) for a in raised] == [
        ("shmem_mib", {"pct": 2.0})
    ], "shmem is judged by its own 2%, ram_mib by host_ram's 10%"


def test_a_tolerance_is_absolute_in_its_unit_or_a_percent_of_what_was_expected(
    tmp_path: Path,
) -> None:
    alerts = _alerts(
        "read a tolerance as an absolute allowance or a percent of what was expected"
    )
    absolute = {**COVERED, "card_memory": {"abs": 100.0}}
    percent = {**COVERED, "card_memory": {"pct": 10.0}}
    over_abs = live(alerts, [seen("card_mib", 2000, 2101)], tmp_path / "a", absolute)
    assert [a["field"] for a in over_abs] == ["card_mib"]
    assert live(alerts, [seen("card_mib", 2000, 2101)], tmp_path / "p", percent) == []
    over_pct = live(alerts, [seen("card_mib", 2000, 2201)], tmp_path / "p", percent)
    assert [a["field"] for a in over_pct] == ["card_mib"]


def test_approval_refuses_a_parameter_no_tolerance_covers() -> None:
    """Refused at approval, never silently unalerted on live."""
    fleet_shape = _fleet_shape(
        "refuse to approve a fleet shape that leaves an observed parameter "
        "without a tolerance"
    )
    approved = fleet_shape.approve(CFG, FSH, [RSH], PASSED, COVERED)
    assert approved["tolerances"] == COVERED
    no_speed = {bucket: t for bucket, t in COVERED.items() if bucket != "speed"}
    partial = {**no_speed, "wake_s": {"pct": 10.0}}
    with pytest.raises(fleet_shape.ApprovalRefusedError) as refused:
        fleet_shape.approve(CFG, FSH, [RSH], PASSED, partial)
    said = str(refused.value)
    assert "warm_decode_tok_s" in said and "wake_s" not in said, said


def test_approval_refuses_a_tolerance_on_nothing_it_can_loosen() -> None:
    fleet_shape = _fleet_shape(
        "refuse a tolerance keyed by no parameter or bucket, restarts included"
    )
    for stray in ("shmem_pc", "restarts", "process_health"):
        keyed = {**COVERED, stray: {"abs": 1.0}}
        with pytest.raises(fleet_shape.ApprovalRefusedError, match=stray):
            fleet_shape.approve(CFG, FSH, [RSH], PASSED, keyed)


def test_a_live_alert_names_its_parameter_bucket_and_what_it_was_computed_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alerts = _alerts(
        "file a live alert under the journal naming the parameter, its bucket, "
        "the tolerance applied and the shape, unit, run and lease it was judged for"
    )
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    journal = tmp_path / "journal"
    before = time.time()
    live(alerts, [seen("swap_out_pages", 0, 565534)], journal)
    after = time.time()
    filed = [
        (path, json.loads(line))
        for path in journal.rglob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    alert_rows = [(p, row) for p, row in filed if row.get("record_kind") == "alert"]
    assert len(alert_rows) == 1, filed
    path, row = alert_rows[0]
    where = path.relative_to(journal).as_posix()
    assert RSH in where and UNIT in where, f"not keyed by rig shape and unit: {where}"
    assert before <= row["ts"] <= after
    want = {
        "field": "swap_out_pages",
        "bucket": "paging",
        "direction": "up",
        "expected": 0,
        "observed": 565534,
        "tolerance": COVERED["paging"],
        "profile": "live",
        "fleet_shape_id": FSH,
        "rig_shape_id": RSH,
        "unit_id": UNIT,
        "run_id": RUN_ID,
        "lease_id": LEASE_ID,
    }
    assert {key: row.get(key) for key in want} == want
    assert list(scratch.iterdir()) == []


def test_a_repeated_deviation_warns_once_and_is_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Twenty runs meeting one paging unit are one warning and a count of twenty.

    Two runs, not one: the memory of what was said is the journal's, not a
    process's.
    """
    alerts = _alerts(
        "warn once per rig shape, unit and parameter, and count every repeat"
    )
    journal = tmp_path / "journal"
    live(alerts, [seen("swap_out_pages", 0, 1200)], journal, run_id="run-a")
    first = capsys.readouterr().err
    again = live(alerts, [seen("swap_out_pages", 0, 1300)], journal, run_id="run-b")
    repeated = capsys.readouterr().err
    live(alerts, [seen("major_faults", 0, 90)], journal, run_id="run-b")
    other = capsys.readouterr().err
    assert "swap_out_pages" in first
    assert [a["field"] for a in again] == ["swap_out_pages"], "a repeat is judged"
    assert "swap_out_pages" not in repeated, f"warned again: {repeated}"
    assert "major_faults" in other, "another parameter is a first occurrence"
    flagged = alerts.flagged(journal)[RSH]
    counts = {(e["unit_id"], e["field"]): e["count"] for e in flagged}
    assert counts == {(UNIT, "swap_out_pages"): 2, (UNIT, "major_faults"): 1}


def test_a_live_deviation_flags_its_rig_shape_for_re_validation(
    tmp_path: Path,
) -> None:
    """The flag is read from the alerts filed, so it cannot disagree with them."""
    alerts = _alerts("flag a rig shape a live deviation was filed against")
    journal = tmp_path / "journal"
    live(alerts, [seen("swap_out_pages", 0, 1200)], journal)
    live(alerts, [seen("card_mib", 1000, 1010)], journal, rig_shape_id=RSH_QUIET)
    flagged = alerts.flagged(journal)
    assert set(flagged) == {RSH}, "a shape within every tolerance is not flagged"
    assert [(e["unit_id"], e["field"]) for e in flagged[RSH]] == [
        (UNIT, "swap_out_pages")
    ]


def test_a_tolerance_change_re_judges_what_was_recorded_and_renames_nothing(
    tmp_path: Path,
) -> None:
    """ID-3. Every observation is recorded, inside its tolerance or not, so a
    tightened tolerance finds what the old one let through, under the same ids.
    """
    alerts = _alerts(
        "re-judge the observations recorded for a rig shape against new tolerances"
    )
    journal = tmp_path / "journal"
    tight = {**COVERED, "host_ram": {"pct": 5.0}}
    assert live(alerts, [seen("shmem_mib", 1000, 1060)], journal, COVERED) == []
    assert alerts.flagged(journal) == {}
    rejudged = alerts.rejudge(journal, RSH, tight)
    assert [
        (a["rig_shape_id"], a["unit_id"], a["field"], a["tolerance"]) for a in rejudged
    ] == [(RSH, UNIT, "shmem_mib", {"pct": 5.0})]
    assert alerts.rejudge(journal, RSH, COVERED) == []


def test_the_operator_reads_a_live_alert_on_stderr_and_from_mcgyvr_fleet_alerts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run's own output carries no alert: that channel is the caller's, and
    the caller is never asked to act on a shape it cannot see. Reading alerts
    acts on nothing, so a live config naming no fleet shape may read them.
    """
    from mcgyvr.cli import main

    alerts = _alerts("tell the operator of a live alert, and where to read them all")
    journal = tmp_path / "journal"
    live(alerts, [seen("swap_out_pages", 0, 565534)], journal)
    out, err = capsys.readouterr()
    assert out == "", out
    warned = [line for line in err.splitlines() if line.startswith("warning:")]
    assert len(warned) == 1, err
    for word in ("swap_out_pages", "paging", "mcgyvr fleet alerts"):
        assert word in warned[0], f"{word!r} missing from {warned[0]!r}"
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(BASE + f"journal:\n  dir: {journal}\n", encoding="utf-8")
    try:
        code = main(["fleet", "alerts", "--config", str(config)])
    except SystemExit as exited:
        pytest.fail(
            "mcgyvr must be able to: list flagged shapes with `mcgyvr fleet alerts`"
            f"\n  argparse exited {exited.code}",
            pytrace=False,
        )
    listed = capsys.readouterr().out
    assert code == 0
    for word in (RSH, UNIT, "swap_out_pages"):
        assert word in listed, f"{word!r} missing from {listed!r}"
