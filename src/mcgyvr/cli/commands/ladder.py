"""The `ladder` commands: sleep and wake a card, manage the ladder, emit it.

`serve` puts one card to sleep or wakes it through the serving door; `manage`
runs the ladder manager, which sleeps and wakes the ladder's units by the queue
Jev answers on; `emit` writes one compose file per launch spec, or compares the
files already on disk with what the config plans; and `mcorch serve` serves the
orchestrator rung as an Anthropic Messages API address for a harness. Nothing
here starts a process: emitting writes a file, and the door does the switching.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from mcgyvr import atomic
from mcgyvr.capability import (
    CapabilityTableError,
)
from mcgyvr.config import (
    FLEET_FILENAME,
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
    planned_locked_paths,
    planned_paths,
    resolved_launch,
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
    ModelSpec,
    Unit,
    UnitError,
    declared_models,
    hold_together,
    units_for,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _named_path
from mcgyvr.cli.fleet_live import _admitted_live, _live
from mcgyvr.cli.sizing import _hosts_wanted, _model_specs, _resolve_hosts, _scans


def _serve(args: argparse.Namespace) -> int:
    """Put one card to sleep, or wake it, through the serving door.

    The host is the one a unit's `address` names. `Exit.REFUSED` covers a fleet
    that is live and not admitted as locked, a card the door will not switch,
    and a card whose slots could not be drained for the sleep; a door that
    exited without switching the card is `Exit.ERROR`.
    """
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
        print(
            f"error: the door exited {made.code} on `serve {made.direction}` for "
            f"{made.host} — read its envelope in the door's log under "
            f"~/.local/state/mcgyvr/door/",
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


def _manage(args: argparse.Namespace) -> int:
    """Run the ladder manager: tick on the config's interval, switching cards.

    Nothing to manage is `Exit.OK`, and so is a loop stopped by an interrupt.
    `Exit.REFUSED` covers a live fleet that is not admitted as locked, and a
    manager lock this run could not hold.
    """
    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    from mcgyvr import ladder_manager
    from mcgyvr.pressure import exclusive

    why = ladder_manager.applicable(config)
    if why is not None:
        print(f"nothing to manage: {why}")
        return Exit.OK

    if _live(config) and _admitted_live(config) is not None:
        return Exit.REFUSED

    # One manager per host: the lock answers True when it is held, False when
    # another `mcgyvr manage` holds it, and anything else when no lock could be
    # taken — both of those refuse, with a different sentence each.
    with exclusive(ladder_manager.MANAGER_LOCK) as held:
        if held is not True:
            print(
                "error: another `mcgyvr manage` is running on this host"
                if held is False
                else "error: no lock could be taken under the rendezvous "
                "directory, so mcgyvr cannot tell whether another `mcgyvr "
                "manage` is running on this host",
                file=sys.stderr,
            )
            return Exit.REFUSED
        return _manage_held(args, config)


def _card_mib(config: Config) -> dict[str, dict[int, int]]:
    """Card memory in MiB, by host and card index, for the ladder's cards.

    The figures come from the recorded scans; an empty mapping means no scan of
    those hosts could be read, which is not the same as hosts with no cards.
    """
    from mcgyvr import wake as wakelib
    from mcgyvr.serving import cards

    hosts = {card.host for card in cards(config).values()}
    try:
        scans = _resolve_hosts(_scans(), hosts)
    except OSError:
        return {}
    return wakelib.card_rooms({host: scans[host] for host in hosts if host in scans})


def _manage_held(args: argparse.Namespace, config: Config) -> int:
    """Manage the ladder with the host's manager lock held: build, say, run.

    The manager is built from the config: capacity measured through a gauge,
    the rung Jev answers on, the ladder as `View` sees it, the card switches,
    the pressure reading and the cooling tracker. `--once` takes one tick.
    """
    from mcgyvr import fleet_manager, ladder_manager
    from mcgyvr import wake as wakelib
    from mcgyvr.capacity import Capacity, CapacityError
    from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
    from mcgyvr.local_pool import source_map
    from mcgyvr.pressure import Board, Gauge, HostCooling, Pressure, RungCooling

    pool = source_map(config)
    fast = fleet_manager.fast_rung(config, pool)
    if fast is None:
        print("error: no local rung for Jev to run on", file=sys.stderr)
        return Exit.ERROR
    gauge = Gauge()
    try:
        capacity = Capacity.of(config, gauge=gauge)
    except CapacityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    stated = config.units[fast.name].request_timeout_s
    bounds = ladder_manager.Bounds.of(config)
    board = Board()
    # The rung Jev answers on, whose card is never slept: `jev.unit` when the
    # config names one, else the fast rung, since Jev has to run on a local one.
    jev = config.get("jev.unit") or fast.name
    view = ladder_manager.View.of(config, jev=jev)
    switches = wakelib.CardSwitches(config, capacity, card_mib=_card_mib(config))
    manager = ladder_manager.Manager(
        view,
        bounds,
        pressure=Pressure(pool, capacity, gauge),
        switches=switches,
        decide=ladder_manager.decide_on(
            pool,
            fast.name,
            timeout_s=DEFAULT_REQUEST_TIMEOUT_S if stated is None else stated,
        ),
        cooling=RungCooling(pool, hold_s=bounds.dwell_s, shared=HostCooling()),
        say=print,
        publish=board.publish,
    )
    print(
        f"managing {', '.join(view.resident)}; can sleep and wake: "
        f"{', '.join(ladder_manager.sleepable_rungs(config))}; Jev runs on "
        f"{jev}; every {bounds.interval_s:g}s"
    )
    for rung, alone in wakelib.left_alone(config).items():
        print(f"note: {rung} is left alone: {alone}")
    for rung in ladder_manager.sleepable_rungs(config):
        why = switches.why_no_room(rung)
        if why is not None:
            print(f"note: no room is made for {rung}: {why}")
    try:
        ladder_manager.run(
            manager, interval_s=bounds.interval_s, ticks=1 if args.once else None
        )
    except KeyboardInterrupt:
        print("stopped")
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


def _render_launch_block(launch: Mapping[str, Any]) -> str:
    """One unit's `launch` mapping as YAML, indented to sit in a unit block.

    `yaml.safe_dump` sorts the keys; `launch:` is written at four spaces and
    its lines at six, so the block lands inside a unit at indent two.
    """
    dumped = yaml.safe_dump(dict(launch), sort_keys=True, width=200)
    lines = ["    launch:"]
    lines.extend(
        f"      {line}" if line else "" for line in dumped.rstrip("\n").splitlines()
    )
    return "\n".join(lines)


def _render_stamped_fleet(fleet: Mapping[str, Any]) -> str:
    """Render `fleet.yaml` with each unit's launch written into its own block.

    `render_fleet` writes the schema's units and cannot render a `launch`
    mapping, so the launches are lifted out before it runs and put back where
    the schema's commented `launch` leaf sits, under the unit they belong to.
    """
    launches: dict[str, Mapping[str, Any]] = {}
    render_units: dict[str, Any] = {}
    for name, block in (fleet.get("units") or {}).items():
        block = dict(block)
        launch = block.pop("launch", None)
        if isinstance(launch, Mapping) and launch:
            launches[name] = launch
        render_units[name] = block
    text = render_fleet({**fleet, "units": render_units})

    current: str | None = None
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            name = line[2:-1].strip()
            current = name if name in launches else None
        elif current is not None and line.startswith("    # launch:  # "):
            out.append(_render_launch_block(launches[current]))
            continue
        out.append(line)
    return "\n".join(out) + "\n"


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
            if merged != block:
                blocks[name] = merged
                changed = True
    if not changed:
        return None
    fleet["units"] = blocks
    try:
        _atomic_write(fleet_path, _render_stamped_fleet(fleet))
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
        return _emit_locked(fleet, args, config.path)

    scans = _scans()
    try:
        hosts = _hosts_wanted(config)
    except UnitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    # Scans are recorded under a rig's id and its hostname, while a unit names
    # its host in `address`: what the ladder names is resolved onto the scans
    # here — a local name onto this machine's — before a host is looked for by
    # name below.
    scans = _resolve_hosts(scans, hosts.values())

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

    # The launch just rendered is stamped back into `fleet.yaml`, so `serve`
    # and the manager read the launch a unit actually runs rather than deriving
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
    fleet: dict[str, Any], args: argparse.Namespace, setup: Path | None = None
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
    except LockedLaunchError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except (EmitError, UnitError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
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


def _mcorch_serve(args: argparse.Namespace) -> int:
    """Serve the orchestrator rung as an Anthropic Messages API address.

    Refused unless `orchestrator.type` is mcorch, and for a fleet that is live
    and not admitted as locked; a role the config leaves unbound is refused too.
    Binds the facade, serves until interrupted, and closes the socket.
    """
    from mcgyvr.config import MCORCH
    from mcgyvr.decision import UnboundRoleError
    from mcgyvr.local_pool import SourceUnavailableError
    from mcgyvr.mcorch import bind, serve
    from mcgyvr.mcorch.authoring import AuthoringUnavailableError

    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR
    if config.get("orchestrator.type") != MCORCH:
        print(
            f"refused: orchestrator.type is {config.get('orchestrator.type')!r}, "
            f"and `mcgyvr mcorch serve` serves only `orchestrator.type: {MCORCH}`. "
            "Set it, with `orchestrator.unit`, `orchestrator.authoring` and "
            "`jev.unit`, or use the orchestrator the config has.",
            file=sys.stderr,
        )
        return Exit.REFUSED
    if _live(config) and _admitted_live(config) is not None:
        return Exit.REFUSED
    try:
        bound = bind.bind(config, journal_dir=bind.journal_dir(config))
    except (UnboundRoleError, SourceUnavailableError, AuthoringUnavailableError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED

    address = args.bind if args.bind else serve.DEFAULT_BIND
    port = args.port if args.port is not None else serve.FACADE_PORT
    server = serve.make_server(bind.facade(bound), bind=address, port=port)
    host, bound_port = str(server.server_address[0]), int(server.server_address[1])
    print(f"mcorch serving http://{host}:{bound_port} as writer {bound.writer}")
    print(f"transcript: {bound.transcript.path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return Exit.OK


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `serve`, `manage` and `emit` subparsers and their flags."""

    srv = sub.add_parser(
        "serve",
        help="put a card to sleep, or wake it, through the serving door",
    )
    srv.add_argument(
        "direction",
        choices=("sleep", "wake"),
        help=(
            "sleep drains every slot the card serves, then rests it at vLLM "
            "level 2 where every unit is vLLM and has the sleep route, and "
            "stops it otherwise; wake brings it back the way it went"
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

    man = sub.add_parser(
        "manage",
        help=(
            "let Jev sleep and wake the ladder's units by the queue on it "
            "(runs until interrupted)"
        ),
    )
    man.add_argument(
        "--config",
        default=None,
        type=_named_path,
        metavar="PATH",
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
    )
    man.add_argument(
        "--once",
        action="store_true",
        help="read the queue and decide once, then stop",
    )
    man.set_defaults(func=_manage)

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


def add_mcorch_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `mcorch` parser and its `serve` subparser."""

    mcorch = sub.add_parser(
        "mcorch",
        help="serve the orchestrator rung as the agent a harness talks to",
    )
    mcorch_sub = mcorch.add_subparsers(dest="mcorch_command", required=True)
    mserve = mcorch_sub.add_parser(
        "serve",
        help=(
            "serve an Anthropic Messages API address for a harness to point at "
            "(ANTHROPIC_BASE_URL); needs `orchestrator.type: mcorch`"
        ),
    )
    mserve.add_argument(
        "--config",
        default=None,
        type=_named_path,
        help=f"config to read (default: {CONFIG_DEFAULT_HELP})",
    )
    mserve.add_argument(
        "--bind",
        default=None,
        help=(
            "the address to listen on (default: the loopback; a LAN or tailnet "
            "address lets another machine's harness reach it)"
        ),
    )
    mserve.add_argument(
        "--port",
        default=None,
        type=int,
        help="the port to listen on (default: the facade's own)",
    )
    mserve.set_defaults(func=_mcorch_serve)
