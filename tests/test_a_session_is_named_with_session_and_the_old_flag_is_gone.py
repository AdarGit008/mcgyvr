"""A run's session is named with ``--session``; ``--orchestrator`` is gone.

The word "orchestrator" belongs to the configured role that drafts contracts
for ``mcgyvr PROMPT``. The id of the conversation that typed a command is its
*session*, so the flag that names it is ``--session ID`` and the result file
carries it as ``session``. ``--orchestrator ID`` was that flag's old name; it is
refused now, on ``mcgyvr direct`` and on the bare verb alike, with no alias.
The result file still carries the old ````orchestrator`` key, with the same value.
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
    assert (journal / "agent-a.jsonl").is_file()
    result = json.loads(lj.result_of(contract).read_text(encoding="utf-8"))
    assert result["session"] == "agent-a"
    # The old key, kept for one release with the same value.
    assert result["orchestrator"] == "agent-a"


def test_the_old_flag_is_refused_by_direct_and_spends_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.clean_env(monkeypatch, tmp_path / "home")
    calls = lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    code = lj.main(lj.run_args(contract, repo, config, "--orchestrator", "agent-b"))

    assert code == 2
    assert calls == []
    assert not journal.exists() or not list(journal.glob("*.jsonl"))
    assert not lj.result_of(contract).exists()


def test_the_bare_verb_refuses_the_old_flag_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli.dispatcher import main

    with pytest.raises(SystemExit) as exit_:
        main(["do it", "--orchestrator", "agent-d"])

    assert exit_.value.code == 2


def test_the_bare_verb_takes_session_into_the_same_place_direct_does() -> None:
    from mcgyvr.cli.dispatcher import _build

    _, prompt, directing = _build()
    assert prompt.parse_args(["do it", "--session", "agent-c"]).session_id == "agent-c"
    direct = directing.parse_args(["c.yaml", "--session", "agent-c"])
    assert direct.session_id == "agent-c"
