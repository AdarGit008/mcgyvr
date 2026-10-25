"""Failure notes: the record a failed attempt leaves, and the climb that carries it.

One :class:`FailureNotes` per failed attempt, built after the fact from what was
observed, never from what a model said about it: the gate's findings and the
rungs it could not decide (:meth:`FailureNotes.of_gate`), a reviewer's refusal
and what the jev rung saw beside it (:meth:`FailureNotes.of_refusal`), or a
reply nothing could read (:meth:`FailureNotes.unreadable`). Each
:class:`FailureNote` in it is one observation of one check. A field a check did
not report as data stays ``None`` — a command, an exit, a test id or a symbol
is never parsed out of a sentence or guessed; a test id and a symbol come from
the test report the acceptance rung asks pytest for (:mod:`mcgyvr.gate.junit`).
A record crosses machines, so it
names nothing of the one it was made on: the gate gives a path under the
workspace a check ran in repo-relative, and a note, however it is built,
passes its message and command through :func:`mcgyvr.redact.scrub` and
:func:`mcgyvr.redact.scrub_paths` — any other absolute path becomes
``<redacted>`` — and keeps a path only when it is repo-relative.

A record names the rung and the attempt it is about, so it can travel: a climb
keeps the ordered history (:data:`ClimbNotes`), and :func:`handed_on` picks
what the next try is shown under the config's `retry_notes` — the whole climb,
this rung's previous attempt, or nothing. A record is never presented as an
attempt other than its own; :mod:`mcgyvr.worker.prompt` renders it under a
banner naming it, within the bounds that module states.

A record can also travel between runs of one contract: :func:`seeded` reads an
earlier run's result file into :class:`CarriedNotes`, each stamped with the run
it was made in and refused when it is not a sound record of that contract, and
:func:`primed` opens a climb with them under `retry_notes: climb`
(`mcgyvr run --notes-from`).

The fields are declared once, as :class:`mcgyvr.schema.Field` tuples
(:data:`NOTE_FIELDS`, :data:`NOTES_FIELDS`): :meth:`FailureNotes.as_json` and
:meth:`FailureNotes.from_json` walk them, and :func:`json_schema` renders the
JSON Schema that `make docs` writes to
``skills/mcgyvr/references/failure-notes.schema.json``. Model-facing text is
rendered from the record (:meth:`FailureNote.for_model`,
:attr:`FailureNotes.lines`), never the other way round.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any

from mcgyvr.config import RETRY_NOTES_CHOICES
from mcgyvr.redact import scrub, scrub_paths
from mcgyvr.schema import Dialect, Field, walk_block

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.gate import GateResult
    from mcgyvr.gate.findings import Finding
    from mcgyvr.gate.runner import InconclusiveRung

#: The record's schema name and version, written into every record so a reader
#: can refuse one it does not know.
SCHEMA_ID = "mcgyvr.failure_notes/1"

#: The check an unreadable reply is filed under: no gate check ran, the reply
#: parser refused what came back.
REPLY_CHECK = "reply"

#: The check a reviewer's refusal is filed under.
VERIFIER_CHECK = "verifier"


class NotesError(ValueError):
    """A failure-notes document this module will not read."""


class NoteKind(StrEnum):
    """What one note observed.

    `finding` is a check that rejected the change, `inconclusive` a rung that
    ran and could not decide, `refusal` a reviewer that refused a change the
    gate passed, and `unreadable` a reply nothing could gate.
    """

    FINDING = "finding"
    INCONCLUSIVE = "inconclusive"
    REFUSAL = "refusal"
    UNREADABLE = "unreadable"


NOTE_FIELDS: tuple[Field, ...] = (
    Field(
        "check",
        "str",
        "The check that raised it, as the gate names it: `lint`, `format`, "
        "`syntax`, `structure`, `typecheck`, `semantic`, `acceptance`, `scope`, "
        "`secret`, `structured-data`, `jev`, `verifier`, `reply`, ...",
        required=True,
    ),
    Field(
        "kind",
        "enum",
        "`finding`: the check rejected the change. `inconclusive`: the rung "
        "ran and could not decide. `refusal`: a reviewer refused a change the "
        "gate passed. `unreadable`: the reply could not be read, so nothing "
        "was gated.",
        required=True,
        choices=tuple(kind.value for kind in NoteKind),
    ),
    Field(
        "message",
        "str",
        "The check's own sentence. A path in the repository is repo-relative; "
        "any other absolute path, and the userinfo of any URL, is replaced by "
        "`<redacted>`.",
        required=True,
    ),
    Field(
        "path",
        "str",
        "The repo-relative file the note is about; null when the check keyed "
        "it by something that is not a file, such as an acceptance command, or "
        "named a file outside the repository.",
    ),
    Field(
        "line",
        "int",
        "The line in `path` the check placed it on; for a failing test, the "
        "line its definition starts on.",
    ),
    Field(
        "code",
        "str",
        "The check's own code for the kind of problem (`F401`, `E501`, mypy's "
        "`attr-defined`, ...). The acceptance rung's: `failed` for a failing "
        "test, or a failing command that named no test; `error` for a test "
        "whose fixture raised around it; `collection-error` for a test module "
        "that could not be collected — each prefixed `demonstration-` for a "
        "demonstrating command — and `timeout` and `tree-altering` for the "
        "command itself.",
    ),
    Field(
        "command",
        "str",
        "The command the check ran, when it ran one (acceptance, typecheck), "
        "shell-quoted, its paths treated as in `message`.",
    ),
    Field(
        "exit_code",
        "int",
        "That command's exit, or the exit of the tool an inconclusive rung "
        "ran; null when it was killed at the time limit or never ran.",
    ),
    Field(
        "test_id",
        "str",
        "The failing test's id (pytest's node id, `path::Class::test[param]`) "
        "when the check reports one as data: read from the JUnit XML report "
        "the acceptance rung asks pytest for, never out of a command's output.",
    ),
    Field(
        "symbol",
        "str",
        "The missing or undefined name, when the check reports it as data: "
        "the semantic rung's missing attribute, or the name in a test "
        "report's NameError, ImportError, ModuleNotFoundError or "
        "AttributeError, read only from the interpreter's fixed wording of "
        "that exception.",
    ),
)

NOTES_FIELDS: tuple[Field, ...] = (
    Field(
        "schema",
        "enum",
        "The record's schema name and version.",
        required=True,
        choices=(SCHEMA_ID,),
    ),
    Field("rung", "str", "The rung the failed attempt ran on.", required=True),
    Field(
        "family",
        "str",
        "That rung's family: `deterministic`, `local` or `api`.",
        required=True,
    ),
    Field(
        "attempt",
        "int",
        "The attempt's number on that rung, from 1.",
        required=True,
        min_value=1,
    ),
    Field(
        "checks",
        "str_list",
        "The checks that failed, in the order they ran.",
        required=True,
    ),
    Field(
        "notes",
        "block_list",
        "One entry per observation, in the order the checks reported them.",
        required=True,
        block=NOTE_FIELDS,
    ),
)


@dataclass(frozen=True)
class FailureNote:
    """One observation of one check, with only what the check reported as data."""

    check: str
    kind: NoteKind
    message: str
    path: str | None = None
    line: int | None = None
    code: str | None = None
    command: str | None = None
    exit_code: int | None = None
    test_id: str | None = None
    symbol: str | None = None

    def __post_init__(self) -> None:
        """Hold the note to what may leave this machine, however it was built.

        A builder, a test or :meth:`FailureNotes.from_json` all land here, so a
        note never carries a URL's userinfo or a host path: the message and the
        command keep their relative paths and lose every absolute one, and a
        path that is not repo-relative is dropped. The gate has already made a
        workspace path relative, so what is lost here is only what no reader on
        another machine could use.
        """
        object.__setattr__(self, "message", _safe(self.message))
        if self.command is not None:
            object.__setattr__(self, "command", _safe(self.command))
        if self.path is not None:
            object.__setattr__(self, "path", _repo_relative(self.path))

    @classmethod
    def of_finding(cls, finding: Finding) -> FailureNote:
        """The note for one gate finding, carrying the fields the check filled in.

        The path is dropped when the finding is keyed by something that is not a
        file — an acceptance command's label — because the record's `path` is a
        file in the repository and nothing else.
        """
        return cls(
            check=finding.check,
            kind=NoteKind.FINDING,
            message=scrub(finding.message),
            path=_repo_relative(finding.path) if finding.names_a_file else None,
            line=finding.line,
            code=finding.code,
            command=scrub(finding.command) if finding.command is not None else None,
            exit_code=finding.exit_code,
            test_id=_safe(finding.test_id) if finding.test_id is not None else None,
            symbol=finding.symbol,
        )

    @classmethod
    def of_inconclusive(cls, rung: InconclusiveRung) -> FailureNote:
        """The note for a rung that ran and could not decide: its rung and exit."""
        return cls(
            check=rung.rung,
            kind=NoteKind.INCONCLUSIVE,
            message=scrub(str(rung)),
            exit_code=rung.exit_code,
        )

    def for_model(self) -> str:
        """The line a model reads: where, the check and its code, the message.

        It is the gate's own one-line form of a finding — `path:line: check
        [code]: message`, with the position left out when the note names no
        file — so a worker reads the same sentence whether it came from a
        finding or from a record handed across rungs. The other kinds read
        the same way: their check (`verifier`, `reply`) or their message (an
        inconclusive rung's says so) already names what they are.
        """
        code = f" [{self.code}]" if self.code else ""
        said = f"{self.check}{code}: {self.message}"
        if self.path is None:
            return said
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{where}: {said}"


@dataclass(frozen=True)
class FailureNotes:
    """The record of one failed attempt: where it ran and what was observed."""

    rung: str
    family: str
    attempt: int
    checks: tuple[str, ...]
    notes: tuple[FailureNote, ...]
    #: Always :data:`SCHEMA_ID`; held as a field so the record walks its own
    #: :data:`NOTES_FIELDS` and writes the version it was built at.
    schema: str = field(default=SCHEMA_ID, init=False)

    @classmethod
    def of_gate(
        cls, gate: GateResult, *, rung: str, family: str, attempt: int
    ) -> FailureNotes | None:
        """The record of a gate that rejected a change, or None if it did not.

        Its findings, then the rungs that could not decide — both reject a
        change. Observations and environment issues are what the gate said
        without refusing, and a retry told to fix them would be fixing
        something that was never held against it, so they are not here.
        """
        if gate.accepted:
            return None
        notes = (
            *(FailureNote.of_finding(f) for f in gate.findings),
            *(FailureNote.of_inconclusive(r) for r in gate.inconclusive),
        )
        return cls(
            rung=rung,
            family=family,
            attempt=attempt,
            checks=_checks(notes),
            notes=notes,
        )

    @classmethod
    def of_refusal(
        cls,
        detail: str,
        gate: GateResult,
        *,
        rung: str,
        family: str,
        attempt: int,
    ) -> FailureNotes:
        """The record of a change the gate passed and a reviewer refused.

        The reviewer's sentence comes first, then whatever the non-blocking jev
        rung saw, as findings and observations. `jev` is named only when that
        rung saw something, so a refusal with no detail claims no more of it
        than it has.
        """
        seen = () if gate.jev is None else (*gate.jev.findings, *gate.jev.observations)
        notes = (
            FailureNote(
                check=VERIFIER_CHECK, kind=NoteKind.REFUSAL, message=scrub(detail)
            ),
            *(FailureNote.of_finding(f) for f in seen),
        )
        return cls(
            rung=rung,
            family=family,
            attempt=attempt,
            checks=_checks(notes),
            notes=notes,
        )

    @classmethod
    def unreadable(
        cls, reason: str, *, rung: str, family: str, attempt: int
    ) -> FailureNotes:
        """The record of an attempt whose every reply could not be read.

        Nothing was gated, so there is no check's finding to repeat: the one
        note is the reply parser's own sentence about what came back, which is
        what the attempt was refused for and what the next try can act on.
        """
        note = FailureNote(
            check=REPLY_CHECK, kind=NoteKind.UNREADABLE, message=scrub(reason)
        )
        return cls(
            rung=rung,
            family=family,
            attempt=attempt,
            checks=(REPLY_CHECK,),
            notes=(note,),
        )

    @property
    def lines(self) -> tuple[str, ...]:
        """One model-facing line per note, in the record's order."""
        return tuple(note.for_model() for note in self.notes)

    @property
    def findings(self) -> tuple[str, ...]:
        """The lines a gate or a reviewer held against the change.

        What a result's `findings` carries: every note but an unreadable
        reply's, which no check judged — its sentence is the attempt's detail.
        """
        return tuple(
            note.for_model()
            for note in self.notes
            if note.kind is not NoteKind.UNREADABLE
        )

    @property
    def text(self) -> str:
        """Every line as a bullet list."""
        return "\n".join(f"- {line}" for line in self.lines)

    @property
    def headline(self) -> str:
        """The banner the record is rendered under, naming the attempt it is about.

        It says what happened to that attempt and nothing about any other: a
        gate's rejection, a reviewer's refusal of a change the gate passed, or a
        reply that could not be read and so was never gated.
        """
        kinds = {note.kind for note in self.notes}
        where = f"ATTEMPT {self.attempt} ON {self.rung}"
        if kinds == {NoteKind.UNREADABLE}:
            return (
                f"THE REPLY TO {where} COULD NOT BE READ, SO NOTHING WAS GATED. "
                f"Reply exactly as the OUTPUT rule says:"
            )
        if NoteKind.REFUSAL in kinds:
            return (
                f"{where} PASSED THE GATE AND WAS REFUSED BY THE REVIEWER. Fix "
                f"exactly these and change nothing else:"
            )
        return (
            f"{where} WAS REJECTED BY THE GATE. Fix exactly these and change "
            f"nothing else — every other check passed:"
        )

    @property
    def summary(self) -> str:
        """The record in one line: `<rung> #<attempt> — check (count), ...`."""
        counts = Counter(note.check for note in self.notes)
        named = ", ".join(f"{check} ({counts[check]})" for check in self.checks)
        return f"{self.rung} #{self.attempt} — {named}"

    def as_json(self) -> dict[str, Any]:
        """The record as JSON-ready data, walked from :data:`NOTES_FIELDS`."""
        return _dump(self, NOTES_FIELDS)

    @classmethod
    def from_json(cls, data: object) -> FailureNotes:
        """Read a record written by :meth:`as_json`, refusing anything else.

        The document is walked against :data:`NOTES_FIELDS` with the schema
        walk setup files and contracts are read with: an unknown key, a missing
        required one, a value of the wrong kind and another schema version are
        all refused by name.
        """
        read = walk_block(data, NOTES_FIELDS, "", _DIALECT)
        return cls(
            rung=read["rung"],
            family=read["family"],
            attempt=read["attempt"],
            checks=read["checks"],
            notes=tuple(
                FailureNote(**{**note, "kind": NoteKind(note["kind"])})
                for note in read["notes"]
            ),
        )


