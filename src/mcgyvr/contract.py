""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

import yaml

from mcgyvr.catalog import RETIRED_TASK_TYPES, CatalogError, catalog
from mcgyvr.catalog import Evidence as CatalogEvidence
from mcgyvr.catalog import TaskType as CatalogTaskType
from mcgyvr.scope import Scope, enters_git_dir
from mcgyvr.strict_yaml import strict_loader

SCHEMA_VERSION = 1

#
#
#
#
_GLOB_META = re.compile(r"[*?\[]")


def is_pattern(target: str) -> bool:
    ""
    return _GLOB_META.search(target) is not None


#
#e.
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#
#
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

#
#
#
_SHELL_OPERATOR_CHARS = frozenset("&|;<>")


class ContractError(Exception):
    ""


class ContractFileError(ContractError):
    ""


class ContractSchemaError(ContractError):
    ""


#

#
#
#e.


def task_types() -> tuple[CatalogTaskType, ...]:
    ""
    return catalog().task_types


def operations() -> tuple[CatalogTaskType, ...]:
    ""
    return catalog().operations


def task_type_names() -> tuple[str, ...]:
    ""
    return catalog().names


def operation_names() -> tuple[str, ...]:
    ""
    return tuple(t.name for t in catalog().operations)


def task_type(name: str) -> CatalogTaskType:
    ""
    try:
        return catalog().require(name)
    except CatalogError as exc:
        raise ContractSchemaError(f"task_type: {exc}") from exc


def kind_of(task_type_name: str, operation: str = "") -> CatalogTaskType:
    ""
    if not operation:
        return task_type(task_type_name)
    try:
        return catalog().require_operation(operation)
    except CatalogError as exc:
        raise ContractSchemaError(f"operation: {exc}") from exc


#
#
#
#
#
#
#
#ts
#
#
#
#
#
#
#
#
#
#
#
#
# a
#s`
#


def evidence_for(
    kind: CatalogTaskType,
    *,
    acceptance: tuple[str, ...] = (),
    demonstration: tuple[str, ...] = (),
    no_semantic_change: bool = False,
    type_check: bool = False,
) -> tuple[CatalogEvidence, ...]:
    ""
    if not getattr(kind, "evidence_derived", False):
        return kind.required_evidence
    book = catalog()
    names = ["gate"]
    if demonstration:
        names.append("failing_test_first")
    if acceptance:
        names.append("tests_pass")
    if no_semantic_change:
        names.append("no_semantic_change")
    if type_check:
        names.append("type_check")
    return tuple(book.evidence(name) for name in names)


def generic_stop_condition(task_type_name: str, subject: str) -> str:
    ""
    return (
        f"{task_type_name} on {subject} would require deciding something the "
        "contract does not state — report BLOCKED rather than guess"
    )


#

Kind = Literal[
    "int",
    "float",
    "str",
    "bool",
    "enum",
    "str_list",
    "glob_list",
    "block",
    "block_list",
]


@dataclass(frozen=True)
class Field:
    ""

    name: str
    kind: Kind
    doc: str
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    block: tuple[Field, ...] = ()
    min_value: float | None = None
    #
    #
    #
    #
    max_value: float | None = None
    worker_facing: bool = False
    hint: str = ""
    choices_from: Callable[[], tuple[str, ...]] | None = None
    #
    #
    retired: Mapping[str, str] | None = None
    #
    #
    #
    #
    session_optional: bool = False

    def valid_choices(self) -> tuple[str, ...]:
        ""
        return self.choices_from() if self.choices_from is not None else self.choices


DEP_FIELDS: tuple[Field, ...] = (
    Field(
        "path",
        "str",
        "Repo-relative path of the dependency this signature came from.",
        required=True,
        worker_facing=True,
    ),
    Field(
        "signature",
        "str",
        "The function or class signature with its type annotations — NOT its "
        "body: a body invites copying, a signature states the interface.",
        required=True,
        worker_facing=True,
    ),
    Field(
        "note",
        "str",
        "One sentence on how the target is expected to use this dependency.",
        default="",
        worker_facing=True,
    ),
)

CONTEXT_FIELDS: tuple[Field, ...] = (
    Field(
        "max_input_tokens",
        "int",
        "Hard ceiling the assembled worker prompt must fit under. Declared on "
        "the contract rather than inferred at dispatch so that a prompt which "
        "will not fit is a contract-level failure, caught before anything is "
        "dispatched.",
        default=4096,
        min_value=1,
        worker_facing=True,
    ),
)

SCOPE_FIELDS: tuple[Field, ...] = (
    Field(
        "allow",
        "glob_list",
        "Glob patterns the worker's change may touch. An empty allow list "
        "permits nothing (`mcgyvr.scope` fails closed), so a contract that "
        "declares none is rejected rather than silently unable to act.",
        required=True,
        session_optional=True,
        hint='e.g. ["src/**/*.py"]',
    ),
    Field(
        "forbid",
        "glob_list",
        "Glob patterns that override `allow`. Forbid wins ties, which is the "
        "safe direction for an autonomous gate.",
        default=(),
    ),
)

