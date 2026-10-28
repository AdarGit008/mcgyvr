"""The dependency tree of one repository's contracts, kept alive beside the queue.

A contract waits on the contracts its `depends_on` names, and on the sibling
that creates a symbol one of its `deps` names when the tree it runs against
does not define that symbol yet. `Tree` holds those edges for one set of
contracts on one repository and answers, as contracts land or fail, which are
ready to run, which still wait, and which are held because what they wait on
can no longer come.

Every answer is read from the contracts' own words and the repository's
committed tree, never asked of a model:

* An edge's *needs* are the names the dependent uses that its provider is to
  create (its `interface`, the new name of a rename its `task` states) or to
  change (a rename's old name, a name its `task` spells that its target
  defines). Its *uses* are the names the dependent imports from the provider's
  file that the provider leaves alone.
* A provider that landed satisfies the edge, unless a name it was to create is
  still not defined: it is then `provider_landed_without` that name.
* A provider that did not land holds the dependent — `provider_failed`, or
  `provider_not_landed` for one accepted but not delivered where the next
  sandbox starts from — unless the edge has no needs and every name the
  dependent uses from that file is already defined.
* A dependent of a held contract is held too (`provider_blocked`), a contract
  on a cycle (`cycle`), one waiting on an id the set does not hold once the set
  is sealed (`unknown_dependency`), and one needing a symbol nothing defines and
  nothing in the set creates (`unprovided`).

A held contract is not dead: a provider retried (`retry`) or replaced
(`replace`, the contracts a re-plan proposed in its place, `mcgyvr.replan`)
frees it again. Only `seal` — the queue drained — turns what is still held
into `dead`, the contracts that get a result with outcome `blocked` and no
attempt spent.
With `hold=False` nothing is held: a dependent runs once each provider has
come to anything at all, the order a plan without the tree ran in.

Several batches can share one tree (`mcgyvr.board`): each contract names the
`batch` that runs it, a later batch `join`s with its own contracts, `seal`
can be told whose contracts it seals, and a contract whose batch is gone is
`abandon`ed. `restore` reads a tree back from its state file.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Protocol

from mcgyvr.contract import Contract
from mcgyvr.orchestrator.provides import declared_names, identifiers, renames
from mcgyvr.orchestrator.symbols import SymbolKind, extract, language_of

#: The outcome a held contract's result is written with.
BLOCKED = "blocked"

#: The outcome a provider's climb reports when its change was accepted.
ACCEPTED = "accepted"

#: The outcome of a contract whose batch ended without settling it, and left
#: no result to settle it from.
ABANDONED = "abandoned"


class State(StrEnum):
    """Where one contract stands in its tree."""

    WAITING = "waiting"
    READY = "ready"
    RUNNING = "running"
    LANDED = "landed"
    FAILED = "failed"
    BLOCKED = "blocked"
    DEAD = "dead"


#: The states a contract does not leave unless the queue says so: started,
#: settled or sealed.
_SETTLED = frozenset({State.RUNNING, State.LANDED, State.FAILED, State.DEAD})

#: The states a contract has come to an end in.
_ENDED = _SETTLED - {State.RUNNING}


class Reason(StrEnum):
    """Why a contract is held."""

    PROVIDER_FAILED = "provider_failed"
    PROVIDER_NOT_LANDED = "provider_not_landed"
    PROVIDER_LANDED_WITHOUT = "provider_landed_without"
    PROVIDER_BLOCKED = "provider_blocked"
    CYCLE = "cycle"
    UNKNOWN_DEPENDENCY = "unknown_dependency"
    UNPROVIDED = "unprovided"


class Source(Protocol):
    """The committed tree the next contract's sandbox starts from.

    `read` returns a file's bytes, or None when the tree holds no such file.
    """

    def read(self, path: str) -> bytes | None: ...


@dataclass(frozen=True)
class Need:
    """A name a dependent uses that its provider is to create or change."""

    path: str
    symbol: str
    #: True when the provider is to create the name, False when it is to
    #: change one that is already there.
    creates: bool

    def as_json(self) -> dict[str, Any]:
        return {"path": self.path, "symbol": self.symbol, "creates": self.creates}

    @classmethod
    def from_json(cls, doc: Mapping[str, Any]) -> Need:
        return cls(str(doc["path"]), str(doc["symbol"]), bool(doc["creates"]))


@dataclass(frozen=True)
class Edge:
    """A dependent's wait on one provider, and what it waits for."""

    provider: str
    needs: tuple[Need, ...] = ()
    #: Names the dependent imports from the provider's file that the provider
    #: neither creates nor changes.
    uses: tuple[str, ...] = ()


