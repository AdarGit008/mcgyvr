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
5. **A type's required evidence must be producible — each kind by the list
   that can satisfy it.** The catalog states what evidence each task type
   needs to be judgeable at all; where that evidence can only come from
   running something, the contract must carry a command *in the right slot*:
   evidence expecting a pass at baseline needs ``acceptance``, evidence
   expecting a failure at baseline (``failing_test_first``) needs
   ``demonstration``. The one exception is ``code``, whose evidence is
   derived from the contract's own fields rather than demanded: a ``code``
   contract with no ``acceptance``, no ``demonstration`` and no flags is
   judged on the gate alone, which is its honest floor.

The field layout follows the split #94 arrived at from small-model research:
worker-facing fields (``id``, ``task_type``, ``task``, ``target``,
``target_content``, ``interface``, ``deps``, ``stop_conditions``,
``output_schema``, ``sources``, ``context``) are separated from orchestrator-only ones
(``scope``, ``acceptance``, ``demonstration``, ``depends_on``, ``risk``,
``verification``, ``limits``, ``rename``), and :meth:`Contract.worker_view` is
the only way to reach the former.

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
"adding a task type does not require a code change" true of this file too. What
this module reads off a catalog entry: ``deterministic`` (the glob rule above,
the stop-condition rule, the output cap), ``needs_acceptance_commands`` /
``needs_demonstration_commands`` (the two halves of rule 5), and
``required_evidence`` (the output cap and the refusal text).
"""

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

# Characters that make a path a pattern rather than a destination. A target
# containing any of these names a set of files, not a file, which is why the
# single-target rule keys on them. A ``]`` alone opens nothing: a glob, a
# shell and a git pathspec all read it as the character it is.
_GLOB_META = re.compile(r"[*?\[]")


def is_pattern(target: str) -> bool:
    """Whether ``target`` names a set of files rather than one file.

    The one answer: the loader refuses a pattern target by it and delivery
    re-checks by it, so a target the loader takes as one file is one file at
    the delivery seam too.
    """
    return _GLOB_META.search(target) is not None


# A contract id: something a record, a log line and a branch name can all carry
# without quoting. Deliberately narrow — an id is a join key, not prose.
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# A leading ``NAME=value`` word. A shell reads it as an assignment for the
# command after it; executed with no shell it is the program's name.
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# The characters a POSIX shell reads as an operator when unquoted: the list
# separators, the pipe and the redirects. Executed with no shell, each one is
# handed to the program as an argument instead.
_SHELL_OPERATOR_CHARS = frozenset("&|;<>")


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
    """Every task type the catalog declares (the model vocabulary)."""
    return catalog().task_types


def operations() -> tuple[CatalogTaskType, ...]:
    """The deterministic operations the catalog declares.

    Not task types: a contract asks for one as ``operation`` beside the task
    type the operation names (``task_type: code``), and the product runs it
    with a tool rather than a model.
    """
    return catalog().operations


def task_type_names() -> tuple[str, ...]:
    """Every task type the catalog declares — the whole vocabulary."""
    return catalog().names


def operation_names() -> tuple[str, ...]:
    """Every name a contract may carry as ``operation``."""
    return tuple(t.name for t in catalog().operations)


def task_type(name: str) -> CatalogTaskType:
    """The declared task type called ``name``.

    Raises :class:`ContractSchemaError` naming the vocabulary, because an
    unknown task type is exactly the case where a caller needs to see the valid
    set rather than a boolean, and naming the replacement for a name that used
    to be a task type. The catalog raises its own error type; it is translated
    here so that everything a contract can be rejected for is one exception
    family.
    """
    try:
        return catalog().require(name)
    except CatalogError as exc:
        raise ContractSchemaError(f"task_type: {exc}") from exc


def kind_of(task_type_name: str, operation: str = "") -> CatalogTaskType:
    """The catalog entry that governs a contract: its operation's, or its type's.

    A contract that names an ``operation`` is run, routed, capped and judged by
    that operation's entry — its starting family, its guarantee, its evidence —
    and one that names none by its task type's.
    """
    if not operation:
        return task_type(task_type_name)
    try:
        return catalog().require_operation(operation)
    except CatalogError as exc:
        raise ContractSchemaError(f"operation: {exc}") from exc


# --- the output cap -------------------------------------------------------

# What a reply may cost, in tokens, before anything is known about the file it
# lands in. One number for every task type is wrong for at least one of them:
# too small truncates a reply into a named failure that costs a whole attempt,
# too large steals context from the prompt that would have made the reply
# right, and a docstring and a function written from nothing cannot both be
# served by the same number.
#
# Keyed by what the catalog says a type must *prove*, never by the type's name.
# A table of names here would be the second definition of the vocabulary that
# :mod:`mcgyvr.catalog` exists to prevent, and adding a task type would mean
# editing this file to give it a cap. Required evidence is the honest key
# because it is already a statement about the reply: evidence a structural
# check can read is evidence about prose or a shape, and evidence only a
# command can produce is evidence about behaviour — which has to be written
# before it can run.
#
# Two steps and not more, because two is as far as the catalog's properties
# actually distinguish. Every type whose required evidence needs a command
# must write what that command will judge, and under `whole_file` each re-emits
# the file around it, so a third number among them would be a preference
# wearing a budget's clothes.
#
# The numbers below are the product's defaults: chosen rather than measured,
# and generous on purpose. An unspent cap costs nothing, while truncation costs
# a whole attempt; a reply that overflows a generous cap is a task too big for
# one contract, which is a re-decomposition and not a larger number.
#
# They are the floor of the automatic cap (`auto_reply_cap`, below): what the
# loader fills in for a whole_file contract that states no cap, the visible
# reply a task type needs before the target's own size is counted. A raw-text
# reply (prose / media_artifact) carries no cap and gets no floor.
#
# Nor are they the last word. A contract states its own cap with
# `limits.max_output_tokens`, and a unit that declares
# `units.<name>.output_tokens` sends that number in place of a stated cap, and
# bounds the automatic one (`mcgyvr.gate.preflight.reply_cap`). A relief rung
# (another person's unit, ridden when the rider's own is full) is sent the
# smaller of the contract's cap and the local unit's, and the local unit's
# where the contract has none.
#
# A cap derived here for a contract loaded from text is not part of that
# contract's emitted form: `dumps` writes `null` for it, so changing these
# numbers moves the identity of no such contract. A declared cap is emitted and
# is part of the identity, and so is the cap of a contract built in code, whose
# dataclass default counts as declared.
STRUCTURAL_ALLOWANCE = 512
"""Nothing to run: the reply is prose, or an edit a parser can check."""

RUNNING_ALLOWANCE = 1024
"""A command has to run afterwards, so behaviour has to be written."""

# A file that does not exist yet arrives with its declarations as well as its
# body — the imports, the def line, the module docstring — so creating one is a
# step dearer than editing one that is already there.
NEW_FILE_STEP = 512

# Caps come out as whole steps, never below the floor. The floor is what a
# deterministic operation gets; the allowances above are already whole steps.
CAP_STEP = 128
MIN_CAP = 256

# --- the automatic cap ----------------------------------------------------
#
# A contract that states no cap is sized per attempt, once the target's
# content is in hand, by `auto_reply_cap`. Two terms, because a reply now holds
# two things and only one of them is ever seen.
#
# The visible reply re-emits the whole file (`whole_file`), so it grows with
# the target: the floor above for what the change adds, plus REWRITE_FACTOR
# times the target's estimated tokens (`mcgyvr.orchestrator.read.
# estimate_tokens`, the one proxy every budget spends against). Two, not one:
# the file once, the proxy's measured under-count on top
# (`mcgyvr.gate.preflight.ESTIMATE_RESERVE`, 0.32), and room for the file to
# grow. A target that does not exist yet has no size and takes NEW_FILE_STEP
# instead, for the declarations a new file arrives with.
#
# The hidden reply is the reasoning a hosted reasoning model spends before it
# writes. It is billed against the same `max_tokens` and never read, so a cap
# sized for the visible reply alone comes back empty. The e2e run of
# 2026-10-13 measured it on DeepSeek: a 1024 cap returned an empty reply on
# both rungs for a small new module, 4096 returned an empty reply on both for a
# duration parser, and the dearer rung finished that parser in 16216 output
# tokens of a 16384 cap, almost all of it reasoning (the cheaper rung finished
# the small module in 599). REASONING_ALLOWANCE is that 16216 with half again on
# top, in whole steps: the worst case seen, with room for a harder one. A model
# that does not reason stops when its file is written, and an unspent cap costs
# nothing on the wire; where it would cost window, the dispatch trims this term
# (and only this one) to what the window leaves
# (`mcgyvr.gate.preflight.reply_cap`).
REWRITE_FACTOR = 2
REASONING_ALLOWANCE = 24576


@dataclass(frozen=True)
class AutoCap:
    """The two halves of an automatic cap, and how they were reached.

    ``visible`` is the room the written file needs; ``reasoning`` the hidden
    allowance on top. Kept apart because only ``reasoning`` may be trimmed to
    fit a window: a visible reply that does not fit is a contract too big for
    the rung, which a fit check refuses by name rather than a cap that
    truncates it.
    """

    floor: int
    target_tokens: int
    visible: int
    reasoning: int = REASONING_ALLOWANCE

    @property
    def tokens(self) -> int:
        """The cap asked for before any unit, window or ceiling bounds it."""
        return self.visible + self.reasoning

    @property
    def basis(self) -> str:
        """How the number was reached, in the words a journal row carries."""
        if self.target_tokens:
            reply = (
                f"{self.floor} for the task type + {REWRITE_FACTOR} x "
                f"{self.target_tokens} target tokens"
            )
        else:
            reply = f"{self.floor} for the task type + {NEW_FILE_STEP} for a new file"
        return f"auto: {reply} + {self.reasoning} reasoning allowance = {self.tokens}"


def auto_reply_cap(floor: int, target: str) -> AutoCap:
    """The automatic cap of a contract that states none, sized from its target.

    ``floor`` is the cap the loader derived for the task type
    (:func:`output_cap`); ``target`` the target's content as the attempt reads
    it, empty for a file that does not exist yet. Deterministic in the two,
    for the reason :func:`output_cap` is: a budget that moved between two runs
    of the same contract on the same file would make every refusal downstream
    unreproducible. The constants and the measurements behind them are above.
    """
    # Imported here for the reason `mcgyvr.gate.preflight` does: the
    # orchestrator package imports this module, so at module scope this would
    # be a cycle to reach one arithmetic helper.
    from mcgyvr.orchestrator.read import estimate_tokens

    tokens = estimate_tokens(target) if target else 0
    grown = REWRITE_FACTOR * tokens if tokens else NEW_FILE_STEP
    visible = ((floor + grown + CAP_STEP - 1) // CAP_STEP) * CAP_STEP
    return AutoCap(floor=floor, target_tokens=tokens, visible=visible)


def evidence_for(
    kind: CatalogTaskType,
    *,
    acceptance: tuple[str, ...] = (),
    demonstration: tuple[str, ...] = (),
    no_semantic_change: bool = False,
    type_check: bool = False,
) -> tuple[CatalogEvidence, ...]:
    """The evidence a contract of ``kind`` carries, given its own fields.

    Every type but ``code`` carries its catalog's static ``required_evidence``
    unchanged. ``code`` derives it: always ``gate``, then the kinds its fields
    name — ``failing_test_first`` from a non-empty ``demonstration``,
    ``tests_pass`` from a non-empty ``acceptance``, and ``no_semantic_change``
    / ``type_check`` from the two flags. This is the one place the derivation
    is spelled, so the loader, the output cap and the gate all read the same
    evidence for a contract rather than three copies that can drift.
    """
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


def output_cap(
    name: str,
    *,
    new_file: bool = False,
    evidence: tuple[CatalogEvidence, ...] | None = None,
    operation: str = "",
) -> int:
    """The output cap a contract of this task type carries when it declares none.

    Deterministic in its inputs and in nothing else: same task type, same
    number, in this process and in the next one. A cap is a budget, and a
    budget that moved between two runs of the same contract would make every
    refusal downstream unreproducible.

    A type the deterministic tier executes gets the floor. There is no model
    reply to size — a tool writes the change — so any larger number would be a
    reservation against something that never happens.

    ``evidence`` overrides the type's static ``required_evidence``, for the one
    type whose evidence is derived per contract (``code``): its cap depends on
    whether it must write behaviour, which only the contract's own fields say.

    ``new_file`` adds the new-file step. No caller passes it: the loader, the
    one call site, cannot supply it, because an empty ``target_content`` means
    "the file does not exist yet" *or* "its content is not needed".

    ``operation`` names the deterministic operation a ``code`` contract asks
    for, whose entry then decides: a tool writes the change, so the floor.
    """
    kind = kind_of(name, operation)
    required = kind.required_evidence if evidence is None else tuple(evidence)
    allowance = (
        0
        if kind.deterministic
        else max(
            (_evidence_allowance(e) for e in required),
            default=STRUCTURAL_ALLOWANCE,
        )
    )
    if allowance and new_file:
        allowance += NEW_FILE_STEP
    whole_steps = ((allowance + CAP_STEP - 1) // CAP_STEP) * CAP_STEP
    return max(MIN_CAP, whole_steps)


def _evidence_allowance(evidence: CatalogEvidence) -> int:
    """How big one required evidence kind says the reply has to be allowed to be.

    Read off the property the catalog declares — whether this evidence needs a
    command to produce it — because that is the property that says what the
    reply must contain: evidence a structural check can read is evidence about
    prose or a shape, and evidence a command produces is evidence about
    behaviour, which has to be written before it can run. A kind matched by
    name would put the evidence vocabulary in this file too.
    """
    return RUNNING_ALLOWANCE if evidence.needs_commands else STRUCTURAL_ALLOWANCE


def generic_stop_condition(task_type_name: str, subject: str) -> str:
    """The stop condition to start from: decide nothing the contract left open.

    One spelling, because three places say it — the proposer writes it into
    the contracts it emits, the field doc shows it, and the loader's refusal
    hands it to an author who named none — and a condition that read
    differently in each would be three conditions.
    """
    return (
        f"{task_type_name} on {subject} would require deciding something the "
        "contract does not state — report BLOCKED rather than guess"
    )


# --- the declared schema --------------------------------------------------

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
    """One key in the contract schema, with what is needed to validate and document it.

    ``doc`` has no default: a key that cannot be explained does not belong in
    a surface an agent is asked to author against. ``worker_facing`` marks the
    keys :meth:`Contract.worker_view` may expose — the split is declared on the
    schema so it cannot drift from the prompt builder that honours it. "May be
    exposed" is not "is rendered": ``id`` and ``context.max_input_tokens`` are
    both in the view and neither is spent on the worker, because a join key and
    an input ceiling are things the orchestrator acts on and a model cannot.

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
    min_value: float | None = None
    #: Inclusive upper bound, for a value that is a share of something rather
    #: than a count of it. Absent on every counting field: a token cap has no
    #: natural ceiling, and inventing one would refuse a contract nobody has
    #: shown to be wrong.
    max_value: float | None = None
    worker_facing: bool = False
    hint: str = ""
    choices_from: Callable[[], tuple[str, ...]] | None = None
    #: For an enum whose values were renamed: the old value and its
    #: replacement, so a contract still naming one is told what to write.
    retired: Mapping[str, str] | None = None
    #: A required key a session's contract may leave out (a task type the
    #: catalog marks ``session``: ``chat``, ``agent``). A session writes
    #: nothing to the tree, so it has no destination to name and no surface to
    #: scope; asking for one would ask for a file that is never written.
    session_optional: bool = False

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
        "Leave it out and each attempt sizes it from the target: the type's "
        "allowance, twice the target's estimated tokens, and a reasoning "
        "allowance; the journal records the number and how. A reply cut off "
        "at the cap is a named failure, never applied to a file. Not bounded "
        "by `context.max_input_tokens`. A raw-text reply (`prose` / "
        "`media_artifact`) carries no cap.",
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


