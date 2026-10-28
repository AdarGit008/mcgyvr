"""`delegate --run --jobs N` runs N ready contracts at once, settling each as it ends.

The batches below run against a real repository. The run of each contract is
stood in for, but its change is delivered through the real `deliver`, from
the HEAD the run started on, the way a sandbox starts from HEAD: so the
per-git-dir delivery lock (#381) and its "committed to after the run started"
refusal are the real ones, and "landed" is read from what HEAD really holds.
Which run ends when is driven by events and barriers, never by sleeping.

What is held at N>1 is what holds at N=1: a contract lands when HEAD holds its
commit, a dependent never starts before what it waits on has settled (#779),
one whose provider failed is held `blocked` (#779), a spent one is re-planned
(#782), and the `--log` record says how the batch ended (#792). `--jobs 1` is
today's loop, on the calling thread, byte for byte.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr.cli.commands import delegate as command
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract, dumps
from mcgyvr.delegate_log import DelegateKind, read
from mcgyvr.deliver import deliver
from mcgyvr.orchestrator.decompose import Decomposition
from mcgyvr.result import RunResult, result_path, run_stamp, write
from mcgyvr.scope import Scope
from mcgyvr.session import Session
from tests.decomposes import git

WAIT = 10.0
#: What a result holds that differs between two runs of the same batch.
VARIES = frozenset({"run", "commit", "started", "finished", "journal", "blocked_by"})
#: A run stamp, as it appears in a result file's name.
STAMP = re.compile(r"\d{8}T\d{6}\.\d{6}Z")
FILES = ("a", "b", "c", "d", "e")


def code(cid: str, target: str, *, depends_on: tuple[str, ...] = ()) -> Contract:
    return Contract(
        id=cid,
        task_type="code",
        task=f"Add a function named {cid.replace('-', '_')} to {target}.",
        target=target,
        scope=Scope.of([target], []),
        depends_on=depends_on,
    )


class Policy(dict[str, Any]):
    """The keys a batch reads from its config."""

    def get(self, key: str, default: Any = None) -> Any:
        return super().get(key, default)


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


def head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def shown(repo: Path, rev: str, path: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "show", f"{rev}:{path}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def waits_for(event: threading.Event) -> Callable[[], None]:
    """A step that waits for `event`, and fails rather than wait forever."""

    def wait() -> None:
        assert event.wait(WAIT), "what this run waits for never came"

    return wait


@dataclass
class Plan:
    """What one stood-in run does: wait, then come to `outcome`."""

    outcome: str = "accepted"
    before: Callable[[], object] | None = None
    raises: BaseException | None = None
    says: tuple[str, ...] = ()


class Runs:
    """Stands in for `_run`: delivers each change for real, and keeps a log."""

    def __init__(
        self, repo: Path, journal: Path, contracts: dict[str, Contract], plans: Any
    ) -> None:
        self.repo = repo
        self.journal = journal
        self.contracts = contracts
        self.plans: dict[str, Plan] = plans
        self.lock = threading.Lock()
        self.log: list[str] = []
        self.running: set[str] = set()
        self.most = 0
        self.bases: dict[str, str] = {}
        self.threads: dict[str, threading.Thread] = {}

    def note(self, line: str) -> None:
        with self.lock:
            self.log.append(line)

    def __call__(self, args: argparse.Namespace) -> int:
        cid = Path(args.contract).stem
        plan = self.plans.get(cid, Plan())
        base = head(self.repo)
        with self.lock:
            self.log.append(f"start {cid}")
            self.running.add(cid)
            self.most = max(self.most, len(self.running))
            self.bases[cid] = base
            self.threads[cid] = threading.current_thread()
        try:
            return self._run(cid, plan, base)
        finally:
            with self.lock:
                self.running.discard(cid)
                self.log.append(f"end {cid}")

    def _run(self, cid: str, plan: Plan, base: str) -> int:
        import sys

        for line in plan.says:
            print(f"{cid}: {line}")
            print(f"{cid}: {line} (err)", file=sys.stderr)
        if plan.before is not None:
            plan.before()
        if plan.raises is not None:
            raise plan.raises
        contract = self.contracts[cid]
        report = RunResult(
            contract=cid,
            task_type="code",
            target=contract.target,
            session="test-session",
            outcome=plan.outcome,
        )
        exit_code = 1
        if plan.outcome == "accepted":
            text = shown(self.repo, base, contract.target)
            name = cid.replace("-", "_")
            delivery = deliver(
                repo=self.repo,
                contract=contract,
                content=f"{text}\n\ndef {name}():\n    return 1\n",
                base=base,
            )
            if delivery.committed:
                report.committed, report.commit = True, delivery.commit
                exit_code = 0
            else:
                report.outcome, report.detail = "delivery_refused", delivery.reason
        write(result_path(self.journal, cid, run_stamp()), report)
        return exit_code


def batch(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: tuple[Contract, ...],
    plans: dict[str, Plan] | None = None,
    *,
    jobs: int | None = 2,
    config: Any = None,
    replan: Any = None,
    book: Any = None,
    later: tuple[Contract, ...] = (),
) -> tuple[int, Runs, Path]:
    journal = tmp_path / "journal"
    known = {c.id: c for c in (*contracts, *later)}
    runs = Runs(repo, journal, known, plans or {})
    monkeypatch.setattr(command, "_run", runs)
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
    )
    if jobs is not None:
        args.jobs = jobs
    if config is None:
        config = Policy({"journal.dir": str(journal), "dependents": "hold"})
        # Width enough for every test that does not test the cap itself.
        monkeypatch.setattr(command, "_fleet_width", lambda _config: 8)
    exit_code = command._run_delegated(
        args, repo, dec, [], cast(Config, config), replan=replan, book=book
    )
    return exit_code, runs, journal


def results(journal: Path, cid: str) -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text())
        for p in sorted((journal / "results").glob(f"{cid}-*.json"))
    ]


def states(journal: Path) -> dict[str, dict[str, Any]]:
    (state,) = (journal / "trees").glob("tree-*.json")
    return {r["contract"]: r for r in json.loads(state.read_text())["contracts"]}


def test_two_siblings_run_at_once_and_both_land(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    both = threading.Barrier(2, timeout=WAIT)
    plans = {"code-a": Plan(before=both.wait), "code-b": Plan(before=both.wait)}

    exit_code, runs, journal = batch(
        repo,
        tmp_path,
        monkeypatch,
        (code("code-a", "pkg/a.py"), code("code-b", "pkg/b.py")),
        plans,
    )

    assert exit_code == 0
    # Neither could pass the barrier without the other: they ran at once.
    assert runs.most == 2
    assert runs.bases["code-a"] == runs.bases["code-b"]
    rows = states(journal)
    assert {rows[c]["state"] for c in ("code-a", "code-b")} == {"landed"}
    # Landed means HEAD holds the commit.
    for cid in ("code-a", "code-b"):
        (result,) = results(journal, cid)
        git(repo, "merge-base", "--is-ancestor", result["commit"], "HEAD")
    assert "def code_a()" in (repo / "pkg" / "a.py").read_text()
    assert "def code_b()" in (repo / "pkg" / "b.py").read_text()


def test_two_siblings_on_one_file_are_never_run_at_once_and_both_land(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At N=1 the second starts from the commit the first landed; so at N>1.

    `code-b` on another file runs beside them, so the width is there to use.
    """
    b_started = threading.Event()
    plans = {
        "code-a1": Plan(before=waits_for(b_started)),
        "code-b": Plan(before=b_started.set),
    }

    exit_code, runs, journal = batch(
        repo,
        tmp_path,
        monkeypatch,
        (
            code("code-a1", "pkg/a.py"),
            code("code-a2", "pkg/a.py"),
            code("code-b", "pkg/b.py"),
        ),
        plans,
    )

    assert exit_code == 0
    assert runs.log.index("end code-a1") < runs.log.index("start code-a2")
    (first,) = results(journal, "code-a1")
    assert runs.bases["code-a2"] != runs.bases["code-a1"]
    git(repo, "merge-base", "--is-ancestor", first["commit"], runs.bases["code-a2"])
    assert {r["state"] for r in states(journal).values()} == {"landed"}
    text = (repo / "pkg" / "a.py").read_text()
    assert "def code_a1()" in text and "def code_a2()" in text


