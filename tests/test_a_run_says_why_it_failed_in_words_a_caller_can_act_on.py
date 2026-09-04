"""A run says why it failed, in words a caller can act on — and in a file.

The agent that types ``mcgyvr run`` has to decide what to do next: accept
the change, commit it, or write a different contract. Until now it was told
``the gate rejected the change on acceptance; no verifier was asked`` and no
more — the finding lines existed (``RetryNotes``) and went into the model's
retry prompt, never to the caller. A caller that cannot see why the gate
refused cannot replan; it can only try the same contract again.

Two channels, one content. On stdout, each failed attempt is followed by its
findings, one ``✗`` line each — the glyph the deterministic path already uses.
And every run writes one result file, ``<journal.dir>/results/<contract>-<utc
stamp>.json`` (``--result PATH`` overrides), and prints ``result: <path>`` so
the caller reads the file rather than the scrollback. A file, not a JSON dump
on stdout, by the owner's ruling: an agent's context is the scarce thing, and
a result it can ``grep`` costs nothing until it is opened.

The result names the contract, its type and target, the outcome word, the rung
that answered, every attempt with its verdict and findings, whether and where
it was committed, the orchestrator and session that drove it, and where the
journal rows are. Nothing lands in the user's repository.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests import livejournal as lj


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def test_a_rejected_climb_prints_its_findings_and_writes_them_to_the_result(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch, lj.BAD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 1
    out = capsys.readouterr().out
    path = lj.result_path(out)
    assert path.is_relative_to(journal / "results"), path
    result = json.loads(path.read_text())
    assert result["contract"] == "impl"
    assert result["task_type"] == "function_implementation"
    assert result["target"] == "src/pkg/messy.py"
    assert result["outcome"] == "ladder_spent"
    assert result["committed"] is False
    assert result["orchestrator"] == "claude-s1"
    assert result["session_file"].endswith("s1.jsonl")
    assert result["journal"] == str(journal)
    (attempt,) = result["attempts"]
    assert attempt["rung"] == "local_qwen-7b"
    assert attempt["verdict"] == "failed"
    assert attempt["attempt_id"] == f"claude-s1:{result['run']}:impl:local_qwen-7b:1"
    assert re.fullmatch(r"\d{8}T\d{6}\.\d{6}Z", result["run"]), result["run"]
    assert path.name == f"impl-{result['run']}.json"
    assert attempt["findings"], attempt
    for finding in attempt["findings"]:
        assert f"✗ {finding}" in out, (finding, out)
    assert not (repo / "results").exists()
    assert lj.git(repo, "status", "--porcelain").strip() == ""


def test_an_accepted_climb_writes_the_landing_to_the_result(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, "--commit"))

    assert code == 0
    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    head = lj.git(repo, "rev-parse", "HEAD").strip()
    assert result["outcome"] == "accepted"
    assert result["rung"] == "local_qwen-7b"
    assert result["committed"] is True
    assert result["commit"] == head
    assert result["exit_code"] == 0
    (attempt,) = result["attempts"]
    assert attempt["verdict"] == "passed"
    assert attempt["findings"] == []


def test_result_path_overrides_where_the_file_goes(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "j")
    contract = lj.make_contract(tmp_path / "impl.yaml")
    wanted = tmp_path / "elsewhere" / "r.json"

    code = lj.main(lj.run_args(contract, repo, config, "--result", str(wanted)))

    assert code == 0
    assert lj.result_path(capsys.readouterr().out) == wanted
    assert json.loads(wanted.read_text())["outcome"] == "accepted"


def test_a_refused_delivery_is_not_reported_as_accepted(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--commit`` on a dirty tree: the gate accepted, the tree got nothing."""
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    (repo / "src" / "pkg" / "other.py").write_text("y = 1\n", encoding="utf-8")
    lj.git(repo, "add", "src/pkg/other.py")
    lj.git(repo, "commit", "-q", "-m", "other")
    (repo / "src" / "pkg" / "other.py").write_text("y = 2\n", encoding="utf-8")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "j")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, "--commit"))

    assert code == 1
    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    assert result["outcome"] == "delivery_refused", result
    assert result["committed"] is False
    assert result["detail"], result
