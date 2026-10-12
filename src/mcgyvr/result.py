"""What one run came to, as a file the caller reads instead of the scrollback.

The agent that types ``mcgyvr run`` decides what to do next from what the run
came to: accept the change, commit it, or write a different contract.

This module is the run's answer as data. One JSON file per run, under the
journal's ``results/``, named by the contract and a UTC stamp so two runs of
one contract are two files; ``mcgyvr run`` prints ``result: <path>`` and no
more. A file rather than a dump on stdout: an agent's context is the scarce
thing, and a file costs nothing until it is opened. Nothing here lands in the
repository a run works on.

The fields are the questions a replanner asks. ``outcome`` is ``accepted``, the
word :class:`~mcgyvr.escalate.Outcome` gives a halt (``ladder_spent``,
``escalation_ceiling``, ...), or one of the CLI's own: ``rejected``,
``nothing_to_change``, ``delivery_refused``, ``error``; ``attempts`` is every
rung touched with its verdict and the gate's finding lines;
``committed``/``commit``/``branch`` say where the work went;
``orchestrator``/``session_file``/``journal``/``attempt_id`` say where the
rows are, so the same agent can find its own prompt and reply.

**A ``chat`` or ``agent`` run is a session, and is logged as one** (owner
decision, e2e run 1 F7: "answers are not throwaway nowhere"). Its reply is
never written to the tree, so besides ``answer`` in the result file it gets a
:class:`SessionRecord` of its own under the journal's ``sessions/``, beside
``results/`` and named the same way: what was asked, under which contract, what
answered, when, how it was judged and how it came out. The result file's
``session_record`` names it, and ``mcgyvr sessions`` lists and shows them.
"Session" here is that exchange; the conversation that typed the command is
the *orchestrator's* session (:mod:`mcgyvr.session`, ``session_file``).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = "results"
SESSIONS_DIR = "sessions"


@dataclass
class AttemptResult:
    """One rung's try, as the climb recorded it."""

    #: Which rung answered. The name stays ``rung`` and is not renamed: the
    #: journal rows and tests say ``rung``, and a second word for one concept is
    #: new vocabulary.
    rung: str
    attempt: int
    verdict: str
    detail: str = ""
    findings: list[str] = field(default_factory=list)
    attempt_id: str | None = None
    #: Which draw the entry is about. ``null`` on an attempt that raised where
    #: no dispatch of it is the culprit; ``attempt_id`` is ``null`` with it,
    #: because there is no row to name. ``rows`` says which such raise it was:
    #: ``0`` is a raise before any dispatch, and anything more is a raise past
    #: draw ``rows - 1``, the last one that answered.
    draw: int | None = 0
    #: The breadth the run asked for (``breadth.draws``), on every attempt and
    #: whatever the verdict.
    draws: int = 1
    #: How many of those draws left a journal row — how far the attempt got.
    #: Below ``draws`` only where the attempt did not finish its draws.
    rows: int = 1


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
    #: The rung the run came to rest on, not renamed for the reason
    #: :attr:`AttemptResult.rung` gives.
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
    #: The raw-text reply (prose / media_artifact), for a run whose answer is
    #: text rather than a committed file. Empty for a whole_file run.
    answer: str = ""
    #: The session record of a ``chat`` or ``agent`` run
    #: (``<journal>/sessions/<contract>-<stamp>.json``); ``None`` for every
    #: other run, and for a session whose record could not be written.
    session_record: str | None = None
    exit_code: int | None = None
    #: A copy of the journal the caller asked for (``--record DIR``) that could
    #: not be written, and why — keyed by the directory. Empty on almost every
    #: run. It is here and not only on stderr because the skill tells a caller
    #: to read this file rather than the scrollback, and "your copy is short"
    #: is exactly the kind of fact a caller reading the file would otherwise
    #: never learn. mcgyvr's own record under ``journal`` is complete whatever
    #: this says: a copy is not a sink, and its failure does not stop a run.
    copy_errors: dict[str, str] = field(default_factory=dict)
    #: What the caller should know about how the run was set up, one line
    #: each, empty on a run with nothing to say. Today: the uncommitted and
    #: untracked paths a sandbox built from HEAD does not hold
    #: (:func:`mcgyvr.orchestrator.repo.head_only_note`), and what the
    #: preflight's baseline commands left behind and had cleaned up
    #: (:meth:`mcgyvr.gate.acceptance.Acceptance.baseline`). Here and not only
    #: on stderr for the reason ``copy_errors`` gives.
    notes: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    finished: float | None = None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionContract:
    """The contract a session ran, kept whole: contract files are often scratch."""

    id: str
    path: str
    sha256: str
    text: str


