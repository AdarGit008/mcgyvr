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
though it were a measurement.

**The text is kept — beside the row, never in it (the live journal, WP0).**
This module used to refuse reply text, on the ground that a measurement stream
should not grow by a worker's output per row. The refusal was right about the
row and wrong about the text: a journal that keeps the hash and not the text
can be counted and never reviewed. A row could say a rung answered in 1.2 s and
could not say what it was asked or what it said, so nothing the product ever
dispatched was reviewable for quality, and every judgement about whether a
cheap rung's answers were any good rested on a number. Four rules govern how
the text is kept:

* **Content-addressed, under ``<sink dir>/blobs/<sha256>``.** The row carries
  ``prompt_sha256`` and ``reply_sha256`` — the names ``tools/bench/identity.py``
  already gives a request — and a blob is named by the digest of its own
  bytes, so a reader can verify a blob without trusting the row that named it.
  This is also what answers the old objection: one scaffold shared by
  thousands of prompts is one blob, and the same text dispatched twice costs
  nothing the second time. The store sits beside the sink rather than inside
  it because a sink is one orchestrator's file and the blobs are every
  orchestrator's — whoever dispatched the scaffold, it is the same scaffold.
* **Scrubbed before it is hashed.** :func:`~mcgyvr.redact.scrub` names
  telemetry as a sink an operator pastes into an issue, and a credential that
  reached a blob has left the machine the moment the blob is shared. Scrubbing
  first means the digest names the scrubbed bytes, so a reader who hashes the
  blob gets the row's name back; scrubbing after would leave the row naming
  bytes that exist nowhere on disk.
* **A raised attempt still names its prompt.** The prompt blob is written
  before the attempt runs, so ``prompt_sha256`` is a fact of the attempt
  whether or not anything came back — a failed dispatch that cannot say what
  it asked is the hole quality review exists to fill. ``reply_sha256`` is then
  absent: not null, and not the digest of the empty string, which looks
  exactly like a model that answered with nothing.
* **A blob that cannot be written raises**, by the sink rule above and without
  softening. A row naming a ``prompt_sha256`` whose blob was never written is
  worse than no row, because the hash reads as evidence that exists.

