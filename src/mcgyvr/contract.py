"""The contract: one unit of work declared as text, and the code that validates it.

`SCHEMA` names every key and what it may hold, `parse` checks a document against
that table and then against the rules spanning several fields in
`_cross_validate`, and `Contract` is the frozen result that the prompt builder,
the gate and the planner all read.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.catalog import RETIRED_TASK_TYPES, CatalogError, catalog
from mcgyvr.catalog import Evidence as CatalogEvidence
from mcgyvr.catalog import TaskType as CatalogTaskType
from mcgyvr.schema import Dialect, join_path, walk_block
from mcgyvr.schema import Field as Field
from mcgyvr.scope import Scope, enters_git_dir
from mcgyvr.strict_yaml import strict_loader

SCHEMA_VERSION = 1

# Glob metacharacters: `*`, `?` and the start of a character class. A target or
# a `sources` entry containing one names a set of files, which only a
# deterministic operation may do; everything else names exactly one literal path
# and the checks below refuse it otherwise.
_GLOB_META = re.compile(r"[*?\[]")


def is_pattern(target: str) -> bool:
    """Whether `target` holds a glob metacharacter, i.e. names several paths."""
    return _GLOB_META.search(target) is not None


# Contract ids reach records, telemetry and branch names, so they are limited to
# 1-64 characters safe in all three: letters, digits, dot, dash, underscore.
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# A leading `NAME=value` token. Commands are executed without a shell, so such a
# token would be looked up as a program name instead of being applied.
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# The characters shell operators are built from (`&&`, `||`, `;`, `|`, `<`, `>`,
# `2>`). Commands run without a shell, so one of these outside quotes is refused
# rather than handed to the program as an argument.
_SHELL_OPERATOR_CHARS = frozenset("&|;<>")


class ContractError(Exception):
    """The base of every error about a contract's text, caught as one family."""


class ContractFileError(ContractError):
    """The contract could not be read or parsed: no file, or not valid YAML."""


class ContractSchemaError(ContractError):
    """Parsed, but the content breaks the schema or a rule across several fields."""


# Vocabulary accessors: everything the schema offers as a choice is read from the
# catalog, so a type added there appears here without a second list to keep.

# `task_type`, `kind_of` and the `*_names` functions are what the schema and the
# cross-field checks call, and each turns a catalog failure into a
# ContractSchemaError naming the field that asked, so an unknown name is answered
# as a bad contract rather than as a crash.


def task_types() -> tuple[CatalogTaskType, ...]:
    """Every task type the catalog declares, in its own order."""
    return catalog().task_types


def operations() -> tuple[CatalogTaskType, ...]:
    """Every deterministic operation: work a tool performs instead of a model."""
    return catalog().operations


def task_type_names() -> tuple[str, ...]:
    """The names of every task type — the valid choices for `task_type`."""
    return catalog().names


def operation_names() -> tuple[str, ...]:
    """The names of every operation — the valid choices for `operation`."""
    return tuple(t.name for t in catalog().operations)


def task_type(name: str) -> CatalogTaskType:
    """The entry for `name`, or a schema error saying it is not a task type."""
    try:
        return catalog().require(name)
    except CatalogError as exc:
        raise ContractSchemaError(f"task_type: {exc}") from exc


def kind_of(task_type_name: str, operation: str = "") -> CatalogTaskType:
    """What a contract runs: the operation when one is named, else the task type."""
    if not operation:
        return task_type(task_type_name)
    try:
        return catalog().require_operation(operation)
    except CatalogError as exc:
        raise ContractSchemaError(f"operation: {exc}") from exc


