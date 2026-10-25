"""The queue's side of the dependency tree: several trees, one state file each.

A `Board` holds the dependency tree (`mcgyvr.tree.Tree`) of every repository
or job it was given — one tree per repository, never an edge between two —
and answers which contract may run next, taking each tree in turn. Every
change to a tree is written to ``<journal>/trees/<tree>.json`` through
`mcgyvr.atomic`, so the tree can be read live from outside the process.
`drain` seals every tree once nothing more will run, and hands back the
contracts still held: each gets a result with outcome `blocked`
(`held_result`) and spends no rung.

`GitSource` is the tree a contract's sandbox starts from: the committed tree
at a revision of a repository, read through git.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.contract import Contract
from mcgyvr.exits import Exit
from mcgyvr.gitcmd import run_git
from mcgyvr.result import RunResult
from mcgyvr.tree import BLOCKED, Hold, Tree

#: The directory under the journal that holds one state file per tree.
TREES_DIR = "trees"


class _GitReadError(Exception):
    """A git read that found nothing there."""


class GitSource:
    """The committed tree at `rev` of the repository at `root`.

    The revision is resolved once and again on `refresh`, so a commit that
    lands moves what is read only when the caller says so.
    """

    def __init__(self, root: Path, rev: str = "HEAD") -> None:
        self.root = root
        self.rev = rev
        self.commit = self._resolve()
        self._files: dict[str, bytes | None] = {}

    def refresh(self) -> None:
        """Read the revision again; the files are read again when it moved."""
        commit = self._resolve()
        if commit != self.commit:
            self.commit = commit
            self._files.clear()

    def read(self, path: str) -> bytes | None:
        if path not in self._files:
            try:
                self._files[path] = self._git("show", f"{self.commit}:{path}")
            except _GitReadError:
                self._files[path] = None
        return self._files[path]

    def holds(self, commit: str) -> bool:
        """Whether `commit` is in the tree read: an ancestor of the revision."""
        if not commit:
            return False
        try:
            self._git("merge-base", "--is-ancestor", commit, self.commit)
        except _GitReadError:
            return False
        return True

    def _resolve(self) -> str:
        try:
            return (
                self._git("rev-parse", "--verify", f"{self.rev}^{{commit}}")
                .decode("ascii")
                .strip()
            )
        except _GitReadError:
            return ""

    def _git(self, *args: str) -> bytes:
        return run_git(self.root, *args, error=_GitReadError)


def tree_id_for(repo: str, base: str, contract_ids: Iterable[str]) -> str:
    """A tree's name: a digest of the repository, its base and its contracts."""
    material = json.dumps([repo, base, sorted(contract_ids)]).encode("utf-8")
    return "tree-" + hashlib.blake2b(material, digest_size=5).hexdigest()


class Board:
    """The trees the queue consults, each kept in a state file under `journal`.

    With no `journal`, nothing is written.
    """

    def __init__(self, journal: Path | None = None) -> None:
        self.journal = journal
        self._trees: dict[str, Tree] = {}

    @property
    def trees(self) -> tuple[Tree, ...]:
        return tuple(self._trees.values())

    def tree(self, tree_id: str) -> Tree:
        return self._trees[tree_id]

    def attach(self, tree: Tree) -> None:
        if tree.tree_id in self._trees:
            raise ValueError(f"{tree.tree_id} is already on this board")
        self._trees[tree.tree_id] = tree
        self._persist(tree)

    def ready(self) -> tuple[tuple[Tree, Contract], ...]:
        """Every contract that may run now, one from each tree in turn."""
        queues = [[(t, c) for c in t.ready()] for t in self._trees.values()]
        taken: list[tuple[Tree, Contract]] = []
        while any(queues):
            for queue in queues:
                if queue:
                    taken.append(queue.pop(0))
        return tuple(taken)

    def start(self, tree_id: str, contract_id: str) -> None:
        tree = self._trees[tree_id]
        tree.start(contract_id)
        self._persist(tree)

    def settle(
        self,
        tree_id: str,
        contract_id: str,
        *,
        outcome: str,
        landed: bool,
        detail: str = "",
        result: str | None = None,
    ) -> None:
        tree = self._trees[tree_id]
        tree.settle(
            contract_id, outcome=outcome, landed=landed, detail=detail, result=result
        )
        self._persist(tree)

    def drain(self) -> tuple[tuple[Tree, Contract, Hold], ...]:
        """Seal every tree, and hand back each contract that is still held."""
        dead: list[tuple[Tree, Contract, Hold]] = []
        for tree in self._trees.values():
            dead.extend((tree, contract, hold) for contract, hold in tree.seal())
            self._persist(tree)
        return tuple(dead)

    def state_file(self, tree_id: str) -> Path | None:
        if self.journal is None:
            return None
        return self.journal / TREES_DIR / f"{tree_id}.json"

    def _persist(self, tree: Tree) -> None:
        path = self.state_file(tree.tree_id)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic.write(path, json.dumps(tree.as_json(), indent=2, sort_keys=True) + "\n")


def held_result(
    contract: Contract,
    hold: Hold,
    *,
    orchestrator: str,
    run: str,
    journal: str | None = None,
    session_file: str | None = None,
) -> RunResult:
    """The result of a contract the tree held: outcome `blocked`, no attempt."""
    return RunResult(
        contract=contract.id,
        task_type=contract.task_type,
        target=contract.target,
        orchestrator=orchestrator,
        run=run,
        session_file=session_file,
        journal=journal,
        outcome=BLOCKED,
        detail=hold.sentence(),
        exit_code=int(Exit.REFUSED),
        blocked_by=hold.as_json(),
    )
