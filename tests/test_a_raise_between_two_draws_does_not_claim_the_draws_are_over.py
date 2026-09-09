"""A raise between two draws is told as what it was, not as a raise after them.

``None`` for "which dispatch raised" carried three different facts at once:
the attempt died before its first dispatch, or between a dispatch and the row
of the *next* one, or after every draw was made. ``_report_climb`` rendered all
three with one sentence — "the attempt raised after its draws" — and for the
middle case that sentence is false: draw 1 of two was still to come, and a
reader of draw 0's row is told the breadth ran to completion when it did not.

The two facts a reader needs are both already on the entry once ``rows`` is a
field of its own: *no dispatch is the culprit* (``draw`` is null) and *this
many draws left a row* (``rows``). Together they say which draw the attempt
had last finished when it died, so the sentence can name it — and when no draw
had, there are no rows to write a sentence on at all.

The seam is ``drive._as_sent``, which runs after ``pool.bind`` and before
``observe``: the exact window in which a dispatch has been decided on and has
left no row. A ``pool.bind`` that raises on draw 1 lands in the same window.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.telemetry import ATTEMPT_KIND, CORRECTION_KIND, fold
from tests import livejournal as lj

TWO_DRAWS = "breadth:\n  draws: 2\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def _records(journal: Path) -> list[dict[str, Any]]:
    return [
        record for path in sorted(journal.glob("*.jsonl")) for record in fold(path=path)
    ]


def _rows(journal: Path) -> list[dict[str, Any]]:
    return sorted(
        (r for r in _records(journal) if r.get("record_kind") == ATTEMPT_KIND),
        key=lambda record: str(record["attempt_id"]),
    )


def _orphans(journal: Path) -> list[dict[str, Any]]:
    return [r for r in _records(journal) if r.get("record_kind") == CORRECTION_KIND]


def test_draw_zeros_row_is_not_told_the_breadth_ran_out(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Draw 1 never reached a row: draw 0's row says so, and says where it died."""
    import mcgyvr.drive as drive

    sent = lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)
    real_as_sent = drive._as_sent
    built = 0

    def dies_preparing_the_second_draw(prompt: Any) -> Any:
        nonlocal built
        built += 1
        if built == 2:
            raise RuntimeError("the prompt could not be read back")
        return real_as_sent(prompt)

    monkeypatch.setattr(drive, "_as_sent", dies_preparing_the_second_draw)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + TWO_DRAWS, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    assert (built, len(sent)) == (2, 1), "draw 1 was prepared and never dispatched"

    (row,) = _rows(journal)
    assert row.get("outcome") == "error"
    assert row["detail"] == (
        "the attempt raised after draw 0 answered; no verdict was reached for this draw"
    ), (
        "'after its draws' is false: draw 1 was still to come, and this row is "
        "the reader's only account of what happened"
    )
    assert _orphans(journal) == []

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert landed["draw"] is None, "no dispatch of the attempt is the culprit"
    assert (landed["draws"], landed["rows"]) == (2, 1)
