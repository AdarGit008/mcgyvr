"""Decomposition — from an understood repository and a request to contracts (#50).

This is the judgment step, and it is the one place in the orchestrator where a
model's opinion becomes a document the rest of the system executes. The whole
design question is therefore *how little* of that document the opinion is
allowed to author.

The answer is ADR-0007's, generalised. A model decides **relevance** — which
kind of work this is, which file it lands in, which of a file's forty symbols
the target actually needs. The repository decides **fact** — what those symbols
look like, whether the file exists at all. So the seam this module draws is not
"the model writes a contract and we check it"; it is "the model writes
*references* and the index resolves them". A :class:`Proposal` names a symbol; it
cannot state a signature, because there is no field for one.

Five properties are structural rather than remembered:

* **Every emitted contract came through the public loader.** A proposal is
  assembled into a document, serialised, and parsed by
  :func:`mcgyvr.contract.loads` — the same entry point direct mode uses. There is
  no other way out of this module, so "an emitted contract is one the direct-mode
  API accepts" is a property of the code path rather than a claim a test has to
  chase. A document the loader rejects becomes a refusal carrying the loader's
  own message, which already names the field and states the fix.
* **The target's current content is a fact, so it is read rather than proposed.**
  #150 gave the contract a slot for it and #155 fills it here. There is no
  ``Proposal`` field for it and there will not be one: a proposer that could
  state a file's content could state one the repository does not hold, which is
  the exact failure ADR-0007 draws the seam to prevent. The bytes come from the
  index — the same read that resolution and exploration already judged from —
  so two contracts emitted from one decomposition cannot disagree about one
  file. See :func:`_content_of`.
* **A dependency the index cannot name is refused, never described.** ADR-0007
  gives up any dependency the parser cannot state — a dynamically constructed
  attribute, a re-export through a barrel file — and the asymmetry is the
  argument: a missing dep degrades a prompt, an invented one poisons it and
  reads as authoritative.
* **A request that cannot be decomposed produces an explanation.** There is no
  fallback that wraps an unparsed prompt in one big contract. A degenerate
  single contract is worse than a refusal, because it looks like a plan.
* **Nothing is emitted whose worker view will not fit under a stated ceiling.**
  :func:`_resize` sizes ``context.max_input_tokens`` to what the worker will
  actually be sent, and a budget derived from the content can never be exceeded
  by the content — so without a stop, inlining a large file would raise the
  ceiling to swallow it and the fit check would become a tautology. The ceiling
  is the stop, and exceeding it is a refusal (#155).
* **Nothing is emitted that no configured ladder can serve.** The check is the
  catalog's own :meth:`~mcgyvr.catalog.Catalog.servable`, against a real config —
  a keyless install genuinely cannot run a type that must start on ``api``, and
  the honest answer is to say so by name rather than to route optimistically and
  fail at dispatch.
* **A type whose evidence only a checker can produce is emitted with that
  checker's command, or not emitted.** This is ADR-0006's other half, and #142's
  whole subject; see :func:`_acceptance_for`.

**The proposer seam.** :data:`Proposer` is where judgment enters, and it has no
default binding. A caller supplies one; the tests supply a fixed one, which is
what makes "the same prompt and repository yield the same shape" an assertion
about this module rather than about a model's temperature. The deterministic
pass always runs first and is handed to the proposer as evidence (ADR-0001
boundary 2) — a proposer cannot ask for the repository, only read what
exploration already found.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from mcgyvr import contract as contract_module
from mcgyvr.catalog import TaskType, catalog
from mcgyvr.contract import Contract, ContractError
from mcgyvr.gate.adapter import LanguageAdapter
from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.orchestrator.index import Index
from mcgyvr.orchestrator.read import Exploration, estimate_tokens, explore
from mcgyvr.orchestrator.resolve import Resolution, resolve
from mcgyvr.orchestrator.symbols import SymbolKind

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pathlib import Path

    from mcgyvr.config import Config

# How much of the identifying material goes into a contract id. Short enough to
# read in a log line, long enough that two different units of work in one
# decomposition do not collide by accident — and a collision is refused rather
# than silently resolved, so this is a readability choice, not a safety one.
_ID_DIGEST_BYTES = 5

# The ceiling `context.max_input_tokens` may be sized up to, in estimated
# tokens. **Policy, not measurement.** Nothing mcgyvr reads declares a rung's
# context window — not `baseline.config.json`, not the capability table, whose
# entries carry quality, throughput and VRAM and no window at all — so there is
# nothing here to derive the number from and it is chosen rather than computed.
# It is a default, and a caller that knows its ladder should say so instead:
# `decompose(..., max_input_tokens=...)`. #158 is where a declared per-rung
# window would replace it, at which point this becomes a fallback for the
# unconfigured case rather than the operative bound.
_DEFAULT_MAX_INPUT_TOKENS = 32768

# The one evidence kind a locator can supply the command for, named as the
# catalog names it. Keying on the string is the coupling that belongs here: the
# catalog is the vocabulary, and `data/task-catalog.json` is where "type_check"
# means "The project's type checker passes on the changed target". The other two
# command-needing kinds — `tests_pass`, `failing_test_first` — are deliberately
# absent; see :func:`_acceptance_for`.
_TYPE_CHECK = "type_check"


@dataclass(frozen=True)
class DepRef:
    """A reference to a dependency: where it lives and what it is called.

    Deliberately not a signature. The decomposer names the symbol; the index
    states what it looks like (ADR-0007). ``note`` is the one free-text field,
    because "how the target is expected to use this" is a judgement about
    relevance and there is nothing in the repository to read it off.
    """

    path: str
    symbol: str
    note: str = ""


@dataclass(frozen=True)
class Proposal:
    """One unit of work the judgment step proposes — references, not facts.

    Everything here is either a choice from a fixed vocabulary (``task_type``),
    a pointer into the repository (``target``, ``deps``), or text a model is the
    right author of (``task``, ``interface``, ``note``). What a symbol looks
    like, whether the type can be served, and whether the whole thing validates
    are all decided downstream, from the repository and the schema.

    ``allow`` defaults to the target alone. That is the smallest scope a
    contract can have, and #50 asks for the smallest well-scoped unit a rung can
    actually complete — so widening the scope is a decision a proposer has to
    make explicitly rather than one it gets by leaving a field blank.
    """

    task_type: str
    task: str
    target: str
    interface: str = ""
    deps: tuple[DepRef, ...] = ()
    allow: tuple[str, ...] = ()
    forbid: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    risk: str = ""
    """Empty means "let the schema's default stand" rather than a fourth level."""


@dataclass(frozen=True)
class Evidence:
    """The deterministic pass a proposer is given to judge from.

    Handed over rather than made available: a proposer receives what exploration
    already found and has no way to ask the repository for more. That is
    ADR-0001 boundary 2 expressed as a type — supplied context accelerates the
    deterministic pass and cannot replace it, and a seam that could re-read the
    tree would be a second, unbounded exploration nobody costed.
    """

    prompt: str
    index: Index
    resolution: Resolution
    exploration: Exploration
    vocabulary: tuple[TaskType, ...]
    """The task types this configuration can actually serve, cheapest first."""


Proposer = Callable[[Evidence], Sequence[Proposal]]
"""The judgment step. No default binding: a caller supplies one.

