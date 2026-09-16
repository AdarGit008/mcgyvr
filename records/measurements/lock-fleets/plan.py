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

A logged entry that failed gets ONE retry (owner ruling, 2026-09-15: "Fix PR,
then retry srv2"):

    ... plan.py retry --use USE --entry E --reason "..." [--log-from TREE]

writes ``<use>/retries.json`` and the retry's own wrapper, and :func:`read_runs`
places each retry right after its failed entry, which stays in the order as a
data point. RUNS.md is not edited: both rigs log into it during a window. A read
or a load has no wrapper and no artifact of its own — ``drive.sh`` mints its run
id just before it runs — so its retry is the same door command under a new id:
the read by owner ruling, 2026-09-16; the load by the extension recorded in
``RETRIED``, which the owner has not ruled on.

A logged unit entry that passed, but whose load was not sampled until idle, gets
ONE extra cold start for room (owner ruling, 2026-09-15), ``plan.py rerun``,
listed under ``reruns`` in the same file and placed the same way. The entry
stays valid for decode and prefill; its re-run gives room and the card peak.

A logged failed retry of a unit entry gets ONE diagnostic start (owner ruling,
2026-09-15: "Fix PR, then one diagnostic start"), ``plan.py diagnose``, listed
under ``diagnostics`` and placed right after the failed retry. A passing one
stands in for the failed entry as a passing retry would.

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
from dataclasses import astuple, dataclass, field
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
#: A use's retries, beside its RUNS.md.
RETRIES = "retries.json"
#: A retry's entry id, wrapper stem and artifact stem: the failed one's, and this.
RETRY_SUFFIX = "-retry1"
#: The kinds a retry re-runs. A campaign unit or move run has a wrapper and an
#: artifact of its own; a read or a load files into the journal under a run id
#: drive.sh mints just before it runs, so running it again supersedes nothing.
#: The READ is the owner's ruling (2026-09-16: "fix the reader and record the
#: line", which let srv2-03 run again). The LOAD is Claude's extension of that
#: ruling, which the owner has not ruled on: a load is the same shape as a read
#: — it starts nothing, and drive.sh mints its id the same way — and no load has
#: failed in this window. The first one that does is worth putting to the owner
#: before it is retried. A serve-up or serve-down writes serve-<mode>.json into
#: the window's envelope, where a second run of it moves the first aside as
#: <mode>.superseded-<run id>.json (05-envelope.py:645-682) — a kept data point
#: named superseded — so it gets none.
RETRIED = ("unit", "move", "read", "load")
RETRY_RULING = {
    "by": "owner",
    "on": "2026-09-15",
    "said": "Fix PR, then retry srv2",
    "rule": (
        "A failed entry can get ONE retry entry with its own step wrapper and "
        "artifact name, placed immediately after the failed entry in that rig's "
        "order. The failed run is kept as a data point, never superseded or "
        "deleted, and a failed retry gets no second one."
    ),
}
RETRIES_DOC = (
    "One retry per failed entry of this use, one extra cold start for room per "
    "passing unit entry whose load was not sampled until idle, one diagnostic "
    "start per failed retry of a unit entry, and one fresh start per failed "
    "diagnostic start whose unit's launch changed. Written by "
    "records/measurements/lock-fleets/plan.py retry, rerun, diagnose and relaunch, "
    "which refuse any entry their ruling does not allow; read by plan.py read_runs, "
    "which places each immediately after its entry in that rig's order."
)
#: A re-run's entry id, wrapper stem and artifact stem: the entry's, and this.
RERUN_SUFFIX = "-rerun1"
RERUN_RULING = {
    "by": "owner",
    "on": "2026-09-15",
    "said": "One extra cold start for room",
    "rule": (
        "A passing unit entry whose load was filed before until-idle sampling gets "
        "ONE extra entry right after it in its rig's order: the same unit and cold "
        "start, with its own wrapper and artifact. The entry stays a valid run and "
        "gives decode and prefill; its re-run, sampled until idle, gives room and "
        "the card peak, and the entry's 30-s peak is kept as a lower bound."
    ),
}
#: A diagnostic start's entry id, wrapper stem and artifact stem: the retried
#: entry's, and this.
DIAGNOSTIC_SUFFIX = "-diag1"
DIAGNOSTIC_RULING = {
    "by": "owner",
    "on": "2026-09-15",
    "said": "Fix PR, then one diagnostic start",
    "rule": (
        "A logged failed retry of a unit entry gets ONE diagnostic start, "
        "<entry>-diag1, placed immediately after the failed retry in that rig's "
        "order: the same unit, cold start and door command, with its own wrapper "
        "and artifact, started once a failed start files its exit cause. If it "
        "passes its check it stands in for the failed entry exactly as a passing "
        "retry would; if it fails, the driver stops. It gets no retry, re-run or "
        "second diagnostic start, and the failed entry and its retry are kept as "
        "data points."
    ),
}
#: A fresh start's entry id, wrapper stem and artifact stem: the diagnosed
#: entry's, and this.
RELAUNCH_SUFFIX = "-relaunch1"
RELAUNCH_RULING = {
    "by": "owner",
    "on": "2026-09-16",
    "said": "Fix PR: allow io_uring",
    "rule": (
        "A logged failed diagnostic start of a unit entry whose LAUNCH has since "
        "changed gets ONE fresh cold start, <entry>-relaunch1, placed immediately "
        "after it in that rig's order: the same unit, cold start and door command, "
        "with its own wrapper and artifact, under the launch as it now stands. The "
        "three runs that failed under the old launch are kept as data points and "
        "none of them is re-judged. If the fresh start passes its check it stands "
        "in for the entry exactly as a passing retry would; if it fails, the driver "
        "stops. It gets no retry, re-run, diagnostic start or second fresh start."
    ),
}


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
    #: Rigs whose pswpout growth is filed and is no reason to stop (owner ruling,
    #: 2026-09-15: "Record swap on srv1, don't stop").
    swap_recorded_not_stopped_on: tuple[str, ...]
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
        swap_recorded_not_stopped_on=tuple(
            str(r) for r in doc.get("swap_recorded_not_stopped_on") or ()
        ),
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
    #: The failed entry this one retries (``retries.json``), or ``""``.
    retry_of: str = ""
    #: The passing entry this one is the extra cold start for room of, or ``""``.
    rerun_of: str = ""
    #: The failed retry this one is the diagnostic start after, or ``""``.
    diagnostic_of: str = ""
    #: The failed diagnostic start this one is the fresh start after, or ``""``.
    relaunch_of: str = ""

    @property
    def rig(self) -> str:
        retried = self.diagnostic_of.removesuffix(RETRY_SUFFIX)
        diagnosed = self.relaunch_of.removesuffix(DIAGNOSTIC_SUFFIX)
        return (
            self.retry_of or self.rerun_of or retried or diagnosed or self.id
        ).rsplit("-", 1)[0]

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


def _step_words(
    kind: str, rig: str, run: str, fleet: str, to: str, unit: str
) -> tuple[str, str, str]:
    """What a campaign run's wrapper says it is, the body it execs, and the
    arguments it gives that body."""
    if kind == "unit":
        return f"cold start {run} of {unit} ({fleet})", "_unit.sh", unit
    return (
        f"run {run} of the move {fleet} -> {to} on {rig}",
        "_move.sh",
        f"{rig} {fleet} {to}",
    )


def wrapper_text(
    use: str, entry_id: str, text: str, body: str, artifact: str, args: str
) -> str:
    """A generated wrapper: it declares its one artifact and execs its body."""
    return (
        "#!/usr/bin/env bash\n"
        f"# lock-fleets use {use}, entry {entry_id}: {text}; the body is {body}. "
        "Generated by records/measurements/lock-fleets/plan.py.\n"
        f"# RUN_ARTIFACTS: {artifact}\n"
        f'exec bash "$(dirname -- "${{BASH_SOURCE[0]}}")/../{body}" {artifact} {args} "$@"\n'
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
    for rig in use.keep_rig_pins + use.unit_caps_on + use.swap_recorded_not_stopped_on:
        if rig not in rigs:
            raise PlanRefusedError(f"use.json names rig {rig}, which no fleet places units on")

    entries: list[Entry] = []
    wrappers: dict[str, str] = {}
    number = 0

    def wrap(rig: str, run: str, slug: str, kind: str, fleet_name: str, to: str,
             unit: str) -> tuple[str, str]:
        nonlocal number
        number += 1
        step = f"{use.name}-{rig}-{run}-{slug}"
        path = (STEPS / use.name / f"{number:02d}-{step}.sh").as_posix()
        artifact = f"{step}.json"
        entry_id = f"{rig}-{len([e for e in entries if e.rig == rig]) + 1:02d}"
        text, body, args = _step_words(kind, rig, run, fleet_name, to, unit)
        wrappers[path] = wrapper_text(use.name, entry_id, text, body, artifact, args)
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
                        rig, run, unit.name, "unit", group.fleet, "-", unit.name
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
                    "move", source.fleet, target.fleet, "",
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

    def retry_for(self, entry_id: str) -> Entry | None:
        """The one retry ``retries.json`` gives ``entry_id``, or ``None``."""
        return next((e for e in self.entries if e.retry_of == entry_id), None)

    def rerun_for(self, entry_id: str) -> Entry | None:
        """The one extra cold start ``retries.json`` gives ``entry_id``, or ``None``."""
        return next((e for e in self.entries if e.rerun_of == entry_id), None)

    def diagnostic_for(self, entry_id: str) -> Entry | None:
        """The one diagnostic start ``retries.json`` gives the failed retry
        ``entry_id``, or ``None``."""
        return next((e for e in self.entries if e.diagnostic_of == entry_id), None)

    def relaunch_for(self, entry_id: str) -> Entry | None:
        """The one fresh start ``retries.json`` gives the failed diagnostic
        start ``entry_id``, or ``None``."""
        return next((e for e in self.entries if e.relaunch_of == entry_id), None)


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
    runs.entries = _with_extras(runs, load_extras(root, use), use)
    return runs


def retries_path(root: Path, use: str) -> Path:
    return use_dir(root, use) / RETRIES


#: The lists ``retries.json`` holds, each written by its own ``plan.py`` command.
EXTRAS = ("retries", "reruns", "diagnostics", "relaunches")


def load_extras(root: Path, use: str) -> dict[str, list[dict[str, str]]]:
    """``<use>/retries.json``'s ``retries``, ``reruns`` and ``diagnostics``, or
    none of any when there is no such file."""
    path = retries_path(root, use)
    if not path.is_file():
        return {key: [] for key in EXTRAS}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanRefusedError(f"{path} cannot be read: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("use") != use:
        raise PlanRefusedError(f"{path} does not list the retries of use {use}")
    out: dict[str, list[dict[str, str]]] = {}
    for key in EXTRAS:
        records = doc.get(key, [])
        if not isinstance(records, list):
            raise PlanRefusedError(f"{path}: {key} is not a list")
        out[key] = [{str(k): str(v) for k, v in record.items()} for record in records]
    return out


def _is_a_diagnostic(entry: Entry) -> str:
    return (
        f"{entry.id} is itself a diagnostic start of {entry.diagnostic_of}: it gets "
        "no retry, re-run or second diagnostic start"
    )


def _is_a_relaunch(entry: Entry) -> str:
    return (
        f"{entry.id} is itself a fresh start of {entry.relaunch_of}: it gets no "
        "retry, re-run, diagnostic start or second fresh start"
    )


def _not_an_extra(entry: Entry) -> None:
    """A retry, a re-run, a diagnostic start or a fresh start gets none of its own."""
    if entry.relaunch_of:
        raise PlanRefusedError(_is_a_relaunch(entry))
    if entry.diagnostic_of:
        raise PlanRefusedError(_is_a_diagnostic(entry))
    if entry.retry_of:
        raise PlanRefusedError(
            f"{entry.id} is itself a retry of {entry.retry_of}: a failed retry gets "
            "no second one"
        )
    if entry.rerun_of:
        raise PlanRefusedError(
            f"{entry.id} is itself a re-run of {entry.rerun_of}: it gets no retry "
            "or re-run of its own"
        )


def _extra(
    use: str, entry: Entry, suffix: str, key: str, said: str, *, strip: str = ""
) -> tuple[dict[str, str], str]:
    """An extra entry of ``entry``: its id and, for a campaign run, the artifact
    and wrapper path under ``suffix``, named from ``entry``'s with ``strip``
    taken off, and the wrapper's text. Same entry, same bytes.

    A read or a load has neither a wrapper nor an artifact: drive.sh mints its
    run id just before it runs, so the extra entry is the same door command
    under a new id and names only itself (the read by owner ruling, 2026-09-16;
    the load by the extension recorded in ``RETRIED``)."""
    if entry.kind not in ("unit", "move"):
        return {key: f"{entry.id.removesuffix(strip)}{suffix}"}, ""
    wrapper = Path(entry.wrapper)
    step = wrapper.with_name(
        f"{wrapper.stem.removesuffix(strip)}{suffix}{wrapper.suffix}"
    )
    artifact = f"{Path(entry.artifact).stem.removesuffix(strip)}{suffix}.json"
    extra_id = f"{entry.id.removesuffix(strip)}{suffix}"
    text, body, args = _step_words(
        entry.kind, entry.rig, entry.run, entry.fleet, entry.to, entry.units[0]
    )
    derived = {key: extra_id, "artifact": artifact, "step": step.as_posix()}
    words = f"{text}, {said} {entry.id}"
    return derived, wrapper_text(use, extra_id, words, body, artifact, args)


def derive_retry(use: str, entry: Entry) -> tuple[dict[str, str], str]:
    """The one retry of ``entry`` (owner ruling, 2026-09-15) — its entry id and,
    for a campaign run, its artifact and wrapper path — and the wrapper's text.
    Same entry, same bytes.

    A campaign unit or move run has a wrapper and an artifact of its own; a read
    or a load has a run id drive.sh mints for it, and is retried as the same door
    command under a new one (``RETRIED``: the read by owner ruling 2026-09-16,
    the load by the extension recorded there). A retry or a re-run gets no retry
    of its own.
    """
    _not_an_extra(entry)
    if entry.kind not in RETRIED:
        raise PlanRefusedError(
            f"{entry.id} is a {entry.kind} entry: only a campaign unit or move run, "
            "which has a wrapper and an artifact of its own, or a read or a load, "
            "whose run id drive.sh mints, is retried — a second serve-up or "
            "serve-down would name its own kept file superseded"
        )
    return _extra(use, entry, RETRY_SUFFIX, "retry_entry", "the one retry of")


def derive_rerun(use: str, entry: Entry) -> tuple[dict[str, str], str]:
    """The one extra cold start for room of ``entry`` (owner ruling, 2026-09-15:
    "One extra cold start for room"), as :func:`derive_retry` gives a retry.

    Only a unit entry carries a load of its own in its artifact.
    """
    _not_an_extra(entry)
    if entry.kind != "unit":
        raise PlanRefusedError(
            f"{entry.id} is a {entry.kind} entry: only a unit entry carries a load "
            "of its own to re-run"
        )
    return _extra(
        use, entry, RERUN_SUFFIX, "rerun_entry", "the one extra cold start for room of"
    )


def derive_diagnostic(use: str, entry: Entry) -> tuple[dict[str, str], str]:
    """The one diagnostic start after the failed retry ``entry`` (owner ruling,
    2026-09-15: "Fix PR, then one diagnostic start"), as :func:`derive_retry`
    gives a retry: ``<retried entry>-diag1``, its wrapper and artifact named from
    the retried entry's. Same retry, same bytes.

    Only a retry of a unit entry gets one; any other entry, a re-run and a
    diagnostic start get none.
    """
    if entry.relaunch_of:
        raise PlanRefusedError(_is_a_relaunch(entry))
    if entry.diagnostic_of:
        raise PlanRefusedError(_is_a_diagnostic(entry))
    if not entry.retry_of:
        raise PlanRefusedError(
            f"{entry.id} is not a retry: only a failed retry gets a diagnostic start"
        )
    if entry.kind != "unit":
        raise PlanRefusedError(
            f"{entry.id} is a {entry.kind} entry: only a failed retry of a unit entry "
            "gets a diagnostic start"
        )
    return _extra(
        use,
        entry,
        DIAGNOSTIC_SUFFIX,
        "diagnostic_entry",
        "the one diagnostic start after the failed retry",
        strip=RETRY_SUFFIX,
    )


def derive_relaunch(use: str, entry: Entry) -> tuple[dict[str, str], str]:
    """The one fresh start after the failed diagnostic start ``entry`` (owner
    ruling, 2026-09-16: "Fix PR: allow io_uring"), as :func:`derive_retry` gives
    a retry: ``<entry>-relaunch1``, its wrapper and artifact named from the
    diagnosed entry's. Same entry, same bytes.

    Only a diagnostic start of a unit entry gets one. The runs that failed under
    the old launch are data points; this is the same unit and the same cold
    start, run once under the launch as it now stands.
    """
    if entry.relaunch_of:
        raise PlanRefusedError(_is_a_relaunch(entry))
    if not entry.diagnostic_of:
        raise PlanRefusedError(
            f"{entry.id} is not a diagnostic start: only a failed diagnostic start "
            "gets a fresh start under a changed launch"
        )
    if entry.kind != "unit":
        raise PlanRefusedError(
            f"{entry.id} is a {entry.kind} entry: only a unit entry has a launch "
            "to change"
        )
    return _extra(
        use,
        entry,
        RELAUNCH_SUFFIX,
        "relaunch_entry",
        "the one fresh start under the changed launch after",
        strip=DIAGNOSTIC_SUFFIX,
    )


def _named_as_derived(
    record: Mapping[str, str], derived: Mapping[str, str], entry_id: str
) -> None:
    named = {name: record.get(name) for name in derived}
    if named != derived:
        raise PlanRefusedError(
            f"{RETRIES} names {named} for {entry_id}, and plan.py derives {derived}"
        )


def _extra_entry(entry: Entry, derived: Mapping[str, str], **of: str) -> Entry:
    """The extra entry ``derived`` names, placed after ``entry``: its door command
    with only the step path changed, or the same command when the entry has no
    step of its own (a read or a load)."""
    argv = list(entry.argv)
    if "step" in derived:
        argv[argv.index("--step") + 1] = derived["step"]
    return Entry(
        id=next(
            derived[k]
            for k in ("retry_entry", "rerun_entry", "diagnostic_entry", "relaunch_entry")
            if k in derived
        ),
        kind=entry.kind,
        fleet=entry.fleet,
        to=entry.to,
        units=entry.units,
        run=entry.run,
        artifact=derived.get("artifact", entry.artifact),
        argv=tuple(argv),
        **of,
    )


def _with_extras(
    runs: Runs, extras: Mapping[str, Sequence[Mapping[str, str]]], use: str
) -> list[Entry]:
    """The frozen order with each retry or re-run right after its entry, and each
    diagnostic start right after its failed retry."""
    derive = {"retries": derive_retry, "reruns": derive_rerun}
    placed: dict[str, tuple[str, dict[str, str]]] = {}
    for key in ("retries", "reruns"):
        for record in extras.get(key, ()):
            entry = runs.entry(record.get("entry", ""))
            derived, _ = derive[key](use, entry)
            if entry.id in placed:
                raise PlanRefusedError(
                    f"{RETRIES} names {entry.id} twice: one retry or re-run per entry"
                )
            _named_as_derived(record, derived, entry.id)
            placed[entry.id] = (key, derived)
    out: list[Entry] = []
    for entry in runs.entries:
        out.append(entry)
        if entry.id in placed:
            key, derived = placed[entry.id]
            of = {"retry_of" if key == "retries" else "rerun_of": entry.id}
            out.append(_extra_entry(entry, derived, **of))
    diagnosed: dict[str, dict[str, str]] = {}
    for record in extras.get("diagnostics", ()):
        wanted = record.get("entry", "")
        retry = next((e for e in out if e.id == wanted), None)
        if retry is None:
            raise PlanRefusedError(f"{runs.path} has no entry {wanted}")
        derived, _ = derive_diagnostic(use, retry)
        if retry.id in diagnosed:
            raise PlanRefusedError(
                f"{RETRIES} names {retry.id} twice: one diagnostic start per failed retry"
            )
        _named_as_derived(record, derived, retry.id)
        diagnosed[retry.id] = derived
    diagnosed_out: list[Entry] = []
    for entry in out:
        diagnosed_out.append(entry)
        if entry.id in diagnosed:
            diagnosed_out.append(
                _extra_entry(entry, diagnosed[entry.id], diagnostic_of=entry.id)
            )
    relaunched: dict[str, dict[str, str]] = {}
    for record in extras.get("relaunches", ()):
        wanted = record.get("entry", "")
        diagnostic = next((e for e in diagnosed_out if e.id == wanted), None)
        if diagnostic is None:
            raise PlanRefusedError(f"{runs.path} has no entry {wanted}")
        derived, _ = derive_relaunch(use, diagnostic)
        if diagnostic.id in relaunched:
            raise PlanRefusedError(
                f"{RETRIES} names {diagnostic.id} twice: one fresh start per "
                "failed diagnostic start"
            )
        _named_as_derived(record, derived, diagnostic.id)
        relaunched[diagnostic.id] = derived
    final: list[Entry] = []
    for entry in diagnosed_out:
        final.append(entry)
        if entry.id in relaunched:
            final.append(
                _extra_entry(entry, relaunched[entry.id], relaunch_of=entry.id)
            )
    return final


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
    if retries_path(root, use).is_file():
        raise PlanRefusedError(
            f"{retries_path(root, use)} names a retry: the order was measured, and "
            "is frozen from its first measurement"
        )
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


def _assembler() -> ModuleType:
    """``assemble_evidence.py``, whose check says whether an entry failed."""
    name = "lockfleets_assemble"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, HERE / "assemble_evidence.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def retry(
    root: Path,
    use: str,
    entry_id: str,
    reason: str,
    *,
    log_from: Path | None = None,
    journal: str | None = None,
) -> dict[str, str]:
    """Give the logged failed ``entry_id`` its one retry (owner ruling, 2026-09-15).

    Refused unless the entry is logged and fails ``assemble_evidence.py check``,
    has no retry yet, and is not itself a retry; and the ruling retries a
    campaign unit or move run, a read or a load (:func:`derive_retry`). Writes
    ``<use>/retries.json`` and the retry's wrapper under ``root``, and returns
    the record it added. RUNS.md is not touched.

    ``log_from`` is a tree whose RUNS.md log, and the envelopes and outputs its
    rows name, show the failure when ``root``'s own log does not — a checkout
    whose RUNS.md was committed before the window was logged into another. Its
    frozen order must be ``root``'s; the check runs there, on its files.
    """
    if not reason.strip():
        raise PlanRefusedError("a retry names its reason (--reason)")
    runs = read_runs(root, use)
    entry = runs.entry(entry_id)
    derived, text = derive_retry(use, entry)
    existing = runs.retry_for(entry_id)
    if existing is not None:
        raise PlanRefusedError(
            f"{entry_id} already has a retry, {existing.id}: one retry per failed entry"
        )
    rerun_by = runs.rerun_for(entry_id)
    if rerun_by is not None:
        raise PlanRefusedError(
            f"{entry_id} has a re-run, {rerun_by.id}: it passed, and a retry is for "
            "a failed entry"
        )
    asm, ctx = _logged_context(root, use, runs, entry_id, log_from, journal, "a retry")
    reasons, _ = asm.verdict(ctx, entry.rig, entry_id)
    if not reasons:
        raise PlanRefusedError(
            f"{entry_id} passes its check: only a failed entry gets a retry"
        )
    record = {"entry": entry_id, "reason": reason, **derived}
    return _write_extra(root, use, "retries", record, text)


def rerun(
    root: Path,
    use: str,
    entry_id: str,
    reason: str,
    *,
    log_from: Path | None = None,
    journal: str | None = None,
) -> dict[str, str]:
    """Give ``entry_id`` its one extra cold start for room (owner ruling,
    2026-09-15: "One extra cold start for room").

    Refused unless the entry is logged and passes ``assemble_evidence.py check``,
    is a unit entry whose load was not sampled until idle, has no re-run and no
    retry, and is not itself a retry or a re-run. The entry stays a valid run:
    the assembler takes its decode and prefill, and room and the card peak from
    the re-run. Writes ``<use>/retries.json``'s ``reruns`` and the re-run's
    wrapper under ``root``; ``log_from`` is as :func:`retry` reads it.
    """
    if not reason.strip():
        raise PlanRefusedError("a re-run names its reason (--reason)")
    runs = read_runs(root, use)
    entry = runs.entry(entry_id)
    derived, text = derive_rerun(use, entry)
    existing = runs.rerun_for(entry_id)
    if existing is not None:
        raise PlanRefusedError(
            f"{entry_id} already has a re-run, {existing.id}: one extra cold start "
            "per entry"
        )
    retried = runs.retry_for(entry_id)
    if retried is not None:
        raise PlanRefusedError(
            f"{entry_id} has a retry, {retried.id}: it failed, and a re-run is for a "
            "run that passed"
        )
    asm, ctx = _logged_context(root, use, runs, entry_id, log_from, journal, "a re-run")
    reasons, _ = asm.verdict(ctx, entry.rig, entry_id)
    if reasons:
        raise PlanRefusedError(
            f"{entry_id} fails its check: only a passing entry gets a re-run "
            f"({'; '.join(reasons)[:300]})"
        )
    try:
        loads = asm.gather(ctx, ctx.runs.entry(entry_id))["loads"]
    except asm.MissingError as exc:
        raise PlanRefusedError(str(exc)) from exc
    load = loads.get(entry.units[0])
    if not load:
        raise PlanRefusedError(f"{entry_id} filed no load: there is no room to re-run")
    if load.get("sampled_until_idle") is not False:
        raise PlanRefusedError(
            f"{entry_id}'s load was sampled until idle: its room needs no re-run"
        )
    record = {"entry": entry_id, "reason": reason, **derived}
    return _write_extra(root, use, "reruns", record, text)


def diagnose(
    root: Path,
    use: str,
    entry_id: str,
    reason: str,
    *,
    log_from: Path | None = None,
    journal: str | None = None,
) -> dict[str, str]:
    """Give the logged failed retry ``entry_id`` its one diagnostic start (owner
    ruling, 2026-09-15: "Fix PR, then one diagnostic start").

    Refused unless the entry is a retry of a unit entry (:func:`derive_diagnostic`),
    has no diagnostic start yet, is logged and fails ``assemble_evidence.py
    check``. Writes ``<use>/retries.json``'s ``diagnostics`` and the diagnostic
    start's wrapper under ``root``; ``log_from`` is as :func:`retry` reads it.
    """
    if not reason.strip():
        raise PlanRefusedError("a diagnostic start names its reason (--reason)")
    runs = read_runs(root, use)
    entry = runs.entry(entry_id)
    derived, text = derive_diagnostic(use, entry)
    existing = runs.diagnostic_for(entry_id)
    if existing is not None:
        raise PlanRefusedError(
            f"{entry_id} already has a diagnostic start, {existing.id}: one per "
            "failed retry"
        )
    asm, ctx = _logged_context(
        root, use, runs, entry_id, log_from, journal, "a diagnostic start"
    )
    reasons, _ = asm.verdict(ctx, entry.rig, entry_id)
    if not reasons:
        raise PlanRefusedError(
            f"{entry_id} passes its check: only a failed retry gets a diagnostic start"
        )
    record = {"entry": entry_id, "reason": reason, **derived}
    return _write_extra(root, use, "diagnostics", record, text)


def relaunch(
    root: Path,
    use: str,
    entry_id: str,
    reason: str,
    *,
    log_from: Path | None = None,
    journal: str | None = None,
) -> dict[str, str]:
    """Give the logged failed diagnostic start ``entry_id`` its one fresh start
    under the changed launch (owner ruling, 2026-09-16: "Fix PR: allow io_uring").

    Refused unless the entry is a diagnostic start of a unit entry
    (:func:`derive_relaunch`), has no fresh start yet, is logged and fails
    ``assemble_evidence.py check``. Writes ``<use>/retries.json``'s
    ``relaunches`` and the fresh start's wrapper under ``root``; ``log_from`` is
    as :func:`retry` reads it.
    """
    if not reason.strip():
        raise PlanRefusedError("a fresh start names its reason (--reason)")
    runs = read_runs(root, use)
    entry = runs.entry(entry_id)
    derived, text = derive_relaunch(use, entry)
    existing = runs.relaunch_for(entry_id)
    if existing is not None:
        raise PlanRefusedError(
            f"{entry_id} already has a fresh start, {existing.id}: one per failed "
            "diagnostic start"
        )
    asm, ctx = _logged_context(
        root, use, runs, entry_id, log_from, journal, "a fresh start"
    )
    reasons, _ = asm.verdict(ctx, entry.rig, entry_id)
    if not reasons:
        raise PlanRefusedError(
            f"{entry_id} passes its check: only a failed diagnostic start gets a "
            "fresh start"
        )
    record = {"entry": entry_id, "reason": reason, **derived}
    return _write_extra(root, use, "relaunches", record, text)


def _logged_context(
    root: Path,
    use: str,
    runs: Runs,
    entry_id: str,
    log_from: Path | None,
    journal: str | None,
    what: str,
) -> tuple[ModuleType, Any]:
    """The assembler, and its context on the tree whose log holds ``entry_id``:
    ``root``, or ``log_from`` when its frozen order is ``root``'s."""
    where = root if log_from is None else log_from
    asm = _assembler()
    try:
        ctx = asm.Context.load(where, use, journal)
    except asm.AssemblyRefusedError as exc:
        raise PlanRefusedError(str(exc)) from exc
    if log_from is not None:
        ours = [
            astuple(e)
            for e in runs.entries
            if not (e.retry_of or e.rerun_of or e.diagnostic_of)
        ]
        theirs = [
            astuple(e)
            for e in ctx.runs.entries
            if not (e.retry_of or e.rerun_of or e.diagnostic_of)
        ]
        there = (
            ctx.runs.retry_for(entry_id)
            or ctx.runs.rerun_for(entry_id)
            or ctx.runs.diagnostic_for(entry_id)
        )
        if ours != theirs or there is not None:
            raise PlanRefusedError(
                f"the log in {where} is of another frozen order of {use} than "
                f"{root}'s, or gives {entry_id} a retry or re-run there already"
            )
    if ctx.runs.logged(entry_id) is None:
        raise PlanRefusedError(
            f"{entry_id} has no log row in {where}: only a logged entry gets {what}"
        )
    return asm, ctx


def _write_extra(
    root: Path, use: str, key: str, record: dict[str, str], text: str
) -> dict[str, str]:
    """Write the extra entry's wrapper, once, and list it under ``key``.

    A read or a load has no wrapper to write: only the listing is written."""
    wrapper = root / record["step"] if record.get("step") else None
    if wrapper is not None and wrapper.exists():
        raise PlanRefusedError(f"{record['step']} already exists: it is written once")
    extras = load_extras(root, use)
    extras[key] = [*extras[key], record]
    doc = {
        "_doc": RETRIES_DOC,
        "use": use,
        "ruling": RETRY_RULING,
        "retries": extras["retries"],
        "rerun_ruling": RERUN_RULING,
        "reruns": extras["reruns"],
        "diagnostic_ruling": DIAGNOSTIC_RULING,
        "diagnostics": extras["diagnostics"],
        "relaunch_ruling": RELAUNCH_RULING,
        "relaunches": extras["relaunches"],
    }
    if wrapper is not None:
        wrapper.write_text(text, encoding="utf-8")
        wrapper.chmod(0o755)
    retries_path(root, use).write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
    return record


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
    one = sub.add_parser("retry")
    for name in ("--use", "--entry", "--reason"):
        one.add_argument(name, required=True)
    one.add_argument(
        "--log-from",
        default="",
        help="a tree whose RUNS.md log, envelopes and outputs show the failure; "
        "the retry is still written under --root",
    )
    one.add_argument("--journal", default="")
    one = sub.add_parser("rerun")
    for name in ("--use", "--entry", "--reason"):
        one.add_argument(name, required=True)
    one.add_argument("--log-from", default="")
    one.add_argument("--journal", default="")
    one = sub.add_parser("diagnose")
    for name in ("--use", "--entry", "--reason"):
        one.add_argument(name, required=True)
    one.add_argument("--log-from", default="")
    one.add_argument("--journal", default="")
    one = sub.add_parser("relaunch")
    for name in ("--use", "--entry", "--reason"):
        one.add_argument(name, required=True)
    one.add_argument("--log-from", default="")
    one.add_argument("--journal", default="")
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
        elif args.command == "retry":
            made = retry(
                root,
                args.use,
                args.entry,
                args.reason,
                log_from=Path(args.log_from) if args.log_from else None,
                journal=args.journal or None,
            )
            where = (
                f": {made['step']} declares {made['artifact']}"
                if "step" in made
                else ", the same door command under the run id drive.sh mints for it"
            )
            print(
                f"{made['entry']} failed its check; its one retry "
                f"{made['retry_entry']} is the entry after it{where}"
            )
        elif args.command == "rerun":
            made = rerun(
                root,
                args.use,
                args.entry,
                args.reason,
                log_from=Path(args.log_from) if args.log_from else None,
                journal=args.journal or None,
            )
            print(
                f"{made['entry']} passed with a load not sampled until idle; its one "
                f"extra cold start for room {made['rerun_entry']} is the entry after "
                f"it: {made['step']} declares {made['artifact']}"
            )
        elif args.command == "diagnose":
            made = diagnose(
                root,
                args.use,
                args.entry,
                args.reason,
                log_from=Path(args.log_from) if args.log_from else None,
                journal=args.journal or None,
            )
            print(
                f"{made['entry']} is a failed retry; its one diagnostic start "
                f"{made['diagnostic_entry']} is the entry after it: {made['step']} "
                f"declares {made['artifact']}"
            )
        elif args.command == "relaunch":
            made = relaunch(
                root,
                args.use,
                args.entry,
                args.reason,
                log_from=Path(args.log_from) if args.log_from else None,
                journal=args.journal or None,
            )
            print(
                f"{made['entry']} failed under the old launch; its one fresh start "
                f"{made['relaunch_entry']} is the entry after it: {made['step']} "
                f"declares {made['artifact']}"
            )
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
