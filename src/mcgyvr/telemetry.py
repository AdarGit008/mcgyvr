"""A journal of dispatches: one JSON line per attempt, blobs beside it.

``observe`` wraps a single attempt. Before calling it, it gathers the identity
of the attempt — condition, endpoint, task type, operation, tier, temperature,
session file, prompt digests and the run tags the environment names — and then
writes the row that says how the attempt went. A row is a flat JSON object
stamped with its record kind, the layout version, a wall-clock time and the
attempt id.

The bytes a row quotes instead of inlining — the rendered prompt, the scrubbed
reply — are stored under ``blobs`` beside the sink, named by the SHA-256 of
their own content, so a row points at its evidence by digest and identical
bytes are stored once however many rows cite them. Rows and blobs can be copied
into mirror directories; a failed copy is reported to an ``on_copy_error``
callback when one is given, and raises otherwise.

``correct`` appends a later stage's verdict on an attempt, and ``fold`` reads a
file back with those verdicts laid over the attempts they name. Text the journal
quotes and did not build itself passes through ``scrub`` first, since a URL
carrying credentials is what a model endpoint tends to look like."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr import atomic, hostos
from mcgyvr.redact import scrub
from mcgyvr.runner import Completion

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Mapping, Sequence

# A row of the journal: a flat mapping from field name to JSON value, assembled
# by joining a stamp — record kind, layout version, timestamp, attempt id — with
# the fields of the attempt or correction it records. Rows are written as one
# JSON object per line and read back as plain dicts, never as typed objects.
type Record = dict[str, Any]

# The layout version stamped on every row. It names the shape of the row, so a
# reader holding a line can tell which set of fields, and which meanings for
# them, it was written under.
TELEMETRY_VERSION = 1

# The two kinds of row a journal holds: an attempt that dispatched something,
# and a correction a later stage appended to say how that attempt turned out.
# ``_read`` keeps both as they are; ``fold`` is what brings them back together.
ATTEMPT_KIND = "attempt"
CORRECTION_KIND = "correction"

# The field a correction's verdict is written under, and the fields on an
# attempt that a correction may overwrite: the verdict, the free-text detail,
# and the orchestrator recorded as having applied it. The verdict is also what
# makes a correction actionable — ``fold`` applies one only when it carries an
# ``outcome``, and passes over one that does not, on the grounds that it says
# nothing about how the attempt went. An applied correction works from the
# values the attempt row itself carried, not from an earlier correction, so a
# field left out of a later correction restores the attempt's own value and
# removes the field if the attempt had none to restore.
_VERDICT = "outcome"
_CORRECTABLE = (_VERDICT, "detail", "applied_by")

# The directory, created beside a journal file, holding the bytes a row names
# by digest rather than inlining: the rendered prompt and the scrubbed reply.
BLOB_DIR = "blobs"

# The condition written on every row. Nothing in this module varies a
# condition, so every row it writes says stock; the field is there so a row can
# be compared with a measurement taken under another condition.
STOCK = "stock"

#: The environment variable naming a JSON object of tags to stamp on every row
#: this process writes.
RUN_TAGS_ENV = "MCGYVR_RUN_TAGS"

#: The key the tags land under. Nested under one key rather than spread over the
#: row, so a tag can never stand in for a field this module writes itself, and so
#: a reader can tell what the product measured from what its caller asserted.
RUN_TAGS_KEY = "run_tags"

#: The limit on the raw variable, in bytes: the object is copied onto every row,
#: so it is held to something a row can afford to carry.
RUN_TAGS_MAX_BYTES = 4096

#: The largest magnitude a numeric tag may have, set so a reader that models
#: JSON numbers as doubles reads back exactly the number that was written.
RUN_TAGS_MAX_INT = 2**53

type TagValue = str | int | float | bool


class RunTagsError(ValueError):
    """Refused run tags: the variable does not hold a small JSON object of text,
    finite numbers and true/false values. The message names the variable and the
    fault.
    """


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
    tier: str | None = None,
    temperature: float | None = None,
    operation: str | None = None,
    mirrors: Sequence[Path] = (),
    on_copy_error: CopyError | None = None,
) -> T:
    """Run ``attempt`` once, journal the attempt, and return what it returned.

    The identity of the attempt is gathered and the prompt blobs written before
    ``attempt`` is called; if that fails, an unlanded row is appended and the
    failure propagates, so no attempt runs unrecorded. A failure raised by
    ``attempt`` is journaled the same way — ``ok`` false, the exception's type
    name and its scrubbed message, and the identity gathered so far — and is
    then re-raised unchanged.

    A successful row carries ``elapsed_s`` for the call as a whole. When the answer
    is a ``Completion``, the row also carries what ``_completion_fields`` draws
    from it, and the scrubbed reply text is stored as a blob named by
    ``reply_sha256``. Any other answer is journaled as ok with no reply blob.
    Every row and blob is copied into ``mirrors`` as well.
    """
    # The clock the row's ``elapsed_s`` is measured from starts here, so
    # gathering identity and writing blobs count towards it. Both helpers below
    # carry this attempt's mirrors and copy-error handler.
    started = time.monotonic()

    def append(record: Record) -> None:
        _append(path, record, mirrors=mirrors, on_copy_error=on_copy_error)

    def store(data: bytes) -> str:
        return _store(path, data, mirrors=mirrors, on_copy_error=on_copy_error)

    # The identity is filled in place before the attempt runs, and filling it is
    # fallible because it writes the prompt blobs. Filling it in rather than
    # returning it means a failure part-way through still leaves the fields
    # gathered so far available to the row that records that failure, so a row
    # that cannot say everything about what was asked still says what it can.
    identity: Record = {}

    def unlanded(failure: BaseException) -> Record:
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
        return record

    try:
        # Identity first and on its own: it writes the prompt blobs, and without
        # them the row cannot say what was asked. A failure here is journaled as
        # an unlanded attempt and re-raised before ``attempt`` is ever called.
        _identity(
            identity,
            store,
            messages=messages,
            endpoint=endpoint,
            task_type=task_type,
            session_file=session_file,
            tier=tier,
            temperature=temperature,
            operation=operation,
        )
    except BaseException as failure:
        append(unlanded(failure))
        raise

    try:
        answer = attempt()
    except BaseException as failure:
        # Journal the failure before letting it out. The row says what was asked
        # (the identity already gathered), that the attempt did not land, the
        # exception's type name, and its message with any credentialed URL
        # removed, so a run that dies is visible in the journal and not only in
        # a traceback.
        append(unlanded(failure))
        raise

    record = (
        _stamp(ATTEMPT_KIND, attempt_id)
        | {
            "orchestrator": orchestrator,
            "rung": rung,
            "ok": True,
            # ``elapsed_s`` times the call as a whole, identity work and blob
            # writes included; a Completion's ``latency_s``, added below, times
            # only the request that produced it. Keeping both shows how much of
            # the dispatch the request itself accounted for.
            "elapsed_s": _since(started),
        }
        | identity
    )
    if isinstance(answer, Completion):
        record |= _completion_fields(answer)
        try:
            # The reply is stored as a blob under the digest of its scrubbed
            # bytes, and only the digest goes on the row. A failure to store it
            # is journaled as an unlanded attempt and re-raised, so no row names
            # a digest that is not on disk.
            record["reply_sha256"] = store(_bytes(scrub(answer.text)))
        except BaseException as failure:
            append(unlanded(failure))
            raise
    append(record)
    return answer


def _completion_fields(answer: Completion) -> Record:
    """The row fields a ``Completion`` contributes, keyed as the row spells them.

    The fields every completion has are always present. Everything a backend may
    or may not report — why the reply cap came out where it did, notes, token
    counts, throughput, in-flight requests, draft counts, tool calls — is added
    only when the completion carries it, so an absent field means the backend
    did not measure it rather than that it measured zero.
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
    # Everything below is optional and goes on the row only when the completion
    # carries it, so an absent field means the backend did not report it rather
    # than that it reported zero. The fields written above are always present,
    # even when a backend has left them at their defaults.
    if answer.cap_basis:
        # Why the reply cap came out where it did: which limit bound it. Kept as
        # text, so the empty string means the runner recorded no reason.
        fields["cap_basis"] = answer.cap_basis
    if answer.notes:
        fields["notes"] = list(answer.notes)
    # Token counts come from the backend's usage block, when it sends one. A
    # backend that omits a count has not measured it, and zero tokens is a claim
    # about the reply rather than an absence, so a count is copied only when it
    # is not None.
    for key, count in (
        ("input_tokens", answer.input_tokens),
        ("output_tokens", answer.output_tokens),
        # Reasoning tokens are the part of the output a backend attributes to
        # thinking; only some backends report them.
        ("reasoning_tokens", answer.reasoning_tokens),
    ):
        if count is not None:
            fields[key] = count
    # Throughput and in-flight concurrency, and speculative-draft counts. The
    # rates and the request count are followed by a ``*_source`` string saying
    # how the number was arrived at, so a rate derived from usage over latency
    # can be told from one the server measured itself. Everything here is
    # optional and is copied only when the completion carries it.
    for key, value in (
        ("decode_tok_s", answer.decode_tok_s),
        ("decode_source", answer.decode_source),
        ("prefill_tok_s", answer.prefill_tok_s),
        ("prefill_source", answer.prefill_source),
        ("in_flight", answer.in_flight),
        ("in_flight_source", answer.in_flight_source),
        # ``draft_n`` is how many tokens speculative decoding proposed and
        # ``draft_n_accepted`` how many the target model kept; together they
        # give an acceptance rate. Backends without drafting report neither.
        ("draft_n", answer.draft_n),
        ("draft_n_accepted", answer.draft_n_accepted),
    ):
        if value is not None:
            fields[key] = value
    # Tool calls are counted, not copied: the row says how many the reply asked
    # for, and nothing of what they contained.
    if answer.tool_calls:
        fields["tool_calls"] = len(answer.tool_calls)
    return fields


