"""The `ladder` commands: sleep and wake a card, emit the ladder.

`serve` puts one card to sleep or wakes it through the serving door; `emit`
writes one compose file per launch spec, or compares the files already on disk
with what the config plans. Nothing here starts a process: emitting writes a
file, and the door does the switching.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcgyvr import atomic, unitkey
from mcgyvr.capability import (
    CapabilityTableError,
)
from mcgyvr.config import (
    FLEET_FILENAME,
    LAUNCHER_NATIVE,
    Config,
    ConfigError,
)
from mcgyvr.config import load as load_config
from mcgyvr.emit import (
    Drift,
    EmitError,
    LockedLaunchError,
    check_all,
    check_locked,
    emit_all,
    emit_locked,
    is_locked,
    keyed,
    listening,
    listens_beyond_loopback,
    locked_keyed,
    locked_open,
    planned_locked_paths,
    planned_paths,
    resolved_launch,
    states_host,
    unplanned,
    unplanned_locked,
)
from mcgyvr.emit import sleep_mode as emit_sleep_mode
from mcgyvr.exits import Exit
from mcgyvr.fleet.files import FleetFileError, load_fleet
from mcgyvr.initialize import (
    render_fleet,
)
from mcgyvr.serving import (
    ROLE_SERVE,
    ModelSpec,
    Unit,
    UnitError,
    declared_models,
    hold_together,
    units_for,
)
from mcgyvr.serving.gatelib import LOCAL_RIGS

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _named_path
from mcgyvr.cli.fleet_live import _admitted_live, _live
from mcgyvr.cli.sizing import _hosts_wanted, _model_specs
from mcgyvr.serving.rigfile import recorded_scans, resolve_hosts


def _native_status(host: str) -> int:
    """Print one line per native unit this machine supervises, or has.

    Only a name of this machine (`gatelib.LOCAL_RIGS`) is read here; a macOS
    or Windows rig's native units are read through the door
    (`python -m mcgyvr.serving.run read --host RIG`), and any other host is
    refused.
    """
    from mcgyvr.serving import gatelib, native

    if host not in gatelib.LOCAL_RIGS:
        print(
            f"error: {host} is not this machine; a rig's native units are "
            "read through the door (`python -m mcgyvr.serving.run read --host "
            f"{host}`)",
            file=sys.stderr,
        )
        return Exit.REFUSED
    rows = native.status()
    if not rows:
        print("no native unit on this machine")
    for row in rows:
        print(
            f"{row['unit']}: {row['state']}, port {row['port']}, "
            f"server pid {row['server_pid']}, {row['restarts']} restarts, "
            f"{row['backend']}; log {row['log']}"
        )
    return Exit.OK


def _serve(args: argparse.Namespace) -> int:
    """Put one card to sleep, or wake it, through the serving door.

    The host is the one a unit's `address` names. `Exit.REFUSED` covers a fleet
    that is live and not admitted as locked, a card the door will not switch,
    and a card whose slots could not be drained for the sleep; a door that
    exited without switching the card is `Exit.ERROR`.
    """
    if args.direction == "status":
        return _native_status(args.host)
    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    from mcgyvr import wake as wakelib
    from mcgyvr.capacity import Capacity, SlotUnavailableError

    # A fleet that is live but does not read as locked is refused before the
    # door is opened: `_admitted_live` prints what would have to be cleaned or
    # restored, and its detail is the refusal. A fleet that is not live has no
    # door aimed at it, so it goes on to the switch below.
    if (
        args.direction == "wake"
        and _live(config)
        and _admitted_live(config) is not None
    ):
        return Exit.REFUSED

    try:
        if args.direction == "wake":
            made = wakelib.wake(config, args.host)
        else:
            card = wakelib.card_named(config, args.host)
            capacity = Capacity.of(config)
            with capacity.drain(
                card.sources, timeout=wakelib.drain_timeout(config, card)
            ):
                made = wakelib.sleep(config, args.host)
    except wakelib.WakeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except SlotUnavailableError as busy:
        print(f"error: {busy}", file=sys.stderr)
        return Exit.REFUSED

    if not made.ok:
        from mcgyvr.fleet.roots import data_home
        from mcgyvr.serving.gatelib import DOOR_LOG

        # The data folder is each system's own (and $MCGYVR_DATA's when set),
        # so the log is named where it is, not where Linux keeps it.
        print(
            f"error: the door exited {made.code} on `serve {made.direction}` for "
            f"{made.host} — read its envelope in the door's log under "
            f"{data_home() / DOOR_LOG}{os.sep}",
            file=sys.stderr,
        )
        return Exit.ERROR
    how = {
        "sleep": "resting at level 2, its processes kept",
        "down": "stopped",
        "wake": "woken in its processes",
        "up": "started",
    }.get(made.direction, made.direction)
    print(
        f"{made.host} {args.direction}: {how}, {made.seconds:.1f}s "
        f"({made.compose_file})"
    )
    return Exit.OK


def _merge_resolved(
    block: Mapping[str, Any], resolved: Mapping[str, Any]
) -> dict[str, Any]:
    """A unit block with what the emitted launch resolved filled into it.

    What the block already states wins: `engine`, `image`, `container` and
    `hf_cache` are filled only where the block is empty, and `launch` is merged
    key by key, so a stated argv or env survives the stamp.
    """
    merged = dict(block)
    for key in ("engine", "image", "container", "hf_cache"):
        if key in resolved and not merged.get(key):
            merged[key] = resolved[key]
    stated = merged.get("launch")
    launch = dict(stated) if isinstance(stated, Mapping) else {}
    for key, value in (resolved.get("launch") or {}).items():
        if key not in launch or launch[key] is None:
            launch[key] = value
    if launch:
        merged["launch"] = launch
    return merged


def _block_declares(block: Mapping[str, Any]) -> bool:
    """Whether the unit block states a launch of its own, wholly or in part.

    Any of `launch`, `hf_cache`, `room_mib` or `kv_cache_memory_bytes` means a
    person has said how the unit runs, so a stamp adds no sizing figures to it.
    """
    return bool(
        block.get("launch")
        or block.get("hf_cache") is not None
        or block.get("room_mib") is not None
        or block.get("kv_cache_memory_bytes") is not None
    )


def _sizing_keys(spec: ModelSpec) -> dict[str, Any]:
    """The sizing figures a model spec states, as keys a launch records.

    Only the figures the spec holds are returned, so a figure it does not state
    is left out of the stamped launch rather than written as a zero.
    """
    keys: dict[str, Any] = {}
    for key in ("vram_gb", "disk_gb", "ram_gb", "kv_cache_dtype_k", "kv_cache_dtype_v"):
        value = getattr(spec, key, None)
        if value:
            keys[key] = value
    return keys


def _atomic_write(path: Path, text: str) -> None:
    """Write `text` to `path` through `atomic.write`, staging a file beside it."""
    atomic.write(path, text)


def _stamp_launch(
    config: Config,
    units: Iterable[Unit],
    *,
    sleep_mode: bool,
    specs: Iterable[ModelSpec],
) -> Path | None:
    """Write each unit's rendered launch back into `fleet.yaml`; return its path.

    None says there was nothing to stamp: the config has no path, no
    `fleet.yaml` sits there, or no unit block changed. `EmitError` says the
    config has no path, the fleet cannot be read, or the write failed.
    """
    if config.path is None:
        raise EmitError("the config has no path, so fleet.yaml cannot be stamped")
    fleet_path = config.path / FLEET_FILENAME
    if not fleet_path.is_file():
        return None
    try:
        fleet = load_fleet(fleet_path.read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise EmitError(f"{fleet_path}: cannot be read to stamp — {exc}") from exc

    catalogue = {spec.name: spec for spec in specs} | declared_models(config)
    blocks = dict(fleet.get("units") or {})
    changed = False
    for unit in units:
        resolved = resolved_launch(unit, sleep_mode=sleep_mode)
        spec = catalogue.get(unit.model)
        for name in unit.rungs:
            block = blocks.get(name)
            if not isinstance(block, Mapping):
                continue
            declared = _block_declares(block)
            merged = _merge_resolved(block, resolved)
            if (
                not declared
                and spec is not None
                and spec.geometry is None
                and not spec.moe
            ):
                launch = dict(merged.get("launch") or {})
                for key, value in _sizing_keys(spec).items():
                    launch.setdefault(key, value)
                merged["launch"] = launch
            # Pin the unit to the card(s) it occupies, so a rig of several
            # cards can be locked: the lock reads ``launch.shards`` and refuses
            # a unit that names none (fleet/lock.py). The rig name comes from
            # the block's ``rig`` (what init wrote: ``localhost`` for a local
            # machine, the host for a remote one), never ``unit.host`` --
            # spans() matches the first shard's rig to the unit's own ``rig``,
            # and a local machine's hostname is not ``localhost``.
            rig = block.get("rig")
            if isinstance(rig, str) and rig:
                launch = dict(merged.get("launch") or {})
                launch.setdefault(
                    "shards",
                    [{"rig": rig, "gpu": gpu} for gpu in unit.cards],
                )
                merged["launch"] = launch
            if merged != block:
                blocks[name] = merged
                changed = True
    if not changed:
        return None
    fleet["units"] = blocks
    try:
        _atomic_write(fleet_path, render_fleet(fleet))
    except OSError as exc:
        raise EmitError(f"{fleet_path}: cannot be written — {exc}") from exc
    return fleet_path


def _emit(args: argparse.Namespace) -> int:
    """Write one compose file per launch spec for the ladder's units, or check.

    A locked `fleet.yaml` is emitted from what it states; otherwise the units
    are sized from the recorded scans of the hosts the units' addresses name,
    and nothing is sized for a host that was never scanned. `--check` writes
    nothing and reports drift instead; a write pass stamps the launch it
    rendered back into `fleet.yaml`.
    """
    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    # A locked fleet states its own launches, so it is emitted from the fleet
    # file and never sized from scans.
    try:
        fleet = _locked_fleet(config)
    except (FleetFileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    if fleet is not None:
        return _emit_locked(fleet, args, config.path, config)

    scans = recorded_scans()
    try:
        hosts = _hosts_wanted(config)
    except UnitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    # Scans are recorded under a rig's id and its hostname, while a unit names
    # its host in `address`: what the ladder names is resolved onto the scans
    # here — a local name onto this machine's — before a host is looked for by
    # name below.
    scans = resolve_hosts(scans, hosts.values())

    # An unscanned host is a refusal, not a warning: a unit is sized from
    # measured free VRAM, RAM and disk, and a launch spec for a machine nobody
    # measured would be a guess wearing a file name. Every unscanned host is
    # named, so one run says all there is to scan.
    unscanned = sorted({host for host in hosts.values() if host not in scans})
    if unscanned:
        for host in unscanned:
            print(
                f"refused: {host} has never been scanned. A unit is sized from "
                f"measured free VRAM, RAM and disk, so there is nothing here to "
                f"size it from — run `mcgyvr scan` on {host} first.",
                file=sys.stderr,
            )
        return Exit.REFUSED

    # The model specs sizing starts from: what the shipped knowledge records
    # say about each model, plus the model registry's entries, so a unit is
    # sized from a known geometry before any host is asked. A table that
    # cannot be read raises `CapabilityTableError`, caught with the unit
    # errors below as an error rather than a refusal.
    specs = _model_specs()
    try:
        units = units_for(config, scans, specs=specs, ctx_per_slot=args.ctx_per_slot)
        # The notes a fit carries are information for the operator, not
        # refusals: they say what a figure was measured or assumed from, and
        # the unit is emitted anyway.
        for unit in sorted(units, key=lambda u: u.key.slug):
            for note in unit.fit.notes:
                print(f"note: {unit.key.slug}: {note}", file=sys.stderr)
        # Units sharing a host are held together: alternatives where the card
        # they share cannot sum them all onto it, and a refusal where those
        # that are up do not fit card or host memory together.
        cut = hold_together(units, scans)
    except UnitError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except CapabilityTableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    out = Path(args.out) if args.out else Path.cwd()
    # Sleep mode decides which documents carry the sleep routes, so it is read
    # from the config once and handed to every render and check below.
    asleep = emit_sleep_mode(config)

    # Being cut into alternatives is a warning, not a refusal: every file is
    # written, and a person brings up the one they mean and deletes the rest.
    for said in cut:
        print(f"warning: {said}", file=sys.stderr)

    # `--check` compares what is already under `--out` with what this config
    # plans and writes nothing: the planned files that drifted, the spec files
    # the config does not plan, and the names it does plan are what it reports.
    # A write pass writes every planned file, and then stamps each unit's
    # rendered launch back into `fleet.yaml`, so the file states what was just
    # emitted rather than what an older config said.
    if args.check:
        try:
            drifted = check_all(units, root=out, sleep_mode=asleep)
        except UnitError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return Exit.REFUSED
        except (EmitError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return Exit.ERROR
        return _report_drift(
            drifted,
            unplanned(units, out, sleep_mode=asleep),
            planned_paths(units, out, sleep_mode=asleep),
        )

    try:
        written = emit_all(units, root=out, sleep_mode=asleep)
    except UnitError as exc:
        # Refused, not failed: the unit set does not fit the rig as measured.
        # `emit_all` plans and refuses every file before it writes any, so the
        # output directory is left as it was.
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except (EmitError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    # A unit of `expose: lan` is given its key now that its compose file names
    # it, and every unit that listens other than it did before says so.
    try:
        _exposure(units, config)
    except unitkey.UnitKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    # The launch just rendered is stamped back into `fleet.yaml`, so `serve`
    # reads the launch a unit actually runs rather than deriving
    # it again, and a block that states its own launch keeps what it states.
    # A fleet that cannot be read or written is an error, and the files already
    # written are left as they are.
    try:
        stamped = _stamp_launch(config, units, sleep_mode=asleep, specs=specs)
    except EmitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    for unit in sorted(units, key=lambda u: u.key.slug):
        rungs = ", ".join(unit.rungs) or "no rung"
        print(
            f"{unit.key.slug}  gpu {unit.gpu}, {unit.width.value} slots "
            f"({unit.width.how})  for {rungs}"
        )
    print()
    for compose in written:
        print(f"wrote {compose}")
    if stamped is not None:
        print(f"stamped {stamped}")
    print("\nNothing was started. `docker compose -f <file> up -d` is yours to run.")
    return Exit.OK


def _exposure(units: Iterable[Unit], config: Config) -> None:
    """Make the key of each keyed unit that has none, and say where the units
    listen when it is not where their address reaches them.

    A keyed unit (`expose: lan`, stated or read off an address on another host)
    is named with where it listens and its key file (`_key_note`), or warned
    about when its own launch keeps it on this machine's loopback. A serving
    unit in a container that keeps `expose: local` while its address names
    another host is warned about (`_local_but_remote`), and so is one whose
    launch states a host beyond this machine with no key. UnitKeyError says a
    key file is there and cannot be trusted.
    """
    for unit in sorted(units, key=lambda u: u.key.slug):
        names = ", ".join(unit.rungs) or unit.key.slug
        if unit.launcher == LAUNCHER_NATIVE or unit.role != ROLE_SERVE:
            continue
        shared = any(
            (declared := config.units.get(name)) is not None and declared.rider_slots
            for name in unit.rungs
        )
        where = listening(unit)
        if keyed(unit):
            path, made = unitkey.ensure(unit.host, unit.port)
            if where in LOCAL_RIGS:
                _keyed_on_loopback(
                    unit.key.slug,
                    where,
                    "launch",
                    "drop the --host or LLAMA_ARG_HOST it states",
                )
            else:
                _key_note(
                    unit.key.slug,
                    where,
                    path,
                    made,
                    names,
                    unit.host,
                    unit.port,
                    shared,
                )
        elif states_host(unit):
            if listens_beyond_loopback(unit):
                print(
                    f"warning: {unit.key.slug}: its launch states where it "
                    f"listens, {where}, beyond this machine, and it asks for no "
                    f"key; state `expose: lan` on {names} for one",
                    file=sys.stderr,
                )
        elif unit.host not in LOCAL_RIGS:
            _local_but_remote(unit, names, shared)


def _local_but_remote(unit: Unit, names: str, shared: bool) -> None:
    """Warn that a unit stating `expose: local` is one its own address, which
    names another host, never reaches; and, for a unit shared with riders, how
    that shows on the rig."""
    said = (
        f"warning: {unit.key.slug}: listens on 127.0.0.1 alone, as its unit states "
        f"(expose: local), and its address names {unit.host}: that name reaches "
        "the machine's network address, never 127.0.0.1, so nothing dials it by "
        f"that name, this machine included. State `expose: lan` on {names}, or "
        "leave `expose` out (an address on another host is `lan` by default), to "
        "listen on every interface behind a key mcgyvr makes"
    )
    if shared:
        first = unit.rungs[0] if unit.rungs else unit.key.slug
        said += (
            ". It is shared with riders, so the rig agent advertises it with no "
            f"free slot and says `unit {first!r} is shared with no free slot: its "
            "server does not say what it has in flight` once on its stderr; "
            "riders are matched elsewhere and no ride fails. On "
            f"{unit.host}, address the unit as http://localhost:{unit.port} in "
            "the rig agent's own config"
        )
    print(said, file=sys.stderr)


def _keyed_on_loopback(slug: str, where: str, stated: str, remedy: str) -> None:
    """Warn that `expose: lan` gave `slug` a key while its own `stated` (launch
    or lock) keeps it listening on this machine's `where` alone."""
    print(
        f"warning: {slug}: expose: lan gives it a key, but its {stated} states "
        f"{where}, so it listens there alone; {remedy}",
        file=sys.stderr,
    )


