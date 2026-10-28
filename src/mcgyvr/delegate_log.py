"""What `mcgyvr PROMPT --log PATH` came to, as one record a script can read.

`mcgyvr PROMPT` and `mcgyvr direct` say how they ended in English on stderr, and the
exit code folds a dozen different failures into 1. A caller that has to act on *which*
one happened — a harness, a script, a shell loop — passes `--log PATH` and
reads a `DelegateLog` there instead of parsing prose. The record is written on
every way the command ends once its arguments are read, success, refusal and a
crash alike, through :mod:`mcgyvr.atomic`, so a reader sees the whole file or
none. It is opt-in, so stderr and stdout are unchanged by it.

Its reader is the process that ran `mcgyvr PROMPT` or `mcgyvr direct`. It is
not part of the /mcgyvr skill and is not rendered under `skills/`: the session
agent neither defines nor reads it. `json_schema` is its one schema, and a
reader imports this module (`read`, `DelegateKind`) rather than copying either.

The schema id is `mcgyvr.delegate_log/1`. Every way the command can end is one
`kind`; the prefix is the group. Within `/1` new kinds may be added, so a
reader must tolerate a kind it does not know (`read` returns it as a plain
string); renaming or removing a kind, or changing a field, is `/2`.

======================== ==== =================================================
kind                     exit when
======================== ==== =================================================
config_invalid           1    the config named or found does not load
config_missing           1    the setup named (`--config`, the environment) is
                              not there
config_no_orchestrator   3    no orchestrator role: a bare install, or a config
                              that binds none
use_case_raw             3    the config's use case serves its model raw
                              (`code`, `chat`, `agent`): nothing is proposed
orchestrator_unrunnable  1    the role is declared but its unit cannot run
orchestrator_unavailable 1    the role resolves to no unit to dispatch to
orchestrator_dispatch_   1    the role's unit was asked and the dispatch failed
failed
source_unavailable       1    a model source the dispatch needs is unusable
repo_attach_failed       1    `--repo` could not be attached (checkout or clone)
repo_index_failed        1    the repository could not be indexed
reply_cut_off            1    the role's reply stopped at a length limit
reply_not_json           1    the reply holds no JSON value
reply_not_array          1    the reply's JSON is not an array of proposals
proposal_not_object      1    a proposal entry is not an object
proposal_field_missing   1    a proposal lacks a required field
proposal_field_invalid   1    a proposal field has the wrong type or shape
session_unresolved       2    `--run` and no session to file the runs under;
                              the role was not asked
usage_invalid            2    a combination of flags refused once parsed
                              (`--branch` with `--no-commit`, an empty name)
emitted                  0    contracts, no refusals
emitted_with_refusals    0    contracts, and some proposals refused
none_emitted             3    the request was read and no contract came of it
batch_held               3    `--run` held contracts whose provider did not
                              land; they were never sent
internal_error           1    an exception nothing above names: a crash
======================== ==== =================================================

`exit_code` is what the process returned. For `emitted` and
`emitted_with_refusals` under `--run` it is the batch's: the last non-zero exit
of its runs, or 0. Precedence when more than one applies: the first failure
ends the command, so a failure kind is the only kind; with `--run`,
`session_unresolved` comes first, then `batch_held`, then what the
decomposition came to. Per-contract outcomes stay in their own run result
files and in the Board's state file, which `batch_held` names; this record
does not copy them.

`detail` holds kind-specific facts the product already has as data, every key
optional: `path` for `config_*`, and `bare_install` for
`config_no_orchestrator`; `use_case` for `use_case_raw`; `error_class` for
`orchestrator_unrunnable`,
`orchestrator_dispatch_failed`, `source_unavailable` and `internal_error`;
`repo` for `repo_*`; `unit`, `output_tokens`, `reasoning_tokens`,
`max_output_tokens` and `cap_basis` for `reply_cut_off`; `decoder`, `line`,
`column`, `pos` and `body_chars` for `reply_not_json`; `found` (a JSON type
name) for `reply_not_array`; `index`, `field` and `found` for `proposal_*`;
`raw_reply_chars` for every `reply_*` and `proposal_*`; `held` (contract ids)
and `tree_state` (the Board's state file, `<journal>/trees/<tree>.json`) for
`batch_held`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from mcgyvr import atomic
from mcgyvr.exits import Exit

#: The record's schema name and version, written as its `schema` key.
SCHEMA_ID = "mcgyvr.delegate_log/1"


class DelegateKind(StrEnum):
    """Every way `mcgyvr PROMPT` is known to end, one value per exit path."""

    CONFIG_INVALID = "config_invalid"
    CONFIG_MISSING = "config_missing"
    CONFIG_NO_ORCHESTRATOR = "config_no_orchestrator"
    USE_CASE_RAW = "use_case_raw"
    ORCHESTRATOR_UNRUNNABLE = "orchestrator_unrunnable"
    ORCHESTRATOR_UNAVAILABLE = "orchestrator_unavailable"
    ORCHESTRATOR_DISPATCH_FAILED = "orchestrator_dispatch_failed"
    SOURCE_UNAVAILABLE = "source_unavailable"
    REPO_ATTACH_FAILED = "repo_attach_failed"
    REPO_INDEX_FAILED = "repo_index_failed"
    REPLY_CUT_OFF = "reply_cut_off"
    REPLY_NOT_JSON = "reply_not_json"
    REPLY_NOT_ARRAY = "reply_not_array"
    PROPOSAL_NOT_OBJECT = "proposal_not_object"
    PROPOSAL_FIELD_MISSING = "proposal_field_missing"
    PROPOSAL_FIELD_INVALID = "proposal_field_invalid"
    SESSION_UNRESOLVED = "session_unresolved"
    USAGE_INVALID = "usage_invalid"
    EMITTED = "emitted"
    EMITTED_WITH_REFUSALS = "emitted_with_refusals"
    NONE_EMITTED = "none_emitted"
    BATCH_HELD = "batch_held"
    INTERNAL_ERROR = "internal_error"


#: The exit code each kind ends with (see the table above; `emitted*` under
#: `--run` carry the batch's instead).
KIND_EXIT: Mapping[DelegateKind, Exit] = {
    DelegateKind.CONFIG_INVALID: Exit.ERROR,
    DelegateKind.CONFIG_MISSING: Exit.ERROR,
    DelegateKind.CONFIG_NO_ORCHESTRATOR: Exit.REFUSED,
    DelegateKind.USE_CASE_RAW: Exit.REFUSED,
    DelegateKind.ORCHESTRATOR_UNRUNNABLE: Exit.ERROR,
    DelegateKind.ORCHESTRATOR_UNAVAILABLE: Exit.ERROR,
    DelegateKind.ORCHESTRATOR_DISPATCH_FAILED: Exit.ERROR,
    DelegateKind.SOURCE_UNAVAILABLE: Exit.ERROR,
    DelegateKind.REPO_ATTACH_FAILED: Exit.ERROR,
    DelegateKind.REPO_INDEX_FAILED: Exit.ERROR,
    DelegateKind.REPLY_CUT_OFF: Exit.ERROR,
    DelegateKind.REPLY_NOT_JSON: Exit.ERROR,
    DelegateKind.REPLY_NOT_ARRAY: Exit.ERROR,
    DelegateKind.PROPOSAL_NOT_OBJECT: Exit.ERROR,
    DelegateKind.PROPOSAL_FIELD_MISSING: Exit.ERROR,
    DelegateKind.PROPOSAL_FIELD_INVALID: Exit.ERROR,
    DelegateKind.SESSION_UNRESOLVED: Exit.USAGE,
    DelegateKind.USAGE_INVALID: Exit.USAGE,
    DelegateKind.EMITTED: Exit.OK,
    DelegateKind.EMITTED_WITH_REFUSALS: Exit.OK,
    DelegateKind.NONE_EMITTED: Exit.REFUSED,
    DelegateKind.BATCH_HELD: Exit.REFUSED,
    DelegateKind.INTERNAL_ERROR: Exit.ERROR,
}

#: The kinds that mean the request was decomposed: the orchestrator answered
#: and its reply was read. Every other kind, a kind this build does not know
#: included, ended the command before that.
DECOMPOSED: frozenset[DelegateKind] = frozenset(
    {
        DelegateKind.EMITTED,
        DelegateKind.EMITTED_WITH_REFUSALS,
        DelegateKind.NONE_EMITTED,
        DelegateKind.BATCH_HELD,
    }
)


class DelegateLogError(ValueError):
    """A file that is not a `mcgyvr.delegate_log/1` record."""


@dataclass(frozen=True)
class LoggedContract:
    """One contract the decomposition emitted, and where `--output` wrote it."""

    id: str
    task_type: str
    target: str
    #: Where `--output` wrote it; None when it was printed to stdout.
    path: str | None = None


@dataclass(frozen=True)
class LoggedRefusal:
    """One refusal of the decomposition, as `Refusal` holds it."""

    subject: str
    reason: str
    #: A proposal field; `request` = the whole request; empty = catch-all.
    field: str = ""
    what_to_change: str = ""


@dataclass(frozen=True)
class DelegateLog:
    """One `mcgyvr PROMPT` run's ending, the shape the `--log` file holds."""

    #: What it came to: a `DelegateKind`, or the plain string of a kind this
    #: build does not know, read from a newer writer's file.
    kind: DelegateKind | str
    #: For a failure, the sentence stderr carries after `error: `, verbatim;
    #: otherwise a one-line account of what was emitted or held.
    message: str
    #: What the process returned, an `mcgyvr.exits.Exit` value.
    exit_code: int
    #: True when the orchestrator's raw reply was printed on stderr.
    raw_reply_present: bool = False
    contracts: tuple[LoggedContract, ...] = ()
    refusals: tuple[LoggedRefusal, ...] = ()
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def known(self) -> bool:
        """Whether `kind` is one this build knows."""
        return isinstance(self.kind, DelegateKind)

    def as_json(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_ID,
            "kind": str(self.kind),
            "message": self.message,
            "exit_code": int(self.exit_code),
            "raw_reply_present": self.raw_reply_present,
            "contracts": [
                {
                    "id": c.id,
                    "task_type": c.task_type,
                    "target": c.target,
                    "path": c.path,
                }
                for c in self.contracts
            ],
            "refusals": [
                {
                    "subject": r.subject,
                    "reason": r.reason,
                    "field": r.field,
                    "what_to_change": r.what_to_change,
                }
                for r in self.refusals
            ],
            "detail": dict(self.detail),
        }

    @classmethod
    def from_json(cls, data: object) -> DelegateLog:
        """Read a record; another schema id, or a record that is not one, refused.

        A `kind` this build does not know is kept as its string (see the module
        note on growing kinds); everything else must have the shape `/1` gives.
        """
        if not isinstance(data, dict):
            raise DelegateLogError(
                f"a delegate log is an object, not {json_type(data)}"
            )
        if data.get("schema") != SCHEMA_ID:
            raise DelegateLogError(
                f"this reads {SCHEMA_ID} records, and the file says "
                f"{data.get('schema')!r}"
            )
        try:
            kind_text = _of(data, "kind", str)
            kind: DelegateKind | str = (
                DelegateKind(kind_text)
                if kind_text in DelegateKind._value2member_map_
                else kind_text
            )
            return cls(
                kind=kind,
                message=_of(data, "message", str),
                exit_code=_of(data, "exit_code", int),
                raw_reply_present=_of(data, "raw_reply_present", bool),
                contracts=tuple(
                    LoggedContract(
                        id=_of(c, "id", str),
                        task_type=_of(c, "task_type", str),
                        target=_of(c, "target", str),
                        path=_of(c, "path", (str, type(None))),
                    )
                    for c in _of(data, "contracts", list)
                ),
                refusals=tuple(
                    LoggedRefusal(
                        subject=_of(r, "subject", str),
                        reason=_of(r, "reason", str),
                        field=_of(r, "field", str),
                        what_to_change=_of(r, "what_to_change", str),
                    )
                    for r in _of(data, "refusals", list)
                ),
                detail=dict(data.get("detail") or {}),
            )
        except (TypeError, ValueError) as exc:
            raise DelegateLogError(f"not a {SCHEMA_ID} record: {exc}") from exc