#: A climb's history of records, oldest first: what the next try is handed.
ClimbNotes = tuple[FailureNotes, ...]


def handed_on(
    climb: Sequence[FailureNotes], mode: str, *, rung: str, attempt: int
) -> ClimbNotes:
    """The records the try at `attempt` on `rung` is shown, under `retry_notes`.

    `climb` hands on every record of the climb, oldest first, so a rung above
    starts with what the rungs below it were refused for. `rung` hands on only
    the record of the attempt just before this one on this rung — what a
    second attempt was told before records travelled — and nothing to a
    rung's first attempt or after an attempt that left no record. `none`
    hands on nothing.
    """
    if mode not in RETRY_NOTES_CHOICES:
        raise ValueError(
            f"retry_notes {mode!r} is not one of {', '.join(RETRY_NOTES_CHOICES)}"
        )
    if mode == "none" or not climb:
        return ()
    if mode == "rung":
        last = climb[-1]
        return (last,) if last.rung == rung and last.attempt == attempt - 1 else ()
    return tuple(climb)


def json_schema() -> dict[str, Any]:
    """The JSON Schema (draft 2020-12) of one record, rendered from the fields."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "mcgyvr failure notes",
        "description": (
            f"{SCHEMA_ID}: the record of one failed attempt, built from what the "
            f"gate, the reviewer or the reply parser observed. Generated from "
            f"src/mcgyvr/notes.py by `make docs`; do not edit."
        ),
        "$ref": "#/$defs/FailureNotes",
        "$defs": {
            "FailureNotes": _object_schema(NOTES_FIELDS, "#/$defs/FailureNote"),
            "FailureNote": _object_schema(NOTE_FIELDS, None),
        },
    }


# --- the walk both directions share ------------------------------------------


def _checks(notes: Sequence[FailureNote]) -> tuple[str, ...]:
    """Each check the notes name, once, in the order they first name it."""
    return tuple(dict.fromkeys(note.check for note in notes))


def _repo_relative(path: str) -> str | None:
    """`path` when it is a path in the repository, else None: a record never
    names a host path, a home-relative one or one that climbs out of the repo."""
    within = PurePosixPath(path)
    if within.is_absolute() or path.startswith("~") or ".." in within.parts:
        return None
    return path


def _safe(text: str) -> str:
    """`text` without a URL's userinfo or an absolute path in it."""
    return scrub_paths(scrub(text))