Given the deterministic evidence, return the units of work to emit — or nothing,
which is a refusal to decompose and is reported as one.
"""


@dataclass(frozen=True)
class Refusal:
    """One thing that was not emitted, and what would have to change.

    ``subject`` names what was refused — a target path, or the request itself
    when nothing could be proposed at all — so a refusal list reads as an
    account rather than as a wall of prose.
    """

    subject: str
    reason: str

    def __str__(self) -> str:
        return f"{self.subject}: {self.reason}"


@dataclass(frozen=True)
class Decomposition:
    """What a prompt and a repository yielded: contracts, and what was refused.

    Both halves are always present. A decomposition that emitted nothing is not
    an error — it is a result with an empty contract list and refusals that say
    why, which is the difference between "I cannot do this" and a traceback.
    """

    contracts: tuple[Contract, ...] = ()
    refusals: tuple[Refusal, ...] = ()
    documents: tuple[str, ...] = ()
    """Each contract's emitted text, in the order the contracts appear."""

    resolution: Resolution | None = None
    exploration: Exploration | None = None

    @property
    def empty(self) -> bool:
        """Whether nothing was emitted. Always accompanied by a refusal."""
        return not self.contracts

    def explain(self) -> str:
        """Why nothing was emitted, or what was — one line per outcome."""
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
) -> Decomposition:
    """Turn ``prompt`` and an indexed repository into validated contracts.

    Runs the deterministic pass — resolution, then bounded reads — hands it to
    ``propose`` as :class:`Evidence`, and turns each proposal into a contract by
    resolving its references against the index and putting the result through
    the public contract loader. Anything that cannot be emitted comes back as a
    :class:`Refusal` naming what would have to change.

    ``config`` is what makes "no configured ladder can serve this" answerable.
    Without one the ladder check is skipped and the whole vocabulary is offered,
    which is the right behaviour for inspecting a repository before a machine is
    configured — and the emitted contracts are then only as routable as the
    config that eventually loads them.

    ``adapters`` are consulted for the one thing a proposal cannot state and the
    repository can: which type checker it runs (:func:`_acceptance_for`). The
    default is the gate's own set, so a decomposition and the gate that later
    judges it agree on which language owns a file by construction rather than by
    two lists being kept in step.

    ``max_input_tokens`` is the ceiling a contract's own budget may be sized up
    to (:func:`_resize`), and therefore what decides whether a target is small
    enough to send. It is a policy number this project has no measurement for —
    see :data:`_DEFAULT_MAX_INPUT_TOKENS` — so a caller that knows what its
    ladder can actually accept should pass its own.

    Never raises for an undecomposable request: a prompt nothing can be made of
    returns a :class:`Decomposition` whose ``contracts`` is empty and whose
    ``refusals`` say why.
    """
    resolution = resolve(index, prompt)
    exploration = (
        explore(index, resolution)
        if budget is None
        else explore(index, resolution, budget=budget)
    )
    vocabulary = _vocabulary(config)
    owners = tuple(adapters) if adapters is not None else _default_adapters()
    evidence = Evidence(
        prompt=prompt,
        index=index,
        resolution=resolution,
        exploration=exploration,
        vocabulary=vocabulary,
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
        emitted = _emit(proposal, index, vocabulary, seen, owners, max_input_tokens)
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
    """The task types on offer: all of them, or the ones a config can serve."""
    known = catalog()
    if config is None:
        return known.task_types
    return known.servable(config)


def _default_adapters() -> tuple[LanguageAdapter, ...]:
    """The gate's own adapter set.

    The same pair :class:`~mcgyvr.gate.runner.Gate` builds, so "which language
    owns this file" means one thing on both sides of the seam rather than two
    lists that have to be kept in step.
    """
    return (PythonAdapter(), JavaScriptAdapter())


def _emit(
    proposal: Proposal,
    index: Index,
    vocabulary: tuple[TaskType, ...],
    seen: dict[str, str],
    adapters: Sequence[LanguageAdapter],
    ceiling: int,
) -> tuple[Contract, str] | Refusal:
    """One proposal as a validated contract, or the reason it is not one.

    The order of the checks is the order in which a failure is cheapest to
    explain: the vocabulary before the repository, the repository before the
    schema. A caller that named an unservable type is told that, rather than
    being told about a target that was never the problem. The repository's
    type checker is looked for before this proposal's own references are
    resolved for the same reason — "this repository runs no checker" is a fact
    about the whole tree, and reporting it first stops one repository-level
    truth arriving disguised as a different complaint per proposal.
    """
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
    acceptance = _acceptance_for(proposal, kind, index.root, adapters)
    if isinstance(acceptance, Refusal):
        return acceptance
    proposal = replace(proposal, acceptance=acceptance)

    dependencies: list[dict[str, str]] = []
    for ref in proposal.deps:
        signature = _signature_for(index, ref)
        if signature is None:
            return Refusal(
                proposal.target,
                f"the index cannot state a signature for {ref.symbol!r} in "
                f"{ref.path!r}, so the dependency would have to be described "
                "rather than stated (ADR-0007) — omit it and let the worker "
                "report BLOCKED, or name a symbol the parser defines there",
            )
        dependencies.append(
            {"path": ref.path, "signature": signature, "note": ref.note}
        )

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
    resized = _resize(built, document, ceiling)
    if isinstance(resized, Refusal):
        return Refusal(proposal.target, resized.reason)
    return resized


def _unservable_reason(task_type: str, servable: set[str]) -> str:
    """Why a type is not on offer: unknown, or known but unreachable here."""
    known = catalog()
    if known.get(task_type) is None:
        excluded = known.excluded_entry(task_type)
        if excluded is not None:
            return (
                f"{task_type!r} was removed from the vocabulary: {excluded.reason}"
                + (
                    f" — use {excluded.superseded_by!r} instead"
                    if excluded.superseded_by
                    else ""
                )
            )
        return f"{task_type!r} is not a task type. Valid: {', '.join(known.names)}"
    family = known.require(task_type).starts_on.name
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
) -> tuple[str, ...] | Refusal:
    """The contract's acceptance list: the proposal's, or the repository's checker.

    ADR-0006 ends with a gap it names precisely — "the schema already demands a
    type-check command for the one task type whose guarantee requires one, and
    nothing yet supplies it. What is missing is not a step; it is whoever fills
    the list in." This is that. The locator (#114) reads what the repository
    declared; this puts it where #38's sandboxed runner already looks.

    Three rules, in this order:

    * **A proposal that declares its own commands is never touched** — not
      overruled, and not appended to. ``locate_type_check_command`` documents
      itself as "a fallback for when the contract declares no acceptance
      command; the contract always wins when it does", and appending would make
      the contract win *and also* lose.
    * **Only ``type_check`` is filled in.** ``tests_pass`` and
      ``failing_test_first`` also need commands and are deliberately left to
      fail at the loader. A located test command is a much weaker claim than a
      located checker — ``locate_test_command`` returns ``pytest`` for any
      repository with a ``tests/`` directory, which is a guess about the runner,
      not a reading of a declaration — and ``failing_test_first`` needs a
      *specific* test that fails before the change and passes after, which no
      locator can name at all.
    * **No checker means no contract.** ADR-0006: "Where the locator returns
      ``None``, the decomposer does not emit ``type_annotation`` for that
      repository — the contract would fail to load anyway, which is the correct
      outcome arriving at the correct layer." Refusing here rather than letting
      :func:`_load` reject it is what turns a schema complaint into a sentence
      about the repository.

    **The command is emitted exactly as located.** Nothing is appended — not the
    target, not a path, not a flag — and that closes the question #114 left for
    this layer ("a repository whose ``[tool.mypy]`` sets no ``files`` gets a
    command that needs a target, and supplying it is the decomposer's job, since
    only it knows what the change touched"). The premise is right and the
    conclusion does not follow, on three measurements taken here:

    1. ``tsc --noEmit path/to/file.ts`` **discards ``tsconfig.json`` entirely** —
       naming files on the command line is how you tell ``tsc`` to ignore the
       project. On a project with ``strict: true``, ``tsc --noEmit`` reports
       ``TS7006`` and exits 2 while ``tsc --noEmit src/a.ts`` over the same file
       exits 0. Appending the target would not narrow the check; it would
       silently replace it with a weaker one that passes, which is worse than
       no check because it reports success.
    2. mypy's ``exclude`` is not applied to a file named on the command line. On
       a tree whose ``[tool.mypy]`` excludes ``pkg/vendor/``, bare ``mypy``
       exits 0 and ``mypy pkg/vendor/bad.py`` exits 1 on the same file.
       Appending the target would type-check a file the repository said to skip
       — inventing scope, which is the one thing ADR-0006 forbids.
    3. The failure the question feared does not reach the worker.
       :meth:`~mcgyvr.gate.acceptance.Acceptance.precondition` runs the whole
       list against the **unchanged** tree before the first attempt, so a
       repository whose bare ``mypy`` cannot run (exit 2, "Missing target
       module, package, files, or command") is a ``PreflightIssue`` — an
       orchestration fault, named, with no attempt spent. So is a repository
       carrying a backlog of pre-existing type errors, which is the larger
       version of the same problem and which no amount of argument-appending
       would have fixed.

    A per-file type check is not a smaller version of a project-wide one. It is
    a different check, and in one of the two launch languages it is not
    expressible at all — the same asymmetry #133 measured, arriving here.
    """
    if proposal.acceptance:
        return proposal.acceptance
    if _TYPE_CHECK not in kind.evidence_names:
        return proposal.acceptance

    owner = _owner(proposal.target, adapters)
    if owner is None:
        languages = ", ".join(a.name for a in adapters) or "none"
        return Refusal(
            proposal.target,
            f"no language adapter owns {proposal.target!r}, so the checker that "
            f"would judge {kind.name!r} cannot be located — its guarantee needs "
            f"evidence only a type checker can produce. Retarget a file in a "
            f"language this build carries ({languages}), or declare the command "
            f"in the proposal's acceptance",
        )

    located = owner.locate_type_check_command(root)
    if located is None:
        return Refusal(
            proposal.target,
            f"this repository declares no type checker, so {kind.name!r} is not "
            f"available here — its guarantee needs evidence only a checker can "
            f"produce, and mcgyvr runs the one the repository configured rather "
            f"than choosing one (ADR-0006). Configure a checker in the "
            f"repository, or declare the command in the proposal's acceptance",
        )
    return (shlex.join(located),)


