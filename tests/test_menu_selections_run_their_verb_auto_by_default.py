"""The menu's per-verb selections run their verb, defaulting to auto.

The no-args menu drives the existing verbs: `setup` asks whether to run the
full pipeline (auto, the default) or stop at a stage, `emit` defaults to
writing and offers `--check` as the stop-early manual, and `serve` picks a
direction and the rig. None of these is a new verb — they call the existing
command handlers.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr.cli import menu
from mcgyvr.cli.commands import setup as setup_cmd


def _returns(monkeypatch: pytest.MonkeyPatch, *said: str) -> None:
    answers = iter(said)
    monkeypatch.setattr(menu, "pick", lambda *a, **k: next(answers))


def test_setup_defaults_to_auto_and_runs_the_full_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(setup_cmd, "run_menu_setup", lambda **kw: calls.append(kw) or 0)
    monkeypatch.setattr(menu, "pick", lambda *a, **k: "auto")

    assert menu._setup_menu(lambda argv: 0) == 0
    assert calls == [{"auto": True, "stop": None}]


def test_setup_manual_picks_a_stage_and_stops_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(setup_cmd, "run_menu_setup", lambda **kw: calls.append(kw) or 0)
    answers = iter(["manual", "start"])
    monkeypatch.setattr(menu, "pick", lambda *a, **k: next(answers))

    assert menu._setup_menu(lambda argv: 0) == 0
    assert calls == [{"auto": False, "stop": "start"}]


def test_emit_defaults_to_writing_and_offers_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def main(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    _returns(monkeypatch, "check")
    assert menu._emit_menu(main) == 0
    assert seen == [["emit", "--check"]]

    _returns(monkeypatch, "write")
    assert menu._emit_menu(main) == 0
    assert seen[1] == ["emit"]


def test_serve_picks_a_direction_and_the_rig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def main(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    monkeypatch.setattr(menu, "pick", lambda *a, **k: "sleep")
    monkeypatch.setattr("builtins.input", lambda question="": "box1")

    assert menu._serve_menu(main) == 0
    assert seen == [["serve", "sleep", "--host", "box1"]]


def test_a_generic_verb_with_subcommands_is_a_nested_pick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def main(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    monkeypatch.setattr(menu, "pick", lambda *a, **k: "status")

    from mcgyvr.cli.dispatcher import build_parser

    assert menu._dispatch("rig", build_parser(), main) == 0
    assert seen == [["rig", "status"]]