@dataclass(frozen=True)
class Provider:
    """A provider as a hold names it: what it is and what it came to."""

    contract: str
    target: str
    outcome: str = ""
    result: str | None = None
    detail: str = ""

    def as_json(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "target": self.target,
            "outcome": self.outcome,
            "result": self.result,
        }

    @classmethod
    def from_json(cls, doc: Mapping[str, Any]) -> Provider:
        return cls(
            contract=str(doc["contract"]),
            target=str(doc["target"]),
            outcome=str(doc.get("outcome") or ""),
            result=doc.get("result"),
        )


@dataclass(frozen=True)
class Hold:
    """Why a contract is held: the reason, who held it and what it needed."""

    reason: Reason
    providers: tuple[Provider, ...] = ()
    needs: tuple[Need, ...] = ()
    #: For `provider_blocked`, the contracts the hold came down through,
    #: nearest first; for `cycle` and `unknown_dependency`, the ids involved.
    chain: tuple[str, ...] = ()

    def sentence(self) -> str:
        """The hold in one sentence, as a result's `detail` carries it."""
        tail = " — not dispatched, no rung spent."
        names = ", ".join(n.symbol for n in self.needs)
        first = self.providers[0] if self.providers else None
        who = f"{first.contract} ({first.target})" if first else "a contract"
        came = first.outcome if first else "nothing"
        if self.reason is Reason.PROVIDER_FAILED:
            if names:
                return (
                    f"held: waits on {who}, which came to {came}; it was to "
                    f"{self._work()}, which this contract needs{tail}"
                )
            return (
                f"held: waits on {who}, which came to {came}, and nothing shows "
                f"this contract can do without it{tail}"
            )
        if self.reason is Reason.PROVIDER_NOT_LANDED:
            why = f" ({first.detail})" if first and first.detail else ""
            return (
                f"held: waits on {who}, which was accepted but did not land where "
                f"this contract's sandbox starts from{why}{tail}"
            )
        if self.reason is Reason.PROVIDER_LANDED_WITHOUT:
            return (
                f"held: {who} landed without {names}, which this contract needs{tail}"
            )
        if self.reason is Reason.PROVIDER_BLOCKED:
            return (
                f"held: waits on {who}, which is itself held "
                f"(through {' -> '.join(self.chain)}){tail}"
            )
        if self.reason is Reason.CYCLE:
            return (
                f"held: its depends_on forms a cycle, or waits on one, among "
                f"{', '.join(self.chain)}, so no order lets it start{tail}"
            )
        if self.reason is Reason.UNKNOWN_DEPENDENCY:
            return (
                f"held: depends on {', '.join(self.chain)}, which this set of "
                f"contracts does not hold{tail}"
            )
        needed = ", ".join(f"{n.path}:{n.symbol}" for n in self.needs)
        return (
            f"held: needs {needed}, which the tree does not define and no contract "
            f"in this set creates{tail}"
        )

    def _work(self) -> str:
        """What the provider was to do for the needs: create some, change some."""
        made = ", ".join(n.symbol for n in self.needs if n.creates)
        changed = ", ".join(n.symbol for n in self.needs if not n.creates)
        return " and ".join(
            part
            for part in (made and f"create {made}", changed and f"change {changed}")
            if part
        )

    def as_json(self) -> dict[str, Any]:
        """The hold as a result's `blocked_by` carries it."""
        return {
            "reason": self.reason.value,
            "providers": [p.as_json() for p in self.providers],
            "needs": [n.as_json() for n in self.needs],
            "chain": list(self.chain),
        }

    @classmethod
    def from_json(cls, doc: Mapping[str, Any]) -> Hold:
        """The hold `as_json` wrote."""
        return cls(
            Reason(doc["reason"]),
            tuple(Provider.from_json(p) for p in doc.get("providers") or ()),
            tuple(Need.from_json(n) for n in doc.get("needs") or ()),
            tuple(str(c) for c in doc.get("chain") or ()),
        )


