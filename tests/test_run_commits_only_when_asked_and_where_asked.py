"""``mcgyvr run`` commits only when asked, and onto the branch it was asked for.

Two policy keys and three flags:

* ``delivery.commit`` — off by default, and written off by ``mcgyvr setup``.
  Off, an accepted change is left in the working tree, uncommitted. On, it is
  committed onto the branch you have checked out.
* ``delivery.branch`` — commit onto this branch instead. It says *where*, not
  *whether*: it commits nothing while ``commit`` is off.
* ``--commit`` / ``--no-commit`` override ``delivery.commit`` for one run, and
  ``--branch NAME`` overrides ``delivery.branch`` and implies ``--commit``.

What a named branch does when it exists, is absent or is checked out is
delivery's, and pinned in
``tests/test_a_commit_lands_on_the_branch_it_was_sent_to.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse
from tests import livejournal as lj

LADDER = """\
units:
  cheap:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: local
    window: 32768
ladder:
- cheap
"""


def _heads(repo: Path) -> set[str]:
    listed = lj.git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return set(listed.split())


def _checked_out(repo: Path) -> str:
    return lj.git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def _rev(repo: Path, name: str) -> str:
    return lj.git(repo, "rev-parse", name).strip()


def _result(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return dict(json.loads(lj.result_path(capsys.readouterr().out).read_text()))


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *flags: str,
    policy: str = "",
) -> tuple[int, Path, str, dict[str, Any]]:
    """One accepted run; the exit code, the repo, its starting HEAD, the result."""
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    head = _rev(repo, "HEAD")
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    if policy:
        lj.append_policy(config, policy)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, *flags))

    return code, repo, head, _result(capsys)


def _left_uncommitted(repo: Path, head: str, result: dict[str, Any]) -> None:
    assert result["committed"] is False, result
    assert _rev(repo, "HEAD") == head, "a commit was made"
    assert _heads(repo) == {_checked_out(repo)}, f"a branch was made: {_heads(repo)}"
    assert "VALUE = 1" in (repo / "src/pkg/messy.py").read_text(), (
        "the accepted change is not in the working tree"
    )


def _committed_here(repo: Path, head: str, result: dict[str, Any]) -> None:
    assert result["committed"] is True, result
    assert _rev(repo, "HEAD") == result["commit"], "not on the checked-out branch"
    assert _rev(repo, "HEAD~1") == head
    assert _heads(repo) == {_checked_out(repo)}, f"a branch was made: {_heads(repo)}"
    assert not lj.git(repo, "status", "--porcelain").strip()


def _committed_on(repo: Path, head: str, result: dict[str, Any], branch: str) -> None:
    assert result["committed"] is True, result
    assert result["branch"] == branch, result
    assert _rev(repo, branch) == result["commit"], f"the commit is not on {branch}"
    assert _rev(repo, f"{branch}~1") == head, f"{branch} did not start at HEAD"
    assert _rev(repo, "HEAD") == head, "the checked-out branch moved"
    assert _checked_out(repo) != branch, "delivery switched the checkout"
    assert (repo / "src/pkg/messy.py").read_text() == "x = 0\n"
    assert not lj.git(repo, "status", "--porcelain").strip()


# --- the policy: commit is off unless it is turned on -------------------------


def test_the_default_policy_commits_nothing(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, repo, head, result = _run(tmp_path, monkeypatch, capsys)

    assert code == 0, result
    _left_uncommitted(repo, head, result)


def test_the_schema_default_is_commit_off_onto_the_checked_out_branch() -> None:
    config = parse(LADDER)
    assert config.get("delivery.commit") is False
    assert config.get("delivery.branch") is None


def test_setup_writes_commit_off_into_policy_yaml() -> None:
    from mcgyvr.detect import Detection
    from mcgyvr.initialize import build, render_policy
    from mcgyvr.propose import Proposal

    text = render_policy(build(Detection(), Proposal()))

    delivery = text[text.index("\ndelivery:") :]
    assert "\n  commit: false\n" in delivery, delivery[:1200]
    assert "\n  # branch:" in delivery, "the branch key is not shown to be set"


def test_policy_commit_on_commits_onto_the_checked_out_branch(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, repo, head, result = _run(
        tmp_path, monkeypatch, capsys, policy="delivery:\n  commit: true\n"
    )

    assert code == 0, result
    _committed_here(repo, head, result)


def test_policy_branch_receives_the_commit_and_the_checkout_stays(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, repo, head, result = _run(
        tmp_path,
        monkeypatch,
        capsys,
        policy="delivery:\n  commit: true\n  branch: mcgyvr-x\n",
    )

    assert code == 0, result
    _committed_on(repo, head, result, "mcgyvr-x")
    assert "mcgyvr-x" in result["handoff"], result["handoff"]


def test_policy_branch_alone_does_not_turn_commit_on(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, repo, head, result = _run(
        tmp_path, monkeypatch, capsys, policy="delivery:\n  branch: mcgyvr-x\n"
    )

    assert code == 0, result
    _left_uncommitted(repo, head, result)


# --- the flags override the policy for one run --------------------------------


def test_commit_flag_commits_onto_the_checked_out_branch(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, repo, head, result = _run(tmp_path, monkeypatch, capsys, "--commit")

    assert code == 0, result
    _committed_here(repo, head, result)


def test_commit_flag_with_a_policy_branch_commits_onto_that_branch(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, repo, head, result = _run(
        tmp_path,
        monkeypatch,
        capsys,
        "--commit",
        policy="delivery:\n  branch: mcgyvr-x\n",
    )

    assert code == 0, result
    _committed_on(repo, head, result, "mcgyvr-x")


def test_branch_flag_overrides_the_policy_branch_and_implies_commit(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, repo, head, result = _run(
        tmp_path,
        monkeypatch,
        capsys,
        "--branch",
        "mcgyvr-y",
        policy="delivery:\n  branch: mcgyvr-x\n",
    )

    assert code == 0, result
    _committed_on(repo, head, result, "mcgyvr-y")
    assert "mcgyvr-x" not in _heads(repo), "the policy's branch was used as well"


def test_no_commit_flag_overrides_policy_commit_on(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, repo, head, result = _run(
        tmp_path,
        monkeypatch,
        capsys,
        "--no-commit",
        policy="delivery:\n  commit: true\n  branch: mcgyvr-x\n",
    )

    assert code == 0, result
    _left_uncommitted(repo, head, result)


def test_branch_and_no_commit_together_are_refused_as_a_contradiction(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    head = _rev(repo, "HEAD")
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, "--branch", "y", "--no-commit"))

    assert code == 2, "a contradiction on the command line is a usage error"
    err = capsys.readouterr().err
    assert "--branch" in err and "--no-commit" in err, err
    assert _rev(repo, "HEAD") == head
    assert (repo / "src/pkg/messy.py").read_text() == "x = 0\n"


def test_a_blank_branch_flag_is_refused_rather_than_read_as_none(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, "--branch", " "))

    assert code == 2
    assert "--branch" in capsys.readouterr().err
