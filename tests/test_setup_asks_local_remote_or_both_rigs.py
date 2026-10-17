"""``mcgyvr setup`` asks which rigs serve as ``local``, ``remote`` or ``both``.

Owner, 2026-10-17: the rigs prompt accepted any token as a hostname, so a
stray ``no`` became an ssh host and the read failed with ``no scanner over
ssh``. It now asks one question that accepts exactly ``local``, ``remote``
or ``both`` (Enter is ``local``), and only ``remote``/``both`` ask again for
the ssh host(s), parsed the way the old prompt parsed them. A stray answer
is refused as a rig choice, never swallowed as a hostname.

These tests exercise the prompt seams directly; nothing reaches a machine.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import cli
from mcgyvr.cli.commands.setup import _ask_setup_rigs, _SetupInteractiveError

RIGS = "Which rig(s) should serve this setup? [local] "
REMOTE = "Remote rig(s) (ssh host or user@host): "


def _ask(answers: list[str]) -> tuple[list[str], Any]:
    """A scripted ``_ask``: record each question and answer in order."""
    asked: list[str] = []

    def fake(question: str, prompt: Any = None) -> str:
        asked.append(question)
        return answers.pop(0)

    return asked, fake


def test_enter_names_this_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    asked, fake = _ask([""])
    monkeypatch.setattr(cli.commands.setup, "_ask", fake)

    assert _ask_setup_rigs() == ("localhost",)
    assert asked == [RIGS]


def test_local_names_this_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    asked, fake = _ask(["local"])
    monkeypatch.setattr(cli.commands.setup, "_ask", fake)

    assert _ask_setup_rigs() == ("localhost",)
    assert asked == [RIGS]


def test_remote_asks_for_the_ssh_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    asked, fake = _ask(["remote", "box1, box2"])
    monkeypatch.setattr(cli.commands.setup, "_ask", fake)

    assert _ask_setup_rigs() == ("box1", "box2")
    assert asked == [RIGS, REMOTE]


def test_both_is_this_machine_plus_the_ssh_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked, fake = _ask(["both", "box1 box2"])
    monkeypatch.setattr(cli.commands.setup, "_ask", fake)

    assert _ask_setup_rigs() == ("localhost", "box1", "box2")
    assert asked == [RIGS, REMOTE]


def test_remote_reasks_until_a_host_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked, fake = _ask(["remote", "", "box1"])
    monkeypatch.setattr(cli.commands.setup, "_ask", fake)

    assert _ask_setup_rigs() == ("box1",)
    assert asked == [RIGS, REMOTE, REMOTE]


def test_a_remote_that_names_no_host_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked, fake = _ask(["remote", "", "", ""])
    monkeypatch.setattr(cli.commands.setup, "_ask", fake)

    with pytest.raises(_SetupInteractiveError):
        _ask_setup_rigs()
    assert asked == [RIGS, REMOTE, REMOTE, REMOTE]


def test_a_stray_answer_is_refused_not_swallowed_as_a_hostname(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked, fake = _ask(["no", "local"])
    monkeypatch.setattr(cli.commands.setup, "_ask", fake)

    assert _ask_setup_rigs() == ("localhost",)
    assert asked == [RIGS, RIGS], "the stray answer re-asks the choice, never a host"
    assert "no" in capsys.readouterr().out