# Evidence is derived from what the contract states, never declared by the
# author: the commands and flags that are set decide the list, and `gate` comes
# first because every judged contract produces it. `failing_test_first` follows
# when a demonstration command is given, `tests_pass` when an acceptance command
# is, and `no_semantic_change` and `type_check` when their flags are on. Kinds
# that are not `evidence_derived` — sessions, which write nothing — know their
# evidence from the catalog and are returned exactly as it lists them. The order matters
# downstream: the gate records evidence in it, and a result whose names differ
# from `Contract.evidence_names` is a mismatch rather than something to take at
# face value. Nothing here reads a contract, only these flags, so the same
# derivation serves one that is planned but not yet built.


def evidence_for(
    kind: CatalogTaskType,
    *,
    acceptance: tuple[str, ...] = (),
    demonstration: tuple[str, ...] = (),
    no_semantic_change: bool = False,
    type_check: bool = False,
) -> tuple[CatalogEvidence, ...]:
    """The catalog evidence this kind implies for these commands and flags."""
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
    """A ready-made stop condition, quoted to a worker that must not guess."""
    return (
        f"{task_type_name} on {subject} would require deciding something the "
        "contract does not state — report BLOCKED rather than guess"
    )


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

#: The attempts a contract allows each rung when its `limits.attempts` is unset.
DEFAULT_ATTEMPTS = 2

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
        default=DEFAULT_ATTEMPTS,
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
        "small-model failure mode these exist to prevent. A `prose` reply is "
        "served whatever it says, so none is required there. Start from "
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
        "raw-text answer for chat and agent (their default). `unified_diff` "
        "validates here and is refused before dispatch.",
        default="whole_file",
        choices=("whole_file", "prose", "unified_diff"),
        worker_facing=True,
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


# The parsed contract. `_build` is the only place a validated document becomes
# one of these, so the fields below are always filled and already checked.


@dataclass(frozen=True)
class Dependency:
    """One dependency handed to the worker as a signature, never as source."""

    path: str
    signature: str
    note: str = ""


@dataclass(frozen=True)
class Rename:
    """What `rename_symbol` is told: the symbol today, and the name it becomes."""

    old: str = ""
    new: str = ""

    @property
    def stated(self) -> bool:
        return bool(self.old and self.new)


@dataclass(frozen=True)
class Verification:
    """How the change is judged once the gate has passed."""

    policy: str


@dataclass(frozen=True)
class Limits:
    """What one execution may spend: the reply cap, retries, the window share."""

    max_output_tokens: int | None
    attempts: int
    #: The contract's own share of the model's window: the assembled prompt plus
    #: `max_output_tokens`, over the whole window. `None` records that the contract
    #: declared none, which is not the same as 1.0 — the run's own cap still applies
    #: on top, and the stricter of the two wins.
    max_window_fraction: float | None = None


