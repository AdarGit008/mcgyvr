"""The mission record — output beside spec, and no verdict the gate did not write.

#365 item 5, off-SURFACE (``tools/missions/`` is not in ``product.SURFACE``).
Rides the owner's 2026-08-25 decision on #365: real commits become the tasks,
and **judging output against the issue body happens blind, at the month's
review** — not on the lane, not in code, not in the record.

**The defect this prevents.** A record that carries a verdict beside its output
is read as judged. Nothing distinguishes a ``"verdict": "good"`` a person typed
after a glance from one a gate computed, and once the field is on disk it is
quoted, tallied and believed (ADR-0026 lens 3: a record states the property it
contains, or it is worse than dead weight). The first reviewer to open sixty of
these a month from now must find sixty outputs and sixty specs and nothing that
tells them what to think. So the record has exactly one place a pass/fail may
appear — ``output.gate``, the gate's own result, which is a measurement of the
sandbox and not an opinion of the work — and :func:`read` refuses the record
outright when a verdict-shaped name appears anywhere else. The refusal is by
name and file (:class:`VerdictNotTheGates`), so the field that crept in is the
first thing on the screen.

**Why the check is on the reader and not only the writer.** :func:`write` is one
of many ways bytes reach ``task.json``; an editor is another. A writer-side
guard proves the record was clean when written, and the property the review
needs is that it is clean when *read*. Both sides run the same walk.

**Why side by side.** ``task.json`` is the record; ``spec.md`` and
``output/<path>`` are the same content laid out for a person — a spec to read
and files to open in an editor, beside each other, without a JSON decoder in
between. Two copies can drift, so :func:`read` refuses when the human-readable
copy disagrees with the record (:class:`RecordDriftError`): the on-disk files are
a view, and a view that says something the record does not is a second record.

**What the reader does not check.** ``identity`` is run.json-shaped and
``intent`` is a ``run-header/1`` — each has its own closed spine
(``identity.RECORDED``, ``headers.KEYS``) and its own reader. This module checks
the record's own top level and the whole ``output`` tree except ``output.gate``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = [
    "GATE",
    "MISSION_RECORD",
    "OUTPUT_DIR",
    "SPEC_FILE",
    "TASK_FILE",
    "VERDICT_SHAPED",
    "MissionRecord",
    "OutputPathError",
    "RecordDriftError",
    "RecordError",
    "RecordExistsError",
    "VerdictNotTheGates",
    "foreign_verdicts",
    "read",
    "write",
]

#: This record type. Versioned in the value, like ``run-header/1``.
MISSION_RECORD = "mission/1"

#: The record, the spec laid out for a person, and the output laid out for one.
TASK_FILE = "task.json"
SPEC_FILE = "spec.md"
OUTPUT_DIR = "output"

#: The one key under ``output`` where a pass/fail may appear: the gate's result.
GATE = "gate"

#: Names that read as a judgement. Matched case-insensitively, on the record's
#: top level and everywhere under ``output`` except ``output.gate``. The list is
#: closed on purpose: a name it does not carry is not refused, and adding one is
#: a diff here rather than a reviewer's memory.
VERDICT_SHAPED: frozenset[str] = frozenset(
    {"verdict", "score", "judged", "judgement", "judgment", "pass", "passed", "grade"}
)

#: The spine ``write`` owns. ``extra`` may not name any of these.
_SPINE: tuple[str, ...] = (
    "record",
    "identity",
    "intent",
    "spec",
    "output",
    "written_at",
)


class RecordError(Exception):
    """A mission record could not be written or read as one."""


# The name is the spec's (tests/test_missions.py, owner-approved): it says
# whose the verdict is not, which is the whole finding. N818 wants a suffix.
class VerdictNotTheGates(RecordError):  # noqa: N818
    """A verdict-shaped field appears where only the gate may write one."""


class OutputPathError(RecordError):
    """An output file's path would land outside ``output/``."""


