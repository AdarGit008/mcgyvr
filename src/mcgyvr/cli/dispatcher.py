"""The command line itself: the parser tree, the way in, and Ctrl-C.

`_build` assembles the `mcgyvr` parser -- `--version` and one subparser per
command module, each of which registers its own verbs -- and hands it back with
the parser of the bare verb, `mcgyvr PROMPT`, and the `direct` subparser,
because `main` finishes the argument checks that need more than one flag there.
`main` sends argv to the bare verb when its first word is not a command, makes
those checks, and calls the handler argparse selected, with the process hanging
up on every dispatch in flight if the keyboard interrupts it. A `FolderError`
raised out of a handler is reported on stderr and becomes exit status 1;
otherwise the handler's own exit code is returned. `build_parser` exposes the
tree alone, without running anything.
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import signal
import sys
import threading
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

from mcgyvr import __version__
from mcgyvr.config import (
    ConfigError,
    ConfigMissingError,
)
from mcgyvr.config import load as load_config
from mcgyvr.fleet.roots import (
    FolderError,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


from mcgyvr.cli import common as _common
from mcgyvr.cli.commands import (
    delegate,
    direct,
    fleet,
    inspect,
    ladder,
    machine,
    repo,
    setup,
)
from mcgyvr.cli.commands import (
    sandbox as sandbox_cmd,
)
from mcgyvr.cli.commands.delegate import _refuse_before_delegating
from mcgyvr.cli.commands.direct import _direct, _refuse_before_direct
from mcgyvr.rig import verbs as rig_verbs

#: The top-level options that are not a prompt's first word.
_TOP_LEVEL_OPTIONS = frozenset({"-h", "--help", "--version"})

#: The verbs that are gone, and what took their place.
_REMOVED = {
    "run": "`mcgyvr direct FILE...` runs contracts you wrote",
    "delegate": "`mcgyvr PROMPT` plans a prompt and runs it, and with "
    "`--output DIR` writes the contracts alone",
}

#: The top-level epilog: the bare verb, which is not a subcommand.
_EPILOG = """\
the bare verb:
  mcgyvr PROMPT [flags]   plan PROMPT into contracts and run them; the flags are
                          `direct`'s (`mcgyvr direct -h`). A prompt whose first
                          word is a command is written after `--`, the flags
                          before it: `mcgyvr [flags] -- PROMPT`."""


def _build() -> tuple[
    argparse.ArgumentParser, argparse.ArgumentParser, argparse.ArgumentParser
]:
    """Build the command tree, the bare verb's parser, and the `direct` subparser.

    Every command module adds its own subparser and verbs. The bare verb,
    `mcgyvr PROMPT`, is a parser of its own, since a prompt is no command's
    name; it and `direct` are returned, since the checks `main` makes after
    parsing need them to report an error the way each verb does.
    """
    parser = argparse.ArgumentParser(
        prog="mcgyvr",
        description=("Offload scoped coding work to a configurable worker ladder."),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action=_Version,
        nargs=0,
        help="the product version, and the path of the config a run here would use",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect.add_parser(sub)
    machine.add_parser(sub)
    ladder.add_parser(sub)
    sandbox_cmd.add_parser(sub)
    setup.add_parser(sub)
    repo.add_parser(sub)
    fleet.add_parser(sub)
    rig_verbs.add_parser(sub, add_config=_common.add_config)
    direct_sub = direct.add_parser(sub)

    return parser, delegate.prompt_parser(), direct_sub


def build_parser() -> argparse.ArgumentParser:
    """The top-level `mcgyvr` parser, for callers that only need the tree."""
    return _build()[0]


class _Version(argparse.Action):
    """`--version`: print the version and the config a run here would read, then exit.

    A config that is missing, unreadable, or cannot be located is reported as a
    `config:` line rather than failing the flag, so `--version` always answers.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        print(f"mcgyvr {__version__}")
        try:
            config = load_config(None)
        except ConfigMissingError:
            print("config: none")
        except ConfigError as exc:
            print(f"config: unreadable ({exc})")
        except (OSError, RuntimeError) as exc:
            print(f"config: cannot be located ({exc!r})")
        else:
            print(f"config: {config.path}")
        parser.exit(0)


@contextlib.contextmanager
def hanging_up_on_interrupt() -> Iterator[None]:
    """Hang up on every dispatch in flight when Ctrl-C arrives, then raise it.

    The handler calls `runner.hang_up_all` and re-raises `KeyboardInterrupt`, so
    a command sees the interrupt exactly as it did before. Nothing is installed
    off the main thread, where a signal is not heard, or when someone else
    already replaced Python's default handler; the default is put back on exit.
    """
    from mcgyvr import runner

    if (
        threading.current_thread() is not threading.main_thread()
        or signal.getsignal(signal.SIGINT) is not signal.default_int_handler
    ):
        yield
        return

    def interrupted(signum: int, frame: object) -> None:
        runner.hang_up_all()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupted)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, signal.default_int_handler)


def _commands(parser: argparse.ArgumentParser) -> frozenset[str]:
    """The names of the subcommands `parser` holds."""
    return frozenset(
        name
        for action in parser._subparsers._group_actions  # type: ignore[union-attr]
        if isinstance(action, argparse._SubParsersAction)
        for name in action.choices
    )


def _is_prompt(argv: Sequence[str], commands: frozenset[str]) -> bool:
    """Whether `argv` is the bare verb: a first word that is no command or
    top-level option. A prompt that is a command's name follows `--`."""
    return bool(argv) and argv[0] not in commands | _TOP_LEVEL_OPTIONS


def _not_a_prompt(argv: Sequence[str], commands: frozenset[str]) -> str | None:
    """Why `argv`'s first word is refused as a prompt, or None.

    A removed verb is named with what took its place, and one word close to a
    command is taken for a typo of it, so neither is sent to a proposer.
    """
    if "--orchestrator" in argv:
        return "--orchestrator is gone: name the session with --session ID."
    first = argv[0]
    if first in _REMOVED:
        return f"`mcgyvr {first}` is gone: {_REMOVED[first]}."
    if first.startswith("-") or len(first.split()) != 1:
        return None
    close = difflib.get_close_matches(first, sorted(commands), n=1, cutoff=0.8)
    if close:
        return (
            f"{first!r} is not a command: did you mean `mcgyvr {close[0]}`? "
            f"To plan it as a prompt, write `mcgyvr -- {first}`."
        )
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser, prompt, directing = _build()
    words = list(sys.argv[1:] if argv is None else argv)
    if _is_prompt(words, _commands(parser)):
        problem = _not_a_prompt(words, _commands(parser))
        if problem is not None:
            parser.error(problem)
        args = prompt.parse_args(words)
        # The prompt may follow flags: it is the first word that is no flag's.
        if "--" not in words:
            problem = _not_a_prompt([args.prompt], _commands(parser))
            if problem is not None:
                parser.error(problem)
        # Unless --output asks for the contracts alone, the session is named
        # here, before the proposer is asked: a batch nobody can be traced to
        # costs no model call and writes no contracts (exit 2).
        _refuse_before_delegating(prompt, args)
    else:
        args = parser.parse_args(words)
        if args.func is _direct:
            _refuse_before_direct(directing, args)
    try:
        with hanging_up_on_interrupt():
            result: int = args.func(args)
    except FolderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return result
