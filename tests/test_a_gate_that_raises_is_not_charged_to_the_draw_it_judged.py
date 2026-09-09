"""A gate that raises is not the fault of the dispatch it was judging.

The second repair of finding 7 had the driver state its own raise, and cleared
"the dispatch in flight" at two moments: on entry to ``sample`` and after
``best_of`` returned. Between those two moments sits the whole of
:func:`~mcgyvr.consensus._draw`'s per-draw work — writing the bytes, calling
the gate, binding the winner, restoring the workspace — and every line of it
ran with the draw that had *already answered* still named as in flight.

So a gate that raised on draw 0 of two was charged to draw 0: the row of a
dispatch that answered normally was corrected to ``outcome: error`` as though
the endpoint had died, and the result named it as the attempt. The dispatch is
in flight for exactly as long as the dispatch is: from the moment ``observe``
is entered to the moment it returns, and not one line further.

What is true here is that draw 0 answered, its row exists and is accounted for,
and the raise belongs to no dispatch — so the result names none.
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


def test_the_gate_dying_on_draw_zero_is_not_draw_zeros_error(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Draw 0 answered and the gate then died: the dispatch is not the culprit."""
    import mcgyvr.drive as drive

    sent = lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)

    def gate_dies(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the acceptance runner died")

    monkeypatch.setattr(drive, "gate_workspace", gate_dies)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + TWO_DRAWS, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    assert len(sent) == 1, "the gate died on draw 0, so draw 1 was never dispatched"

    (row,) = _rows(journal)
    assert row.get("ok") is True, "the dispatch answered; it is the gate that died"
    assert row.get("outcome") == "error", "the row is still accounted for"
    assert row["detail"] == (
        "the attempt raised after draw 0 answered; no verdict was reached for this draw"
    ), row
    assert _orphans(journal) == [], "draw 1 wrote no row, so nothing names one"

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert landed["verdict"] == "error"
    assert landed["draw"] is None, (
        "the dispatch answered; charging the raise to it reports a dead "
        "endpoint that nobody saw"
    )
    assert landed["attempt_id"] is None, "there is no dispatch for the result to name"
    assert (landed["draws"], landed["rows"]) == (2, 1), (
        "two draws were asked for and one of them left a row"
    )
