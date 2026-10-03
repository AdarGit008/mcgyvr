"""The mcorch transcript: one row per request, under the writer's own name.

An mcorch server is a journal writer like a Claude Code or Pi session
(:mod:`mcgyvr.session`): its id is ``mcorch-<stamp>``, minted once when the
server starts, and the ``mcgyvr run`` calls the rung has the harness make
carry that id as ``--orchestrator``. What the server itself saw — which kind
of request, what Jev answered, what it dropped from the harness's prompt, how
many internal rounds it took, how the turn ended — is one JSON line per
request under ``<journal.dir>/mcorch/<id>.jsonl``, appended and never
rewritten, so a run's rows can be followed back to the exchange that made them
(:func:`mcgyvr.session.with_mcorch_transcript`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from mcgyvr.config import MCORCH
from mcgyvr.mcorch.loop import Trace
from mcgyvr.result import run_stamp

#: The folder under the journal directory that holds mcorch transcripts.
FOLDER = "mcorch"


def writer_id(now: datetime | None = None) -> str:
    """``mcorch-<stamp>``: the writer this server is, from its start time."""
    return f"{MCORCH}-{run_stamp(now)}"


def transcript_path(journal_dir: Path, writer: str) -> Path:
    """Where ``writer``'s transcript is under ``journal_dir``."""
    return journal_dir / FOLDER / f"{writer}.jsonl"


@dataclass(frozen=True)
class Transcript:
    """An append-only JSONL file, one row per request the server answered."""

    writer: str
    path: Path

    @classmethod
    def open(cls, journal_dir: Path, writer: str) -> Transcript:
        return cls(writer=writer, path=transcript_path(journal_dir, writer))

    def record(
        self, trace: Trace, *, model: str, stop_reason: str, elapsed_s: float
    ) -> None:
        row = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "orchestrator": self.writer,
            "model": model,
            "stop_reason": stop_reason,
            "elapsed_s": elapsed_s,
            **asdict(trace),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