**A row names what answered it, and under which round.** ``tools/bench/identity.py``
settled what a measurement records after five lists disagreed and a manifest
mutated in the sixth field produced a byte-identical report; a live row that
carried none of those names could not be laid beside a bench cell, because it
did not say which endpoint served it, which system prompt it carried or which
product revision dispatched it. So each row also carries ``endpoint``,
``model``, ``protocol``, ``condition`` — always ``"stock"``: live work is the
product as shipped, never an ablation, and the field is what tells a live row
from a bench cell by content rather than by path — ``bundle_sha256`` (the
system prompt, hashed as the bench hashes it), and, when the process runs
inside this repo checkout, ``round`` and ``product_sha256``, read from
``tools/bench/product`` loaded by path the way ``tools/breadth/measure.py``
loads it. Off-round is recorded, not refused: live work is not a measurement
run, ``require_pinned`` is never called here, and the digest written is the
tree's, so a reader can flag ``off_round`` instead of being told nothing ran.
An install that is not this checkout has no round to name, and both keys are
absent rather than null — ``round: null`` would read to ``product.declare`` as
a run that recorded something.
"""

from __future__ import annotations

import contextlib
import fcntl
import functools
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import mcgyvr
from mcgyvr.redact import scrub
from mcgyvr.runner import Completion

if TYPE_CHECKING:  # pragma: no cover - typing only
    import types
    from collections.abc import Callable, Mapping, Sequence

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

# Where the text lives: a directory beside the sink, one file per distinct
# scrubbed text, named by the sha256 of its bytes. Beside rather than inside
# the sink because the sink is one orchestrator's and the blobs are shared.
BLOB_DIR = "blobs"

# The bench's word for "no ablation" (tools/bench/identity.py's `condition`).
# Written on every live row, because a live row and a bench cell have to be
# told apart by content: a directory of rows says nothing about which it holds.
STOCK = "stock"

# The `sys.modules` slot tools/breadth/measure.py loads tools/bench/product.py
# into. The same slot, not a suffixed one, so a process that already holds the
# module is handed that copy rather than a second one that could disagree.
_PRODUCT_SLOT = "bench_product"


def observe[T](
    attempt: Callable[[], T],
    *,
    path: Path,
    attempt_id: str,
    orchestrator: str,
    rung: str,
    model: str | None = None,
    messages: Sequence[Mapping[str, str]] | None = None,
    endpoint: str | None = None,
    task_type: str | None = None,
    session_file: Path | None = None,
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

    ``messages`` is the prompt as sent — ``{"role", "content"}`` pairs in the
    order the backend received them — and ``endpoint`` is the base URL that
    served it. Both are optional because an attempt need not be a dispatch at
    all, and both are absent from the row rather than null when not given.
    When ``messages`` is given, the prompt is scrubbed and stored as a blob
    *before* the attempt runs, so the row for an attempt that raised still
    names what it asked, and the system message is hashed onto the row as
    ``bundle_sha256``. A caller that has the prompt and does not pass it is
    writing a row nobody can review.

    ``task_type`` is the contract's kind of work and ``session_file`` is the
    transcript of the session that typed the command (:mod:`mcgyvr.session`).
    Both are identity, known before the attempt and written on both rows: a
    feedback loop that wants to say "this rung fails implementations" needs
    the type beside the verdict, and a reviewer who wants the conversation
    behind an attempt needs the path beside the row. Absent, not null, when
    the caller has neither.

    A sink that cannot be written raises rather than being swallowed. Silence
    here is the failure this module was built to end, and an unwritable path is
    an operator error that is cheap to fix at the moment it happens and
    impossible to notice a week later, when the answer is simply missing rows.
    The blob store is a sink under the same rule.
    """
    # Before the clock starts and before the attempt: what the attempt *is* —
    # its prompt, its endpoint, the revision dispatching it — is known now and
    # is the same fact whichever of the two rows below gets written. The
    # prompt blob reaches disk here, which is what lets a raised attempt still
    # name it; the clock starts after, so ``elapsed_s`` stays the attempt's.
    identity = _identity(path, messages=messages, endpoint=endpoint)
    if task_type is not None:
        identity["task_type"] = task_type
    if session_file is not None:
        identity["session_file"] = str(session_file)
    started = time.monotonic()
    try:
        answer = attempt()
    except BaseException as failure:
        # BaseException rather than Exception: an interrupted run is still an
        # attempt that happened, and the moment a run is killed is exactly when
        # a hole in the record is hardest to account for afterwards. The record
        # is written before the re-raise, so the caller's exception is what
        # propagates and this line is not in its path.
        record = (
            _stamp(ATTEMPT_KIND, attempt_id)
            | {
                "orchestrator": orchestrator,
                "rung": rung,
                "ok": False,
                "elapsed_s": _since(started),
                "error": type(failure).__name__,
                "error_detail": scrub(str(failure)),
            }
            | identity
        )
        if model is not None:
            record["model"] = model
        _append(path, record)
        raise

    record = (
        _stamp(ATTEMPT_KIND, attempt_id)
        | {
            "orchestrator": orchestrator,
            "rung": rung,
            "ok": True,
            # Two timings that are two different quantities. ``latency_s`` is
            # the runner's, around the request alone; ``elapsed_s`` is this
            # call's, around everything the attempt did — prompt, dispatch,
            # apply, gate. Their difference is the host-side cost of an
            # attempt, which no single measurement states.
            "elapsed_s": _since(started),
        }
        | identity
    )
    if isinstance(answer, Completion):
        record |= _completion_fields(answer)
        # Stored before the row that names it is appended, never after: a
        # reader must not find a row whose ``reply_sha256`` names nothing on
        # disk. A blob that cannot be written raises here and the row is not
        # written — the sink rule, not an exception to it.
        record["reply_sha256"] = _store(path, _bytes(scrub(answer.text)))
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


def _identity(
    path: Path,
    *,
    messages: Sequence[Mapping[str, str]] | None,
    endpoint: str | None,
) -> Record:
    """What the attempt is, known before it runs and shared by both rows it can write.

    The failing row and the succeeding row name the same prompt, endpoint and
    product revision, which is what makes a raised attempt reviewable at all.
    Every key here is absent, not null, when the caller could not supply it —
    an attempt that is not a dispatch has no endpoint and no prompt — under the
    rule that keeps an unreported token count out of the row.

    ``condition`` is the one key always written: live work is the product as
    shipped, and the bench's word for "no ablation" is ``"stock"``.
    """
    fields: Record = {"condition": STOCK}
    if endpoint is not None:
        fields["endpoint"] = endpoint
    if messages is not None:
        fields["prompt_sha256"] = _store(path, _render(messages))
        system = next(
            (m["content"] for m in messages if m.get("role") == "system"), None
        )
        if system is not None:
            # Raw, not scrubbed: this is the bench's ``bundle_sha256``
            # (``sha256(prompt.system)``, tools/breadth/measure.py) and has to
            # equal it for a live row to lie beside a bench cell. A digest
            # discloses nothing, so scrubbing would only make the two disagree.
            fields["bundle_sha256"] = hashlib.sha256(_bytes(system)).hexdigest()
    revision = _product_revision()
    if revision is not None:
        fields["round"], fields["product_sha256"] = revision
    return fields


