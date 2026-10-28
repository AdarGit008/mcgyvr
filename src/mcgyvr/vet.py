"""Vet a contract set someone wrote, the way a proposal is vetted.

`mcgyvr direct` takes contracts a person or a session model wrote, where the
bare verb takes the ones its proposer proposed. From there the two are one
process, and it starts here: every contract is put to the checks
`decompose.emit_one` puts a proposal to — the task type is servable, the
target is a file the index holds, a `type_check` acceptance can be located,
each dependency's symbol has a signature in the index or in a sibling that
creates it, the worker view fits the ceiling, and the same unit of work is not
stated twice. Those checks are `emit_one`'s own, called here, not restated.

What `emit_one` cannot see is the set as files: a file that does not load as
a contract, two files that give one id, a dependency whose signature declares
no name, a pattern target (vetted as the first indexed file it names),
`depends_on` ids that form a cycle (refused by `decompose`'s own ordering), a
view over the contract's own `context.max_input_tokens` (`emit_one` would
raise it on its copy; the author's file runs as written), and a contract that
waits on one refused here. An id the set does not hold is left to the tree,
where it may name a contract of another batch on the repository. Each is a `Refusal`
too, with the same `what_to_change` directive, so the author is told what to
change and resubmit. A contract that passes runs as it was written:
`emit_one`'s document is its verdict, never a rewrite of the author's file.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.contract import Contract, ContractError, dumps, is_pattern
from mcgyvr.contract import load as load_contract
from mcgyvr.orchestrator.decompose import (
    Decomposition,
    DepRef,
    Evidence,
    Refusal,
    _default_adapters,
    _fan_out,
    _proposal_of,
    _vocabulary,
    emit_one,
)
from mcgyvr.orchestrator.provides import declared_names
from mcgyvr.orchestrator.read import estimate_tokens, explore
from mcgyvr.orchestrator.resolve import resolve
from mcgyvr.scope import Scope

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.orchestrator.index import Index


@dataclass(frozen=True)
class Vetted:
    """What vetting a set came to: a `Decomposition`, and the file of each contract.

    `decomposition` holds the contracts that passed, in the order their files
    were given, each beside its own text, and a refusal for each that did not;
    `paths` is parallel to its contracts.
    """

    decomposition: Decomposition
    paths: tuple[Path, ...]


def vet(paths: Sequence[Path], index: Index, *, config: Config | None = None) -> Vetted:
    """Load and vet the contracts at `paths` against `index`.

    The servable task types are `config`'s (every known type with none). A
    refusal's subject is the file it is about, so an author knows which to
    change; its reason and directive are the check's own.
    """
    loaded: list[tuple[Path, Contract]] = []
    refused: dict[Path, Refusal] = {}
    first: dict[str, Path] = {}
    for path in paths:
        try:
            contract = load_contract(path)
        except ContractError as exc:
            refused[path] = Refusal(
                str(path),
                f"it does not load as a contract: {exc}",
                field="",
                what_to_change=str(exc),
            )
            continue
        if contract.id in first:
            refused[path] = Refusal(
                str(path),
                f"its id {contract.id!r} is the id of {first[contract.id]} too, and "
                "one set holds one contract per id",
                field="id",
                what_to_change="give each contract in the set its own id",
            )
            continue
        first[contract.id] = path
        loaded.append((path, contract))

    resolution = resolve(index, "")
    evidence = Evidence(
        prompt="",
        index=index,
        resolution=resolution,
        exploration=explore(index, resolution),
        vocabulary=_vocabulary(config),
    )
    adapters = _default_adapters()
    refused.update(_cycles(loaded))
    by_id = {c.id: p for p, c in loaded}
    # A dependency is stated from a sibling only while that sibling passes, as
    # `decompose` states one only from a contract it emitted: so the set is
    # vetted again, against what is left, until nothing more is refused.
    changed = True
    while changed:
        changed = False
        seen: dict[str, str] = {}
        for path, contract in loaded:
            if path in refused:
                continue
            siblings = tuple(c for p, c in loaded if p != path and p not in refused)
            verdict = _vetted(evidence, contract, seen, adapters, siblings)
            if verdict is not None:
                refused[path] = replace(verdict, subject=str(path))
                changed = True
        # One that waits on a refused contract can never start: it is refused
        # too, as `decompose` refuses a proposal that depends on a refused one.
        # An id the set does not hold is left to the tree: it may be a contract
        # of another batch on the repository's live tree.
        for path, contract in loaded:
            if path in refused:
                continue
            gone = [d for d in contract.depends_on if by_id.get(d) in refused]
            if gone:
                refused[path] = Refusal(
                    str(path),
                    f"it waits on {', '.join(gone)}, which was refused, so it could "
                    "never start",
                    field="depends_on",
                    what_to_change=(
                        "fix the contract it waits on first, or drop that id from "
                        "depends_on"
                    ),
                )
                changed = True

    passed = [(p, c) for p, c in loaded if p not in refused]
    return Vetted(
        decomposition=Decomposition(
            contracts=tuple(c for _, c in passed),
            refusals=tuple(refused[p] for p in paths if p in refused),
            documents=tuple(dumps(c) for _, c in passed),
        ),
        paths=tuple(p for p, _ in passed),
    )


def _cycles(loaded: Sequence[tuple[Path, Contract]]) -> dict[Path, Refusal]:
    """The contracts of the set whose `depends_on` ids form a cycle, refused.

    `decompose`'s own ordering (`_fan_out`) is asked, over the set's contracts
    as proposals whose `depends_on` indexes stand for the ids the set holds;
    whatever it cannot order is on a cycle, or waits on one, and is refused
    with its reason and directive.
    """
    at = {contract.id: i for i, (_, contract) in enumerate(loaded)}
    proposals = tuple(
        replace(
            _proposal_of(contract),
            depends_on=tuple(at[d] for d in contract.depends_on if d in at),
        )
        for _, contract in loaded
    )
    ordered, refusals = _fan_out(proposals)
    placed = {id(proposal) for proposal, _ in ordered}
    left = [i for i, proposal in enumerate(proposals) if id(proposal) not in placed]
    return {
        loaded[i][0]: replace(refusal, subject=str(loaded[i][0]))
        for i, refusal in zip(left, refusals, strict=True)
    }


def _vetted(
    evidence: Evidence,
    contract: Contract,
    seen: dict[str, str],
    adapters: Sequence[LanguageAdapter],
    siblings: Sequence[Contract],
) -> Refusal | None:
    """`emit_one`'s refusal of `contract`, or None when it passes.

    The contract is put as the proposal that states it (`_proposal_of`), each
    dependency as the names its signature declares, and every sibling may
    provide a symbol it depends on, as the tree reads it. A contract that
    passes is entered in `seen`, so the same unit of work stated twice is
    refused the second time.
    """
    deps: list[DepRef] = []
    for dep in contract.deps:
        names = sorted(declared_names(dep.path, dep.signature))
        if not names:
            return Refusal(
                contract.target,
                f"the dependency on {dep.path!r} states a signature that declares "
                "no name the parser reads, so it cannot be checked against the "
                "index",
                field="deps",
                what_to_change=(
                    "state the dependency's signature as its declaration, "
                    "e.g. `def name(arg: type) -> type`"
                ),
            )
        deps.extend(DepRef(dep.path, name, dep.note) for name in names)
    proposal = replace(_proposal_of(contract), deps=tuple(deps))
    if is_pattern(contract.target):
        # A pattern names files, which only a deterministic operation may
        # target; it is vetted as the first file the index holds that it
        # names, and refused when it names none.
        named = sorted(
            f.path
            for f in evidence.index.files
            if Scope.of([contract.target]).permits(f.path)
        )
        if not named:
            return Refusal(
                contract.target,
                "the pattern names no file the index holds, so the operation "
                "would have nothing to run on",
                field="target",
                what_to_change="name a pattern matching a file the repository holds",
            )
        proposal = replace(proposal, target=named[0])
    emitted = emit_one(
        evidence,
        proposal,
        seen=seen,
        adapters=adapters,
        ceiling=evidence.ceiling,
        depends_on_ids=contract.depends_on,
        providers=siblings,
    )
    if isinstance(emitted, Refusal):
        return emitted
    built, _ = emitted
    # The ceiling `emit_one` holds a proposal to is the batch's, and it raises
    # a fitting contract's own `context.max_input_tokens` to the view; a
    # written contract runs as written, so its own number must hold the view.
    needed = estimate_tokens(json.dumps(built.worker_view(), sort_keys=True))
    if needed > contract.max_input_tokens:
        return Refusal(
            contract.target,
            f"the worker view is {needed} estimated tokens and the contract's "
            f"context.max_input_tokens is {contract.max_input_tokens}, so its "
            "prompt would be refused as too large",
            field="context",
            what_to_change=(
                f"raise context.max_input_tokens to at least {needed}, or narrow "
                "the target"
            ),
        )
    seen[built.id] = contract.target
    return None
