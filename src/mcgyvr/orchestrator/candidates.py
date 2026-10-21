"""The deterministic candidate-set layer between `Evidence` and `Proposal`.

Each contract field is enumerated as a ranked :class:`CandidateSet` of
:class:`FieldCandidate` values: one value per rank, with rank 0 the value
:func:`collapse` folds into a :class:`~mcgyvr.orchestrator.decompose.Proposal`.
A :class:`Provenance` tag records whether a template authored the value
(DETERMINISTIC) or a jev answer chose it (MODEL). The classifier proposer
builds a plan, promotes its jev answers to rank 0 with :func:`choose`, and
collapses it, so the emitted proposal is byte-identical to the one it
hand-built before this layer existed.

:func:`enumerate_candidates` and :func:`collapse` are built and unit-tested
here but are NOT wired into ``decompose``/``authoring`` yet: the pure
deterministic collapse picks the first target/type/symbol, which is not what
the classifier chooses.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from mcgyvr.catalog import TaskType, catalog
from mcgyvr.contract import generic_stop_condition
from mcgyvr.orchestrator.decompose import DepRef, Evidence, Proposal
from mcgyvr.orchestrator.symbols import Symbol, SymbolKind

#: One typed question carries at most 62 options: the single-token labels read
#: back are A-Z, a-z and 0-9. Targets are truncated to this, and the symbol
#: question keeps one slot back for the "no specific symbol" option.
_MAX_CHOICE_OPTIONS = 62

#: The option that picks no symbol, because the whole file is the work.
_NO_SYMBOL = ""


class Provenance(StrEnum):
    """Who authored a candidate: a deterministic template, or a model choice."""

    DETERMINISTIC = "deterministic"
    MODEL = "model"


@dataclass(frozen=True)
class FieldCandidate:
    """One value a contract field may take, ranked, with a provenance tag."""

    id: str  # stable within its CandidateSet (value is the dedup key)
    value: Any  # str | tuple[str, ...] | tuple[DepRef, ...]
    rank: int  # 0-based; lower wins; rank-0 collapses
    provenance: Provenance = Provenance.DETERMINISTIC


@dataclass(frozen=True)
class CandidateSet:
    """The ranked, ordered candidates for one field."""

    field: str
    candidates: tuple[FieldCandidate, ...]  # sorted by rank, ascending

    @property
    def rank0(self) -> FieldCandidate | None:
        return self.candidates[0] if self.candidates else None


CandidatePlan = Mapping[str, CandidateSet]


def _set(field: str, values: tuple[Any, ...]) -> CandidateSet:
    """Build a candidate set whose values are ranked in the order given."""
    return CandidateSet(
        field=field,
        candidates=tuple(
            FieldCandidate(id=f"{field}:{index}", value=value, rank=index)
            for index, value in enumerate(values)
        ),
    )


def without(set: CandidateSet, values: Collection[Any]) -> CandidateSet:
    """The same candidate set minus any candidate whose value is in `values`.

    Order, ids and provenance are preserved; only the ranks are re-normalized
    to ``0..n-1``. Used by the retry loop to drop a rejected candidate.
    """
    dropped = frozenset(values)
    kept = [candidate for candidate in set.candidates if candidate.value not in dropped]
    return CandidateSet(
        field=set.field,
        candidates=tuple(
            FieldCandidate(
                id=candidate.id,
                value=candidate.value,
                rank=index,
                provenance=candidate.provenance,
            )
            for index, candidate in enumerate(kept)
        ),
    )


# --- moved deterministic helpers, verbatim from delegate.py ----------------


def candidate_targets(evidence: Evidence) -> tuple[str, ...]:
    """Paths the evidence points at: candidates first, then reads, deduplicated.

    Truncated to `_MAX_CHOICE_OPTIONS`, since each becomes one option of a
    single typed question.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for candidate in evidence.resolution.candidates:
        if candidate.path not in seen:
            seen.add(candidate.path)
            paths.append(candidate.path)
    for read in evidence.exploration.reads:
        if read.path not in seen:
            seen.add(read.path)
            paths.append(read.path)
    return tuple(paths[:_MAX_CHOICE_OPTIONS])


