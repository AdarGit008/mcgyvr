""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from mcgyvr.config import MCORCH
from mcgyvr.mcorch.loop import Trace
from mcgyvr.result import run_stamp

#
FOLDER = "mcorch"


def writer_id(now: datetime | None = None) -> str:
    ""
    return f"{MCORCH}-{run_stamp(now)}"


def transcript_path(journal_dir: Path, writer: str) -> Path:
    ""
    return journal_dir / FOLDER / f"{writer}.jsonl"


@dataclass(frozen=True)
class Transcript:
    ""

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
