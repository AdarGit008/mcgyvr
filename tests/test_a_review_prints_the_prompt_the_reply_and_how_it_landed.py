"""A review prints the prompt, the reply and how it landed — and nothing else.

The whole reason the live journal keeps text (brief, *Live journal (WP0)*) is
that someone can read what the product dispatched and judge it: a number says a
rung answered, and only the prompt beside the reply says whether the answer was
any good. ``tools/live/review.py DIR [--outcome X] [--orchestrator ID]`` is that
reader: one prompt/reply/outcome triple per matching attempt, out of the journal
directory alone — the ``*.jsonl`` files and ``blobs/``, with no index built
first.

The filter is the pin as much as the printing. A reviewer asking for the
rejected attempts who is handed the accepted ones too has to re-do the filter
by eye over prompts that run to pages, and a review nobody can narrow is a
review nobody runs.
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
    """Three attempts: one rejected, one accepted, one never corrected."""
    journal = tmp_path / "journal"
    journal.mkdir()
    _attempt(
        journal,
        "agent-a",
        "agent-a:impl:local_qwen-7b:1",
        "PROMPT-REJECTED-9f1c",
        "REPLY-REJECTED-9f1c",
    )
    _attempt(
        journal,
        "agent-a",
        "agent-a:impl:local_qwen-7b:2",
        "PROMPT-ACCEPTED-2b7e",
        "REPLY-ACCEPTED-2b7e",
    )
    _attempt(
        journal,
        "agent-b",
        "agent-b:impl:local_qwen-7b:1",
        "PROMPT-OPEN-c4d0",
        "REPLY-OPEN-c4d0",
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
    )
    correct(
        path=a,
        attempt_id="agent-a:impl:local_qwen-7b:2",
        outcome="accepted",
        orchestrator="review",
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


def test_outcome_filters_to_the_matching_attempts_and_prints_their_triples(
    tmp_path: Path,
) -> None:
    journal = _journal(tmp_path)

    shown = _review(journal, "--outcome", "rejected")
    assert shown.returncode == 0, shown.stdout + shown.stderr

    out = shown.stdout
    assert "PROMPT-REJECTED-9f1c" in out
    assert "REPLY-REJECTED-9f1c" in out
    assert "rejected" in out
    # Nothing for the attempts that did not match — neither the accepted one
    # nor the one nobody has corrected yet.
    assert "PROMPT-ACCEPTED-2b7e" not in out
    assert "REPLY-ACCEPTED-2b7e" not in out
    assert "PROMPT-OPEN-c4d0" not in out


def test_orchestrator_filters_to_that_writers_attempts(tmp_path: Path) -> None:
    journal = _journal(tmp_path)

    shown = _review(journal, "--orchestrator", "agent-b")
    assert shown.returncode == 0, shown.stdout + shown.stderr

    out = shown.stdout
    assert "PROMPT-OPEN-c4d0" in out
    assert "REPLY-OPEN-c4d0" in out
    assert "PROMPT-REJECTED-9f1c" not in out
    assert "PROMPT-ACCEPTED-2b7e" not in out
