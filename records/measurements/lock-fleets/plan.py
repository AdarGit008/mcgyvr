#!/usr/bin/env python3
"""lock-fleets planner: one use's frozen run order, its RUNS.md and its wrappers.

Owner, 2026-09-15: "lock-fleets, general campign to lock new fleets in". A use is
a folder beside this file holding ``use.json`` — why it exists and the checks it
adds — and everything the order is made of comes from ``fleet-setup/fleet.yaml``,
``fleet-setup/policy.yaml``, ``fleet-setup/digests-<rig>.json`` and
``tools/runs/hosts.json``:

    uv run --no-sync python records/measurements/lock-fleets/plan.py freeze --use USE

writes ``<use>/RUNS.md`` and the use's numbered wrappers under
``tools/runs/campaigns/lock-fleets/<use>/``. Once the log holds a row it refuses:
a run is expandable until its first measurement, and frozen from then on
(``okf/must-read/always.md``). ``drive.sh`` and ``assemble_evidence.py`` read the
frozen order back with :func:`read_runs`, so each door command, artifact name and
run id is spelled once, here. Same inputs, same bytes.

The order, per rig (owner, 2026-09-15): every combination of every fleet layout,
K cold starts each, interleaved by cold start (c1 of every combination, then c2,
then c3); then every switch move (``mcgyvr.fleet.lock._switch_moves`` over each
fleet's ``next``), K runs each, interleaved the same way. Moves are last on every
rig. A llama.cpp combination is a campaign unit run; a vLLM group is the door's
own serve and read cycle: ``serve up``, ``read --probe`` its units, ``read
--probe U --load WxN`` per unit, ``serve down``.

It sits under records/measurements/ with the lock's last assembler
(``records/measurements/fleet-setup-2026-09-13/srv2/assemble_evidence.py``) and
the quick check's driver (``records/measurements/quick-check-2026-09-15/``):
code that plans, drives and reads a measurement from outside the door. What runs
under the door is a campaign step (``tools/runs/campaigns/``) or a driver that
proves the door first (``tools/runs/drivers/``, ``tests/test_one_door.py``
ALLOWED); this does neither.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CAMPAIGN = "lock-fleets"
STEPS = Path("tools") / "runs" / "campaigns" / CAMPAIGN
#: Cold starts per combination and runs per move (owner, 2026-09-15).
K = 3
DOOR = "python -m mcgyvr.serving.run"
WINDOW_DATE = "@WINDOW_DATE@"
COMPOSE_DIR = "@COMPOSE_DIR@"
READ_RUN_ID = "@READ_RUN_ID@"
USE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
FROZEN_HEADER = "## Frozen order"
IDLE_HEADER = "## Idle minutes"
LOG_HEADER = "## Log"
CAPS_HEADER = "## Checks this use adds, from data"
LOG_COLUMNS = (
    "entry",
    "rig",
    "started_at",
    "ended_at",
    "exit",
    "run id",
    "envelope",
    "output",
)
IDLE_COLUMNS = ("event", "rig", "at", "idle minutes")
ENTRY_COLUMNS = (
    "entry",
    "kind",
    "fleet",
    "to",
    "units",
    "run",
    "artifact or run id",
    "door command",
)
CAP_COLUMNS = ("rig", "fleet", "unit", "cap_mib", "from")


class PlanRefusedError(Exception):
    """The order cannot be planned, or a frozen one read back."""


def lockfleets() -> ModuleType:
    """``tools/runs/campaigns/lock-fleets/lockfleets.py``: the code's own copy."""
    name = "lockfleets_campaign"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, REPO / STEPS / "lockfleets.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def use_dir(root: Path, use: str) -> Path:
    if not USE_NAME.match(use):
        raise PlanRefusedError(f"use {use!r} is not [a-z0-9-]+")
    return root / "records" / "measurements" / CAMPAIGN / use


def wrappers_dir(root: Path, use: str) -> Path:
    return root / STEPS / use