@dataclass
class _Node:
    """One contract's place in the tree, and what it came to."""

    contract: Contract
    state: State = State.WAITING
    outcome: str = ""
    detail: str = ""
    result: str | None = None
    hold: Hold | None = None
    edges: tuple[Edge, ...] = ()
    #: `deps` symbols nothing defines and nothing in the set creates.
    unprovided: tuple[Need, ...] = ()
    #: The batch that runs it, on a tree several batches share; else empty.
    batch: str = ""
    #: When it was started (a run stamp), while it runs and after.
    started: str = ""


@dataclass
class Tree:
    """The live dependency tree of one repository's contracts.

    `tree_id` names the tree on a queue that holds several. `sealed` says the
    set is whole, so an id it does not hold never will be. The contracts keep
    the order they were given in, and `ready` answers in that order.
    """

    tree_id: str
    source: Source
    hold: bool = True
    sealed: bool = True
    _nodes: dict[str, _Node] = field(default_factory=dict)
    _order: tuple[str, ...] = ()
    _cycle: frozenset[str] = frozenset()

    @classmethod
    def of(
        cls,
        contracts: Iterable[Contract],
        source: Source,
        *,
        tree_id: str,
        hold: bool = True,
        sealed: bool = True,
        batch: str = "",
    ) -> Tree:
        """A tree of `contracts` read against `source`; each starts waiting.

        `batch` names the batch that runs them, on a tree batches share.
        """
        tree = cls(tree_id=tree_id, source=source, hold=hold, sealed=sealed)
        for contract in contracts:
            if contract.id in tree._nodes:
                raise ValueError(f"{contract.id} is in this tree twice")
            tree._nodes[contract.id] = _Node(contract, batch=batch)
        tree._build()
        tree._evaluate()
        return tree

    @classmethod
    def restore(
        cls,
        doc: Mapping[str, Any],
        contracts: Mapping[str, Contract],
        source: Source,
    ) -> Tree:
        """The tree `as_json` wrote as `doc`, each contract in `contracts`.

        What each contract came to is read back; whether one not yet started
        or settled is ready, waiting or held is read again, against `source`.
        """
        tree = cls(
            tree_id=str(doc["tree"]),
            source=source,
            hold=bool(doc.get("hold", True)),
            sealed=bool(doc.get("sealed", True)),
        )
        for row in doc["contracts"]:
            cid = str(row["contract"])
            state = State(row["state"])
            blocked_by = row.get("blocked_by")
            tree._nodes[cid] = _Node(
                contracts[cid],
                state=state,
                outcome=str(row.get("outcome") or ""),
                detail=str(row.get("detail") or ""),
                result=row.get("result"),
                hold=(
                    Hold.from_json(blocked_by)
                    if state is State.DEAD and blocked_by
                    else None
                ),
                batch=str(row.get("batch") or ""),
                started=str(row.get("started") or ""),
            )
        tree._build()
        tree._evaluate()
        return tree

    # -- what the queue asks ------------------------------------------------

    def ready(self) -> tuple[Contract, ...]:
        """The contracts that may run now, in the order the tree was given."""
        self._evaluate()
        return tuple(n.contract for n in self._nodes.values() if n.state is State.READY)

    def state(self, contract_id: str) -> State:
        return self._nodes[contract_id].state

    def held(self, contract_id: str) -> Hold | None:
        """Why the contract is held, or None when it is not."""
        return self._nodes[contract_id].hold

    def contracts(self) -> tuple[Contract, ...]:
        return tuple(n.contract for n in self._nodes.values())

    def batch(self, contract_id: str) -> str:
        """The batch that runs the contract, or empty when no batch is named."""
        return self._nodes[contract_id].batch

    def started(self, contract_id: str) -> str:
        """When the contract was started (a run stamp), or empty."""
        return self._nodes[contract_id].started

    def finished(self) -> bool:
        """Whether every contract has come to an end: landed, failed or dead."""
        return all(n.state in _ENDED for n in self._nodes.values())

    def edges(self, contract_id: str) -> tuple[Edge, ...]:
        return self._nodes[contract_id].edges

    def levels(self) -> dict[str, int]:
        """Each contract's level, 1 first: one past the deepest it waits on.

        Contracts on a cycle, or waiting on one, go one past the deepest level
        that could be ordered, the way a wave plan without the tree places them.
        """
        level: dict[str, int] = {}
        for cid in self._order:
            if cid in self._cycle:
                continue
            waits = [e.provider for e in self._nodes[cid].edges if e.provider in level]
            level[cid] = 1 + max((level[p] for p in waits), default=0)
        last = max(level.values(), default=0)
        for cid in self._order:
            level.setdefault(cid, last + 1)
        return level

    # -- what the queue tells it --------------------------------------------

    def start(self, contract_id: str, *, started: str = "") -> None:
        """The contract was dispatched, at `started` when that is given."""
        node = self._nodes[contract_id]
        self._evaluate()
        if node.state is not State.READY:
            raise ValueError(f"{contract_id} is {node.state.value}, not ready")
        node.state = State.RUNNING
        node.started = started

    def settle(
        self,
        contract_id: str,
        *,
        outcome: str,
        landed: bool,
        detail: str = "",
        result: str | None = None,
    ) -> None:
        """The contract's run came to `outcome`; `landed` says its change is in
        the tree the next sandbox starts from."""
        node = self._nodes[contract_id]
        node.state = State.LANDED if landed else State.FAILED
        node.outcome = outcome
        node.detail = detail
        node.result = result
        node.hold = None
        self._evaluate()

    def retry(self, contract_id: str) -> None:
        """The contract will run again: it waits once more, and frees its dependents."""
        node = self._nodes[contract_id]
        node.state = State.WAITING
        node.outcome = node.detail = node.started = ""
        node.result = None
        node.hold = None
        self._evaluate()

    def abandon(self, contract_id: str, detail: str) -> None:
        """The contract's batch is gone and left nothing to settle it from:
        it failed, as `abandoned`, and holds what waits on it."""
        node = self._nodes[contract_id]
        node.state = State.FAILED
        node.outcome = ABANDONED
        node.detail = detail
        node.hold = None
        self._evaluate()

    def join(self, contracts: Iterable[Contract], *, batch: str) -> tuple[str, ...]:
        """A later batch's `contracts` join the tree, each waiting afresh.

        Edges are read again over every contract the tree holds, so one may
        wait on a contract of another batch, in flight or landed. A contract
        whose id the tree already holds is the same unit of work: when it has
        come to an end it is the later batch's to run again, as a retry; while
        another batch still has it in flight it is left to that batch, and its
        id comes back.
        """
        left: list[str] = []
        for contract in contracts:
            there = self._nodes.get(contract.id)
            if there is not None and there.state not in _ENDED:
                left.append(contract.id)
                continue
            self._nodes[contract.id] = _Node(contract, batch=batch)
        self._build()
        self._evaluate()
        return tuple(left)

    def replace(self, old_id: str, contract: Contract, *more: Contract) -> None:
        """`contract`, and `more`, stand for `old_id` from now on: a re-decomposition.

        They take its place in the tree's order, each waiting afresh. A wait on
        `old_id` moves to the ones on its target — or, when none of them is on
        it, to every one of them — so nothing that waited is sent before the
        work that stands for its provider is done.
        """
        old = self._nodes[old_id]
        fresh = (contract, *more)
        ids = [c.id for c in fresh]
        if len(set(ids)) != len(ids):
            raise ValueError(f"a replacement for {old_id} is named twice: {ids}")
        for each in ids:
            if each in self._nodes and each != old_id:
                raise ValueError(f"{each} is already in this tree")
        on_target = tuple(c.id for c in fresh if c.target == old.contract.target)
        heirs = on_target or tuple(ids)
        rebuilt: dict[str, _Node] = {}
        for cid, node in self._nodes.items():
            if cid == old_id:
                rebuilt.update((c.id, _Node(c, batch=old.batch)) for c in fresh)
                continue
            if old_id in node.contract.depends_on:
                waits: list[str] = []
                for w in node.contract.depends_on:
                    waits.extend(heirs if w == old_id else (w,))
                node.contract = _with_depends_on(
                    node.contract, tuple(dict.fromkeys(waits))
                )
            rebuilt[cid] = node
        self._nodes = rebuilt
        self._build()
        self._evaluate()

    def seal(
        self, only: Collection[str] | None = None
    ) -> tuple[tuple[Contract, Hold], ...]:
        """The queue is drained: whatever is still held is dead, and comes back.

        A contract still waiting here waits on nothing that will run, so it is
        held first, then dead. With `only`, just those contracts are sealed:
        one batch's, on a tree other batches still run.
        """
        self.sealed = True
        self._evaluate()
        dead: list[tuple[Contract, Hold]] = []
        for cid, node in self._nodes.items():
            if only is not None and cid not in only:
                continue
            if node.state is State.WAITING:
                node.state = State.BLOCKED
                node.hold = node.hold or Hold(
                    Reason.PROVIDER_BLOCKED,
                    providers=self._providers_waited_on(node),
                    chain=tuple(e.provider for e in node.edges),
                )
            if node.state is State.BLOCKED and node.hold is not None:
                node.state = State.DEAD
                dead.append((node.contract, node.hold))
        return tuple(dead)

    def as_json(self) -> dict[str, Any]:
        """The tree as its state file holds it."""
        return {
            "tree": self.tree_id,
            "hold": self.hold,
            "sealed": self.sealed,
            "contracts": [
                {
                    "contract": cid,
                    "target": node.contract.target,
                    "state": node.state.value,
                    "waits_on": [e.provider for e in node.edges],
                    "outcome": node.outcome or None,
                    "detail": node.detail or None,
                    "result": node.result,
                    "blocked_by": node.hold.as_json() if node.hold else None,
                    **(
                        {"replaces": node.contract.replan.replaces}
                        if node.contract.replan.stated
                        else {}
                    ),
                    **({"batch": node.batch} if node.batch else {}),
                    **({"started": node.started} if node.started else {}),
                }
                for cid, node in self._nodes.items()
            ],
        }

    # -- inside -------------------------------------------------------------

    def _build(self) -> None:
        """Every node's edges, the order to read them in, and the cycles."""
        definitions = _Definitions(self.source)
        creates = {cid: _creates(node.contract) for cid, node in self._nodes.items()}
        for cid, node in self._nodes.items():
            waits = list(dict.fromkeys(node.contract.depends_on))
            unprovided: list[Need] = []
            for dep in node.contract.deps:
                for symbol in declared_names(dep.path, dep.signature):
                    if definitions.defines(dep.path, symbol) is not False:
                        continue
                    provider = next(
                        (
                            other
                            for other, made in creates.items()
                            if other != cid
                            and self._nodes[other].contract.target == dep.path
                            and symbol in made
                        ),
                        None,
                    )
                    if provider is None:
                        unprovided.append(Need(dep.path, symbol, creates=True))
                    elif provider not in waits:
                        waits.append(provider)
            node.edges = tuple(
                _edge(node.contract, self._nodes[w].contract, creates[w], definitions)
                if w in self._nodes
                else Edge(w)
                for w in waits
            )
            node.unprovided = tuple(unprovided)
        self._order, self._cycle = self._sort()

    def _sort(self) -> tuple[tuple[str, ...], frozenset[str]]:
        """Kahn's order over the edges among the tree's own contracts, the given
        order breaking ties; what cannot be placed is on or behind a cycle."""
        given = list(self._nodes)
        before = {
            cid: {
                e.provider for e in self._nodes[cid].edges if e.provider in self._nodes
            }
            for cid in given
        }
        order: list[str] = []
        placed: set[str] = set()
        progress = True
        while progress:
            progress = False
            for cid in given:
                if cid not in placed and before[cid] <= placed:
                    order.append(cid)
                    placed.add(cid)
                    progress = True
                    break
        cycle = frozenset(cid for cid in given if cid not in placed)
        return tuple(order) + tuple(c for c in given if c in cycle), cycle

    def _evaluate(self) -> None:
        """Every contract not started or settled: ready, waiting or held."""
        definitions = _Definitions(self.source)
        for cid in self._order:
            node = self._nodes[cid]
            if node.state in _SETTLED:
                continue
            node.hold = None
            if not self.hold:
                # Nothing is held: a contract runs once each provider has come
                # to anything, and one on a cycle runs as it would without the
                # tree, since no order exists to wait for.
                done = cid in self._cycle or all(
                    self._nodes[e.provider].state in _SETTLED - {State.RUNNING}
                    for e in node.edges
                    if e.provider in self._nodes
                )
                node.state = State.READY if done else State.WAITING
                continue
            if cid in self._cycle:
                node.state = State.BLOCKED
                node.hold = Hold(Reason.CYCLE, chain=tuple(sorted(self._cycle)))
                continue
            holds, waiting = self._holds(node, definitions)
            if holds:
                node.state = State.BLOCKED
                node.hold = _merged(holds)
            else:
                node.state = State.WAITING if waiting else State.READY

    def _holds(self, node: _Node, definitions: _Definitions) -> tuple[list[Hold], bool]:
        """What holds `node`, and whether it still waits on anything."""
        holds: list[Hold] = []
        waiting = False
        for edge in node.edges:
            provider = self._nodes.get(edge.provider)
            if provider is None:
                if self.sealed:
                    holds.append(
                        Hold(Reason.UNKNOWN_DEPENDENCY, chain=(edge.provider,))
                    )
                else:
                    waiting = True
                continue
            named = _provider(provider)
            if provider.state in (State.WAITING, State.READY, State.RUNNING):
                waiting = True
            elif provider.state is State.LANDED:
                missing = tuple(
                    n
                    for n in edge.needs
                    if n.creates and definitions.defines(n.path, n.symbol) is False
                )
                if missing:
                    holds.append(
                        Hold(Reason.PROVIDER_LANDED_WITHOUT, (named,), needs=missing)
                    )
            elif provider.state is State.FAILED:
                spared = (
                    not edge.needs
                    and edge.uses
                    and all(
                        definitions.defines(provider.contract.target, u) is True
                        for u in edge.uses
                    )
                )
                if not spared:
                    reason = (
                        Reason.PROVIDER_NOT_LANDED
                        if provider.outcome == ACCEPTED
                        else Reason.PROVIDER_FAILED
                    )
                    holds.append(Hold(reason, (named,), needs=edge.needs))
            else:
                above = provider.hold.chain if provider.hold else ()
                holds.append(
                    Hold(
                        Reason.PROVIDER_BLOCKED,
                        (named,),
                        chain=(edge.provider, *above),
                    )
                )
        missing = tuple(
            n for n in node.unprovided if definitions.defines(n.path, n.symbol) is False
        )
        if missing:
            holds.append(Hold(Reason.UNPROVIDED, needs=missing))
        return holds, waiting

    def _providers_waited_on(self, node: _Node) -> tuple[Provider, ...]:
        return tuple(
            _provider(self._nodes[e.provider])
            for e in node.edges
            if e.provider in self._nodes
        )


