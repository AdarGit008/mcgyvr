"""README.md shows the real `mcgyvr --help` usage and maps every command.

The README's usage block and its command map are copies of the parser's own
text, and a copy drifts silently: v0.3.0 shipped a usage line missing
`recommend`, `manage` and `mcorch`. Both are read here off `cli.build_parser`,
so a command added, renamed or re-described fails this test until the README
says the same.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from mcgyvr.cli import build_parser

README = Path(__file__).resolve().parent.parent / "README.md"


def _subcommands() -> list[argparse.Action]:
    parser = build_parser()
    sub = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return list(sub._choices_actions)


def test_the_readme_usage_block_is_the_real_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # argparse wraps to the terminal; the README block is the 80-column one.
    monkeypatch.setenv("COLUMNS", "80")
    usage = build_parser().format_usage()
    assert usage in README.read_text(encoding="utf-8"), usage


@pytest.mark.parametrize("action", _subcommands(), ids=lambda action: action.dest)
def test_the_readme_maps_each_command_with_its_help(action: argparse.Action) -> None:
    name = f"`{action.dest}`"
    assert isinstance(action.metavar, str), action.metavar
    aliases = action.metavar.removeprefix(action.dest).strip(" ()")
    if aliases:
        name += f" (`{aliases}`)"
    row = f"| {name} | {action.help} |"
    assert row in README.read_text(encoding="utf-8"), row
