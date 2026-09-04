"""What one run came to, as a file the caller reads instead of the scrollback.

The agent that types ``mcgyvr run`` decides what to do next from what the run
came to: accept the change, commit it, or write a different contract. It used
to learn that from prose on stdout and stderr and an exit code, and the one
thing it most needs — *why* the gate refused — from nowhere, because the
finding lines went into the model's retry prompt and never to the caller.

This module is the run's answer as data. One JSON file per run, under the
journal's ``results/``, named by the contract and a UTC stamp so two runs of
one contract are two files; ``mcgyvr run`` prints ``result: <path>`` and no
more. A file rather than a dump on stdout by the owner's ruling (2026-09-03):
an agent's context is the scarce thing, and a file costs nothing until it is
opened. Nothing here lands in the repository a run works on.

The fields are the questions a replanner asks. ``outcome`` is ``accepted`` or
the word :class:`~mcgyvr.escalate.Outcome` gives a halt (``ladder_spent``,
``escalation_ceiling``, ...) or ``rejected`` for the deterministic gate or
``error``; ``attempts`` is every rung touched with its verdict and the gate's
finding lines; ``committed``/``commit``/``branch`` say where the work went;
``orchestrator``/``session_file``/``journal``/``attempt_id`` say where the
rows are, so the same agent can find its own prompt and reply.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = "results"


@dataclass
class AttemptResult:
    """One rung's try, as the climb recorded it."""

    rung: str
    attempt: int
    verdict: str
    detail: str = ""
    findings: list[str] = field(default_factory=list)
    attempt_id: str | None = None
    #: ``null`` on an attempt that raised where no dispatch of it is the
    #: culprit — before the first draw, or after the last. ``attempt_id`` is
    #: ``null`` with it: there is no row to name.
    draw: int | None = 0
    draws: int = 1


@dataclass
class RunResult:
    """Everything a caller needs to decide what to do after one run."""

    contract: str
    task_type: str
    target: str
    orchestrator: str
    #: The stamp that names this run: the result file's, and the one every
    #: journal row of the run carries in its ``attempt_id``.
    run: str = ""
    session_file: str | None = None
    journal: str | None = None
    outcome: str = "error"
    detail: str = ""
    rung: str | None = None
    assurance: str | None = None
    attempts: list[AttemptResult] = field(default_factory=list)
    #: The deterministic gate's findings, for a contract that dispatched
    #: nothing; a climb's findings live on its attempts.
    findings: list[str] = field(default_factory=list)
    committed: bool = False
    commit: str = ""
    branch: str = ""
    handoff: str = ""
    exit_code: int | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def run_stamp(now: datetime | None = None) -> str:
    """The UTC stamp that names one run, to the microsecond."""
    return (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S.%fZ")


def result_path(journal_dir: Path, contract_id: str, stamp: str) -> Path:
    """``<journal>/results/<contract>-<stamp>.json``, one per run."""
    return journal_dir / RESULTS_DIR / f"{contract_id}-{stamp}.json"


def write(path: Path, result: RunResult) -> Path:
    """Write ``result`` whole: a reader never sees half a file."""
    result.finished = time.time()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.part")
    try:
        staging.write_text(
            json.dumps(result.as_json(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, path)
    except OSError:
        # The same tidy-up `telemetry._store` makes: a write that failed
        # partway leaves no `.part` for the next reader to wonder about.
        staging.unlink(missing_ok=True)
        raise
    return path