class _Definitions:
    """The names each file of the source defines, read once per evaluation.

    `defines` answers True or False only where it can tell: a file in a
    language the index cannot read answers None, and None never holds a
    contract.
    """

    def __init__(self, source: Source) -> None:
        self._source = source
        self._names: dict[str, frozenset[str] | None] = {}

    def read(self, path: str) -> bytes | None:
        return self._source.read(path)

    def defines(self, path: str, symbol: str) -> bool | None:
        if path not in self._names:
            self._names[path] = self._read(path)
        names = self._names[path]
        return None if names is None else symbol in names

    def _read(self, path: str) -> frozenset[str] | None:
        if language_of(path) is None:
            return None
        raw = self._source.read(path)
        if raw is None:
            return frozenset()
        return frozenset(
            s.name for s in extract(path, raw) if s.kind is SymbolKind.DEFINITION
        )


def _creates(contract: Contract) -> frozenset[str]:
    """The names `contract` is to create: its interface's, and a rename's new one."""
    made = set(declared_names(contract.target, contract.interface))
    made.update(new for _, new in renames(contract.task))
    if contract.rename.stated:
        made.add(contract.rename.new)
    return frozenset(made)


def _edge(
    dependent: Contract,
    provider: Contract,
    creates: frozenset[str],
    definitions: _Definitions,
) -> Edge:
    """What `dependent` waits for from `provider`."""
    target = provider.target
    changes = {old for old, _ in renames(provider.task)}
    if provider.rename.stated:
        changes.add(provider.rename.old)
    changes.update(
        name
        for name in identifiers(provider.task)
        if definitions.defines(target, name) is True
    )
    changes -= creates
    imported = _imported(dependent, target, definitions)
    wanted = imported | identifiers(
        dependent.task,
        dependent.interface,
        *(d.signature for d in dependent.deps if d.path == target),
    )
    needs = tuple(Need(target, s, creates=True) for s in sorted(creates & wanted))
    needs += tuple(Need(target, s, creates=False) for s in sorted(changes & wanted))
    uses = tuple(sorted(imported - creates - changes))
    return Edge(provider.id, needs, uses)


