"""What a run came to, as data, and the record a session leaves behind.

``RunResult`` is one ``mcgyvr run`` written out: the outcome and the sentence
behind it, every attempt that was spent, the commit as fields, a chat or agent
reply, and the paths to the run's own result file, journal and session record.
``SessionRecord`` is the narrower answer a session contract keeps, so its
question and reply outlive the result file.

Both land under the journal — ``results/`` and ``sessions/`` — through
:func:`write` and :func:`write_session`, which go through
:mod:`mcgyvr.atomic`, so a reader sees the previous file or the new one and
never a half-written one.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcgyvr import atomic

RESULTS_DIR = "results"
SESSIONS_DIR = "sessions"


@dataclass
class AttemptResult:
    """One try at one rung, as the result file reports it."""

    #: The rung this try ran on and its number there, the verdict it came to
    #: (`passed`, `failed`, `declined`, `error`) with `detail` and `findings`
    #: behind it, and `attempt_id`, the journal row it was recorded as.
    rung: str
    attempt: int
    verdict: str
    detail: str = ""
    findings: list[str] = field(default_factory=list)
    attempt_id: str | None = None
    #: An attempt can spend several draws: independent dispatches of the same
    #: try, so breadth buys more than one answer to choose between. `draw` is
    #: the one this entry is about, and `None` when no single dispatch caused
    #: the error it reports — `rows` of `0` means it raised before dispatching
    #: at all, and any more means it raised past draw `rows - 1`.
    draw: int | None = 0
    #: `draws` is the breadth the attempt asked for — `breadth.draws`, or this
    #: rung's entry under `draws` — whatever the verdict turned out to be.
    draws: int = 1
    #: `rows` is how many of those draws left a journal row: `draws` unless the
    #: attempt raised part-way, and `0` for a try that declined before dispatch.
    rows: int = 1
    #: `relief` is `True` for a rung lent through a hub — recorded like any
    #: try, but charged against the budget only when it passes — and `model`
    #: and `address` name the unit that served it.
    relief: bool = False
    model: str = ""
    address: str = ""


@dataclass
class RunResult:
    """A run's answer as data: the shape the result file is written in."""

    contract: str
    task_type: str
    target: str
    orchestrator: str
    #: `run` is this run's stamp, the id its journal rows and result file share;
    #: `journal` is the directory it was recorded under.
    run: str = ""
    session_file: str | None = None
    journal: str | None = None
    outcome: str = "error"
    #: `outcome` is one word for what the run came to — `accepted`, `rejected`,
    #: `nothing_to_change`, `delivery_refused`, one of the ceilings that stopped
    #: the climb (`ladder_spent`, `escalation_ceiling`, `attempt_ceiling`,
    #: `nothing_to_run`, `declined_throughout`), or `error` when nothing was
    #: judged at all — and `detail` says it in a sentence.
    detail: str = ""
    #: `delivery` is where the work went: the commit, the fact that the change
    #: was left in the tree uncommitted, or why the write to it was refused —
    #: the same sentence `detail` carries for a refused delivery. Empty on a run
    #: that never reached delivery, which is every rejected one: those stop at
    #: the gate, with the change still in the sandbox and nothing written.
    delivery: str = ""
    #: `rung` is the rung the accepted change came from, `assurance` what
    #: accepting it rests on, and `attempts` every try in the order they were made.
    rung: str | None = None
    assurance: str | None = None
    attempts: list[AttemptResult] = field(default_factory=list)
    #: `findings` is why a change was refused, one line per reason; `committed`,
    #: `commit`, `branch` and `handoff` are the commit as fields.
    findings: list[str] = field(default_factory=list)
    committed: bool = False
    commit: str = ""
    branch: str = ""
    handoff: str = ""
    #: `answer` is a `chat` or `agent` reply — the prose the run
    #: produced and never wrote to the tree; empty for one that changed files.
    answer: str = ""
    #: `session_record` is where a session's record landed under `sessions/`, so
    #: the question and answer can be read back without the result file;
    #: `exit_code` is what the process returned for this run.
    session_record: str | None = None
    exit_code: int | None = None
    #: `copy_errors` is a `--record DIR` copy that could not be written, keyed by
    #: the mirror directory it was meant for and holding the reason it was not.
    #: A copy is not a sink: mcgyvr's own record under `journal` is complete
    #: whatever this says, and a copy going missing must not turn a run that
    #: reached an answer into an error — so the failure is said on stderr, the
    #: run goes on, and the result file names it here. Empty on almost every
    #: run, which is what makes a non-empty one worth reading.
    copy_errors: dict[str, str] = field(default_factory=dict)
    #: `notes` is what the run said in passing and the result would otherwise
    #: lose: the uncommitted and untracked paths the sandbox of HEAD left out,
    #: what a tool printed as it worked, and what an acceptance baseline left
    #: behind before cleanup took it away. `started` and `finished` are epoch
    #: stamps — `started` when the run began, `finished` when this file was
    #: written — kept as numbers so a caller can measure a run without parsing
    #: the ISO times beside them in a session record.
    notes: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    finished: float | None = None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionContract:
    """The contract a session was asked under, kept with the question.

    ``path`` and ``sha256`` are what the bytes were when the session ran, and
    ``text`` is those bytes decoded as UTF-8 with undecodable ones replaced —
    so a record still says what was asked after the contract file is edited or
    gone.
    """

    id: str
    path: str
    sha256: str
    text: str