VERIFICATION_FIELDS: tuple[Field, ...] = (
    Field(
        "policy",
        "enum",
        "How the change is judged. `gate_only` is honoured only for work a "
        "deterministic tool does; work a model does is raised to `model`, "
        "which asks a fresh-context reviewer to agree. An install with no "
        "reviewer labels such an acceptance unverified.",
        default="gate_only",
        choices=("gate_only", "model"),
    ),
)

RENAME_FIELDS: tuple[Field, ...] = (
    Field(
        "from",
        "str",
        "The symbol as it is written today. Stated rather than read out of "
        "`task`: mcgyvr renames every reference the index resolved across "
        "every file that holds one, and a name inferred from prose is a "
        "multi-file rewrite resting on a guess about English. A worker asked "
        "to guess would guess; a program must be told.",
        default="",
        hint="e.g. fetch_page",
    ),
    Field(
        "to",
        "str",
        "What the symbol becomes. Must be a legal identifier — the rename "
        "rewrites text, and a `to` that is not a name would produce a tree "
        "that no longer parses while reporting success.",
        default="",
        hint="e.g. fetch_document",
    ),
)

LIMITS_FIELDS: tuple[Field, ...] = (
    Field(
        "max_output_tokens",
        "int",
        "What the worker's reply may spend, in output tokens: what the *work* "
        "is worth, counting any reasoning a model does before it writes. "
        "Model-written `code` must state it: without it the contract is "
        "valid, and `mcgyvr run` refuses it before any model is called. Sent "
        "exactly; refused by name if above the ceiling of a unit the run may "
        "reach (its `window` less the prompt, or its `output_tokens`). A "
        "reply cut off at the cap is a named failure, never applied to a "
        "file. `chat` and `agent` are a raw connection: stating it there is "
        "refused. A deterministic operation has no cap.",
        default=None,
        min_value=1,
    ),
    Field(
        "max_window_fraction",
        "float",
        "The largest share of the context window this contract may claim: "
        "its assembled prompt and `max_output_tokens` together, over the "
        "whole window. A different question from whether the two fit, which "
        "`context.max_input_tokens` already bounds — a contract that fits "
        "with nothing to spare leaves nothing to hold anything beside it and "
        "nothing to absorb an estimate that ran long. Declared here because "
        "it is a statement about this unit of work, and checked before the "
        "work is sent. The run's `max_window_fraction` caps it: the stricter "
        "of the two applies. Unset is not 1.0: a contract that declared none "
        "is recorded as having declared none.",
        default=None,
        min_value=0.0,
        max_value=1.0,
        hint="e.g. 0.75 to leave a quarter of the window clear",
    ),
    Field(
        "attempts",
        "int",
        "How many times the work may be retried before escalating. Retrying "
        "forever is how a cheap task becomes an expensive one.",
        default=2,
        min_value=1,
    ),
)

