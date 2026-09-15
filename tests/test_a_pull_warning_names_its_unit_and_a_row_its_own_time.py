"""A pull's warning names its unit, and each filed row carries its own time.

Owner, 2026-09-15 (F5). The first live probe (run-20260915T050342-42b9afd8)
printed ``warning: warm_decode_tok_s pulled b-small — see `mcgyvr fleet
alerts``` twice, identically, for two different units: no unit, rig or
combination was named. Every row it filed carried the run's start, 05:03:42,
though units were probed up to two minutes later; :func:`alerts.pulled` clears
a pull against the newest alert's ``at``, so a start time can clear a pull
that a later validation never covered.

* **The warning names the unit, its rig and its short combination id**:
  ``warning: srv1_coder warm_decode_tok_s pulled b-small (srv1, cmb-…)``.
* **A row's ``at`` is the moment its unit's measurement finished**, read from
  the probe's own ``now`` and ``clock``, in ``%Y-%m-%dT%H:%M:%S``: judged,
  contended and off-the-rig rows alike.
* **A caller of :func:`alerts.check` with no unit name or finish time** keeps
  the run id's time and names what it has.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tests.test_a_live_probe_is_judged_against_its_lock import (
    EVIDENCE,
    FLEET,
    HOLDING,
    NOW,
    RIG1,
    STAMP,
    UNIT_3B,
    UNIT_DS,
    FakeUnits,
    idle,
    live_home,
    lock_root,
    rows,
)

UNIT_CODER = "unt-" + "9" * 64
#: Each llama.cpp request takes this long on the fake clock.
LLAMA_REQUEST_S = 2.0
#: A llama.cpp probe is 9 requests: a warm-up, 5 decodes and 3 prefills.
LLAMA_PROBE_S = 9 * LLAMA_REQUEST_S

#: b-small with a second llama.cpp unit beside srv1_deepseek on srv1.
TWO_ON_SRV1: dict[str, Any] = copy.deepcopy(FLEET)
TWO_ON_SRV1["units"]["srv1_coder"] = {
    "rig": "srv1",
    "unit_id": UNIT_CODER,
    "address": "http://srv1:8081",
    "engine": "llama.cpp",
    "model": "qwen2.5-coder-7b",
    "width": 1,
    "window": 4096,
    "output_tokens": 2048,
    "request_timeout_s": 180,
    "room_mib": 3000,
    "launch": {"flags": ["-c", "4096", "-ngl", "99"]},
}
TWO_ON_SRV1["fleets"]["b-small"]["layout"]["srv1"] = [
    ["srv1_deepseek", "awake"],
    ["srv1_coder", "awake"],
]
TWO_EVIDENCE: dict[str, Any] = copy.deepcopy(EVIDENCE)
TWO_EVIDENCE["rigs"]["srv1"]["card_mib"] = 12288
_SRV1 = TWO_EVIDENCE["combinations"][1]
_SRV1["slots"] = [["srv1_deepseek", "awake"], ["srv1_coder", "awake"]]
_SRV1["restarts"]["srv1_coder"] = 0
_SRV1["warm_decode_tok_s"]["srv1_coder"] = 50.0
_SRV1["prefill_tok_s"]["srv1_coder"] = 900.0
_SRV1["card_peak_mib"]["srv1_coder"] = 2900
_SRV1["card_steady_mib"]["srv1_coder"] = 2880


class TimedUnits(FakeUnits):
    """:class:`FakeUnits` whose llama.cpp requests take time on the clock too,
    with a second llama.cpp unit answering at srv1:8081."""

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if not url.startswith("http://srv1:"):
            return super().post(url, payload, timeout)
        self.posts.append((url, payload))
        self.now += LLAMA_REQUEST_S
        unit = "coder" if url == "http://srv1:8081/completion" else "ds"
        assert url in {"http://srv1:8080/completion", "http://srv1:8081/completion"}
        if payload["n_predict"] == 256:
            return {"timings": {"predicted_per_second": self.rates[f"{unit}_decode"]}}
        if payload["n_predict"] == 16:
            return {"timings": {"prompt_per_second": self.rates[f"{unit}_prefill"]}}
        return {"timings": {"predicted_per_second": 1.0}}


def probe(fake: FakeUnits, in_flight: Any = idle) -> Any:
    from mcgyvr.fleet import probe as probe_module

    return probe_module.run(
        transport=fake, in_flight=in_flight, clock=fake.clock, now=NOW
    )


def warnings(err: str) -> list[str]:
    return [line for line in err.splitlines() if line.startswith("warning:")]


#: Both srv1 units slower than their class allows on the same field: 16.0 is
#: 50.9% under deepseek's 32.56 (48%), and 40.0 is 20% under coder's 50.0 (1%).
BOTH_SLOW = HOLDING | {"ds_decode": 16.0, "coder_decode": 40.0, "coder_prefill": 900.0}


def test_two_units_alerting_on_one_field_warn_two_lines_naming_unit_rig_and_cmb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = live_home(tmp_path, monkeypatch, TWO_ON_SRV1, TWO_EVIDENCE)
    capsys.readouterr()
    report = probe(TimedUnits(BOTH_SLOW))

    assert sorted((a["unit_id"], a["field"]) for a in report.alerts) == sorted(
        [(UNIT_DS, "warm_decode_tok_s"), (UNIT_CODER, "warm_decode_tok_s")]
    )
    combination = {
        r["combination_id"] for r in rows(journal / "fleet") if r["rig"] == "srv1"
    }
    assert len(combination) == 1, combination
    short = next(iter(combination))[:12] + "…"
    where = f"pulled b-small (srv1, {short}) — see `mcgyvr fleet alerts`"
    assert warnings(capsys.readouterr().err) == [
        f"warning: srv1_deepseek warm_decode_tok_s {where}",
        f"warning: srv1_coder warm_decode_tok_s {where}",
    ]


def test_each_units_rows_carry_the_moment_its_own_measurement_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The layout probes srv1_deepseek, then srv1_coder, then srv2_3b.

    deepseek's 9 requests end 18 s in; coder's 18 s after that; srv2_3b's
    vLLM requests, filed off the rig, 11.1 s after that.
    """
    journal = live_home(tmp_path, monkeypatch, TWO_ON_SRV1, TWO_EVIDENCE)
    probe(TimedUnits(BOTH_SLOW))

    at: dict[str, set[str]] = {}
    for row in rows(journal / "fleet"):
        at.setdefault(row["unit_id"], set()).add(row["at"])
    assert at == {
        UNIT_DS: {"2026-09-15T12:00:18"},  # judged, and alerted
        UNIT_CODER: {"2026-09-15T12:00:36"},  # judged, and alerted
        UNIT_3B: {"2026-09-15T12:00:47"},  # off the rig, recorded
    }


