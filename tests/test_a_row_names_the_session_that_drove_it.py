"""A row names the session that drove it.

The orchestrator id on a journal row is derived from the session that typed
the command, and the row carries the transcript's path as ``session_file`` so
the full conversation behind any attempt is one ``open`` away. Claude Code
exports ``CLAUDE_CODE_SESSION_ID`` and keeps the transcript at
``~/.claude/projects/<cwd-slug>/<id>.jsonl`` (``CLAUDE_CONFIG_DIR`` moves the
root); Pi keeps ``~/.pi/agent/sessions/<cwd-slug>/<stamp>_<id>.jsonl`` and a
Pi extension exports that path as ``PI_SESSION_FILE``. The id is
``claude-<id>`` or ``pi-<id>``: a dash, not a colon, because the id is the
journal's file name and the prefix of every ``attempt_id``.

An explicit ``--orchestrator`` still wins, verbatim, and an id that does not
claim a transcript carries no ``session_file`` — absent, not null, under the
rule that keeps an unreported token count out of the row.

``task_type`` rides on the row too. A feedback loop that wants to say "this
rung passes bug fixes and fails implementations" needs the type beside the
verdict, and the contract id alone does not say it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.telemetry import fold
from tests import livejournal as lj


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    return tmp_path / "home"


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> Path:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    code = lj.main(lj.run_args(contract, repo, config, *extra))
    assert code == 0, code
    return journal


def test_a_claude_session_names_the_row_and_its_transcript(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = lj.claude_transcript(home, "f438133f-0000-4c33-92f0-31f43d9dd3b6")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "f438133f-0000-4c33-92f0-31f43d9dd3b6")

    journal = _run(tmp_path, monkeypatch)

    sink = journal / "claude-f438133f-0000-4c33-92f0-31f43d9dd3b6.jsonl"
    assert sink.is_file(), sorted(p.name for p in journal.iterdir())
    (row,) = fold(path=sink)
    assert row["orchestrator"] == "claude-f438133f-0000-4c33-92f0-31f43d9dd3b6"
    assert row["session_file"] == str(transcript)
    assert row["task_type"] == "function_implementation"
    assert row["attempt_id"].startswith("claude-f438133f-0000-4c33-92f0-31f43d9dd3b6:")
    assert ":impl:local_qwen-7b:1" in row["attempt_id"]


def test_a_claude_config_dir_moves_where_the_transcript_is_looked_for(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    project = elsewhere / "projects" / "-x"
    project.mkdir(parents=True)
    transcript = project / "abc.jsonl"
    transcript.write_text("{}\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(elsewhere))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")

    journal = _run(tmp_path, monkeypatch)

    (row,) = fold(path=journal / "claude-abc.jsonl")
    assert row["session_file"] == str(transcript)


def test_a_pi_session_names_the_row_and_its_transcript(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = lj.pi_transcript(home, "01a065ec-33df-7279-8af7-a2801bc99751")
    monkeypatch.setenv("PI_SESSION_FILE", str(transcript))

    journal = _run(tmp_path, monkeypatch)

    sink = journal / "pi-01a065ec-33df-7279-8af7-a2801bc99751.jsonl"
    assert sink.is_file(), sorted(p.name for p in journal.iterdir())
    (row,) = fold(path=sink)
    assert row["orchestrator"] == "pi-01a065ec-33df-7279-8af7-a2801bc99751"
    assert row["session_file"] == str(transcript)


def test_an_explicit_orchestrator_wins_verbatim_and_claims_no_transcript(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.claude_transcript(home, "c1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "c1")

    journal = _run(tmp_path, monkeypatch, "--orchestrator", "agent-a")

    (row,) = fold(path=journal / "agent-a.jsonl")
    assert row["orchestrator"] == "agent-a"
    assert "session_file" not in row, row


def test_an_explicit_claude_id_is_resolved_to_its_transcript(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transcript = lj.claude_transcript(home, "c2")

    journal = _run(tmp_path, monkeypatch, "--orchestrator", "claude-c2")

    (row,) = fold(path=journal / "claude-c2.jsonl")
    assert row["session_file"] == str(transcript)