def _owner(path: str, adapters: Sequence[LanguageAdapter]) -> LanguageAdapter | None:
    """The first adapter claiming ``path``, or ``None`` if no language owns it."""
    return next((a for a in adapters if a.owns(path)), None)


def _indexed(index: Index, path: str) -> bool:
    return any(file.path == path for file in index.files)


def _content_of(index: Index, target: str) -> str:
    """The target's current content as the index holds it, or ``""``.

    **From the index, not from a fresh read.** The index is the state resolution
    and exploration already judged from, so taking the bytes from anywhere else
    would let one decomposition emit two contracts that disagree about one file
    — and would put a second, unbounded read inside a step whose whole cost
    model is "the index was built once". The reconstruction is exact rather than
    approximate: :func:`~mcgyvr.orchestrator.index.index_source` builds
    ``lines`` as ``text.split("\\n")`` over a ``surrogateescape`` decode, and
    joining on the same separator inverts it byte for byte.

    Absence is not an error, and it has three causes that the empty string does
    not distinguish between, because nothing downstream needs it to: the file
    does not exist, the index skipped it (binary, or past its size cap), or the
    target is a pattern and there is no one file it could be the content of. The
    contract loader states the same rule from the other side — content against a
    pattern target is rejected — so an empty result here is the only one that
    could load anyway.
    """
    for file in index.files:
        if file.path == target:
            return "\n".join(file.lines)
    return ""


