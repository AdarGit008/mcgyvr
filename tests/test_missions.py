"""#365 — the mission runner: five RED tests, one property each.

Each test loads its module under ``tools/missions/`` by path, the way the bench
rigs are loaded (``tests/test_bench_rounds.py``), and fails **by name** while
the module does not exist — a missing file is that test's own red, not a
sibling's (ADR-0037: a finding is a check). The properties are the five items
of #365; the code that turns them green lands on the same lane.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
MISSIONS = REPO / "tools" / "missions"


def _missions_module(name: str, item: str) -> types.ModuleType:
    path = MISSIONS / f"{name}.py"
    if not path.is_file():
        pytest.fail(f"tools/missions/{name}.py does not exist — #365 item {item}")
    spec = importlib.util.spec_from_file_location(f"missions_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def two_commit_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """A canonical clone with a parent and a child commit: (root, parent, child)."""
    root = tmp_path / "canonical"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "mod.py").write_text("def f():\n    return 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "parent")
    parent = _git(root, "rev-parse", "HEAD")
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text(
        "from mod import f\n\ndef test_f():\n    assert f() == 2\n"
    )
    (root / "mod.py").write_text("def f():\n    return 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "child: f returns 2 (#1)")
    child = _git(root, "rev-parse", "HEAD")
    return root, parent, child


# 1. Task loader — a tasks_admitted row becomes a worktree at the parent sha + the spec.


def test_task_loader_checks_out_the_parent_tree_and_refuses_an_unreachable_parent(
    two_commit_repo: tuple[Path, str, str], tmp_path: Path
) -> None:
    tasks = _missions_module("tasks", "1")
    root, parent, child = two_commit_repo
    row: dict[str, Any] = {
        "sha": child,
        "repo_root": str(root),
        "parents": parent,
        "spec": "f returns 2\n\nMake f() return 2.",
        "test_paths": "tests/test_mod.py",
        "reachable": 1,
    }
    task = tasks.Task.from_row(row)
    worktree = tasks.checkout(task, into=tmp_path / "wt")
    assert _git(worktree, "rev-parse", "HEAD") == parent
    assert (worktree / "mod.py").read_text() == "def f():\n    return 1\n"
    assert not (worktree / "tests" / "test_mod.py").exists(), (
        "the child's test is the acceptance, not the base"
    )
    assert task.spec.startswith("f returns 2")
    assert task.test_paths == ("tests/test_mod.py",)

    bad = tasks.Task.from_row({**row, "parents": "0" * 40})
    with pytest.raises(tasks.TaskError, match="0" * 40):
        tasks.checkout(bad, into=tmp_path / "wt2")


# 2. Live proposer — a reply is proposals or a recorded refusal, never an exception.


def test_live_proposer_parses_proposals_and_records_prose_as_refusal() -> None:
    propose = _missions_module("propose", "2")
    from mcgyvr.orchestrator.decompose import Proposal, Refusal

    reply = json.dumps(
        {
            "proposals": [
                {
                    "task_type": "function_impl",
                    "target": "mod.py",
                    "task": "make f return 2",
                    "interface": "def f() -> int",
                }
            ]
        }
    )
    out = propose.parse_proposals(reply)
    assert isinstance(out, list) and len(out) == 1 and isinstance(out[0], Proposal)
    assert out[0].target == "mod.py"

    prose = propose.parse_proposals("I think you should change f. Here is why: ...")
    assert isinstance(prose, Refusal), "prose is a refusal with a reason, not a crash"
    assert prose.reason


# 3. The attempt — the adapter's test command narrowed to the task's test paths.


def test_attempt_narrows_the_test_command_to_the_tasks_test_paths() -> None:
    attempt = _missions_module("attempt", "3")
    narrow = attempt.narrow_test_command
    assert narrow(["pytest"], ("tests/test_mod.py",)) == ["pytest", "tests/test_mod.py"]
    assert narrow(["npm", "test", "--"], ("src/a.test.ts",)) == [
        "npm",
        "test",
        "--",
        "src/a.test.ts",
    ]
    with pytest.raises(attempt.AttemptError, match="no test command"):
        attempt.narrow_test_command(None, ("tests/test_mod.py",))
    assert callable(attempt.make_attempt), "make_attempt(...) -> Callable[[Try], Judg.]"


# 4. The runner — no API fallback: a credentialed source is refused before any dispatch.


def test_runner_refuses_a_credentialed_source_before_dispatch(tmp_path: Path) -> None:
    run = _missions_module("run", "4")
    from mcgyvr import config as cfg

    local_only = cfg.parse(
        "version: 1\n"
        "sources:\n  srv2:\n    base_url: http://srv2:11434\n    api: openai\n"
        "ladder:\n  tiers:\n    - name: local_small\n      source: srv2\n"
        "      model: qwen2.5-coder:1.5b\n",
        path=tmp_path / "mcgyvr.yaml",
    )
    run.require_local_only(local_only)  # passes silently

    with_api = cfg.parse(
        "version: 1\n"
        "sources:\n  srv2:\n    base_url: http://srv2:11434\n    api: openai\n"
        "  cloud:\n    base_url: https://api.example.invalid\n    api: openai\n"
        "    api_key_env: EXAMPLE_KEY\n"
        "ladder:\n  tiers:\n    - name: local_small\n      source: srv2\n"
        "      model: qwen2.5-coder:1.5b\n"
        "    - name: api_big\n      source: cloud\n      model: big\n",
        path=tmp_path / "mcgyvr.yaml",
    )
    with pytest.raises(run.NoApiFallback, match="cloud"):
        run.require_local_only(with_api)

    assert run.record_dir(REPO, "abc123") == REPO / "records" / "missions" / "abc123"


# 5. The record — output and spec side by side, and no verdict the gate did not write.


def test_record_holds_output_beside_spec_and_refuses_a_foreign_verdict(
    tmp_path: Path,
) -> None:
    record = _missions_module("record", "5")
    where = tmp_path / "records" / "missions" / "abc123"
    record.write(
        where,
        identity={"model": "qwen2.5-coder:1.5b", "endpoint": "http://srv2:11434"},
        intent={"record": "run-header/1", "question": "does the pool reach the tests"},
        spec="f returns 2",
        output={
            "files": {"mod.py": "def f():\n    return 2\n"},
            "gate": {"accepted": True},
        },
    )
    got = record.read(where)
    assert got.spec == "f returns 2"
    assert got.output["files"]["mod.py"].endswith("return 2\n")
    assert "verdict" not in got.as_dict()

    payload = json.loads((where / "task.json").read_text())
    payload["verdict"] = "good"
    (where / "task.json").write_text(json.dumps(payload))
    with pytest.raises(record.VerdictNotTheGates, match="verdict"):
        record.read(where)
