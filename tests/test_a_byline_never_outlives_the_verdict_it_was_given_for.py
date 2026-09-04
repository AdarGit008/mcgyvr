"""A folded row's outcome, detail and byline all come from one correction.

:mod:`mcgyvr.telemetry` says the three correctable fields "move together": the
detail is the winning outcome's own words and ``applied_by`` is the writer who
gave it. ``fold`` applied each of them independently, so a correction that
stated a new outcome and nothing else left the previous correction's prose and
byline standing beside it — and ``tools/live/index.py`` then wrote that byline
into an ``applied_by`` column that reads "this is who judged the row". A
reviewer weighing a verdict was being told an author who never gave it.

The split is only reachable from a correction :func:`mcgyvr.telemetry.correct`
did not write, because ``correct`` always states all three. That is not an
exotic case: ``fold``'s whole shape is chosen for journals written by other
hosts and other processes, and a foreign line is exactly what the append-only
sink promises to read.

The rule these pin: the outcome is the verdict, and the detail and the byline
are attributes of it. A correction that states an outcome replaces all three,
absent fields included; a correction that states no outcome is not a verdict
and repaints none of them.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from mcgyvr.telemetry import correct, fold

ATTEMPT = "agent-a:impl:local_qwen-7b:1"


def _attempt(sink: Path, attempt_id: str = ATTEMPT) -> None:
    """One attempt line as ``observe`` writes it — no blobs, nobody reads them here."""
    row: dict[str, Any] = {
        "record_kind": "attempt",
        "version": 1,
        "ts": time.time(),
        "attempt_id": attempt_id,
        "orchestrator": "agent-a",
        "rung": "local_qwen-7b",
        "ok": True,
        "elapsed_s": 0.1,
    }
    _line(sink, row)


def _foreign(sink: Path, **fields: Any) -> None:
    """A correction line written by somebody who is not ``correct()``.

    Another host, another version, a hand-written repair: the append-only sink
    is shared by construction, so the fields a correction carries are whatever
    its writer chose to carry, not whatever this version writes.
    """
    _line(
        sink,
        {
            "record_kind": "correction",
            "version": 1,
            "ts": time.time(),
            "attempt_id": ATTEMPT,
            **fields,
        },
    )


def _line(sink: Path, record: dict[str, Any]) -> None:
    with sink.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _folded(sink: Path) -> dict[str, Any]:
    rows = [row for row in fold(path=sink) if row.get("attempt_id") == ATTEMPT]
    assert len(rows) == 1, rows
    return rows[0]


def test_a_verdict_that_names_no_author_does_not_borrow_the_last_ones(
    tmp_path: Path,
) -> None:
    """The new outcome arrives alone, so the row says nothing about who or why."""
    sink = tmp_path / "agent-a.jsonl"
    _attempt(sink)
    correct(
        path=sink,
        attempt_id=ATTEMPT,
        outcome="accepted",
        detail="gate ok",
        orchestrator="review",
    )
    _foreign(sink, outcome="reverted", detail=None, applied_by=None)

    row = _folded(sink)
    assert row["outcome"] == "reverted", row
    assert row.get("applied_by") is None, (
        f"the row credits {row.get('applied_by')!r} with a verdict it did not "
        f"give: {row}"
    )
    assert not row.get("detail"), (
        f"the superseded correction's words stand beside a newer verdict: {row}"
    )
    # The attempt's own writer is untouched: applying is not running.
    assert row["orchestrator"] == "agent-a", row


def test_a_correction_that_states_no_outcome_repaints_no_standing_verdict(
    tmp_path: Path,
) -> None:
    """Words and a byline without a verdict are not a verdict, and stand alone."""
    sink = tmp_path / "agent-a.jsonl"
    _attempt(sink)
    correct(
        path=sink,
        attempt_id=ATTEMPT,
        outcome="accepted",
        detail="gate ok",
        orchestrator="review",
    )
    _foreign(sink, detail="looked at it again", applied_by="stranger")

    row = _folded(sink)
    assert row["outcome"] == "accepted", row
    assert row["detail"] == "gate ok", (
        f"a correction that judged nothing rewrote the verdict's words: {row}"
    )
    assert row["applied_by"] == "review", (
        f"a correction that judged nothing took the verdict's byline: {row}"
    )