def symbols_of(evidence: Evidence, target: str) -> tuple[Symbol, ...]:
    """The symbols the index holds as definitions in `target`, in index order."""
    return tuple(
        symbol
        for symbol in evidence.index.symbols.all()
        if symbol.path == target and symbol.kind is SymbolKind.DEFINITION
    )


def symbol_options(symbols: Sequence[Symbol]) -> dict[str, str]:
    """Render up to 61 symbols as question options, plus one for "no symbol".

    A symbol's detail is its option text, falling back to "symbol", and a name
    appears once. `_NO_SYMBOL` is added last and means the whole file is the
    work, so the question never exceeds `_MAX_CHOICE_OPTIONS` options.
    """
    options: dict[str, str] = {}
    for symbol in symbols[: _MAX_CHOICE_OPTIONS - 1]:
        if symbol.name not in options:
            options[symbol.name] = symbol.detail or "symbol"
    options[_NO_SYMBOL] = "no specific symbol — the whole file is the work"
    return options


def kind_for(name: str, vocabulary: Sequence[TaskType]) -> TaskType | None:
    """Find the servable type named `name`, or None when this config cannot serve it."""
    return next((task for task in vocabulary if task.name == name), None)


def directive(kind: TaskType, target: str, symbol: str | None) -> str:
    """The task line: the type's doc up to its first full stop, then the subject."""
    return f"{kind.doc.split('.', 1)[0]}: {subject(target, symbol)}."


def stop_condition(kind: TaskType, target: str, symbol: str | None) -> tuple[str, ...]:
    """Stop conditions: none for a deterministic type, else the generic one.

    A deterministic type starts on a gate and needs no stop condition; any other
    gets `generic_stop_condition`, which tells the worker to report BLOCKED
    rather than decide something the contract does not state.
    """
    if kind.deterministic:
        return ()
    return (generic_stop_condition(kind.name, subject(target, symbol)),)


def subject(target: str, symbol: str | None) -> str:
    """Name the work's subject: the file alone, or the symbol within it."""
    return target if symbol is None else f"{symbol} in {target}"


def completable(vocabulary: Sequence[TaskType]) -> tuple[TaskType, ...]:
    """The servable types a classifier can propose: those needing no commands.

    A type whose evidence requires acceptance or demonstration commands is left
    out, because a typed answer cannot supply the commands themselves.
    """
    return tuple(
        task
        for task in vocabulary
        if not task.needs_acceptance_commands and not task.needs_demonstration_commands
    )


# --- per-field enumerators --------------------------------------------------


def task_type_candidates(evidence: Evidence) -> CandidateSet:
    """The servable types a classifier can complete, cheapest family first."""
    return _set(
        "task_type", tuple(kind.name for kind in completable(evidence.vocabulary))
    )


def target_candidates(evidence: Evidence) -> CandidateSet:
    """The paths the evidence points at: candidates first, then reads, deduped."""
    return _set("target", candidate_targets(evidence))


def symbol_candidates(evidence: Evidence, target: str) -> CandidateSet:
    """Definition names in `target`, index order, with the no-symbol option last."""
    names: list[str] = []
    seen: set[str] = set()
    for symbol in symbols_of(evidence, target)[: _MAX_CHOICE_OPTIONS - 1]:
        if symbol.name not in seen:
            seen.add(symbol.name)
            names.append(symbol.name)
    names.append(_NO_SYMBOL)
    return _set("symbol", tuple(names))


def task_candidates(
    kind: TaskType | None, target: str, symbol: str | None
) -> CandidateSet:
    """The one deterministic directive line; richer candidates are deferred.

    The template authors the text from a subject the model picked, so this is
    deterministic authorship rather than a model decision.
    """
    if kind is None:
        return _set("task", ("",))
    return _set("task", (directive(kind, target, symbol),))


def stop_condition_candidates(
    kind: TaskType | None, target: str, symbol: str | None
) -> CandidateSet:
    """No stop condition for a deterministic type, else the generic one."""
    if kind is None:
        return _set("stop_conditions", ((),))
    return _set("stop_conditions", (stop_condition(kind, target, symbol),))


