"""The `mcgyvr fleet` subcommands. `use` names a promoted fleet live in
`live.json` and says whether the move from the fleet that was live is one that
fleet's lock measured; `probe` judges the live fleet's awake units by the figures
their lock approves and files the result; `alerts` lists the combinations the
journal holds pulled, with the unit/field pairs that tripped them; `key` prints
the key mcgyvr made for a unit of `expose: lan`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _named_path
from mcgyvr.fleet.roots import (
    LIVE_FILE_SHOWN,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


def _fleet_alerts(args: argparse.Namespace) -> int:
    """Print every pulled unit/field pair as `<combination> <unit_id> <field>`.

    The journal is `--journal`, or the live fleet's filed journal; the lock tree
    the pulls are read against is `--root`, or the folder of the fleet the live
    pointer names. A journal or lock tree that cannot be named is printed to
    stderr and returns 1; otherwise 0.
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
            # The lock tree defaults to the folder of the fleet the live
            # pointer names; a pointer that is broken is reported, not raised.
            root = live_fleet_dir()
        except LiveFleetError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    for combination, entries in pulled(journal, root).items():
        for entry in entries:
            print(f"{combination} {entry['unit_id']} {entry['field']}")
    return 0


def _timed(move: dict[str, object]) -> str:
    """A measured move's cost as printed: its downtime, then the wakes it pays."""
    wake_s = move.get("wake_s")
    wakes = ", ".join(
        f"{unit} {seconds} s"
        for unit, seconds in sorted(wake_s.items() if isinstance(wake_s, dict) else ())
    )
    return f"downtime {move.get('downtime_s')} s" + (f", wake {wakes}" if wakes else "")


def _fleet_use(args: argparse.Namespace) -> int:
    """Point `live.json` at the promoted fleet named on the command line.

    Says what was live before: nothing, the same fleet, a move the previous
    fleet's lock measured (with each rig's downtime and wakes), or a move that
    lock does not measure; then each sleeper's swap the named fleet's lock
    measured, each way with its downtime and wakes. A refusal or a filesystem
    error is printed to stderr and returns 1; otherwise 0.
    """
    from mcgyvr.fleet.promote import PromoteRefusedError, use
    from mcgyvr.fleet.roots import layout_of

    try:
        switch = use(args.name)
    except (PromoteRefusedError, OSError) as exc:
        # A name that is not a fleet folder, a folder that holds no such fleet
        # in its setup, or a pointer that cannot be read or written: refused,
        # and nothing was switched.
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
        # The moves the lock measured, each as its rig, its downtime and the
        # wakes it pays; a lock that recorded no moves prints none.
        for move in switch.moves:
            print(f"  {move.get('rig')}: {_timed(move)}")
    else:
        print(
            f"move: {switch.previous} -> {switch.name} is unmeasured: "
            f"{switch.unmeasured}. use starts nothing; a live serve up is "
            f"admitted from {switch.name}'s own lock"
        )
    # The swaps the named fleet's lock measured, in the same shape; a fleet
    # that lays out no sleeper prints none.
    for swap in switch.swaps:
        print(
            f"swap: {swap.get('unit')} {swap.get('way')} on {swap.get('rig')}: "
            f"{_timed(swap)}"
        )
    return 0


def _fleet_probe(args: argparse.Namespace) -> int:
    """Probe the live fleet's awake units and print what the run found.

    The units named narrow the run; with none named, every awake unit of the
    live fleet is probed. Probed figures, units left alone for work in flight,
    contended units, fields the rig could not read or timed from off it, alerts,
    links and failures are each printed as their own line. A `ProbeError` is
    printed to stderr and returns 1; otherwise the report's exit code is
    returned, which is 1 when a unit or a link failed and 0 otherwise.
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


def _fleet_key(args: argparse.Namespace) -> int:
    """Print the key of a unit of `expose: lan`, alone on stdout, for a client.

    Refused (3) for a unit that is not `lan`, and for one whose key `mcgyvr
    emit` has not made yet; an unknown unit, a config that cannot be read and a
    key file that cannot be trusted are errors (1). Nothing is made here.
    """
    from mcgyvr import unitkey
    from mcgyvr.config import EXPOSE_LAN, ConfigError
    from mcgyvr.config import load as load_config
    from mcgyvr.exits import Exit
    from mcgyvr.serving import exposure

    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    unit = config.units.get(args.unit)
    if unit is None or unit.relief or unit.crew:
        print(f"error: no unit of your fleet is named {args.unit!r}", file=sys.stderr)
        return Exit.ERROR
    exposed = exposure(unit.expose, address=unit.address, launcher=unit.launcher)
    if exposed != EXPOSE_LAN:
        print(
            f"refused: {args.unit} is expose: {exposed}, so it listens on "
            "127.0.0.1 alone and asks for no key; state `expose: lan` on it and "
            "run `mcgyvr emit` to give it one",
            file=sys.stderr,
        )
        return Exit.REFUSED
    try:
        key = unitkey.for_address(unit.address)
    except unitkey.UnitKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    if key is None:
        print(
            f"refused: {args.unit} has no key yet; `mcgyvr emit` makes it the "
            "first time it writes the unit",
            file=sys.stderr,
        )
        return Exit.REFUSED
    print(key)
    return Exit.OK


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Add the `fleet` subparser to `sub`, with its `use`, `probe`, `alerts` and
    `key` subcommands, each one's arguments and the command its `func` runs.
    """

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
        help="the promoted folder to run live (one with no lock date by plain name)",
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
    fkey = fleet_sub.add_parser(
        "key",
        help=(
            "print the key a unit of `expose: lan` asks every request for, for "
            "a client of yours (mcgyvr's own requests send it already)"
        ),
    )
    fkey.add_argument("unit", metavar="UNIT", help="the unit, as fleet.yaml names it")
    fkey.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
    )
    fkey.set_defaults(func=_fleet_key)