@dataclass(frozen=True)
class Use:
    """What one use of the campaign says about itself (``<use>/use.json``)."""

    name: str
    why: tuple[str, ...]
    #: Rigs whose fleet.yaml rig id the measured snapshot must still name.
    keep_rig_pins: tuple[str, ...]
    #: Rigs whose multi-unit combinations get a per-unit card cap.
    unit_caps_on: tuple[str, ...]
    #: fleet -> the directory its live compose files are in; the emitted dev
    #: compose must be byte-identical to each.
    compose_must_match_live: dict[str, str]


def load_use(root: Path, use: str) -> Use:
    path = use_dir(root, use) / "use.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanRefusedError(f"{path} cannot be read: {exc}") from exc
    if doc.get("use") != use:
        raise PlanRefusedError(f"{path} names use {doc.get('use')!r}, not {use!r}")
    return Use(
        name=use,
        why=tuple(str(line) for line in doc.get("why") or ()),
        keep_rig_pins=tuple(str(r) for r in doc.get("keep_rig_pins") or ()),
        unit_caps_on=tuple(str(r) for r in doc.get("unit_caps_on") or ()),
        compose_must_match_live={
            str(k): str(v) for k, v in (doc.get("compose_must_match_live") or {}).items()
        },
    )


@dataclass(frozen=True)
class Entry:
    """One door invocation of the frozen order."""

    id: str
    kind: str
    fleet: str
    to: str
    units: tuple[str, ...]
    run: str
    #: The artifact a campaign step writes, or where the run id comes from.
    artifact: str
    #: What follows ``python -m mcgyvr.serving.run``, placeholders unfilled.
    argv: tuple[str, ...]

    @property
    def rig(self) -> str:
        return self.id.rsplit("-", 1)[0]

    @property
    def wrapper(self) -> str:
        """The wrapper a campaign step runs, relative to the root, or ``""``."""
        if self.kind not in ("unit", "move"):
            return ""
        return self.argv[self.argv.index("--step") + 1]

    @property
    def step(self) -> str:
        """The step name gate 5 mints the run id from: the stem, number dropped."""
        return re.sub(r"^\d+-", "", Path(self.wrapper).stem)

    @property
    def suffix(self) -> str:
        return self.argv[self.argv.index("--suffix") + 1] if "--suffix" in self.argv else ""

    def run_id(self, window_date: str, read_run_id: str = "") -> str:
        """The id this entry's run files under."""
        if self.kind in ("unit", "move"):
            return f"{window_date}-{CAMPAIGN}-{self.step}"
        if self.kind in ("serve-up", "serve-down"):
            return f"{window_date}-live-{self.rig}-{self.kind}-{self.suffix}"
        return read_run_id

    def envelope(self, window_date: str) -> str:
        """Where the run's files are, relative to the root; a read files in the journal."""
        if self.kind in ("unit", "move"):
            return f"records/evidence/{window_date}-{CAMPAIGN}"
        if self.kind in ("serve-up", "serve-down"):
            return f"records/evidence/{window_date}-live-{self.rig}"
        return "journal"


@dataclass
class Plan:
    use: Use
    entries: list[Entry]
    wrappers: dict[str, str]
    caps: list[dict[str, str]]
    inputs: dict[str, str]
    estimate: dict[str, str]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slots_key(slots: Any) -> tuple[Any, ...]:
    return tuple(tuple(slot) if slot is not None else None for slot in slots or [])


def _combinations(fleet: Mapping[str, Any], rig: str) -> list[Any]:
    """Each distinct combination on ``rig``, named by the first fleet that holds it."""
    lf = lockfleets()
    seen: set[tuple[Any, ...]] = set()
    out: list[Any] = []
    for name, block in (fleet.get("fleets") or {}).items():
        slots = (block.get("layout") or {}).get(rig)
        if slots is None or _slots_key(slots) in seen:
            continue
        seen.add(_slots_key(slots))
        try:
            out.append(lf.side(fleet, name, rig, slots))
        except lf.StepRefusedError as exc:
            raise PlanRefusedError(str(exc)) from exc
    return out