def _key_note(
    slug: str,
    where: str,
    path: Path,
    made: bool,
    names: str,
    host: str,
    port: int,
    shared: bool,
) -> None:
    """Say that `slug` listens on `where` behind the key in `path`; for a unit
    shared with riders on another host, that the rig agent there needs the same
    file and `mcgyvr emit` does not put it there."""
    kept = "made its key in" if made else "its key is in"
    said = (
        f"note: {slug}: listens on {where} (expose: lan) and asks every request "
        f"for its key; {kept} {path} (mode 0600). mcgyvr's own requests from this "
        f"machine send it; `mcgyvr fleet key {names.split(', ')[0]}` prints it for "
        "a client of yours"
    )
    if shared and host not in LOCAL_RIGS:
        said += (
            f". It is shared with riders, and the rig agent on {host} looks its key "
            f"up in its own data folder, in {unitkey.KEYS_DIR}/ under the name of "
            "the address its own config gives the unit: "
            f"{path.name} for http://{host}:{port}, localhost-{port}.env for "
            f"http://localhost:{port}. `mcgyvr emit` does not put it there: copy "
            "this file there under that name at mode 0600, or the agent does not "
            "share the unit and says once on its stderr which file it lacks"
        )
    print(said, file=sys.stderr)


def _locked_fleet(config: Config) -> dict[str, Any] | None:
    """The parsed `fleet.yaml` when it is locked, or None when there is none.

    None when the config has no path, when no `fleet.yaml` sits there, and when
    no unit in it carries a `unit_id` — a fleet that does not state its own
    launches is sized from scans instead.
    """
    if config.path is None:
        return None
    where = config.path / FLEET_FILENAME
    if not where.is_file():
        return None
    fleet = load_fleet(where.read_text(encoding="utf-8"))
    return fleet if is_locked(fleet) else None


