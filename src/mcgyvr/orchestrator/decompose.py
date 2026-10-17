""

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

if TYPE_CHECKING:  #
    from pathlib import Path

    from mcgyvr.config import Config

#
#
#er
#
_ID_DIGEST_BYTES = 5

#
#
#
#
#
_DEFAULT_MAX_INPUT_TOKENS = 32768


@dataclass(frozen=True)
class DepRef:
    ""

    path: str
    symbol: str
    note: str = ""


@dataclass(frozen=True)
class Proposal:
    ""

    task_type: str
    task: str
    target: str
    interface: str = ""
    deps: tuple[DepRef, ...] = ()
    allow: tuple[str, ...] = ()
    forbid: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    #
    #
    #
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
    risk: str = ""
    """Empty means "let the schema's default stand" rather than a fourth level."""


@dataclass(frozen=True)
class Evidence:
    ""

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
    ""

    subject: str
    reason: str

    def __str__(self) -> str:
        return f"{self.subject}: {self.reason}"


@dataclass(frozen=True)
class Decomposition:
    ""

    contracts: tuple[Contract, ...] = ()
    refusals: tuple[Refusal, ...] = ()
    documents: tuple[str, ...] = ()
    """Each contract's emitted text, in the order the contracts appear."""

    resolution: Resolution | None = None
    exploration: Exploration | None = None

    @property
    def empty(self) -> bool:
        ""
        return not self.contracts

    def explain(self) -> str:
        ""
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
    ""
    resolution = resolve(index, prompt)
    exploration = (
        explore(index, resolution)
        if budget is None
        else explore(index, resolution, budget=budget)
    )
    vocabulary = _vocabulary(config)
    owners = tuple(adapters) if adapters is not None else _default_adapters()
    observation = locate_baseline(index.root)
    evidence = Evidence(
        prompt=prompt,
        index=index,
        resolution=resolution,
        exploration=exploration,
        vocabulary=vocabulary,
        baseline=observation,
    )

    proposals = tuple(propose(evidence))
    if not proposals:
        return Decomposition(
            refusals=(
                Refusal(
                    "request",
                    "nothing could be proposed from this prompt and repository — "
                    "narrow the request to work of one of the catalog's types, or "
                    f"name a target that exists here. Servable types: "
                    f"{', '.join(t.name for t in vocabulary) or 'none'}",
                ),
            ),
            resolution=resolution,
            exploration=exploration,
        )

    contracts: list[Contract] = []
    documents: list[str] = []
    refusals: list[Refusal] = []
    seen: dict[str, str] = {}
    for proposal in proposals:
        emitted = _emit(
            proposal,
            index,
            vocabulary,
            seen,
            owners,
            max_input_tokens,
            located,
            observation,
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
        resolution=resolution,
        exploration=exploration,
    )


def _vocabulary(config: Config | None) -> tuple[TaskType, ...]:
    ""
    known = catalog()
    if config is None:
        return known.task_types
    return known.servable(config)


def _default_adapters() -> tuple[LanguageAdapter, ...]:
    ""
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
) -> tuple[Contract, str] | Refusal:
    ""
    servable = {t.name for t in vocabulary}
    if proposal.task_type not in servable:
        return Refusal(
            proposal.target or proposal.task_type,
            _unservable_reason(proposal.task_type, servable),
        )

    if not _indexed(index, proposal.target):
        return Refusal(
            proposal.target,
            "no such file in the index — a contract's target must be a path the "
            "repository holds; check the path, or index a repository that has it",
        )

    kind = next(t for t in vocabulary if t.name == proposal.task_type)
    acceptance = _acceptance_for(proposal, kind, index.root, adapters, located)
    if isinstance(acceptance, Refusal):
        return acceptance
    proposal = replace(proposal, acceptance=acceptance)
    proposal = _baseline_for(proposal, kind, baseline)

    #
    #
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
    )
    if document["id"] in seen:
        return Refusal(
            proposal.target,
            f"duplicates contract {document['id']} on {seen[document['id']]} — the "
            "same type, target and directive is the same unit of work twice",
        )

    built = _load(document)
    if isinstance(built, Refusal):
        return Refusal(proposal.target, built.reason)
    if built.needs_output_cap and built.limits.max_output_tokens is None:
        #
        #
        #
        #
        return Refusal(
            proposal.target,
            f"a model-written {proposal.task_type!r} contract states "
            "limits.max_output_tokens — what its reply is worth, in output "
            "tokens — and this proposal states no max_output_tokens, so "
            "`mcgyvr run` would refuse it before any model is called. State "
            "max_output_tokens on the proposal",
        )
    resized = _resize(built, document, ceiling)
    if isinstance(resized, Refusal):
        return Refusal(proposal.target, resized.reason)
    return resized