def _prompt_identity(
    store: Callable[[bytes], str], messages: Sequence[Mapping[str, str]] | None
) -> Record:
    """The digests that identify the prompt, as row fields.

    ``prompt_sha256`` is the blob digest of the prompt as ``_render`` lays it
    out, so the rendered prompt can be recovered from ``blobs``.
    ``bundle_sha256`` is the SHA-256 of the system message alone, hashed as it
    was given, so rows built on the same system text can be grouped without
    reading a blob. No system message leaves that field out, and no messages
    leaves the mapping empty.
    """
    if messages is None:
        return {}
    fields: Record = {"prompt_sha256": store(_render(messages))}
    system = next((m["content"] for m in messages if m.get("role") == "system"), None)
    if system is not None:
        # The system message alone, digested as given and with no blob of its
        # own: the whole prompt is already stored under ``prompt_sha256``, and
        # this second digest is what lets rows be grouped by the bundle they
        # were built from without opening any of them.
        fields["bundle_sha256"] = hashlib.sha256(_bytes(system)).hexdigest()
    return fields


def _identity(
    fields: Record,
    store: Callable[[bytes], str],
    *,
    messages: Sequence[Mapping[str, str]] | None,
    endpoint: str | None,
    task_type: str | None,
    session_file: Path | None,
    tier: str | None = None,
    temperature: float | None = None,
    operation: str | None = None,
) -> None:
    """Add the attempt's identity fields to ``fields`` in place.

    ``condition`` is always written. The rest are written only when the caller
    supplied them — an empty ``operation`` counts as not supplied — so an absent
    field means the caller said nothing about it. The prompt digests come from
    ``_prompt_identity``, and the run tags from the environment are added under
    ``run_tags`` when there are any.
    """
    fields["condition"] = STOCK
    if endpoint is not None:
        fields["endpoint"] = endpoint
    if task_type is not None:
        fields["task_type"] = task_type
    if operation:
        fields["operation"] = operation
    if session_file is not None:
        fields["session_file"] = str(session_file)
    if tier is not None:
        fields["tier"] = tier
    if temperature is not None:
        fields["temperature"] = temperature
    fields |= _prompt_identity(store, messages)
    # Read from the environment per row: a run whose caller said what it belongs
    # to carries that on every record, and a caller who said nothing adds
    # nothing.
    tags = run_tags()
    if tags:
        fields[RUN_TAGS_KEY] = tags


