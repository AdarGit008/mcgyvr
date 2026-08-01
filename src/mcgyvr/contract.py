"""The task contract: the boundary between the calling agent and mcgyvr.

In delegated mode a contract is an internal artifact the orchestrator produces.
In direct mode it is **public API an agent authors** — which makes its schema,
its validation errors and its guarantees a compatibility surface from v1
onward (#13). Both modes go through the one loader here, so "a contract the
orchestrator emits is one the direct-mode API accepts" is a property of there
being a single definition, not a promise maintained in two places.

Five things are load-bearing, and each is enforced at load rather than
discovered later:

1. **Every rejection names the field and the fix.** This is API surface for an
   agent, so an unparseable rejection is a defect: a caller that cannot tell
   which key was wrong cannot correct it. Errors here read
   ``path.to.key: what is wrong. What a valid value looks like.``
2. **Unknown keys fail.** A silently ignored key is a contract that does
   something other than what it says — the same rule :mod:`mcgyvr.config`
   holds for the config file, for the same reason.
3. **Self-contradiction is rejected at load, not at execution.** A target its
   own scope forbids, a pattern that is both allowed and forbidden, a scope
   that permits nothing: each fails here, naming the contradiction, rather
   than failing mysteriously mid-task once a rung has already been spent.
4. **Single-target discipline.** A model worker's output has exactly one
   literal destination. A glob-scoped target is legal only for task types the
   deterministic tier can execute outright, because only those can fan a
   change across files without a model guessing where its output goes.
5. **A type's required evidence must be producible.** The catalog states what
   evidence each task type needs to be judgeable at all; where that evidence
   can only come from running something, a contract declaring no acceptance
   commands is rejected. A `bug_fix` with nothing to run does not fail — it
   gets accepted on the gate alone, which is worse.

The field layout follows the split #94 arrived at from small-model research:
worker-facing fields (``task``, ``target``, ``deps``, ``interface``,
``stop_conditions``, ``output_schema``, ``context``) are separated from
orchestrator-only ones (``risk``, ``verification``, ``attempts``,
``acceptance``), and :meth:`Contract.worker_view` is the only way to reach the
former. Building the flat shape first and splitting it later was the rework
#94 exists to describe, so the split is here from the start.

``SCHEMA`` below is declarative data, not hand-written checks — the same
approach :mod:`mcgyvr.config` takes, so the authoring guide (#18) can be
rendered from the definitions the validator walks rather than written beside
them. The ``Field`` type is deliberately *not* shared with the config schema:
the two validate different documents with different value kinds (a config has
credentials and URLs; a contract has globs and token budgets), and coupling
them would make every contract key answerable to a config concern. What is
emphatically *not* duplicated is path matching — every scope decision here
goes through :class:`mcgyvr.scope.Scope`, the one canonical matcher.

The task-type vocabulary is **not defined here**. :mod:`mcgyvr.catalog` reads it
from ``data/task-catalog.json`` (#15), and this module asks the catalog what a
type guarantees rather than knowing any type by name — which is what keeps
"adding a task type does not require a code change" true of this file too. Two
of the catalog's properties are load-bearing here: ``deterministic`` decides the
glob rule above, and ``needs_acceptance_commands`` decides rule 5.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from mcgyvr.catalog import CatalogError, catalog
from mcgyvr.catalog import TaskType as CatalogTaskType
from mcgyvr.scope import Scope

SCHEMA_VERSION = 1

# Characters that make a path a pattern rather than a destination. A target
# containing any of these names a set of files, not a file, which is why the
# single-target rule keys on them.
_GLOB_META = re.compile(r"[*?\[]")

# A contract id: something a record, a log line and a branch name can all carry
# without quoting. Deliberately narrow — an id is a join key, not prose.
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ContractError(Exception):
    """Base class for every contract failure."""


class ContractFileError(ContractError):
    """The contract is missing, unreadable, or not parseable."""


class ContractSchemaError(ContractError):
    """The contract parsed, but does not satisfy the schema.

    Every message names the offending field and says what a valid value looks
    like. That is the acceptance criterion for this class, not a stylistic
    preference: the reader is an agent trying to correct its own output.
    """


# --- the task-type vocabulary (owned by mcgyvr.catalog / #15) --------------

# Re-exported so a caller validating a contract does not need to know the
# catalog exists. These are thin views over the loaded catalog, computed once,
# and NOT a second definition — nothing here names a task type.


def task_types() -> tuple[CatalogTaskType, ...]:
    """Every task type the catalog declares."""
    return catalog().task_types


def task_type_names() -> tuple[str, ...]:
    return catalog().names


def task_type(name: str) -> CatalogTaskType:
    """The declared task type called ``name``.

    Raises :class:`ContractSchemaError` naming the vocabulary, because an
    unknown task type is exactly the case where a caller needs to see the valid
    set rather than a boolean. The catalog raises its own error type; it is
    translated here so that everything a contract can be rejected for is one
    exception family.
    """
    try:
        return catalog().require(name)
    except CatalogError as exc:
        gone = catalog().excluded_entry(name)
        if gone is not None:
            hint = f" Use {gone.superseded_by!r} instead." if gone.superseded_by else ""
            raise ContractSchemaError(
                f"task_type: {name!r} is not in the vocabulary. {gone.reason}{hint}"
            ) from exc
        raise ContractSchemaError(f"task_type: {exc}") from exc


# --- the declared schema --------------------------------------------------

Kind = Literal[
    "int",
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
    """One key in the contract schema, with what is needed to validate and document it.

    ``doc`` has no default: a key that cannot be explained does not belong in
    a surface an agent is asked to author against. ``worker_facing`` marks the
    keys :meth:`Contract.worker_view` may expose — the split is declared on the
    schema so it cannot drift from the prompt builder that honours it.

    ``choices_from`` is for an enum whose valid set is owned elsewhere — today
    only ``task_type``, whose vocabulary lives in the catalog. Resolving it per
    validation rather than freezing it into ``choices`` at import is what makes
    "adding a task type does not require a code change" true: a snapshot taken
    when this module was imported would be a copy of the catalog living in code,
    which is the thing #15 forbids.
    """

    name: str
    kind: Kind
    doc: str
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    block: tuple[Field, ...] = ()
    min_value: int | None = None
    worker_facing: bool = False
    hint: str = ""
    choices_from: Callable[[], tuple[str, ...]] | None = None

    def valid_choices(self) -> tuple[str, ...]:
        """The enum's valid set, resolved now rather than at import."""
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
        "body. Hierarchical context pruning measured signature-only "
        "dependency context as improving accuracy while cutting context "
        "roughly sixfold (#94, #96): a body invites copying, a signature "
        "states the interface.",
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
        "will not fit is a contract-level failure, caught before a rung is "
        "spent.",
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
        "How the change is judged. `gate_only` accepts on the deterministic "
        "gate alone — the whole acceptance bar in a keyless install. `model` "
        "additionally requires a fresh-context verifier to agree.",
        default="gate_only",
        choices=("gate_only", "model"),
    ),
)