def read(path: Path) -> DelegateLog:
    """The record at `path`; `DelegateLogError` when it is not a `/1` record."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DelegateLogError(f"{path} is not JSON: {exc}") from exc
    return DelegateLog.from_json(data)


def write(path: Path, log: DelegateLog) -> Path:
    """Write `log` at `path`, whole or not at all, and return the path.

    The parent directory is made first; the bytes are indented, key-sorted and
    newline-terminated, and replace the file in one step (`mcgyvr.atomic`).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(path, json.dumps(log.as_json(), indent=2, sort_keys=True) + "\n")
    return path


def json_schema() -> dict[str, Any]:
    """The JSON Schema (draft 2020-12) of one record: the only copy there is."""
    known = [kind.value for kind in DelegateKind]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://mcgyvr/delegate-log/v1.schema.json",
        "title": "mcgyvr batch log",
        "description": (
            f"{SCHEMA_ID}: what one `mcgyvr PROMPT --log PATH` came to. Defined "
            f"in src/mcgyvr/delegate_log.py, the one copy; import it, do not "
            f"copy it. New kinds may be added under /1: a reader tolerates a "
            f"kind it does not know."
        ),
        "$ref": "#/$defs/DelegateLog",
        "x-exit-codes": {kind.value: int(KIND_EXIT[kind]) for kind in DelegateKind},
        "$defs": {
            "DelegateLog": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema",
                    "kind",
                    "message",
                    "exit_code",
                    "raw_reply_present",
                    "contracts",
                    "refusals",
                    "detail",
                ],
                "properties": {
                    "schema": {
                        "description": "The record's schema name and version.",
                        "const": SCHEMA_ID,
                    },
                    "kind": {
                        "description": (
                            "What it came to; the prefix is the group. One of "
                            "the known kinds, or a newer one a reader tolerates."
                        ),
                        "anyOf": [
                            {"$ref": "#/$defs/KnownKind"},
                            {"type": "string", "pattern": "^[a-z][a-z_]*$"},
                        ],
                    },
                    "message": {
                        "description": (
                            "For a failure, the sentence stderr carries after "
                            "`error: `, verbatim; otherwise a one-line account."
                        ),
                        "type": "string",
                    },
                    "exit_code": {
                        "description": (
                            "What the process returned: an `mcgyvr.exits.Exit` "
                            "value. Under --run, `emitted*` carry the batch's."
                        ),
                        "type": "integer",
                        "minimum": 0,
                    },
                    "raw_reply_present": {
                        "description": (
                            "True when the orchestrator's raw reply was printed "
                            "on stderr."
                        ),
                        "type": "boolean",
                    },
                    "contracts": {
                        "description": "The contracts emitted, in order; [] when none.",
                        "type": "array",
                        "items": {"$ref": "#/$defs/Contract"},
                    },
                    "refusals": {
                        "description": "Every refusal of the decomposition.",
                        "type": "array",
                        "items": {"$ref": "#/$defs/Refusal"},
                    },
                    "detail": {
                        "description": (
                            "Kind-specific facts, every key optional; the module "
                            "names them per kind."
                        ),
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
            },
            "KnownKind": {"enum": known},
            "Contract": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "task_type", "target", "path"],
                "properties": {
                    "id": {"type": "string"},
                    "task_type": {"type": "string"},
                    "target": {"type": "string"},
                    "path": {
                        "description": (
                            "Where --output wrote it; null when printed to stdout."
                        ),
                        "anyOf": [{"type": "string"}, {"type": "null"}],
                    },
                },
            },
            "Refusal": {
                "type": "object",
                "additionalProperties": False,
                "required": ["subject", "reason", "field", "what_to_change"],
                "properties": {
                    "subject": {"type": "string"},
                    "reason": {"type": "string"},
                    "field": {
                        "description": (
                            "A proposal field; `request` = the whole request; "
                            "empty = catch-all."
                        ),
                        "type": "string",
                    },
                    "what_to_change": {"type": "string"},
                },
            },
        },
    }


