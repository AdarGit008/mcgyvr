"""``delegate --run`` names its session before the orchestrator role is asked.

The session (``mcgyvr.session``) is who typed the command, and every run a
batch makes is filed under it. ``mcgyvr run`` resolves it before any work and
refuses with exit 2 when nobody can be named. ``delegate --run`` used to
resolve it only after the role had been asked and the contracts written, so a
batch nobody could be traced to still cost a model call and left contracts
behind, and said so with exit 1. Now it is named first, through the same check
``run`` makes: exit 2, no proposer built, nothing written to ``--output``.
Without ``--run`` nothing is filed, so no session is asked for.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.cli.commands import delegate as command
from tests import livejournal as lj


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every time the orchestrator role would have been built to be asked."""
    calls: list[Any] = []

    def spy(config: Any, pool: Any) -> None:
        calls.append(config)

    monkeypatch.setattr(command, "_proposer_for_delegate", spy)
    return calls


def _delegate(tmp_path: Path, *extra: str) -> list[str]:
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr")
    return [
        "delegate",
        "Set VALUE to 1.",
        "--repo",
        str(repo),
        "--config",
        str(config),
        "--output",
        str(tmp_path / "contracts"),
        *extra,
    ]


def test_no_session_is_refused_before_the_role_is_asked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asked: list[Any],
) -> None:
    lj.clean_env(monkeypatch, tmp_path / "home")

    code = lj.main(_delegate(tmp_path, "--run"))

    assert code == 2, code
    err = capsys.readouterr().err
    assert "--session" in err, err
    assert "mcgyvr delegate" in err, err  # refused by delegate's own parser
    assert asked == [], "the orchestrator role was asked for a batch nobody typed"
    assert not (tmp_path / "contracts").exists()


def test_a_blank_session_is_refused_the_way_run_refuses_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asked: list[Any],
) -> None:
    lj.clean_env(monkeypatch, tmp_path / "home")

    code = lj.main(_delegate(tmp_path, "--run", "--session", " "))

    assert code == 2, code
    assert "--session was given an empty id" in capsys.readouterr().err
    assert asked == []
    assert not (tmp_path / "contracts").exists()


def test_without_run_no_session_is_asked_for(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    asked: list[Any],
) -> None:
    lj.clean_env(monkeypatch, tmp_path / "home")

    code = lj.main(_delegate(tmp_path))

    # The stand-in builds no proposer, so this is the no-role refusal, reached
    # past the point a session would have been demanded.
    assert code == 3, capsys.readouterr().err
    assert len(asked) == 1
