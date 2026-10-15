"""The `mcgyvr detect`/`scan`/`recommend` commands.

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
    """Measure this machine, record it as its rig file, and say what moved.

    ``--json`` exits :attr:`Exit.OK` even when the scan disagrees with the
    record, and that asymmetry is the point rather than an oversight.
    ``--json`` is not a quieter mode of this command for a person; it prints
    the wire format that :func:`mcgyvr.scan.Scan.from_json` reads — the same
    shape the one reader prints on a rig. The exit-code
    channel belongs to the human-facing command, which keeps exit 4: a rig
    that lost a DIMM or a card still delivers its measurement down the wire
    and the mismatch goes to stderr, where the operator reads it. The record is
    this machine's rig file (``localhost``, :mod:`mcgyvr.serving.rigfile`), the
    one record of a machine; what moved since it is said, and exit 4 is kept
    for the hardware changing under it (a card, RAM, cores, bandwidth).
    """
    if args.rig is not None:
        return _scan_rig(args.rig, as_json=args.json)
    from mcgyvr.serving import rigfile

    reading = scan_module.reading(
        model_stores=tuple(Path(store) for store in (args.model_store or ()))
    )
    # Recorded before anything is reported, and recorded even when it
    # disagrees with the last record. A mismatch is a successful measurement of
    # a machine that changed, not a failed one; withholding it would leave the
    # stale record in place for the next run to disagree with all over again.
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
        # stdout is the wire format `Scan.from_json` reads — the same shape the
        # one reader prints on the rig. One banner line
        # here and the scan stops parsing, so everything a person would read
        # goes to stderr.
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
    """Scan ``rig`` over ssh and save it as the door's rig file; say what moved.

    The read is the read-only one ``mcgyvr recommend`` takes (the one reader,
    shipped over the user's own ssh config and keys with ``BatchMode``), and
    the file is what a user-mode door run holds the rig to
    (:mod:`mcgyvr.serving.rigfile`). A rig that does not answer writes
    nothing.
    """
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
    """``single`` or a positive count — the two spellings ``recommend`` takes."""
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
    """Print one JSON plan: which checkpoint and engine serve ``args.profile``.

    Read-only: the rigs are re-read over the sanctioned detection ssh path and
    nothing is written, woken or slept. The plan is the only thing on stdout.
    """
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
    """What moved since this machine's last record, one line each."""
    if before is None or not changes:
        return
    print(f"moved since the record of {before.read_at}:", file=stream)
    for change in changes:
        print(f"  {change.said()}", file=stream)


def add_parser(sub: argparse.ArgumentParser) -> None:
    """Register `detect`, `scan`, `recommend`."""

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