# --- the loaded contract --------------------------------------------------


@dataclass(frozen=True)
class Dependency:
    """One dependency, carried as a signature rather than as source."""

    path: str
    signature: str
    note: str = ""


@dataclass(frozen=True)
class Rename:
    """The symbol a ``rename_symbol`` operation renames, and what it becomes.

    Both empty is the ordinary state of every contract that is not a rename,
    and :attr:`stated` is how a caller asks whether this one said anything.
    """

    old: str = ""
    new: str = ""

    @property
    def stated(self) -> bool:
        return bool(self.old and self.new)


@dataclass(frozen=True)
class Verification:
    """How a change is judged once the deterministic gate has passed."""

    policy: str


@dataclass(frozen=True)
class Limits:
    """Hard ceilings on one execution of a contract."""

    max_output_tokens: int | None
    attempts: int
    #: The share of a rung's window this contract may claim, or ``None`` when
    #: it declared none. ``None`` rather than ``1.0`` because "no share was
    #: stated" and "the whole window was allowed" are different declarations,
    #: and only one of them should read as an operator's choice in a record.
    max_window_fraction: float | None = None


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
    limits: Limits = Limits(RUNNING_ALLOWANCE, 2)
    rename: Rename = Rename()
    no_semantic_change: bool = False
    type_check: bool = False
    max_output_tokens_declared: bool = True
    #: The content of each of ``sources``, in order, once the attempt has read
    #: them off the tree the run started from (:func:`mcgyvr.drive.worker_attempt`,
    #: :mod:`mcgyvr.worker.sources`). Not a schema key: a contract names its
    #: sources, and the run reads them — so a contract on disk never carries a
    #: copy that could disagree with the tree. Empty until read.
    source_content: tuple[str, ...] = ()

    @property
    def type(self) -> CatalogTaskType:
        """The declared task type, as its catalog entry."""
        return catalog().require(self.task_type)

    @property
    def kind(self) -> CatalogTaskType:
        """The catalog entry that governs this contract.

        Its ``operation``'s entry when it names one — the operation decides the
        starting family, the guarantee and the evidence — and its task type's
        when it does not.
        """
        return kind_of(self.task_type, self.operation)

    @property
    def evidence(self) -> tuple[CatalogEvidence, ...]:
        """The evidence this contract carries, derived from its own fields.

        For ``code`` this is computed per contract from ``demonstration``,
        ``acceptance``, ``no_semantic_change`` and ``type_check``; every other
        type carries its catalog's static ``required_evidence`` unchanged.
        """
        return evidence_for(
            self.kind,
            acceptance=self.acceptance,
            demonstration=self.demonstration,
            no_semantic_change=self.no_semantic_change,
            type_check=self.type_check,
        )

    @property
    def evidence_names(self) -> tuple[str, ...]:
        """The names of the evidence kinds this contract carries."""
        return tuple(e.name for e in self.evidence)

    @property
    def is_deterministic(self) -> bool:
        """Whether the deterministic tier can execute this contract outright."""
        return self.kind.deterministic

    @property
    def is_session(self) -> bool:
        """Whether a run of this contract is a session (``chat``, ``agent``).

        Its reply is the answer: returned in the result file and kept in the
        journal's session log, never written to the tree. ``target`` and
        ``scope`` are not used — empty unless the contract gave them anyway.
        """
        return self.kind.session

    @property
    def acceptance_commands(self) -> tuple[tuple[str, ...], ...]:
        """``acceptance``, split into argv the acceptance rung can run.

        A contract writes a command the way a person types it —
        ``"pytest -q"`` — and :class:`~mcgyvr.gate.acceptance.Acceptance` takes
        argv, because it runs commands without a shell (a shell would give an
        acceptance command the metacharacters to do things an acceptance
        command must not do, starting with writing to the tree).

        The split is here rather than at each caller for the reason
        :attr:`demonstration_commands` shares: two spellings of "what this
        contract's commands are" would eventually disagree about quoting, and a
        contract whose acceptance bar means one thing to the gate and another
        to a report is a contract nothing can be said to have passed.
        """
        return tuple(tuple(shlex.split(command)) for command in self.acceptance)

    @property
    def demonstration_commands(self) -> tuple[tuple[str, ...], ...]:
        """``demonstration``, split into argv, with the opposite baseline.

        Separate from :attr:`acceptance_commands` because the two lists are
        judged against opposite expectations at baseline (#183) and the gate
        takes them as two arguments; folding them here would lose exactly the
        distinction the split exists for.
        """
        return tuple(tuple(shlex.split(command)) for command in self.demonstration)

    @property
    def prose(self) -> str:
        """What this contract asked for, in its own words, for a rung to read.

        ``task`` and ``interface`` and nothing else: they are the two fields
        that state the work, they are the two a worker is given, and a gate
        rung standing itself down on the strength of something the worker never
        saw would be excusing a change nobody asked for.

        ``param-mutation`` stands down for a contract that *ordered* in-place
        work — "sort the rows in place" — and reads this to find out. Joined
        here rather than at each gate call site so the two callers cannot come
        to disagree about which fields count.
        """
        return f"{self.task}\n{self.interface}"

    def worker_view(self) -> dict[str, Any]:
        """Exactly the fields a worker prompt may be built from.

        The one way to reach worker-facing content, so "orchestrator-only
        fields never reach the worker prompt" (#94) is enforced by there being
        no other accessor rather than by reviewing every prompt builder. What
        is excluded is excluded on purpose: ``risk``, ``verification``,
        ``acceptance``, ``demonstration`` and ``limits`` are how the
        *orchestrator* decides where to run the work and whether to believe
        the result, and a worker that could read them could argue with them.

        ``sources`` carries each path with its content once the attempt has
        read it (:attr:`source_content`), and ``None`` before — what
        ``mcgyvr contract --worker-view`` shows, since no tree has been read.
        """
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
        """The whole contract as plain data, in schema declaration order.

        Round-trips: ``parse(dumps(c))`` reconstructs ``c``. That is what makes
        "a contract the orchestrator emits is one the direct-mode API accepts"
        testable rather than asserted.

        ``depends_on`` is emitted only when the contract states one, where
        every other key is emitted empty or not. The difference is not
        tidiness: this form is an identity — a digest of ``dumps(contract)``
        names a contract by what it says — so a key every contract carries
        whether or not it means anything changes that digest for every contract
        ever emitted, and whatever was keyed by the old digest no longer finds
        its contract. A key that appears exactly when it says something costs
        nothing to add later.
        """
        stated = {"depends_on": sorted(self.depends_on)} if self.depends_on else {}
        # Emitted on the same rule and for the same reason: a key every
        # contract carries whether or not it means anything re-keys every
        # contract ever emitted, and every record of a run keyed by one.
        renamed = (
            {"rename": {"from": self.rename.old, "to": self.rename.new}}
            if self.rename.stated
            else {}
        )
        # Same rule again, for the share: one carried whether or not it was
        # declared would change the serialised form of every contract that
        # never mentioned one, and with it the digest each recorded run is
        # keyed by.
        share = (
            {"max_window_fraction": self.limits.max_window_fraction}
            if self.limits.max_window_fraction is not None
            else {}
        )
        # The two code flags appear exactly when they say something, for the
        # same reason as ``depends_on`` and the share above: a key carried
        # whether or not it means anything re-keys every contract ever emitted.
        flags: dict[str, bool] = {}
        if self.no_semantic_change:
            flags["no_semantic_change"] = True
        if self.type_check:
            flags["type_check"] = True
        return {
            "version": self.version,
            "id": self.id,
            "task_type": self.task_type,
            # Emitted exactly when one is named, for the reason ``depends_on``
            # is: a key every contract carried would re-key every contract.
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
                "max_output_tokens": (
                    self.limits.max_output_tokens
                    if self.max_output_tokens_declared
                    else None
                ),
                "attempts": self.limits.attempts,
                **share,
            },
        }