def _moves(fleet: Mapping[str, Any], rig: str) -> list[tuple[Any, Any]]:
    """Each distinct move on ``rig`` over every fleet's ``next``, as (source, target)."""
    from mcgyvr.fleet.lock import _switch_moves

    lf = lockfleets()
    fleets = fleet.get("fleets") or {}
    seen: set[tuple[Any, ...]] = set()
    out: list[tuple[Any, Any]] = []
    for name, block in fleets.items():
        for target in block.get("next") or []:
            if target not in fleets:
                raise PlanRefusedError(f"{name} switches to {target}, which is not a fleet")
            for move_rig, before, after in _switch_moves(
                block.get("layout") or {}, fleets[target].get("layout") or {}
            ):
                key = (_slots_key(before), _slots_key(after))
                if move_rig != rig or key in seen:
                    continue
                seen.add(key)
                try:
                    out.append(lf.move_sides(fleet, rig, name, target))
                except lf.StepRefusedError as exc:
                    raise PlanRefusedError(str(exc)) from exc
    return out


def _door_run(unit: Any) -> list[str]:
    argv = ["--model", unit.model, "--parallel", str(unit.width)]
    argv += ["--ctx-per-slot", str(unit.window)]
    if unit.ubatch is not None:
        argv += ["--ubatch", str(unit.ubatch)]
    return argv


def _compose(rig: str, fleet_name: str) -> str:
    from mcgyvr.serving import spec_name

    return f"{COMPOSE_DIR}/{spec_name(rig, fleet_name)}"


def _wrapper(use: str, number: int, entry_id: str, text: str, body: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        f"# lock-fleets use {use}, entry {entry_id}: {text}; the body is {body}. "
        "Generated by records/measurements/lock-fleets/plan.py.\n"
    )