def _render(messages: Sequence[Mapping[str, str]]) -> bytes:
    """The prompt as one blob: ``[role]``, the content, a blank line, per message.

    Deterministic — the same messages always render to the same bytes, which
    is what lets one prompt dispatched a thousand times be one blob — and
    readable as it is, every content a plain substring, so a reviewer who
    opens the blob reads what the model read rather than a JSON encoding of
    it. Each content is scrubbed on the way in, before the bytes exist to be
    hashed; the role is a vocabulary word and carries nothing to scrub.
    """
    rendered = "\n".join(f"[{m['role']}]\n{scrub(m['content'])}\n" for m in messages)
    return _bytes(rendered)


def _bytes(text: str) -> bytes:
    """``text`` as UTF-8, encoded the way every other writer in the project encodes.

    ``surrogateescape`` rather than strict: the prompt carries the target file,
    which :mod:`mcgyvr.drive` reads with ``surrogateescape`` so a byte no codec
    round-trips still reaches the worker, and the blob has to be able to hold
    what was sent. For text that is plain UTF-8 — every reply, and every prompt
    over a clean file — the bytes are identical to a strict encode; for the
    rest, a strict encode would raise out of an attempt that has not failed.
    """
    return text.encode("utf-8", "surrogateescape")


def _store(path: Path, data: bytes) -> str:
    """Put ``data`` in the sink's blob store and return the name it is stored under.

    The name is the sha256 of the bytes, so the store is a store and not a
    lookup table: a reader who hashes what it opened gets the name back. An
    existing blob is left alone — same bytes, same name — and a new one is
    written whole to a private staging name and moved into place, so a reader
    never opens a blob whose bytes do not yet hash to its name, and a crash
    mid-write leaves a stray ``.part`` file rather than a blob that lies about
    itself and, being "existing", would never be rewritten.

    Every ``OSError`` propagates, ``mkdir`` included: a file sitting where the
    directory must go is the cheapest way to be unwritable and is refused the
    same as a full disk. The row that would have named the blob is not
    written, which is the sink rule applied one level down.
    """
    digest = hashlib.sha256(data).hexdigest()
    blobs = path.parent / BLOB_DIR
    blobs.mkdir(parents=True, exist_ok=True)
    blob = blobs / digest
    if blob.exists():
        return digest
    # Unique per writer, so two threads or processes storing the same text at
    # once each stage their own copy and the last ``replace`` wins with bytes
    # identical to the first.
    staging = blobs / f".{digest}.{os.getpid()}-{threading.get_ident()}.part"
    fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        try:
            _write_all(fd, data)
        finally:
            os.close(fd)
        os.replace(staging, blob)
    except BaseException:
        # Best effort and only for the file this call created: the failure
        # that matters is the one about to propagate.
        with contextlib.suppress(OSError):
            os.unlink(staging)
        raise
    return digest


def _checkout() -> Path:
    """The repository this package was imported from — never the working directory.

    A wheel install run from inside somebody's checkout must not borrow that
    checkout's round, and a checkout run from elsewhere must not lose its own,
    so the only path that counts is the one the package itself resolves to.
    """
    return Path(mcgyvr.__file__).resolve().parents[2]


def _bench_product() -> types.ModuleType | None:
    """``tools/bench/product.py`` by path, or ``None`` when this is not the checkout.

    ``tools/`` is not a package, so the bench loads it by path into a named
    ``sys.modules`` slot; this uses the slot ``tools/breadth/measure.py`` uses
    and reuses whatever is already there, so a process that holds the module
    is not handed a second copy that could disagree with the first. ``None``
    is the honest answer for an install with no ``tools/bench/product.py``
    beside it: there is no round to name, and the row carries none.
    """
    cached = sys.modules.get(_PRODUCT_SLOT)
    if cached is not None:
        return cached
    source = _checkout() / "tools" / "bench" / "product.py"
    if not source.is_file():
        return None
    spec = importlib.util.spec_from_file_location(_PRODUCT_SLOT, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"{source} exists and cannot be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PRODUCT_SLOT] = module
    spec.loader.exec_module(module)
    return module


@functools.cache
def _product_revision() -> tuple[str, str] | None:
    """The open round's id and this tree's digest, or ``None`` outside the checkout.

    Memoised for the process because the digest walks every file of the
    product surface, and it is a fact about the checkout rather than about any
    orchestrator: two orchestrators in one process share one tree by
    construction, so this is a memo and not the shared state §9 forbids.
    ``require_pinned`` is deliberately not called. A live run off its round is
    recorded as such — the digest written is the tree's — and the reader flags
    it; refusing would make the journal go dark on exactly the days the
    product is changing.
    """
    product = _bench_product()
    if product is None:
        return None
    return str(product.open_round()["id"]), str(product.digest(_checkout()))


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
