"""A run writes down what happened, so the ordering question can be answered later.

Which rung should have gone first is a research question, and research needs
rows: which rung ran, on which machine and serving unit, how long it took, what
the verdict was, and what it cost against the rung's attempt budget. Those are
facts the run is in a position to state.

What is deliberately *not* here is a column naming the rung that should have
run. mcgyvr has no measurement that would fill it in — that is the question the
ladder exists to study — and a field called ``rank`` or ``should_have_used``
would be this module answering it by construction, in a file every later
analysis reads as data. The record therefore holds no opinion; it holds the
rows an opinion could one day be argued from.

JSONL, appended, one object per attempt in the order they happened. Append
rather than rewrite because a run that dies half way through should leave the
attempts it did make, and one line per attempt because a partial write then
costs the last row instead of the file. Order is the record's own claim: it is
the sequence the ladder actually took.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

RECORD_SUFFIX = ".jsonl"


@dataclass(frozen=True)
class Attempt:
    """One rung, tried once, and what came of it.

    ``unit`` names the process the rung ran against
    (:attr:`mcgyvr.serving.UnitKey.slug`) and is not implied by ``host`` and
    ``model``: two rungs can name one model on one machine and resolve to a
    single server, and an analysis that could not see that would count one
    process's throughput twice.

    ``attempts_charged`` is separate from the row existing at all, because a
    declined rung is an event worth recording that cost nothing — the ladder
    looked, decided this rung could not hold the model, and moved on. Dropping
    those rows would make the record say the ladder never considered it.
    """

    rung: str
    host: str
    model: str
    unit: str
    wall_clock_s: float
    verdict: str
    attempts_charged: int


def new_run_id() -> str:
    """A fresh run's id: sortable by when, unique by construction.

    The timestamp is there so a directory of records reads in order; the random
    tail is there because two runs can start inside the same second and a
    collision would silently braid two runs into one file.
    """
    return f"run-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}"


def write_record(
    attempts: Iterable[Attempt], root: Path, run_id: str | None = None
) -> Path:
    """Append ``attempts`` to a run's record under ``root``. Returns the file.

    Without ``run_id`` this starts a new record; passing a prior file's stem
    continues that one, which is how a run that reports as it goes stays one
    file. The stem *is* the id, so the path a caller was handed is the only
    thing it has to keep.
    """
    if run_id is not None and (run_id != Path(run_id).name or run_id in {".", ".."}):
        raise ValueError(f"{run_id!r} is not a run id; it names a path")
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{run_id or new_run_id()}{RECORD_SUFFIX}"
    with path.open("a", encoding="utf-8") as handle:
        for attempt in attempts:
            handle.write(json.dumps(asdict(attempt)) + "\n")
    return path
