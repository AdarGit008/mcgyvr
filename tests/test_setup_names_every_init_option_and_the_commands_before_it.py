"""SETUP.md names every option `mcgyvr init` takes, and the commands before it.

SETUP.md is the first-run document: a machine's owner reads it before there is
a config. An `init` option it does not name is one that owner never learns
about, so the option list is read off the real parser (`cli.build_parser`),
not copied here. `mcgyvr scan` and `mcgyvr recommend` are the steps that
measure a machine and plan for it before `init` writes a config.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from mcgyvr.cli import build_parser

SETUP_MD = Path(__file__).resolve().parent.parent / "skills" / "mcgyvr" / "SETUP.md"


def _init_options() -> list[str]:
    parser = build_parser()
    sub = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    init = sub.choices["init"]
    return [
        option
        for action in init._actions
        for option in action.option_strings
        if option.startswith("--") and option != "--help"
    ]


def test_init_has_options_to_name() -> None:
    assert "--use-case" in _init_options()


@pytest.mark.parametrize("option", _init_options())
def test_setup_names_each_init_option(option: str) -> None:
    text = SETUP_MD.read_text(encoding="utf-8")
    assert f"`{option}" in text, f"SETUP.md does not name `mcgyvr init {option}`"


@pytest.mark.parametrize("command", ["mcgyvr scan", "mcgyvr recommend"])
def test_setup_names_the_steps_before_init(command: str) -> None:
    text = SETUP_MD.read_text(encoding="utf-8")
    assert command in text, f"SETUP.md does not name `{command}`"
