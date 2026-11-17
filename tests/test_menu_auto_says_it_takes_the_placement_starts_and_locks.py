"""The menu's auto says what it does without asking, before it is chosen and as it runs.

Auto answers three questions for the user: it takes the recommended
placement, starts the servers and locks the fleet live. The menu's setup
prompt names all three, and the wizard's opening line under auto says so
instead of "on your yes". Without auto the opening line is unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr.cli import menu
from mcgyvr.cli.commands import setup as setup_cmd
from mcgyvr.cli.commands.setup import run_menu_setup
from tests import setup_door as sd

USE_CASE = "Use case — [m] mcgyvr-code, [k] code, [c] chat, [a] agent: "

TODAYS_OPENING = (
    "Read each rig, plan a model per rig, then start and sample a fleet and "
    "lock it live on your yes."
)


def test_the_menu_prompt_names_the_placement_the_start_and_the_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    questions: list[str] = []

    def pick(question: str, *a: Any, **k: Any) -> str:
        questions.append(question)
        return "auto"

    monkeypatch.setattr(menu, "pick", pick)
    monkeypatch.setattr(setup_cmd, "run_menu_setup", lambda **kw: 0)

    assert menu._setup_menu(lambda argv: 0) == 0
    (prompt,) = questions
    assert "[auto]" in prompt and "[manual]" in prompt
    for word in ("placement", "starts the servers", "locks the fleet live"):
        assert word in prompt
    assert "without asking" in prompt


def test_the_opening_line_under_auto_says_it_does_not_ask(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sd.interactive(monkeypatch, sd.FakeRig(), {}, typed={USE_CASE: "m"})

    assert run_menu_setup(auto=True, stop=None) == 0

    out = capsys.readouterr().out
    assert setup_cmd.AUTO_OPENING in out
    assert "on your yes" not in out
    for word in ("placement", "starts the servers", "locks the fleet live"):
        assert word in setup_cmd.AUTO_OPENING


def test_the_opening_line_without_auto_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sd.interactive(monkeypatch, sd.FakeRig(), {}, typed={USE_CASE: "m"})

    assert run_menu_setup(auto=False, stop="config") == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[lines.index("mcgyvr setup") + 1] == TODAYS_OPENING
    assert setup_cmd.OPENING == TODAYS_OPENING
