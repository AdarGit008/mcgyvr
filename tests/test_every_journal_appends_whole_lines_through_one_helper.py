"""Every JSON-lines journal appends through one helper, :mod:`mcgyvr.jsonl`.

The dispatch journal, the decision shadow log and the fleet read's rows used to
carry two copies of "append one line under a lock, end a torn line first", and
the fleet's two writers appended with a plain ``open("a")``: a writer that died
mid-line left a stump the next row was glued onto, and both rows were lost to
every reader. Now all four go through :func:`mcgyvr.jsonl.append_line`.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcgyvr import jsonl
from mcgyvr.fleet import alerts


def test_a_row_after_a_torn_line_is_still_its_own_line(tmp_path: Path) -> None:
    path = tmp_path / "unit.jsonl"
    path.write_text('{"field": "card_mib", "obs')

    jsonl.append_line(path, b'{"field": "restarts"}\n')

    assert jsonl.read_lines(path) == [(2, {"field": "restarts"})]


def test_the_fleet_alert_journal_ends_a_torn_line_before_its_row(
    tmp_path: Path,
) -> None:
    stamp = {"combination_id": "c1", "unit_id": "u1", "run_id": "r1"}
    first = alerts.record(tmp_path, stamp, {"field": "card_mib", "observed": 1})
    first.write_bytes(first.read_bytes() + b'{"torn": ')

    alerts.record(tmp_path, stamp, {"field": "restarts", "observed": 0})

    rows = [json.loads(line) for line in first.read_text().splitlines()[::2]]
    assert [row["field"] for row in rows] == ["card_mib", "restarts"]
    assert first.read_text().splitlines()[1] == '{"torn": '


def test_read_lines_passes_over_what_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_bytes(b'\n[1, 2]\n\xff\xfe\nnot json\n{"ok": 1}\n')

    assert jsonl.read_lines(path) == [(5, {"ok": 1})]
    assert jsonl.read_lines(tmp_path / "missing.jsonl") == []