def interface_candidates(
    evidence: Evidence, target: str, symbol: str | None
) -> CandidateSet:
    """The chosen symbol's signature, then the other signatures in `target`.

    Rank 0 is "" (the classifier states none). The rest are raw
    `Symbol.signature` values for DEFINITION/EXPORT symbols in the target, in
    index order, with the chosen symbol first and duplicates dropped.
    """
    signatures: list[str] = []
    seen: set[str] = {""}
    symbols = tuple(
        s
        for s in evidence.index.symbols.all()
        if s.path == target and s.kind in (SymbolKind.DEFINITION, SymbolKind.EXPORT)
    )
    chosen: Symbol | None = None
    if symbol is not None:
        chosen = next((s for s in symbols if s.name == symbol), None)
        if chosen is not None:
            _add_signature(chosen, signatures, seen)
    for s in symbols:
        if chosen is not None and s is chosen:
            continue
        _add_signature(s, signatures, seen)
    return _set("interface", ("", *signatures))


def _add_signature(symbol: Symbol, signatures: list[str], seen: set[str]) -> None:
    """Record `symbol`'s signature once, skipping the empty one (rank 0)."""
    signature = symbol.signature or ""
    if signature not in seen:
        seen.add(signature)
        signatures.append(signature)


def deps_candidates(evidence: Evidence, target: str) -> CandidateSet:
    """Dependencies the target's imports resolve to in other files.

    Each IMPORT in `target` whose name names a DEFINITION in a different file
    becomes a `DepRef`, in import order, deduplicated and capped.
    """
    deps: list[DepRef] = []
    seen: set[tuple[str, str]] = set()
    for imported in evidence.index.symbols.imports(target):
        for definition in evidence.index.symbols.definitions(imported.name):
            if definition.path == target:
                continue
            key = (definition.path, definition.name)
            if key not in seen:
                seen.add(key)
                deps.append(DepRef(path=definition.path, symbol=definition.name))
    return _set("deps", ((), *deps[:_MAX_CHOICE_OPTIONS]))


def sources_candidates(evidence: Evidence, target: str) -> CandidateSet:
    """The other files the evidence touches, excluding `target`, deduplicated.

    Reads come first, then resolution candidates, matching the field table; the
    target itself is always left out.
    """
    paths: list[str] = []
    seen: set[str] = {target}
    for read in evidence.exploration.reads:
        if read.path not in seen:
            seen.add(read.path)
            paths.append(read.path)
    for candidate in evidence.resolution.candidates:
        if candidate.path not in seen:
            seen.add(candidate.path)
            paths.append(candidate.path)
    return _set("sources", ((), *paths[:_MAX_CHOICE_OPTIONS]))


def acceptance_candidates(evidence: Evidence, kind: TaskType | None) -> CandidateSet:
    """Acceptance commands from the baseline run only (no disk probe here).

    Rank 0 is () — the classifier states none. When the kind derives evidence
    and a baseline was observed, its acceptance commands are the rank-1
    candidate.
    """
    values: list[Any] = [()]
    if kind is not None and kind.evidence_derived and evidence.baseline is not None:
        acceptance = evidence.baseline.acceptance()
        if acceptance:
            values.append(acceptance)
    return _set("acceptance", tuple(values))


def demonstration_candidates(evidence: Evidence, kind: TaskType | None) -> CandidateSet:
    """Demonstration commands from the baseline run only (no disk probe here).

    Rank 0 is () — the classifier states none. When the kind derives evidence
    and a baseline was observed, its demonstration commands are the rank-1
    candidate.
    """
    values: list[Any] = [()]
    if kind is not None and kind.evidence_derived and evidence.baseline is not None:
        demonstration = evidence.baseline.demonstrations()
        if demonstration:
            values.append(demonstration)
    return _set("demonstration", tuple(values))


