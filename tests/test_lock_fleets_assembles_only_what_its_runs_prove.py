"""lock-fleets stops on what its rulings name, and locks only what its runs prove.

``records/measurements/lock-fleets/assemble_evidence.py`` (owner, 2026-09-15):

* ``check`` is the one stop-and-ask list, run after every entry of a window;
* ``assemble`` writes the evidence ``mcgyvr.fleet.lock`` reads, for every
  combination and move, and refuses by name what the runs do not prove;
* ``tolerance`` derives a prefill class tolerance from the locked value.

Every file a window leaves is written by :mod:`tests.lockfleets_window`; no rig
is reached.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.fleet import lock
from mcgyvr.fleet.files import load_fleet, load_policy
from mcgyvr.fleet.ids import rig_id
from tests.lockfleets_window import (
    TOLERANCES,
    USE,
    Window,
    assemble_module,
    context,
    fleet_doc,
    frozen_window,
    plan_module,
    snapshot,
    unit_id,
    use_doc,
)

Change = Callable[[dict[str, Any]], None]


def _set(path: str, value: Any) -> Change:
    """A change that sets ``payload[a][b]...`` to ``value``."""

    def change(payload: dict[str, Any]) -> None:
        keys = path.split(".")
        where: Any = payload
        for key in keys[:-1]:
            where = where[key]
        where[keys[-1]] = value

    return change


def _both(*changes: Change) -> Change:
    def change(payload: dict[str, Any]) -> None:
        for one in changes:
            one(payload)

    return change


@pytest.fixture
def window(tmp_path: Path) -> Window:
    return frozen_window(tmp_path)


def test_a_clean_window_gives_no_reason_to_stop_on_any_entry(window: Window) -> None:
    window.write_all()
    ctx = context(window)
    asm = assemble_module()
    for entry in window.runs.entries:
        assert asm.check(ctx, entry.rig, entry.id) == [], entry.id


STOPS: list[tuple[str, Change, str]] = [
    (
        "beta-03",
        _set("rig.failed", {"b_small": "no answer"}),
        "the rig row shows failed",
    ),
    ("beta-03", _set("rig.contended", ["b_small"]), "the rig row shows contended"),
    ("beta-03", _set("rig.busy", {"b_mid": 2}), "the rig row shows busy"),
    ("beta-04", _set("rig.unloaded", {"b_small": "not idle"}), "the load was not run"),
    (
        "beta-04",
        _set("units.b_small.load_peak_mib.errors", ["URLError: reset"]),
        "errors other than the 30-s close",
    ),
    (
        "beta-04",
        _set("units.b_small.load_peak_mib.idle_error", "/metrics unread"),
        "a status-page error during the idle wait",
    ),
    (
        "beta-04",
        _set("units.b_small.load_peak_mib.peak_mib", None),
        "no card sample shows the unit's container",
    ),
    (
        "alpha-02",
        _set("doc.load.load.samples", ["gpu_app=1,4000,ffff,llama-server\n"]),
        "no card sample shows the unit's container",
    ),
    ("alpha-02", _set("doc.load.load.limit_s", 25), "its limit_s is 25, not 30"),
    ("alpha-02", _set("doc.restarts", 1), "a_pair restarted 1 time(s)"),
    ("beta-03", _set("units.b_mid.restarts.observed", 2), "b_mid restarted 2 time(s)"),
    ("alpha-02", _set("sidecar", True), ".RIGMOVED sidecar"),
    ("beta-02", _set("sidecar", True), ".RIGMOVED sidecar"),
    (
        "alpha-02",
        _both(
            _set("write", False),
            _set("output", "run.py: REFUSED at data-30-placement.py — the placement\n"),
        ),
        "data-30 refused",
    ),
    (
        "alpha-02",
        _both(
            _set("write", False),
            _set("output", "gate 5: x\nrun.py: REFUSED at 02-rig.py — gate 2: busy\n"),
        ),
        "the door refused: run.py: REFUSED at 02-rig.py",
    ),
    (
        "alpha-02",
        _set("output", "ssh refused: the host it named is not the door's\n"),
        "the door refused: ssh refused:",
    ),
    (
        "alpha-03",
        _set("doc.snapshots.end.hostname", "alpha-moved"),
        "the rig id changed between runs",
    ),
    (
        "alpha-02",
        _set(
            "doc.markers.end",
            "### END uptime_since=2026-09-16T11:00:00Z "
            "pl1_uw=95000000 pl2_uw=120000000 ram_mt_s=3600",
        ),
        "the START and END markers differ: uptime_since",
    ),
    (
        "alpha-02",
        _set("doc.failure", "the launch of a_pair failed"),
        "the step failed: the launch of a_pair failed",
    ),
    (
        "beta-02",
        _set("step.units", [{"container": "mcgyvr-beta-b_small", "healthy": False}]),
        "the step failed: not serving after serve up",
    ),
    (
        "alpha-02",
        _set("doc.harness", {"error": "HarnessError: no decode sample"}),
        "the harness on the rig could not measure",
    ),
    ("alpha-07", _set("doc.rc.rc_drop", 1), "rc_drop is 1"),
    ("alpha-07", _set("doc.stamps.t2", {}), "no t2 for a_pair"),
    (
        "beta-19",
        _set("doc.stamps.rc", {"rc_stop": 0, "rc_drop": 0}),
        "the stopwatch filed no rc_compose",
    ),
    (
        "beta-19",
        _set("doc.compose_sha256", "d" * 64),
        "the compose file of two on beta differs between runs",
    ),
    (
        "alpha-02",
        _set("doc.vmstat.end.pswpout", 11),
        "pswpout rose during the run (10 -> 11)",
    ),
    (
        "alpha-02",
        _set("doc.load.load.samples", ["gpu_app=1,5800,x,llama-server\n"]),
        "no card sample",
    ),
    (
        "beta-01",
        _set(
            "doc.load.load.samples",
            [
                f"gpu_app=1,11950,{hashlib.sha256(b'beta-01').hexdigest()},llama-server\n"
            ],
        ),
        "b_big's peak 11950 + reserve 377 > card 12288",
    ),
    (
        "beta-05",
        _set("units.b_mid.load_peak_mib.peak_mib", 8600),
        "the peaks of two on beta",
    ),
    (
        "beta-04",
        _set("units.b_small.load_peak_mib.peak_mib", 4000),
        "b_small's peak 4000 > its cap 3911",
    ),
    (
        "beta-03",
        _set("units.b_small.attention_backend.observed", "TRITON_ATTN"),
        "reported attention backend TRITON_ATTN, not the pinned FLASH_ATTN",
    ),
    (
        "beta-03",
        _set("units.b_mid.attention_backend.observed", None),
        "b_mid reported no attention_backend",
    ),
]


@pytest.mark.parametrize(
    ("entry", "change", "said"), STOPS, ids=[f"{e}:{s[:40]}" for e, _, s in STOPS]
)
def test_check_stops_on_each_thing_the_rulings_name(
    window: Window, entry: str, change: Change, said: str
) -> None:
    window.write_all({entry: change})
    reasons = assemble_module().check(context(window), entry.split("-")[0], entry)
    assert any(said in reason for reason in reasons), reasons


def test_a_load_is_not_refused_for_unfinished_requests_or_a_late_idle_alone(
    window: Window,
) -> None:
    change = _both(
        _set("doc.load.load.closed_unfinished", 2),
        _set("doc.load.load.completed", 0),
        _set("doc.load.load.idle_after_close", False),
        _set("doc.load.load.idle_after_s", 41.5),
    )
    window.write_all({"alpha-02": change})
    assert assemble_module().check(context(window), "alpha", "alpha-02") == []


def test_check_names_an_entry_that_is_not_logged(window: Window) -> None:
    window.write_all(unlogged=frozenset({"alpha-02"}))
    assert assemble_module().check(context(window), "alpha", "alpha-02") == [
        "alpha-02 has no log row"
    ]


def test_a_clean_window_assembles_into_evidence_the_lock_accepts(
    window: Window, tmp_path: Path
) -> None:
    window.write_all()
    evidence, runs, lines = assemble_module().assemble(context(window))
    by_rig = {(c["rig"], c["slots"][0][0]): c for c in evidence["combinations"]}
    solo = by_rig[("alpha", "a_solo")]
    assert solo["warm_decode_tok_s"] == {"a_solo": 32.0}
    assert solo["prefill_tok_s"] == {"a_solo": 310.0}
    assert solo["card_peak_mib"] == {"a_solo": 4000}
    assert solo["overhead_mib"] == 399 and solo["restarts"] == {"a_solo": 0}
    assert solo["baseline_tok_s"] == {}
    assert solo["envelope"] == "records/evidence/2026-09-16-lock-fleets"
    pair = by_rig[("beta", "b_small")]
    assert pair["attention_backend"] == {"b_small": "FLASH_ATTN", "b_mid": "FLASH_ATTN"}
    assert "card_peak_mib" not in pair
    last_down = [e for e in window.runs.entries if e.kind == "serve-down"][-1]
    header = (
        window.root
        / last_down.envelope("2026-09-16")
        / f"{last_down.run_id('2026-09-16')}.run.json"
    )
    assert pair["validated_at"] == json.loads(header.read_text())["started_at"]
    assert evidence["rigs"]["alpha"] == {
        "card_mib": 6144,
        "snapshot": snapshot("alpha"),
    }
    assert len(evidence["moves"]) == 4
    move = next(
        m
        for m in evidence["moves"]
        if m["rig"] == "beta" and m["to"][0][0] == "b_small"
    )
    assert move == {
        "rig": "beta",
        "from": [["b_big", "awake"]],
        "to": [["b_small", "awake"], ["b_mid", "awake"]],
        "passed": True,
        "downtime_s": 60.0,
        "wake_s": {"b_small": 58.0, "b_mid": 58.0},
    }
    assert set(runs["runs"]) == {e.id for e in window.runs.entries}
    assert (
        f"  rigs.alpha.rig_id: rig-{'0' * 64} -> {rig_id(snapshot('alpha'))}" in lines
    )
    assert "  units.a_solo.room_mib: 5000 -> 4000" in lines

    fleet = fleet_doc()
    fleet["rigs"]["alpha"]["rig_id"] = rig_id(snapshot("alpha"))
    for line in lines:
        if ".room_mib: " in line and " -> " in line:
            name = line.split(".")[1]
            fleet["units"][name]["room_mib"] = int(line.rsplit(" ", 1)[1])
    policy = load_policy((window.root / "fleet-setup" / "policy.yaml").read_text())
    lock.write(tmp_path / "lock", fleet, evidence, policy=policy, tolerances=TOLERANCES)
    assert sorted(p.name for p in (tmp_path / "lock/records/fleet").glob("*.json")) == [
        "one.json",
        "two.json",
    ]


def _refused(window: Window, said: str) -> None:
    asm = assemble_module()
    with pytest.raises(asm.AssemblyRefusedError, match=said):
        asm.assemble(context(window))


@pytest.mark.parametrize(
    ("change", "unlogged", "said"),
    [
        (
            {},
            frozenset({"alpha-03"}),
            "a frozen entry is missing: alpha-03 has no log row",
        ),
        (
            {"alpha-02": _set("write", False)},
            frozenset(),
            "a frozen entry is missing: alpha-02: .* cannot be read",
        ),
        (
            {"beta-03": _set("write", False)},
            frozenset(),
            "a frozen entry is missing: beta-03: the journal holds no rig row",
        ),
        (
            {"beta-06": _set("write", False)},
            frozenset(),
            "a frozen entry is missing: beta-06 header",
        ),
        (
            {"alpha-01": _set("doc.restarts", 1)},
            frozenset(),
            "alpha-01 fails its check: a_solo restarted",
        ),
        (
            {"alpha-01": _set("doc.harness.figures.warm_decode_tok_s", 31.0)},
            frozenset(),
            "a_solo's warm_decode_tok_s 31.0 is not the median of its own samples",
        ),
        (
            {"beta-09": _set("units.b_mid.prefill_samples.observed", [1.0, 2.0, 3.0])},
            frozenset(),
            "b_mid's prefill_tok_s 11000.0 is not the median",
        ),
        (
            {"alpha-07": _set("doc.stamps.t1", 999.0)},
            frozenset(),
            "alpha-07: t1 999.0 is before t0 1000.0",
        ),
        (
            {"alpha-07": _set("doc.stamps.t2", {"a_pair": 1001.0})},
            frozenset(),
            "alpha-07: a_pair's t2 1001.0 is before t1 1002.0",
        ),
        (
            {"beta-21": _set("doc.stamps.t_compose", None)},
            frozenset(),
            "beta-21: a compose target filed no t_compose",
        ),
        (
            {"alpha-01": _set("doc.snapshots.end.gpu_reserve_mib", "405")},
            frozenset(),
            "the reserve read 405 MiB, more than 3 MiB from "
            "tools/runs/hosts.json's 399",
        ),
    ],
)
def test_assemble_refuses_by_name_what_the_runs_do_not_prove(
    window: Window, change: dict[str, Change], unlogged: frozenset[str], said: str
) -> None:
    window.write_all(change, unlogged)
    _refused(window, said)


def test_assemble_refuses_fewer_valid_runs_than_the_lock_needs(
    window: Window, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.write_all()
    monkeypatch.setattr(plan_module(), "K", 4)
    _refused(window, "one on alpha has 3 valid runs, and the lock needs 4")


def test_assemble_refuses_rooms_that_do_not_fit_the_card_together(
    tmp_path: Path,
) -> None:
    window = frozen_window(tmp_path, use=use_doc(unit_caps_on=[]))
    window.write_all(
        {
            "beta-04": _set("units.b_small.load_peak_mib.peak_mib", 3400),
            "beta-05": _set("units.b_mid.load_peak_mib.peak_mib", 8400),
            "beta-10": _set("units.b_small.load_peak_mib.peak_mib", 3900),
            "beta-11": _set("units.b_mid.load_peak_mib.peak_mib", 7800),
        }
    )
    _refused(
        window,
        r"two: beta units' room 12300 MiB plus overhead 377 MiB exceeds the card 12288",
    )


def test_assemble_refuses_a_reply_that_cannot_finish_in_its_timeout(
    tmp_path: Path,
) -> None:
    fleet = fleet_doc()
    fleet["units"]["a_solo"]["request_timeout_s"] = 10
    window = frozen_window(tmp_path, fleet=fleet)
    window.write_all()
    _refused(
        window,
        "a_solo: a reply of 512 tokens at 32.0 tok/s cannot finish inside "
        "request_timeout_s 10",
    )


def test_assemble_refuses_a_validation_not_after_the_journals_last_alert(
    window: Window,
) -> None:
    window.write_all()
    fleet = load_fleet((window.root / "fleet-setup" / "fleet.yaml").read_text())
    rig_ids = {rig: block["rig_id"] for rig, block in fleet["rigs"].items()}
    combination = lock._combination_id_for(
        rig_ids, {"a_solo": unit_id("a_solo")}, "alpha", [["a_solo", "awake"]]
    )
    where = window.journal / combination
    where.mkdir(parents=True)
    alert = {
        "unit_id": unit_id("a_solo"),
        "field": "prefill_tok_s",
        "alert": True,
        "at": "2026-09-16T23:59:59",
    }
    (where / f"{unit_id('a_solo')}.jsonl").write_text(json.dumps(alert) + "\n")
    _refused(
        window,
        "one on alpha: validated_at .* is not after the journal's last alert at "
        "2026-09-16T23:59:59",
    )


def test_assemble_refuses_a_rig_whose_pin_must_not_change(tmp_path: Path) -> None:
    fleet = fleet_doc()
    fleet["rigs"]["beta"]["rig_id"] = "rig-" + "1" * 64
    window = frozen_window(tmp_path, fleet=fleet)
    window.write_all()
    _refused(window, "beta's pin must not change")


def _tolerance_window(tmp_path: Path) -> Window:
    window = frozen_window(tmp_path)
    window.write_all()
    asm = assemble_module()
    evidence, _, _ = asm.assemble(context(window))
    (window.root / "fleet-setup" / "evidence.json").write_text(json.dumps(evidence))
    return window


def test_a_prefill_class_tolerance_is_taken_from_the_locked_value(
    tmp_path: Path,
) -> None:
    window = _tolerance_window(tmp_path)
    doc = assemble_module().tolerance(context(window), "llamacpp", "a_solo")
    assert doc["locked_prefill_tok_s"] == 310.0
    assert doc["run_medians"] == [310.0, 312.0, 309.0]
    assert len(doc["samples"]) == 9
    assert doc["worst_shortfall_pct"] == pytest.approx((310.0 - 290.0) / 310.0 * 100)
    assert doc["tolerance_pct"] == 7
    assert min(doc["shortfall_pct"]) == 0.0
    assert "15 samples" in doc["note"] and "max(1, ceil(" in doc["rule"]


@pytest.mark.parametrize(
    ("klass", "evidence_value", "change", "said"),
    [
        ("cpu_experts", None, None, "a_solo is in class llamacpp, not cpu_experts"),
        (
            "llamacpp",
            311.0,
            None,
            r"L 310.0 for a_solo is not evidence.json's prefill_tok_s \(\[311.0\]\)",
        ),
        (
            "llamacpp",
            None,
            _both(
                _set("doc.harness.figures.prefill_samples", [300.0, 320.0]),
                _set("doc.harness.figures.prefill_tok_s", 310.0),
            ),
            "has 8 prefill samples from 3 valid runs",
        ),
    ],
)
def test_a_prefill_tolerance_refuses_what_its_rule_does_not_take(
    tmp_path: Path,
    klass: str,
    evidence_value: float | None,
    change: Change | None,
    said: str,
) -> None:
    window = frozen_window(tmp_path)
    window.write_all({"alpha-03": change} if change else None)
    asm = assemble_module()
    evidence, _, _ = asm.assemble(context(window))
    if evidence_value is not None:
        solo = next(c for c in evidence["combinations"] if c["slots"][0][0] == "a_solo")
        solo["prefill_tok_s"]["a_solo"] = evidence_value
    (window.root / "fleet-setup" / "evidence.json").write_text(json.dumps(evidence))
    with pytest.raises(asm.AssemblyRefusedError, match=said):
        asm.tolerance(context(window), klass, "a_solo")


def test_the_plan_the_window_follows_is_the_one_frozen(window: Window) -> None:
    """The window's entries are the frozen RUNS.md's, so a check reads the order
    the driver ran and nothing rebuilt from today's fleet files."""
    assert [e.id for e in window.runs.entries] == [
        e.id for e in plan_module().read_runs(window.root, USE).entries
    ]
