"""Journal rows are written under layout version 2; version 1 still reads.

Version 2 names the writer of a row ``session`` (the chat the run was typed
from) and the catalog family it ran in ``family``. Version 1 called them
``orchestrator`` and ``tier``. For one release a version-1 row is read under
version 2's names, so a journal written before the rename still folds and
``mcgyvr usage`` still counts it. A file whose rows this mcgyvr cannot read is
named on stderr and left out, the rest of the directory is still counted, and
the command exits 1 so a script sees the gap.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.cli import main
from mcgyvr.telemetry import READ_VERSIONS, TELEMETRY_VERSION, correct, fold, observe

RUN = "20261110T120000.000001Z"


def test_a_row_is_written_under_version_2_with_session_and_family(
    tmp_path: Path,
) -> None:
    sink = tmp_path / "sess-a.jsonl"
    observe(
        lambda: "ran",
        path=sink,
        attempt_id="a1",
        session="sess-a",
        rung="ruff",
        family="deterministic",
    )
    correct(path=sink, attempt_id="a1", outcome="passed", session="review")

    rows = [json.loads(line) for line in sink.read_text().splitlines()]
    assert TELEMETRY_VERSION == 2
    assert [row["version"] for row in rows] == [2, 2]
    attempt, correction = rows
    assert attempt["session"] == "sess-a"
    assert attempt["family"] == "deterministic"
    assert "orchestrator" not in attempt and "tier" not in attempt
    assert correction["applied_by"] == "review"


def _v1_row(session: str, n: int) -> str:
    return json.dumps(
        {
            "record_kind": "attempt",
            "version": 1,
            "ts": 1.0,
            "attempt_id": f"{session}:{RUN}:c1:ruff:{n}",
            "orchestrator": session,
            "rung": "ruff",
            "tier": "deterministic",
            "ok": True,
            "elapsed_s": 0.5,
        }
    )


def test_a_version_1_row_is_read_under_version_2_names(tmp_path: Path) -> None:
    sink = tmp_path / "old.jsonl"
    sink.write_text(_v1_row("old", 1) + "\n", encoding="utf-8")

    (row,) = fold(path=sink)

    assert READ_VERSIONS == (1, 2)
    assert row["session"] == "old"
    assert row["family"] == "deterministic"
    assert "orchestrator" not in row and "tier" not in row
    assert row["version"] == 1


def test_usage_counts_a_journal_written_before_the_rename(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    (journal / "old.jsonl").write_text(_v1_row("old", 1) + "\n", encoding="utf-8")
    observe(
        lambda: "ran",
        path=journal / "new.jsonl",
        attempt_id=f"new:{RUN}:c1:ruff:1",
        session="new",
        rung="ruff",
    )

    assert main(["usage", str(journal)]) == 0
    out = capsys.readouterr().out

    assert out.splitlines()[0].endswith("2 attempt row(s) in 2 file(s)"), out
    sessions = {
        line.split()[1] for line in out.splitlines() if line.split()[:1] == [RUN]
    }
    assert sessions == {"old", "new"}, out


def test_a_file_it_cannot_read_is_named_and_the_rest_still_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    later = journal / "later.jsonl"
    later.write_text(
        json.dumps({"record_kind": "attempt", "version": 99, "attempt_id": "x"}) + "\n",
        encoding="utf-8",
    )
    (journal / "old.jsonl").write_text(_v1_row("old", 1) + "\n", encoding="utf-8")

    assert main(["usage", str(journal)]) == 1
    captured = capsys.readouterr()

    assert captured.out.splitlines()[0].endswith("1 attempt row(s) in 1 file(s)")
    assert f"left out: {later}:1:" in captured.err, captured.err
    assert "layout version 99" in captured.err, captured.err