def _imported(
    dependent: Contract, target: str, definitions: _Definitions
) -> frozenset[str]:
    """The names `dependent`'s target imports from the file `target`.

    A whole-module import counts every name the dependent references that the
    file defines.
    """
    if dependent.target_content:
        raw: bytes | None = dependent.target_content.encode("utf-8", "surrogateescape")
    else:
        raw = definitions.read(dependent.target)
    if not raw:
        return frozenset()
    symbols = extract(dependent.target, raw)
    module = _module_parts(target)
    names: set[str] = set()
    whole = False
    for symbol in symbols:
        if symbol.kind is not SymbolKind.IMPORT:
            continue
        spec = symbol.detail or symbol.name
        joined = spec if symbol.name == spec else f"{spec}.{symbol.name}"
        if _names_module(joined, module):
            whole = True
        elif _names_module(spec, module):
            names.add(symbol.name)
    if whole:
        names.update(
            s.name
            for s in symbols
            if s.kind is SymbolKind.REFERENCE and definitions.defines(target, s.name)
        )
    return frozenset(names)


def _module_parts(path: str) -> tuple[str, ...]:
    """A file's path as the parts an import names it by."""
    stem = path.rsplit(".", 1)[0] if "." in path.rsplit("/", 1)[-1] else path
    parts = tuple(p for p in stem.split("/") if p)
    if parts and parts[-1] in ("__init__", "index", "mod"):
        parts = parts[:-1]
    return parts