def _dump(obj: object, fields: tuple[Field, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in fields:
        value = getattr(obj, spec.name)
        if spec.kind == "block_list":
            value = [_dump(item, spec.block) for item in value]
        elif spec.kind == "str_list":
            value = list(value)
        elif isinstance(value, StrEnum):
            value = value.value
        out[spec.name] = value
    return out


def _mapping(raw: object, path: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping) or not all(isinstance(k, str) for k in raw):
        raise NotesError(
            f"{path or 'failure notes'}: expected an object with text keys"
        )
    return raw


def _value(raw: object, spec: Field, path: str) -> Any:
    if spec.kind == "str":
        if not isinstance(raw, str):
            raise NotesError(f"{path}: expected text, got {type(raw).__name__}")
        return raw
    if spec.kind == "int":
        if not isinstance(raw, int) or isinstance(raw, bool):
            raise NotesError(f"{path}: expected a whole number, got {raw!r}")
        if spec.min_value is not None and raw < spec.min_value:
            raise NotesError(f"{path}: {raw} is below {spec.min_value:g}")
        return raw
    if spec.kind == "enum":
        if raw not in spec.valid_choices():
            raise NotesError(
                f"{path}: {raw!r} is not one of {', '.join(spec.valid_choices())}"
            )
        return raw
    if spec.kind == "str_list":
        if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
            raise NotesError(f"{path}: expected a list of text")
        return tuple(raw)
    if spec.kind == "block_list":
        if not isinstance(raw, list):
            raise NotesError(f"{path}: expected a list")
        return tuple(
            walk_block(item, spec.block, f"{path}[{index}]", _DIALECT)
            for index, item in enumerate(raw)
        )
    raise NotesError(f"{path}: kind {spec.kind!r} is not read here")  # pragma: no cover


def _missing(spec: Field, path: str) -> Exception:
    return NotesError(f"{path}: required key missing — {spec.doc}")


_DIALECT = Dialect(
    noun="failure notes",
    error=NotesError,
    mapping=_mapping,
    value=_value,
    missing=_missing,
    default_for=lambda spec: spec.default,
)


def _field_schema(spec: Field, items: str | None) -> dict[str, Any]:
    if spec.kind == "enum":
        choices = list(spec.valid_choices())
        return {"const": choices[0]} if len(choices) == 1 else {"enum": choices}
    if spec.kind == "str_list":
        return {"type": "array", "items": {"type": "string"}}
    if spec.kind == "block_list":
        assert items is not None, f"{spec.name}: a block list needs its items"
        return {"type": "array", "items": {"$ref": items}}
    typed: dict[str, Any] = {"type": "integer" if spec.kind == "int" else "string"}
    if spec.min_value is not None:
        typed["minimum"] = int(spec.min_value)
    return typed


def _object_schema(fields: tuple[Field, ...], items: str | None) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for spec in fields:
        shape = _field_schema(spec, items)
        if not spec.required:
            shape = {"anyOf": [shape, {"type": "null"}]}
        properties[spec.name] = {"description": spec.doc, **shape}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [spec.name for spec in fields if spec.required],
        "properties": properties,
    }


# --- notes handed in from an earlier run --------------------------------------

#: The most bytes a seed file may hold. A result file is a few kilobytes per
#: attempt; one this size is not a result, and it is refused before it is read.
MAX_SEED_BYTES = 1 << 20


@dataclass(frozen=True)
class CarriedNotes(FailureNotes):
    """A record handed in from an earlier run of the same contract.

    The record itself is the schema's, unchanged — :meth:`as_json` writes the
    same `mcgyvr.failure_notes/1` document — and `run` travels beside it: the
    stamp of the run it was made in, or empty when the source did not name one.
    Its banner and its summary say so, so a seeded record is never presented
    as an attempt of the run that reads it.
    """

    run: str = ""

    @classmethod
    def of(cls, record: FailureNotes, run: str) -> CarriedNotes:
        """`record`, stamped as made in `run`."""
        return cls(
            rung=record.rung,
            family=record.family,
            attempt=record.attempt,
            checks=record.checks,
            notes=record.notes,
            run=run,
        )

    @property
    def origin(self) -> str:
        """`AN EARLIER RUN`, with its stamp when the source named one."""
        return f"AN EARLIER RUN ({self.run})" if self.run else "AN EARLIER RUN"

    @property
    def headline(self) -> str:
        """The record's own banner, under the earlier run it belongs to."""
        return f"IN {self.origin}, NOT THIS ONE: {super().headline}"

    @property
    def summary(self) -> str:
        """The record's one line, naming the earlier run first."""
        earlier = f"earlier run {self.run}" if self.run else "earlier run"
        return f"{earlier}: {super().summary}"

    def carried_json(self) -> dict[str, Any]:
        """The record and its run, as a result file's `seeded.records` holds it."""
        return {"run": self.run, "notes": self.as_json()}


def seeded(
    source: Mapping[str, Any] | Sequence[Any] | Path, *, contract: str
) -> tuple[CarriedNotes, ...]:
    """The failure notes an earlier run of `contract` leaves for a run of it now.

    `source` is that run's result file (`mcgyvr.result.RunResult`), its parsed
    JSON, or a bare list of `mcgyvr.failure_notes/1` records. From a result, the
    records an earlier seed handed it come first (`seeded.records`, each with
    its own run), then the records of its own failed attempts, stamped with its
    `run`; a bare list names no run and no contract, so its caller vouches for
    both. Only the latest records a prompt shows are kept
    (:data:`mcgyvr.worker.prompt.MAX_RECORDS_SHOWN`).

    What is read is untrusted, so every record is walked through
    :meth:`FailureNotes.from_json` and each note's path must name a file in the
    repository; messages and commands are scrubbed again. A file larger than
    :data:`MAX_SEED_BYTES`, one that cannot be read or is not JSON, a result of
    another contract and an unsound record are each a :class:`NotesError`.
    """
    from mcgyvr.worker.prompt import MAX_RECORDS_SHOWN

    data = _seed_file(source) if isinstance(source, Path) else source
    if isinstance(data, Mapping):
        found = _of_result(data, contract)
    elif isinstance(data, Sequence) and not isinstance(data, str | bytes):
        found = [
            (_sound(record, f"records[{index}]"), "")
            for index, record in enumerate(data)
        ]
    else:
        raise NotesError(
            f"the seed is neither a result nor a list of records: {type(data).__name__}"
        )
    return tuple(
        CarriedNotes.of(record, run) for record, run in found[-MAX_RECORDS_SHOWN:]
    )


def primed(seed: Sequence[FailureNotes], mode: str) -> list[FailureNotes]:
    """The climb a driver starts with: `seed`, under `retry_notes: climb` only.

    `climb` hands on every record of the climb, so a seed is the start of it.
    `rung` hands on the attempt just before this one on this rung, which an
    earlier run's record never is, and `none` hands on nothing — under either,
    the climb starts empty.
    """
    if mode not in RETRY_NOTES_CHOICES:
        raise ValueError(
            f"retry_notes {mode!r} is not one of {', '.join(RETRY_NOTES_CHOICES)}"
        )
    return list(seed) if mode == "climb" else []


def _seed_file(path: Path) -> object:
    """The JSON in the seed file at `path`, refused by name when it is no use."""
    try:
        size = path.stat().st_size
        if size > MAX_SEED_BYTES:
            raise NotesError(
                f"{path} is larger than {MAX_SEED_BYTES} bytes ({size}); a "
                f"result file is not"
            )
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise NotesError(f"{path} cannot be read: {exc}") from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        raise NotesError(f"{path} is not JSON: {exc}") from exc


def _of_result(
    result: Mapping[str, Any], contract: str
) -> list[tuple[FailureNotes, str]]:
    """A result's records with their runs: its seed's, then its own attempts'."""
    named = result.get("contract")
    if named != contract:
        raise NotesError(
            f"the seed is the result of contract {named!r}, not {contract!r}: "
            f"a run is handed only the notes of its own contract"
        )
    run = result.get("run")
    if not isinstance(run, str):
        raise NotesError(f"the seed's `run` is not a run stamp: {run!r}")
    found: list[tuple[FailureNotes, str]] = []
    carried = result.get("seeded") or {}
    earlier = carried.get("records", []) if isinstance(carried, Mapping) else None
    if not isinstance(earlier, list):
        raise NotesError("the seed's `seeded.records` is not a list")
    for index, entry in enumerate(earlier):
        where = f"seeded.records[{index}]"
        if not isinstance(entry, Mapping) or not isinstance(entry.get("run"), str):
            raise NotesError(f"{where}: expected an object with a text `run`")
        found.append((_sound(entry.get("notes"), f"{where}.notes"), entry["run"]))
    attempts = result.get("attempts", [])
    if not isinstance(attempts, list):
        raise NotesError("the seed's `attempts` is not a list")
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, Mapping):
            raise NotesError(f"attempts[{index}]: expected an object")
        if attempt.get("notes") is not None:
            found.append((_sound(attempt["notes"], f"attempts[{index}].notes"), run))
    return found