def plan(root: Path, use_name: str) -> Plan:
    """The frozen order for ``use_name``, from the fleet files under ``root``."""
    from mcgyvr.fleet.files import FleetFileError, load_policy

    lf = lockfleets()
    use = load_use(root, use_name)
    try:
        fleet = lf.load(root)
        policy_path = root / "fleet-setup" / "policy.yaml"
        policy = load_policy(policy_path.read_text(encoding="utf-8"))
    except (lf.StepRefusedError, OSError, FleetFileError) as exc:
        raise PlanRefusedError(str(exc)) from exc
    units = fleet.get("units") or {}
    for name in policy.get("ladder") or []:
        if name not in units:
            raise PlanRefusedError(f"policy ladder names {name!r}, which fleet.yaml lacks")
    hosts_path = root / "tools" / "runs" / "hosts.json"
    hosts = json.loads(hosts_path.read_text(encoding="utf-8"))
    rigs = sorted(
        {rig for block in (fleet.get("fleets") or {}).values() for rig in block.get("layout") or {}}
    )
    for rig in rigs:
        if not isinstance((hosts.get(rig) or {}).get("rig"), dict):
            raise PlanRefusedError(f"tools/runs/hosts.json declares no rig {rig}")
    for rig in use.keep_rig_pins + use.unit_caps_on:
        if rig not in rigs:
            raise PlanRefusedError(f"use.json names rig {rig}, which no fleet places units on")

    entries: list[Entry] = []
    wrappers: dict[str, str] = {}
    number = 0

    def wrap(rig: str, run: str, slug: str, text: str, body: str, args: str) -> tuple[str, str]:
        nonlocal number
        number += 1
        step = f"{use.name}-{rig}-{run}-{slug}"
        path = (STEPS / use.name / f"{number:02d}-{step}.sh").as_posix()
        artifact = f"{step}.json"
        entry_id = f"{rig}-{len([e for e in entries if e.rig == rig]) + 1:02d}"
        wrappers[path] = (
            _wrapper(use.name, number, entry_id, text, body)
            + f"# RUN_ARTIFACTS: {artifact}\n"
            + f'exec bash "$(dirname -- "${{BASH_SOURCE[0]}}")/../{body}" {artifact} {args} "$@"\n'
        )
        return path, artifact

    for rig in rigs:
        combos = _combinations(fleet, rig)
        moves = _moves(fleet, rig)

        def add(kind: str, fleet_name: str, to: str, names: Sequence[str], run: str,
                artifact: str, argv: list[str], rig: str = rig) -> Entry:
            entry = Entry(
                id=f"{rig}-{len([e for e in entries if e.rig == rig]) + 1:02d}",
                kind=kind,
                fleet=fleet_name,
                to=to,
                units=tuple(names),
                run=run,
                artifact=artifact,
                argv=tuple(argv),
            )
            entries.append(entry)
            return entry

        for cold in range(1, K + 1):
            run = f"c{cold}"
            for group in combos:
                names = [u.name for u in group.units]
                if not group.compose:
                    unit = group.units[0]
                    path, artifact = wrap(
                        rig, run, unit.name,
                        f"cold start {run} of {unit.name} ({group.fleet})",
                        "_unit.sh", unit.name,
                    )
                    argv = ["--host", rig, "--campaign", CAMPAIGN, "--step", path]
                    argv += [*_door_run(unit), "--date", WINDOW_DATE]
                    add("unit", group.fleet, "-", names, run, artifact, argv)
                    continue
                compose = _compose(rig, group.fleet)
                next_id = f"{rig}-{len([e for e in entries if e.rig == rig]) + 1:02d}"
                add(
                    "serve-up", group.fleet, "-", names, run,
                    f"run id {WINDOW_DATE}-live-{rig}-serve-up-{use.name}-{next_id}",
                    ["serve", "up", "--host", rig, "--compose", compose,
                     "--suffix", f"{use.name}-{next_id}", "--date", WINDOW_DATE],
                )
                add(
                    "read", group.fleet, "-", names, run,
                    "run id minted by drive.sh just before the read",
                    ["read", "--host", rig, "--probe", *names, "--run-id", READ_RUN_ID],
                )
                for unit in group.units:
                    add(
                        "load", group.fleet, "-", [unit.name], run,
                        "run id minted by drive.sh just before the read",
                        ["read", "--host", rig, "--probe", unit.name,
                         "--load", f"{unit.width}x{unit.window}", "--run-id", READ_RUN_ID],
                    )
                next_id = f"{rig}-{len([e for e in entries if e.rig == rig]) + 1:02d}"
                add(
                    "serve-down", group.fleet, "-", names, run,
                    f"run id {WINDOW_DATE}-live-{rig}-serve-down-{use.name}-{next_id}",
                    ["serve", "down", "--host", rig, "--compose", compose,
                     "--suffix", f"{use.name}-{next_id}", "--date", WINDOW_DATE],
                )
        for count in range(1, K + 1):
            run = f"r{count}"
            for source, target in moves:
                runs = [u for s in (target, source) if not s.compose for u in s.units]
                if not runs:
                    raise PlanRefusedError(
                        f"{source.fleet} -> {target.fleet} on {rig}: neither side is a "
                        "llama.cpp unit, and the door's --model names one"
                    )
                path, artifact = wrap(
                    rig, run, f"{source.fleet}-to-{target.fleet}",
                    f"run {run} of the move {source.fleet} -> {target.fleet} on {rig}",
                    "_move.sh", f"{rig} {source.fleet} {target.fleet}",
                )
                argv = ["--host", rig, "--campaign", CAMPAIGN, "--step", path]
                argv += [*_door_run(runs[0]), "--date", WINDOW_DATE]
                groups = [s for s in (source, target) if s.compose]
                if groups:
                    argv += ["--", _compose(rig, groups[0].fleet)]
                add(
                    "move", source.fleet, target.fleet,
                    [u.name for u in (*source.units, *target.units)],
                    run, artifact, argv,
                )

    caps: list[dict[str, str]] = []
    for rig in use.unit_caps_on:
        declared = hosts[rig]["rig"]
        card, reserve = int(declared["gpu_vram_mib"]), int(declared["gpu_reserve_mib"])
        for group in _combinations(fleet, rig):
            if len(group.units) < 2:
                continue
            for unit in group.units:
                others = [u for u in group.units if u.name != unit.name]
                rooms = [int(units[u.name]["room_mib"]) for u in others]
                caps.append(
                    {
                        "rig": rig,
                        "fleet": group.fleet,
                        "unit": unit.name,
                        "cap_mib": str(card - reserve - sum(rooms)),
                        "from": f"{card} card - {reserve} reserve - "
                        + " - ".join(f"{r} {u.name} room" for r, u in zip(rooms, others, strict=True)),
                    }
                )

    inputs = {
        "fleet-setup/fleet.yaml": _sha256(root / "fleet-setup" / "fleet.yaml"),
        "fleet-setup/policy.yaml": _sha256(root / "fleet-setup" / "policy.yaml"),
        **{
            f"fleet-setup/digests-{rig}.json": _sha256(lf.digests_file(root, rig))
            for rig in rigs
        },
        "tools/runs/hosts.json": _sha256(hosts_path),
        f"records/measurements/{CAMPAIGN}/{use.name}/use.json": _sha256(
            use_dir(root, use.name) / "use.json"
        ),
    }
    return Plan(use, entries, wrappers, caps, inputs, _estimate(root, fleet, entries, rigs))


