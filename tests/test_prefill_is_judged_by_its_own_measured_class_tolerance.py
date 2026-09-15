"""A live prefill is judged by its own measured class tolerance, not decode's.

Owner, 2026-09-15. ``records/plans/fleet-identity.md`` §12 records "Prefill
tolerance — ruled 8%" (B89), while the code judged a probe's prefill with the
warm decode class percent (``engine.warm_decode_class_pct``). An on-rig
``read --probe srv2_3b`` measured prefill 11157.62 against the locked 11500
(-2.98%), and it alerted at vLLM decode's 1%.

The prefill classes are those of
``records/measurements/fleet-identity-prefill-2026-09-12/README.md``, stated in
``tools/runs/derived.json`` as ``engine.prefill_class_pct``:

* **vLLM 8%**: the 3B's 7.86% worst single-sample shortfall, rounded up, after
  the single restart-tail outlier (the 7B's 9,460 tok/s) is dropped;
* **llama.cpp 1%**: 0.37% worst shortfall, floored to the rule's 1%;
* **CPU experts 1%**: 0.13% worst shortfall, floored to 1%.

Warm decode keeps its own classes (vLLM 1, llama.cpp 1, CPU experts 48). A
unit's class still comes from :func:`mcgyvr.fleet.tolerance.tolerance_class`
alone. Every judge of the two fields applies each its own percent: the probe
(:func:`mcgyvr.fleet.probe._approved` feeding :func:`mcgyvr.fleet.alerts.check`)
and :func:`mcgyvr.fleet.alerts.rejudge`. A row filed from here on carries the
percent its field was judged at.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from tests import test_a_live_probe_is_judged_against_its_lock as probed

REPO = Path(__file__).resolve().parent.parent
PREFILL_RECORD = (
    REPO
    / "records"
    / "measurements"
    / "fleet-identity-prefill-2026-09-12"
    / "results-prefill.json"
)
#: The 3B's median prefill in that record, whose worst sample sets vLLM's 8%.
THREE_B = "mcgyvr-srv2-Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001"
RUN_ID = "run-20260915T120000-0a1b2c3d"
LEASE_ID = "probe-0a1b2c3d"


# --- the numbers ------------------------------------------------------------


def test_prefill_and_decode_each_state_their_own_class_percents() -> None:
    from mcgyvr import derived

    measured = json.loads(PREFILL_RECORD.read_text(encoding="utf-8"))
    tolerances = derived.class_tolerances()

    assert tolerances["prefill_tok_s"] == {
        "vllm": float(math.ceil(measured["per_unit"][THREE_B]["shortfall_pct"])),
        "llamacpp": float(measured["classes"]["llamacpp"]["tolerance_pct"]),
        "cpu_experts": float(measured["classes"]["cpu_experts"]["tolerance_pct"]),
    }
    assert tolerances["prefill_tok_s"] == {
        "vllm": 8.0,
        "llamacpp": 1.0,
        "cpu_experts": 1.0,
    }
    assert tolerances["warm_decode_tok_s"] == {
        "vllm": 1.0,
        "llamacpp": 1.0,
        "cpu_experts": 48.0,
    }


@pytest.mark.parametrize("name", ["vllm", "llamacpp", "cpu_experts"])
def test_an_absent_prefill_class_is_refused_by_name(name: str, tmp_path: Path) -> None:
    from mcgyvr import derived

    doc = json.loads((REPO / "tools/runs/derived.json").read_text(encoding="utf-8"))
    del doc["engine"]["prefill_class_pct"][name]
    path = tmp_path / "derived.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError, match="prefill_class_pct") as was:
        derived.class_tolerances(path=path)
    assert repr(name) in str(was.value), str(was.value)


def test_an_absent_prefill_entry_is_refused_by_name(tmp_path: Path) -> None:
    from mcgyvr import derived

    doc = json.loads((REPO / "tools/runs/derived.json").read_text(encoding="utf-8"))
    del doc["engine"]["prefill_class_pct"]
    path = tmp_path / "derived.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError, match="prefill_class_pct"):
        derived.class_tolerances(path=path)


# --- the probe's judge ------------------------------------------------------


def _approved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unit: str) -> Any:
    """The probe's view of ``unit``, from a promoted lock and derived.json."""
    from mcgyvr import derived
    from mcgyvr.fleet import probe
    from mcgyvr.fleet.admit import layout_ids

    probed.live_home(tmp_path, monkeypatch)
    fleet = probed.FLEET
    block = fleet["units"][unit]
    rig_id = fleet["rigs"][block["rig"]]["rig_id"]
    combination = layout_ids(fleet, fleet["fleets"]["b-small"]["layout"])[rig_id]
    approved = probe._approved(
        probed.lock_root(tmp_path),
        rig_id,
        combination,
        unit,
        block,
        derived.class_tolerances(),
    )
    stamp = {
        "fleet": "b-small",
        "rig": block["rig"],
        "rig_id": rig_id,
        "combination_id": combination,
        "unit_id": block["unit_id"],
    }
    return approved, stamp