def _emit_locked(
    fleet: dict[str, Any],
    args: argparse.Namespace,
    setup: Path | None = None,
    config: Config | None = None,
) -> int:
    """Write, or check, what a locked fleet states; return an `Exit`.

    `--ctx-per-slot` is refused here: a locked unit serves the window its
    `launch.argv` states, so there is nothing for the flag to set. `setup` is
    where the fleet's own files live, read to find a seccomp profile a unit
    names.
    """
    if args.ctx_per_slot is not None:
        print(
            "refused: a locked unit serves the window its launch.argv states, "
            "so --ctx-per-slot has nothing to set",
            file=sys.stderr,
        )
        return Exit.REFUSED
    out = Path(args.out) if args.out else Path.cwd()
    try:
        if args.check:
            return _report_drift(
                check_locked(fleet, out, setup),
                unplanned_locked(fleet, out, setup),
                planned_locked_paths(fleet, out, setup),
            )
        written = emit_locked(fleet, out, setup)
        for name, host, port, where in locked_keyed(fleet):
            path, made = unitkey.ensure(host, port)
            if where in LOCAL_RIGS:
                _keyed_on_loopback(name, where, "lock", "lock it again")
                continue
            declared = config.units.get(name) if config is not None else None
            shared = declared is not None and declared.rider_slots > 0
            _key_note(name, where, path, made, name, host, port, shared)
    except LockedLaunchError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except (EmitError, UnitError, OSError, unitkey.UnitKeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    for name, host in locked_open(fleet):
        print(
            f"warning: {name}: its lock has it listen on {host} with no key, and "
            "it is `expose: local` (stated, or its address names this machine); "
            "state `expose: lan` on it for a key, or lock it again for 127.0.0.1",
            file=sys.stderr,
        )
    for compose in written:
        print(f"wrote {compose}")
    print("\nNothing was started. `docker compose -f <file> up -d` is yours to run.")
    return Exit.OK


def _report_drift(
    drifted: Sequence[Drift], leftover: Sequence[Path], planned: Sequence[Path]
) -> Exit:
    """Report what drifted: `Exit.OK` when nothing did, else `Exit.MISMATCH`.

    `drifted` are planned files whose content differs or that are missing,
    `leftover` the spec files this config does not plan, and `planned` the
    names it does — printed when there is nothing to report, so the run says
    what the rig is served from.
    """
    if not drifted and not leftover:
        # Nothing differs: naming the files this config plans says what the rig
        # is served from, which is what an operator ran `--check` to learn.
        for path in planned:
            print(f"{path.name} is what this config emits")
        return Exit.OK

    for path in leftover:
        print(
            f"mismatch: {path} is a launch spec this config does not write. "
            f"`mcgyvr emit` leaves the files it no longer plans where they are, "
            f"so this is an older cut of the same rig — and while it is there a "
            f"wake finds more than one launch spec for that card and will not "
            f"pick one. Bring up what you mean and delete it; nothing here "
            f"deletes a file that may be what is running.",
            file=sys.stderr,
        )

    for item in sorted(drifted, key=lambda d: d.path.name):
        if item.missing:
            print(
                f"mismatch: no compose file at {item.path} — this config "
                f"names the rig and nothing has been emitted for it. Run "
                f"`mcgyvr emit` to write it.",
                file=sys.stderr,
            )
            continue
        print(
            f"mismatch: {item.path} is not what this config emits. The file "
            f"was written from an older config, so the rig is serving argv "
            f"nobody is reading any more. Run `mcgyvr emit` and then restart "
            f"the unit — the file alone changes nothing that is already up.",
            file=sys.stderr,
        )
        for line in item.diff():
            print(f"  {line}", file=sys.stderr)
    return Exit.MISMATCH


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `serve` and `emit` subparsers and their flags."""

    srv = sub.add_parser(
        "serve",
        help="put a card to sleep, or wake it, through the serving door",
    )
    srv.add_argument(
        "direction",
        choices=("sleep", "wake", "status"),
        help=(
            "sleep drains every slot the card serves, then rests it at vLLM "
            "level 2 where every unit is vLLM and has the sleep route, and "
            "stops it otherwise; wake brings it back the way it went; status "
            "lists the native units this machine (--host localhost) keeps up"
        ),
    )
    srv.add_argument(
        "--host",
        required=True,
        metavar="HOST",
        help="the rig, as the host in a unit's `address` names it",
    )
    srv.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
    )
    srv.set_defaults(func=_serve)

    emi = sub.add_parser(
        "emit",
        help="write a compose file per launch spec for the ladder's serving units",
    )
    emi.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
    )
    emi.add_argument(
        "--out",
        default=None,
        metavar="DIR",
        help="where the compose files are written (default: the current directory)",
    )
    # The window per slot this run serves, for units that declare none: the
    # flag is the product the launch arguments and the cache law are both fed,
    # so the two cannot disagree. A unit that declares its own `window` is
    # emitted at that window, and a flag that contradicts the declaration is
    # refused rather than preferred.
    emi.add_argument(
        "--ctx-per-slot",
        type=int,
        metavar="N",
        help=(
            "the window this run serves per slot, for units that declare no "
            "`window` of their own; `-c` is this times the slot count, "
            "and the cache law is fed the same product. A unit that declares "
            "its window is emitted at that window, and a flag that contradicts "
            "a declaration is refused rather than preferred"
        ),
    )
    emi.add_argument(
        "--check",
        action="store_true",
        help=(
            "compare the files already under --out with what this config "
            "emits and write nothing: exit 4 when they disagree, naming each "
            "file and the lines that moved. A config edited without "
            "re-emitting is two configurations, and the rig goes on serving "
            "the older one"
        ),
    )
    emi.set_defaults(func=_emit)