@dataclass
class SessionRecord:
    """One ``chat`` or ``agent`` exchange: the question, the answer, and how."""

    #: ``<contract>-<stamp>``, the record's file name and the result file's.
    session: str
    task_type: str
    contract: SessionContract
    #: The contract's ``task``: what was asked. The whole prompt the unit was
    #: sent is in the journal row ``attempt_id`` names (``prompt_sha256``).
    question: str
    #: The reply, as the result file's ``answer`` carries it; empty when the
    #: run was not accepted.
    answer: str
    #: The unit that answered (the rung the run came to rest on).
    unit: str | None
    outcome: str
    assurance: str | None
    detail: str
    attempt_id: str | None
    #: Who typed the command, and that conversation's transcript.
    orchestrator: str
    session_file: str | None
    #: mcgyvr's own copy of the run's result file, and the journal rows.
    result: str
    journal: str
    #: UTC, ISO 8601: a log is read by people as well as programs.
    started: str
    finished: str

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def session_record(
    report: RunResult,
    *,
    contract_path: Path,
    question: str,
    result: Path,
    journal: Path,
) -> SessionRecord:
    """The session record of a finished run, from its result and its contract file."""
    data = contract_path.read_bytes()
    landed = report.attempts[-1] if report.attempts else None
    return SessionRecord(
        session=f"{report.contract}-{report.run}",
        task_type=report.task_type,
        contract=SessionContract(
            id=report.contract,
            path=str(contract_path),
            sha256=hashlib.sha256(data).hexdigest(),
            text=data.decode("utf-8", "replace"),
        ),
        question=question,
        answer=report.answer,
        unit=report.rung,
        outcome=report.outcome,
        assurance=report.assurance,
        detail=report.detail,
        attempt_id=landed.attempt_id if landed is not None else None,
        orchestrator=report.orchestrator,
        session_file=report.session_file,
        result=str(result),
        journal=str(journal),
        started=_iso(report.started),
        finished=_iso(time.time()),
    )


def _iso(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, UTC).isoformat().replace("+00:00", "Z")


def session_path(journal_dir: Path, contract_id: str, stamp: str) -> Path:
    """``<journal>/sessions/<contract>-<stamp>.json``, one per session."""
    return journal_dir / SESSIONS_DIR / f"{contract_id}-{stamp}.json"


def write_session(path: Path, record: SessionRecord) -> Path:
    """Write ``record`` whole, as :func:`write` writes a result."""
    return _write_json(path, record.as_json())


def sessions(journal_dir: Path) -> list[Path]:
    """Every session record under ``journal_dir``, newest first.

    By name, which ends in the run's UTC stamp: the stamp is fixed-width, so
    within one contract the order is the order the runs started; across
    contracts the stamp is compared, not the contract id.
    """
    found = (journal_dir / SESSIONS_DIR).glob("*.json")
    return sorted(found, key=lambda p: p.stem.rsplit("-", 1)[-1], reverse=True)


def run_stamp(now: datetime | None = None) -> str:
    """The UTC stamp that names one run, to the microsecond."""
    return (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S.%fZ")


def result_path(journal_dir: Path, contract_id: str, stamp: str) -> Path:
    """``<journal>/results/<contract>-<stamp>.json``, one per run."""
    return journal_dir / RESULTS_DIR / f"{contract_id}-{stamp}.json"


def write(path: Path, result: RunResult) -> Path:
    """Write ``result`` whole: a reader never sees half a file."""
    result.finished = time.time()
    return _write_json(path, result.as_json())


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    """``data`` as JSON at ``path``, through a staging name: whole or not at all."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.part")
    try:
        staging.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, path)
    except OSError:
        # The same tidy-up `telemetry._store_one` makes: a write that failed
        # partway leaves no `.part` for the next reader to wonder about.
        staging.unlink(missing_ok=True)
        raise
    return path
