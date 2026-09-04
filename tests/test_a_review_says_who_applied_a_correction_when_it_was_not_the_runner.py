"""A review names the writer of a verdict when it is not the row's own runner.

The fold carries ``applied_by`` — who applied the correction — and
``tools/live/index.py`` keeps a column for it, so the sqlite reader can answer
"who judged this row". ``tools/live/review.py`` is the other reader of the same
fold, and it printed ``outcome`` and ``detail`` and never the byline: two tools
over one journal, disagreeing about what a row says. A reviewer reading the
prompt beside the reply is weighing a verdict, and a verdict from the
orchestrator that also ran the attempt is worth something different from one a
separate gate or review gave.

Quiet when it is the same writer, though. Under §9 the one applying a
correction need not be the one that ran the attempt — but in mcgyvr's own runs
it always is, so printing the byline unconditionally would add a column of
noise saying ``agent-a`` beside ``agent-a`` on every row of every journal the
product writes.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mcgyvr.telemetry import correct

REPO = Path(__file__).resolve().parent.parent
REVIEW = REPO / "tools" / "live" / "review.py"


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
    """Two attempts one writer ran: one judged by a review, one by itself."""
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
        outcome="rejected",
        orchestrator="review",
        detail="the diff touched a second file",
    )
    correct(
        path=a,
        attempt_id="agent-a:impl:local_qwen-7b:2",
        outcome="committed",
        orchestrator="agent-a",
        detail="committed 0badcafe on main",
    )
    return journal


def _review(journal: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REVIEW), str(journal), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )


def test_a_verdict_from_another_writer_is_printed_with_its_author(
    tmp_path: Path,
) -> None:
    """The reviewer is told the review rejected it, not left to assume the runner."""
    journal = _journal(tmp_path)

    shown = _review(journal, "--outcome", "rejected")
    assert shown.returncode == 0, shown.stdout + shown.stderr

    out = shown.stdout
    assert "PROMPT-A1" in out, out
    assert "review" in out, (
        f"the review prints a verdict and never says who gave it: {out}"
    )
    assert "applied by review" in out, out


def test_a_verdict_from_the_runner_itself_adds_no_byline(tmp_path: Path) -> None:
    """Every row of mcgyvr's own journals is self-corrected: no redundant column."""
    journal = _journal(tmp_path)

    shown = _review(journal, "--outcome", "committed")
    assert shown.returncode == 0, shown.stdout + shown.stderr

    out = shown.stdout
    assert "PROMPT-A2" in out, out
    assert "applied by" not in out, (
        f"the byline repeats the row's own orchestrator as news: {out}"
    )