def _signature_for(index: Index, ref: DepRef) -> str | None:
    """The signature the index holds for ``ref``, or ``None`` if it holds none.

    Only a definition in the named file counts. A symbol defined somewhere else
    under the same name is a different symbol, and an import of it is a mention
    rather than a statement of what it looks like.
    """
    for symbol in index.symbols.definitions(ref.symbol):
        if symbol.path == ref.path and symbol.kind is SymbolKind.DEFINITION:
            return symbol.signature or None
    return None


def _identify(proposal: Proposal) -> str:
    """A contract id that is a function of the work, not of when it was made.

    Reproducibility is the whole point: the same prompt over the same repository
    must yield the same contracts, and an id drawn from a clock or a counter
    would defeat that at the first field. Derived from what makes this unit of
    work distinct, so two genuinely identical proposals collide — which is
    caught and refused rather than papered over with an ordinal.
    """
    material = json.dumps(
        [proposal.task_type, proposal.target, proposal.task, proposal.interface]
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
    """The contract as plain data, before the loader has agreed to it.

    Only the fields the proposal actually determines are written. Everything
    else is left out so the schema's own defaults apply — writing them here
    would copy the schema into this module, and the copy would be the thing that
    drifts.

    ``target_content`` is passed rather than read off the proposal for the
    reason the module docstring gives: it is a fact about the repository, and
    :class:`Proposal` has no field a judgement could state it in.
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
    if proposal.interface:
        document["interface"] = proposal.interface
    if dependencies:
        document["deps"] = dependencies
    if proposal.stop_conditions:
        document["stop_conditions"] = list(proposal.stop_conditions)
    if proposal.acceptance:
        document["acceptance"] = list(proposal.acceptance)
    if proposal.risk:
        document["risk"] = proposal.risk
    if max_input_tokens is not None:
        document["context"] = {"max_input_tokens": max_input_tokens}
    return document


def _load(document: dict[str, Any]) -> Contract | Refusal:
    """The document through the public loader, or the loader's own complaint.

    Serialising and re-parsing rather than constructing a :class:`Contract`
    directly is the point: this is the same path a hand-written contract takes,
    so an emission that direct mode would reject cannot leave this module.
    """
    try:
        return contract_module.loads(json.dumps(document))
    except ContractError as exc:
        return Refusal("", f"the emitted contract does not validate — {exc}")


def _resize(
    built: Contract, document: dict[str, Any], ceiling: int
) -> tuple[Contract, str] | Refusal:
    """Size ``context.max_input_tokens`` to what the worker will actually be sent.

    The budget is declared on the contract so that a prompt which will not fit
    fails before a rung is spent (`contract.py`), and
    :func:`~mcgyvr.gate.preflight.check_prompt_fits` is what enforces it. Sizing
    it here closes the loop #115 left open: the measurement is of
    :meth:`~mcgyvr.contract.Contract.worker_view`, which is the only accessor a
    worker prompt may be built from, so what is measured is what will be sent.

    The schema's default is a floor, never a ceiling — a small contract keeps the
    declared default rather than being given a suspiciously precise budget. No
    margin is added on top: the estimator's error band is #117's to measure, and
    a margin invented here would be exactly the unsourceable constant ADR-0007
    rejected.

    ``ceiling`` is where the sizing stops, and #155 is why it has to exist at
    all. Once the target's own content is part of the view, a budget derived
    from the view is a budget the view can never exceed: inline a 4 000-line
    file and ``max_input_tokens`` simply grows to fit it, so
    :func:`~mcgyvr.gate.preflight.check_prompt_fits` would be asking whether a
    number exceeds itself. Refusing at the ceiling is what keeps that check
    answerable — and refusing rather than emitting a blind contract is the
    honest reading of the output protocol, not merely the strict one: with
    ``output_schema: whole_file`` the worker's reply *is* the file's complete
    new content, so a target too large to send is a target too large to receive
    back. The contract would be undispatchable in both directions.
    """
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
    if isinstance(reloaded, Refusal):  # pragma: no cover - the first load passed
        return built, contract_module.dumps(built)
    return reloaded, contract_module.dumps(reloaded)


def _too_large_reason(built: Contract, needed: int, ceiling: int) -> str:
    """Why a contract will not be emitted, in the terms that make it actionable.

    The target's own share is named separately when it has one, because the two
    cases have different fixes: a view dominated by the file says narrow the
    target, and a view that is large without it says the contract is carrying
    too much else.
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
    """The proposal a built contract stands for, for the one rebuild above."""
    return Proposal(
        task_type=built.task_type,
        task=built.task,
        target=built.target,
        interface=built.interface,
        allow=built.scope.allow,
        forbid=built.scope.forbid,
        stop_conditions=built.stop_conditions,
        acceptance=built.acceptance,
        risk=built.risk,
    )


@dataclass(frozen=True)
class RecordedProposer:
    """A proposer that returns a fixed list — the seam's testing counterpart.

    Not a stand-in for judgment. It exists so that "the same prompt and
    repository yield the same shape" can be asserted about *this* module, with
    the one non-deterministic ingredient held still, and so that a caller
    holding proposals from anywhere else — a file, another agent, a model it
    called itself — can drive decomposition without implementing the protocol.
    """

    proposals: tuple[Proposal, ...] = ()
    seen: list[Evidence] = field(default_factory=list)

    def __call__(self, evidence: Evidence) -> Sequence[Proposal]:
        self.seen.append(evidence)
        return self.proposals
