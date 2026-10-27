"""A run's session is named with ``--session``; ``--orchestrator`` still works, warned.

The word "orchestrator" belongs to the configured role that drafts contracts
for ``mcgyvr delegate``. The id of the conversation that typed a command is its
*session*, so the flag that names it is ``--session ID`` and the result file
carries it as ``session``. ``--orchestrator ID`` was that flag's name and stays
for one release as a deprecated alias: it still names the session, and says on
stderr what to pass instead. The result file still carries the old
``orchestrator`` key, with the same value, for the same release.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj

FORMAT = """
id: tidy
task_type: code
operation: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""


def test_session_names_the_journal_and_the_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.clean_env(monkeypatch, tmp_path / "home")
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    code = lj.main(lj.run_args(contract, repo, config, "--session", "agent-a"))

    out = capsys.readouterr()
    assert code == 0, out.err
    assert "deprecated" not in out.err, out.err
    assert (journal / "agent-a.jsonl").is_file()
    result = json.loads(lj.result_path(out.out).read_text(encoding="utf-8"))
    assert result["session"] == "agent-a"
    # The old key, kept for one release with the same value.
    assert result["orchestrator"] == "agent-a"


def test_the_old_flag_still_names_the_session_and_says_it_is_deprecated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.clean_env(monkeypatch, tmp_path / "home")
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    code = lj.main(lj.run_args(contract, repo, config, "--orchestrator", "agent-b"))

    out = capsys.readouterr()
    assert code == 0, out.err
    assert "--orchestrator is deprecated" in out.err, out.err
    assert "--session agent-b" in out.err, out.err
    assert (journal / "agent-b.jsonl").is_file()
    result = json.loads(lj.result_path(out.out).read_text(encoding="utf-8"))
    assert result["session"] == "agent-b"


def test_delegate_takes_both_spellings_into_the_same_place(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli.dispatcher import build_parser

    parser = build_parser()
    new = parser.parse_args(["delegate", "do it", "--session", "agent-c"])
    assert new.session_id == "agent-c"
    assert "deprecated" not in capsys.readouterr().err

    old = parser.parse_args(["delegate", "do it", "--orchestrator", "agent-d"])
    assert old.session_id == "agent-d"
    assert "--orchestrator is deprecated" in capsys.readouterr().err
