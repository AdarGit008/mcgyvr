"""The command line itself: the parser tree, the way in, and Ctrl-C.

`_build` assembles the `mcgyvr` parser -- `--version` and one subparser per
command module, each of which registers its own verbs -- and hands back both the
top-level parser and the `run` subparser, because `main` finishes the argument
checks that need more than one flag there. `main` parses argv, makes those checks
for `run` and `delegate`, and calls the handler argparse selected, with the
process hanging up on every dispatch in flight if the keyboard interrupts it. A
`FolderError` raised out of a handler is reported on stderr and becomes exit
status 1; otherwise the handler's own exit code is returned. `build_parser`
exposes the tree alone, without running anything.
"""

from __future__ import annotations

import argparse
import contextlib
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
    fleet,
    inspect,
    ladder,
    machine,
    repo,
    setup,
)
from mcgyvr.cli.commands import (
    run as run_cmd,
)
from mcgyvr.cli.commands import (
    sandbox as sandbox_cmd,
)
from mcgyvr.cli.commands.delegate import _delegate
from mcgyvr.cli.commands.run import _name_the_writer, _one_delivery_answer, _run
from mcgyvr.rig import verbs as rig_verbs


def _build() -> tuple[
    argparse.ArgumentParser, argparse.ArgumentParser, argparse.ArgumentParser
]:
    """Build the whole command tree and return it with two of its subparsers.

    Every command module adds its own subparser and verbs; `run` and `delegate`
    are the subparsers returned, since the checks `main` makes after parsing
    need them to report an error the way each command does.
    """
    parser = argparse.ArgumentParser(
        prog="mcgyvr",
        description=("Offload scoped coding work to a configurable worker ladder."),
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
    run_sub = run_cmd.add_parser(sub)
    delegate_sub = delegate.add_parser(sub)

    return parser, run_sub, delegate_sub


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


def main(argv: Sequence[str] | None = None) -> int:
    parser, run, delegating = _build()
    args = parser.parse_args(argv)
    if args.func is _run:
        _name_the_writer(run, args)
        _one_delivery_answer(run, args)
    elif args.func is _delegate:
        _one_delivery_answer(parser, args)
        if args.run:
            # The session is named before the orchestrator role is asked, as
            # `run` names it before any work: a batch nobody can be traced to
            # costs no model call and writes no contracts (exit 2).
            _name_the_writer(delegating, args)
    try:
        with hanging_up_on_interrupt():
            result: int = args.func(args)
    except FolderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return result
