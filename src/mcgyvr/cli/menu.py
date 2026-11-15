"""The no-args interactive menu: pick a verb, then its prompts.

`mcgyvr` with no arguments on a terminal opens this menu instead of failing:
a nested list of the existing verbs, driven by `input()` alone — no
prompt_toolkit, questionary, rich or curses. It is a mode of the one `mcgyvr`
command, not a new verb, and it adds no dependency.

A choice is taken by its number, its full name, or a prefix that names exactly
one; Enter takes the default where one is offered. Arrow keys are not read:
a plain `input()` loop reads whole lines, and reading raw escape sequences
would mean owning the terminal, which is exactly the dependency this menu is
for.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import Any

from mcgyvr.exits import Exit

#: How many times one question is asked before the menu gives up.
_TRIES = 3


class MenuError(Exception):
    """A menu question could not be answered; the menu exits with usage."""


def is_interactive() -> bool:
    """Whether stdin and stdout are both a terminal: the menu needs both."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _spoken(names: Sequence[str]) -> str:
    """`names` as a prompt says them: `a`, `a or b`, or `a, b or c`."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"


def _match(said: str, order: Sequence[str]) -> str | None:
    """The one choice of `order` `said` names, or None when it names none.

    A number takes the choice at that position (1-based); the full name and a
    prefix that names exactly one choice are taken as the choice too.
    """
    if said.isdigit():
        at = int(said)
        if 1 <= at <= len(order):
            return order[at - 1]
        return None
    named = [name for name in order if name == said]
    if len(named) == 1:
        return named[0]
    prefixed = [name for name in order if name.startswith(said)]
    if len(prefixed) == 1:
        return prefixed[0]
    return None


def pick(
    question: str,
    choices: Sequence[str],
    *,
    default: str | None = None,
    what: str = "a choice",
    numbered: bool = True,
    prompt: Callable[[str], str] = input,
) -> str:
    """Ask for one of `choices` and answer it, as :mod:`mcgyvr.cli.menu` reads it.

    The choices are listed numbered by default; with `numbered` off the
    question is expected to spell them. Enter takes `default`, and an answer
    that names nothing is reported and asked again, up to `_TRIES` times.
    """
    order = list(dict.fromkeys(choices))
    if numbered:
        for number, name in enumerate(order, start=1):
            print(f"{number}. {name}")
    said = ""
    for _ in range(_TRIES):
        said = str(prompt(question)).strip()
        if not said and default is not None:
            return default
        found = _match(said, order)
        if found is not None:
            return found
        if not said:
            print("Pick one: " + _spoken(order) + ".")
        else:
            print(f"{said!r} is not {what}; pick {_spoken(order)}.")
    raise MenuError(f"{said!r} is not {what}; the menu offers {_spoken(order)}")


def _subparsers_action(parser: argparse.ArgumentParser) -> Any:
    """The one subparsers action `parser` holds, or None."""
    group = getattr(parser, "_subparsers", None)
    if group is None:
        return None
    for action in group._group_actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    action = _subparsers_action(parser)
    if action is None:
        return {}
    return dict(action.choices)


def menu_commands(parser: argparse.ArgumentParser) -> tuple[str, ...]:
    """The commands `parser` offers, canonical names only, sorted.

    An alias (`caps` for `capabilities`) names the same parser as its
    canonical spelling; it is dropped, so the menu lists one entry per verb.
    """
    seen: set[int] = set()
    names: list[str] = []
    for name, sub in _choices(parser).items():
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        names.append(name)
    return tuple(sorted(names))


def _call(main: Callable[[Sequence[str]], int], argv: Sequence[str]) -> int:
    """Run `main(argv)`, reading an argparse usage exit as its code."""
    try:
        return main(list(argv))
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else Exit.USAGE


def _setup_menu(main: Callable[[Sequence[str]], int]) -> int:
    """Pick how far `setup` runs: the full pipeline, or a stage that stops there."""
    from mcgyvr.cli.commands import setup as setup_cmd

    mode = pick(
        "setup — [auto] the full pipeline, or [manual] a stage that "
        "stops there? [auto] ",
        ("auto", "manual"),
        default="auto",
        what="auto or manual",
        numbered=False,
    )
    if mode == "auto":
        return setup_cmd.run_menu_setup(auto=True, stop=None)
    stop = pick(
        "stop after — [config] write the config, [emit] also write launch "
        "specs, or [start] also bring the servers up (no sample/lock)? [emit] ",
        ("config", "emit", "start"),
        default="emit",
        what="a stage",
        numbered=False,
    )
    return setup_cmd.run_menu_setup(auto=False, stop=stop)


def _emit_menu(main: Callable[[Sequence[str]], int]) -> int:
    """`emit` defaults to writing the launch specs; `--check` writes none."""
    mode = pick(
        "emit — [write] the launch specs, or [check] compare without writing? [write] ",
        ("write", "check"),
        default="write",
        what="write or check",
        numbered=False,
    )
    return _call(main, ["emit"] if mode == "write" else ["emit", "--check"])


def _serve_menu(main: Callable[[Sequence[str]], int]) -> int:
    """Pick a `serve` direction, then the rig it acts on."""
    direction = pick(
        "serve — [status] list, [sleep] rest a card, or [wake] bring it "
        "back? [status] ",
        ("status", "sleep", "wake"),
        default="status",
        what="a serve direction",
        numbered=False,
    )
    host = input("rig (--host): ").strip()
    if not host:
        raise MenuError("serve needs a rig (--host)")
    return _call(main, ["serve", direction, "--host", host])


def _dispatch(
    verb: str, parser: argparse.ArgumentParser, main: Callable[[Sequence[str]], int]
) -> int:
    """Run the verb the menu picked: its own menu, a nested pick, or the verb."""
    if verb == "setup":
        return _setup_menu(main)
    if verb == "emit":
        return _emit_menu(main)
    if verb == "serve":
        return _serve_menu(main)
    sub = _choices(parser).get(verb)
    subcommands = menu_commands(sub) if sub is not None else ()
    if subcommands:
        subverb = pick(
            f"{verb} — pick an action: ",
            subcommands,
            default=subcommands[0],
            what=f"a {verb} action",
        )
        return _call(main, [verb, subverb])
    return _call(main, [verb])


def run(parser: argparse.ArgumentParser, main: Callable[[Sequence[str]], int]) -> int:
    """The no-args menu: pick a verb, then dispatch it, answering the exit code."""
    commands = menu_commands(parser)
    if not commands:
        return main([])
    verb = pick("Pick a command: ", commands, default=None, what="a command")
    return _dispatch(verb, parser, main)
