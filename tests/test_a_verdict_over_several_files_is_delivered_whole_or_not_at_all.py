"""A verdict over several files lands as one change, or not at all.

The deterministic floor judges the sandbox's whole change, and a
``rename_symbol`` changes every file that references the symbol. Delivery used
to write back ``contract.target`` alone, so a rename of ``fetch_page`` left the
user's ``use.py`` importing a name ``web.py`` no longer defined, under a result
that said ``accepted`` (e2e run 2, R3).

So an :class:`~mcgyvr.deliver.Accepted` minted over several paths carries all
of them, and :func:`~mcgyvr.deliver.deliver` and :func:`~mcgyvr.deliver.place`
hold every one to every check — the contract's scope, a person's uncommitted
edit, the gate — and write and commit them together, in one commit, or write
nothing.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
from pathlib import Path

import pytest

from mcgyvr.config import parse
from mcgyvr.contract import Contract, loads
from mcgyvr.deliver import (
    Accepted,
    DeliveryError,
    DeliveryRefusedError,
    deliver,
    place,
)
from mcgyvr.gate import GateResult
from tests._helpers import git

CONTRACT = """
id: rename-fetch
task_type: code
operation: rename_symbol
task: Rename fetch_page to fetch_document.
target: src/pkg/web.py
rename:
  from: fetch_page
  to: fetch_document
scope:
  allow: ["src/pkg/**"]
