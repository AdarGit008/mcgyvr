"""The `mcgyvr serve`/`manage`/`emit` ladder commands.

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

from mcgyvr.cli.common import CONFIG_DEFAULT_HELP, _named_path
from mcgyvr.cli.fleet_live import _admitted_live, _live
from mcgyvr.cli.sizing import _hosts_wanted, _model_specs, _resolve_hosts, _scans


def _serve(args: argparse.Namespace) -> int:
    """Hand a card back, or take it back, by name.

    A thin front over the door's two steps for the operator who wants to say it
    by hand, and it is deliberately **not** gated by
    ``serving.enable_sleep_wake``: that switch exists so that mcgyvr does not
    decide to take a card down without being asked, and a person typing this has
    asked (the lab's sleep-wake plan, §15).

    ``sleep`` drains before it evicts. Every slot of every bound the card serves
    is taken first, so a dispatch that had already been admitted finishes rather
    than having its container killed under it — the one thing whole-card
    eviction is not allowed to do (D8 of the same plan). The census that
    decides *whether* to sleep is a reading and this is a hold, and between the
    two a dispatch can start, which is why both exist. Then the card goes down
    the way the ladder manager puts one down (:func:`mcgyvr.wake.put_down`): at
    vLLM's level 2 where every unit can, stopped otherwise.
    """
    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    from mcgyvr import wake as wakelib
    from mcgyvr.capacity import Capacity, SlotUnavailableError

    # A live wake starts units, so it is admitted as a live run is, and refused
    # while the rigs do not read as locked: nothing is restored for it, because
    # carrying a plan out is not decided. A sleep is always admitted: stopping
    # starts nothing unapproved, and it is the way out.
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
    """Run the ladder manager: Jev sleeps and wakes the ladder's units by its queue.

    Optional per fleet: a ladder with no unit that can sleep and wake, or one
    whose ``serving.enable_sleep_wake`` is off, is told so and nothing is built
    — no pool, no capacity, no file under the rendezvous directory, no network.
    Otherwise the manager reads the queue on each local rung every
    ``manager.interval_s``, asks Jev only where more than one answer is legal,
    and throws the same two switches ``mcgyvr serve`` does
    (:class:`mcgyvr.wake.CardSwitches`). See :mod:`mcgyvr.ladder_manager`.

    It may wake a card, so it is admitted as a live wake is: refused while the
    live fleet's rigs do not read as locked. It runs until interrupted;
    ``--once`` is one tick, for a person who wants to see what it would read.
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

    # One manager per host: a second would throw switches on the same cards
    # from streaks and a dwell of its own, sleeping what the first just woke.
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
    """Each card's memory in MiB from the rig files, by host and card index.

    The records ``emit`` sizes against (:func:`_scans`), resolved to the hosts
    this ladder names (:func:`_resolve_hosts`); a host with no record is not in
    the answer, and the ladder manager then makes no room on it and says so at
    start.
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
    """:func:`_manage` once this process is the host's only ladder manager."""
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
    # The card the decisions run on is never slept: the `jev.unit` when one
    # is bound (every decision asks it), the fast rung when not.
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
    """``block`` with ``resolved``'s fields filled where the block states none.

    What an operator wrote wins: a key the block already states is left alone,
    and only what is missing is stamped. The same rule holds inside
    ``launch``, which is free-form and may already carry sizing keys
    (``vram_gb``, ``shards``, ...) beside the argv/env/volumes the emit layer
    resolves.
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
    """Whether ``block`` already declares a model spec rather than the table's.

    Mirrors :func:`mcgyvr.serving.declared_models`' own skip condition: a block
    that states anything under ``launch`` (or ``hf_cache``, ``room_mib``,
    ``kv_cache_memory_bytes``) is sized from what it declares, so a stamp must
    not paper over those keys with the shipped table's numbers.
    """
    return bool(
        block.get("launch")
        or block.get("hf_cache") is not None
        or block.get("room_mib") is not None
        or block.get("kv_cache_memory_bytes") is not None
    )



def _sizing_keys(spec: ModelSpec) -> dict[str, Any]:
    """The scalar sizing keys a shipped dense row declares, for re-sizing.

    A dev unit sized from the shipped table declares nothing in ``fleet.yaml``,
    so once ``launch`` carries the resolved argv/env/volumes,
    :func:`mcgyvr.serving.declared_models` reads it as a declared spec of all
    zeros and refuses the next emit. Copying the table's scalar facts keeps the
    two emits the same bytes. MoE rows and geometries are never copied: those
    reach emit only through an operator's own declaration, which the stamp
    already preserves.
    """
    keys: dict[str, Any] = {}
    for key in ("vram_gb", "disk_gb", "ram_gb", "kv_cache_dtype_k", "kv_cache_dtype_v"):
        value = getattr(spec, key, None)
        if value:
            keys[key] = value
    return keys



def _render_launch_block(launch: Mapping[str, Any]) -> str:
    """The ``launch:`` block of one unit, indented to sit at four spaces."""
    dumped = yaml.safe_dump(dict(launch), sort_keys=True, width=200)
    lines = ["    launch:"]
    lines.extend(
        f"      {line}" if line else "" for line in dumped.rstrip("\n").splitlines()
    )
    return "\n".join(lines)



def _render_stamped_fleet(fleet: Mapping[str, Any]) -> str:
    """Render a stamped ``fleet.yaml`` with the schema renderer, plus ``launch``.

    :func:`mcgyvr.initialize.render_fleet` renders every unit field but does not
    know how to spell a free-form ``launch`` mapping, so the launch blocks are
    rendered here and spliced into its output at the field's own place — the
    schema comments and the operator's ordering survive.
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
    """Write ``text`` beside ``path`` and move it over atomically."""
    atomic.write(path, text)



def _stamp_launch(
    config: Config,
    units: Iterable[Unit],
    *,
    sleep_mode: bool,
    specs: Iterable[ModelSpec],
) -> Path | None:
    """Stamp ``resolved_launch`` into each serving unit of ``config``'s fleet.yaml.

    Returns the file written, or ``None`` when there is no fleet.yaml beside the
    config (a single merged document has none) or nothing changed. The write is
    atomic and idempotent: a unit that already states a field keeps it.

    A unit that was sized from the shipped table declares no model spec in
    ``fleet.yaml``; once its ``launch`` carries the resolved argv, the loader
    would read it as a declared spec of zeros. The table's scalar facts are
    stamped beside the launch for exactly those units so a re-emit re-sizes to
    the same argv.
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
    """Write one compose file per launch spec for the ladder's serving units.

    A launch spec is what comes up together, which is a host wherever a host's
    units are co-residents and is one model wherever they take turns on a port.
    Nothing is started. See :mod:`mcgyvr.emit` — this hands the operator a
    launch spec and stops.
    """
    try:
        config = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    # A locked setup is rendered from what it states and never sized, so it is
    # decided before a scan is read: a locked unit needs none.
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
    # A source's URL names a *route* to a machine; a scan is filed under what
    # the machine calls *itself*. Those are two names for one rig and they
    # rarely match, so the two are reconciled here, once, before either the
    # refusal below or `units_for` looks a host up.
    scans = _resolve_hosts(scans, hosts.values())

    # Refusal is decided before a single model is looked up, because it is the
    # earlier question and the more useful answer: told "no spec for
    # qwen3-coder-30b" about a rig nobody has measured, an operator goes and
    # edits the model name, which was never the problem.
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

    # A model the table does not carry, and a model too large for the machine
    # it was bound to, are both refusals rather than failures: nothing is
    # broken, mcgyvr is declining to write a launch spec it cannot stand
    # behind. A caller branching on the code should read them the same way it
    # reads an unscanned host. A malformed capability table is a real error.
    specs = _model_specs()
    try:
        units = units_for(config, scans, specs=specs, ctx_per_slot=args.ctx_per_slot)
        # What each unit's sizing says beside its answer (`Fit.notes`), such as
        # a host memory figure it has not read; a fitting unit's `why` reaches
        # no one else. Before `hold_together`, which may refuse the set.
        for unit in sorted(units, key=lambda u: u.key.slug):
            for note in unit.fit.notes:
                print(f"note: {unit.key.slug}: {note}", file=sys.stderr)
        # `hold_together` returns a sentence for each host it cut into
        # alternatives; they are printed as warnings below so the cut is not
        # only a second `wrote ...` line.
        cut = hold_together(units, scans)
    except UnitError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except CapabilityTableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    out = Path(args.out) if args.out else Path.cwd()
    # vLLM's sleep mode and its unauthenticated routes, only where the config
    # asked mcgyvr to sleep and wake cards (`emit.sleep_mode`).
    asleep = emit_sleep_mode(config)

    # Before the files and before the check, because it is the fact both of
    # them are about: a host that was cut into alternatives has N files where it
    # had one, only one of which is ever up.
    for said in cut:
        print(f"warning: {said}", file=sys.stderr)

    # `--check` is the whole answer to "the config moved and the rig did not".
    # It is here rather than in the door because this is the function that
    # knows what a config implies, and the comparison must be against the
    # bytes this same call would write — `check_all` shares the plan with
    # `emit_all` so the two cannot drift apart the way the thing they are
    # detecting did.
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
        # A ladder describing a shape mcgyvr will not stand behind, not a
        # failure to render one: same exit code as `hold_together`'s refusal,
        # which is the other thing that reads a unit set and declines it.
        print(f"refused: {exc}", file=sys.stderr)
        return Exit.REFUSED
    except (EmitError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return Exit.ERROR

    # The same launch that was just written to compose is stamped back into
    # the config's fleet.yaml, so a later lock of this setup is emittable and
    # admissible. A stamp failure is an error: a compose file and a fleet.yaml
    # that disagree are the exact drift this command exists to prevent.
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
    """The config's ``fleet.yaml`` when it is a locked setup, else ``None``.

    Read with :mod:`mcgyvr.fleet.files`, because the run config drops
    ``fleets`` and ``unit_id`` as the lock's, and those are what a locked emit
    is cut by.
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
    """Emit a locked setup: each unit's stated launch, one file per fleet per rig.

    ``setup`` is the directory the setup was loaded from: a unit's
    ``launch.seccomp`` names a profile relative to it, and that profile is
    written beside the compose file that names it.
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
    """Say which compose files stopped matching the config, and stop.

    Nothing here writes: an operator re-emits and then restarts the container,
    and doing the first half for them would leave a rig serving argv that no
    file on disk has ever named. The exit code is
    :attr:`~mcgyvr.exits.Exit.MISMATCH`, which is what ``scan`` already returns
    for a record and a machine that stopped agreeing — this is that fact about
    a different pair.

    A missing file and a stale one are printed differently on purpose. The
    first is one command away from correct; the second is two, and the second
    of those is on the rig.

    **A third kind, and it is not a drift of any planned file.** `unplanned`
    names a launch spec on disk, for a rig this ladder still binds, that this
    config would not write — the `compose.<host>.yml` an earlier emit left
    behind when the host stopped fitting together, holding every unit on one
    card. It is reported at the same severity because while it is there
    :func:`mcgyvr.wake.compose_for` finds more than one launch spec for the card
    and declines to wake it. The repair is the other one, and the sentence says
    so — a drifted file is re-emitted, this one is deleted.
    """
    if not drifted and not leftover:
        # The files this config would write, asked of the function that writes
        # them.
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
    """Serve the orchestrator rung as the agent, at an Anthropic Messages address.

    Refuses a config whose orchestrator is not ``type: mcorch`` — the command
    has nothing to serve then — and, under the live fleet (:func:`_live`), a
    fleet live admission does not admit (:func:`_admitted_live`), as ``run``
    is. Binds the
    loopback and the facade's own port unless told otherwise; prints where it
    listens and the writer id it journals under, so a reader can find the
    transcript; runs until interrupted.
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


def add_parser(sub: argparse.ArgumentParser) -> None:
    """Register the `serve`, `manage` and `emit` commands."""

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
    # Not defaulted and not required: a unit that declares `window` is emitted
    # at it, and this flag speaks for the units that declare none. A unit with
    # no window from either is refused (`serving._window_for`), because the
    # cache, the `-c` on the argv and the `--n-cpu-moe` floor are all priced
    # against it.
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



def add_mcorch_parser(sub: argparse.ArgumentParser) -> None:
    """Register `mcorch serve` (called between fleet and run)."""

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

