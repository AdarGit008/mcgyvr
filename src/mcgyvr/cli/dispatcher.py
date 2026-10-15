"""Command-line entrypoint: builds the parser and dispatches.

Only what is built is exposed.
"""

from __future__ import annotations


import argparse


import contextlib


import ipaddress


import json


import os


import signal


import sys


import textwrap


import threading


from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence


from dataclasses import dataclass


from pathlib import Path


from typing import TYPE_CHECKING, Any, TextIO


import yaml


from mcgyvr import __version__, atomic


from mcgyvr import recommend as recommend_module


from mcgyvr import scan as scan_module


from mcgyvr.availability import PROBE_TIMEOUT_S


from mcgyvr.capability import (
    ESTIMATES_NOTICE,
    GB_PER_GIB,
    CapabilityTableError,
    Model,
    load,
    table_path,
)


from mcgyvr.config import (
    API_OUTPUT_TOKENS,
    CONFIG_PATH_ENV,
    FLEET_FILENAME,
    Config,
    ConfigError,
    ConfigMissingError,
    named_config_path,
)


from mcgyvr.config import config_path as resolve_config_path


from mcgyvr.config import load as load_config


from mcgyvr.detect import DEFAULT_PROBE_TARGETS, detect, targets_for


from mcgyvr.emit import (
    Drift,
    EmitError,
    LockedLaunchError,
    check_all,
    check_locked,
    emit_all,
    emit_locked,
    is_locked,
    planned_locked_paths,
    planned_paths,
    resolved_launch,
    unplanned,
    unplanned_locked,
)


from mcgyvr.emit import sleep_mode as emit_sleep_mode


from mcgyvr.exits import Exit


from mcgyvr.fleet.files import FleetFileError, load_fleet


from mcgyvr.fleet.roots import (
    FLEETS_SHOWN,
    LIVE_FILE_SHOWN,
    RIGS_SHOWN,
    STAGING_SHOWN,
    FolderError,
)


from mcgyvr.initialize import (
    PRIORITIES,
    ApiSpecError,
    InitError,
    initialize,
    parse_api_unit,
    render_fleet,
    unit_names,
)


from mcgyvr.scan import ModelOnDisk, Scan


from mcgyvr.serving import (
    ModelSpec,
    Unit,
    UnitError,
    declared_models,
    hold_together,
    host_of,
    units_for,
)


if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.contract import Contract
    from mcgyvr.deliver import Accepted
    from mcgyvr.detect import Detection
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.drive import Recording
    from mcgyvr.escalate import Delivered, Halted, Judgement
    from mcgyvr.gate import GateResult
    from mcgyvr.gate.adapter import LanguageAdapter
    from mcgyvr.knowledge.record import ModelRecord
    from mcgyvr.local_pool import SourceMap
    from mcgyvr.orchestrator.decompose import Decomposition, Proposer
    from mcgyvr.result import RunResult
    from mcgyvr.route import Attempted, Try
    from mcgyvr.sandbox.base import Sandbox
    from mcgyvr.session import Session


from mcgyvr.cli import common as _common
from mcgyvr.cli.commands import (
    setup,
    fleet,
    ladder,
    run as run_cmd,
    delegate,
    inspect,
    sandbox as sandbox_cmd,
    repo,
    lab,
)
from mcgyvr.cli.commands.run import _name_the_writer, _one_delivery_answer, _run
from mcgyvr.cli.commands.delegate import _delegate
from mcgyvr.rig import verbs as rig_verbs


def _build() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    """The whole command line, plus the `run` subparser on its own."""
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
    """The command line as a person types it.

    Public so what a run reads and what a person typed can be checked against
    each other.
    """
    return _build()[0]


class _Version(argparse.Action):
    """`--version`: the product, then the config a run here would be made under."""

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
    """Ctrl-C hangs up on every dispatch of the process before it stops the command."""
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
