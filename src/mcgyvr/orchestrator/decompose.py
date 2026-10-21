"""Decompose a request into contracts, or into refusals that say why not.

`decompose` is the whole of this module's interface: it resolves a prompt
against an index, reads what the prompt touches, and hands that evidence to a
`Proposer` once. Each proposal that comes back is checked — the task type must
be servable, the target must be a file the index holds, the acceptance a
`type_check` implies must be locatable, every dependency must have a signature
the index can state, the id must be unused, and the worker view must fit the
ceiling — and is then either emitted as a validated contract document or
refused with the reason it could not be.

Nothing here decides what the work is. It decides whether the work can be
stated as something runnable, and says what stands in the way when it cannot:
refusals are returned as values, not raised, so one bad proposal does not lose
the others.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from mcgyvr import contract as contract_module
from mcgyvr.catalog import CatalogError, TaskType, catalog
from mcgyvr.contract import Contract, ContractError
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.orchestrator.baseline import BaselineObservation, locate_baseline
from mcgyvr.orchestrator.index import Index
from mcgyvr.orchestrator.read import Exploration, estimate_tokens, explore
from mcgyvr.orchestrator.resolve import Resolution, resolve
from mcgyvr.orchestrator.symbols import SymbolKind

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pathlib import Path

    from mcgyvr.config import Config

# Bytes of digest kept in every contract id. Five bytes is ten hex characters:
# short enough that an id is still a filename a caller can write, long enough
# that two different changes to the same target do not land on one id. The
# digest itself is blake2b over the proposal, in `_identify`.
_ID_DIGEST_BYTES = 5

# The ceiling on a contract's worker view, in estimated tokens, when the
# caller names none. `_resize` refuses a view over it: the worker must return
# every token it is sent, so a target this large is neither sendable nor
# answerable. `decompose`'s `max_input_tokens` argument overrides it, and
# `context.max_input_tokens` is a separate, per-contract number.
_DEFAULT_MAX_INPUT_TOKENS = 32768

#: Prefix `_load` puts on a schema-error refusal. `_emit` strips it to recover
#: the schema's own error text (which names the bad key) for `what_to_change`.
_SCHEMA_ERROR_PREFIX = "the emitted contract does not validate — "


@dataclass(frozen=True)
class DepRef:
    """A dependency a proposal wants restated on its contract.

    Only the path and the symbol are stated here: `_emit` looks the signature
    up in the index, so a dependency whose signature cannot be read is refused
    rather than described in prose.
    """

    path: str
    symbol: str
    note: str = ""


@dataclass(frozen=True)
class Proposal:
    """One unit of work as a proposer states it, before it is a contract.

    These are the proposer's answers. What the repository can answer better —
    the acceptance command a `type_check` implies, the demonstration and
    acceptance a baseline run yields — `_emit` fills in or checks, and refuses
    the proposal when it cannot be had.
    """

    task_type: str
    task: str
    target: str
    interface: str = ""
    deps: tuple[DepRef, ...] = ()
    allow: tuple[str, ...] = ()
    forbid: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    #: What the reply to this unit of work is worth, in output tokens. A
    #: model-written contract that is judged by evidence must state one, so
    #: `_emit` refuses such a proposal while this is None.
    max_output_tokens: int | None = None
    acceptance: tuple[str, ...] = ()
    demonstration: tuple[str, ...] = ()
    """Commands that must fail at baseline and pass after — `failing_test_first`
    (#183). Only a proposer can name one (#146: no locator can, in principle),
    which is why the slot exists here: without it a `code` proposal could never
    carry the demonstration that derives `failing_test_first`."""
    no_semantic_change: bool = False
    """Whether the change must leave parsed structure untouched apart from the
    region the task touches — the `code` flag that derives `no_semantic_change`."""
    type_check: bool = False
    """Whether the project's own type checker must pass — the `code` flag that
    derives `type_check`."""
    operation: str = ""
    """A deterministic operation a tool performs instead of a model."""
    sources: tuple[str, ...] = ()
    """Other repo files the worker is given whole, beside the target."""
    depends_on: tuple[int, ...] = ()
    """0-based indexes into the proposer's own proposal array that must land
    first. Indexes are digested by `_identify`; the resolved contract ids are
    supplied separately to `_document`."""


@dataclass(frozen=True)
class Evidence:
    """What a proposer is shown: the prompt and what the readers found in it.

    Everything here was read from the repository without a model — resolution
    and exploration of the prompt, the servable task types, and the baseline
    observation — so a proposer judges a repository it has actually been
    shown rather than one it remembers.
    """

    prompt: str
    index: Index
    resolution: Resolution
    exploration: Exploration
    vocabulary: tuple[TaskType, ...]
    """The task types this configuration can actually serve, cheapest first."""
    baseline: BaselineObservation | None = None
    """The baseline observation, when the repository declares a test runner.

    The locator's result — the runner and the red/green split read from one run
    — so a proposer (and, downstream, an emitted ``code`` contract) can derive
    ``demonstration`` and ``acceptance`` from the run instead of a
    model-invented command. ``None`` means the repository declared no runner
    (or the observation could not be read), and the model's own fields stand."""


Proposer = Callable[[Evidence], Sequence[Proposal]]
"""The judgment step. No default binding: a caller supplies one.

Given the deterministic evidence, return the units of work to emit — or nothing,
which is a refusal to decompose and is reported as one.
"""


@dataclass(frozen=True)
class Refusal:
    """A piece of work that was not emitted, and why.

    The subject is what the refusal is about — a target, a task type, or the
    request as a whole — so a reader sees which proposal failed without
    counting them; `str` is the one-line form. `field` and `what_to_change`
    are the machine-actionable half: `field` names a `Proposal` field to
    change, with the sentinel `"request"` for the request as a whole and `""`
    for a catch-all that cannot be attributed to one field; `what_to_change`
    is the directive a retry loop can act on.
    """

    subject: str
    reason: str
    field: str = ""  # Proposal field; "request" = whole request; "" = catch-all
    what_to_change: str = ""  # machine-actionable directive for the retry loop

    def __str__(self) -> str:
        return f"{self.subject}: {self.reason}"


@dataclass(frozen=True)
class Decomposition:
    """What one call to `decompose` produced.

    `contracts` and `documents` are parallel and in the same order: each
    document is the emitted text of the contract beside it. `refusals` are the
    proposals that could not become contracts — a decomposition may hold both
    kinds. When no proposal could be made at all, both tuples are empty and the
    single refusal is against the request.
    """

    contracts: tuple[Contract, ...] = ()
    refusals: tuple[Refusal, ...] = ()
    documents: tuple[str, ...] = ()
    """Each contract's emitted text, in the order the contracts appear."""

    resolution: Resolution | None = None
    exploration: Exploration | None = None

    @property
    def empty(self) -> bool:
        """Whether no contract was emitted at all; refusals do not count."""
        return not self.contracts

    def explain(self) -> str:
        """One line per contract, `id: task_type -> target`, then one per refusal."""
        lines = [f"{c.id}: {c.task_type} -> {c.target}" for c in self.contracts]
        lines.extend(str(r) for r in self.refusals)
        return "\n".join(lines)


def decompose(
    index: Index,
    prompt: str,
    *,
    propose: Proposer,
    config: Config | None = None,
    budget: int | None = None,
    adapters: Sequence[LanguageAdapter] | None = None,
    max_input_tokens: int = _DEFAULT_MAX_INPUT_TOKENS,
    located: Mapping[str, Sequence[str]] | None = None,
) -> Decomposition:
    """Turn a prompt into contracts, or into refusals that say why not.

    Resolution and exploration are read from the index, the task types from the
    catalog — all of them when no config is given, and only those whose
    starting family the configured ladder binds otherwise — the adapters from
    the defaults unless they are supplied, and the baseline from the
    repository's own test runner. All of it goes to `propose` in one call.

    An empty answer is a refusal to decompose, reported against the request
    with the servable types named. Otherwise every proposal goes through
    `_emit`, and a refusal against one does not stop the others; the emitted
    contracts come back in dependency order, with the proposer's order as the
    stable tiebreak.

    `budget` is passed to exploration when stated. `max_input_tokens` is the
    ceiling on a contract's worker view, above which the target is refused as
    too large. `located` carries checker commands a caller has already found,
    keyed by adapter name, so a `type_check` acceptance can be derived without
    probing the disk again.
    """
    evidence = _evidence(index, prompt, config=config, budget=budget, adapters=adapters)
    owners = tuple(adapters) if adapters is not None else _default_adapters()

    proposals = tuple(propose(evidence))
    if not proposals:
        return Decomposition(
            refusals=(
                Refusal(
                    "request",
                    "nothing could be proposed from this prompt and repository — "
                    "narrow the request to work of one of the catalog's types, or "
                    f"name a target that exists here. Servable types: "
                    f"{', '.join(t.name for t in evidence.vocabulary) or 'none'}",
                    field="request",
                    what_to_change=(
                        "name a target the index holds, or narrow the request "
                        "to a servable type"
                    ),
                ),
            ),
            resolution=evidence.resolution,
            exploration=evidence.exploration,
        )

    ordered, fan_out_refusals = _fan_out(proposals)

    contracts: list[Contract] = []
    documents: list[str] = []
    refusals: list[Refusal] = list(fan_out_refusals)
    seen: dict[str, str] = {}
    for proposal, depends_on_ids in ordered:
        emitted = emit_one(
            evidence,
            proposal,
            seen=seen,
            adapters=owners,
            ceiling=max_input_tokens,
            located=located,
            depends_on_ids=depends_on_ids,
        )
        if isinstance(emitted, Refusal):
            refusals.append(emitted)
            continue
        built, document = emitted
        seen[built.id] = proposal.target
        contracts.append(built)
        documents.append(document)

    return Decomposition(
        contracts=tuple(contracts),
        refusals=tuple(refusals),
        documents=tuple(documents),
        resolution=evidence.resolution,
        exploration=evidence.exploration,
    )


def _evidence(
    index: Index,
    prompt: str,
    *,
    config: Config | None = None,
    budget: int | None = None,
    adapters: Sequence[LanguageAdapter] | None = None,
) -> Evidence:
    """The deterministic pass a proposer is handed: resolve, read, catalog, baseline.

    `adapters` is accepted for the shared call shape with `decompose`/`iterate`;
    the evidence itself needs none — the baseline is located from the index's
    root and the vocabulary from the catalog.
    """
    resolution = resolve(index, prompt)
    exploration = (
        explore(index, resolution)
        if budget is None
        else explore(index, resolution, budget=budget)
    )
    vocabulary = _vocabulary(config)
    baseline = locate_baseline(index.root)
    return Evidence(
        prompt=prompt,
        index=index,
        resolution=resolution,
        exploration=exploration,
        vocabulary=vocabulary,
        baseline=baseline,
    )


def emit_one(
    evidence: Evidence,
    proposal: Proposal,
    *,
    seen: dict[str, str],
    adapters: Sequence[LanguageAdapter],
    ceiling: int,
    located: Mapping[str, Sequence[str]] | None = None,
    depends_on_ids: tuple[str, ...] = (),
) -> tuple[Contract, str] | Refusal:
    """Emit one proposal against `evidence`; the seam the retry loop reuses."""
    return _emit(
        proposal,
        evidence.index,
        evidence.vocabulary,
        seen,
        adapters,
        ceiling,
        located,
        evidence.baseline,
        depends_on_ids,
    )


def _vocabulary(config: Config | None) -> tuple[TaskType, ...]:
    """The task types this configuration can serve; every known type otherwise."""
    known = catalog()
    if config is None:
        return known.task_types
    return known.servable(config)


def _default_adapters() -> tuple[LanguageAdapter, ...]:
    """The adapters this build carries when the caller names none.

    Python first, then JavaScript — the order `_owner` and `locate_checkers`
    consult.
    """
    return (PythonAdapter(), JavaScriptAdapter())


def _emit(
    proposal: Proposal,
    index: Index,
    vocabulary: tuple[TaskType, ...],
    seen: dict[str, str],
    adapters: Sequence[LanguageAdapter],
    ceiling: int,
    located: Mapping[str, Sequence[str]] | None = None,
    baseline: BaselineObservation | None = None,
    depends_on_ids: tuple[str, ...] = (),
) -> tuple[Contract, str] | Refusal:
    """Emit one proposal as a validated contract, or refuse it.

    The checks run in sequence: the task type must be servable, the target must
    be a file the index holds, the acceptance a `type_check` implies must be
    locatable, and the demonstration and acceptance a baseline run yields fill
    in whatever the proposal left unstated. Each dependency is restated as the
    index's signature for that symbol, with its notes deduplicated per path.

    The document is then built, identified and loaded as a contract. A
    duplicate id, a schema error, a judged model-written contract with no
    output cap, and a worker view beyond `ceiling` are refusals rather than
    exceptions, each reported against the proposal's target. The returned text
    is that contract dumped as the document a caller writes out.
    """
    servable = {t.name for t in vocabulary}
    if proposal.task_type not in servable:
        return Refusal(
            proposal.target or proposal.task_type,
            _unservable_reason(proposal.task_type, servable),
            field="task_type",
            what_to_change="pick a servable type",
        )

    if not _indexed(index, proposal.target):
        return Refusal(
            proposal.target,
            "no such file in the index — a contract's target must be a path the "
            "repository holds; check the path, or index a repository that has it",
            field="target",
            what_to_change=(
                "name a path the index holds (check spelling, or index the repo "
                "that has it)"
            ),
        )

    kind = next(t for t in vocabulary if t.name == proposal.task_type)
    acceptance = _acceptance_for(proposal, kind, index.root, adapters, located)
    if isinstance(acceptance, Refusal):
        return acceptance
    proposal = replace(proposal, acceptance=acceptance)
    proposal = _baseline_for(proposal, kind, baseline)

    # Each dependency is restated as the signature the index holds for it, and
    # its notes kept once per path: prose here would be the worker's to guess.
    signatures: dict[str, list[str]] = {}
    notes: dict[str, list[str]] = {}
    for ref in proposal.deps:
        signature = _signature_for(index, ref)
        if signature is None:
            return Refusal(
                proposal.target,
                f"the index cannot state a signature for {ref.symbol!r} in "
                f"{ref.path!r}, so the dependency would have to be described "
                "rather than stated — omit it and let the worker "
                "report BLOCKED, or name a symbol the parser defines there",
                field="deps",
                what_to_change=(
                    "omit that symbol from deps, or name a symbol the parser defines"
                ),
            )
        stated = signatures.setdefault(ref.path, [])
        if signature not in stated:
            stated.append(signature)
        said = notes.setdefault(ref.path, [])
        if ref.note and ref.note not in said:
            said.append(ref.note)
    dependencies = [
        {"path": path, "signature": "\n\n".join(stated), "note": "; ".join(notes[path])}
        for path, stated in signatures.items()
    ]

    document = _document(
        proposal,
        dependencies,
        contract_id=_identify(proposal),
        target_content=_content_of(index, proposal.target),
        depends_on_ids=depends_on_ids,
    )
    if document["id"] in seen:
        return Refusal(
            proposal.target,
            f"duplicates contract {document['id']} on {seen[document['id']]} — the "
            "same type, target and directive is the same unit of work twice",
            field="task",
            what_to_change=(
                "make the directive distinct (same type+target+task is one unit twice)"
            ),
        )

    built = _load(document)
    if isinstance(built, Refusal):
        # `_load` returns `Refusal("", reason)` with no proposal context; the
        # schema error text is recovered from its reason so a retry loop can
        # act on the bad key. `field` stays empty: this is a catch-all.
        schema = (
            built.reason[len(_SCHEMA_ERROR_PREFIX) :]
            if built.reason.startswith(_SCHEMA_ERROR_PREFIX)
            else ""
        )
        return Refusal(
            proposal.target,
            built.reason,
            field="",
            what_to_change=schema,
        )
    if built.needs_output_cap and built.limits.max_output_tokens is None:
        # The document validates without the cap, but `mcgyvr run` refuses a
        # judged, model-written contract that states none — the reply must say
        # what it is worth — so emitting it would hand the caller a contract
        # certain to be refused. Refuse here instead, naming the field.
        return Refusal(
            proposal.target,
            f"a model-written {proposal.task_type!r} contract states "
            "limits.max_output_tokens — what its reply is worth, in output "
            "tokens — and this proposal states no max_output_tokens, so "
            "`mcgyvr run` would refuse it before any model is called. State "
            "max_output_tokens on the proposal",
            field="max_output_tokens",
            what_to_change=("state limits.max_output_tokens (whole number >= 1)"),
        )
    resized = _resize(built, document, ceiling, depends_on_ids=depends_on_ids)
    if isinstance(resized, Refusal):
        # `_resize` returns `Refusal("", reason)` with no proposal context;
        # `_emit` re-wraps it and attaches the field.
        return Refusal(
            proposal.target,
            resized.reason,
            field="target",
            what_to_change=(
                "narrow the target to a smaller file/region, or raise the ceiling"
            ),
        )
    return resized


def _unservable_reason(task_type: str, servable: set[str]) -> str:
    """Why a task type cannot be served here.

    The catalog's own error when the type is unknown; otherwise the family the
    type must start on, and the types this ladder does serve.
    """
    known = catalog()
    try:
        family = known.require(task_type).starts_on.name
    except CatalogError as exc:
        return str(exc)
    return (
        f"{task_type!r} must start on the {family!r} family and no configured "
        f"rung serves it — bind one, or ask for work of a type this ladder can "
        f"run: {', '.join(sorted(servable)) or 'none'}"
    )


def _acceptance_for(
    proposal: Proposal,
    kind: TaskType,
    root: Path,
    adapters: Sequence[LanguageAdapter],
    located: Mapping[str, Sequence[str]] | None = None,
) -> tuple[str, ...] | Refusal:
    """The acceptance commands a `type_check` proposal implies beyond its own.

    A proposal that states its own acceptance keeps it, and any task type that
    is not evidence-derived — or any proposal not asking for `type_check` —
    implies nothing. Otherwise the command is the checker the repository
    declared, as located by the adapter owning the target, or, when `located`
    is given, the command already found for that adapter. It is refused when no
    adapter owns the target, and when the repository declares no checker.
    """
    if proposal.acceptance:
        return proposal.acceptance
    if not (kind.evidence_derived and proposal.type_check):
        return proposal.acceptance

    owner = _owner(proposal.target, adapters)
    if owner is None:
        languages = ", ".join(a.name for a in adapters) or "none"
        return Refusal(
            proposal.target,
            f"no language adapter owns {proposal.target!r}, so the checker that "
            f"would back `type_check: true` cannot be located — its evidence "
            f"needs a type checker. Retarget a file in a "
            f"language this build carries ({languages}), or declare the command "
            f"in the proposal's acceptance",
            field="target",
            what_to_change=(
                "retarget a file in a carried language, or state the acceptance command"
            ),
        )

    command = (
        owner.locate_type_check_command(root)
        if located is None
        else (list(located[owner.name]) if located.get(owner.name) else None)
    )
    if command is None:
        return Refusal(
            proposal.target,
            "this repository declares no type checker, so a `type_check: true` "
            "`code` contract is not available here — its evidence needs a "
            "checker, and mcgyvr runs the one the repository configured rather "
            "than choosing one. Configure a checker in the "
            "repository, or declare the command in the proposal's acceptance",
            field="type_check",
            what_to_change=(
                "configure a checker in the repo, or drop type_check / state acceptance"
            ),
        )
    return (shlex.join(command),)


def _baseline_for(
    proposal: Proposal,
    kind: TaskType,
    baseline: BaselineObservation | None,
) -> Proposal:
    """Fill demonstration and acceptance from the baseline run where none were stated.

    Only for evidence-derived task types, and only when the repository's runner
    was observed: the proposal's own commands always win, and a proposal that
    nothing changed is returned as it was rather than rebuilt.
    """
    if baseline is None or not kind.evidence_derived:
        return proposal
    demonstration = proposal.demonstration or baseline.demonstrations()
    acceptance = proposal.acceptance or baseline.acceptance()
    if demonstration == proposal.demonstration and acceptance == proposal.acceptance:
        return proposal
    return replace(proposal, demonstration=demonstration, acceptance=acceptance)


def locate_checkers(
    root: Path, adapters: Sequence[LanguageAdapter] | None = None
) -> dict[str, list[str]]:
    """The type-check command each adapter locates here, keyed by adapter name.

    Adapters that find no checker are absent, so an empty mapping means this
    repository declares none in a language this build carries.
    """
    found: dict[str, list[str]] = {}
    for adapter in adapters if adapters is not None else _default_adapters():
        command = adapter.locate_type_check_command(root)
        if command is not None:
            found[adapter.name] = list(command)
    return found


def _owner(path: str, adapters: Sequence[LanguageAdapter]) -> LanguageAdapter | None:
    """The first adapter that claims this path, or None when none does."""
    return next((a for a in adapters if a.owns(path)), None)


def _indexed(index: Index, path: str) -> bool:
    return any(file.path == path for file in index.files)


def _content_of(index: Index, target: str) -> str:
    """The target's lines joined as one text for the contract to carry.

    Empty when the index does not hold the path — `_emit` has already checked
    that it does.
    """
    for file in index.files:
        if file.path == target:
            return "\n".join(file.lines)
    return ""


def _signature_for(index: Index, ref: DepRef) -> str | None:
    """The signature the index states for `ref.symbol`, or None.

    Only a definition in `ref.path` counts: a same-named symbol elsewhere is a
    different dependency.
    """
    for symbol in index.symbols.definitions(ref.symbol):
        if symbol.path == ref.path and symbol.kind is SymbolKind.DEFINITION:
            return symbol.signature or None
    return None


def _identify(proposal: Proposal) -> str:
    """The contract id: the task type, and a digest of what makes this unit of work.

    The digest covers the type, target, task, interface and the two flags,
    plus each dependency's path and symbol — and, only when stated, the
    operation, sources and the fan-out indexes — so two proposals share an id
    exactly when they direct the same change at the same target with the same
    plan edges, which is what lets `_emit` detect one unit of work stated
    twice. The fan-out fields are appended only when non-empty, so a proposal
    that uses none of them keeps the exact id it had before fan-out.
    `depends_on` digests the raw indexes, never the resolved ids, so an id
    needs no other id to be computed.
    """
    material: list[object] = [
        proposal.task_type,
        proposal.target,
        proposal.task,
        proposal.interface,
        proposal.no_semantic_change,
        proposal.type_check,
    ]
    material.extend([d.path, d.symbol] for d in proposal.deps)
    if proposal.operation:
        material.append(proposal.operation)
    if proposal.sources:
        material.append(proposal.sources)
    if proposal.depends_on:
        material.append(sorted(proposal.depends_on))
    digest = hashlib.blake2b(
        json.dumps(material, sort_keys=True).encode("utf-8", "surrogateescape"),
        digest_size=_ID_DIGEST_BYTES,
    ).hexdigest()
    return f"{proposal.task_type}-{digest}"


def _fan_out(
    proposals: tuple[Proposal, ...],
) -> tuple[tuple[tuple[Proposal, tuple[str, ...]], ...], tuple[Refusal, ...]]:
    """Resolve `depends_on` indexes into ids, and order proposals topologically.

    Every proposal's id is computed once, then each proposal's `depends_on`
    indexes are validated against the array — each must be a 0-based index of a
    *different* proposal. A proposal that names a bad index is refused, and so
    is every proposal that waits on it, directly or transitively: a dependency
    on a refused proposal can never be satisfied. Any cycle left after that is
    refused the same way. What remains comes back in dependency order, ties
    broken by the proposer's original order, each proposal paired with the ids
    of the proposals it waits on, so a plan with no edges comes back unchanged.
    """
    ids = [_identify(proposal) for proposal in proposals]
    count = len(proposals)

    # One pass validates every dependency and records the usable edges.
    predecessors: list[tuple[int, ...]] = []
    refusals_by_index: dict[int, Refusal] = {}
    refused: set[int] = set()
    for index, proposal in enumerate(proposals):
        stated: list[int] = []
        bad = False
        for dependency in proposal.depends_on:
            if (
                isinstance(dependency, bool)
                or not isinstance(dependency, int)
                or not 0 <= dependency < count
                or dependency == index
            ):
                refusals_by_index[index] = Refusal(
                    proposal.target or proposal.task_type or "request",
                    f"proposal {index} depends on {dependency!r}, which is not a "
                    f"0-based index of another one of the {count} proposals — "
                    "state the index of a proposal that must land first",
                    field="depends_on",
                    what_to_change="reference a proposal index in range",
                )
                refused.add(index)
                bad = True
                break
            if dependency not in stated:
                stated.append(dependency)
        predecessors.append(tuple(sorted(stated)) if not bad else ())

    # Transitive closure over the refused proposals: whatever waits on a
    # refused proposal is itself refused, and so on, because its dependency can
    # never be satisfied.
    changed = True
    while changed:
        changed = False
        for index in range(count):
            if index in refused:
                continue
            if any(dependency in refused for dependency in predecessors[index]):
                refusals_by_index[index] = Refusal(
                    proposals[index].target or proposals[index].task_type or "request",
                    f"proposal {index} depends on a proposal that was refused, so "
                    "its dependency cannot be satisfied",
                    field="depends_on",
                    what_to_change=(
                        "drop the dependency on the refused proposal, or fix that "
                        "proposal first"
                    ),
                )
                refused.add(index)
                changed = True

    # Kahn's algorithm over the proposals that are left, always taking the
    # smallest original index among those whose dependencies are already
    # placed: that keeps the proposer's order as the stable tiebreak.
    remaining = {
        index: set(predecessors[index])
        for index in range(count)
        if index not in refused
    }
    successors: dict[int, list[int]] = {index: [] for index in remaining}
    for index, before in remaining.items():
        for dependency in before:
            successors[dependency].append(index)

    ready = [index for index in remaining if not remaining[index]]
    order: list[int] = []
    while ready:
        index = min(ready)
        ready.remove(index)
        order.append(index)
        for successor in successors[index]:
            remaining[successor].discard(index)
            if not remaining[successor]:
                ready.append(successor)

    # Whatever Kahn could not place is on a cycle, or waits on a cycle, so none
    # of it can be satisfied; each such proposal is refused.
    for index in remaining:
        if index not in order:
            refusals_by_index[index] = Refusal(
                proposals[index].target or proposals[index].task_type or "request",
                "the proposals' depends_on references form a cycle, so no plan "
                "order exists — drop one edge so each contract can follow the one "
                "it waits on",
                field="depends_on",
                what_to_change="break the cycle in depends_on",
            )

    refusals = tuple(refusals_by_index[index] for index in sorted(refusals_by_index))
    return (
        tuple(
            (proposals[index], tuple(ids[j] for j in predecessors[index]))
            for index in order
        ),
        refusals,
    )


def _document(
    proposal: Proposal,
    dependencies: list[dict[str, str]],
    *,
    contract_id: str,
    target_content: str = "",
    max_input_tokens: int | None = None,
    depends_on_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Assemble the contract document from the proposal.

    `scope.allow` defaults to the target itself, and every other optional field
    is written only when the proposal states something for it, so the emitted
    document stays what was asked for rather than a full schema. The
    exceptions are supplied by the caller: `target_content`, written when
    non-empty, `max_input_tokens`, written as `context` when a resize has
    measured the worker view, and `depends_on_ids`, the already-resolved
    contract ids behind the proposal's raw `depends_on` indexes.
    """
    document: dict[str, Any] = {
        "id": contract_id,
        "task_type": proposal.task_type,
        "task": proposal.task,
        "target": proposal.target,
        "scope": {"allow": list(proposal.allow or (proposal.target,))},
    }
    if target_content:
        document["target_content"] = target_content
    if proposal.forbid:
        document["scope"]["forbid"] = list(proposal.forbid)
    if proposal.operation:
        document["operation"] = proposal.operation
    if proposal.interface:
        document["interface"] = proposal.interface
    if dependencies:
        document["deps"] = dependencies
    if proposal.sources:
        document["sources"] = list(proposal.sources)
    if depends_on_ids:
        document["depends_on"] = list(depends_on_ids)
    if proposal.stop_conditions:
        document["stop_conditions"] = list(proposal.stop_conditions)
    if proposal.acceptance:
        document["acceptance"] = list(proposal.acceptance)
    if proposal.demonstration:
        document["demonstration"] = list(proposal.demonstration)
    if proposal.no_semantic_change:
        document["no_semantic_change"] = True
    if proposal.type_check:
        document["type_check"] = True
    if max_input_tokens is not None:
        document["context"] = {"max_input_tokens": max_input_tokens}
    cap = _reply_cap(proposal)
    if cap is not None:
        document["limits"] = {"max_output_tokens": cap}
    return document


def _reply_cap(proposal: Proposal) -> int | None:
    """The reply cap the proposal states, or None when it states none."""
    return proposal.max_output_tokens


def _load(document: dict[str, Any]) -> Contract | Refusal:
    """Load an assembled document as a contract, or refuse it with the schema error.

    Its refusals carry no proposal context: subject and `field` are empty, and
    `_emit` re-wraps them against the proposal's target and attaches the field
    (and recovers the schema error text for `what_to_change`).
    """
    try:
        return contract_module.loads(json.dumps(document))
    except ContractError as exc:
        return Refusal("", f"{_SCHEMA_ERROR_PREFIX}{exc}")


def _resize(
    built: Contract,
    document: dict[str, Any],
    ceiling: int,
    *,
    depends_on_ids: tuple[str, ...] = (),
) -> tuple[Contract, str] | Refusal:
    """Fit the contract's worker view inside the ceiling, or refuse it as too large.

    The view is estimated as JSON. Over `ceiling` the target is refused: the
    worker must return everything it is sent. A view that already fits the
    contract's own `context.max_input_tokens` is returned untouched. Otherwise
    the document is rebuilt with `max_input_tokens` raised to the measured size
    and the reloaded contract is returned — or, if that rebuild does not
    validate, the original contract stands.
    """
    needed = estimate_tokens(json.dumps(built.worker_view(), sort_keys=True))
    if needed > ceiling:
        # No proposal context here: `_emit` re-wraps this refusal and attaches
        # the field and directive.
        return Refusal("", _too_large_reason(built, needed, ceiling))
    if needed <= built.max_input_tokens:
        return built, contract_module.dumps(built)
    carried = [
        {"path": d.path, "signature": d.signature, "note": d.note} for d in built.deps
    ]
    resized = _document(
        _proposal_of(built),
        carried,
        contract_id=built.id,
        target_content=built.target_content,
        max_input_tokens=needed,
        depends_on_ids=depends_on_ids,
    )
    reloaded = _load(resized)
    if isinstance(reloaded, Refusal):  # pragma: no cover - the first load passed
        return built, contract_module.dumps(built)
    return reloaded, contract_module.dumps(reloaded)


def _too_large_reason(built: Contract, needed: int, ceiling: int) -> str:
    """The refusal a target too large for the ceiling gets.

    It names the estimate, the ceiling, and how much of the estimate is the
    target's own content, since that is what makes the reply as large as the
    prompt.
    """
    share = (
        f", {estimate_tokens(built.target_content)} of it the target's own content"
        if built.target_content
        else ""
    )
    return (
        f"the worker view is {needed} estimated tokens against a ceiling of "
        f"{ceiling}{share}. With a whole-file reply the worker must return every "
        f"one of those tokens too, so this target is too large to send and too "
        f"large to receive — narrow the target (#126), or raise the ceiling to "
        f"what this ladder's rungs can actually accept"
    )


def _proposal_of(built: Contract) -> Proposal:
    """The proposal that reproduces an already-loaded contract.

    Dependencies are not carried: `_resize` hands `_document` the contract's own
    deps itself, and every field rebuilt here is one the contract stores
    verbatim. `depends_on` is left empty: a single loaded contract has no
    siblings, and the resolved ids are passed to `_document` separately.
    """
    return Proposal(
        task_type=built.task_type,
        task=built.task,
        target=built.target,
        interface=built.interface,
        allow=built.scope.allow,
        forbid=built.scope.forbid,
        max_output_tokens=built.limits.max_output_tokens,
        stop_conditions=built.stop_conditions,
        acceptance=built.acceptance,
        demonstration=built.demonstration,
        no_semantic_change=built.no_semantic_change,
        type_check=built.type_check,
        operation=built.operation,
        sources=built.sources,
    )


@dataclass(frozen=True)
class RecordedProposer:
    """A proposer that answers the same proposals and keeps the evidence it was shown.

    For callers that already know what to propose: `seen` receives each
    `Evidence` in the order the calls arrived.
    """

    proposals: tuple[Proposal, ...] = ()
    seen: list[Evidence] = field(default_factory=list)

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        self.seen.append(evidence)
        return self.proposals