@dataclass
class SessionRecord:
    """A session as it is filed under ``sessions/``, for ``mcgyvr sessions``.

    A ``chat`` or ``agent`` contract writes nothing to the tree, so this record
    is all that is left of it: the question, the answer, which unit answered,
    the times at both ends, and where the run's own result and journal are.
    """

    #: `session` is `<contract id>-<run stamp>`, the name it is filed under.
    session: str
    task_type: str
    contract: SessionContract
    #: `question` is the contract's task verbatim, kept with the contract's bytes
    #: above so the record still reads as a question after the file changes.
    question: str
    #: `answer` is the reply a session contract produced; where there is none it
    #: is empty and `detail` says why.
    answer: str
    #: `unit` is the rung that answered; the outcome, assurance and detail are its.
    unit: str | None
    outcome: str
    assurance: str | None
    detail: str
    attempt_id: str | None
    #: `orchestrator` is who typed the session, and `session_file` its transcript.
    orchestrator: str
    session_file: str | None
    #: `result` and `journal` are the run's result file and its journal, as paths.
    result: str
    journal: str
    #: `started` and `finished` are ISO 8601 UTC stamps ending in `Z`.
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
    """Build the record a finished run leaves under ``sessions/``.

    The contract is read back from ``contract_path`` rather than taken from the
    run, so the record carries the bytes the run was judged against and a
    sha256 a later reader can check them with. ``unit`` is the rung the answer
    came from and ``attempt_id`` the last attempt's — the one that landed. The
    clock starts at the run's own ``started`` and ends here, at the write.
    """
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
    """Where a session's record goes: ``<journal>/sessions/<id>-<stamp>.json``."""
    return journal_dir / SESSIONS_DIR / f"{contract_id}-{stamp}.json"


def write_session(path: Path, record: SessionRecord) -> Path:
    """Write a session record as JSON and return the path it went to."""
    return _write_json(path, record.as_json())


def sessions(journal_dir: Path) -> list[Path]:
    """Every session record in the journal, newest first.

    Ordered by the run stamp each file name ends in, not by mtime, so the order
    is the order the runs were made in. A journal with no ``sessions/`` yet
    lists nothing.
    """
    found = (journal_dir / SESSIONS_DIR).glob("*.json")
    return sorted(found, key=lambda p: p.stem.rsplit("-", 1)[-1], reverse=True)


def run_stamp(now: datetime | None = None) -> str:
    """This run's stamp: UTC as ``YYYYMMDDTHHMMSS.ffffffZ``, sortable as text.

    ``now`` lets the caller supply the clock instead of it being read here.
    """
    return (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S.%fZ")


def result_path(journal_dir: Path, contract_id: str, stamp: str) -> Path:
    """Where a run's result file goes: ``<journal>/results/<id>-<stamp>.json``."""
    return journal_dir / RESULTS_DIR / f"{contract_id}-{stamp}.json"


def write(path: Path, result: RunResult) -> Path:
    """Write a result as JSON and return the path it went to.

    ``finished`` is stamped here, at the moment of writing, rather than by the
    caller, so the closing time is the time the file was written.
    """
    result.finished = time.time()
    return _write_json(path, result.as_json())


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    """Write ``data`` as JSON at ``path`` and return the path.

    The parent directory is made first — a run's ``results/`` need not exist
    yet — and the bytes are indented, key-sorted and newline-terminated, then
    written through :func:`mcgyvr.atomic.write` so the file is replaced whole.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(path, json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path
