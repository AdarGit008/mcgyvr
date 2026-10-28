"""A repository has one live tree, and every batch on it joins that tree.

A batch started while another still has contracts in flight on the same
repository joins the live tree under the journal: its contracts are added, its
edges are inferred against every contract there, and a dependent of the other
batch's provider waits for that provider to settle. The tree retires when its
last contract settles, and a later batch starts a fresh one. Every read and
write of the tree is taken under the per-git-dir delivery lock (#381), and a
contract left in flight by a batch that is gone (its lease is free) is freed
by the next reader, from the result its run wrote or as `abandoned`.

The runs are stood in for as in the `--jobs` tests, each change delivered
through the real `deliver`; two batches run on two threads of this process,
which contend for the lock as two processes do. Which run ends when is driven
by events, never by sleeping.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr.cli.commands import delegate as command
from mcgyvr.config import Config
from mcgyvr.contract import Contract, Dependency, dumps
from mcgyvr.orchestrator.decompose import Decomposition
from mcgyvr.scope import Scope
from mcgyvr.session import Session
from tests.decomposes import git
from tests.test_delegate_run_jobs_runs_ready_contracts_at_once import (
    WAIT,
    Plan,
    Policy,
    Runs,
    results,
    waits_for,
)

FILES = ("a", "b", "c", "d")


def code(
    cid: str,
    target: str,
    *,
    needs: tuple[tuple[str, str], ...] = (),
    depends_on: tuple[str, ...] = (),
) -> Contract:
    """A contract that adds `def <cid>()` to `target`, and says it will.

    `needs` are the (path, name) of functions it calls that another contract
    is to create: the tree infers its wait on that contract from them.
    """
    name = cid.replace("-", "_")
    return Contract(
        id=cid,
        task_type="code",
        task=f"Add a function named {name} to {target}.",
        target=target,
        scope=Scope.of([target], []),
        interface=f"def {name}()",
        deps=tuple(
            Dependency(path=path, signature=f"def {symbol}()", note="")
            for path, symbol in needs
        ),
        depends_on=depends_on,
        stop_conditions=(
            f"code on {target} would require deciding something the contract "
            f"does not state - report BLOCKED rather than guess",
        ),
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    for name in FILES:
        (root / "pkg" / f"{name}.py").write_text(f"def {name}():\n    return 0\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return root


@pytest.fixture
def journal(tmp_path: Path) -> Path:
    return tmp_path / "journal"


@pytest.fixture
def runs(repo: Path, journal: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Runs]:
    """One stand-in for `_run` that every batch in the test shares."""
    stand_in = Runs(repo, journal, {}, {})
    monkeypatch.setattr(command, "_run", stand_in)
    monkeypatch.setattr(command, "_fleet_width", lambda _config: 8)
    yield stand_in


def run_batch(
    repo: Path,
    journal: Path,
    runs: Runs,
    contracts: tuple[Contract, ...],
    plans: dict[str, Plan] | None = None,
    *,
    jobs: int = 1,
    book: Any = None,
) -> int:
    """`delegate --run` on `contracts`, as `_delegate_logged` hands them over."""
    for contract in contracts:
        runs.contracts[contract.id] = contract
    runs.plans.update(plans or {})
    dec = Decomposition(
        contracts=contracts, documents=tuple(dumps(c) for c in contracts)
    )
    args = argparse.Namespace(
        config=None,
        sandbox=None,
        commit=True,
        branch=None,
        record=None,
        session_id="test-session",
        session=Session("test-session"),
        jobs=jobs,
    )
    policy = Policy({"journal.dir": str(journal), "dependents": "hold"})
    return command._run_delegated(args, repo, dec, [], cast(Config, policy), book=book)


class Batch(threading.Thread):
    """A batch on its own thread: what it returned, or what it raised."""

    def __init__(self, go: Callable[[], int]) -> None:
        super().__init__(daemon=True)
        self.go = go
        self.code: int | None = None
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self.code = self.go()
        except BaseException as exc:  # handed to the test, raised there
            self.error = exc

    def ended(self) -> int:
        self.join(WAIT)
        assert not self.is_alive(), "the batch never ended"
        if self.error is not None:
            raise self.error
        assert self.code is not None
        return self.code


def starts_then_waits(
    started: threading.Event, may_end: threading.Event
) -> Callable[[], None]:
    """A step that says it started, then waits for `may_end`."""

    def step() -> None:
        started.set()
        waits_for(may_end)()

    return step


def tree_files(journal: Path) -> list[Path]:
    return sorted((journal / "trees").glob("tree-*.json"))


def state(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text()))


def rows(path: Path) -> dict[str, dict[str, Any]]:
    return {r["contract"]: r for r in state(path)["contracts"]}


def settled_event(monkeypatch: pytest.MonkeyPatch, contract_id: str) -> threading.Event:
    """An event set once the Board has settled `contract_id`."""
    from mcgyvr.board import Board

    settle = Board.settle
    done = threading.Event()

    def settling(self: Board, tree_id: str, cid: str, **kw: Any) -> None:
        settle(self, tree_id, cid, **kw)
        if cid == contract_id:
            done.set()

    monkeypatch.setattr(Board, "settle", settling)
    return done


def joined_event(monkeypatch: pytest.MonkeyPatch, joins: int) -> threading.Event:
    """An event set once `joins` batches have joined the Board."""
    from mcgyvr.board import Board

    join = Board.join
    done = threading.Event()
    count: list[str] = []

    def joining(self: Board, *args: Any, **kwargs: Any) -> str:
        tree_id = join(self, *args, **kwargs)
        count.append(tree_id)
        if len(count) >= joins:
            done.set()
        return tree_id

    monkeypatch.setattr(Board, "join", joining)
    return done


def test_a_later_batch_joins_the_live_tree_and_its_dependent_waits_for_the_provider(
    repo: Path, journal: Path, runs: Runs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batch 1 runs `code-p`, which creates `code_p` in pkg/a.py. Batch 2,
    started while it runs, holds `code-d`, which calls `code_p`, and `code-s`,
    which needs nothing: `code-s` runs at once, `code-d` waits until batch 1
    has settled `code-p`, then starts from the commit `code-p` landed."""
    p_started = threading.Event()
    p_may_end = threading.Event()
    seen_by_s: dict[str, dict[str, Any]] = {}

    def s_reads_the_tree() -> None:
        (path,) = tree_files(journal)
        seen_by_s.update(rows(path))

    s_settled = settled_event(monkeypatch, "code-s")
    first = Batch(
        lambda: run_batch(
            repo,
            journal,
            runs,
            (code("code-p", "pkg/a.py"),),
            {"code-p": Plan(before=starts_then_waits(p_started, p_may_end))},
        )
    )
    first.start()
    assert p_started.wait(WAIT)

    second = Batch(
        lambda: run_batch(
            repo,
            journal,
            runs,
            (
                code("code-d", "pkg/c.py", needs=(("pkg/a.py", "code_p"),)),
                code("code-s", "pkg/b.py"),
            ),
            {"code-s": Plan(before=s_reads_the_tree)},
        )
    )
    second.start()
    assert s_settled.wait(WAIT)
    # Batch 2 joined the tree batch 1 made, while `code-p` was in flight.
    assert seen_by_s["code-p"]["state"] == "running"
    assert seen_by_s["code-d"]["state"] == "waiting"
    assert seen_by_s["code-d"]["waits_on"] == ["code-p"]
    assert seen_by_s["code-p"]["batch"] != seen_by_s["code-d"]["batch"]
    assert "start code-d" not in runs.log
    p_may_end.set()

    assert first.ended() == 0
    assert second.ended() == 0
    assert runs.log.index("end code-p") < runs.log.index("start code-d")
    (provider,) = results(journal, "code-p")
    git(repo, "merge-base", "--is-ancestor", provider["commit"], runs.bases["code-d"])
    (path,) = tree_files(journal)
    assert {r["state"] for r in rows(path).values()} == {"landed"}