LIMITS_FIELDS: tuple[Field, ...] = (
    Field(
        "max_output_tokens",
        "int",
        "Hard cap on the worker's reply, enforced in the runner. A reply cut "
        "off at the cap is a named failure and is never applied to a file. "
        "Deriving this from the target's own content is #17; the schema only "
        "requires that a contract carry one.",
        default=1024,
        min_value=1,
    ),
    Field(
        "attempts",
        "int",
        "How many times a rung may be retried before escalating. Retrying "
        "forever on one rung is how a cheap task becomes an expensive one.",
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
        hint="e.g. fetch-helper-retry",
    ),
    Field(
        "task_type",
        "enum",
        "What kind of work this is, from the declared vocabulary. The type "
        "decides whether the deterministic tier can execute the contract "
        "outright, and therefore whether a glob target is legal.",
        required=True,
        choices_from=task_type_names,
        worker_facing=True,
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
        "any task type a model executes — a model worker's output has one "
        "destination, and a pattern would leave it guessing. A glob is legal "
        "only for a task type the deterministic tier executes outright.",
        required=True,
        worker_facing=True,
        hint="e.g. src/pkg/fetch.py",
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
        "directive. Required for any task type a model executes: guessing is "
        "the documented small-model failure mode these exist to prevent "
        "(#94), and a worker with no stated stop condition has no licence to "
        "refuse.",
        default=(),
        worker_facing=True,
    ),
    Field(
        "output_schema",
        "enum",
        "The shape the worker must reply in, declared so a runner can hand "
        "the model format instructions rather than hoping for a convention. "
        "`whole_file` is the single-file output protocol; `unified_diff` is a "
        "patch against the target.",
        default="whole_file",
        choices=("whole_file", "unified_diff"),
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
    ),
    Field(
        "acceptance",
        "str_list",
        "Shell commands that must pass for the change to be accepted — the "
        "strongest signal the gate has. Arbitrary shell from a contract, so "
        "they run inside the per-task sandbox, never on the host.",
        default=(),
    ),
    Field(
        "risk",
        "enum",
        "How much a wrong answer costs. A floor on how cheap the work may "
        "start and how cheaply it may be verified, never a preference. "
        "Deterministic classification from type, prompt and scope is #16; a "
        "declared value may raise that classification, never lower it.",
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
)


# --- the loaded contract --------------------------------------------------


@dataclass(frozen=True)
class Dependency:
    """One dependency, carried as a signature rather than as source."""

    path: str
    signature: str
    note: str = ""


@dataclass(frozen=True)
class Verification:
    """How a change is judged once the deterministic gate has passed."""

    policy: str


@dataclass(frozen=True)
class Limits:
    """Hard ceilings on one execution of a contract."""

    max_output_tokens: int
    attempts: int


@dataclass(frozen=True)
class Contract:
    """A validated unit of work: what to do, where it goes, and how it is judged.

    Immutable, and valid by construction — every instance came through
    :func:`parse`, so nothing downstream re-checks what the loader already
    settled. Build one with :func:`parse`, :func:`loads` or :func:`load`.
    """

    id: str
    task_type: str
    task: str
    target: str
    scope: Scope
    version: int = SCHEMA_VERSION
    interface: str = ""
    deps: tuple[Dependency, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    output_schema: str = "whole_file"
    max_input_tokens: int = 4096
    acceptance: tuple[str, ...] = ()
    risk: str = "medium"
    verification: Verification = Verification("gate_only")
    limits: Limits = Limits(1024, 2)

    @property
    def type(self) -> CatalogTaskType:
        """The declared task type, as its catalog entry."""
        return catalog().require(self.task_type)

    @property
    def is_deterministic(self) -> bool:
        """Whether the deterministic tier can execute this contract outright."""
        return self.type.deterministic

    def worker_view(self) -> dict[str, Any]:
        """Exactly the fields a worker prompt may be built from.

        The one way to reach worker-facing content, so "orchestrator-only
        fields never reach the worker prompt" (#94) is enforced by there being
        no other accessor rather than by reviewing every prompt builder. What
        is excluded is excluded on purpose: ``risk``, ``verification``,
        ``acceptance`` and ``limits`` are how the *orchestrator* decides where
        to run the work and whether to believe the result, and a worker that
        could read them could argue with them.
        """
        return {
            "id": self.id,
            "task_type": self.task_type,
            "task": self.task,
            "target": self.target,
            "interface": self.interface,
            "deps": [
                {"path": d.path, "signature": d.signature, "note": d.note}
                for d in self.deps
            ],
            "stop_conditions": list(self.stop_conditions),
            "output_schema": self.output_schema,
            "context": {"max_input_tokens": self.max_input_tokens},
        }

    def as_dict(self) -> dict[str, Any]:
        """The whole contract as plain data, in schema declaration order.

        Round-trips: ``parse(dumps(c))`` reconstructs ``c``. That is what makes
        "a contract the orchestrator emits is one the direct-mode API accepts"
        testable rather than asserted.
        """
        return {
            "version": self.version,
            "id": self.id,
            "task_type": self.task_type,
            "task": self.task,
            "target": self.target,
            "interface": self.interface,
            "deps": [
                {"path": d.path, "signature": d.signature, "note": d.note}
                for d in self.deps
            ],
            "stop_conditions": list(self.stop_conditions),
            "output_schema": self.output_schema,
            "context": {"max_input_tokens": self.max_input_tokens},
            "scope": {
                "allow": list(self.scope.allow),
                "forbid": list(self.scope.forbid),
            },
            "acceptance": list(self.acceptance),
            "risk": self.risk,
            "verification": {"policy": self.verification.policy},
            "limits": {
                "max_output_tokens": self.limits.max_output_tokens,
                "attempts": self.limits.attempts,
            },
        }


# --- loading --------------------------------------------------------------


class _StrictLoader(yaml.SafeLoader):
    """A YAML loader that refuses duplicate keys.

    PyYAML's default silently keeps the last of a repeated key, which in a
    contract means a scope or a limit quietly overriding an earlier one. The
    same guard :mod:`mcgyvr.config` applies to the config file.
    """


def _no_duplicates(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ContractSchemaError(
                f"{key!r}: duplicate key. A repeated key silently overrides "
                f"the first, so the contract would not do what it reads as."
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates
)


def load(path: Path) -> Contract:
    """Read and validate the contract at ``path``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractFileError(f"{path}: cannot be read ({exc.strerror}).") from exc
    return parse(text, path=path)


def loads(text: str) -> Contract:
    """Validate a contract from YAML or JSON text (YAML is a JSON superset)."""
    return parse(text)


def parse(text: str, path: Path | None = None) -> Contract:
    """Validate a contract, naming the offending field on any failure."""
    where = f"{path}: " if path else ""
    try:
        raw = yaml.load(text, Loader=_StrictLoader)
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

    data = _block(raw, SCHEMA, "")
    _cross_validate(data)
    return _build(data)


def dumps(contract: Contract) -> str:
    """The contract as JSON, in schema order — the emitted form of the API."""
    return json.dumps(contract.as_dict(), indent=2)


def _build(data: Mapping[str, Any]) -> Contract:
    """Assemble the validated mapping into a Contract."""
    return Contract(
        id=data["id"],
        task_type=data["task_type"],
        task=data["task"],
        target=data["target"],
        scope=Scope.of(data["scope"]["allow"], data["scope"]["forbid"]),
        version=data["version"],
        interface=data["interface"],
        deps=tuple(
            Dependency(path=d["path"], signature=d["signature"], note=d["note"])
            for d in data["deps"]
        ),
        stop_conditions=tuple(data["stop_conditions"]),
        output_schema=data["output_schema"],
        max_input_tokens=data["context"]["max_input_tokens"],
        acceptance=tuple(data["acceptance"]),
        risk=data["risk"],
        verification=Verification(policy=data["verification"]["policy"]),
        limits=Limits(
            max_output_tokens=data["limits"]["max_output_tokens"],
            attempts=data["limits"]["attempts"],
        ),
    )


# --- schema walking -------------------------------------------------------


def _block(raw: object, fields: tuple[Field, ...], path: str) -> dict[str, Any]:
    """Validate one mapping against its declared fields."""
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
    """One value, validated against its field's kind."""
    if spec.kind == "int":
        return _int(raw, spec, path)
    if spec.kind == "bool":
        if not isinstance(raw, bool):
            raise ContractSchemaError(f"{path}: must be true or false, got {raw!r}.")
        return raw
    if spec.kind == "str":
        # An optional string may be empty: "" is how "not stated" round-trips
        # through the emitted form. A required one may not — an empty `task`
        # is a contract with nothing to do.
        return _str(raw, path, allow_empty=not spec.required)
    if spec.kind == "enum":
        text = _str(raw, path)
        valid = spec.valid_choices()
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
    return raw


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
    """Reject a pattern that cannot mean what its author intended."""
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


# --- self-contradiction ---------------------------------------------------


def _cross_validate(data: Mapping[str, Any]) -> None:
    """Reject contracts that satisfy the schema but contradict themselves.

    Each check here is a failure that would otherwise surface mid-task, after
    a rung had already been spent on work that could never have been accepted.
    """
    identity = data["id"]
    if not _ID.match(identity):
        raise ContractSchemaError(
            f"id: {identity!r} is not a usable identity. Use letters, digits, "
            f"dot, dash or underscore, starting with a letter or digit, up to "
            f"64 characters."
        )

    kind = task_type(data["task_type"])
    target = data["target"]
    allow = data["scope"]["allow"]
    forbid = data["scope"]["forbid"]

    if not allow:
        raise ContractSchemaError(
            "scope.allow: is empty, which permits nothing — the contract "
            "could not change a single file. Name at least one pattern the "
            "worker may touch."
        )

    _check_glob(target, "target")
    if _GLOB_META.search(target) and not kind.deterministic:
        raise ContractSchemaError(
            f"target: {target!r} is a pattern, but task type "
            f"{kind.name!r} runs on a model, whose output has exactly one "
            f"destination. Name a single literal path, or use a task type the "
            f"deterministic tier executes "
            f"({', '.join(t.name for t in task_types() if t.deterministic)})."
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

    if not kind.deterministic and not data["stop_conditions"]:
        raise ContractSchemaError(
            f"stop_conditions: is empty, but task type {kind.name!r} runs on "
            f"a model. Without a stated trigger to report BLOCKED, a worker "
            f"that meets an unknown will guess. Name at least one condition."
        )

    if kind.needs_acceptance_commands and not data["acceptance"]:
        needed = ", ".join(e.name for e in kind.required_evidence if e.needs_commands)
        raise ContractSchemaError(
            f"acceptance: is empty, but task type {kind.name!r} requires "
            f"evidence only a command can produce ({needed}). Its guarantee is "
            f'"{kind.guarantee}" — with nothing to run, a change would be '
            f"accepted on the gate alone and the guarantee would be unbacked. "
            f"Name at least one command that demonstrates it."
        )

    seen: set[str] = set()
    for index, dep in enumerate(data["deps"]):
        if dep["path"] in seen:
            raise ContractSchemaError(
                f"deps.{index}.path: {dep['path']!r} appears more than once. "
                f"One signature per dependency — a second entry would silently "
                f"pad the prompt."
            )
        seen.add(dep["path"])

    if data["limits"]["max_output_tokens"] > data["context"]["max_input_tokens"]:
        raise ContractSchemaError(
            f"limits.max_output_tokens: {data['limits']['max_output_tokens']} "
            f"exceeds context.max_input_tokens "
            f"({data['context']['max_input_tokens']}). A reply larger than the "
            f"whole prompt budget cannot be assembled into a next attempt."
        )