def _estimate(
    root: Path, fleet: Mapping[str, Any], entries: Sequence[Entry], rigs: Sequence[str]
) -> dict[str, str]:
    """A recorded lower bound per rig, or why there is none.

    Only what a committed lock recorded is added: each unit's wake (the largest
    ``wake_s`` any switch into it recorded, ``records/fleet/<fleet>.json``), its
    warm decode (``records/fleet/rigs/``) over the harness's decode tokens, the
    load's 30 s, and each move's recorded downtime. The prefill, the wait for
    idle and the door's own gates are not recorded anywhere, so they are left
    out, and a unit with no recorded wake leaves its rig with no estimate.
    """
    from mcgyvr.fleet.harness import DECODE_SAMPLES, DECODE_TOKENS, LOAD_LIMIT_S, WARMUP_TOKENS

    wake: dict[str, float] = {}
    downtime: dict[tuple[str, str, str], float] = {}
    decode: dict[str, float] = {}
    for path in sorted((root / "records" / "fleet").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for switch in doc.get("switches") or []:
            for move in switch.get("moves") or []:
                for unit, seconds in (move.get("wake_s") or {}).items():
                    wake[unit] = max(wake.get(unit, 0.0), float(seconds))
                key = (str(move.get("rig")), path.stem, str(switch.get("to")))
                downtime[key] = float(move.get("downtime_s") or 0.0)
    for path in sorted((root / "records" / "fleet" / "rigs").glob("*/*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for unit, entry in (doc.get("approved") or {}).items():
            if isinstance(entry.get("warm_decode_tok_s"), int | float):
                decode[unit] = float(entry["warm_decode_tok_s"])
    out: dict[str, str] = {}
    tokens = WARMUP_TOKENS + DECODE_SAMPLES * DECODE_TOKENS
    for rig in rigs:
        total = 0.0
        missing: list[str] = []
        for entry in (e for e in entries if e.rig == rig):
            if entry.kind == "move":
                key = (rig, entry.fleet, entry.to)
                if key not in downtime:
                    missing.append(f"{entry.fleet}->{entry.to} downtime")
                total += downtime.get(key, 0.0)
                continue
            if entry.kind not in ("unit", "load", "serve-up"):
                continue
            for unit in entry.units:
                if entry.kind in ("unit", "serve-up") and unit not in wake:
                    missing.append(f"{unit} wake")
                if entry.kind in ("unit", "load") and unit not in decode:
                    missing.append(f"{unit} decode")
                total += wake.get(unit, 0.0) if entry.kind != "load" else 0.0
                if entry.kind in ("unit", "load"):
                    total += tokens / decode.get(unit, float("inf")) + LOAD_LIMIT_S
        out[rig] = (
            f"none: no recorded {', '.join(sorted(set(missing)))}"
            if missing
            else f"{total / 60:.0f} min recorded lower bound"
        )
    return out


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(_cell(c) for c in cells) + " |\n"


def _table(columns: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    return (
        _row(columns)
        + "|" + "---|" * len(columns) + "\n"
        + "".join(_row(r) for r in rows)
    )


def render(p: Plan) -> str:
    """RUNS.md for a plan, with an empty log and no idle minutes yet."""
    rigs = sorted({e.rig for e in p.entries})
    text = f"# lock-fleets use `{p.use.name}`\n\n"
    text += (
        "Generated by `records/measurements/lock-fleets/plan.py freeze --use "
        f"{p.use.name}`; the method and every ruling it applies are in "
        "`../README.md`. Nothing above `## Idle minutes` changes once the log holds "
        "a row: a run is expandable until its first measurement, and frozen from "
        "then on.\n\n"
    )
    text += "## Why this use exists\n\n" + "".join(f"- {line}\n" for line in p.use.why)
    text += "\n## Inputs\n\n" + _table(
        ("file", "sha256"), [(f"`{k}`", f"`{v}`") for k, v in p.inputs.items()]
    )
    text += "\n## Order\n\n"
    text += (
        f"Per rig: every combination, {K} cold starts each, interleaved by cold "
        f"start (c1 of every combination, then c2, then c3); then every move, {K} "
        "runs each, interleaved the same way. Moves are last on every rig. Read run "
        "ids are minted by `drive.sh` just before each read.\n\n"
    )
    counts = []
    for rig in rigs:
        mine = [e for e in p.entries if e.rig == rig]
        counts.append(
            (
                rig,
                str(len(mine)),
                str(sum(e.kind == "unit" for e in mine)),
                str(sum(e.kind == "serve-up" for e in mine)),
                str(sum(e.kind == "move" for e in mine)),
                p.estimate[rig],
            )
        )
    text += _table(
        ("rig", "entries", "unit runs", "serve/read cycles", "move runs", "estimate"),
        counts,
    )
    bounds = {rig: p.estimate[rig] for rig in rigs if not p.estimate[rig].startswith("none")}
    text += (
        "\nThe rig that finishes first cannot be named from recorded data, so the "
        "order is the plain one.\n"
        if len(bounds) < len(rigs)
        else "\nFinishes first by the recorded lower bound: "
        + min(bounds, key=lambda r: float(bounds[r].split()[0]))
        + ".\n"
    )
    text += f"\n{CAPS_HEADER}\n\n"
    if p.caps:
        text += (
            "A unit's load peak in a combination of several may not pass the card "
            "less the reserve and the other units' room (hosts.json, fleet.yaml).\n\n"
        )
        text += _table(CAP_COLUMNS, [[c[k] for k in CAP_COLUMNS] for c in p.caps])
    else:
        text += "None.\n"
    text += f"\n{FROZEN_HEADER}\n"
    for rig in rigs:
        text += f"\n### {rig}\n\n"
        text += _table(
            ENTRY_COLUMNS,
            [
                (
                    e.id,
                    e.kind,
                    e.fleet,
                    e.to,
                    "+".join(e.units),
                    e.run,
                    f"`{e.artifact}`" if e.kind in ("unit", "move") else e.artifact,
                    f"`{DOOR} {shlex.join(e.argv)}`",
                )
                for e in p.entries
                if e.rig == rig
            ],
        )
    text += f"\n{IDLE_HEADER}\n\n" + _table(IDLE_COLUMNS, [])
    text += f"\n{LOG_HEADER}\n\n" + _table(LOG_COLUMNS, [])
    return text


@dataclass
class Runs:
    """A frozen RUNS.md, read back."""

    path: Path
    entries: list[Entry]
    caps: list[dict[str, str]]
    idle: list[dict[str, str]] = field(default_factory=list)
    log: list[dict[str, str]] = field(default_factory=list)

    def entry(self, entry_id: str) -> Entry:
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        raise PlanRefusedError(f"{self.path} has no entry {entry_id}")

    def logged(self, entry_id: str) -> dict[str, str] | None:
        """The last log row for ``entry_id``."""
        rows = [row for row in self.log if row["entry"] == entry_id]
        return rows[-1] if rows else None


def _cells(line: str) -> list[str]:
    inner = line.strip()[1:-1]
    cells = re.split(r"(?<!\\) \| ", f" {inner} ")
    return [c.strip().replace("\\|", "|") for c in cells]


def _unquote(cell: str) -> str:
    return cell[1:-1] if len(cell) >= 2 and cell[0] == cell[-1] == "`" else cell


def read_runs(root: Path, use: str) -> Runs:
    """``<use>/RUNS.md`` as entries, caps, idle events and log rows."""
    path = use_dir(root, use) / "RUNS.md"
    if not path.is_file():
        raise PlanRefusedError(f"{path} does not exist: freeze the use first")
    section = ""
    runs = Runs(path, [], [])
    header: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section, header = line, None
            continue
        if line.startswith("### "):
            header = None
            continue
        if not line.startswith("|"):
            header = None
            continue
        if line.startswith("|---"):
            continue
        cells = _cells(line)
        if header is None:
            header = cells
            continue
        row = dict(zip(header, cells, strict=True))
        if section == FROZEN_HEADER:
            command = _unquote(row["door command"])
            if not command.startswith(DOOR + " "):
                raise PlanRefusedError(f"{path}: {row['entry']} is not a door command")
            runs.entries.append(
                Entry(
                    id=row["entry"],
                    kind=row["kind"],
                    fleet=row["fleet"],
                    to=row["to"],
                    units=tuple(row["units"].split("+")),
                    run=row["run"],
                    artifact=_unquote(row["artifact or run id"]),
                    argv=tuple(shlex.split(command[len(DOOR) + 1 :])),
                )
            )
        elif section == CAPS_HEADER:
            runs.caps.append(row)
        elif section == IDLE_HEADER:
            runs.idle.append(row)
        elif section == LOG_HEADER:
            runs.log.append(row)
    return runs


def insert_row(path: Path, section: str, cells: Sequence[str]) -> None:
    """Add one row at the end of ``section``'s table, in place.

    The caller holds the use directory's flock (``drive.sh``): two rigs log into
    one RUNS.md.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.rstrip("\n") == section), None)
    if start is None:
        raise PlanRefusedError(f"{path} has no {section}")
    end = start + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    last = max(i for i in range(start, end) if lines[i].startswith("|"))
    lines.insert(last + 1, _row(cells))
    path.write_text("".join(lines), encoding="utf-8")


def freeze(root: Path, use: str) -> Plan:
    """Write RUNS.md and the wrappers, unless the use is already measured."""
    p = plan(root, use)
    runs_md = use_dir(root, use) / "RUNS.md"
    if runs_md.is_file() and read_runs(root, use).log:
        raise PlanRefusedError(
            f"{runs_md} logs a run: the order is frozen from its first measurement"
        )
    folder = wrappers_dir(root, use)
    folder.mkdir(parents=True, exist_ok=True)
    wanted = {Path(rel).name for rel in p.wrappers}
    for stale in folder.glob("*.sh"):
        if stale.name not in wanted:
            stale.unlink()
    for rel, text in p.wrappers.items():
        path = root / rel
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
    runs_md.write_text(render(p), encoding="utf-8")
    return p


def live_compose(root: Path, use: str, rig: str) -> list[tuple[str, Path]]:
    """``(emitted file name, live file)`` for each compose group ``use.json`` holds
    to its live compose on ``rig``."""
    from mcgyvr.serving import spec_name

    lf = lockfleets()
    u = load_use(root, use)
    fleet = lf.load(root)
    out: list[tuple[str, Path]] = []
    for fleet_name, directory in sorted(u.compose_must_match_live.items()):
        block = (fleet.get("fleets") or {}).get(fleet_name)
        if block is None:
            raise PlanRefusedError(f"use.json names fleet {fleet_name}, which fleet.yaml lacks")
        slots = (block.get("layout") or {}).get(rig)
        if slots is None or not lf.side(fleet, fleet_name, rig, slots).compose:
            continue
        name = spec_name(rig, fleet_name)
        out.append((name, Path(os.path.expanduser(directory)) / name))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan.py", description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=str(REPO), help="the tree the fleet files are in")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("freeze")
    one.add_argument("--use", required=True)
    one = sub.add_parser("entries")
    one.add_argument("--use", required=True)
    one.add_argument("--rig", required=True)
    one = sub.add_parser("argv")
    one.add_argument("--use", required=True)
    one.add_argument("--entry", required=True)
    one = sub.add_parser("log")
    for name in ("--use", "--entry", "--rig", "--window-date"):
        one.add_argument(name, required=True)
    for name in ("--started", "--ended", "--exit", "--read-run-id", "--output"):
        one.add_argument(name, default="")
    one = sub.add_parser("event")
    for name in ("--use", "--rig", "--event", "--at"):
        one.add_argument(name, required=True)
    one = sub.add_parser("logged")
    one.add_argument("--use", required=True)
    one.add_argument("--entry", required=True)
    one = sub.add_parser("live-compose")
    one.add_argument("--use", required=True)
    one.add_argument("--rig", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.command == "freeze":
            p = freeze(root, args.use)
            for rig in sorted({e.rig for e in p.entries}):
                kinds = [e.kind for e in p.entries if e.rig == rig]
                print(
                    f"{rig}: {len(kinds)} entries — "
                    + ", ".join(f"{kinds.count(k)} {k}" for k in dict.fromkeys(kinds))
                )
        elif args.command == "entries":
            for entry in read_runs(root, args.use).entries:
                if entry.rig == args.rig:
                    print(f"{entry.id}\t{entry.kind}")
        elif args.command == "argv":
            entry = read_runs(root, args.use).entry(args.entry)
            sys.stdout.write("".join(f"{arg}\0" for arg in entry.argv))
        elif args.command == "log":
            runs = read_runs(root, args.use)
            if args.entry == "window":
                cells = ["window", args.rig, args.started, "", "", "", f"window date {args.window_date}", ""]
            else:
                entry = runs.entry(args.entry)
                cells = [
                    entry.id,
                    args.rig,
                    args.started,
                    args.ended,
                    args.exit,
                    entry.run_id(args.window_date, args.read_run_id),
                    entry.envelope(args.window_date),
                    args.output,
                ]
            insert_row(runs.path, LOG_HEADER, cells)
        elif args.command == "event":
            runs = read_runs(root, args.use)
            cells = _event(runs, args.rig, args.event, args.at)
            insert_row(runs.path, IDLE_HEADER, cells)
            print(" ".join(cell for cell in cells if cell))
        elif args.command == "logged":
            return 0 if read_runs(root, args.use).logged(args.entry) is not None else 1
        elif args.command == "live-compose":
            for name, path in live_compose(root, args.use, args.rig):
                print(f"{name}\t{path}")
    except PlanRefusedError as exc:
        print(f"plan.py: REFUSED — {exc}", file=sys.stderr)
        return 2
    return 0


def _event(runs: Runs, rig: str, event: str, at: str) -> list[str]:
    """An idle-minutes row. ``finished`` on the second rig to finish names the
    first rig's idle tail: the minutes between the two ``finished`` stamps."""
    from datetime import datetime

    minutes = ""
    if event == "finished":
        others = [r for r in runs.idle if r["event"] == "finished" and r["rig"] != rig]
        if others:
            first = datetime.fromisoformat(others[-1]["at"].replace("Z", "+00:00"))
            last = datetime.fromisoformat(at.replace("Z", "+00:00"))
            minutes = f"{others[-1]['rig']} idle {(last - first).total_seconds() / 60:.1f}"
        else:
            minutes = "the other rig is still running"
    return [event, rig, at, minutes]


if __name__ == "__main__":
    raise SystemExit(main())
