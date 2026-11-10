"""SETUP.md lists every verb and flag the `mcgyvr` parser defines.

The parser is the one truth of what the CLI takes, and SETUP.md's *Commands*
is rendered from it: every verb (aliases too) and every flag `-h` shows is
named there, a verb with its help line and a flag with its own, so a verb or
flag added to the parser is in the document on the next `make docs` and the
drift check fails until it is. `direct`'s flags are the skills' to explain:
they are named and pointed at, never restated. Hidden flags stay hidden.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator

import pytest

from mcgyvr import docgen
from mcgyvr.cli.dispatcher import build_parser
from tests._paths import REPO

SETUP_MD = REPO / "skills" / "mcgyvr" / "SETUP.md"


def _commands(text: str) -> str:
    start = text.index("## Commands\n")
    return text[start : text.index("\n## ", start + 1)]


def _tree(
    parser: argparse.ArgumentParser, path: str = "mcgyvr"
) -> Iterator[tuple[str, argparse.ArgumentParser]]:
    """Every (verb name, parser) the tree holds, aliases included."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, child in action.choices.items():
                yield f"{path} {name}", child
                yield from _tree(child, f"{path} {name}")


def _flags(parser: argparse.ArgumentParser) -> list[str]:
    return [
        name
        for action in parser._actions
        if action.option_strings
        and not isinstance(action, argparse._HelpAction)
        and action.help != argparse.SUPPRESS
        for name in action.option_strings
    ]


@pytest.fixture(scope="module")
def commands() -> str:
    return _commands(SETUP_MD.read_text(encoding="utf-8"))


def test_every_verb_and_alias_the_parser_defines_is_named(commands: str) -> None:
    missing = []
    for verb, _parser in _tree(build_parser()):
        name = verb.rsplit(" ", 1)[-1]
        # A verb is named with its full path, an alias beside its verb's.
        if f"`{verb}" not in commands and f"`{name}`" not in commands:
            missing.append(verb)
    assert missing == []


def test_every_flag_of_every_verb_is_named_under_it(commands: str) -> None:
    missing = []
    for verb, parser in _tree(build_parser()):
        start = commands.find(f"- `{verb}")
        if start < 0:
            continue  # an alias: its flags are its verb's
        end = commands.find("\n- `", start + 1)
        block = commands[start : end if end > 0 else None]
        missing += [f"{verb} {f}" for f in _flags(parser) if f"`{f}" not in block]
    assert missing == []


def test_the_verbs_the_other_documents_never_named_are_listed(commands: str) -> None:
    for verb in (
        "mcgyvr attach",
        "mcgyvr index",
        "mcgyvr resolve QUERY",
        "mcgyvr read QUERY",
        "mcgyvr fleet alerts",
        "mcgyvr rig leave",
        "mcgyvr rig peers",
    ):
        assert f"- `{verb}" in commands, verb
    assert "(also `lend`)" in commands and "(also `caps`)" in commands


def test_read_says_what_hint_and_holds_do(commands: str) -> None:
    assert "`--hint PATH` — a path you believe is relevant; re-ranks the shortlist" in (
        " ".join(commands.split())
    )
    assert "`--holds PATH` — a path whose current content you already hold" in (
        " ".join(commands.split())
    )


def test_direct_s_flags_are_named_and_left_to_the_skills(commands: str) -> None:
    start = commands.index("- `mcgyvr direct")
    block = commands[start : commands.find("\n- `", start + 1)]
    assert "/mcgyvr-direct and `mcgyvr direct -h` say what each does" in block
    assert " — " not in block.split("\n", 1)[1], "no flag of direct is restated"


def test_a_verb_added_to_the_parser_is_listed_on_the_next_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.cli import dispatcher

    real = dispatcher.build_parser

    def grown() -> argparse.ArgumentParser:
        parser = real()
        sub = next(
            a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
        )
        added = sub.add_parser("example-verb", help="an invented verb")
        added.add_argument("--example-flag", metavar="N", help="an invented flag")
        return parser

    monkeypatch.setattr(dispatcher, "build_parser", grown)
    rendered = _commands(docgen.render_setup())
    assert "- `mcgyvr example-verb` — an invented verb." in rendered
    assert "  - `--example-flag N` — an invented flag." in rendered
