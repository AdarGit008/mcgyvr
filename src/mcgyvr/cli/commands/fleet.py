"""The `mcgyvr fleet` commands: name a live fleet, probe and read alerts.

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




def _fleet_alerts(args: argparse.Namespace) -> int:
    """List the combinations the journal holds pulled, unit and field each.

    The journal is ``--journal``, else ``<journal.dir>/fleet`` of the live fleet
    — where ``mcgyvr fleet probe`` files (:func:`mcgyvr.fleet.probe.journal_dir`).
    The lock is read from the live fleet's folder
    (:func:`mcgyvr.fleet.roots.live_fleet_dir`) unless ``--root`` names one.
    """
    from mcgyvr.fleet.alerts import pulled
    from mcgyvr.fleet.probe import ProbeError, journal_dir
    from mcgyvr.fleet.roots import LiveFleetError, live_fleet_dir

    if args.journal:
        journal = Path(args.journal)
    else:
        try:
            journal = journal_dir(live_fleet_dir())
        except (LiveFleetError, ProbeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    root: Path | None
    if args.root:
        root = Path(args.root)
    else:
        try:
            # With no fleet named live there is no lock to clear a pull, so
            # every pull the journal holds is listed.
            root = live_fleet_dir()
        except LiveFleetError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    for combination, entries in pulled(journal, root).items():
        for entry in entries:
            print(f"{combination} {entry['unit_id']} {entry['field']}")
    return 0



def _fleet_use(args: argparse.Namespace) -> int:
    """Name a promoted fleet live, and say what the lock knows of the move.

    Any promoted folder whose layout matches its lock may be
    named; the move from the fleet that was live is reported as locked — in
    that fleet's ``next``, with the downtime and wake its lock measured — or
    as unmeasured. Nothing is started either way.
    """
    from mcgyvr.fleet.promote import PromoteRefusedError, use
    from mcgyvr.fleet.roots import layout_of

    try:
        switch = use(args.name)
    except (PromoteRefusedError, OSError) as exc:
        # OSError: a config folder that cannot be searched or written.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"live: {switch.name} ({switch.pointer})")
    if switch.previous is None:
        print("move: none, no fleet was live")
    elif switch.previous == switch.name:
        print(f"move: none, {switch.name} was already live")
    elif switch.locked:
        print(
            f"move: {switch.previous} -> {switch.name} is locked: "
            f"{layout_of(switch.previous)}'s lock lists {switch.layout} in next"
        )
        # The lock's own figures, as it recorded them.
        for move in switch.moves:
            wakes = ", ".join(
                f"{unit} {seconds} s"
                for unit, seconds in sorted((move.get("wake_s") or {}).items())
            )
            print(
                f"  {move.get('rig')}: downtime {move.get('downtime_s')} s"
                + (f", wake {wakes}" if wakes else "")
            )
    else:
        print(
            f"move: {switch.previous} -> {switch.name} is unmeasured: "
            f"{switch.unmeasured}. use starts nothing; a live serve up is "
            f"admitted from {switch.name}'s own lock"
        )
    return 0



def _fleet_probe(args: argparse.Namespace) -> int:
    """Probe the live fleet's idle units by their lock's own method, and judge them.

    Exit 1 when the probe cannot run at all or a unit's probe could not run;
    an alert is printed and filed, and is not a failed probe
    (:mod:`mcgyvr.fleet.probe`).
    """
    from mcgyvr.fleet import linkread, read
    from mcgyvr.fleet.probe import ProbeError, run

    try:
        report = run(
            units=args.units or None,
            reader=read.spawn_read,
            link_reader=linkread.door_timer(),
        )
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for unit, figures in report.probed.items():
        shown = ", ".join(f"{name} {value:.2f}" for name, value in figures.items())
        print(f"probed {unit}: {shown}")
    for unit, count in report.busy.items():
        print(f"busy {unit}: {count} in flight, not probed")
    for unit in report.contended:
        print(f"contended {unit}: took work during the probe; filed, not judged")
    for unit, (fields, reason) in report.not_read.items():
        print(f"not read {unit}: {', '.join(fields)} ({reason})")
    for unit, (fields, reason) in report.off_the_rig.items():
        print(f"not judged {unit}: {', '.join(fields)} recorded ({reason})")
    for alert in report.alerts:
        print(f"alert {alert['unit_id']} {alert['field']}")
    for key, says in report.links.items():
        print(f"link {key}: {says}")
    for unit, why in report.failed.items():
        print(f"error: {unit}: {why}", file=sys.stderr)
    for key, why in report.links_failed.items():
        print(f"error: link {key}: {why}", file=sys.stderr)
    return report.exit_code


def add_parser(sub: argparse.ArgumentParser) -> None:
    """Register the `fleet use/probe/alerts` commands."""

    fleet = sub.add_parser(
        "fleet",
        help="name a promoted fleet live, and read what its lock approves",
    )
    fleet_sub = fleet.add_subparsers(dest="fleet_command", required=True)
    fuse = fleet_sub.add_parser(
        "use",
        help=(
            f"name a promoted fleet live, in {LIVE_FILE_SHOWN}, and say whether "
            "the move from the fleet that was live is one its lock measured"
        ),
    )
    fuse.add_argument(
        "name",
        metavar="FLEET@DATE",
        help="the promoted folder to run live (a pre-ruling folder by its plain name)",
    )
    fuse.set_defaults(func=_fleet_use)
    fprobe = fleet_sub.add_parser(
        "probe",
        help=(
            "judge the live fleet's idle units by their lock's own measurement, "
            "filed under <journal.dir>/fleet"
        ),
    )
    fprobe.add_argument(
        "units",
        nargs="*",
        metavar="UNIT",
        help="the awake units to probe (default: every awake unit of the live fleet)",
    )
    fprobe.set_defaults(func=_fleet_probe)
    falerts = fleet_sub.add_parser(
        "alerts",
        help="list the combinations the journal holds pulled",
    )
    falerts.add_argument(
        "--journal",
        default=None,
        metavar="DIR",
        help=(
            "where the fleet journal was filed (default: <journal.dir>/fleet of "
            "the live fleet, where `mcgyvr fleet probe` files)"
        ),
    )
    falerts.add_argument(
        "--root",
        default=None,
        metavar="DIR",
        help=(
            "where the lock tree is read (default: the folder of the fleet "
            f"{LIVE_FILE_SHOWN} names)"
        ),
    )
    falerts.set_defaults(func=_fleet_alerts)