def _render(messages: Sequence[Mapping[str, str]]) -> bytes:
    """The prompt as the bytes to be stored.

    Each message becomes a ``[role]`` line, its scrubbed content, then a blank
    line, in the order given. The role header keeps two prompts that differ only
    in who said what from hashing alike, and encoding with ``surrogateescape``
    keeps text that is not valid UTF-8 from failing to encode.
    """
    rendered = "\n".join(f"[{m['role']}]\n{scrub(m['content'])}\n" for m in messages)
    return _bytes(rendered)


def _bytes(text: str) -> bytes:
    """Encode text as UTF-8, writing undecodable surrogates back as the bytes
    they stand for, so a string that came from bytes that were not valid UTF-8
    encodes back to those same bytes.
    """
    return text.encode("utf-8", "surrogateescape")


def _store(
    path: Path,
    data: bytes,
    *,
    mirrors: Sequence[Path] = (),
    on_copy_error: CopyError | None = None,
) -> str:
    """Store ``data`` as a blob beside ``path`` and return the digest.

    The same bytes are stored in each mirror's blob directory, with mirror
    failures routed through ``on_copy_error``.
    """
    digest = _store_one(path, data)
    _also(mirrors, on_copy_error, lambda mirror: _store_one(mirror / path.name, data))
    return digest


