""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.detect import DEFAULT_PROBE_TARGETS, detect, targets_for
from mcgyvr.exits import Exit
from mcgyvr.fleet.roots import (
    RIGS_SHOWN,
)

if TYPE_CHECKING:  #
    pass


def _detect(args: argparse.Namespace) -> int:
    hosts = tuple(args.host or ())
    found = detect(targets_for(hosts) if hosts else DEFAULT_PROBE_TARGETS)

    if found.gpus:
        print("GPU:")
        for gpu in found.gpus:
            print(f"  {gpu.name} — {gpu.size}  ({gpu.how})")
        if found.has_remote_backend:
            print("  (this machine's card — the remote backends below have their own)")
    else:
        print("GPU: none detected")

    context = []
    if found.cpu_count is not None:
        context.append(f"{found.cpu_count} CPUs")
    if found.ram_gb is not None:
        context.append(f"{found.ram_gb:g} GB RAM")
    if context:
        print(f"Host: {', '.join(context)}")

    print(f"Docker: {'yes' if found.docker else 'no'}  ({found.provenance['docker']})")

    if found.backends:
        print("\nBackends reachable:")
        for host in found.hosts_answering:
            if hosts:
                print(f"  {host}:")
            for backend in (b for b in found.backends if b.host == host):
                indent = "    " if hosts else "  "
                protocol = f"api={backend.api}"
                print(f"{indent}{backend.name:<20} {backend.base_url:<30} {protocol}")
                if backend.models:
                    for model in backend.models:
                        print(f"{indent}    listed: {model}")
                else:
                    print(f"{indent}    (reachable, but reports no models)")
                print(f"{indent}    {backend.how}")
    else:
        print("\nBackends reachable: none")

    if found.notes:
        print("\nWhat could not be determined, and what it costs:")
        for note in found.notes:
            print(f"  - {note}")
    return 0


def _scan(args: argparse.Namespace) -> int:
    ""
    if args.rig is not None:
        return _scan_rig(args.rig, as_json=args.json)
    from mcgyvr.serving import rigfile

    reading = scan_module.reading(
        model_stores=tuple(Path(store) for store in (args.model_store or ()))
    )
    #
    #
    #
    #
    try:
        saved = rigfile.save(rigfile.LOCAL, reading)
    except (OSError, rigfile.RigFileError) as exc:
        print(
            f"error: this machine's rig file could not be written: {exc}",
            file=sys.stderr,
        )
        return Exit.ERROR
    measured = saved.now.scan
    changes = () if saved.before is None else rigfile.moved(saved.before, saved.now)
    drift = [change for change in changes if rigfile.is_hardware(change)]
    path = saved.path

    if args.json:
        #he
        #
        #
        #
        sys.stdout.write(measured.to_json())
        _report_moved(saved.before, changes, sys.stderr)
        return Exit.OK

    machine = measured.machine
    print(f"{machine.host} ({machine.id}), kernel {machine.kernel}")
    if measured.gpus:
        for gpu in measured.gpus:
            print(
                f"  GPU {gpu.index}    {gpu.name} — "
                f"{gpu.vram.free_mib} MiB free of {gpu.vram.total_mib} MiB"
            )
    else:
        print("  GPU      none found")
    if measured.memory is not None:
        print(
            f"  RAM      {measured.memory.available_gb:.1f} GB available of "
            f"{measured.memory.total_gb:.1f} GB"
        )
    if measured.cpu is not None:
        print(f"  CPU      {measured.cpu.cores} cores, {measured.cpu.threads} threads")
    if measured.bandwidth is not None:
        print(
            f"  Memory   {measured.bandwidth.measured_gbps:.1f} GB/s "
            f"({measured.bandwidth.how})"
        )
    if measured.disk is not None:
        device = f" on {measured.disk.device}" if measured.disk.device else ""
        total = (
            f" of {measured.disk.total_gb:.1f} GB"
            if measured.disk.total_gb is not None
            else ""
        )
        print(
            f"  Disk     {measured.disk.free_gb:.1f} GB free{total} "
            f"at {measured.disk.path}{device}"
        )
    for model in measured.models_on_disk:
        quant = f" {model.quant}" if model.quant else ""
        print(
            f"  Model    {model.name}{quant} "
            f"({model.size_bytes / 1024 / 1024 / 1024:.1f} GiB)"
        )
    for note in measured.notes:
        print(f"  - {note}")
    if saved.kept:
        print(
            f"\nKept the record at {path}: it knew its cards, and this read "
            "could not read them"
        )
    else:
        print(f"\nRecorded at {path}")

    _report_moved(saved.before, changes, sys.stdout)
    return Exit.MISMATCH if drift else Exit.OK


