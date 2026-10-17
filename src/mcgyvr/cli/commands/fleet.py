""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.fleet.roots import (
    LIVE_FILE_SHOWN,
)

if TYPE_CHECKING:  #
    pass


def _fleet_alerts(args: argparse.Namespace) -> int:
    ""
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
            #
            #
            root = live_fleet_dir()
        except LiveFleetError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    for combination, entries in pulled(journal, root).items():
        for entry in entries:
            print(f"{combination} {entry['unit_id']} {entry['field']}")
    return 0


def _fleet_use(args: argparse.Namespace) -> int:
    ""
    from mcgyvr.fleet.promote import PromoteRefusedError, use
    from mcgyvr.fleet.roots import layout_of

    try:
        switch = use(args.name)
    except (PromoteRefusedError, OSError) as exc:
        #
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
        #
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
    ""
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


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    ""

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
