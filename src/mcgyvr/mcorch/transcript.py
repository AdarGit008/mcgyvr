"""The mcorch orchestrator's own journal: one JSON row per turn it served.

An mcorch server is a journal writer like Claude Code or Pi, so its id (minted
once at start by :func:`writer_id`) is a name a reader can follow to a file:
``<journal.dir>/mcorch/<writer>.jsonl``, appended to, one row per request. A row
names the time, the writer, the model, why the turn stopped and how long it
took, alongside every field of the turn's :class:`~mcgyvr.mcorch.loop.Trace` —
what the request was taken to be, what Jev answered, what the harness dropped
from the prompt, what the loop handed back.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from mcgyvr.config import MCORCH
from mcgyvr.mcorch.loop import Trace
from mcgyvr.result import run_stamp

#: The sub-folder of the journal directory an mcorch transcript is filed under,
#: next to the run rows, results and blobs of the run that wrote it.
FOLDER = "mcorch"


def writer_id(now: datetime | None = None) -> str:
    """This server's writer id: ``mcorch-<stamp>``, minted once when it starts.

    ``now`` lets the caller supply the clock instead of it being read here. The
    stamp is :func:`mcgyvr.result.run_stamp`'s, so ids sort by start time as
    text.
    """
    return f"{MCORCH}-{run_stamp(now)}"


def transcript_path(journal_dir: Path, writer: str) -> Path:
    """Where a writer's transcript goes: ``<journal>/mcorch/<writer>.jsonl``."""
    return journal_dir / FOLDER / f"{writer}.jsonl"


@dataclass(frozen=True)
class Transcript:
    """A writer's transcript file: who is writing it and where it lives.

    ``writer`` is the id every row names and ``path`` is the file the rows go
    to; :meth:`record` appends one row per turn.
    """

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
