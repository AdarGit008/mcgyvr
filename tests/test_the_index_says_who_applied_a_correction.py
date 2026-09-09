"""A folded row says who applied the correction it is carrying.

:func:`mcgyvr.telemetry.correct` requires its ``orchestrator`` and writes it
as ``applied_by`` on every correction line, because under §9 the one applying
a correction need not be the one that ran the attempt: the gate that judged,
the review that rejected and the orchestrator that took the work off the
out-queue are three different writers, and a verdict whose author is unknown
is a verdict a reviewer cannot weigh. ``tools/live/index.py`` declares an
``applied_by`` column for exactly that question.

The column was always ``NULL``. ``fold`` carried only ``outcome`` and
``detail`` from a correction onto the attempt, and ``index.attempts`` drops
the correction records themselves — so the one place ``applied_by`` was
written was the one place nothing read it. It moves with the outcome it
belongs to: the detail is the winning outcome's words and the author is the
winning outcome's writer, and reporting one correction's prose or byline
beside another's verdict would name somebody for a judgement they did not
make.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mcgyvr.telemetry import correct, fold

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "tools" / "live" / "index.py"

TABLE = "attempts"


def _blob(journal: Path, text: str) -> str:
    data = text.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    blobs = journal / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    (blobs / digest).write_bytes(data)
    return digest


def _attempt(
    journal: Path, orchestrator: str, attempt_id: str, prompt: str, reply: str
) -> None:
    """One attempt line as ``observe`` writes it, with its two blobs in place."""
    row: dict[str, Any] = {
        "record_kind": "attempt",
        "version": 1,
        "ts": time.time(),
        "attempt_id": attempt_id,
        "orchestrator": orchestrator,
        "rung": "local_qwen-7b",
        "ok": True,
        "elapsed_s": 0.1,
        "model": "qwen2.5-coder:7b",
        "endpoint": "http://localhost:11434",
        "protocol": "ollama",
        "condition": "stock",
        "prompt_sha256": _blob(journal, prompt),
        "reply_sha256": _blob(journal, reply),
    }
    with (journal / f"{orchestrator}.jsonl").open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(row) + "\n")


def _journal(tmp_path: Path) -> Path:
    """One attempt corrected by its runner and then by a reviewer, one uncorrected."""
    journal = tmp_path / "journal"
    journal.mkdir()
    _attempt(
        journal, "agent-a", "agent-a:impl:local_qwen-7b:1", "PROMPT-A1", "REPLY-A1"
    )
    _attempt(
        journal, "agent-a", "agent-a:impl:local_qwen-7b:2", "PROMPT-A2", "REPLY-A2"
    )
    a = journal / "agent-a.jsonl"
    correct(
        path=a,
        attempt_id="agent-a:impl:local_qwen-7b:1",
        outcome="accepted",
        orchestrator="agent-a",
    )
    correct(
        path=a,
        attempt_id="agent-a:impl:local_qwen-7b:1",
        outcome="rejected",
        orchestrator="review",
        detail="the diff touched a second file",
    )
    return journal


def _build(journal: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INDEX), str(journal)],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )


def _rows(journal: Path) -> dict[str, dict[str, Any]]:
    with sqlite3.connect(journal / "index.sqlite") as db:
        db.row_factory = sqlite3.Row
        found = db.execute(f"SELECT * FROM {TABLE}").fetchall()
    return {row["attempt_id"]: dict(row) for row in found}


def test_a_folded_attempt_names_the_writer_of_the_correction_that_won(
    tmp_path: Path,
) -> None:
    """The author moves with the outcome and the detail, latest-wins in file order."""
    journal = _journal(tmp_path)

    folded = {row["attempt_id"]: row for row in fold(path=journal / "agent-a.jsonl")}
    corrected = folded["agent-a:impl:local_qwen-7b:1"]
    assert corrected["outcome"] == "rejected", corrected
    assert corrected.get("applied_by") == "review", (
        f"the folded row does not say who rejected it: {corrected}"
    )
    # The attempt's own writer is untouched: applying is not running.
    assert corrected["orchestrator"] == "agent-a", corrected
    # Never corrected: no outcome and no author, and absence is not a name.
    assert folded["agent-a:impl:local_qwen-7b:2"].get("applied_by") is None


def test_the_index_column_carries_the_author_of_the_folded_outcome(
    tmp_path: Path,
) -> None:
    """The declared ``applied_by`` column is populated, not silently ``NULL``."""
    journal = _journal(tmp_path)

    built = _build(journal)
    assert built.returncode == 0, built.stdout + built.stderr

    rows = _rows(journal)
    assert len(rows) == 2, sorted(rows)
    assert rows["agent-a:impl:local_qwen-7b:1"]["applied_by"] == "review", rows
    assert rows["agent-a:impl:local_qwen-7b:2"]["applied_by"] is None, rows
