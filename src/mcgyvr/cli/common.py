"""Shared argparse wiring and small helpers for the command line."""

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




CONFIG_DEFAULT_HELP = (
    f"${CONFIG_PATH_ENV}, else the live fleet folder under {FLEETS_SHOWN} that "
    f"{LIVE_FILE_SHOWN} names — a directory holding fleet.yaml and policy.yaml"
)



INIT_DEFAULT_HELP = (
    f"${CONFIG_PATH_ENV}, else a folder of the run's own, {STAGING_SHOWN} — "
    f"never the working directory, and never a live fleet folder, which is "
    f"written only when setup promotes a fleet it locked"
)



SETUP_DOC = "skills/mcgyvr/SETUP.md"



def _mib(size_bytes: int) -> str:
    return f"{size_bytes / 1024 / 1024:.1f} MiB"



def _named_path(value: str) -> str:
    """A path argument's value, refused when it names nothing.

    Argparse's own ``type``, so the refusal is the subparser's usage error —
    exit 2, with the argument's name in it — and arrives before a contract, a
    repository or a config file is opened. That is the same seam and the same
    code as the blank ``--orchestrator`` (:func:`_name_the_writer`), because it
    is the same mistake: an argument given a value that names nothing.

    **A blank is not "the caller named none".** Every path here is optional and
    resolves a default when absent; an empty string is falsy and equals
    ``Path('.')``, so unrefused it would take that default — for ``--record``,
    the current directory.

    What puts a blank there is not somebody typing two quotes. It is
    ``--record "$JOURNAL_DIR"`` with the variable unset, which is the shape
    every wrapper script has, and a wrapper is exactly the caller who will not
    read the scrollback to notice.

    Whitespace counts as blank, as it does for the orchestrator id. A directory
    named three spaces is legal on this filesystem and is not what anybody
    meant; the value is otherwise handed on untouched, because a path with a
    space at either end is legal too and stripping it would be this function
    choosing a different file than the caller named.
    """
    if not value.strip():
        raise argparse.ArgumentTypeError(
            "a blank value is not a path. It is what an unset variable leaves "
            "behind. Pass a path, or leave the argument off to take the default "
            "on purpose."
        )
    return value



class _RepoByPosition(argparse.Action):
    """The old spelling, a repository typed by position, refused by name.

    Hidden from the usage: it is not an argument, only the catch for one that
    is no longer taken. Without it the old form meets argparse's bare
    "unrecognized arguments", which says nothing about ``--repo``. Absent, it
    is never called (its default is ``SUPPRESS``) and leaves nothing behind.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        raise argparse.ArgumentError(
            None,
            f"the repository is named with --repo, not by position: --repo {values}",
        )



def _add_repo(parser: argparse.ArgumentParser, what: str) -> None:
    """``--repo PATH``, the one way every verb is told its repository.

    ``run`` named it with this flag and five other verbs by position, so the
    flag a user learned on ``run`` was refused everywhere else. Every verb now
    takes the flag, defaulting to the current directory and refusing a blank
    the way ``run`` always has (:func:`_named_path`); a repository typed by
    position is refused by :class:`_RepoByPosition`.
    """
    parser.add_argument(
        "--repo",
        default=".",
        type=_named_path,
        metavar="PATH",
        help=f"{what} (default: .)",
    )
    parser.add_argument(
        "_repo_by_position",
        nargs="?",
        default=argparse.SUPPRESS,
        action=_RepoByPosition,
        help=argparse.SUPPRESS,
    )



def add_config(
    parser: argparse.ArgumentParser,
    *,
    dest: str = "config",
    what: str = "config to read",
) -> None:
    """``--config PATH``, the one way every verb is told which setup to read.

    ``run`` took the setup as ``--config`` while ``config`` and ``local_pool``
    took it by position, ``catalog`` as ``--against``, and ``sandbox``,
    ``fleet alerts`` and the ``rig`` agent had no way to name it, so the flag a
    user learned on ``run`` was refused elsewhere (e2e run 2, R9). Every verb
    that reads the setup now takes it, with ``run``'s meaning and precedence:
    the directory (or one merged file) it names wins over ``$MCGYVR_CONFIG``
    and the live fleet, and leaving it off takes that chain.
    ``tests/test_every_command_that_reads_a_config_takes_dash_dash_config.py``
    walks the parser so a new verb cannot miss it.

    ``dest`` is for a verb whose older spelling is kept beside the flag (a
    positional, ``--against``): both store into it through
    :class:`_OneSetup`, so the handler reads one value and two different
    setups on one line are refused.
    """
    parser.add_argument(
        "--config",
        dest=dest,
        default=argparse.SUPPRESS,
        type=_named_path,
        metavar="PATH",
        action=_OneSetup,
        help=f"{what} (default: {CONFIG_DEFAULT_HELP})",
    )



class _OneSetup(argparse.Action):
    """Store a setup path, refusing a second, different one on the same line.

    The action of ``--config`` and of the older spelling a verb keeps beside it
    (``mcgyvr config PATH``, ``catalog --against PATH``). A value that names no
    path — an absent positional, a bare ``--against`` — never replaces one
    that does, so the order they are typed in does not matter. Two paths that
    differ are a usage error through the subparser's own ``error`` (exit 2):
    picking one would be guessing which setup the person meant.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        earlier = getattr(namespace, self.dest, None)
        if not isinstance(values, str):
            if not isinstance(earlier, str):
                setattr(namespace, self.dest, values)
            return
        if (
            isinstance(earlier, str)
            and Path(earlier).expanduser() != Path(values).expanduser()
        ):
            parser.error(
                f"the command line names two setups, {earlier} and {values}; "
                "name one, with --config"
            )
        setattr(namespace, self.dest, values)