def test_two_deliveries_into_one_repository_from_two_threads_never_lose_one(
    repo: Path,
) -> None:
    """#380 B3 under threads: one commits, the other is refused by name.

    Both changes were judged against the same base; the delivery lock is a
    `flock` per git directory, which two threads of one process contend for
    as two processes do.
    """
    target = "pkg/a.py"
    contract = code("code-a", target)
    base = head(repo)
    text = shown(repo, base, target)
    both = threading.Barrier(2, timeout=WAIT)
    came: dict[str, Any] = {}

    def land(name: str) -> None:
        both.wait()
        came[name] = deliver(
            repo=repo,
            contract=contract,
            content=f"{text}\n\ndef {name}():\n    return 1\n",
            base=base,
        )

    workers = [threading.Thread(target=land, args=(n,)) for n in ("one", "two")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(WAIT)

    landed = [n for n, d in came.items() if d.committed]
    refused = [d for d in came.values() if not d.committed]
    assert len(landed) == 1 and len(refused) == 1
    assert "pkg/a.py was committed to after the run started" in refused[0].reason
    assert f"def {landed[0]}()" in (repo / target).read_text()
    assert git_status(repo) == ""


def test_a_reader_between_deliveries_holds_the_delivery_lock(repo: Path) -> None:
    """What a run beside others reads of the working tree is read between two
    deliveries: the lock a delivery takes is held for the block."""
    import fcntl
    import os

    from mcgyvr.deliver import between_deliveries

    lock = repo / ".git" / "mcgyvr-delivery.lock"
    with between_deliveries(repo):
        fd = os.open(lock, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
    fd = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)


def test_a_reader_between_deliveries_reads_anyway_where_none_can_deliver(
    tmp_path: Path,
) -> None:
    from mcgyvr.deliver import between_deliveries

    ran = False
    with between_deliveries(tmp_path / "not-a-repository"):
        ran = True
    assert ran


def git_status(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_a_dependent_never_starts_before_what_it_waits_on_has_settled(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provider and a sibling run at once; the dependent waits for the settle."""
    from mcgyvr.board import Board

    seen: list[str] = []
    settle = Board.settle

    def settling(self: Board, tree_id: str, contract_id: str, **kw: Any) -> None:
        seen.append(f"settle {contract_id}")
        settle(self, tree_id, contract_id, **kw)

    monkeypatch.setattr(Board, "settle", settling)
    sibling_started = threading.Event()
    plans = {
        "code-p": Plan(before=waits_for(sibling_started)),
        "code-s": Plan(before=sibling_started.set),
        "code-d": Plan(before=lambda: seen.append("start code-d")),
    }

    exit_code, runs, journal = batch(
        repo,
        tmp_path,
        monkeypatch,
        (
            code("code-p", "pkg/a.py"),
            code("code-d", "pkg/c.py", depends_on=("code-p",)),
            code("code-s", "pkg/b.py"),
        ),
        plans,
        jobs=3,
    )

    assert exit_code == 0
    assert runs.most == 2
    assert seen.index("settle code-p") < seen.index("start code-d")
    (provider,) = results(journal, "code-p")
    git(repo, "merge-base", "--is-ancestor", provider["commit"], runs.bases["code-d"])
    assert {r["state"] for r in states(journal).values()} == {"landed"}


def test_a_contract_whose_provider_failed_is_held_blocked_as_at_one_job(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contracts = (
        code("code-p", "pkg/a.py"),
        code("code-d", "pkg/c.py", depends_on=("code-p",)),
        code("code-s", "pkg/b.py"),
    )
    plans = {"code-p": Plan(outcome="ladder_spent")}
    held: dict[int, dict[str, Any]] = {}
    for jobs in (1, 2):
        where = tmp_path / f"jobs-{jobs}"
        where.mkdir()
        log = where / "delegate-log.json"
        book = command._Logbook(str(log))
        exit_code, runs, journal = batch(
            repo, where, monkeypatch, contracts, plans, jobs=jobs, book=book
        )
        book.write(exit_code)

        assert exit_code == 3
        assert "start code-d" not in runs.log
        (result,) = results(journal, "code-d")
        assert result["outcome"] == "blocked"
        assert result["attempts"] == []
        assert result["blocked_by"]["reason"] == "provider_failed"
        rows = states(journal)
        assert rows["code-d"]["state"] == "dead"
        assert rows["code-p"]["state"] == "failed"
        assert rows["code-s"]["state"] == "landed"
        record = read(log)
        assert record.kind is DelegateKind.BATCH_HELD
        assert record.exit_code == 3
        assert record.detail["held"] == ["code-d"]
        (state,) = (journal / "trees").glob("tree-*.json")
        assert record.detail["tree_state"] == str(state)
        held[jobs] = {k: v for k, v in result.items() if k not in VARIES}
        git(repo, "reset", "-q", "--hard", "HEAD~1")
    assert held[1] == held[2]


class Orchestrator:
    """Stands in for re-planning: answers with `proposes`."""

    def __init__(self, *proposes: Contract) -> None:
        self.proposes = proposes
        self.shown: list[Any] = []

    def __call__(self, spent: Any) -> Decomposition:
        self.shown.append(spent)
        return Decomposition(
            contracts=self.proposes,
            documents=tuple(dumps(c) for c in self.proposes),
        )


def test_a_spent_contract_is_replanned_and_its_dependent_runs_after_the_replacement(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    narrow = code("code-narrow", "pkg/a.py")
    contracts = (
        code("code-p", "pkg/a.py"),
        code("code-d", "pkg/c.py", depends_on=("code-p",)),
        code("code-s", "pkg/b.py"),
    )
    orchestrator = Orchestrator(narrow)
    plans = {"code-p": Plan(outcome="ladder_spent")}
    policy = Policy(
        {
            "journal.dir": str(tmp_path / "journal"),
            "dependents": "hold",
            "max_replans": 1,
        }
    )
    monkeypatch.setattr(command, "_fleet_width", lambda _config: 8)

    exit_code, runs, journal = batch(
        repo,
        tmp_path,
        monkeypatch,
        contracts,
        plans,
        config=policy,
        replan=orchestrator,
        later=(narrow,),
    )

    assert exit_code == 0, runs.log
    (spent,) = orchestrator.shown
    assert spent.contract.id == "code-p"
    assert runs.log.index("end code-narrow") < runs.log.index("start code-d")
    (result,) = results(journal, "code-p")
    assert result["replanned"]["contracts"] == ["code-narrow"]
    rows = states(journal)
    assert rows["code-narrow"]["state"] == "landed"
    assert rows["code-d"]["state"] == "landed"
    assert rows["code-s"]["state"] == "landed"


def test_jobs_is_capped_at_the_fleet_width(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Five siblings, `--jobs 8`, a fleet of 1 + 2 slots: three run at once, no more."""
    journal = tmp_path / "journal"
    config = parse(
        f"""
units:
  small:
    address: http://127.0.0.1:9/v1
    model: small-coder
    width: 1
    window: 32768
  large:
    address: http://127.0.0.1:9/v1
    model: large-coder
    width: 2
    window: 32768
ladder: [small, large]
journal:
  dir: {journal}
"""
    )
    three = threading.Barrier(3, timeout=WAIT)
    contracts = tuple(code(f"code-{n}", f"pkg/{n}.py") for n in FILES)
    plans = {c.id: Plan(before=three.wait) for c in contracts[:3]}

    exit_code, runs, journal = batch(
        repo, tmp_path, monkeypatch, contracts, plans, jobs=8, config=config
    )

    assert exit_code == 0
    assert runs.most == 3
    assert "--jobs 8 is capped at the fleet's 3 slots" in capsys.readouterr().err
    assert command._fleet_width(config) == 3


@pytest.mark.parametrize("asked", [0, 3, 8])
def test_auto_or_zero_is_the_fleet_width_and_any_n_is_capped_at_it(asked: int) -> None:
    assert command._width(asked, 3) == 3
    assert command._width(2, 3) == 2
    assert command._width(1, 0) == 1
    assert command._width(0, 0) == 1


def test_jobs_parses_auto_as_zero_and_refuses_a_negative() -> None:
    assert command._jobs("auto") == 0
    assert command._jobs("4") == 4
    with pytest.raises(argparse.ArgumentTypeError):
        command._jobs("-1")
    with pytest.raises(argparse.ArgumentTypeError):
        command._jobs("many")


def test_jobs_one_is_todays_loop_on_the_calling_thread_byte_for_byte(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No `--jobs` and `--jobs 1` write the same results, log and output."""
    contracts = (
        code("code-p", "pkg/a.py"),
        code("code-d", "pkg/c.py", depends_on=("code-p",)),
        code("code-s", "pkg/b.py"),
    )
    plans = {"code-p": Plan(outcome="ladder_spent", says=("climbing",))}
    seen: dict[str, Any] = {}
    for label, jobs in (("default", None), ("one", 1)):
        where = tmp_path / label
        where.mkdir()
        log = where / "delegate-log.json"
        book = command._Logbook(str(log))
        exit_code, runs, journal = batch(
            repo, where, monkeypatch, contracts, plans, jobs=jobs, book=book
        )
        book.write(exit_code)
        out = capsys.readouterr()
        assert set(runs.threads.values()) == {threading.current_thread()}
        seen[label] = (
            exit_code,
            runs.log,
            out.out.replace(str(journal), "<journal>"),
            out.err.replace(str(journal), "<journal>"),
            {
                c.id: [_stable(r, journal) for r in results(journal, c.id)]
                for c in contracts
            },
            _stable(json.loads(log.read_text()), journal),
        )
        git(repo, "reset", "-q", "--hard", "HEAD~1")
    for default, one in zip(seen["default"], seen["one"], strict=True):
        assert default == one


def _stable(doc: Any, journal: Path) -> Any:
    """`doc` without what differs between two runs: stamps, commits, the dir."""
    text = json.dumps(doc, sort_keys=True).replace(str(journal), "<journal>")
    found = json.loads(STAMP.sub("<stamp>", text))
    if isinstance(found, dict):
        for key in VARIES - {"journal", "blocked_by"}:
            found.pop(key, None)
    return found


def test_a_run_s_output_is_written_whole_never_between_another_s_lines(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`code-a` says its first line, `code-b` says its own, `code-a` its second."""
    a_said = threading.Event()
    b_said = threading.Event()

    def a_waits() -> None:
        a_said.set()
        assert b_said.wait(WAIT)
        print("code-a: second")

    def b_waits() -> None:
        assert a_said.wait(WAIT)
        b_said.set()

    plans = {
        "code-a": Plan(says=("first",), before=a_waits),
        "code-b": Plan(says=("only",), before=b_waits),
    }

    exit_code, _, _ = batch(
        repo,
        tmp_path,
        monkeypatch,
        (code("code-a", "pkg/a.py"), code("code-b", "pkg/b.py")),
        plans,
    )

    assert exit_code == 0
    out = capsys.readouterr()
    assert "code-a: first\ncode-a: second\n" in out.out
    assert "code-b: only\n" in out.out
    assert "code-a: first (err)\n" in out.err
    assert "code-b: only (err)\n" in out.err


def test_a_worker_that_raises_is_logged_internal_error_once_the_others_end(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exception is raised on, as at N=1, but only after `code-b` has ended
    and been settled, so the tree's state file says what became of it."""
    b_started = threading.Event()
    plans = {
        "code-a": Plan(
            before=waits_for(b_started),
            raises=RuntimeError("the run broke"),
        ),
        "code-b": Plan(before=b_started.set),
    }
    log = tmp_path / "delegate-log.json"
    contracts = (code("code-a", "pkg/a.py"), code("code-b", "pkg/b.py"))

    def logged(args: argparse.Namespace, book: Any) -> int:
        return batch(repo, tmp_path, monkeypatch, contracts, plans, book=book)[0]

    monkeypatch.setattr(command, "_delegate_logged", logged)
    with pytest.raises(RuntimeError, match="the run broke"):
        command._delegate(argparse.Namespace(log=str(log)))

    record = read(log)
    assert record.kind is DelegateKind.INTERNAL_ERROR
    assert record.exit_code == 1
    assert record.detail["error_class"] == "RuntimeError"
    journal = tmp_path / "journal"
    (b,) = results(journal, "code-b")
    assert b["committed"] is True
    rows = states(journal)
    assert rows["code-b"]["state"] == "landed"
    assert rows["code-a"]["state"] == "running"