def test_the_tree_retires_after_its_last_settle_and_a_later_batch_starts_afresh(
    repo: Path, journal: Path, runs: Runs
) -> None:
    assert run_batch(repo, journal, runs, (code("code-a", "pkg/a.py"),)) == 0
    (first,) = tree_files(journal)
    assert state(first)["retired"] is True
    assert list((journal / "trees" / "live").iterdir()) == []

    assert run_batch(repo, journal, runs, (code("code-b", "pkg/b.py"),)) == 0
    (later,) = [p for p in tree_files(journal) if p != first]
    assert set(rows(later)) == {"code-b"}
    assert set(rows(first)) == {"code-a"}
    assert state(later)["retired"] is True


def test_a_batch_that_ends_with_its_contracts_in_flight_leaves_them_to_be_freed(
    repo: Path, journal: Path, runs: Runs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batch 1 is interrupted after `code-p` wrote its result and landed, but
    before the Board settled it, and `code-q` never started. The next batch
    frees both, `code-p` from its result (landed) and `code-q` as abandoned;
    that was the tree's last contract, so it retires and the batch starts a
    fresh one."""
    from mcgyvr.board import Board

    settle = Board.settle

    def interrupted(self: Board, tree_id: str, cid: str, **kw: Any) -> None:
        if cid == "code-p":
            raise KeyboardInterrupt
        settle(self, tree_id, cid, **kw)

    monkeypatch.setattr(Board, "settle", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_batch(
            repo,
            journal,
            runs,
            (code("code-p", "pkg/a.py"), code("code-q", "pkg/b.py")),
        )
    monkeypatch.setattr(Board, "settle", settle)
    (first,) = tree_files(journal)
    before = rows(first)
    assert before["code-p"]["state"] == "running"
    assert before["code-q"]["state"] == "ready"

    exit_code = run_batch(
        repo,
        journal,
        runs,
        (code("code-d", "pkg/c.py", needs=(("pkg/a.py", "code_p"),)),),
    )

    assert exit_code == 0
    after = rows(first)
    assert after["code-p"]["state"] == "landed"
    assert after["code-q"]["state"] == "failed"
    assert after["code-q"]["outcome"] == "abandoned"
    assert state(first)["retired"] is True
    (later,) = [p for p in tree_files(journal) if p != first]
    assert rows(later)["code-d"]["state"] == "landed"
    assert runs.log.count("start code-p") == 1
    assert "start code-q" not in runs.log


def test_a_dependent_in_a_later_batch_is_held_when_the_provider_fails(
    repo: Path, journal: Path, runs: Runs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hold means across batches what it means in one: batch 1's `code-p`
    comes to `ladder_spent`, so batch 2's `code-d`, which calls `code_p`, is
    held `blocked`, naming `code-p`, and never started."""
    p_started = threading.Event()
    p_may_end = threading.Event()
    joined = joined_event(monkeypatch, 2)
    first = Batch(
        lambda: run_batch(
            repo,
            journal,
            runs,
            (code("code-p", "pkg/a.py"),),
            {
                "code-p": Plan(
                    outcome="ladder_spent",
                    before=starts_then_waits(p_started, p_may_end),
                )
            },
        )
    )
    first.start()
    assert p_started.wait(WAIT)
    second = Batch(
        lambda: run_batch(
            repo,
            journal,
            runs,
            (code("code-d", "pkg/c.py", needs=(("pkg/a.py", "code_p"),)),),
        )
    )
    second.start()
    assert joined.wait(WAIT)
    p_may_end.set()

    assert first.ended() == 1
    assert second.ended() == 3
    (held,) = results(journal, "code-d")
    assert held["outcome"] == "blocked"
    assert held["blocked_by"]["reason"] == "provider_failed"
    assert held["blocked_by"]["providers"][0]["contract"] == "code-p"
    assert "start code-d" not in runs.log
    (path,) = tree_files(journal)
    assert rows(path)["code-d"]["state"] == "dead"
    assert state(path)["retired"] is True


CRASH = """
import os, sys
from pathlib import Path
from mcgyvr.board import Board, GitSource
from mcgyvr.contract import loads
journal, repo, document = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
board = Board.live(journal, repo)
tree_id = board.join([loads(document)], GitSource(repo))
board.start(tree_id, loads(document).id)
os._exit(9)
"""


def test_a_contract_left_running_by_a_process_that_died_is_freed(
    repo: Path, journal: Path, runs: Runs
) -> None:
    """The process is killed with its contract in flight: the kernel frees
    its lease, and the next batch frees the contract as abandoned."""
    crashed = code("code-p", "pkg/a.py")
    died = subprocess.run(
        [sys.executable, "-c", CRASH, str(journal), str(repo), dumps(crashed)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert died.returncode == 9, died.stderr
    (path,) = tree_files(journal)
    assert rows(path)["code-p"]["state"] == "running"

    exit_code = run_batch(
        repo,
        journal,
        runs,
        (code("code-d", "pkg/c.py", needs=(("pkg/a.py", "code_p"),)),),
    )

    assert exit_code == 3
    assert rows(path)["code-p"]["outcome"] == "abandoned"
    assert state(path)["retired"] is True
    # `code_p` never came, and nothing left in flight creates it.
    (held,) = results(journal, "code-d")
    assert held["blocked_by"]["reason"] == "unprovided"
    assert "start code-d" not in runs.log


def test_a_contract_in_flight_under_a_live_lease_is_never_freed(
    repo: Path, journal: Path, runs: Runs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While batch 1 runs `code-p`, a reader in batch 2 leaves it running."""
    p_started = threading.Event()
    p_may_end = threading.Event()
    seen: list[str] = []

    def reader() -> None:
        (path,) = tree_files(journal)
        seen.append(rows(path)["code-p"]["state"])

    s_settled = settled_event(monkeypatch, "code-s")
    first = Batch(
        lambda: run_batch(
            repo,
            journal,
            runs,
            (code("code-p", "pkg/a.py"),),
            {"code-p": Plan(before=starts_then_waits(p_started, p_may_end))},
        )
    )
    first.start()
    assert p_started.wait(WAIT)
    assert (
        run_batch(
            repo,
            journal,
            runs,
            (code("code-s", "pkg/b.py"),),
            {"code-s": Plan(before=reader)},
        )
        == 0
    )
    assert s_settled.is_set()
    p_may_end.set()
    assert first.ended() == 0
    assert seen == ["running"]
    (path,) = tree_files(journal)
    assert rows(path)["code-p"]["state"] == "landed"
    assert state(path)["retired"] is True


def test_a_contract_already_in_flight_in_another_batch_is_not_run_twice(
    repo: Path, journal: Path, runs: Runs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Batch 2 proposes `code-p` again, the same unit of work: it waits on
    batch 1's run of it rather than run it a second time."""
    joined = joined_event(monkeypatch, 2)
    p_started = threading.Event()
    p_may_end = threading.Event()
    first = Batch(
        lambda: run_batch(
            repo,
            journal,
            runs,
            (code("code-p", "pkg/a.py"),),
            {"code-p": Plan(before=starts_then_waits(p_started, p_may_end))},
        )
    )
    first.start()
    assert p_started.wait(WAIT)
    second = Batch(
        lambda: run_batch(
            repo,
            journal,
            runs,
            (
                code("code-p", "pkg/a.py"),
                code("code-d", "pkg/c.py", depends_on=("code-p",)),
            ),
        )
    )
    second.start()
    assert joined.wait(WAIT)
    p_may_end.set()

    assert first.ended() == 0
    assert second.ended() == 0
    assert runs.log.count("start code-p") == 1
    assert runs.log.index("end code-p") < runs.log.index("start code-d")


def test_every_read_and_write_of_the_tree_holds_the_per_git_dir_lock(
    repo: Path, journal: Path, runs: Runs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each time the tree's state file is written, the delivery lock in the
    git directory is held: another descriptor cannot take it."""
    from mcgyvr import atomic

    lock = repo / ".git" / "mcgyvr-delivery.lock"
    write = atomic.write
    held: list[bool] = []

    def checked(path: Path, *args: Any, **kwargs: Any) -> Any:
        if "trees" in path.parts:
            fd = os.open(lock, os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held.append(False)
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BlockingIOError:
                held.append(True)
            finally:
                os.close(fd)
        return write(path, *args, **kwargs)

    monkeypatch.setattr(atomic, "write", checked)
    assert run_batch(repo, journal, runs, (code("code-a", "pkg/a.py"),)) == 0
    assert held and all(held)


def test_two_batches_started_at_once_serialize_and_lose_nothing(
    repo: Path, journal: Path, runs: Runs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two batches reach the tree together, each with two contracts: one makes
    the tree, the other joins it, and the state file ends with all four."""
    from mcgyvr.board import Board

    both = threading.Barrier(2, timeout=WAIT)
    join = Board.join

    def together(self: Board, *args: Any, **kwargs: Any) -> str:
        both.wait()
        return join(self, *args, **kwargs)

    monkeypatch.setattr(Board, "join", together)

    def batch_of(pair: str) -> Callable[[], int]:
        contracts = tuple(code(f"code-{n}", f"pkg/{n}.py") for n in pair)
        return lambda: run_batch(repo, journal, runs, contracts)

    batches = [Batch(batch_of(pair)) for pair in ("ab", "cd")]
    for each in batches:
        each.start()
    assert [each.ended() for each in batches] == [0, 0]

    (path,) = tree_files(journal)
    assert {cid: r["state"] for cid, r in rows(path).items()} == {
        f"code-{n}": "landed" for n in "abcd"
    }
    assert len({r["batch"] for r in rows(path).values()}) == 2
    assert state(path)["retired"] is True