def test_a_contended_units_rows_carry_the_moment_its_measurement_finished(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = live_home(tmp_path, monkeypatch)
    reads: dict[str, int] = {}

    def later(name: str, unit: Mapping[str, Any]) -> int | None:
        reads[name] = reads.get(name, 0) + 1
        return 1 if name == "srv1_deepseek" and reads[name] > 1 else 0

    report = probe(TimedUnits(HOLDING), in_flight=later)
    assert report.contended == ["srv1_deepseek"]
    deepseek = [r for r in rows(journal / "fleet") if r["unit_id"] == UNIT_DS]
    assert deepseek and all(r.get("contended") is True for r in deepseek)
    assert {r["at"] for r in deepseek} == {"2026-09-15T12:00:18"}


def test_a_validation_between_the_run_start_and_the_units_finish_keeps_the_pull(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The probe starts 12:00:00 and srv1_deepseek's measurement ends 12:00:18.

    A lock validated at 12:00:09 did not see that measurement, so the pull
    stands; one validated at 12:00:19 did, and clears it.
    """
    from mcgyvr.fleet import alerts

    journal = live_home(tmp_path, monkeypatch)
    report = probe(TimedUnits(HOLDING | {"ds_decode": 16.0}))
    assert [(a["unit_id"], a["field"]) for a in report.alerts] == [
        (UNIT_DS, "warm_decode_tok_s")
    ]
    (record,) = (lock_root(tmp_path) / "records" / "fleet" / "rigs" / RIG1).glob(
        "cmb-*.json"
    )
    lock = json.loads(record.read_text(encoding="utf-8"))

    lock["validated_at"] = "2026-09-15T12:00:09Z"
    record.write_text(json.dumps(lock), encoding="utf-8")
    assert set(alerts.pulled(journal / "fleet", lock_root(tmp_path))) == {
        record.stem
    }, "a validation before the unit's measurement finished cleared its pull"

    lock["validated_at"] = "2026-09-15T12:00:19Z"
    record.write_text(json.dumps(lock), encoding="utf-8")
    assert alerts.pulled(journal / "fleet", lock_root(tmp_path)) == {}


def test_a_check_given_no_unit_name_or_time_keeps_the_run_time_and_names_what_it_has(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No name is guessed: the unit is named by its short id."""
    from mcgyvr.fleet import alerts

    journal = tmp_path / "journal"
    raised = list(
        alerts.check(
            [{"unit_id": UNIT_DS, "field": "warm_decode_tok_s", "observed": 16.0}],
            approved={UNIT_DS: {"warm_decode_tok_s": 32.56, "tolerance_pct": 48.0}},
            profile="live",
            journal_dir=journal,
            stamp=STAMP,
            run_id="run-20260915T120000-0a1b2c3d",
            lease_id="probe-0a1b2c3d",
        )
    )
    assert [a["field"] for a in raised] == ["warm_decode_tok_s"]
    assert [r["at"] for r in rows(journal)] == ["2026-09-15T12:00:00"]
    short_unit = UNIT_DS[:12] + "…"
    short_cmb = STAMP["combination_id"][:12] + "…"
    assert warnings(capsys.readouterr().err) == [
        f"warning: {short_unit} warm_decode_tok_s pulled b-small "
        f"(srv1, {short_cmb}) — see `mcgyvr fleet alerts`"
    ]
