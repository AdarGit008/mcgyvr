"""COMMANDS.md lists every verb and flag the `mcgyvr` parser defines.

The parser is the one truth of what the CLI takes, and COMMANDS.md is rendered
from it by `mcgyvr.cli.verbdoc`: `mcgyvr` itself with its own flags
(`--version`), then every verb and every flag `-h` shows, a verb on its own
line with its help and its aliases in that line's `(also ...)`, a flag under
its verb with its own help, so a verb or flag added to the parser is in the
document on the next `make docs` and the drift check fails until it is.
Hidden verbs and flags stay hidden. The renderer sits on the command line's
side, since the core (docgen included) may not reach the command line;
SETUP.md points at the document by its name.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator

import pytest

from mcgyvr import docgen
from mcgyvr.cli import verbdoc
from mcgyvr.cli.dispatcher import build_parser
from tests._paths import REPO

COMMANDS_MD = REPO / verbdoc.COMMANDS_PATH


def _tree(
    parser: argparse.ArgumentParser, path: str = "mcgyvr"
) -> Iterator[tuple[str, tuple[str, ...], argparse.ArgumentParser]]:
    """Every verb the tree holds: its full name, its aliases and its parser."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            names: dict[int, list[str]] = {}
            for name, child in action.choices.items():
                names.setdefault(id(child), []).append(name)
            for name, child in action.choices.items():
                first, *aliases = names[id(child)]
                if name != first:
                    continue
                yield f"{path} {name}", tuple(aliases), child
                yield from _tree(child, f"{path} {name}")


def _entry(commands: str, verb: str) -> str | None:
    """The list entry of `verb`, its own line and the flags under it: the line
    names the verb exactly, followed only by its positionals (which are upper
    case or bracketed, where a verb's own name is lower case)."""
    found = re.search(
        rf"^- `{re.escape(verb)}(?: [A-Z\[][^`]*)?`.*?(?=^- `|\Z)",
        commands,
        flags=re.MULTILINE | re.DOTALL,
    )
    return found.group(0) if found else None


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
    return COMMANDS_MD.read_text(encoding="utf-8")


def test_the_committed_document_is_what_the_parser_renders(commands: str) -> None:
    assert commands == verbdoc.render()
    assert verbdoc.main(["--check"]) == 0


def test_every_verb_and_alias_the_parser_defines_is_named(commands: str) -> None:
    missing = []
    for verb, aliases, _parser in _tree(build_parser()):
        entry = _entry(commands, verb)
        if entry is None:
            missing.append(verb)
            continue
        # An alias is named in its own verb's line, inside its `(also ...)`.
        line = " ".join(entry.split("\n  - ", 1)[0].split())
        also = re.search(r"\(also ([^)]*)\)", line)
        missing += [
            f"{verb} alias {alias}"
            for alias in aliases
            if also is None or f"`{alias}`" not in also.group(1)
        ]
    assert missing == []


def test_every_flag_of_every_verb_is_named_under_it(commands: str) -> None:
    root = build_parser()
    missing = []
    for verb, _aliases, parser in [("mcgyvr", (), root), *_tree(root)]:
        entry = _entry(commands, verb) or ""
        missing += [f"{verb} {f}" for f in _flags(parser) if f"`{f}" not in entry]
    assert missing == []


def test_the_root_parser_s_own_flags_are_listed(commands: str) -> None:
    entry = _entry(commands, "mcgyvr")
    assert entry is not None and "  - `--version` — " in entry


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
    flat = " ".join(commands.split())
    assert "`--hint PATH` — a path you believe is relevant; re-ranks the shortlist" in (
        flat
    )
    assert "`--holds PATH` — a path whose current content you already hold" in flat


def test_setup_names_the_document() -> None:
    assert str(verbdoc.COMMANDS_PATH) == docgen.COMMANDS_DOC
    assert f"`{docgen.COMMANDS_DOC}`" in docgen.render_setup()


def test_a_verb_added_to_the_parser_is_listed_on_the_next_render() -> None:
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    added = sub.add_parser("example-verb", help="an invented verb")
    added.add_argument("--example-flag", metavar="N", help="an invented flag")
    hidden = sub.add_parser("hidden-verb", help=argparse.SUPPRESS)
    hidden.add_argument("--hidden-flag")

    rendered = verbdoc.render(parser)
    assert "- `mcgyvr example-verb` — an invented verb." in rendered
    assert "  - `--example-flag N` — an invented flag." in rendered
    assert "hidden" not in rendered
    assert rendered != COMMANDS_MD.read_text(encoding="utf-8"), "the check would fail"
