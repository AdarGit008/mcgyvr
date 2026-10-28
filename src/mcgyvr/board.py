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

A live board (`Board.live`) holds the one live tree of a repository, shared
by every batch run on it — in this process or another — through its state
file. `trees/live/<repository>` names that tree while it lives. A batch
`join`s it: its contracts are added, each naming the batch, and their edges
are read against every contract there, in flight or landed. A batch is
handed only its own contracts as ready, `drain` seals only its own, and
`waiting` says whether one of them still waits on work another batch has in
flight, so the batch `wait`s rather than seal it. Every read and write of the
tree is taken under the repository's delivery lock
(`deliver.between_deliveries`, the per-git-dir lock of #381), the state file
read again when another batch wrote it since. Each contract's document is
kept beside it, in `trees/<tree>/<id>.json`, so any batch can read the tree
back whole. The tree retires (`retired`) when its last contract has come to
an end, and the next batch on the repository starts a fresh one.

While a batch runs it holds its lease: a `flock` on
`trees/leases/<batch>.lease`, which the kernel drops when the process dies
and the batch drops when it ends (`leave`). A reader that finds a contract
not yet ended under a lease nobody holds frees it: settled from the result
its run wrote, when one is there, else failed as `abandoned`.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import secrets
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from mcgyvr import atomic
from mcgyvr.contract import Contract, ContractError, dumps, loads
from mcgyvr.deliver import between_deliveries
from mcgyvr.exits import Exit
from mcgyvr.gitcmd import run_git
from mcgyvr.result import RunResult, run_stamp
from mcgyvr.tree import BLOCKED, Hold, Source, State, Tree

#: The directory under the journal that holds one state file per tree.
TREES_DIR = "trees"

#: Under `TREES_DIR`: one file per repository naming its live tree.
LIVE_DIR = "live"

#: Under `TREES_DIR`: one lease file per running batch.
LEASES_DIR = "leases"

#: How long a batch waiting on another process's work waits between looks;
#: a change made in this process wakes it at once.
POLL_S = 1.0

#: What a stale contract's run came to, read from what it left (its result),
#: as `Board.settle` takes it; None when it left nothing. Handed the contract
#: id and the stamp it was started at.
Found = Callable[[str, str], dict[str, Any] | None]

#: The states a contract is still in flight in.
_IN_FLIGHT = frozenset({State.WAITING, State.READY, State.RUNNING})

#: The states a contract has not come to an end in.
_OPEN = _IN_FLIGHT | {State.BLOCKED}


class _Writes:
    """The writes the live boards of this process have made, counted, so a
    batch waiting in this process wakes at the next one."""

    def __init__(self) -> None:
        self.count = 0
        self.changed = threading.Condition()

    def wrote(self) -> None:
        with self.changed:
            self.count += 1
            self.changed.notify_all()


_WRITES = _Writes()


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


class _Live:
    """What a live board keeps: its repository, its batch, its lease, and the
    version of the state file it last read or wrote."""

    def __init__(self, repo: Path, found: Found | None) -> None:
        self.repo = repo
        self.found = found
        self.batch = "batch-" + secrets.token_hex(6)
        self.lease: int | None = None
        self.source: Source | None = None
        self.tree_id = ""
        self.version = 0
        self.depth = 0
        #: Each contract's document as last written or read.
        self.documents: dict[str, str] = {}
        #: The ids a join left to the batch that has them in flight.
        self.left: tuple[str, ...] = ()


class Board:
    """The trees the queue consults, each kept in a state file under `journal`.

    With no `journal`, nothing is written. `live` makes the board of one
    repository's live tree, shared by every batch on it.
    """

    def __init__(self, journal: Path | None = None) -> None:
        self.journal = journal
        self._trees: dict[str, Tree] = {}
        self._live: _Live | None = None

    @classmethod
    def live(cls, journal: Path, repo: Path, *, found: Found | None = None) -> Board:
        """The board of `repo`'s live tree, kept under `journal`, for one batch.

        `found` reads what a stale contract's run came to (`Found`).
        """
        board = cls(journal)
        board._live = _Live(repo, found)
        return board

    @property
    def batch(self) -> str:
        """The batch a live board runs for; empty on any other board."""
        return self._live.batch if self._live else ""

    @property
    def left(self) -> tuple[str, ...]:
        """The contracts `join` left to another batch, which has them in flight."""
        return self._live.left if self._live else ()

    @property
    def trees(self) -> tuple[Tree, ...]:
        return tuple(self._trees.values())

    def tree(self, tree_id: str) -> Tree:
        with self._shared():
            return self._trees[tree_id]

    def attach(self, tree: Tree) -> None:
        if tree.tree_id in self._trees:
            raise ValueError(f"{tree.tree_id} is already on this board")
        self._trees[tree.tree_id] = tree
        self._persist(tree)

    def join(
        self, contracts: Iterable[Contract], source: Source, *, hold: bool = True
    ) -> str:
        """Put this batch's `contracts` on the repository's live tree; its id.

        The batch's lease is taken first. The live tree, when there is one, is
        read back, what a gone batch left in flight is freed, and the
        contracts join it (`Tree.join`); when none lives, or freeing ended its
        last contract, a fresh tree is made of them and named live. `hold` is
        the fresh tree's; a joined tree keeps its own.
        """
        live = self._need_live()
        wanted = tuple(contracts)
        self._lease()
        live.source = source
        with self._locked():
            tree = self._live_tree(source)
            if tree is None:
                tree = Tree.of(
                    wanted,
                    source,
                    tree_id=tree_id_for(
                        str(live.repo), _commit(source), (c.id for c in wanted)
                    ),
                    hold=hold,
                    batch=live.batch,
                )
                live.version = self._version_of(tree.tree_id)
                live.documents = {}
                live.left = ()
            else:
                live.left = tree.join(wanted, batch=live.batch)
            live.tree_id = tree.tree_id
            self._trees = {tree.tree_id: tree}
            self._persist(tree)
            return tree.tree_id

    def ready(self) -> tuple[tuple[Tree, Contract], ...]:
        """Every contract that may run now, one from each tree in turn.

        On a live board, only this batch's, and none whose scope meets that of
        a contract another batch is running.
        """
        with self._shared():
            queues = [
                [(t, c) for c in t.ready() if self._runs(t, c)]
                for t in self._trees.values()
            ]
        taken: list[tuple[Tree, Contract]] = []
        while any(queues):
            for queue in queues:
                if queue:
                    taken.append(queue.pop(0))
        return tuple(taken)

    def start(self, tree_id: str, contract_id: str) -> None:
        with self._shared():
            tree = self._trees[tree_id]
            tree.start(contract_id, started=run_stamp() if self._live else "")
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
        with self._shared():
            tree = self._trees[tree_id]
            tree.settle(
                contract_id,
                outcome=outcome,
                landed=landed,
                detail=detail,
                result=result,
            )
            self._persist(tree)

    def replace(
        self, tree_id: str, old_id: str, contract: Contract, *more: Contract
    ) -> None:
        """`contract`, and `more`, take `old_id`'s place on its tree."""
        with self._shared():
            tree = self._trees[tree_id]
            tree.replace(old_id, contract, *more)
            self._persist(tree)

    def drain(self) -> tuple[tuple[Tree, Contract, Hold], ...]:
        """Seal every tree, and hand back each contract that is still held.

        On a live board only this batch's contracts are sealed.
        """
        dead: list[tuple[Tree, Contract, Hold]] = []
        with self._shared():
            for tree in self._trees.values():
                only = self._own(tree) if self._live else None
                dead.extend(
                    (tree, contract, hold) for contract, hold in tree.seal(only)
                )
                self._persist(tree)
        return tuple(dead)

    def waiting(self) -> bool:
        """Whether one of this batch's contracts still waits on work in flight.

        A contract of this batch not yet ended waits when it is ready but was
        not handed out (its scope meets a running one's), or when what it
        waits on, through contracts not yet ended, comes to a contract
        another batch has in flight. A contract held by one that has ended
        waits on nothing. Always False on a board that is not live.
        """
        if self._live is None:
            return False
        with self._shared():
            return any(self._waits(tree) for tree in self._trees.values())

    def generation(self) -> int:
        """How many writes the live boards of this process have made: what
        `wait` is handed, read before asking `ready` and `waiting`."""
        with _WRITES.changed:
            return _WRITES.count

    def wait(self, seen: int, timeout: float = POLL_S) -> None:
        """Wait until a live board in this process writes after `seen`, or for
        `timeout` seconds, the most another process's write goes unseen."""
        with _WRITES.changed:
            if _WRITES.count == seen:
                _WRITES.changed.wait(timeout)

    def leave(self) -> None:
        """This batch has ended: its lease is dropped, so what it left in
        flight is freed by the next reader."""
        live = self._live
        if live is None or live.lease is None:
            return
        with contextlib.suppress(OSError):
            self._lease_file(live.batch).unlink()
        os.close(live.lease)  # closing the descriptor releases the lease
        live.lease = None

    def state_file(self, tree_id: str) -> Path | None:
        if self.journal is None:
            return None
        return self.journal / TREES_DIR / f"{tree_id}.json"

    def _persist(self, tree: Tree) -> None:
        path = self.state_file(tree.tree_id)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = tree.as_json()
        live = self._live
        if live is not None:
            self._write_documents(tree, doc)
            live.version += 1
            doc.update(
                repo=str(live.repo), version=live.version, retired=tree.finished()
            )
        atomic.write(path, json.dumps(doc, indent=2, sort_keys=True) + "\n")
        if live is not None:
            self._name_live(tree, retired=doc["retired"])
            _WRITES.wrote()

    # -- a live board ----------------------------------------------------------

    def _need_live(self) -> _Live:
        if self._live is None or self.journal is None:
            raise ValueError("only a live board (Board.live) joins a repository's tree")
        return self._live

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        """Hold the repository's delivery lock for the block, once per board."""
        live = self._need_live()
        if live.depth:
            live.depth += 1
            try:
                yield
            finally:
                live.depth -= 1
            return
        with between_deliveries(live.repo):
            live.depth += 1
            try:
                yield
            finally:
                live.depth -= 1

    @contextlib.contextmanager
    def _shared(self) -> Iterator[None]:
        """On a live board joined to its tree: the lock held, the tree read
        again when another batch wrote it, and what a gone batch left in
        flight freed. On any other board, nothing."""
        live = self._live
        if live is None or not live.tree_id:
            yield
            return
        with self._locked():
            if live.depth == 1:
                self._sync()
            yield

    def _sync(self) -> None:
        live = self._need_live()
        doc = self._read(live.tree_id)
        if doc is not None and doc.get("version") != live.version:
            assert live.source is not None
            _refresh(live.source)
            tree = self._restore(doc, live.source)
            live.version = int(doc.get("version") or 0)
            self._trees = {tree.tree_id: tree}
        tree = self._trees[live.tree_id]
        if self._free(tree):
            self._persist(tree)

    def _live_tree(self, source: Source) -> Tree | None:
        """The repository's live tree, read back with what a gone batch left
        in flight freed; None when none lives, or freeing ended it."""
        live = self._need_live()
        pointer = self._pointer()
        try:
            tree_id = pointer.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        doc = self._read(tree_id) if tree_id else None
        if doc is None or doc.get("retired"):
            return None
        try:
            tree = self._restore(doc, source)
        except (OSError, ValueError, KeyError, ContractError):
            # A tree that cannot be read back is not joined: the batch starts
            # its own, and the pointer names that one from now on.
            return None
        live.version = int(doc.get("version") or 0)
        if self._free(tree):
            self._persist(tree)
        return None if tree.finished() else tree

    def _restore(self, doc: Mapping[str, Any], source: Source) -> Tree:
        live = self._need_live()
        tree_id = str(doc["tree"])
        documents: dict[str, str] = {}
        contracts: dict[str, Contract] = {}
        for row in doc["contracts"]:
            cid = str(row["contract"])
            text = self._document(tree_id, cid).read_text(encoding="utf-8")
            documents[cid] = text
            contracts[cid] = loads(text)
        live.documents = documents
        return Tree.restore(doc, contracts, source)

    def _read(self, tree_id: str) -> dict[str, Any] | None:
        path = self.state_file(tree_id)
        if path is None:
            return None
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return doc if isinstance(doc, dict) else None

    def _version_of(self, tree_id: str) -> int:
        """The version a state file already at this name has, so a fresh tree
        written over a retired one of the same name is never taken for it."""
        doc = self._read(tree_id)
        return int(doc.get("version") or 0) if doc else 0

    def _free(self, tree: Tree) -> bool:
        """Free what a batch whose lease nobody holds left not yet ended."""
        live = self._need_live()
        held: dict[str, bool] = {}
        freed = False
        for contract in tree.contracts():
            cid = contract.id
            batch = tree.batch(cid)
            if not batch or batch == live.batch or tree.state(cid) not in _OPEN:
                continue
            if batch not in held:
                held[batch] = self._leased(batch)
            if held[batch]:
                continue
            came = None
            if tree.state(cid) is State.RUNNING and live.found is not None:
                came = live.found(cid, tree.started(cid))
            if came is not None:
                tree.settle(cid, **came)
            else:
                tree.abandon(cid, f"its batch ({batch}) ended without settling it")
            freed = True
        return freed

    def _leased(self, batch: str) -> bool:
        """Whether `batch` still holds its lease. A lease file that is gone,
        or whose lock is free, is a batch that has ended; one that cannot be
        told is taken as held, so nothing is freed on a guess."""
        path = self._lease_file(batch)
        try:
            fd = os.open(path, os.O_RDWR)
        except FileNotFoundError:
            return False
        except OSError:
            return True
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        else:
            with contextlib.suppress(OSError):
                path.unlink()
            return False
        finally:
            os.close(fd)

    def _lease(self) -> None:
        live = self._need_live()
        if live.lease is not None:
            return
        path = self._lease_file(live.batch)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise
        live.lease = fd

    def _lease_file(self, batch: str) -> Path:
        assert self.journal is not None
        return self.journal / TREES_DIR / LEASES_DIR / f"{batch}.lease"

    def _pointer(self) -> Path:
        live = self._need_live()
        assert self.journal is not None
        key = hashlib.blake2b(
            str(live.repo.resolve()).encode("utf-8"), digest_size=8
        ).hexdigest()
        return self.journal / TREES_DIR / LIVE_DIR / key

    def _name_live(self, tree: Tree, *, retired: bool) -> None:
        """Name `tree` the repository's live tree, or, once retired, no more."""
        pointer = self._pointer()
        try:
            named = pointer.read_text(encoding="utf-8").strip()
        except OSError:
            named = ""
        if retired:
            if named == tree.tree_id:
                pointer.unlink()
            return
        if named != tree.tree_id:
            pointer.parent.mkdir(parents=True, exist_ok=True)
            atomic.write(pointer, tree.tree_id + "\n")

    def _document(self, tree_id: str, contract_id: str) -> Path:
        assert self.journal is not None
        return self.journal / TREES_DIR / tree_id / f"{contract_id}.json"

    def _write_documents(self, tree: Tree, doc: dict[str, Any]) -> None:
        """Write each contract's document that changed, and name it in `doc`."""
        live = self._need_live()
        for contract, row in zip(tree.contracts(), doc["contracts"], strict=True):
            path = self._document(tree.tree_id, contract.id)
            text = dumps(contract) + "\n"
            if live.documents.get(contract.id) != text:
                path.parent.mkdir(parents=True, exist_ok=True)
                atomic.write(path, text)
                live.documents[contract.id] = text
            row["document"] = str(path)

    def _own(self, tree: Tree) -> frozenset[str]:
        mine = self.batch
        return frozenset(c.id for c in tree.contracts() if tree.batch(c.id) == mine)

    def _runs(self, tree: Tree, contract: Contract) -> bool:
        """Whether this board hands `contract` out: any contract, unless the
        board is live, where only its batch's and none beside another batch's
        run on a file both could write."""
        if self._live is None:
            return True
        if tree.batch(contract.id) != self.batch:
            return False
        return not any(
            tree.state(other.id) is State.RUNNING
            and tree.batch(other.id) != self.batch
            and contract.scope.meets(other.scope)
            for other in tree.contracts()
        )

    def _waits(self, tree: Tree) -> bool:
        mine = self.batch
        there = frozenset(c.id for c in tree.contracts())
        seen: set[str] = set()
        todo = [cid for cid in self._own(tree) if tree.state(cid) in _OPEN]
        while todo:
            cid = todo.pop()
            if cid in seen:
                continue
            seen.add(cid)
            state = tree.state(cid)
            if tree.batch(cid) == mine:
                if state in (State.READY, State.RUNNING):
                    return True
            elif state in _IN_FLIGHT:
                return True
            if state in _OPEN:
                todo.extend(e.provider for e in tree.edges(cid) if e.provider in there)
        return False


def _commit(source: Source) -> str:
    return str(getattr(source, "commit", ""))


def _refresh(source: Source) -> None:
    refresh = getattr(source, "refresh", None)
    if callable(refresh):
        refresh()


def held_result(
    contract: Contract,
    hold: Hold,
    *,
    session: str,
    run: str,
    journal: str | None = None,
    session_file: str | None = None,
) -> RunResult:
    """The result of a contract the tree held: outcome `blocked`, no attempt."""
    return RunResult(
        contract=contract.id,
        task_type=contract.task_type,
        target=contract.target,
        session=session,
        run=run,
        session_file=session_file,
        journal=journal,
        outcome=BLOCKED,
        detail=hold.sentence(),
        exit_code=int(Exit.REFUSED),
        blocked_by=hold.as_json(),
    )
