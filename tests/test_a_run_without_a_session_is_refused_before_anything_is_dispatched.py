"""A run without a session is refused before anything is dispatched.

Every row of the live journal names the orchestrator that produced it (§9),
and until now that name was whatever ``--orchestrator`` said or nothing at all:
a run without the flag journaled nothing, and a run with it could be traced to
a string and no further. The owner's ruling (2026-09-03) is that a run must
fail loud when nobody can be named, and that the name is a *session* — the
Claude Code or Pi transcript that typed the command — so a row can be followed
back to the full conversation that produced it.

Three ways to be named, in the order a process meets them: ``--orchestrator ID``
on the command line; ``CLAUDE_CODE_SESSION_ID``, which Claude Code exports to
every child process; ``PI_SESSION_FILE``, which a Pi extension exports on
session start. None of the three, and the run is refused through the
subparser's own ``error`` — exit 2, before a config is read or a sandbox is
opened — with a message that names all three so the operator does not have to
find them in ``--help``.

Two sessions at once is refused too, not guessed at. Claude Code can launch Pi
and Pi can launch Claude Code, and the environment does not say which one is
nearer; a wrong guess would file a whole conversation under the wrong agent,
and the flag is one word away.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import livejournal as lj


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    lj.clean_env(monkeypatch, tmp_path / "home")
    (tmp_path / "home").mkdir(exist_ok=True)
    return tmp_path / "home"


def test_no_flag_and_no_session_is_refused_naming_all_three_ways(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = lj.scripted(monkeypatch)  # nothing scripted: any dispatch is a failure
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 2, code
    err = capsys.readouterr().err
    for name in ("--orchestrator", "CLAUDE_CODE_SESSION_ID", "PI_SESSION_FILE"):
        assert name in err, err
    assert sent == [], "a refused run still dispatched"
    assert not journal.exists(), sorted(p.name for p in journal.iterdir())


def test_two_sessions_in_the_environment_is_refused_not_guessed(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent = lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    lj.claude_transcript(home, "c1")
    pi = lj.pi_transcript(home, "p1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "c1")
    monkeypatch.setenv("PI_SESSION_FILE", str(pi))

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 2, code
    err = capsys.readouterr().err
    assert "--orchestrator" in err, err
    assert sent == []
    assert not journal.exists()


def test_a_named_session_whose_transcript_does_not_exist_is_refused(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``claude-<id>`` claims a transcript; a claim nobody can check is refused."""
    sent = lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(
        lj.run_args(contract, repo, config, "--orchestrator", "claude-nowhere")
    )

    assert code == 2, code
    err = capsys.readouterr().err
    assert "claude-nowhere" in err, err
    assert sent == []
    assert not journal.exists()


def test_a_session_id_with_glob_characters_is_refused_not_matched(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``*`` in the id would match someone else's transcript and name no file."""
    sent = lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    lj.claude_transcript(home, "someone-else")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "*")

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 2, code
    assert "not a Claude Code session id" in capsys.readouterr().err
    assert sent == []
    assert not journal.exists()