@dataclass(frozen=True)
class Contract:
    """One validated unit of work, with the schema's nested keys flattened onto it."""

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
    #: The text of each entry in `sources`, in that order, filled in when the
    #: contract is dispatched against a workspace rather than parsed from a
    #: document. It is empty, or of another length, when the sources were never
    #: read: `worker_view` then reports no content and the worker reads each file
    #: from the tree it is given.
    source_content: tuple[str, ...] = ()

    @property
    def type(self) -> CatalogTaskType:
        """The task type `task_type` names, ignoring any `operation` beside it."""
        return catalog().require(self.task_type)

    @property
    def kind(self) -> CatalogTaskType:
        """What runs: the operation when one is named, otherwise the task type."""
        return kind_of(self.task_type, self.operation)

    @property
    def evidence(self) -> tuple[CatalogEvidence, ...]:
        """The evidence this contract's commands and flags derive, in gate order."""
        return evidence_for(
            self.kind,
            acceptance=self.acceptance,
            demonstration=self.demonstration,
            no_semantic_change=self.no_semantic_change,
            type_check=self.type_check,
        )

    @property
    def evidence_names(self) -> tuple[str, ...]:
        """The names of `evidence`, for checking what a result reported back."""
        return tuple(e.name for e in self.evidence)

    @property
    def is_deterministic(self) -> bool:
        """Whether a tool performs the work rather than a model."""
        return self.kind.deterministic

    @property
    def is_session(self) -> bool:
        """Whether this is a session: the reply is the answer, nothing is written."""
        return self.kind.session

    @property
    def needs_output_cap(self) -> bool:
        """Whether `limits.max_output_tokens` must be stated for this work."""
        return self.kind.needs_output_cap

    @property
    def acceptance_commands(self) -> tuple[tuple[str, ...], ...]:
        """The acceptance commands split into argv, as they will be executed."""
        return tuple(tuple(shlex.split(command)) for command in self.acceptance)

    @property
    def demonstration_commands(self) -> tuple[tuple[str, ...], ...]:
        """The demonstration commands split into argv, as they will be executed."""
        return tuple(tuple(shlex.split(command)) for command in self.demonstration)

    @property
    def prose(self) -> str:
        """The task and the interface as one block of text, for a reader of prose."""
        return f"{self.task}\n{self.interface}"

    def worker_view(self) -> dict[str, Any]:
        """The fields the worker is shown, as data — never scope, commands or limits."""
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
        """The contract as schema keys, so `parse(dumps(c))` round-trips it."""
        stated = {"depends_on": sorted(self.depends_on)} if self.depends_on else {}
        # `rename` is written only when both halves are stated: a half-stated pair
        # names nothing, and emitting it would turn a contract that says nothing
        # about renaming into one that claims to.
        renamed = (
            {"rename": {"from": self.rename.old, "to": self.rename.new}}
            if self.rename.stated
            else {}
        )
        # An unset `max_window_fraction` is not a default to be filled in: "the
        # contract declared no share" is a different statement from 1.0, so the key
        # is left out rather than written with a number nobody asked for. The same
        # holds for every optional key below.
        share = (
            {"max_window_fraction": self.limits.max_window_fraction}
            if self.limits.max_window_fraction is not None
            else {}
        )
        # Flags likewise: a key appears only when the contract asked for that check,
        # so its presence in the output always means the author turned it on.
        flags: dict[str, bool] = {}
        if self.no_semantic_change:
            flags["no_semantic_change"] = True
        if self.type_check:
            flags["type_check"] = True
        return {
            "version": self.version,
            "id": self.id,
            "task_type": self.task_type,
            # `operation` appears only when one is named: writing "" would name an
            # operation that does not exist, and absent means the task type alone.
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


# Reading a contract: from a file and from text, both through the same pipeline.


def load(path: Path) -> Contract:
    """Read and parse the file at `path`, reporting an unreadable one as an error."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractFileError(f"{path}: cannot be read ({exc.strerror}).") from exc
    return parse(text, path=path)


def loads(text: str) -> Contract:
    """Parse contract text that has no file name, so errors name only the field."""
    return parse(text)


def parse(text: str, path: Path | None = None) -> Contract:
    """Parse a document: strict YAML, `SCHEMA`, then the cross-field rules."""
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
        # A session's reply is the answer itself, so prose is the shape it is
        # given when the author says nothing; anything file-shaped is refused below.
        data["output_schema"] = "prose"
    _cross_validate(data)
    return _build(data)


def dumps(contract: Contract) -> str:
    """Render the contract as JSON text under the key names `parse` accepts."""
    return json.dumps(contract.as_dict(), indent=2)


def _build(data: Mapping[str, Any]) -> Contract:
    """Build a `Contract` from validated block data, flattening the nested keys."""
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


# The schema walk: every block is validated against its own `Field` table, one key
# at a time, so the error for a bad key can name the path that reached it.


def _block(raw: object, fields: tuple[Field, ...], path: str) -> dict[str, Any]:
    """Validate one block: defaults filled in, unknown and missing keys refused."""
    return walk_block(raw, fields, path, _DIALECT)


def _value(raw: object, spec: Field, path: str) -> Any:
    """Coerce one raw value by the field's `kind`, leaving the rules to the helpers."""
    if spec.kind == "int":
        return _int(raw, spec, path)
    if spec.kind == "float":
        return _float(raw, spec, path)
    if spec.kind == "bool":
        if not isinstance(raw, bool):
            raise ContractSchemaError(f"{path}: must be true or false, got {raw!r}.")
        return raw
    if spec.kind == "str":
        # Only an optional string may be blank: "" is a real value for keys like
        # `interface`, while a required one that is empty was left unfilled and is
        # refused rather than accepted as an empty promise.
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
    raise AssertionError(f"unhandled kind {spec.kind!r}")  # pragma: no cover


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
    # `bool` is a subclass of `int`, so it is refused before the numeric check; a
    # whole number is accepted and widened, since YAML need not write `1.0`.
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
    """Refuse a scope pattern that is absolute or climbs out with `..`."""
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
    """Whether the document names a session type, which decides the schema walked."""
    if not isinstance(raw, Mapping):
        return False
    name = raw.get("task_type")
    if not isinstance(name, str):
        return False
    return name in task_type_names() and task_type(name).session


def _for_sessions(fields: tuple[Field, ...]) -> tuple[Field, ...]:
    """The schema with `session_optional` fields made optional, nested blocks too."""
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


_join = join_path

#: The contract's half of the schema walk.
_DIALECT = Dialect(
    noun="contract",
    error=ContractSchemaError,
    mapping=_mapping,
    value=_value,
    missing=_missing,
    default_for=_default_for,
)


# Commands are split like a shell but run without one, so whatever a shell would
# have interpreted is refused here rather than reaching the program as a surprise
# argument.


def _check_command(command: str, path: str) -> None:
    """Refuse a command a shell-less run would not execute as its author meant."""
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
    """The operator characters left unquoted in `command`, or `None`."""
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
    """The rules spanning several fields, run after the schema walk on flat data."""
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
        # A session's reply is the answer, returned in the result file and kept in
        # the session log, never written to a target — so a file-shaped
        # `output_schema` names a protocol the run cannot honour.
        if data["output_schema"] != "prose":
            raise ContractSchemaError(
                f"output_schema: {data['output_schema']!r} is a file-shaped "
                f"reply, but a {kind.name!r} run is a session: its reply is the "
                f"answer, returned in the result file and kept in the session "
                f"log, never written. Drop output_schema; 'prose' is the "
                f"default."
            )
        # A session is a raw connection to a model: mcgyvr sends no output cap and
        # makes no prompt or window check, so a stated cap would be a promise the
        # run does not keep. Refused rather than ignored, because an ignored key is
        # a contract that does not do what it says.
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

    # `whole_file` is the reply shape whose refusal escalates: a model that meets
    # something the contract never stated either stops or guesses, and a guess is
    # applied straight to the target. So a model-written whole-file contract must
    # name at least one condition that sends it to BLOCKED instead.
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

    _check_sources(data["sources"])

    # `depends_on` is checked for shape, not for existence: the ids may name
    # contracts written later, so only the ones that could never be satisfied —
    # this contract's own id, an unusable id, a repeat — are refused here. Whether
    # a dependency exists at all is a question for the plan.
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

    # A repeat in `deps` is caught by path rather than by content: two entries for
    # one file would put the same signature in the prompt twice and pad it. What
    # is left is answered at dispatch, not from text: whether each `sources` entry
    # exists, is text and is not a secret, what `target_content` becomes when the
    # contract left it empty, and whether `limits` fits the unit the run reaches.
    # None of those can be settled here, and refusing a contract for something a
    # later stage can report with a better message would only move the error
    # somewhere less useful.


def _check_sources(sources: Sequence[str]) -> None:
    """Check `sources`: repo-relative literal files, each named once."""
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
    """Check the target against the scope: literal or pattern by tier, and writable."""
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
