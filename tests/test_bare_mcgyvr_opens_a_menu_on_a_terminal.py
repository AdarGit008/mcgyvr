"""Bare `mcgyvr` opens a menu on a terminal, and keeps the usage error off one.

With no arguments on a tty, `mcgyvr` no longer fails with "command is required":
it opens the no-args menu, a mode of the one command, not a new verb. Off a
terminal — stdin or stdout not a tty — it keeps today's behaviour, the required
subcommand's usage error (exit 2), and never hangs waiting for input.
"""

from __future__ import annotations

import pytest

from mcgyvr.cli import menu
from mcgyvr.cli.dispatcher import build_parser, main
from tests import livejournal as lj


def test_menu_lists_each_command_once_with_aliases_dropped() -> None:
    commands = menu.menu_commands(build_parser())

    assert "capabilities" in commands
    assert "caps" not in commands, "an alias is one entry, not a second verb"
    assert {"setup", "scan", "emit", "serve", "use", "fleet"} <= set(commands)


def test_off_a_terminal_bare_mcgyvr_keeps_the_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(menu, "is_interactive", lambda: False)

    assert lj.main([]) == 2
    assert "required" in capsys.readouterr().err


def test_on_a_terminal_bare_mcgyvr_opens_the_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[tuple[object, object]] = []

    def fake_run(parser: object, main_fn: object) -> int:
        opened.append((parser, main_fn))
        return 0

    monkeypatch.setattr(menu, "is_interactive", lambda: True)
    monkeypatch.setattr(menu, "run", fake_run)

    assert main([]) == 0
    assert len(opened) == 1
    assert opened[0][0] is not None
    assert opened[0][1] is main


@pytest.mark.parametrize(
    ("said", "choice"),
    [("2", "b"), ("b", "b"), ("ch", "chat"), ("", "a")],
)
def test_pick_takes_number_name_prefix_and_default(
    monkeypatch: pytest.MonkeyPatch, said: str, choice: str
) -> None:
    asked: list[str] = []

    def prompt(question: str) -> str:
        asked.append(question)
        return said

    assert menu.pick("q", ("a", "b", "chat"), default="a", prompt=prompt) == choice
    assert asked == ["q"]


def test_pick_reasks_an_answer_that_names_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter(["nope", "a"])

    def prompt(question: str) -> str:
        return next(answers)

    assert menu.pick("q", ("a", "b"), prompt=prompt) == "a"
    assert "nope" in capsys.readouterr().out