"""

WEB = "def fetch_page(url):\n    return url\n"
USE = "from pkg.web import fetch_page\n\n\ndef go():\n    return fetch_page(1)\n"

RENAMED = {
    "src/pkg/web.py": "def fetch_document(url):\n    return url\n",
    "src/pkg/use.py": (
        "from pkg.web import fetch_document\n\n\ndef go():\n"
        "    return fetch_document(1)\n"
    ),
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    where = tmp_path / "repo"
    (where / "src/pkg").mkdir(parents=True)
    (where / "src/pkg/__init__.py").write_text("", encoding="utf-8")
    (where / "src/pkg/web.py").write_text(WEB, encoding="utf-8")
    (where / "src/pkg/use.py").write_text(USE, encoding="utf-8")
    (where / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "work", str(where))
    git(where, "config", "user.email", "test@example.invalid")
    git(where, "config", "user.name", "test")
    git(where, "add", "-A")
    git(where, "commit", "-qm", "base")
    return where


@pytest.fixture
def contract() -> Contract:
    return loads(CONTRACT)


def _judged(
    repo: Path, contract: Contract, changes: dict[str, str] | None = None
) -> Accepted:
    """The binding a floor run mints: off a copy of the tree the gate judged."""
    workspace = repo.parent / "workspace"
    shutil.copytree(repo, workspace)
    for path, text in (changes or RENAMED).items():
        (workspace / path).parent.mkdir(parents=True, exist_ok=True)
        (workspace / path).write_text(text, encoding="utf-8")
    return Accepted.read(
        repo=workspace,
        contract=contract,
        result=GateResult(),
        paths=sorted(changes or RENAMED),
    )


def _head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def _as_committed(repo: Path) -> dict[str, str]:
    return {
        "src/pkg/web.py": (repo / "src/pkg/web.py").read_text(encoding="utf-8"),
        "src/pkg/use.py": (repo / "src/pkg/use.py").read_text(encoding="utf-8"),
    }


# --- the binding --------------------------------------------------------------


def test_the_binding_carries_every_changed_file_with_the_target_first(
    repo: Path, contract: Contract
) -> None:
    bound = _judged(repo, contract)

    assert bound.path == "src/pkg/web.py", "the target leads when it changed"
    assert [path for path, _ in bound.files(contract)] == [
        "src/pkg/web.py",
        "src/pkg/use.py",
    ]
    assert dict(bound.files(contract)) == RENAMED
    assert bound.intact


def test_a_companion_whose_bytes_were_swapped_is_not_intact_and_is_refused(
    repo: Path, contract: Contract
) -> None:
    bound = _judged(repo, contract)
    (companion,) = bound.companions
    forged = dataclasses.replace(
        bound,
        companions=(dataclasses.replace(companion, content="import os\n"),),
    )

    assert not forged.intact
    result = deliver(repo=repo, contract=contract, content=forged, base=_head(repo))

    assert not result.committed
    assert "src/pkg/use.py" in result.reason
    assert _as_committed(repo) == {"src/pkg/web.py": WEB, "src/pkg/use.py": USE}


# --- delivered whole ------------------------------------------------------------


def test_commit_delivers_every_renamed_file_in_one_commit(
    repo: Path, contract: Contract
) -> None:
    head = _head(repo)

    result = deliver(
        repo=repo, contract=contract, content=_judged(repo, contract), base=head
    )

    assert result.committed, result.reason
    assert result.paths == ("src/pkg/web.py", "src/pkg/use.py")
    assert git(repo, "rev-parse", "HEAD~1").strip() == head, "more than one commit"
    shipped = git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(shipped) == ["src/pkg/use.py", "src/pkg/web.py"]
    assert git(repo, "status", "--porcelain") == ""
    assert _as_committed(repo) == RENAMED
    message = git(repo, "log", "-1", "--format=%B")
    assert "Files: src/pkg/web.py, src/pkg/use.py" in message
    assert "src/pkg/web.py, src/pkg/use.py" in str(result)


def test_a_branch_delivery_commits_every_file_onto_the_branch(
    repo: Path, contract: Contract
) -> None:
    head = _head(repo)
    config = parse(
        "units:\n  cheap:\n    address: http://localhost:11434\n"
        "    model: qwen2.5-coder:7b\n    rig: local\nladder:\n- cheap\n"
        "delivery:\n  mode: branch\n"
    )

    result = deliver(
        repo=repo,
        contract=contract,
        content=_judged(repo, contract),
        base=head,
        config=config,
    )

    assert result.committed, result.reason
    assert _head(repo) == head, "branch mode moved the checked-out branch"
    assert git(repo, "status", "--porcelain") == "", "the checkout was left dirty"
    shipped = git(repo, "show", "--name-only", "--format=", result.branch).split()
    assert sorted(shipped) == ["src/pkg/use.py", "src/pkg/web.py"]
    for path, text in RENAMED.items():
        assert git(repo, "show", f"{result.branch}:{path}") == text


def test_place_leaves_every_renamed_file_in_the_tree(
    repo: Path, contract: Contract
) -> None:
    head = _head(repo)

    place(repo=repo, contract=contract, content=_judged(repo, contract), base=head)

    assert _as_committed(repo) == RENAMED
    assert _head(repo) == head


# --- or not at all --------------------------------------------------------------


@pytest.mark.parametrize("commit", [False, True], ids=["place", "deliver"])
def test_a_dirty_file_that_is_not_the_target_refuses_and_nothing_is_written(
    repo: Path, contract: Contract, commit: bool
) -> None:
    """The refusal F11/F14 made for the target, made for every delivered file."""
    bound = _judged(repo, contract)
    edited = USE + "# a person's unfinished edit\n"
    (repo / "src/pkg/use.py").write_text(edited, encoding="utf-8")
    head = _head(repo)

    if commit:
        result = deliver(repo=repo, contract=contract, content=bound, base=head)
        assert not result.committed
        assert "src/pkg/use.py" in result.reason
    else:
        with pytest.raises(DeliveryError, match=re.escape("src/pkg/use.py")):
            place(repo=repo, contract=contract, content=bound, base=head)

    assert _as_committed(repo) == {"src/pkg/web.py": WEB, "src/pkg/use.py": edited}
    assert _head(repo) == head


@pytest.mark.parametrize("commit", [False, True], ids=["place", "deliver"])
def test_a_changed_file_outside_the_allowed_scope_refuses_before_anything_is_written(
    repo: Path, contract: Contract, commit: bool
) -> None:
    narrow = dataclasses.replace(
        contract, scope=dataclasses.replace(contract.scope, allow=("src/pkg/web.py",))
    )
    bound = _judged(repo, narrow)
    head = _head(repo)

    if commit:
        result = deliver(repo=repo, contract=narrow, content=bound, base=head)
        assert not result.committed
        reason = result.reason
    else:
        with pytest.raises(DeliveryRefusedError) as refused:
            place(repo=repo, contract=narrow, content=bound, base=head)
        reason = str(refused.value)

    assert "src/pkg/use.py is outside the scope rename-fetch declares" in reason
    assert "nothing was written" in reason
    assert _as_committed(repo) == {"src/pkg/web.py": WEB, "src/pkg/use.py": USE}
    assert _head(repo) == head


@pytest.mark.parametrize("commit", [False, True], ids=["place", "deliver"])
def test_one_file_the_gate_rejects_puts_every_file_back(
    repo: Path, contract: Contract, commit: bool
) -> None:
    """A refusal after the write restores all of them, and new directories go."""
    changes = {
        **RENAMED,
        "src/pkg/new/broken.py": "def oops(:\n",
    }
    bound = _judged(repo, contract, changes)
    head = _head(repo)

    if commit:
        result = deliver(repo=repo, contract=contract, content=bound, base=head)
        assert not result.committed
        assert result.findings, result.reason
    else:
        with pytest.raises(DeliveryRefusedError):
            place(repo=repo, contract=contract, content=bound, base=head)

    assert _as_committed(repo) == {"src/pkg/web.py": WEB, "src/pkg/use.py": USE}
    assert not (repo / "src/pkg/new").exists(), "a directory the write made stayed"
    assert git(repo, "status", "--porcelain") == ""
    assert _head(repo) == head


def test_a_file_committed_to_since_the_base_refuses_every_file(
    repo: Path, contract: Contract
) -> None:
    base = _head(repo)
    bound = _judged(repo, contract)
    (repo / "src/pkg/use.py").write_text(USE + "VALUE = 1\n", encoding="utf-8")
    git(repo, "commit", "-qam", "someone else")
    moved = _as_committed(repo)

    result = deliver(repo=repo, contract=contract, content=bound, base=base)

    assert not result.committed
    assert "src/pkg/use.py was committed to after the run started" in result.reason
    assert _as_committed(repo) == moved