def _unservable_reason(task_type: str, servable: set[str]) -> str:
    ""
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
    ""
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
        )
    return (shlex.join(command),)


def _baseline_for(
    proposal: Proposal,
    kind: TaskType,
    baseline: BaselineObservation | None,
) -> Proposal:
    ""
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
    ""
    found: dict[str, list[str]] = {}
    for adapter in adapters if adapters is not None else _default_adapters():
        command = adapter.locate_type_check_command(root)
        if command is not None:
            found[adapter.name] = list(command)
    return found


def _owner(path: str, adapters: Sequence[LanguageAdapter]) -> LanguageAdapter | None:
    ""
    return next((a for a in adapters if a.owns(path)), None)


def _indexed(index: Index, path: str) -> bool:
    return any(file.path == path for file in index.files)


def _content_of(index: Index, target: str) -> str:
    ""
    for file in index.files:
        if file.path == target:
            return "\n".join(file.lines)
    return ""


def _signature_for(index: Index, ref: DepRef) -> str | None:
    ""
    for symbol in index.symbols.definitions(ref.symbol):
        if symbol.path == ref.path and symbol.kind is SymbolKind.DEFINITION:
            return symbol.signature or None
    return None


def _identify(proposal: Proposal) -> str:
    ""
    material = json.dumps(
        [
            proposal.task_type,
            proposal.target,
            proposal.task,
            proposal.interface,
            proposal.no_semantic_change,
            proposal.type_check,
        ]
        + [[d.path, d.symbol] for d in proposal.deps],
        sort_keys=True,
    )
    digest = hashlib.blake2b(
        material.encode("utf-8", "surrogateescape"), digest_size=_ID_DIGEST_BYTES
    ).hexdigest()
    return f"{proposal.task_type}-{digest}"


def _document(
    proposal: Proposal,
    dependencies: list[dict[str, str]],
    *,
    contract_id: str,
    target_content: str = "",
    max_input_tokens: int | None = None,
) -> dict[str, Any]:
    ""
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
    if proposal.interface:
        document["interface"] = proposal.interface
    if dependencies:
        document["deps"] = dependencies
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
    if proposal.risk:
        document["risk"] = proposal.risk
    if max_input_tokens is not None:
        document["context"] = {"max_input_tokens": max_input_tokens}
    cap = _reply_cap(proposal)
    if cap is not None:
        document["limits"] = {"max_output_tokens": cap}
    return document


def _reply_cap(proposal: Proposal) -> int | None:
    ""
    return proposal.max_output_tokens


def _load(document: dict[str, Any]) -> Contract | Refusal:
    ""
    try:
        return contract_module.loads(json.dumps(document))
    except ContractError as exc:
        return Refusal("", f"the emitted contract does not validate — {exc}")


def _resize(
    built: Contract, document: dict[str, Any], ceiling: int
) -> tuple[Contract, str] | Refusal:
    ""
    needed = estimate_tokens(json.dumps(built.worker_view(), sort_keys=True))
    if needed > ceiling:
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
    )
    reloaded = _load(resized)
    if isinstance(reloaded, Refusal):  #
        return built, contract_module.dumps(built)
    return reloaded, contract_module.dumps(reloaded)


def _too_large_reason(built: Contract, needed: int, ceiling: int) -> str:
    ""
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
    ""
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
        risk=built.risk,
    )


@dataclass(frozen=True)
class RecordedProposer:
    ""

    proposals: tuple[Proposal, ...] = ()
    seen: list[Evidence] = field(default_factory=list)

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        self.seen.append(evidence)
        return self.proposals
