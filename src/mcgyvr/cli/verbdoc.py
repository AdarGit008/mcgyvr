"""Render COMMANDS.md: every verb and flag the `mcgyvr` parser defines.

The parser is the one truth of what the command line takes, so the list is
rendered from the parser itself (`mcgyvr.cli.dispatcher.build_parser`): a verb
or flag added there is listed on the next `make docs`, and `make docs-check`
fails until it is. The help is the parser's own words, the text `mcgyvr VERB -h`
prints. It lives on the command line's side because the core, `mcgyvr.docgen`
included, may not reach the command line; it borrows docgen's wrapping and its
write-or-check, so the document reads and is checked like the others.

`main` writes the document, or with `--check` reports it out of date without
touching it.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mcgyvr import docgen
from mcgyvr.cli.common import CONFIG_DEFAULT_HELP
from mcgyvr.cli.dispatcher import build_parser

COMMANDS_PATH = Path("COMMANDS.md")
COMMANDS_MARKER = (
    "<!-- Code generated from the mcgyvr parser by `make docs` "
    "(src/mcgyvr/cli/verbdoc.py). DO NOT EDIT. -->"
)

#: One verb of the parser tree: its full name, that name with its positionals,
#: its parser, its help line and its aliases.
_Verb = tuple[str, str, argparse.ArgumentParser, str, tuple[str, ...]]


def verbs(parser: argparse.ArgumentParser | None = None) -> list[_Verb]:
    """Every verb the `mcgyvr` parser defines, depth first in the parser's order;
    a verb whose help is hidden is left out, with everything under it."""
    found: list[_Verb] = []

    def walk(parser: argparse.ArgumentParser, path: str) -> None:
        for action in parser._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            helps = {
                choice.dest: choice.help or "" for choice in action._choices_actions
            }
            names: dict[int, list[str]] = {}
            parsers: dict[int, argparse.ArgumentParser] = {}
            for name, child in action.choices.items():
                names.setdefault(id(child), []).append(name)
                parsers[id(child)] = child
            for key, (name, *aliases) in names.items():
                child = parsers[key]
                if helps.get(name) == argparse.SUPPRESS:
                    continue
                positionals = " ".join(
                    _shown_positional(each)
                    for each in child._actions
                    if not each.option_strings
                    and each.help != argparse.SUPPRESS
                    and not isinstance(each, argparse._SubParsersAction)
                )
                full = f"{path} {name}"
                shown = f"{full} {positionals}" if positionals else full
                found.append((full, shown, child, helps.get(name, ""), tuple(aliases)))
                walk(child, full)

    walk(parser if parser is not None else build_parser(), "mcgyvr")
    return found


def _shown_positional(action: argparse.Action) -> str:
    """A positional as `-h` shows it: its metavar, or its name upper-cased, with
    `...` when it repeats and brackets when it may be left out."""
    shown = str(action.metavar or action.dest.upper())
    if action.nargs in ("*", "+", argparse.REMAINDER):
        shown += " ..."
    if action.nargs in ("?", "*"):
        shown = f"[{shown}]"
    return shown


def flags(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    """The flags `parser` shows in `-h`: every option but `-h` and a hidden one."""
    return [
        action
        for action in parser._actions
        if action.option_strings
        and not isinstance(action, argparse._HelpAction)
        and action.help != argparse.SUPPRESS
    ]


def _flag_help(parser: argparse.ArgumentParser, action: argparse.Action) -> str:
    """A flag's help as `-h` prints it, defaults filled in, as one sentence; the
    setup every `--config` falls back to is named, not spelled again, and a `*`
    is escaped so Markdown shows it."""
    text = parser._get_formatter()._expand_help(action) if action.help else ""
    text = " ".join(text.split()).replace(CONFIG_DEFAULT_HELP, "the usual setup")
    text = text.replace("*", "\\*").rstrip(".")
    return f"{text}." if text else ""


def _flag_names(action: argparse.Action) -> str:
    metavar = action.metavar
    if (
        metavar is None
        and action.nargs != 0
        and not isinstance(
            action, argparse._StoreConstAction | argparse.BooleanOptionalAction
        )
    ):
        metavar = action.dest.upper()
    return ", ".join(
        f"`{name} {metavar}`" if metavar else f"`{name}`"
        for name in action.option_strings
    )


def render(parser: argparse.ArgumentParser | None = None) -> str:
    """COMMANDS.md: `mcgyvr` itself with its own flags, then each verb with its
    help line and aliases, each flag under it with its own help."""
    wrap = docgen._wrap
    root = parser if parser is not None else build_parser()
    lines = [
        COMMANDS_MARKER,
        "",
        "# mcgyvr commands",
        "",
        *wrap(
            "Every verb and flag the `mcgyvr` parser defines, listed from the "
            "parser itself; `mcgyvr VERB -h` prints the same help. The bare verb, "
            "`mcgyvr PROMPT [flags]`, plans a prompt and runs it with `direct`'s "
            "flags. Where a flag's help says *the usual setup*, that is "
            f"{CONFIG_DEFAULT_HELP}.",
            rest="",
        ),
        "",
    ]
    said = " ".join((root.description or "").split()).rstrip(".")
    entries = [("`mcgyvr`", said, root)]
    for _full, shown, child, help_text, aliases in verbs(root):
        head = f"`{shown}`"
        if aliases:
            head += " (also " + ", ".join(f"`{alias}`" for alias in aliases) + ")"
        entries.append((head, " ".join(help_text.split()).rstrip("."), child))
    for head, said, child in entries:
        lines += wrap(f"{head} — {said}." if said else head, first="- ", rest="  ")
        for flag in flags(child):
            names = _flag_names(flag)
            help_said = _flag_help(child, flag)
            lines += wrap(
                f"{names} — {help_said}" if help_said else names,
                first="  - ",
                rest="    ",
            )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Write COMMANDS.md, or with `--check` report it stale (exit 1)."""
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.cli.verbdoc",
        description="Render COMMANDS.md from the mcgyvr parser.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed copy is out of date, without writing it",
    )
    parser.add_argument(
        "--output",
        default=str(docgen.REPO_ROOT / COMMANDS_PATH),
        help="where to write the document (default: the checkout's copy)",
    )
    args = parser.parse_args(argv)
    return docgen._write_or_check(
        Path(args.output), render(), "the parser under src/mcgyvr/cli/", args.check
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