def _store_one(path: Path, data: bytes) -> str:
    """Store ``data`` in the ``blobs`` directory beside ``path``; return its digest.

    The digest is the SHA-256 of the bytes, so the same content stored twice
    lands in one file. The write goes through ``atomic.write``, which stages the
    file and renames it, so a reader never sees a partial blob.
    """
    digest = hashlib.sha256(data).hexdigest()
    blobs = path.parent / BLOB_DIR
    blobs.mkdir(parents=True, exist_ok=True)
    blob = blobs / digest
    if blob.exists():
        return digest
    # Content addressing makes the write idempotent: a blob under this digest
    # already holds these bytes.
    atomic.write(blob, data)
    return digest


def run_tags() -> dict[str, TagValue] | None:
    """The run tags ``MCGYVR_RUN_TAGS`` names, or None when it is unset or empty.

    The variable is parsed as one JSON object, and every value is copied onto the
    row as given, except that text is scrubbed. A value that is not text, a
    finite number within ``RUN_TAGS_MAX_INT`` or a boolean is refused, as are a
    variable over ``RUN_TAGS_MAX_BYTES``, text that is not JSON or not an object,
    and keys that are empty, invalid UTF-8, duplicated or carrying credentials.
    Every refusal raises ``RunTagsError``.
    """
    value = os.environ.get(RUN_TAGS_ENV)
    if not value:
        return None
    size = len(value.encode("utf-8", "surrogateescape"))
    if size > RUN_TAGS_MAX_BYTES:
        raise RunTagsError(
            f"{RUN_TAGS_ENV} holds {size} bytes; it is copied onto every row, "
            f"so it is held to {RUN_TAGS_MAX_BYTES} bytes. Tag the run, do not "
            f"store a document in it"
        )

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in items]
        twice = sorted({key for key in keys if keys.count(key) > 1})
        if twice:
            named = [scrub(key) for key in twice]
            raise RunTagsError(f"{RUN_TAGS_ENV} names {named!r} twice")
        return dict(items)

    try:
        parsed = json.loads(value, object_pairs_hook=pairs)
    except json.JSONDecodeError as exc:
        raise RunTagsError(
            f"{RUN_TAGS_ENV} is not JSON ({exc.msg} at character {exc.pos}); set "
            f'it to a JSON object, e.g. {{"round": "r7"}}, or unset it'
        ) from exc
    if not isinstance(parsed, dict):
        raise RunTagsError(
            f"{RUN_TAGS_ENV} is not a JSON object but {type(parsed).__name__}; "
            f'set it to an object, e.g. {{"round": "r7"}}'
        )
    tags: dict[str, TagValue] = {}
    for key, tag in parsed.items():
        if not key:
            raise RunTagsError(f"{RUN_TAGS_ENV} has an empty key")
        if not _utf8(key):
            raise RunTagsError(f"{RUN_TAGS_ENV} has a key with a lone surrogate")
        if scrub(key) != key:
            raise RunTagsError(
                f"{RUN_TAGS_ENV} has a key holding a credentialed URL; a key "
                f"names a tag, it does not carry one"
            )
        if isinstance(tag, str) and _utf8(tag):
            tags[key] = scrub(tag)
        elif (
            isinstance(tag, bool)
            or (isinstance(tag, int) and abs(tag) <= RUN_TAGS_MAX_INT)
            or (isinstance(tag, float) and math.isfinite(tag))
        ):
            tags[key] = tag
        else:
            raise RunTagsError(
                f"{RUN_TAGS_ENV} sets {key!r} to {scrub(json.dumps(tag))}; a tag "
                f"is text, a number within ±2**53 or true/false"
            )
    return tags