def _sound(raw: object, where: str) -> FailureNotes:
    """One record read from a seed: its paths in the repo, walked, scrubbed.

    A note's path is checked as written, before the record is built, so one
    that is absolute or climbs out of the repository refuses the seed rather
    than being quietly dropped from it.
    """
    listed = raw.get("notes") if isinstance(raw, Mapping) else None
    for index, note in enumerate(listed if isinstance(listed, list) else ()):
        path = note.get("path") if isinstance(note, Mapping) else None
        if isinstance(path, str):
            _in_repo(path, f"{where}.notes[{index}].path")
    try:
        record = FailureNotes.from_json(raw)
    except NotesError as exc:
        raise NotesError(f"{where}: {exc}") from exc
    notes = tuple(
        replace(
            note,
            message=scrub(note.message),
            command=scrub(note.command) if note.command is not None else None,
        )
        for note in record.notes
    )
    return replace(record, notes=notes)


def _in_repo(path: str, where: str) -> None:
    """Refuse a note path that is not a file inside the repository."""
    if not path:
        raise NotesError(f"{where}: an empty path names no file")
    posix = PurePosixPath(path.replace("\\", "/"))
    if posix.is_absolute() or path.startswith("~") or PureWindowsPath(path).drive:
        raise NotesError(f"{where}: {path!r} is absolute, not repo-relative")
    if ".." in posix.parts:
        raise NotesError(f"{where}: {path!r} reaches outside the repository")