# --- loading --------------------------------------------------------------


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
        # A session's reply is the answer, so prose is its shape; whole_file,
        # the schema's default, would have a chat reply written over a target.
        data["output_schema"] = "prose"
    declared_cap = data["limits"]["max_output_tokens"] is not None
    if not declared_cap:
        # The one key the schema cannot default statically: how big a reply may
        # be depends on what the reply has to be. What is filled here is the
        # floor of the automatic cap — the task type's visible allowance — and
        # each attempt sizes the cap it sends from the target it reads
        # (`auto_reply_cap`, through `mcgyvr.gate.preflight.reply_cap`). A
        # raw-text reply (prose / media_artifact) carries no cap at all — a
        # chatty model is a prompting issue, not a cap issue — so only a
        # whole_file reply gets a derived number.
        data["limits"]["max_output_tokens"] = (
            output_cap(
                data["task_type"],
                operation=data["operation"],
                evidence=evidence_for(
                    kind_of(data["task_type"], data["operation"]),
                    acceptance=data["acceptance"],
                    demonstration=data["demonstration"],
                    no_semantic_change=data["no_semantic_change"],
                    type_check=data["type_check"],
                ),
            )
            if data["output_schema"] == "whole_file"
            else None
        )
    _cross_validate(data)
    return _build(data, max_output_tokens_declared=declared_cap)