def _names_module(spec: str, module: tuple[str, ...]) -> bool:
    """Whether an import's module `spec` names the file whose parts are `module`.

    A spec with a slash is a path (``./io/jsonio.js``), any other a dotted name
    (``stockroom.io.jsonio``, ``.jsonio``); either matches the file's trailing
    parts.
    """
    if "/" in spec:
        bare = spec.lstrip("./")
        last = bare.rsplit("/", 1)[-1]
        if "." in last:
            bare = bare.rsplit(".", 1)[0]
        parts = tuple(p for p in bare.split("/") if p and p != "..")
    else:
        parts = tuple(p for p in spec.lstrip(".").split(".") if p)
    return bool(parts) and len(parts) <= len(module) and module[-len(parts) :] == parts


def _provider(node: _Node) -> Provider:
    return Provider(
        contract=node.contract.id,
        target=node.contract.target,
        outcome=node.outcome or node.state.value,
        result=node.result,
        detail=node.detail,
    )


def _merged(holds: Sequence[Hold]) -> Hold:
    """Several holds as one: the first one's reason, every provider and need."""
    first = holds[0]
    providers = tuple(dict.fromkeys(p for h in holds for p in h.providers))
    needs = tuple(dict.fromkeys(n for h in holds for n in h.needs))
    return Hold(first.reason, providers, needs, first.chain)


def _with_depends_on(contract: Contract, waits: tuple[str, ...]) -> Contract:
    return replace(contract, depends_on=waits)
