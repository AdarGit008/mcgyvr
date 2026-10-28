"""What a run came to, as data.

``RunResult`` is one run of a contract written out: the outcome and the sentence
behind it, every attempt that was spent, the commit as fields, and the paths to
the run's own result file and journal. It lands under the journal's
``results/`` through :func:`write`, which goes through :mod:`mcgyvr.atomic`, so
a reader sees the previous file or the new one and never a half-written one.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcgyvr import atomic

RESULTS_DIR = "results"

#: The key `session` was written under before it was renamed: still written,
#: with the same value, for one release (see `RunResult.session`).
DEPRECATED_SESSION_KEY = "orchestrator"


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
    #: `notes` is the failure-notes record `findings` is rendered from, as the
    #: JSON `mcgyvr.notes.FailureNotes.as_json` writes (`mcgyvr.failure_notes/1`):
    #: each check's observation with its path, line, code, command and exit
    #: where the check reported them. `None` on a try that left no record.
    notes: dict[str, Any] | None = None
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
    #: `session` is the session the run was filed under (`mcgyvr.session`), the
    #: name of its journal; `session_file` is that session's transcript. The file
    #: also carries the same name under `orchestrator`, its key before the rename,
    #: read by nothing here and kept for one release so an older reader finds it.
    session: str
    #: `run` is this run's stamp, the id its journal rows and result file share;
    #: `journal` is the directory it was recorded under.
    run: str = ""
    session_file: str | None = None
    journal: str | None = None
    outcome: str = "error"
    #: `outcome` is one word for what the run came to — `accepted`, `rejected`,
    #: `nothing_to_change`, `delivery_refused`, one of the ceilings that stopped
    #: the climb (`ladder_spent`, `escalation_ceiling`, `attempt_ceiling`,
    #: `nothing_to_run`, `declined_throughout`), `blocked` when the dependency
    #: tree held the contract and nothing was dispatched (`mcgyvr.tree`), or
    #: `error` when nothing was judged at all — and `detail` says it in a
    #: sentence, and on a re-planned contract what took its place.
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
    #: `exit_code` is what the process returned for this run.
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
    #: a time.
    notes: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    finished: float | None = None
    #: `triage` is where the climb started and who decided it, under
    #: `triage: jev` or a contract's `start_rung`: the `rung`, its `source`
    #: (`jev` or `contract`), and for jev every rung's `probabilities`, its
    #: `confidence` and the `model` asked, or a `fallback` saying why the climb
    #: started on its first rung instead. `None` when nothing decided a start,
    #: and then the key is left out of the file.
    triage: dict[str, Any] | None = None
    #: `blocked_by` is why the dependency tree held a `blocked` contract: the
    #: `reason`, the `providers` it waited on with what each came to, the
    #: `needs` it had of them and the `chain` a hold came down through. `None`
    #: on every other run, and then the key is left out of the file.
    blocked_by: dict[str, Any] | None = None
    #: `seeded` is what this run was handed from an earlier run of the same
    #: contract (`mcgyvr direct --notes-from RESULT`): `from`, the result file read,
    #: `records`, each failure-notes record read from it with the `run` it was
    #: made in, oldest first, and `handed`, how many of them the climb was
    #: started with — all of them under `retry_notes: climb`, none under `rung`,
    #: `none` or on the deterministic floor. `None` on a run that was not
    #: seeded, and then the key is left out of the file.
    seeded: dict[str, Any] | None = None
    #: `replanned` is what a batch made of a `ladder_spent` contract after its
    #: run (`mcgyvr.replan`): the `round` and the `max_replans` it was held to,
    #: the `contracts` proposed in its place (none when it was not re-planned)
    #: and a `detail` sentence. `None` on every other run, and then the key is
    #: left out of the file.
    replanned: dict[str, Any] | None = None

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        data[DEPRECATED_SESSION_KEY] = self.session
        if self.triage is None:
            del data["triage"]
        if self.blocked_by is None:
            del data["blocked_by"]
        if self.seeded is None:
            del data["seeded"]
        if self.replanned is None:
            del data["replanned"]
        return data


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


def amend(path: Path, changes: dict[str, Any]) -> Path:
    """Rewrite the result file at `path` with `changes` over what it holds.

    For what is learned about a run after its result was written, such as the
    contracts a batch re-planned it into. The rest of the file is kept as it
    was, `finished` included, and the file is replaced whole.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    return _write_json(path, data)


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    """Write ``data`` as JSON at ``path`` and return the path.

    The parent directory is made first — a run's ``results/`` need not exist
    yet — and the bytes are indented, key-sorted and newline-terminated, then
    written through :func:`mcgyvr.atomic.write` so the file is replaced whole.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(path, json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path