def dumps(contract: Contract) -> str:
    """The contract as JSON, in schema order — the emitted form of the API."""
    return json.dumps(contract.as_dict(), indent=2)


def _build(data: Mapping[str, Any], *, max_output_tokens_declared: bool) -> Contract:
    """Assemble the validated mapping into a Contract."""
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
        max_output_tokens_declared=max_output_tokens_declared,
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
    if spec.kind == "float":
        return _float(raw, spec, path)
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
    # A whole number is a valid decimal and a bool is not, which is the same
    # rule `_int` runs on: `max_window_fraction: true` is not a share.
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


def _is_session(raw: object) -> bool:
    """Whether ``raw`` declares a session task type, read before validation.

    Before, because which keys are required turns on it. An unknown or
    malformed ``task_type`` is not a session; ``_block`` refuses it by name.
    """
    if not isinstance(raw, Mapping):
        return False
    name = raw.get("task_type")
    if not isinstance(name, str):
        return False
    return name in task_type_names() and task_type(name).session


def _for_sessions(fields: tuple[Field, ...]) -> tuple[Field, ...]:
    """``fields`` with every ``session_optional`` key made optional, nested too."""
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


# --- self-contradiction ---------------------------------------------------


def _check_command(command: str, path: str) -> None:
    """Refuse shell syntax in a command that will be executed with no shell.

    ``acceptance`` and ``demonstration`` are split like a shell would split
    them and executed directly (:attr:`Contract.acceptance_commands`). Syntax
    only a shell gives meaning to would otherwise fail at run time and read
    as something else — a ``VAR=x`` prefix as exit 127, "a missing
    dependency", and an unclosed quote as a ``ValueError`` out of the split —
    so it is named here, before a sandbox is built.
    """
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
    """The first run of shell-operator characters outside quotes, or ``None``.

    Read with POSIX quoting — single quotes, double quotes and the backslash —
    so ``grep -q '|' f`` passes and ``pytest 2>/dev/null`` does not. Only
    called on a command ``shlex.split`` accepted, so every quote closes.
    """
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
        # Nothing is written, so there is no destination or surface to check:
        # a target or scope given anyway is not used, and judging it would
        # refuse a session for a file it never writes.
        if data["output_schema"] != "prose":
            raise ContractSchemaError(
                f"output_schema: {data['output_schema']!r} is a file-shaped "
                f"reply, but a {kind.name!r} run is a session: its reply is the "
                f"answer, returned in the result file and kept in the session "
                f"log, never written. Drop output_schema; 'prose' is the "
                f"default."
            )
    else:
        _check_destination(data, kind, target, allow, forbid)

    # Required only where a BLOCKED reply is heard: a whole_file reply is
    # parsed, and a refusal in it escalates (worker/reply.py), while a raw-text
    # reply is served as the answer whatever it says — a condition there would
    # be filler nothing reads.
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

    # Output evidence kinds that name a contract parameter: the gate makes the
    # check, but the contract must say what to check against. The names live in
    # gate/output.py — imported lazily because the gate package's __init__
    # imports gate.preflight, which imports this module, so a top-level import
    # here would be circular.
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

    # A dependency is a join key onto another contract's id, and every way of
    # writing one that no contract could ever match is a plan that deadlocks
    # instead of running — which is only visible once a driver has ordered the
    # whole set, long after this contract was accepted.
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

    # No bound of `limits.max_output_tokens` by `context.max_input_tokens`.
    # There was one, on the ground that a reply larger than the prompt budget
    # could not be assembled into a next attempt — but the cap counts the
    # hidden reasoning a hosted reasoning model spends before it writes, which
    # is never read back into anything, and the visible reply is bounded where
    # it competes for room: against the window of the rung it is sent to
    # (`mcgyvr.gate.preflight.check_contract_against_rung`). The rule only
    # forced a reasoning model's cap to drag the prompt budget up with it (the
    # e2e run of 2026-10-13).


def _check_sources(sources: Sequence[str]) -> None:
    """Each source names one file in the tree, once.

    Checked here, where it costs nothing, for the shape a path must have to be
    read at all; whether the file is there, and may be given to a worker, is
    the attempt's question (:mod:`mcgyvr.worker.sources`), asked of the tree
    the run starts from.
    """
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
    """The target and scope of a contract that writes: one file, in its scope."""
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