class RecordDriftError(RecordError):
    """The human-readable copy says something ``task.json`` does not."""


class RecordExistsError(RecordError):
    """A record is already at this path; a run is not overwritten (ADR-0026 1)."""


@dataclass(frozen=True)
class MissionRecord:
    """One task's record, as read back. ``as_dict`` is ``task.json``'s shape."""

    identity: dict[str, Any]
    intent: dict[str, Any]
    spec: str
    output: dict[str, Any]
    written_at: str
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return _payload(
            identity=self.identity,
            intent=self.intent,
            spec=self.spec,
            output=self.output,
            written_at=self.written_at,
            extra=self.extra,
        )


def _payload(
    *,
    identity: Mapping[str, Any],
    intent: Mapping[str, Any],
    spec: str,
    output: Mapping[str, Any],
    written_at: str,
    extra: Mapping[str, Any],
) -> dict[str, Any]:
    """The record's shape, spine first so a reader sees ``record`` on line one."""
    for key in extra:
        if key in _SPINE:
            raise RecordError(
                f"extra names {key!r}, which is the record's own spine "
                f"({', '.join(_SPINE)}) and cannot be supplied twice"
            )
    return {
        "record": MISSION_RECORD,
        "identity": dict(identity),
        "intent": dict(intent),
        "spec": spec,
        "output": dict(output),
        "written_at": written_at,
        **dict(extra),
    }


def _walk(value: Any, at: str) -> Iterator[tuple[str, str]]:
    """Every key under ``value`` with its dotted path — nested, because a verdict
    two levels down under ``output.files`` is the same claim as one at the top."""
    if isinstance(value, dict):
        for key, inner in value.items():
            here = f"{at}.{key}" if at else str(key)
            yield here, str(key)
            yield from _walk(inner, here)
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            yield from _walk(inner, f"{at}[{index}]")


def foreign_verdicts(payload: Mapping[str, Any]) -> list[str]:
    """Every verdict-shaped path the gate did not write, in reading order.

    The record's own top level, then the whole ``output`` tree with
    ``output.gate`` skipped — the gate's block is the one place a pass/fail
    lives, and what the gate puts inside it is the gate's contract, not this
    module's.
    """
    found = [key for key in payload if str(key).lower() in VERDICT_SHAPED]
    output = payload.get("output")
    if isinstance(output, dict):
        for key, inner in output.items():
            if key == GATE:
                continue
            here = f"output.{key}"
            if str(key).lower() in VERDICT_SHAPED:
                found.append(here)
            found.extend(
                path
                for path, name in _walk(inner, here)
                if name.lower() in VERDICT_SHAPED
            )
    return found


def _refuse_foreign(payload: Mapping[str, Any], file: Path) -> None:
    foreign = foreign_verdicts(payload)
    if foreign:
        raise VerdictNotTheGates(
            f"{file}: {', '.join(repr(f) for f in foreign)} "
            f"{'is' if len(foreign) == 1 else 'are'} verdict-shaped and not the "
            f"gate's — a pass/fail lives only under output.{GATE}; judging the "
            "output against the spec is blind, at the month's review (#365)"
        )


def _output_path(root: Path, name: str) -> Path:
    """``output/<name>``, refused if it would land anywhere else."""
    rel = PurePosixPath(name)
    if not name or rel.is_absolute() or ".." in rel.parts or name.endswith("/"):
        raise OutputPathError(
            f"{name!r} is not a path under {root.name}/: an output file is named "
            "relative to the sandbox root, with no '..' and no leading '/'"
        )
    return root / Path(*rel.parts)


