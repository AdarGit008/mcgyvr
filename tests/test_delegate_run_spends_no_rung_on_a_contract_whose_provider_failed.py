"""`delegate --run` spends no rung on a contract whose provider failed.

A batch of two: one contract renames a function in `pkg/codec.py`, the other
moves its caller in `pkg/export.py` to the new name and waits on the first.
The run of each contract is stood in for — it writes the result file a real
run writes, and commits when told to land — so what is checked is the order
the batch runs in, what it holds, and what it writes for a held contract,
against a real repository.
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
from mcgyvr.contract import Contract
from mcgyvr.orchestrator.decompose import Decomposition
from mcgyvr.result import RunResult, result_path, run_stamp, write
from mcgyvr.scope import Scope
from mcgyvr.session import Session
from tests.decomposes import git

CODEC = "def rec_to_map(record):\n    return sorted(record.items())\n"
EXPORT = "from pkg.codec import rec_to_map\n\n\ndef export(rs):\n    return rs\n"

RENAME = Contract(
    id="code-rename",
    task_type="code",
    task="Rename rec_to_map to pairs_of and update callers within the module.",
    target="pkg/codec.py",
    scope=Scope.of(["pkg/codec.py"], []),
    interface="def pairs_of(record) -> list",
)
CALLER = Contract(
    id="code-caller",
    task_type="code",
    task="Call pairs_of from pkg.codec instead of the old rec_to_map.",
    target="pkg/export.py",
    scope=Scope.of(["pkg/export.py"], []),
    target_content=EXPORT,
    depends_on=("code-rename",),
)


class Policy(dict[str, Any]):
    """The two keys a batch reads from its config."""

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


def stand_in(
    repo: Path, journal: Path, came_to: dict[str, tuple[str, bool]], ran: list[str]
) -> Callable[[argparse.Namespace], int]:
    """A run that comes to `came_to[id]`: an outcome, and whether to commit."""

    def run(args: argparse.Namespace) -> int:
        cid = Path(args.contract).stem
        ran.append(cid)
        outcome, commits = came_to[cid]
        report = RunResult(
            contract=cid, task_type="code", target="", session="o", outcome=outcome
        )
        if commits:
            codec = repo / "pkg" / "codec.py"
            codec.write_text(codec.read_text().replace("rec_to_map", "pairs_of"))
            git(repo, "commit", "-q", "-am", "rename")
            head = git_head(repo)
            report.committed, report.commit = True, head
        write(result_path(journal, cid, run_stamp()), report)
        return 0 if outcome == "accepted" else 1

    return run


def git_head(repo: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def run_batch(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    came_to: dict[str, tuple[str, bool]],
    *,
    dependents: str = "hold",
    record: Path | None = None,
    book: Any = None,
) -> tuple[int, list[str], Path]:
    journal = tmp_path / "journal"
    ran: list[str] = []
    monkeypatch.setattr(command, "_run", stand_in(repo, journal, came_to, ran))
    dec = Decomposition(contracts=(RENAME, CALLER), documents=("{}", "{}"))
    args = argparse.Namespace(
        config=None,
        sandbox=None,
        commit=True,
        branch=None,
        record=str(record) if record else None,
        session_id="test-session",
        session=Session("test-session"),
    )
    config = cast(
        Config, Policy({"journal.dir": str(journal), "dependents": dependents})
    )
    code = command._run_delegated(args, repo, dec, [], config, book=book)
    return code, ran, journal


def results(journal: Path, cid: str) -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text())
        for p in sorted((journal / "results").glob(f"{cid}-*.json"))
    ]


def test_the_caller_of_a_failed_rename_is_held_and_never_sent(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mirror = tmp_path / "mirror"
    code, ran, journal = run_batch(
        repo,
        tmp_path,
        monkeypatch,
        {"code-rename": ("ladder_spent", False)},
        record=mirror,
    )

    assert ran == ["code-rename"]
    assert code == 3
    (held,) = results(journal, "code-caller")
    assert held["outcome"] == "blocked"
    assert held["attempts"] == []
    assert held["exit_code"] == 3
    assert held["session"] == "test-session"
    blocked_by = held["blocked_by"]
    assert blocked_by["reason"] == "provider_failed"
    assert [(p["contract"], p["outcome"]) for p in blocked_by["providers"]] == [
        ("code-rename", "ladder_spent")
    ]
    assert blocked_by["providers"][0]["result"].endswith(".json")
    assert {n["symbol"] for n in blocked_by["needs"]} == {"pairs_of", "rec_to_map"}
    assert "no rung spent" in held["detail"]
    assert results(mirror, "code-caller") == [held]
    (state,) = (journal / "trees").glob("tree-*.json")
    rows = {r["contract"]: r for r in json.loads(state.read_text())["contracts"]}
    assert rows["code-caller"]["state"] == "dead"
    assert rows["code-rename"]["state"] == "failed"
    out = capsys.readouterr()
    assert "result: " not in out.out, out.out
    assert "held: waits on code-rename" in out.err


def test_the_caller_of_a_rename_that_landed_is_sent_after_it(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, ran, journal = run_batch(
        repo,
        tmp_path,
        monkeypatch,
        {"code-rename": ("accepted", True), "code-caller": ("accepted", False)},
    )

    assert ran == ["code-rename", "code-caller"]
    assert code == 0
    assert [r["outcome"] for r in results(journal, "code-caller")] == ["accepted"]


def test_a_rename_accepted_but_left_uncommitted_did_not_land(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ran, journal = run_batch(
        repo, tmp_path, monkeypatch, {"code-rename": ("accepted", False)}
    )

    assert ran == ["code-rename"]
    (held,) = results(journal, "code-caller")
    assert held["blocked_by"]["reason"] == "provider_not_landed"
    assert "--commit" in held["detail"]


def test_under_dependents_run_the_caller_is_sent_anyway(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ran, journal = run_batch(
        repo,
        tmp_path,
        monkeypatch,
        {"code-rename": ("ladder_spent", False), "code-caller": ("rejected", False)},
        dependents="run",
    )

    assert ran == ["code-rename", "code-caller"]
    assert [r["outcome"] for r in results(journal, "code-caller")] == ["rejected"]


def test_a_batch_that_held_a_contract_is_logged_as_batch_held(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `--log` record names what was held and the Board's state file.

    It points at the tree's state file, never at the per-contract result files:
    those stay with the Board and the re-planner that read them.
    """
    from mcgyvr.delegate_log import DelegateKind, read

    log = tmp_path / "delegate-log.json"
    book = command._Logbook(str(log))
    code, _, journal = run_batch(
        repo,
        tmp_path,
        monkeypatch,
        {"code-rename": ("ladder_spent", False)},
        book=book,
    )
    book.write(code)

    record = read(log)
    assert record.kind is DelegateKind.BATCH_HELD
    assert record.exit_code == code == 3
    assert record.detail["held"] == ["code-caller"]
    (state,) = (journal / "trees").glob("tree-*.json")
    assert record.detail["tree_state"] == str(state)
    assert "results" not in json.dumps(record.detail)
