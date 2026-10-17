""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr import atomic
from mcgyvr.redact import scrub
from mcgyvr.runner import Completion

if TYPE_CHECKING:  #
    from collections.abc import Callable, Mapping, Sequence

#
#
#
#
type Record = dict[str, Any]

# a
#
#
TELEMETRY_VERSION = 1

#
#
#
ATTEMPT_KIND = "attempt"
CORRECTION_KIND = "correction"

#
#
#
#y.
#
#
#
#
#ow
#
#
#
#
#e
#ys
#
_VERDICT = "outcome"
_CORRECTABLE = (_VERDICT, "detail", "applied_by")

#
#
#
BLOB_DIR = "blobs"

#
#
#
STOCK = "stock"

#
#
RUN_TAGS_ENV = "MCGYVR_RUN_TAGS"

#
#
#
#
RUN_TAGS_KEY = "run_tags"

#
#
#
RUN_TAGS_MAX_BYTES = 4096

#
#
RUN_TAGS_MAX_INT = 2**53

type TagValue = str | int | float | bool


class RunTagsError(ValueError):
    ""


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
    ""
    #
    #
    #
    started = time.monotonic()

    def append(record: Record) -> None:
        _append(path, record, mirrors=mirrors, on_copy_error=on_copy_error)

    def store(data: bytes) -> str:
        return _store(path, data, mirrors=mirrors, on_copy_error=on_copy_error)

    #on
    #ct
    #
    #
    #
    #
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
        #
        #
        #
        #
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
        #
        #
        #
        #
        #
        append(unlanded(failure))
        raise

    record = (
        _stamp(ATTEMPT_KIND, attempt_id)
        | {
            "orchestrator": orchestrator,
            "rung": rung,
            "ok": True,
            #
            #
            #h,
            #
            #
            "elapsed_s": _since(started),
        }
        | identity
    )
    if isinstance(answer, Completion):
        record |= _completion_fields(answer)
        try:
            #
            #
            #nk
            #as
            #
            record["reply_sha256"] = store(_bytes(scrub(answer.text)))
        except BaseException as failure:
            append(unlanded(failure))
            raise
    append(record)
    return answer


def _completion_fields(answer: Completion) -> Record:
    ""
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
    #
    # a
    #
    #
    if answer.cap_basis:
        #or
        #es
        #
        fields["cap_basis"] = answer.cap_basis
    if answer.notes:
        fields["notes"] = list(answer.notes)
    #
    #
    #
    #
    for key, count in (
        ("input_tokens", answer.input_tokens),
        ("output_tokens", answer.output_tokens),
        #
        #
        ("reasoning_tokens", answer.reasoning_tokens),
    ):
        if count is not None:
            fields[key] = count
    #
    #
    #
    #
    #
    for key, value in (
        ("decode_tok_s", answer.decode_tok_s),
        ("decode_source", answer.decode_source),
        ("prefill_tok_s", answer.prefill_tok_s),
        ("prefill_source", answer.prefill_source),
        ("in_flight", answer.in_flight),
        ("in_flight_source", answer.in_flight_source),
        #
        #
        #
        ("draft_n", answer.draft_n),
        ("draft_n_accepted", answer.draft_n_accepted),
    ):
        if value is not None:
            fields[key] = value
    #
    #
    if answer.tool_calls:
        fields["tool_calls"] = len(answer.tool_calls)
    return fields


def _prompt_identity(
    store: Callable[[bytes], str], messages: Sequence[Mapping[str, str]] | None
) -> Record:
    ""
    if messages is None:
        return {}
    fields: Record = {"prompt_sha256": store(_render(messages))}
    system = next((m["content"] for m in messages if m.get("role") == "system"), None)
    if system is not None:
        #
        #
        #
        #
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
    ""
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
    #
    tags = run_tags()
    if tags:
        fields[RUN_TAGS_KEY] = tags