def scope_candidates(
    evidence: Evidence, target: str
) -> tuple[CandidateSet, CandidateSet]:
    """Allow and forbid candidates.

    `allow` rank 0 must be () (omit → target default downstream), rank 1 is the
    target alone, rank 2 is every evidence path. `forbid` has only rank 0 () in
    W2.
    """
    allow_values: list[Any] = [()]
    if target:
        allow_values.append((target,))
    paths = candidate_targets(evidence)
    if paths and paths != (target,):
        allow_values.append(paths)
    return _set("allow", tuple(allow_values)), _set("forbid", ((),))


def operation_candidates() -> CandidateSet:
    """The deterministic operation names, catalog order; rank 0 is ""."""
    names = tuple(operation.name for operation in catalog().operations)
    return _set("operation", ("", *names))


# --- the plan and its collapse ---------------------------------------------


def enumerate_candidates(evidence: Evidence) -> CandidatePlan:
    """Enumerate the deterministic candidates for every contract field.

    The rank-0 target and kind pick the rank-0 symbol, which in turn derives
    the rank-0 task and stop conditions. The pure deterministic collapse of
    this plan is test-only in W2: it is not what the classifier emits.
    """
    kinds = completable(evidence.vocabulary)
    kind = kinds[0] if kinds else None  # rank-0 task type
    target_set = target_candidates(evidence)
    target0 = target_set.rank0
    target = target0.value if target0 is not None else ""

    symbol_set = symbol_candidates(evidence, target)
    symbol0 = symbol_set.rank0
    symbol_name = symbol0.value if symbol0 is not None else _NO_SYMBOL
    symbol = None if symbol_name == _NO_SYMBOL else symbol_name

    allow, forbid = scope_candidates(evidence, target)
    return {
        "task_type": task_type_candidates(evidence),
        "target": target_set,
        "symbol": symbol_set,
        "task": task_candidates(kind, target, symbol),
        "stop_conditions": stop_condition_candidates(kind, target, symbol),
        "interface": interface_candidates(evidence, target, symbol),
        "deps": deps_candidates(evidence, target),
        "sources": sources_candidates(evidence, target),
        "acceptance": acceptance_candidates(evidence, kind),
        "demonstration": demonstration_candidates(evidence, kind),
        "allow": allow,
        "forbid": forbid,
        "operation": operation_candidates(),
    }


def collapse(plan: CandidatePlan) -> Proposal:
    """Fold rank-0 of each field into one Proposal."""

    def value(field: str, default: Any) -> Any:
        s = plan.get(field)
        return default if s is None or s.rank0 is None else s.rank0.value

    return Proposal(
        task_type=value("task_type", ""),
        task=value("task", ""),
        target=value("target", ""),
        interface=value("interface", ""),
        deps=value("deps", ()),
        allow=value("allow", ()),
        forbid=value("forbid", ()),
        stop_conditions=value("stop_conditions", ()),
        acceptance=value("acceptance", ()),
        demonstration=value("demonstration", ()),
        operation=value("operation", ""),
        sources=value("sources", ()),
        depends_on=value("depends_on", ()),
    )


def choose(
    plan: CandidatePlan,
    field: str,
    value: Any,
    *,
    provenance: Provenance = Provenance.MODEL,
) -> CandidatePlan:
    """Replace `field`'s set with one whose rank-0 is `value` (provenance-tagged).

    The previous candidates stay below it at rank 1+, in their original order,
    except any whose value equals the promoted one (it is now rank 0, so the
    duplicate is dropped).

    NOTE: promoting a model's target/symbol rewrites only those fields; the
    `interface`/`deps`/`sources` sets still reflect the deterministic rank-0
    target/symbol. Harmless now because their rank-0 is the empty default, but
    a trap when this layer is later wired into authoring.
    """
    current = plan.get(field)
    chosen = FieldCandidate(
        id=f"{field}:{provenance.value}",
        value=value,
        rank=0,
        provenance=provenance,
    )
    if current is None:
        candidates: tuple[FieldCandidate, ...] = (chosen,)
    else:
        rest = tuple(
            FieldCandidate(
                id=c.id, value=c.value, rank=index + 1, provenance=c.provenance
            )
            for index, c in enumerate(c for c in current.candidates if c.value != value)
        )
        candidates = (chosen, *rest)
    return {**plan, field: CandidateSet(field=field, candidates=candidates)}