def _scan_rig(rig: str, *, as_json: bool) -> int:
    ""
    from mcgyvr.serving import rigfile

    try:
        target = rigfile.path(rig)
        try:
            before = rigfile.read(rig)
        except rigfile.RigFileError as exc:
            print(f"note: the rig file there is replaced: {exc}", file=sys.stderr)
            before = None
    except rigfile.RigFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.USAGE
    try:
        reading = scan_module.read_over(scan_module.Reach.ssh(rig))
    except scan_module.Unreachable:
        print(
            f"error: {rig} did not answer ssh (BatchMode: your own ssh config and "
            "keys, no password prompt); no rig file is written",
            file=sys.stderr,
        )
        return Exit.ERROR
    except (scan_module.ScannerMissing, scan_module.ScanFailed):
        print(
            f"error: {rig} answered ssh but the scan did not run there (it needs "
            "python3); no rig file is written",
            file=sys.stderr,
        )
        return Exit.ERROR
    try:
        saved = rigfile.save(rig, reading)
    except rigfile.RigFileError as exc:
        print(f"error: {exc}; no rig file is written", file=sys.stderr)
        return Exit.ERROR
    now = saved.now
    out = sys.stderr if as_json else sys.stdout
    if as_json:
        sys.stdout.write(now.to_json())
    print(f"{rig}: {now.hostname}, docker {now.docker or 'not read'}", file=out)
    for card in now.cards:
        print(f"  card {card.index}  {card.said()}", file=out)
    if now.ram_total_gb is not None:
        print(f"  RAM     {now.ram_total_gb:.1f} GB", file=out)
    if now.cpu_cores is not None or now.cpu_threads is not None:
        print(
            f"  CPU     {now.cpu_cores or '?'} cores, {now.cpu_threads or '?'} threads",
            file=out,
        )
    if now.bandwidth_gbps is not None:
        print(
            f"  Memory  {now.bandwidth_gbps:.1f} GB/s ({now.bandwidth_how})",
            file=out,
        )
    if now.disk_path is not None:
        device = f" on {now.disk_device}" if now.disk_device else ""
        print(
            f"  Disk    {now.disk_free_gb} GB free"
            f"{f' of {now.disk_total_gb} GB' if now.disk_total_gb is not None else ''}"
            f" at {now.disk_path}{device}",
            file=out,
        )
    for model in now.models_on_disk:
        quant = f" {model.quant}" if model.quant else ""
        print(
            f"  Model   {model.name}{quant} "
            f"({model.size_bytes / 1024 / 1024 / 1024:.1f} GiB)",
            file=out,
        )
    if now.private_ipv4 is not None:
        print(f"  Address {now.private_ipv4} ({now.private_ipv4_how})", file=out)
    else:
        print(f"  Address no private IPv4 recorded: {now.private_ipv4_how}", file=out)
    for note in now.notes:
        print(f"  - {note}", file=out)
    if before is not None:
        for change in rigfile.moved(before, now):
            print(f"moved since {before.read_at}: {change.said()}", file=out)
    if saved.kept:
        print(
            f"\nKept the rig file at {target}: it knew its cards, and this read "
            "could not read them",
            file=out,
        )
    else:
        print(f"\nSaved as {target}", file=out)
    return Exit.OK


def _users_count(value: str) -> int:
    ""
    if value == "single":
        return 1
    try:
        count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"users must be `single` or a number, not {value!r}"
        ) from None
    if count < 1:
        raise argparse.ArgumentTypeError(f"users must be at least 1, not {count}")
    return count


def _recommend(args: argparse.Namespace) -> int:
    ""
    try:
        made = recommend_module.plan(
            profile=args.profile,
            users=args.users,
            hosts=args.host,
            model_stores=args.model_store,
        )
    except (recommend_module.RecommendError, recommend_module.CatalogError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    sys.stdout.write(json.dumps(made, indent=2, sort_keys=True) + "\n")
    return Exit.OK


def _report_moved(before: Any, changes: Sequence[Any], stream: TextIO) -> None:
    ""
    if before is None or not changes:
        return
    print(f"moved since the record of {before.read_at}:", file=stream)
    for change in changes:
        print(f"  {change.said()}", file=stream)


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    ""

    det = sub.add_parser(
        "detect",
        help="show what can run the work, and how each fact was detected",
    )
    det.add_argument(
        "--host",
        action="append",
        default=[],
        metavar="HOST",
        help=(
            "also sweep this machine for backends, by name or address "
            "(repeatable; default: localhost only). Hardware detection stays "
            "local — a remote rig is described by what it serves"
        ),
    )
    det.set_defaults(func=_detect)

    sca = sub.add_parser(
        "scan",
        help="measure this machine, record it, and report what changed since",
    )
    sca.add_argument(
        "--json",
        action="store_true",
        help=(
            "write the scan to stdout and nothing else — the wire format the "
            "remote transport parses"
        ),
    )
    sca.add_argument(
        "--rig",
        metavar="RIG",
        default=None,
        help=(
            "scan RIG instead, over your own ssh (read-only), and save it as the "
            f"serving door's rig file RIG.json in {RIGS_SHOWN}, which a door run "
            "from an install holds the rig to; says what moved since the last"
        ),
    )
    sca.add_argument(
        "--model-store",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "a directory holding *.gguf and *.safetensors checkpoints to "
            "inventory as models-on-disk, in addition to the weights dir "
            "(repeatable)"
        ),
    )
    sca.set_defaults(func=_scan)

    rec = sub.add_parser(
        "recommend",
        help="print one JSON plan: which checkpoint and engine serve a profile",
    )
    rec.add_argument(
        "--profile",
        required=True,
        choices=recommend_module.PROFILES,
        help="the usage profile to place for",
    )
    rec.add_argument(
        "--users",
        required=True,
        type=_users_count,
        metavar="N|single",
        help="how many users the placement serves: `single` or a positive number",
    )
    rec.add_argument(
        "--host",
        action="append",
        required=True,
        metavar="RIG",
        help="a rig to re-read over ssh and place on (repeatable)",
    )
    rec.add_argument(
        "--model-store",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "a directory on the rig holding *.gguf checkpoints (repeatable); "
            "when any fits, recommend only from it"
        ),
    )
    rec.set_defaults(func=_recommend)
