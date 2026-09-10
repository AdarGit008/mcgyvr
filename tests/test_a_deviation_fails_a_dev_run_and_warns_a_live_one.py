"""A deviation fails a dev run; on live it warns, records and keeps serving.

RED. ``mcgyvr.fleet.observe`` does not exist, and the only predicted-against-
actual record mcgyvr keeps is a wake time under ``/tmp`` that this machine
cannot write (``src/mcgyvr/wake.py:341``; flexibility-2026-09-09, Defects: "The Waker
has no memory on this machine").
The intent is ``records/plans/fleet-identity.md``, "live and dev".

Owner's rulings: dev runs anything and fails loud on a deviation; live warns,
records and keeps serving, and the shape is flagged for re-validation. Every
observation is filed under the journal, keyed by the rig shape and the unit it
was expected of, so a figure can never again be quoted without the conditions
it was measured under.
"""

from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from tests.red_port.conftest import required

RSH = "rsh-" + "2" * 64
UNIT = "unt-" + "7" * 64
DEVIATION: dict[str, Any] = {
    "unit_id": UNIT,
    "field": "swap_out_pages",
    "expected": 0,
    "observed": 565534,
}


def _observe() -> Any:
    return required(
        "act on a deviation by profile, and file observations under the journal",
        lambda: importlib.import_module("mcgyvr.fleet.observe"),
    )


def test_a_dev_run_with_a_deviation_fails(tmp_path: Path) -> None:
    observe = _observe()
    with pytest.raises(observe.DeviationError, match="swap_out_pages"):
        observe.act([DEVIATION], profile="dev", journal_dir=tmp_path, rig_shape_id=RSH)


def test_a_live_run_with_a_deviation_warns_records_and_keeps_serving(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    observe = _observe()
    assert (
        observe.act([DEVIATION], profile="live", journal_dir=tmp_path, rig_shape_id=RSH)
        is None
    )
    err = capsys.readouterr().err
    assert "warning" in err and "swap_out_pages" in err
    lines = [
        json.loads(line)
        for path in tmp_path.rglob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(row.get("field") == "swap_out_pages" for row in lines), lines


def test_observations_append_under_the_journal_and_nothing_goes_under_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observe = _observe()
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    journal = tmp_path / "journal"
    first = observe.record(journal, RSH, UNIT, {"card_mib": 7544})
    second = observe.record(journal, RSH, UNIT, {"card_mib": 7546})
    assert first == second and Path(first).is_relative_to(journal)
    rows = [json.loads(line) for line in Path(first).read_text().splitlines()]
    assert [row["card_mib"] for row in rows] == [7544, 7546]
    assert all(row["rig_shape_id"] == RSH and row["unit_id"] == UNIT for row in rows)
    assert list(scratch.iterdir()) == []