def json_type(value: object) -> str:
    """The JSON type name of a decoded value: `object`, `array`, `string`, ..."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _of(data: object, key: str, kind: type | tuple[type, ...]) -> Any:
    """`data[key]`, refused when `data` is not an object or the value is not `kind`."""
    if not isinstance(data, dict) or key not in data:
        raise ValueError(f"missing {key!r}")
    value = data[key]
    wanted = kind if isinstance(kind, tuple) else (kind,)
    # `True` is an int to Python and not to JSON: a bool is refused as a number.
    if isinstance(value, bool) and bool not in wanted:
        raise TypeError(f"{key!r} is a boolean")
    if not isinstance(value, wanted):
        raise TypeError(f"{key!r} is {json_type(value)}")
    return value


def logged(
    kind: DelegateKind,
    message: str,
    exit_code: int,
    *,
    contracts: Sequence[LoggedContract] = (),
    refusals: Sequence[LoggedRefusal] = (),
    raw_reply_present: bool = False,
    detail: Mapping[str, Any] | None = None,
) -> DelegateLog:
    """A `DelegateLog`, its `detail` with the keys whose value is None left out."""
    return DelegateLog(
        kind=kind,
        message=message,
        exit_code=exit_code,
        raw_reply_present=raw_reply_present,
        contracts=tuple(contracts),
        refusals=tuple(refusals),
        detail={k: v for k, v in (detail or {}).items() if v is not None},
    )
