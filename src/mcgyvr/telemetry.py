"""Attempt telemetry — one appended record per attempt, and how it landed (X02).

mcgyvr measures a great deal and keeps none of it. A
:class:`~mcgyvr.runner.Completion` carries host-side latency, the backend's own
token counts and the cap it was issued under; a gate run carries findings and
the rungs that could not say; a judgement carries the assurance an acceptance
rests on. Every one of them is discarded when the call returns, so nothing about
a run is answerable once it exits — not what it cost, not which rung did the
work, not whether climbing the ladder was worth it. This module is where a run
stops being unanswerable, and every before/after claim about the ladder is
downstream of it.

The shape is one JSON object per line, appended and never rewritten. Each of its
properties is load-bearing:

* **Exactly one record per attempt, including the attempt that raised.** The
  write sits inside an ``except`` that re-raises rather than after the call, so
  the failing path — reached by an exception, and therefore the path a sink
  written after the call site never sees — is recorded by construction. A store
  holding only the attempts that returned describes only the runs that went
  well, which is worse than no store, because the numbers look complete.
* **A correction is appended, never edited in.** How the work finally landed is
  learned after the attempt was written, and the cheap way to apply it is to
  rewrite the line. That trades away the two properties append-only is chosen
  for: it is the only shape several orchestrators can write at once, and the
  only one that survives a crash mid-write. So :func:`correct` writes a small
  record of its own keyed by the attempt's id, and :func:`fold` applies it at
  read time, latest-wins.
* **A correction naming no attempt is surfaced, not dropped.** It is an
  authoring error, and a fold that discarded it would turn a visible mistake
  into missing data. It comes back from :func:`fold` verbatim, after the
  attempts; a reader that wants attempts alone filters on ``record_kind``.
* **An unreported token count is absent, never zero.** :mod:`mcgyvr.runner`
  states the rule twice in its own words — "a zero would average into telemetry
  as a real measurement of nothing" — and this is the module where it is kept or
  lost, because ``0`` is what a dataclass default and a ``dict.get(key, 0)``
  both produce, and both look deliberate. A count the backend did not report has
  no key here at all. A reader that reads a missing key as zero is making the
  error the rule exists to prevent; one that reads it as "not reported" is
  reading the store correctly.

**The v2 constraint (docs/port-from-local-ai.md §9).** The queue architecture
puts several orchestrators behind one stream, so this module holds no state:
there is no logger object, no default sink, and nothing module-level for a
second orchestrator to share by accident. ``path`` is required at every call —
an implicit sink is exactly how two orchestrators come to write one file without
either of them saying so — and every attempt record names the ``orchestrator``
that produced it, because a field added on the day the second orchestrator
starts leaves every record written before it unattributable forever. Writes are
serialised with an exclusive ``flock`` around a single appending write, so
concurrent callers in one process or across processes interleave whole lines and
never halves of two.

**What is deliberately not here.** No dispatch: :func:`observe` takes a callable
and records whatever it returns — a completion or anything else — because what
has to be recorded is not a property of how the work was done, and a telemetry
module that knew how to run an attempt could not record one it did not run. No
derived quantities: a cost in
dollars, an overran-cap flag and a success rate are all computable from fields
already on the row, and freezing one here would store today's price list as
though it were a measurement. No reply text: this is a measurement stream, and
copying a worker's output into it grows every row without answering a question
the row exists to answer.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from typing import TYPE_CHECKING, Any

from mcgyvr.redact import scrub
from mcgyvr.runner import Completion

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable
    from pathlib import Path

# One record is one JSON object. Deliberately not a dataclass on the way out:
# a reader is looking at records written by versions of mcgyvr other than its
# own, and a schema class would refuse the ones it does not recognise rather
# than handing them over as what they are.
type Record = dict[str, Any]

# Bump when what a field *means* changes. Additive fields do not need it — a
# reader that has never heard of a key ignores it, which is the durability the
# line-per-record shape is for.
TELEMETRY_VERSION = 1

# ``record_kind`` discriminates the two line shapes sharing one sink: an
# attempt is the full per-attempt row, a correction is the small append-only
# statement of how that attempt's work finally landed.
ATTEMPT_KIND = "attempt"
CORRECTION_KIND = "correction"

# What a correction is allowed to say about its attempt, and the whole of it. A
# correction that could set any field could rewrite which orchestrator ran the
# work or how long it took, which is the in-place edit this shape exists to
# refuse — spelled differently. ``outcome`` and ``detail`` move together
# because the detail is the winning outcome's own words: keeping a superseded
# correction's prose beside a newer verdict would report a reason nobody gave
# for it.
_CORRECTABLE = ("outcome", "detail")


def observe[T](
    attempt: Callable[[], T],
    *,
    path: Path,
    attempt_id: str,
    orchestrator: str,
    rung: str,
    model: str | None = None,
) -> T:
    """Run one attempt, append exactly one record for it, and hand back its answer.

    The answer is returned unchanged — the same object, not a copy — so that
    recording an attempt is never a decision about whether to record it: a call
    site can be wrapped without its result changing identity or shape. It need
    not be a :class:`~mcgyvr.runner.Completion`: a deterministic-floor run
    produces no completion, and its row simply omits the completion-only
    fields.

    ``model`` is only read when the attempt raised. A completion names the model
    that actually answered, which is the better fact and wins whenever there is
    one; a dispatch that died never produced one, and a failed attempt that
    cannot say which model failed is a hole in exactly the data this exists to
    collect.

    A sink that cannot be written raises rather than being swallowed. Silence
    here is the failure this module was built to end, and an unwritable path is
    an operator error that is cheap to fix at the moment it happens and
    impossible to notice a week later, when the answer is simply missing rows.
    """
    started = time.monotonic()
    try:
        answer = attempt()
    except BaseException as failure:
        # BaseException rather than Exception: an interrupted run is still an
        # attempt that happened, and the moment a run is killed is exactly when
        # a hole in the record is hardest to account for afterwards. The record
        # is written before the re-raise, so the caller's exception is what
        # propagates and this line is not in its path.
        record = _stamp(ATTEMPT_KIND, attempt_id) | {
            "orchestrator": orchestrator,
            "rung": rung,
            "ok": False,
            "elapsed_s": _since(started),
            "error": type(failure).__name__,
            "error_detail": scrub(str(failure)),
        }
        if model is not None:
            record["model"] = model
        _append(path, record)
        raise

    record = _stamp(ATTEMPT_KIND, attempt_id) | {
        "orchestrator": orchestrator,
        "rung": rung,
        "ok": True,
        # Two timings that are two different quantities. ``latency_s`` is the
        # runner's, around the request alone; ``elapsed_s`` is this call's,
        # around everything the attempt did — prompt, dispatch, apply, gate.
        # Their difference is the host-side cost of an attempt, which no single
        # measurement states.
        "elapsed_s": _since(started),
    }
    if isinstance(answer, Completion):
        record |= _completion_fields(answer)
    _append(path, record)
    return answer


def _completion_fields(answer: Completion) -> Record:
    """The completion-only fields of a row, read from a real completion.

    A deterministic attempt produces no completion, so these keys are absent
    from its row — the same absence-is-honest rule that governs token counts.
    """
    fields: Record = {
        "latency_s": answer.latency_s,
        "model": answer.model,
        "source": answer.source,
        "protocol": answer.protocol.value,
        "stop_reason": answer.stop_reason.value,
        "raw_stop_reason": answer.raw_stop_reason,
        "max_output_tokens": answer.max_output_tokens,
        "quality_safe": answer.quality_safe,
    }
    if answer.notes:
        fields["notes"] = list(answer.notes)
    # The rule, in the one place it can be broken: a count the backend did not
    # report is left out of the row entirely. Writing ``None`` would be honest
    # too, but a key present in some rows and null in others invites a reader to
    # coerce it, and coercing an absent count is how it becomes a zero.
    for key, count in (
        ("input_tokens", answer.input_tokens),
        ("output_tokens", answer.output_tokens),
    ):
        if count is not None:
            fields[key] = count
    return fields


def correct(
    *,
    path: Path,
    attempt_id: str,
    outcome: str,
    orchestrator: str,
    detail: str = "",
) -> None:
    """Append how one attempt's work finally landed, leaving its record alone.

    ``outcome`` is a word, not an enum, because the vocabulary belongs to
    whatever finally accepts the work — a merge gate, a review, another
    orchestrator taking it off the out-queue — and this module is not entitled
    to decide what those may say. What it does decide is that the statement
    arrives as its own line: an attempt's record is bytes on disk that no later
    fact rewrites.

    ``orchestrator`` is the one applying the correction, which under §9 need not
    be the one that ran the attempt. It is required, not optional, because a
    correction that names no known attempt has no attempt row to borrow an
    author from: the one place an orphan could be anonymous is the one place a
    reader most needs to know who wrote it.
    """
    record = _stamp(CORRECTION_KIND, attempt_id) | {
        "outcome": outcome,
        "detail": detail,
        "applied_by": orchestrator,
    }
    _append(path, record)


def fold(*, path: Path) -> list[Record]:
    """Attempt records in the order they were written, corrections folded in.

    This is what a report or a learning loop reads; the raw lines are for
    forensics. Each correction is applied onto the attempt whose id it names,
    latest-wins, where "latest" is position in the file — the order the writes
    actually happened. A correction's own ``ts`` is wall-clock metadata a reader
    can inspect, not a ranking: two hosts writing one sink have two clocks, and
    the file's order is the only order they share. A repeat attempt id is a
    collision, not a supersede — every attempt row survives, and a correction
    binds to the latest row carrying its id.

    A correction naming no known attempt comes back verbatim at the end rather
    than being dropped. It is a mistake somebody made, and a mistake that is
    visible costs one question; a mistake that deletes itself costs the trust in
    every other number in the file.
    """
    attempts: list[Record] = []
    corrections: list[tuple[int, Record]] = []
    for position, record in enumerate(_read(path)):
        if record.get("record_kind") == CORRECTION_KIND:
            corrections.append((position, record))
            continue
        attempts.append(record)

    # A correction binds to the latest attempt row carrying its id — the one a
    # corrector most plausibly just corrected — but a repeat id never makes a
    # row disappear.
    latest: dict[str, int] = {}
    for index, record in enumerate(attempts):
        latest[str(record.get("attempt_id", ""))] = index

    orphans: list[Record] = []
    for _, correction in sorted(corrections, key=lambda entry: entry[0]):
        match = latest.get(str(correction.get("attempt_id", "")))
        if match is None:
            orphans.append(correction)
            continue
        base = attempts[match]
        for key in _CORRECTABLE:
            # ``None`` is "this correction does not say", which leaves whatever
            # an earlier one said standing. Absence is not a retraction.
            if correction.get(key) is not None:
                base[key] = correction[key]

    return attempts + orphans


def _stamp(kind: str, attempt_id: str) -> Record:
    """The fields every line carries, whatever its kind.

    ``ts`` is wall-clock rather than monotonic on purpose: it has to be
    comparable against a record another process wrote, and a monotonic clock is
    only meaningful within the process that read it.
    """
    return {
        "record_kind": kind,
        "version": TELEMETRY_VERSION,
        "ts": time.time(),
        "attempt_id": attempt_id,
    }


def _since(started: float) -> float:
    """Wall time since ``started``, measured on the clock that cannot go back."""
    return round(time.monotonic() - started, 6)


def _append(path: Path, record: Record) -> None:
    """Add one line to the sink, whole, under an exclusive lock.

    The lock and the append mode do two different jobs, and both are needed for
    the concurrency §9 asks for: ``O_APPEND`` puts every write at the end of the
    file as it is *now*, so a writer that waited does not overwrite what it
    waited for, and the ``flock`` keeps two writers from interleaving parts of
    two lines. Two more rules keep one line from destroying the next: the file
    is checked to end on a line boundary first — a torn line left by a crash is
    terminated, not glued onto — and the write is counted, because a short write
    on a full disk is a failure to signal, not a stump to leave behind.
    """
    line = (json.dumps(record) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            _terminate_stump(fd)
            _write_all(fd, line)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _terminate_stump(fd: int) -> None:
    """End the file on a line boundary if it does not already end on one.

    A write that crashed, or that a full disk accepted only half of, leaves
    bytes with no trailing newline. The next record must not be glued onto them,
    so the stump is terminated before the new line is written.
    """
    end = os.lseek(fd, 0, os.SEEK_END)
    if end == 0:
        return
    os.lseek(fd, end - 1, os.SEEK_SET)
    if os.read(fd, 1) != b"\n":
        os.write(fd, b"\n")


def _write_all(fd: int, data: bytes) -> None:
    """Write ``data`` whole, raising if the sink accepts less than all of it.

    A regular file on a full disk can take a short write without an error from
    ``os.write``; the only way to know the line is intact is to count. A partial
    line is the exact stump this module's append-only shape exists to survive,
    and it is survivable only if the writer does not silently declare victory.
    """
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(
                f"telemetry sink accepted {len(data) - len(view)} of {len(data)} bytes"
            )
        view = view[written:]


def _read(path: Path) -> list[Record]:
    """Every record in the sink, in file order. A sink that does not exist is empty.

    A line that will not decode or parse is skipped rather than raising. The
    append-only shape is chosen because it survives a crash mid-write, and it
    only actually survives one if the reader does too: a torn last line is
    already lost, and letting it take every record before it as well would give
    up the property the shape was chosen for. An undecodable byte is the same
    case one step earlier — the line is decoded on its own, so one bad byte
    loses one line, not the whole sink.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return []
    records: list[Record] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            text = line.decode("utf-8")
            parsed = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records