def write(
    where: Path,
    *,
    identity: Mapping[str, Any],
    intent: Mapping[str, Any],
    spec: str,
    output: Mapping[str, Any],
    extra: Mapping[str, Any] | None = None,
) -> Path:
    """Write one task's record under ``where`` and return ``where/task.json``.

    ``output["files"]`` maps sandbox-relative paths to text; each is also laid
    out as ``where/output/<path>``, bytes on disk, beside ``where/spec.md``.
    A record already at ``where`` is refused, not replaced.
    """
    task = where / TASK_FILE
    if task.exists():
        raise RecordExistsError(
            f"{task} already holds a record; a run is not overwritten"
        )
    payload = _payload(
        identity=identity,
        intent=intent,
        spec=spec,
        output=output,
        written_at=datetime.now(UTC).isoformat(timespec="seconds"),
        extra=extra or {},
    )
    _refuse_foreign(payload, task)
    files = _files(payload["output"], task)
    targets = {name: _output_path(where / OUTPUT_DIR, name) for name in files}

    where.mkdir(parents=True, exist_ok=True)
    (where / SPEC_FILE).write_text(spec, encoding="utf-8")
    for name, text in files.items():
        targets[name].parent.mkdir(parents=True, exist_ok=True)
        targets[name].write_bytes(text.encode("utf-8"))
    task.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return task


def _files(output: Mapping[str, Any], file: Path) -> dict[str, str]:
    """``output.files`` as path → text, or a refusal naming what it is instead."""
    files = output.get("files", {})
    if not isinstance(files, dict):
        raise RecordError(
            f"{file}: output.files is {type(files).__name__}, not a mapping of "
            "path to text"
        )
    for name, text in files.items():
        if not isinstance(name, str) or not isinstance(text, str):
            raise RecordError(
                f"{file}: output.files[{name!r}] is {type(text).__name__}; an "
                "output file is text under a path"
            )
    return dict(files)


def _load(task: Path) -> dict[str, Any]:
    if not task.is_file():
        raise RecordError(f"{task} does not exist: no record here")
    loaded = json.loads(task.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RecordError(f"{task}: a record is an object, not {type(loaded).__name__}")
    if loaded.get("record") != MISSION_RECORD:
        raise RecordError(
            f"{task}: record is {loaded.get('record')!r}, not {MISSION_RECORD!r}"
        )
    for key in _SPINE:
        if key not in loaded:
            raise RecordError(f"{task}: {key} is missing")
    for key in ("identity", "intent", "output"):
        if not isinstance(loaded[key], dict):
            raise RecordError(
                f"{task}: {key} is {type(loaded[key]).__name__}, not an object"
            )
    if not isinstance(loaded["spec"], str) or not isinstance(loaded["written_at"], str):
        raise RecordError(f"{task}: spec and written_at are strings")
    return loaded


def _refuse_drift(where: Path, payload: Mapping[str, Any]) -> None:
    """The person-readable copy must say what the record says."""
    task = where / TASK_FILE
    spec = where / SPEC_FILE
    if not spec.is_file():
        raise RecordDriftError(f"{spec} is missing beside {task.name}")
    if spec.read_text(encoding="utf-8") != payload["spec"]:
        raise RecordDriftError(f"{spec} differs from {task.name}'s spec")
    for name, text in _files(payload["output"], task).items():
        target = _output_path(where / OUTPUT_DIR, name)
        if not target.is_file():
            raise RecordDriftError(
                f"{target} is missing: {task.name} names output.files[{name!r}]"
            )
        if target.read_bytes() != text.encode("utf-8"):
            raise RecordDriftError(
                f"{target} differs from {task.name}'s output.files[{name!r}]"
            )


def read(where: Path) -> MissionRecord:
    """The record at ``where``, or a refusal naming what is wrong with it."""
    task = where / TASK_FILE
    payload = _load(task)
    _refuse_foreign(payload, task)
    _refuse_drift(where, payload)
    return MissionRecord(
        identity=payload["identity"],
        intent=payload["intent"],
        spec=payload["spec"],
        output=payload["output"],
        written_at=payload["written_at"],
        extra={k: v for k, v in payload.items() if k not in _SPINE},
    )