def _utf8(text: str) -> bool:
    """Whether ``text`` encodes as UTF-8, which text holding a lone surrogate
    does not.
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def correct(
    *,
    path: Path,
    attempt_id: str,
    outcome: str,
    orchestrator: str,
    detail: str = "",
    mirrors: Sequence[Path] = (),
    on_copy_error: CopyError | None = None,
) -> None:
    """Append a correction row recording how the named attempt turned out.

    ``outcome`` is the verdict ``fold`` lays onto the attempt, ``detail`` the
    free text that goes with it, and ``orchestrator`` the name recorded as
    having applied it. The row is stamped as a correction and appended to the
    same sinks and mirrors an attempt row is.
    """
    record = _stamp(CORRECTION_KIND, attempt_id) | {
        "outcome": outcome,
        "detail": detail,
        "applied_by": orchestrator,
    }
    _append(path, record, mirrors=mirrors, on_copy_error=on_copy_error)


def fold(*, path: Path) -> list[Record]:
    """The attempts in the journal at ``path``, with corrections laid over them.

    Correction rows are separated out and the remaining rows are read as
    attempts. A correction names an ``attempt_id`` and is laid onto the last
    attempt row carrying that id; corrections are applied in file order, and
    each acts on the values that attempt row itself carried. A correction naming
    an id with no attempt row has nothing to correct and is returned after the
    attempts rather than dropped. A ``path`` that does not exist folds to no
    records at all.
    """
    attempts: list[Record] = []
    corrections: list[tuple[int, Record]] = []
    for position, record in enumerate(_read(path)):
        if record.get("record_kind") == CORRECTION_KIND:
            corrections.append((position, record))
            continue
        attempts.append(record)

    # Corrections are held back rather than applied where they are read: folding
    # needs each one's position in the file, and an attempt row has to exist
    # before a correction can be laid onto it.
    latest: dict[str, int] = {}
    for index, record in enumerate(attempts):
        latest[str(record.get("attempt_id", ""))] = index

    orphans: list[Record] = []
    # Corrections are applied in file order, so the last one written for an
    # attempt has the last word. ``said`` snapshots an attempt's own values the
    # first time a correction touches it, to be fallen back on for fields a later
    # correction leaves out: the attempt row as written is the baseline, not the
    # previous correction.
    said: dict[int, Record] = {}
    for _, correction in sorted(corrections, key=lambda entry: entry[0]):
        match = latest.get(str(correction.get("attempt_id", "")))
        if match is None:
            orphans.append(correction)
            continue
        base = attempts[match]
        if correction.get(_VERDICT) is None:
            # A correction with no ``outcome`` says nothing about how the attempt
            # turned out, so there is no verdict to fold and nothing is applied.
            # The row was counted as a correction, so it is not returned as an
            # attempt either.
            continue
        own = said.setdefault(
            match, {key: base[key] for key in _CORRECTABLE if key in base}
        )
        for key in _CORRECTABLE:
            # A field the correction leaves out falls back to the value the
            # attempt carried; when the attempt carried none there either, the
            # field is removed from the attempt rather than left standing, so a
            # correction can take a field away.
            value = correction.get(key)
            if value is None:
                value = own.get(key)
            if value is None:
                base.pop(key, None)
            else:
                base[key] = value

    return attempts + orphans


def _stamp(kind: str, attempt_id: str) -> Record:
    """The fields common to every row: its kind, the layout version, the time it
    was written, and the attempt it belongs to.
    """
    return {
        "record_kind": kind,
        "version": TELEMETRY_VERSION,
        "ts": time.time(),
        "attempt_id": attempt_id,
    }


def _since(started: float) -> float:
    """Seconds elapsed on the monotonic clock since ``started``, rounded to
    microseconds.
    """
    return round(time.monotonic() - started, 6)


#: What ``on_copy_error`` receives when a copy fails: the mirror directory and
#: the exception. Left as None, a failed copy propagates; given a handler, that
#: handler decides and the remaining mirrors are still written.
type CopyError = Callable[[Path, BaseException], None]


def _also(
    mirrors: Sequence[Path],
    on_copy_error: CopyError | None,
    write: Callable[[Path], object],
) -> None:
    """Run ``write`` for each mirror, handing a failure to ``on_copy_error``.

    Without a handler the first failure propagates; with one, the handler is
    called and the remaining mirrors are still written.
    """
    for mirror in mirrors:
        try:
            write(mirror)
        except Exception as exc:
            if on_copy_error is None:
                raise
            on_copy_error(mirror, exc)


def _append(
    path: Path,
    record: Record,
    *,
    mirrors: Sequence[Path] = (),
    on_copy_error: CopyError | None = None,
) -> None:
    """Append ``record`` to ``path`` as one JSON line, and to each mirror.

    The line is serialized once and the same bytes are written to every sink.
    """
    line = (json.dumps(record) + "\n").encode("utf-8")
    _append_line(path, line)
    _also(mirrors, on_copy_error, lambda mirror: _append_line(mirror / path.name, line))


def _append_line(path: Path, line: bytes) -> None:
    """Append ``line`` to the journal file at ``path``, creating it if needed.

    The parent directory is created, and the write happens under an exclusive
    ``flock`` on the file so concurrent writers append whole lines instead of
    interleaving them.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o666)
    try:
        hostos.lock(fd)
        try:
            _terminate_stump(fd)
            _write_all(fd, line)
        finally:
            hostos.unlock(fd)
    finally:
        os.close(fd)


def _terminate_stump(fd: int) -> None:
    """End the file in a newline before more is appended to it.

    A writer that died mid-line would otherwise leave a partial line for the next
    record to be glued onto, and ``_read`` would drop both of them.
    """
    end = os.lseek(fd, 0, os.SEEK_END)
    if end == 0:
        return
    os.lseek(fd, end - 1, os.SEEK_SET)
    if os.read(fd, 1) != b"\n":
        os.write(fd, b"\n")


def _write_all(fd: int, data: bytes) -> None:
    """Write all of ``data`` to ``fd``, looping while the kernel takes less.

    ``os.write`` may accept fewer bytes than it was given; a write that accepts
    none is raised as an error naming how much of the record reached the sink.
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
    """The records in the journal at ``path``, oldest first.

    Lines that are blank, not decodable UTF-8, not JSON, or not JSON objects are
    skipped, so one damaged line cannot hide the rest of the file. A missing file
    reads as no records at all.
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
