"""An index over the journal folds the corrections in and never rewrites the journal.

The journal is append-only for two reasons its module states — several
orchestrators can write one sink, and a crash mid-write loses one line — and
those hold only as long as nothing else opens the file for writing. A reviewer
wants the opposite shape: one row per attempt with its final outcome already
applied and the prompt and reply beside it as text. The brief (*Live journal
(WP0)*) puts that shape in a separate artifact, ``tools/live/index.py DIR``
building ``DIR/index.sqlite`` from every ``*.jsonl`` under ``DIR`` with
``telemetry.fold`` applied and the blobs joined by hash, so the journal stays
what it is and the review reads a derived table.

What is pinned: one row per **folded** attempt, so a correction is a column and
not a second row and an orphan correction is not an attempt; the latest
correction wins, in file order, exactly as ``fold`` decides; ``prompt_text`` /
``reply_text`` are the blobs' bytes and not their names; the build is idempotent
— running it twice yields the same rows — and the ``.jsonl`` files are
byte-identical before and after, which is the read-only property spelled as an
assertion about the filesystem.
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

from mcgyvr.telemetry import correct

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
    """Two orchestrators, three attempts, one of them corrected twice, one orphan."""
    journal = tmp_path / "journal"
    journal.mkdir()
    _attempt(
        journal, "agent-a", "agent-a:impl:local_qwen-7b:1", "PROMPT-A1", "REPLY-A1"
    )
    _attempt(
        journal, "agent-a", "agent-a:impl:local_qwen-7b:2", "PROMPT-A2", "REPLY-A2"
    )
    _attempt(
        journal, "agent-b", "agent-b:impl:local_qwen-7b:1", "PROMPT-B1", "REPLY-B1"
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
    correct(
        path=a, attempt_id="agent-a:impl:nobody:9", outcome="lost", orchestrator="x"
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


def _digests(journal: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(journal.glob("*.jsonl"))
    }


def test_the_index_has_one_row_per_folded_attempt_with_the_blobs_as_text(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)

    built = _build(journal)
    assert built.returncode == 0, built.stdout + built.stderr
    assert (journal / "index.sqlite").is_file()

    rows = _rows(journal)
    assert len(rows) == 3, sorted(rows)
    a1 = rows["agent-a:impl:local_qwen-7b:1"]
    # Latest correction wins, in file order — what `fold` decides, kept.
    assert a1["outcome"] == "rejected"
    assert a1["orchestrator"] == "agent-a"
    # The blobs are joined as text, not as names.
    assert a1["prompt_text"] == "PROMPT-A1"
    assert a1["reply_text"] == "REPLY-A1"
    assert a1["prompt_sha256"] == hashlib.sha256(b"PROMPT-A1").hexdigest()
    b1 = rows["agent-b:impl:local_qwen-7b:1"]
    assert b1["orchestrator"] == "agent-b"
    assert b1["prompt_text"] == "PROMPT-B1"
    # Never corrected: no outcome, and absence is not a word.
    assert b1["outcome"] is None


def test_building_twice_yields_the_same_rows_and_leaves_the_journal_untouched(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)
    before = _digests(journal)

    first = _build(journal)
    assert first.returncode == 0, first.stdout + first.stderr
    once = _rows(journal)
    second = _build(journal)
    assert second.returncode == 0, second.stdout + second.stderr
    twice = _rows(journal)

    assert len(once) == len(twice) == 3
    assert {k: r["outcome"] for k, r in once.items()} == {
        k: r["outcome"] for k, r in twice.items()
    }
    assert _digests(journal) == before, "the index build rewrote a .jsonl"