SCHEMA: tuple[Field, ...] = (
    Field(
        "version",
        "int",
        "Schema version this contract is written against. A contract "
        "declaring a version this build does not read is rejected rather than "
        "interpreted under the wrong rules.",
        default=SCHEMA_VERSION,
        min_value=1,
    ),
    Field(
        "id",
        "str",
        "Identity: how this contract is referred to in records, telemetry and "
        "branch names. Letters, digits, dot, dash and underscore, up to 64 "
        "characters.",
        required=True,
        worker_facing=True,
        hint="e.g. fetch-helper-retry",
    ),
    Field(
        "task_type",
        "enum",
        "What kind of work this is, from the declared vocabulary. The type "
        "decides what evidence the contract must carry and how its result is "
        "judged.",
        required=True,
        choices_from=task_type_names,
        retired=RETIRED_TASK_TYPES,
        worker_facing=True,
    ),
    Field(
        "operation",
        "enum",
        "A deterministic operation a tool performs instead of a model, for "
        "`task_type: code`; its own guarantee and evidence apply, and the "
        "target may be a glob.",
        default="",
        choices_from=operation_names,
    ),
    Field(
        "task",
        "str",
        "What to do, in words, addressed to the worker. Self-contained: a "
        "worker sees this and the rest of the worker-facing fields, never the "
        "conversation that produced them.",
        required=True,
        worker_facing=True,
    ),
    Field(
        "target",
        "str",
        "Where the result goes. Exactly one literal repo-relative path for "
        "any contract a model executes — a model worker's output has one "
        "destination, and a pattern would leave it guessing. A glob is legal "
        "only for a contract with a deterministic `operation`. A session "
        "(`chat`, `agent`) writes nothing and names none.",
        required=True,
        session_optional=True,
        worker_facing=True,
        hint="e.g. src/pkg/fetch.py",
    ),
    Field(
        "target_content",
        "str",
        "The current content of `target`, verbatim, when the file already "
        "exists. A contract that carries it is self-contained: "
        "`parse(dumps(c))` round-trips the bytes a worker is sent. Empty "
        "means the target does not exist yet, or the contract did not carry "
        "it: the worker is then given the file as the sandbox workspace holds "
        "it at dispatch, and a deterministic tool reads the file itself.",
        default="",
        worker_facing=True,
    ),
    Field(
        "interface",
        "str",
        "What the result must expose — the signature, the name, the shape a "
        "caller depends on. Stated separately from `task` because it is the "
        "machine-checkable half of done.",
        default="",
        worker_facing=True,
    ),
    Field(
        "deps",
        "block_list",
        "Dependencies the target needs, as signatures rather than source.",
        block=DEP_FIELDS,
        default=(),
        worker_facing=True,
    ),
    Field(
        "stop_conditions",
        "str_list",
        "Explicit triggers on which the worker must stop and report BLOCKED "
        "instead of guessing — scope creep, an unknown API, an ambiguous "
        "directive. Required when a model writes a `whole_file` reply, the "
        "one whose refusal is caught and escalated: guessing is the documented "
        "small-model failure mode these exist to prevent. A `prose` or "
        "`media_artifact` reply is served whatever it says, so none is "
        "required there. Start from "
        f"`{generic_stop_condition('<task_type>', '<target>')}`.",
        default=(),
        worker_facing=True,
    ),
    Field(
        "output_schema",
        "enum",
        "The shape the worker must reply in, declared so a runner can hand "
        "the model format instructions rather than hoping for a convention. "
        "`whole_file` is the single-file output protocol; `prose` is the "
        "raw-text answer for chat and agent (their default); `media_artifact` "
        "is the "
        "media-generation request for media, whose artifact the bound media "
        "engine writes to the target. `unified_diff` validates here and is "
        "refused before dispatch.",
        default="whole_file",
        choices=("whole_file", "prose", "media_artifact", "unified_diff"),
        worker_facing=True,
    ),
    Field(
        "media_kind",
        "enum",
        "The media kind of the artifact, for `media_valid`: image, audio or video.",
        default="",
        choices=("image", "audio", "video"),
    ),
    Field(
        "transcript",
        "str",
        "The text the audio output must say, for `asr_wer`.",
        default="",
    ),
    Field(
        "wer_threshold",
        "float",
        "The word-error-rate ceiling for `asr_wer`, a share from 0 to 1.",
        default=None,
        min_value=0.0,
        max_value=1.0,
    ),
    Field(
        "sources",
        "str_list",
        "Repo files given whole to the worker as `[1]`, `[2]`, …; a missing, "
        "binary or secret one is refused.",
        default=(),
        worker_facing=True,
    ),
    Field(
        "context",
        "block",
        "Budgets governing what may be assembled into the worker's prompt.",
        block=CONTEXT_FIELDS,
        worker_facing=True,
    ),
    Field(
        "scope",
        "block",
        "The writable surface the gate enforces. Not worker-facing: the "
        "worker is told its one target, and scope is how the gate judges what "
        "actually changed.",
        block=SCOPE_FIELDS,
        required=True,
        session_optional=True,
    ),
    Field(
        "acceptance",
        "str_list",
        "Commands, one per entry, split like a shell would split them (quotes "
        "respected) and executed directly with no shell: no `VAR=x` prefix, "
        "`&&`, pipes or redirects (`mcgyvr contract` refuses them; write "
        "`env VAR=x cmd`, or commit a script). Each must pass for the change "
        "to be accepted — the strongest signal the gate has — and also on the "
        "*unchanged* tree (the preflight refuses a suite that is already red), "
        "which is why a command meant to demonstrate a defect goes in "
        "`demonstration`. Arbitrary code from a contract: they run inside the "
        "per-task sandbox — a container in `docker` mode, a throwaway "
        "workspace on your own machine in `tempdir` mode.",
        default=(),
    ),
    Field(
        "demonstration",
        "str_list",
        "Commands that demonstrate the defect: each must FAIL on the "
        "unchanged tree and pass after the change — the `failing_test_first` "
        "evidence, as a slot of its own because its baseline expectation is "
        "the opposite of `acceptance`'s. Written, run and sandboxed exactly "
        "like `acceptance`; what it leaves behind is cleaned up.",
        default=(),
    ),
    Field(
        "no_semantic_change",
        "bool",
        "Whether the change must leave the parsed structure untouched apart "
        "from the region the task is allowed to touch. A flag rather than a "
        "task type: for `task_type: code` it derives the `no_semantic_change` "
        "evidence, and for every other type it is ignored. Defaults to false.",
        default=False,
    ),
    Field(
        "type_check",
        "bool",
        "Whether the project's own type checker must pass on the changed "
        "target. A flag rather than a task type: for `task_type: code` it "
        "derives the `type_check` evidence, and for every other type it is "
        "ignored. Defaults to false.",
        default=False,
    ),
    Field(
        "depends_on",
        "str_list",
        "Ids of the contracts that must complete before this one may run. "
        "Stated on the contract, so a plan can be ordered — and the parts of "
        "it that cannot run at all found — before a token is spent, the way "
        "`route.plan()` already is. A proposer's emission order is the order a "
        "model thought of things, not a dependency order, so ordering that is "
        "not written down here is ordering that does not exist. Not "
        "worker-facing: a worker is handed one task and never the plan around "
        "it, and a dependency that has landed is already in the tree it reads.",
        default=(),
        hint='e.g. ["write-fetch"]',
    ),
    Field(
        "risk",
        "enum",
        "How much a wrong answer costs. Recorded on the contract and printed "
        "by `mcgyvr contract`; routing and verification do not read it.",
        default="medium",
        choices=("low", "medium", "high"),
    ),
    Field(
        "verification",
        "block",
        "How the change is judged once the gate has passed.",
        block=VERIFICATION_FIELDS,
    ),
    Field(
        "limits",
        "block",
        "Hard ceilings on what one execution of this contract may spend.",
        block=LIMITS_FIELDS,
    ),
    Field(
        "rename",
        "block",
        "Which symbol becomes which, for `operation: rename_symbol`. The one "
        "operation mcgyvr executes in-process rather than by running a "
        "program, and the only one whose input is not fully determined by "
        "`target`: a rename fans across every file that references the "
        "symbol, so the pair has to be said. Meaningless on any other "
        "contract and ignored there.",
        block=RENAME_FIELDS,
    ),
)


