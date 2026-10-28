"""A batch re-plans a contract whose ladder is spent, and frees what it held.

A batch of two: one contract renames a function in `pkg/codec.py`, the other
moves its caller in `pkg/export.py` to the new name and waits on the first.
The rename climbs every rung and comes to `ladder_spent`. Rather than stop
there and hold the caller, the batch hands the spent contract back to the
orchestrator with the failure notes its climb left (`attempts[].notes` of its
result), takes the contract that comes back in its place on the tree, and
runs it; once it lands the caller is sent. `max_replans` bounds how many
times a line of work is re-planned, read from the `replan` lineage the new
contract carries, never from memory.

The run of each contract and the orchestrator are stood in for, so what is
checked is what the batch hands the orchestrator, what it swaps in, the order
it runs in and what the results say, against a real repository.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr.cli.commands import delegate as command
from mcgyvr.config import Config
from mcgyvr.contract import Contract, dumps
from mcgyvr.contract import load as load_contract
from mcgyvr.notes import FailureNote, FailureNotes, NoteKind
from mcgyvr.orchestrator.decompose import Decomposition
from mcgyvr.result import AttemptResult, RunResult, result_path, run_stamp, write
from mcgyvr.scope import Scope
from mcgyvr.session import Session
from tests.decomposes import git

CODEC = "def rec_to_map(record):\n    return sorted(record.items())\n"
EXPORT = "from pkg.codec import rec_to_map\n\n\ndef export(rs):\n    return rs\n"
STOP = ("the change needs a file outside the target",)

RENAME = Contract(
    id="code-rename",
    task_type="code",
    task="Rename rec_to_map to pairs_of and update callers within the module.",
    target="pkg/codec.py",
    scope=Scope.of(["pkg/codec.py"], []),
    stop_conditions=STOP,
    interface="def pairs_of(record) -> list",
)
CALLER = Contract(
    id="code-caller",
    task_type="code",
    task="Call pairs_of from pkg.codec instead of the old rec_to_map.",
    target="pkg/export.py",
    scope=Scope.of(["pkg/export.py"], []),
    stop_conditions=STOP,
    target_content=EXPORT,
    depends_on=("code-rename",),
)
#: What the orchestrator proposes in the spent rename's place: the same target,
#: a narrower task.
NARROWER = Contract(
    id="code-narrow",
    task_type="code",
    task="Rename the function rec_to_map to pairs_of; change nothing else.",
    target="pkg/codec.py",
    scope=Scope.of(["pkg/codec.py"], []),
    stop_conditions=STOP,
    interface="def pairs_of(record) -> list",
)

#: The record the rename's one failed attempt left.
NOTES = FailureNotes(
    rung="local",
    family="local",
    attempt=1,
    checks=("tests_pass",),
    notes=(
        FailureNote(
            check="tests_pass",
            kind=NoteKind.FINDING,
            message="NameError: name 'pairs_of' is not defined",
            path="pkg/codec.py",
            line=2,
            command="pytest -q",
            exit_code=1,
        ),
    ),
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
    (root / "pkg" / "codec.py").write_text(CODEC)
    (root / "pkg" / "export.py").write_text(EXPORT)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return root


def git_head(repo: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def stand_in(
    repo: Path,
    journal: Path,
    came_to: dict[str, tuple[str, bool]],
    ran: list[Contract],
) -> Callable[[argparse.Namespace], int]:
    """A run that comes to `came_to[id]`: an outcome, and whether to commit.

    It reads the contract file it is handed, as a real run does, and a spent
    climb's result carries the failure notes of its one attempt.
    """

    def run(args: argparse.Namespace) -> int:
        contract = load_contract(Path(args.contract))
        # A run inside the batch is told so: the batch, not the run, says what
        # becomes of a spent contract.
        assert args.in_batch is True
        ran.append(contract)
        outcome, commits = came_to[contract.id]
        report = RunResult(
            contract=contract.id,
            task_type="code",
            target=contract.target,
            session="o",
            outcome=outcome,
            detail=f"{contract.id} came to {outcome}",
        )
        if outcome == "ladder_spent":
            report.attempts.append(
                AttemptResult(
                    rung="local",
                    attempt=1,
                    verdict="failed",
                    notes=NOTES.as_json(),
                )
            )
        if commits:
            codec = repo / "pkg" / "codec.py"
            codec.write_text(codec.read_text().replace("rec_to_map", "pairs_of"))
            git(repo, "commit", "-q", "-am", "rename")
            report.committed, report.commit = True, git_head(repo)
        write(result_path(journal, contract.id, run_stamp()), report)
        return 0 if outcome == "accepted" else 1

    return run


class Orchestrator:
    """Stands in for re-planning: answers `proposes`, and keeps what it was shown."""

    def __init__(self, *proposes: Contract) -> None:
        self.proposes = proposes
        self.shown: list[Any] = []

    def __call__(self, spent: Any) -> Decomposition:
        self.shown.append(spent)
        return Decomposition(
            contracts=self.proposes,
            documents=tuple(dumps(c) for c in self.proposes),
        )


def run_batch(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    came_to: dict[str, tuple[str, bool]],
    orchestrator: Orchestrator,
    *,
    max_replans: int | None = None,
) -> tuple[int, list[Contract], Path]:
    journal = tmp_path / "journal"
    ran: list[Contract] = []
    monkeypatch.setattr(command, "_run", stand_in(repo, journal, came_to, ran))
    dec = Decomposition(
        contracts=(RENAME, CALLER), documents=(dumps(RENAME), dumps(CALLER))
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
    policy = Policy({"journal.dir": str(journal), "dependents": "hold"})
    if max_replans is not None:
        policy["max_replans"] = max_replans
    code = command._run_delegated(
        args, repo, dec, [], cast(Config, policy), replan=orchestrator
    )
    return code, ran, journal


def results(journal: Path, cid: str) -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text())
        for p in sorted((journal / "results").glob(f"{cid}-*.json"))
    ]


def test_a_spent_rename_is_replanned_and_its_caller_runs_after_the_replacement(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    orchestrator = Orchestrator(NARROWER)
    code, ran, journal = run_batch(
        repo,
        tmp_path,
        monkeypatch,
        {
            "code-rename": ("ladder_spent", False),
            "code-narrow": ("accepted", True),
            "code-caller": ("accepted", False),
        },
        orchestrator,
    )

    assert [c.id for c in ran] == ["code-rename", "code-narrow", "code-caller"]
    assert code == 0
    # The orchestrator was shown the spent contract and the notes its climb left,
    # as records, not as prose.
    (spent,) = orchestrator.shown
    assert spent.contract.id == "code-rename"
    assert spent.failures == (NOTES,)
    # The contract run in its place says what it replaces and which round it is.
    narrow = ran[1]
    assert (narrow.replan.replaces, narrow.replan.round) == ("code-rename", 1)
    # The spent run's result says what became of it.
    (result,) = results(journal, "code-rename")
    assert result["outcome"] == "ladder_spent"
    assert result["replanned"]["round"] == 1
    assert result["replanned"]["max_replans"] == 1
    assert result["replanned"]["contracts"] == ["code-narrow"]
    assert "code-narrow" in result["detail"]
    # The tree took the new contract in the spent one's place.
    (state,) = (journal / "trees").glob("tree-*.json")
    rows = {r["contract"]: r for r in json.loads(state.read_text())["contracts"]}
    assert "code-rename" not in rows
    assert rows["code-narrow"]["state"] == "landed"
    assert rows["code-narrow"]["replaces"] == "code-rename"
    assert rows["code-caller"]["waits_on"] == ["code-narrow"]
    assert "re-planned" in capsys.readouterr().err


def test_a_replacement_that_is_spent_too_is_not_replanned_past_max_replans(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = Orchestrator(NARROWER)
    code, ran, journal = run_batch(
        repo,
        tmp_path,
        monkeypatch,
        {
            "code-rename": ("ladder_spent", False),
            "code-narrow": ("ladder_spent", False),
        },
        orchestrator,
    )

    assert [c.id for c in ran] == ["code-rename", "code-narrow"]
    assert len(orchestrator.shown) == 1
    (second,) = results(journal, "code-narrow")
    assert second["replanned"]["contracts"] == []
    assert "max_replans" in second["replanned"]["detail"]
    (held,) = results(journal, "code-caller")
    assert held["outcome"] == "blocked"
    assert held["blocked_by"]["providers"][0]["contract"] == "code-narrow"
    assert code == 3


def test_max_replans_zero_leaves_a_spent_contract_where_it_stopped(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = Orchestrator(NARROWER)
    code, ran, journal = run_batch(
        repo,
        tmp_path,
        monkeypatch,
        {"code-rename": ("ladder_spent", False)},
        orchestrator,
        max_replans=0,
    )

    assert [c.id for c in ran] == ["code-rename"]
    assert orchestrator.shown == []
    (result,) = results(journal, "code-rename")
    assert "replanned" not in result
    assert results(journal, "code-caller")[0]["outcome"] == "blocked"
    assert code == 3


def test_a_replan_that_proposes_the_spent_contract_again_frees_nothing(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = Orchestrator(RENAME)
    code, ran, journal = run_batch(
        repo,
        tmp_path,
        monkeypatch,
        {"code-rename": ("ladder_spent", False)},
        orchestrator,
    )

    assert [c.id for c in ran] == ["code-rename"]
    (result,) = results(journal, "code-rename")
    assert result["replanned"]["contracts"] == []
    assert "nothing new" in result["replanned"]["detail"]
    assert results(journal, "code-caller")[0]["outcome"] == "blocked"
    assert code == 3


def test_a_replacement_that_waits_on_the_spent_contract_is_not_taken(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The spent rename proposed again unchanged, and a follow-up waiting on it:
    # the follow-up could never start, so nothing new came back.
    follow_up = Contract(
        id="code-follow-up",
        task_type="code",
        task="Document pairs_of.",
        target="pkg/codec.py",
        scope=Scope.of(["pkg/codec.py"], []),
        stop_conditions=STOP,
        depends_on=("code-rename",),
    )
    orchestrator = Orchestrator(RENAME, follow_up)
    code, ran, journal = run_batch(
        repo,
        tmp_path,
        monkeypatch,
        {"code-rename": ("ladder_spent", False)},
        orchestrator,
    )

    assert [c.id for c in ran] == ["code-rename"]
    (result,) = results(journal, "code-rename")
    assert result["replanned"]["contracts"] == []
    assert "nothing new" in result["replanned"]["detail"]
    assert results(journal, "code-caller")[0]["outcome"] == "blocked"
    assert code == 3
