"""A target whose base moved under the run is refused, not overwritten.

The sandbox is ``git archive`` of the source's HEAD at open, and a climb can
take minutes. ``place`` — what a run does by default — asked git one thing
only: whether the target had uncommitted changes. A user who *committed* to
the target during the climb had a clean tree, so the accepted bytes, judged
against the old copy, were written over the new one with exit 0 and nothing
in the result saying the base had moved. ``deliver`` diffs against the base
the worker started from and takes the repository's delivery lock; ``place``
now does both, and refuses in the same words for the same reason.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.contract import load
from mcgyvr.deliver import Accepted, DeliveryError, place
from mcgyvr.gate import GateResult
from tests import livejournal as lj


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def _accepted(repo: Path, contract: Any, text: str) -> Accepted:
    """An `Accepted` minted the only way one can be: read off a tree."""
    (repo / contract.target).write_text(text, encoding="utf-8")
    bound = Accepted.read(repo=repo, contract=contract, result=GateResult())
    lj.git(repo, "checkout", "--", contract.target)
    return bound


def _commit_edit(repo: Path, rel: str, text: str) -> str:
    (repo / rel).write_text(text, encoding="utf-8")
    lj.git(repo, "add", "-A")
    lj.git(repo, "commit", "-q", "-m", "the user moved on")
    return lj.git(repo, "rev-parse", "HEAD").strip()


def test_place_refuses_when_the_target_changed_between_base_and_head(
    tmp_path: Path,
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    bound = _accepted(repo, contract, "VALUE = 1\n")
    _commit_edit(repo, contract.target, "x = 2  # the user's own edit\n")

    with pytest.raises(DeliveryError, match=base[:12]) as refused:
        place(repo=repo, contract=contract, content=bound, base=base)

    assert contract.target in str(refused.value)
    assert (repo / contract.target).read_text() == "x = 2  # the user's own edit\n"


def test_place_writes_when_only_other_files_moved(tmp_path: Path) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    base = lj.git(repo, "rev-parse", "HEAD").strip()
    bound = _accepted(repo, contract, "VALUE = 1\n")
    _commit_edit(repo, "README", "unrelated\n")

    written = place(repo=repo, contract=contract, content=bound, base=base)

    assert written.read_text() == "VALUE = 1\n"


def test_place_refuses_an_empty_base(tmp_path: Path) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))
    bound = _accepted(repo, contract, "VALUE = 1\n")

    with pytest.raises(DeliveryError, match="empty base"):
        place(repo=repo, contract=contract, content=bound, base="")
    assert (repo / contract.target).read_text() == "x = 0\n"


def test_a_run_whose_base_moved_is_delivery_refused_and_leaves_the_users_commit(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The user commits to the target while the model is answering."""
    import mcgyvr.drive as drive

    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    scripted = lj.scripted(monkeypatch, lj.GOOD_REPLY)
    real_dispatch: Any = drive.dispatch  # type: ignore[attr-defined]  # scripted above
    moved: list[str] = []

    def dispatch_while_the_user_commits(*args: Any, **kwargs: Any) -> Any:
        moved.append(_commit_edit(repo, "src/pkg/messy.py", "x = 2\n"))
        return real_dispatch(*args, **kwargs)

    monkeypatch.setattr(drive, "dispatch", dispatch_while_the_user_commits)

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 1
    assert scripted, "the model was asked"
    assert (repo / "src/pkg/messy.py").read_text() == "x = 2\n"
    assert lj.git(repo, "status", "--porcelain") == ""
    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    assert result["outcome"] == "delivery_refused", result
    assert moved[0][:12] in result["detail"] or "moved" in result["detail"], result
