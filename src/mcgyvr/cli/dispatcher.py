""

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

if TYPE_CHECKING:  #
    pass


from mcgyvr.cli import common as _common
from mcgyvr.cli.commands import (
    delegate,
    fleet,
    inspect,
    lab,
    ladder,
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


def _build() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    ""
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
    lab.add_parser(sub)
    ladder.add_parser(sub)
    sandbox_cmd.add_parser(sub)
    setup.add_parser(sub)
    repo.add_parser(sub)
    fleet.add_parser(sub)
    rig_verbs.add_parser(sub, add_config=_common.add_config)
    ladder.add_mcorch_parser(sub)
    run_sub = run_cmd.add_parser(sub)
    delegate.add_parser(sub)

    return parser, run_sub


def build_parser() -> argparse.ArgumentParser:
    ""
    return _build()[0]


class _Version(argparse.Action):
    ""

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
    ""
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
    parser, run = _build()
    args = parser.parse_args(argv)
    if args.func is _run:
        _name_the_writer(run, args)
        _one_delivery_answer(run, args)
    elif args.func is _delegate:
        _one_delivery_answer(parser, args)
    try:
        with hanging_up_on_interrupt():
            result: int = args.func(args)
    except FolderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return result
