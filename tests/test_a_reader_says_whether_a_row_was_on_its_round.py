"""A reader says whether a row was on its round — and says nothing when it cannot.

A live attempt row carries ``round`` and ``product_sha256`` when the process
ran inside this checkout (:mod:`mcgyvr.telemetry`, *a row names what answered
it, and under which round*): the open round's id and the digest of the tree
that dispatched, whether or not that tree was the round's pinned tree. Off-round
is NOT refused for live work — the brief (*Live journal (WP0)*) has the reader
flag it instead — and until now neither reader did: a row said which round it
was written under, and nothing said whether the tree was that round's tree.

What is pinned. ``tools/live/index.py DIR`` gives ``attempts`` an ``off_round``
column: ``0`` when the row's ``product_sha256`` is the digest
``tools/bench/rounds.json`` pins for the row's ``round``, ``1`` when it differs,
``NULL`` when the row has no round to compare against or names one the file has
never opened. Absent-is-honest: a digest nobody can check is never coerced to a
verdict. ``tools/live/review.py DIR`` prints the same answer as a word in each
attempt's header line — ``on-round``, ``off-round`` or ``round-unknown`` — so
the reviewer reading a reply knows which product produced it.
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

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "tools" / "live" / "index.py"
REVIEW = REPO / "tools" / "live" / "review.py"
ROUNDS = REPO / "tools" / "bench" / "rounds.json"

ROUND = "r1-commissioning"
ON = "agent-a:impl:local_qwen-7b:1"
OFF = "agent-a:impl:local_qwen-7b:2"
NO_ROUND = "agent-a:impl:local_qwen-7b:3"
UNOPENED = "agent-a:impl:local_qwen-7b:4"


def _pinned(round_id: str) -> str:
    """What ``rounds.json`` pins for ``round_id`` — the file's word, not the tree's."""
    doc = json.loads(ROUNDS.read_text(encoding="utf-8"))
    for entry in doc["rounds"]:
        if entry["id"] == round_id:
            return str(entry["product_sha256"])
    raise AssertionError(f"{ROUNDS} has no round {round_id!r}")


def _blob(journal: Path, text: str) -> str:
    data = text.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    blobs = journal / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    (blobs / digest).write_bytes(data)
    return digest


def _attempt(
    journal: Path, attempt_id: str, prompt: str, reply: str, **revision: str
) -> None:
    """One attempt line as ``observe`` writes it, with whatever round keys it knew."""
    row: dict[str, Any] = {
        "record_kind": "attempt",
        "version": 1,
        "ts": time.time(),
        "attempt_id": attempt_id,
        "orchestrator": "agent-a",
        "rung": "local_qwen-7b",
        "ok": True,
        "elapsed_s": 0.1,
        "model": "qwen2.5-coder:7b",
        "endpoint": "http://localhost:11434",
        "protocol": "ollama",
        "condition": "stock",
        "prompt_sha256": _blob(journal, prompt),
        "reply_sha256": _blob(journal, reply),
        **revision,
    }
    with (journal / "agent-a.jsonl").open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(row) + "\n")


def _journal(tmp_path: Path) -> Path:
    """Four attempts: on the pin, off it, no round at all, and a round never opened."""
    pinned = _pinned(ROUND)
    elsewhere = hashlib.sha256(b"a tree that is not the pinned one").hexdigest()
    assert elsewhere != pinned
    journal = tmp_path / "journal"
    journal.mkdir()
    _attempt(journal, ON, "PROMPT-ON", "REPLY-ON", round=ROUND, product_sha256=pinned)
    _attempt(
        journal, OFF, "PROMPT-OFF", "REPLY-OFF", round=ROUND, product_sha256=elsewhere
    )
    _attempt(journal, NO_ROUND, "PROMPT-NONE", "REPLY-NONE")
    _attempt(
        journal,
        UNOPENED,
        "PROMPT-UNOPENED",
        "REPLY-UNOPENED",
        round="r0-never-opened",
        product_sha256=pinned,
    )
    return journal


def _run(tool: Path, journal: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tool), str(journal)],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )


def _rows(journal: Path) -> dict[str, dict[str, Any]]:
    with sqlite3.connect(journal / "index.sqlite") as db:
        db.row_factory = sqlite3.Row
        found = db.execute("SELECT * FROM attempts").fetchall()
    return {row["attempt_id"]: dict(row) for row in found}


def _headers(out: str) -> dict[str, list[str]]:
    """Each attempt's header line, as the words on it, keyed by attempt id."""
    return {
        line.split()[1]: line.split()
        for line in out.splitlines()
        if line.startswith("=== ")
    }


def test_the_index_flags_off_round_as_0_1_or_null_against_the_rounds_file(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)

    built = _run(INDEX, journal)
    assert built.returncode == 0, built.stdout + built.stderr

    rows = _rows(journal)
    assert len(rows) == 4, sorted(rows)
    assert "off_round" in rows[ON], sorted(rows[ON])
    assert rows[ON]["off_round"] == 0
    assert rows[OFF]["off_round"] == 1
    # Nothing to compare against: NULL, never 0 — a digest nobody can check
    # is not a digest that checked out.
    assert rows[NO_ROUND]["off_round"] is None
    assert rows[UNOPENED]["off_round"] is None
    # The reader's verdict sits beside the row's own facts, which are kept as
    # written: the digest is the tree's, not the pin's.
    assert rows[OFF]["round"] == ROUND
    assert rows[OFF]["product_sha256"] != _pinned(ROUND)
    assert rows[NO_ROUND]["round"] is None
    assert rows[NO_ROUND]["product_sha256"] is None


def test_a_review_says_on_round_off_round_or_round_unknown_in_the_header(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)

    shown = _run(REVIEW, journal)
    assert shown.returncode == 0, shown.stdout + shown.stderr

    headers = _headers(shown.stdout)
    assert set(headers) == {ON, OFF, NO_ROUND, UNOPENED}, shown.stdout
    assert "on-round" in headers[ON], headers[ON]
    assert "off-round" in headers[OFF], headers[OFF]
    assert "round-unknown" in headers[NO_ROUND], headers[NO_ROUND]
    assert "round-unknown" in headers[UNOPENED], headers[UNOPENED]
    # One word per header, and only the right one.
    words = {"on-round", "off-round", "round-unknown"}
    for attempt_id, header in headers.items():
        assert len(words & set(header)) == 1, (attempt_id, header)
    # The triples are still printed around the verdict.
    assert "PROMPT-OFF" in shown.stdout
    assert "REPLY-OFF" in shown.stdout
