"""`mcgyvr PROMPT` and `mcgyvr direct` take one flag set; `run` and `delegate` are gone.

The two verbs differ only in who wrote the contracts, so every flag is on
both, with one help text, read off the parsers themselves. A flag with no
meaning on one side is refused there, exit 2, before anything is asked or
run, never dropped or read as nothing. `run`, `delegate` and the old
`--orchestrator` spelling of `--session` are gone with no alias: typing one
spends nothing and says what took its place.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from mcgyvr.cli.dispatcher import _build, _commands
from tests import livejournal as lj

#: The one flag set, as the brief of the two verbs names it.
FLAGS = {
    "--jobs",
    "--output",
    "--into",
    "--budget",
    "--log",
    "--notes-from",
    "--result",
    "--branch",
    "--commit",
    "--no-commit",
    "--config",
    "--record",
    "--sandbox",
    "--session",
    "--repo",
    "-h",
    "--help",
}


def options(parser: argparse.ArgumentParser) -> dict[str, str | None]:
    """Every option string `parser` takes, with its help."""
    return {
        flag: action.help
        for action in parser._actions
        for flag in action.option_strings
    }


def test_both_verbs_take_the_same_flags_with_the_same_help() -> None:
    _, prompt, direct = _build()

    assert set(options(prompt)) == set(options(direct)) == FLAGS
    assert options(prompt) == options(direct)


def test_each_flag_with_no_meaning_on_one_side_says_so_in_its_help() -> None:
    _, prompt, _ = _build()
    said = options(prompt)

    assert "No meaning under `direct`" in str(said["--budget"])
    assert "Refused for a prompt" in str(said["--notes-from"])
    assert "for a prompt" in str(said["--result"])


def test_run_and_delegate_are_no_commands_and_spend_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser, _, _ = _build()
    assert {"run", "delegate"}.isdisjoint(_commands(parser))
    assert "direct" in _commands(parser)

    assert lj.main(["run", "contract.yaml"]) == 2
    assert "`mcgyvr direct FILE...`" in capsys.readouterr().err
    assert lj.main(["delegate", "Fix listing.", "--run"]) == 2
    assert "`mcgyvr PROMPT`" in capsys.readouterr().err


def test_the_old_session_spelling_is_gone(tmp_path: Path) -> None:
    _, prompt, direct = _build()
    for parser in (prompt, direct):
        assert "--orchestrator" not in options(parser)
    assert lj.main(["direct", str(tmp_path), "--orchestrator", "s1"]) == 2


def test_one_word_close_to_a_command_is_taken_for_a_typo_not_a_prompt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert lj.main(["fleeet"]) == 2
    assert "did you mean `mcgyvr fleet`" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (
            ["Fix listing.", "--result", "r.json"],
            "--result has no meaning for a prompt",
        ),
        (
            ["Fix listing.", "--notes-from", "r.json"],
            "--notes-from has no meaning for a prompt",
        ),
        (["direct", "{folder}", "--budget", "100"], "--budget has no meaning"),
        (["direct", "{folder}", "--result", "r.json"], "--result names one file"),
        (["direct", "{folder}/nowhere.yaml"], "is not there"),
        (["direct", "{empty}"], "holds no contract file"),
    ],
)
def test_a_flag_or_path_that_cannot_be_honoured_is_refused_exit_2(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    said: str,
) -> None:
    lj.clean_env(monkeypatch, home)
    folder, empty = tmp_path / "contracts", tmp_path / "empty"
    folder.mkdir()
    empty.mkdir()
    for name in ("a", "b"):
        (folder / f"{name}.yaml").write_text("id: x\n")
    argv = [a.format(folder=folder, empty=empty) for a in argv]

    assert lj.main([*argv, "--session", "s1"]) == 2
    assert said in capsys.readouterr().err