#


@dataclass(frozen=True)
class Dependency:
    ""

    path: str
    signature: str
    note: str = ""


@dataclass(frozen=True)
class Rename:
    ""

    old: str = ""
    new: str = ""

    @property
    def stated(self) -> bool:
        return bool(self.old and self.new)


@dataclass(frozen=True)
class Verification:
    ""

    policy: str


@dataclass(frozen=True)
class Limits:
    ""

    max_output_tokens: int | None
    attempts: int
    #
    #
    #
    #
    max_window_fraction: float | None = None


@dataclass(frozen=True)
class Contract:
    ""

    id: str
    task_type: str
    task: str
    target: str
    scope: Scope
    version: int = SCHEMA_VERSION
    operation: str = ""
    target_content: str = ""
    interface: str = ""
    deps: tuple[Dependency, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    output_schema: str = "whole_file"
    media_kind: str = ""
    transcript: str = ""
    wer_threshold: float | None = None
    sources: tuple[str, ...] = ()
    max_input_tokens: int = 4096
    acceptance: tuple[str, ...] = ()
    demonstration: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    risk: str = "medium"
    verification: Verification = Verification("gate_only")
    limits: Limits = Limits(None, 2)
    rename: Rename = Rename()
    no_semantic_change: bool = False
    type_check: bool = False
    #
    #
    #
    # a
    #
    source_content: tuple[str, ...] = ()

    @property
    def type(self) -> CatalogTaskType:
        ""
        return catalog().require(self.task_type)

    @property
    def kind(self) -> CatalogTaskType:
        ""
        return kind_of(self.task_type, self.operation)

    @property
    def evidence(self) -> tuple[CatalogEvidence, ...]:
        ""
        return evidence_for(
            self.kind,
            acceptance=self.acceptance,
            demonstration=self.demonstration,
            no_semantic_change=self.no_semantic_change,
            type_check=self.type_check,
        )

    @property
    def evidence_names(self) -> tuple[str, ...]:
        ""
        return tuple(e.name for e in self.evidence)

    @property
    def is_deterministic(self) -> bool:
        ""
        return self.kind.deterministic

    @property
    def is_session(self) -> bool:
        ""
        return self.kind.session

    @property
    def needs_output_cap(self) -> bool:
        ""
        return self.kind.needs_output_cap

    @property
    def acceptance_commands(self) -> tuple[tuple[str, ...], ...]:
        ""
        return tuple(tuple(shlex.split(command)) for command in self.acceptance)

    @property
    def demonstration_commands(self) -> tuple[tuple[str, ...], ...]:
        ""
        return tuple(tuple(shlex.split(command)) for command in self.demonstration)

    @property
    def prose(self) -> str:
        ""
        return f"{self.task}\n{self.interface}"

    def worker_view(self) -> dict[str, Any]:
        ""
        return {
            "id": self.id,
            "task_type": self.task_type,
            "task": self.task,
            "target": self.target,
            "target_content": self.target_content,
            "interface": self.interface,
            "deps": [
                {"path": d.path, "signature": d.signature, "note": d.note}
                for d in self.deps
            ],
            "stop_conditions": list(self.stop_conditions),
            "output_schema": self.output_schema,
            "sources": [
                {
                    "path": path,
                    "content": (
                        self.source_content[index]
                        if len(self.source_content) == len(self.sources)
                        else None
                    ),
                }
                for index, path in enumerate(self.sources)
            ],
            "context": {"max_input_tokens": self.max_input_tokens},
        }

    def as_dict(self) -> dict[str, Any]:
        ""
        stated = {"depends_on": sorted(self.depends_on)} if self.depends_on else {}
        #
        #
        #
        renamed = (
            {"rename": {"from": self.rename.old, "to": self.rename.new}}
            if self.rename.stated
            else {}
        )
        #
        #
        #
        #
        share = (
            {"max_window_fraction": self.limits.max_window_fraction}
            if self.limits.max_window_fraction is not None
            else {}
        )
        #
        #
        #
        flags: dict[str, bool] = {}
        if self.no_semantic_change:
            flags["no_semantic_change"] = True
        if self.type_check:
            flags["type_check"] = True
        return {
            "version": self.version,
            "id": self.id,
            "task_type": self.task_type,
            #
            #
            **({"operation": self.operation} if self.operation else {}),
            "task": self.task,
            "target": self.target,
            "target_content": self.target_content,
            "interface": self.interface,
            "deps": [
                {"path": d.path, "signature": d.signature, "note": d.note}
                for d in self.deps
            ],
            "stop_conditions": list(self.stop_conditions),
            "output_schema": self.output_schema,
            **({"media_kind": self.media_kind} if self.media_kind else {}),
            **({"transcript": self.transcript} if self.transcript else {}),
            **(
                {"wer_threshold": self.wer_threshold}
                if self.wer_threshold is not None
                else {}
            ),
            **({"sources": list(self.sources)} if self.sources else {}),
            "context": {"max_input_tokens": self.max_input_tokens},
            "scope": {
                "allow": list(self.scope.allow),
                "forbid": list(self.scope.forbid),
            },
            "acceptance": list(self.acceptance),
            "demonstration": list(self.demonstration),
            **flags,
            **stated,
            "risk": self.risk,
            **renamed,
            "verification": {"policy": self.verification.policy},
            "limits": {
                "max_output_tokens": self.limits.max_output_tokens,
                "attempts": self.limits.attempts,
                **share,
            },
        }


#


def load(path: Path) -> Contract:
    ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractFileError(f"{path}: cannot be read ({exc.strerror}).") from exc
    return parse(text, path=path)


def loads(text: str) -> Contract:
    ""
    return parse(text)


def parse(text: str, path: Path | None = None) -> Contract:
    ""
    where = f"{path}: " if path else ""
    try:
        raw = yaml.load(text, Loader=strict_loader(ContractSchemaError))
    except yaml.YAMLError as exc:
        raise ContractFileError(f"{where}not valid YAML or JSON: {exc}") from exc
    if raw is None:
        raise ContractSchemaError(
            f"{where}the contract is empty. It needs at least id, task_type, "
            f"task, target and scope.allow."
        )

    declared = raw.get("version") if isinstance(raw, dict) else None
    if isinstance(declared, int) and declared != SCHEMA_VERSION:
        raise ContractSchemaError(
            f"version: {declared!r} is not a schema version this build reads. "
            f"This build reads version {SCHEMA_VERSION}."
        )

    session = _is_session(raw)
    data = _block(raw, _for_sessions(SCHEMA) if session else SCHEMA, "")
    if session and "output_schema" not in raw:
        #
        #
        data["output_schema"] = "prose"
    _cross_validate(data)
    return _build(data)


def dumps(contract: Contract) -> str:
    ""
    return json.dumps(contract.as_dict(), indent=2)


def _build(data: Mapping[str, Any]) -> Contract:
    ""
    return Contract(
        id=data["id"],
        task_type=data["task_type"],
        task=data["task"],
        target=data["target"],
        scope=Scope.of(data["scope"]["allow"], data["scope"]["forbid"]),
        version=data["version"],
        operation=data["operation"],
        target_content=data["target_content"],
        interface=data["interface"],
        deps=tuple(
            Dependency(path=d["path"], signature=d["signature"], note=d["note"])
            for d in data["deps"]
        ),
        stop_conditions=tuple(data["stop_conditions"]),
        output_schema=data["output_schema"],
        media_kind=data["media_kind"],
        transcript=data["transcript"],
        wer_threshold=data["wer_threshold"],
        sources=tuple(data["sources"]),
        max_input_tokens=data["context"]["max_input_tokens"],
        acceptance=tuple(data["acceptance"]),
        demonstration=tuple(data["demonstration"]),
        depends_on=tuple(data["depends_on"]),
        risk=data["risk"],
        verification=Verification(policy=data["verification"]["policy"]),
        limits=Limits(
            max_output_tokens=data["limits"]["max_output_tokens"],
            attempts=data["limits"]["attempts"],
            max_window_fraction=data["limits"]["max_window_fraction"],
        ),
        rename=Rename(old=data["rename"]["from"], new=data["rename"]["to"]),
        no_semantic_change=data["no_semantic_change"],
        type_check=data["type_check"],
    )


#


def _block(raw: object, fields: tuple[Field, ...], path: str) -> dict[str, Any]:
    ""
    given = _mapping(raw if raw is not None else {}, path)
    known = {f.name: f for f in fields}

    for key in given:
        if key not in known:
            where = f"{path}: " if path else "contract: "
            raise ContractSchemaError(
                f"{where}unknown key {key!r}. An ignored key is a contract "
                f"that does not do what it says. Valid keys here: "
                f"{', '.join(sorted(known))}"
            )

    result: dict[str, Any] = {}
    for spec in fields:
        here = _join(path, spec.name)
        if spec.name in given and given[spec.name] is not None:
            result[spec.name] = _value(given[spec.name], spec, here)
        elif spec.required:
            raise _missing(spec, here)
        else:
            result[spec.name] = _default_for(spec)
    return result


def _value(raw: object, spec: Field, path: str) -> Any:
    ""
    if spec.kind == "int":
        return _int(raw, spec, path)
    if spec.kind == "float":
        return _float(raw, spec, path)
    if spec.kind == "bool":
        if not isinstance(raw, bool):
            raise ContractSchemaError(f"{path}: must be true or false, got {raw!r}.")
        return raw
    if spec.kind == "str":
        #
        #k`
        #
        return _str(raw, path, allow_empty=not spec.required)
    if spec.kind == "enum":
        text = _str(raw, path)
        valid = spec.valid_choices()
        if text not in valid and spec.retired and text in spec.retired:
            raise ContractSchemaError(
                f"{path}: {text!r} is now {spec.retired[text]}. "
                f"Valid: {', '.join(valid)}"
            )
        if text not in valid:
            raise ContractSchemaError(
                f"{path}: {text!r} is not valid here. Valid: {', '.join(valid)}"
            )
        return text
    if spec.kind in ("str_list", "glob_list"):
        return _string_list(raw, spec, path)
    if spec.kind == "block":
        return _block(raw, spec.block, path)
    if spec.kind == "block_list":
        items = _sequence(raw, path)
        return tuple(
            _block(item, spec.block, f"{path}.{index}")
            for index, item in enumerate(items)
        )
    raise AssertionError(f"unhandled kind {spec.kind!r}")  #


def _int(raw: object, spec: Field, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ContractSchemaError(f"{path}: must be a whole number, got {raw!r}.")
    if spec.min_value is not None and raw < spec.min_value:
        raise ContractSchemaError(
            f"{path}: must be at least {spec.min_value}, got {raw}."
        )
    if spec.max_value is not None and raw > spec.max_value:
        raise ContractSchemaError(
            f"{path}: must be at most {spec.max_value}, got {raw}."
        )
    return raw


def _float(raw: object, spec: Field, path: str) -> float:
    #
    #
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ContractSchemaError(f"{path}: must be a number, got {raw!r}.")
    if spec.min_value is not None and raw < spec.min_value:
        raise ContractSchemaError(
            f"{path}: must be at least {spec.min_value}, got {raw}."
        )
    if spec.max_value is not None and raw > spec.max_value:
        raise ContractSchemaError(
            f"{path}: must be at most {spec.max_value}, got {raw}."
        )
    return float(raw)


def _str(raw: object, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(raw, str):
        raise ContractSchemaError(f"{path}: must be text, got {raw!r}.")
    if not raw.strip() and not allow_empty:
        raise ContractSchemaError(
            f"{path}: is empty. Either give it a value or leave the key out."
        )
    return raw


def _string_list(raw: object, spec: Field, path: str) -> tuple[str, ...]:
    items = _sequence(raw, path)
    out: list[str] = []
    for index, item in enumerate(items):
        text = _str(item, f"{path}.{index}")
        if spec.kind == "glob_list":
            _check_glob(text, f"{path}.{index}")
        out.append(text)
    return tuple(out)


def _check_glob(pattern: str, path: str) -> None:
    ""
    if pattern.startswith("/"):
        raise ContractSchemaError(
            f"{path}: {pattern!r} is absolute. Scope patterns are "
            f"repo-relative — drop the leading '/'."
        )
    if ".." in pattern.split("/"):
        raise ContractSchemaError(
            f"{path}: {pattern!r} escapes the repository with '..'. Scope "
            f"patterns may only name paths inside it."
        )


def _sequence(raw: object, path: str) -> Sequence[Any]:
    if isinstance(raw, str) or not isinstance(raw, Sequence):
        raise ContractSchemaError(
            f"{path}: must be a list, got {raw!r}. A single value still goes in a list."
        )
    return raw


def _mapping(raw: object, path: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ContractSchemaError(
            f"{path or 'contract'}: must be a block of keys, got {raw!r}."
        )
    for key in raw:
        if not isinstance(key, str):
            raise ContractSchemaError(f"{path or 'contract'}: key {key!r} is not text.")
    return raw


def _is_session(raw: object) -> bool:
    ""
    if not isinstance(raw, Mapping):
        return False
    name = raw.get("task_type")
    if not isinstance(name, str):
        return False
    return name in task_type_names() and task_type(name).session


def _for_sessions(fields: tuple[Field, ...]) -> tuple[Field, ...]:
    ""
    return tuple(
        replace(
            spec,
            required=spec.required and not spec.session_optional,
            block=_for_sessions(spec.block),
        )
        for spec in fields
    )


def _missing(spec: Field, path: str) -> ContractSchemaError:
    hint = f" {spec.hint}" if spec.hint else ""
    return ContractSchemaError(f"{path}: required key is not set. {spec.doc}{hint}")


def _default_for(spec: Field) -> Any:
    if spec.kind == "block":
        return _block({}, spec.block, "")
    if spec.default is None and spec.kind in ("str_list", "glob_list", "block_list"):
        return ()
    if spec.default is None and spec.kind == "str":
        return ""
    return spec.default


def _join(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


#


def _check_command(command: str, path: str) -> None:
    ""
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ContractSchemaError(
            f"{path}: {command!r} cannot be split into arguments ({exc}); "
            f"commands run without a shell but are split like one, so every "
            f"quote must close."
        ) from None
    if argv and _ENV_ASSIGNMENT.match(argv[0]):
        raise ContractSchemaError(
            f"{path}: starts with the environment assignment {argv[0]!r}, but "
            f"commands run without a shell, so it would be executed as a "
            f"program of that name. Write `env {command}`, or use the tool's "
            f"own flag (`python -B` rather than PYTHONDONTWRITEBYTECODE=1)."
        )
    operator = _unquoted_operator(command)
    if operator is not None:
        raise ContractSchemaError(
            f"{path}: {command!r} contains the shell operator `{operator}`, "
            f"but commands run without a shell, so the program would receive "
            f"it as an argument. Put one command in each entry, or put the "
            f"pipeline in a committed script and run that."
        )


def _unquoted_operator(command: str) -> str | None:
    ""
    run = ""
    quote = ""
    escaped = False
    for char in command:
        if escaped:
            escaped = False
        elif quote == "'":
            quote = "" if char == "'" else quote
        elif char == "\\":
            escaped = True
        elif quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char in _SHELL_OPERATOR_CHARS:
            run += char
            continue
        if run:
            return run
    return run or None


def _cross_validate(data: Mapping[str, Any]) -> None:
    ""
    identity = data["id"]
    if not _ID.match(identity):
        raise ContractSchemaError(
            f"id: {identity!r} is not a usable identity. Use letters, digits, "
            f"dot, dash or underscore, starting with a letter or digit, up to "
            f"64 characters."
        )

    declared = task_type(data["task_type"])
    if data["operation"]:
        operation = kind_of(data["task_type"], data["operation"])
        if operation.task_type != declared.name:
            raise ContractSchemaError(
                f"operation: {operation.name!r} is an operation of task type "
                f"{operation.task_type!r}, not of {declared.name!r}. Write "
                f"`task_type: {operation.task_type}` beside it, or drop the "
                f"operation."
            )
    kind = kind_of(data["task_type"], data["operation"])
    target = data["target"]
    allow = data["scope"]["allow"]
    forbid = data["scope"]["forbid"]

    if kind.session:
        #
        #
        #
        if data["output_schema"] != "prose":
            raise ContractSchemaError(
                f"output_schema: {data['output_schema']!r} is a file-shaped "
                f"reply, but a {kind.name!r} run is a session: its reply is the "
                f"answer, returned in the result file and kept in the session "
                f"log, never written. Drop output_schema; 'prose' is the "
                f"default."
            )
        #
        #
        #
        #
        stated = data["limits"]["max_output_tokens"]
        if stated is not None:
            raise ContractSchemaError(
                f"limits.max_output_tokens: {stated} is stated, but a "
                f"{kind.name!r} run is a raw connection to a model and mcgyvr "
                f"sets no limits on it: no output cap is sent, and no prompt or "
                f"window check is made. Drop limits.max_output_tokens."
            )
    else:
        _check_destination(data, kind, target, allow, forbid)

    #
    #
    #ld
    #
    if (
        not kind.deterministic
        and data["output_schema"] == "whole_file"
        and not data["stop_conditions"]
    ):
        raise ContractSchemaError(
            f"stop_conditions: is empty, but task type {kind.name!r} runs on "
            f"a model that replies with a whole_file. Without a stated trigger "
            f"to report BLOCKED, a worker that meets an unknown will guess. "
            f"Name at least one condition; start from "
            f'"{generic_stop_condition(kind.name, target)}".'
        )

    for field in ("acceptance", "demonstration"):
        for index, command in enumerate(data[field]):
            _check_command(command, f"{field}.{index}")

    if kind.needs_acceptance_commands and not data["acceptance"]:
        needed = ", ".join(
            e.name
            for e in kind.required_evidence
            if e.needs_commands and e.baseline == "pass"
        )
        raise ContractSchemaError(
            f"acceptance: is empty, but task type {kind.name!r} requires "
            f"evidence only a command can produce ({needed}). Its guarantee is "
            f'"{kind.guarantee}" — with nothing to run, a change would be '
            f"accepted on the gate alone and the guarantee would be unbacked. "
            f"Name at least one command that demonstrates it."
        )

    if kind.needs_demonstration_commands and not data["demonstration"]:
        needed = ", ".join(
            e.name
            for e in kind.required_evidence
            if e.needs_commands and e.baseline == "fail"
        )
        raise ContractSchemaError(
            f"demonstration: is empty, but task type {kind.name!r} requires a "
            f"command that demonstrates the defect ({needed}) — one that fails "
            f"before the change and passes after. Without it a fix is "
            f"indistinguishable from a plausible edit, and the type's "
            f'guarantee ("{kind.guarantee}") would be unbacked. Name the '
            f"command in `demonstration`, not `acceptance` — the preflight "
            f"expects the two lists to do opposite things on the unchanged tree."
        )

    both = sorted(set(data["acceptance"]) & set(data["demonstration"]))
    if both:
        raise ContractSchemaError(
            f"demonstration: {both[0]!r} is also in acceptance. One command "
            f"cannot both pass and fail on the unchanged tree — put it in "
            f"acceptance if it is a regression signal, demonstration if it "
            f"shows the defect."
        )

    #
    #
    #__
    #
    #
    from mcgyvr.gate.output import ASR_WER, MEDIA_VALID

    evidence_names = {e.name for e in kind.required_evidence}
    if MEDIA_VALID in evidence_names and not data["media_kind"]:
        raise ContractSchemaError(
            f"media_kind: is empty, but task type {kind.name!r} requires "
            f"media_valid evidence — the gate must know which media kind to "
            f"expect. Name image, audio or video."
        )
    if ASR_WER in evidence_names and not data["transcript"]:
        raise ContractSchemaError(
            f"transcript: is empty, but task type {kind.name!r} requires "
            f"asr_wer evidence — the ASR gate needs the text the audio is "
            f"expected to say."
        )
    if ASR_WER in evidence_names and data["wer_threshold"] is None:
        raise ContractSchemaError(
            f"wer_threshold: is not set, but task type {kind.name!r} requires "
            f"asr_wer evidence — name the word-error-rate ceiling (0 to 1)."
        )
    _check_sources(data["sources"])

    #
    #
    #he
    #
    waiting: set[str] = set()
    for index, needed in enumerate(data["depends_on"]):
        if needed == identity:
            raise ContractSchemaError(
                f"depends_on.{index}: {needed!r} is this contract's own id, so "
                f"it would be waiting for itself and could never start. Name "
                f"the contract that must land first, or drop the key."
            )
        if not _ID.match(needed):
            raise ContractSchemaError(
                f"depends_on.{index}: {needed!r} is not a usable contract id, "
                f"so no contract could ever satisfy it. Use letters, digits, "
                f"dot, dash or underscore, starting with a letter or digit, up "
                f"to 64 characters."
            )
        if needed in waiting:
            raise ContractSchemaError(
                f"depends_on.{index}: {needed!r} appears more than once. "
                f"Waiting for one contract twice is waiting for it once — "
                f"remove the repeat."
            )
        waiting.add(needed)

    seen: set[str] = set()
    for index, dep in enumerate(data["deps"]):
        if dep["path"] in seen:
            raise ContractSchemaError(
                f"deps.{index}.path: {dep['path']!r} appears more than once. "
                f"One signature per dependency — a second entry would silently "
                f"pad the prompt."
            )
        seen.add(dep["path"])

    #
    #
    #he
    #
    #
    #
    #
    #
    #


def _check_sources(sources: Sequence[str]) -> None:
    ""
    seen: set[str] = set()
    for index, source in enumerate(sources):
        where = f"sources.{index}: {source!r}"
        if not source.strip():
            raise ContractSchemaError(
                f"{where} is empty. Name a repo-relative file, or drop the entry."
            )
        if source.startswith("/"):
            raise ContractSchemaError(
                f"{where} is absolute. A source is a file in the repository, "
                f"named relative to its root — drop the leading '/'."
            )
        if ".." in source.split("/"):
            raise ContractSchemaError(
                f"{where} escapes the repository with '..'. A source is a file "
                f"in the repository."
            )
        if enters_git_dir(source):
            raise ContractSchemaError(
                f"{where} is inside a .git directory, which is git's own state "
                f"and not a file in the tree. Name a file in the tree."
            )
        if _GLOB_META.search(source):
            raise ContractSchemaError(
                f"{where} is a pattern. Each source is one literal file, read "
                f"whole and numbered in the prompt — list the files."
            )
        if source in seen:
            raise ContractSchemaError(
                f"{where} is named twice. Each source is given to the worker "
                f"once, under one number — remove the repeat."
            )
        seen.add(source)


def _check_destination(
    data: Mapping[str, Any],
    kind: CatalogTaskType,
    target: str,
    allow: Sequence[str],
    forbid: Sequence[str],
) -> None:
    ""
    if not allow:
        raise ContractSchemaError(
            "scope.allow: is empty, which permits nothing — the contract "
            "could not change a single file. Name at least one pattern the "
            "worker may touch."
        )

    _check_glob(target, "target")
    if enters_git_dir(target):
        raise ContractSchemaError(
            f"target: {target!r} is inside a .git directory. Host git reads it "
            f"as configuration and hooks, so a worker's bytes there are commands "
            f"the host runs. Name a file in the tree."
        )
    if _GLOB_META.search(target) and not kind.deterministic:
        raise ContractSchemaError(
            f"target: {target!r} is a pattern, but task type "
            f"{kind.name!r} runs on a model, whose output has exactly one "
            f"destination. Name a single literal path, or name a deterministic "
            f"operation "
            f"({', '.join(t.name for t in operations() if t.deterministic)})."
        )

    if _GLOB_META.search(target) and data["target_content"]:
        raise ContractSchemaError(
            f"target_content: is set, but target {target!r} is a pattern — "
            f"there is no one file whose content this could be. Name a single "
            f"literal path, or drop target_content: a pattern target runs on "
            f"the deterministic tier, whose tools read each file themselves."
        )

    overlap = sorted(set(allow) & set(forbid))
    if overlap:
        raise ContractSchemaError(
            f"scope.forbid: {overlap[0]!r} is both allowed and forbidden. "
            f"Forbid always wins, so the allow entry can never apply — remove "
            f"whichever one is wrong."
        )

    scope = Scope.of(allow, forbid)
    if not _GLOB_META.search(target):
        if scope.forbidden(target):
            raise ContractSchemaError(
                f"target: {target!r} is forbidden by this contract's own "
                f"scope.forbid, so nothing it produced could ever be "
                f"accepted. Remove the forbid pattern or retarget."
            )
        if not scope.permits(target):
            raise ContractSchemaError(
                f"target: {target!r} is outside scope.allow "
                f"({', '.join(allow)}), so a change writing it would be "
                f"rejected by the gate. Add a pattern that covers it."
            )