def _judged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unit: str,
    field: str,
    value: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The alerts ``value`` raises for ``unit``'s ``field``, and the rows filed."""
    from mcgyvr.fleet import alerts

    approved, stamp = _approved(tmp_path, monkeypatch, unit)
    journal = tmp_path / "journal" / "fleet"
    raised = list(
        alerts.check(
            [
                {
                    "unit_id": stamp["unit_id"],
                    "unit": unit,
                    "field": field,
                    "observed": value,
                }
            ],
            approved=approved,
            profile="live",
            journal_dir=journal,
            stamp=stamp,
            run_id=RUN_ID,
            lease_id=LEASE_ID,
        )
    )
    return raised, probed.rows(journal)


def test_a_vllm_prefill_2_98_pct_under_its_lock_does_not_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The on-rig srv2_3b reading of 2026-09-15: 11157.62 against 11500."""
    raised, filed = _judged(tmp_path, monkeypatch, "srv2_3b", "prefill_tok_s", 11157.62)
    assert raised == []
    assert [(r["field"], r["alert"]) for r in filed] == [("prefill_tok_s", False)]


def test_a_vllm_prefill_9_pct_under_its_lock_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """10465 is 9% under 11500: past vLLM prefill's 8%."""
    raised, _ = _judged(tmp_path, monkeypatch, "srv2_3b", "prefill_tok_s", 10465.0)
    assert [a["field"] for a in raised] == ["prefill_tok_s"]


def test_a_vllm_decode_2_pct_under_its_lock_still_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """124.1 is 2.05% under 126.7: past vLLM decode's 1%."""
    raised, _ = _judged(tmp_path, monkeypatch, "srv2_3b", "warm_decode_tok_s", 124.1)
    assert [a["field"] for a in raised] == ["warm_decode_tok_s"]


def test_a_cpu_experts_prefill_5_pct_under_its_lock_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """291.55 is 5.07% under 307.11: past CPU-experts prefill's 1%."""
    raised, _ = _judged(tmp_path, monkeypatch, "srv1_deepseek", "prefill_tok_s", 291.55)
    assert [a["field"] for a in raised] == ["prefill_tok_s"]


def test_a_cpu_experts_decode_5_pct_under_its_lock_does_not_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """30.93 is 5.0% under 32.56: inside CPU-experts decode's 48%."""
    raised, _ = _judged(
        tmp_path, monkeypatch, "srv1_deepseek", "warm_decode_tok_s", 30.93
    )
    assert raised == []


@pytest.mark.parametrize(
    ("unit", "field", "value", "pct"),
    [
        ("srv2_3b", "prefill_tok_s", 11157.62, 8.0),
        ("srv2_3b", "warm_decode_tok_s", 124.1, 1.0),
        ("srv1_deepseek", "prefill_tok_s", 291.55, 1.0),
        ("srv1_deepseek", "warm_decode_tok_s", 30.93, 48.0),
    ],
)
def test_a_judged_row_carries_the_percent_its_field_was_judged_at(
    unit: str,
    field: str,
    value: float,
    pct: float,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, filed = _judged(tmp_path, monkeypatch, unit, field, value)
    assert [(r["field"], r["tolerance_pct"]) for r in filed] == [(field, pct)]


def test_the_live_probe_judges_a_cpu_experts_unit_by_each_fields_percent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first live probe's deepseek prefill, 291.55, alerts at 1%; a decode
    5% under its lock holds at 48%."""
    journal = probed.live_home(tmp_path, monkeypatch)
    report = probed.run_probe(
        probed.FakeUnits(probed.HOLDING | {"ds_prefill": 291.55, "ds_decode": 30.93})
    )

    assert [(a["unit_id"], a["field"]) for a in report.alerts] == [
        (probed.UNIT_DS, "prefill_tok_s")
    ]
    deepseek = {
        r["field"]: r
        for r in probed.rows(journal / "fleet")
        if r["unit_id"] == probed.UNIT_DS
    }
    assert (
        deepseek["prefill_tok_s"]["alert"],
        deepseek["prefill_tok_s"]["tolerance_pct"],
    ) == (
        True,
        1.0,
    )
    assert (
        deepseek["warm_decode_tok_s"]["alert"],
        deepseek["warm_decode_tok_s"]["tolerance_pct"],
    ) == (False, 48.0)


# --- rejudge ----------------------------------------------------------------


def test_rejudge_applies_each_fields_own_percent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A journal holding srv2_3b's prefill 2.98% under and decode 2.05% under:
    rejudged against the probe's view, only the decode is found."""
    from mcgyvr.fleet import alerts

    approved, stamp = _approved(tmp_path, monkeypatch, "srv2_3b")
    journal = tmp_path / "rejudged"
    for field, value in (("prefill_tok_s", 11157.62), ("warm_decode_tok_s", 124.1)):
        alerts.record(
            journal,
            stamp,
            {"field": field, "observed": value, "run_id": RUN_ID, "lease_id": LEASE_ID},
        )

    found = alerts.rejudge(journal, stamp["combination_id"], approved)
    assert found == [{"unit_id": stamp["unit_id"], "field": "warm_decode_tok_s"}]