def _render(messages: Sequence[Mapping[str, str]]) -> bytes:
    ""
    rendered = "\n".join(f"[{m['role']}]\n{scrub(m['content'])}\n" for m in messages)
    return _bytes(rendered)


def _bytes(text: str) -> bytes:
    ""
    return text.encode("utf-8", "surrogateescape")


def _store(
    path: Path,
    data: bytes,
    *,
    mirrors: Sequence[Path] = (),
    on_copy_error: CopyError | None = None,
) -> str:
    ""
    digest = _store_one(path, data)
    _also(mirrors, on_copy_error, lambda mirror: _store_one(mirror / path.name, data))
    return digest


def _store_one(path: Path, data: bytes) -> str:
    ""
    digest = hashlib.sha256(data).hexdigest()
    blobs = path.parent / BLOB_DIR
    blobs.mkdir(parents=True, exist_ok=True)
    blob = blobs / digest
    if blob.exists():
        return digest
    #
    #
    atomic.write(blob, data)
    return digest


def run_tags() -> dict[str, TagValue] | None:
    ""
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
    ""
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
    ""
    record = _stamp(CORRECTION_KIND, attempt_id) | {
        "outcome": outcome,
        "detail": detail,
        "applied_by": orchestrator,
    }
    _append(path, record, mirrors=mirrors, on_copy_error=on_copy_error)


def fold(*, path: Path) -> list[Record]:
    ""
    attempts: list[Record] = []
    corrections: list[tuple[int, Record]] = []
    for position, record in enumerate(_read(path)):
        if record.get("record_kind") == CORRECTION_KIND:
            corrections.append((position, record))
            continue
        attempts.append(record)

    # a
    # a
    #
    latest: dict[str, int] = {}
    for index, record in enumerate(attempts):
        latest[str(record.get("attempt_id", ""))] = index

    orphans: list[Record] = []
    #
    #
    #
    #
    #
    #
    #
    said: dict[int, Record] = {}
    for _, correction in sorted(corrections, key=lambda entry: entry[0]):
        match = latest.get(str(correction.get("attempt_id", "")))
        if match is None:
            orphans.append(correction)
            continue
        base = attempts[match]
        if correction.get(_VERDICT) is None:
            #
            #
            #
            #s.
            continue
        own = said.setdefault(
            match, {key: base[key] for key in _CORRECTABLE if key in base}
        )
        for key in _CORRECTABLE:
            #
            #
            #
            #
            value = correction.get(key)
            if value is None:
                value = own.get(key)
            if value is None:
                base.pop(key, None)
            else:
                base[key] = value

    return attempts + orphans


def _stamp(kind: str, attempt_id: str) -> Record:
    ""
    return {
        "record_kind": kind,
        "version": TELEMETRY_VERSION,
        "ts": time.time(),
        "attempt_id": attempt_id,
    }


def _since(started: float) -> float:
    ""
    return round(time.monotonic() - started, 6)


#
#
#
type CopyError = Callable[[Path, BaseException], None]


def _also(
    mirrors: Sequence[Path],
    on_copy_error: CopyError | None,
    write: Callable[[Path], object],
) -> None:
    ""
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
    ""
    line = (json.dumps(record) + "\n").encode("utf-8")
    _append_line(path, line)
    _also(mirrors, on_copy_error, lambda mirror: _append_line(mirror / path.name, line))


def _append_line(path: Path, line: bytes) -> None:
    ""
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
    ""
    end = os.lseek(fd, 0, os.SEEK_END)
    if end == 0:
        return
    os.lseek(fd, end - 1, os.SEEK_SET)
    if os.read(fd, 1) != b"\n":
        os.write(fd, b"\n")


def _write_all(fd: int, data: bytes) -> None:
    ""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(
                f"telemetry sink accepted {len(data) - len(view)} of {len(data)} bytes"
            )
        view = view[written:]


def _read(path: Path) -> list[Record]:
    ""
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
