"""lock-fleets: what a step acts on, read from fleet.yaml, its digests and the door.

Owner, 2026-09-15: ``lock-fleets`` is a reusable campaign that measures what the
fleet lock needs. Its two step bodies — ``_unit.sh``, one cold start of one
llama.cpp unit, and ``_move.sh``, one timed switch move on one rig — ask this
file for every fact they act on, by path (``_py lockfleets.py COMMAND ...``;
``lock-fleets`` is not an importable name). The facts come from
``fleet-setup/fleet.yaml``, ``fleet-setup/digests-<rig>.json`` and the variables
the door exports; nothing about any one use of the campaign is written here.

It judges nothing a run measured. It refuses a launch that is not the one
fleet.yaml and its digests name, renders the shell a move runs on the rig, and
writes each step's artifact whole, whatever the step got to.

The planner and the assembler (``records/measurements/lock-fleets/``) load it
too, so a side of a move is classified, and a stamp is parsed, in one place.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mcgyvr.fleet.files import FleetFileError, load_fleet

CAMPAIGN = "lock-fleets"
UNIT_SCHEMA = "lock-fleets-unit/1"
MOVE_SCHEMA = "lock-fleets-move/1"
#: Where a step tees its markers and stamps on the rig, under the rig user's
#: home: a lock takes the ssh pipe with it (okf/must-read/touching-rigs.md,
#: "srv1 hard-locks under CPU expert offload").
RIG_DIR = "mcgyvr-relock"
LLAMACPP = "llama.cpp"
VLLM = "vllm"
AWAKE = "awake"
#: What ``docker run`` is given before the image, for a unit this campaign starts.
RUN_FLAGS = ("--gpus", "all", "--network", "host")
#: The marker fields a run's START and END must agree on (owner, 2026-09-15).
MARKER_FIELDS = ("uptime_since", "ram_mt_s", "pl1_uw", "pl2_uw")
#: The counters read from the rig's /proc/vmstat at START and END.
VMSTAT_FIELDS = ("pswpout", "pgmajfault")
#: A placeholder in a move's shell template: ``@NAME@``.
PLACEHOLDER = re.compile(r"@([A-Z][A-Z0-9_]*)@")


class StepRefusedError(Exception):
    """The launch a step was asked for is not the one the fleet files name."""


def fleet_file(root: Path) -> Path:
    return root / "fleet-setup" / "fleet.yaml"


def digests_file(root: Path, rig: str) -> Path:
    return root / "fleet-setup" / f"digests-{rig}.json"


def load(root: Path) -> dict[str, Any]:
    """``fleet-setup/fleet.yaml`` under ``root``, through the one parser."""
    path = fleet_file(root)
    try:
        return load_fleet(path.read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise StepRefusedError(f"{path} cannot be read: {exc}") from exc


def flag(argv: Sequence[str], *names: str) -> str | None:
    """The value after the first of ``names`` in ``argv``, or ``None``."""
    for index, token in enumerate(argv):
        if token in names and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _int(value: str | None, what: str, unit: str) -> int:
    if value is None or not value.isascii() or not value.isdigit():
        raise StepRefusedError(f"{unit}: launch.argv states no integer {what}")
    return int(value)


@dataclass(frozen=True)
class Launch:
    """One unit as fleet.yaml states its launch."""

    name: str
    rig: str
    engine: str
    image: str
    container: str
    port: int
    argv: tuple[str, ...]
    env: dict[str, str]
    volumes: tuple[str, ...]
    #: llama.cpp: the ``--model`` blob as the rig sees it; vLLM: the model id.
    model: str
    #: W: ``--parallel``/``-np`` or ``--max-num-seqs``.
    width: int
    #: N: the per-slot window, ``-c`` over ``-np`` or ``--max-model-len``.
    window: int
    #: llama.cpp's ``-c``, the whole cache across slots.
    ctx: int | None
    #: llama.cpp's ``-ub``, ``None`` when the argv states none.
    ubatch: int | None


def launch(fleet: Mapping[str, Any], name: str) -> Launch:
    """``name``'s launch, or :class:`StepRefusedError` naming what is missing."""
    unit = (fleet.get("units") or {}).get(name)
    if not isinstance(unit, Mapping):
        raise StepRefusedError(f"{name} is not a unit of fleet.yaml")
    block = unit.get("launch")
    launch_block: Mapping[str, Any] = block if isinstance(block, Mapping) else {}
    argv = launch_block.get("argv")
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise StepRefusedError(f"{name}: fleet.yaml states no launch.argv")
    env = launch_block.get("env") or {}
    if not isinstance(env, Mapping):
        raise StepRefusedError(f"{name}: launch.env is not a mapping")
    volumes = launch_block.get("volumes") or []
    engine = unit.get("engine")
    engine = engine if isinstance(engine, str) and engine else LLAMACPP
    port = urlsplit(str(unit.get("address") or "")).port
    if port is None:
        raise StepRefusedError(f"{name}: its address names no port")
    ctx: int | None = None
    ubatch: int | None = None
    if engine == VLLM:
        model = argv[0] if argv else ""
        width = _int(flag(argv, "--max-num-seqs"), "--max-num-seqs", name)
        window = _int(flag(argv, "--max-model-len"), "--max-model-len", name)
    else:
        model = flag(argv, "--model", "-m") or ""
        width = _int(flag(argv, "--parallel", "-np"), "--parallel/-np", name)
        ctx = _int(flag(argv, "-c", "--ctx-size"), "-c", name)
        stated = flag(argv, "-ub", "--ubatch-size")
        ubatch = None if stated is None else _int(stated, "-ub", name)
        window = ctx // width if width else 0
    if not model:
        raise StepRefusedError(f"{name}: launch.argv names no model")
    return Launch(
        name=name,
        rig=str(unit.get("rig") or ""),
        engine=engine,
        image=str(unit.get("image") or ""),
        container=str(unit.get("container") or ""),
        port=port,
        argv=tuple(argv),
        env={str(k): str(v) for k, v in env.items()},
        volumes=tuple(str(v) for v in volumes),
        model=model,
        width=width,
        window=window,
        ctx=ctx,
        ubatch=ubatch,
    )


def recorded(root: Path, rig: str, name: str) -> dict[str, Any]:
    """The fields ``digests-<rig>.json`` hashed for ``name``."""
    path = digests_file(root, rig)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StepRefusedError(f"{path} cannot be read: {exc}") from exc
    fields = ((doc.get("units") or {}).get(name) or {}).get("fields")
    if not isinstance(fields, dict):
        raise StepRefusedError(f"{path} records no fields for {name}")
    return fields


def recorded_image(fields: Mapping[str, Any]) -> str:
    """The image a digests file recorded: ``image_id`` in one, ``image`` in another."""
    for key in ("image_id", "image"):
        value = fields.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def digest_part(image: str) -> str:
    """``sha256:<hex>`` of ``repo@sha256:<hex>``, or the value as it is."""
    return image.rpartition("@")[2]


def launch_refusals(root: Path, unit: Launch) -> list[str]:
    """Where ``unit``'s launch is not what its digests file hashed."""
    try:
        fields = recorded(root, unit.rig, unit.name)
    except StepRefusedError as exc:
        return [str(exc)]
    out: list[str] = []
    if list(unit.argv) != fields.get("argv"):
        out.append(
            f"{unit.name}: launch.argv is not digests-{unit.rig}.json fields.argv"
        )
    if unit.env != fields.get("env"):
        out.append(f"{unit.name}: launch.env is not digests-{unit.rig}.json fields.env")
    if not recorded_image(fields):
        out.append(f"{unit.name}: digests-{unit.rig}.json records no image")
    return out


@dataclass(frozen=True)
class Door:
    """What the door exported to the step about the run it opened."""

    host: str
    run_id: str
    model: str
    parallel: str
    ctx_per_slot: str
    ubatch: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Door:
        return cls(
            host=env.get("RUN_HOST", ""),
            run_id=env.get("RUN_ID", ""),
            model=env.get("RUN_MODEL", ""),
            parallel=env.get("RUN_PARALLEL", ""),
            ctx_per_slot=env.get("RUN_CTX_PER_SLOT", ""),
            ubatch=env.get("RUN_UBATCH", ""),
        )


def door_refusals(unit: Launch, door: Door) -> list[str]:
    """Where the door's ``--model``/``--parallel``/``--ctx-per-slot``/``--ubatch``
    are not ``unit``'s own: data-20 and data-30 read them, and a floor derived
    for another launch is not this one's."""
    out: list[str] = []
    if unit.model != door.model:
        out.append(f"--model {door.model} is not {unit.name}'s --model {unit.model}")
    if str(unit.width) != door.parallel:
        out.append(
            f"--parallel {door.parallel} is not {unit.name}'s --parallel {unit.width}"
        )
    if unit.ctx is not None and (unit.width < 1 or unit.ctx % unit.width):
        out.append(f"{unit.name}: -c {unit.ctx} is not a whole multiple of -np")
    elif str(unit.window) != door.ctx_per_slot:
        out.append(
            f"--ctx-per-slot {door.ctx_per_slot} is not {unit.name}'s -c/np "
            f"{unit.window}"
        )
    if unit.ubatch is not None and str(unit.ubatch) != door.ubatch:
        out.append(f"--ubatch {door.ubatch} is not {unit.name}'s -ub {unit.ubatch}")
    return out


def unit_refusals(
    root: Path, fleet: Mapping[str, Any], name: str, door: Door
) -> tuple[Launch | None, list[str]]:
    """``_unit.sh``'s refusals, before the rig is touched."""
    try:
        unit = launch(fleet, name)
    except StepRefusedError as exc:
        return None, [str(exc)]
    out: list[str] = []
    if unit.rig != door.host:
        out.append(f"{name} is placed on {unit.rig}, and this run is on {door.host}")
    if unit.engine != LLAMACPP:
        out.append(
            f"{name} is {unit.engine}: a campaign unit run starts one llama.cpp "
            "unit, and a vLLM combination is measured by the door's serve and read"
        )
    out += launch_refusals(root, unit)
    out += door_refusals(unit, door)
    return unit, out


@dataclass(frozen=True)
class Side:
    """One side of a combination or a move: one llama.cpp unit, or a vLLM group."""

    fleet: str
    rig: str
    units: tuple[Launch, ...]

    @property
    def compose(self) -> bool:
        """A vLLM group, started together by ``docker compose``."""
        return all(unit.engine == VLLM for unit in self.units)

    @property
    def slots(self) -> list[list[str]]:
        return [[unit.name, AWAKE] for unit in self.units]


def side(fleet: Mapping[str, Any], fleet_name: str, rig: str, slots: Any) -> Side:
    """What ``fleet_name`` places on ``rig``, or refused naming why it cannot run."""
    names: list[str] = []
    for slot in slots or []:
        if slot is None:
            continue
        unit_name, state = slot
        if state != AWAKE:
            raise StepRefusedError(
                f"{fleet_name}/{rig}: {unit_name} is {state}, and lock-fleets "
                "measures only awake units"
            )
        names.append(str(unit_name))
    if not names:
        raise StepRefusedError(f"{fleet_name}/{rig}: no unit is placed there")
    units = tuple(launch(fleet, name) for name in names)
    engines = {unit.engine for unit in units}
    if engines != {VLLM} and not (engines == {LLAMACPP} and len(units) == 1):
        raise StepRefusedError(
            f"{fleet_name}/{rig}: {'+'.join(names)} is neither one llama.cpp unit "
            "nor a group of vLLM units, and lock-fleets measures only those"
        )
    return Side(fleet_name, rig, units)


def move_sides(
    fleet: Mapping[str, Any], rig: str, from_fleet: str, to_fleet: str
) -> tuple[Side, Side]:
    """The source and target of ``from_fleet``'s switch to ``to_fleet`` on ``rig``."""
    from mcgyvr.fleet.lock import _switch_moves

    fleets = fleet.get("fleets") or {}
    for name in (from_fleet, to_fleet):
        if name not in fleets:
            raise StepRefusedError(f"{name} is not a fleet of fleet.yaml")
    if to_fleet not in (fleets[from_fleet].get("next") or []):
        raise StepRefusedError(f"{from_fleet} does not list {to_fleet} in its next")
    moves = {
        move[0]: move
        for move in _switch_moves(
            fleets[from_fleet].get("layout") or {}, fleets[to_fleet].get("layout") or {}
        )
    }
    if rig not in moves:
        raise StepRefusedError(f"{from_fleet} -> {to_fleet} moves nothing on {rig}")
    _, before, after = moves[rig]
    return side(fleet, from_fleet, rig, before), side(fleet, to_fleet, rig, after)


def emitted_compose(fleet: Mapping[str, Any], rig: str, fleet_name: str) -> bytes:
    """The compose file ``mcgyvr emit`` writes for ``fleet_name`` on ``rig``."""
    from mcgyvr.emit import emit_locked
    from mcgyvr.serving import spec_name

    with tempfile.TemporaryDirectory() as tmp:
        emit_locked(fleet, Path(tmp))
        return (Path(tmp) / spec_name(rig, fleet_name)).read_bytes()


def compose_refusals(fleet: Mapping[str, Any], group: Side, compose: str) -> list[str]:
    """Where ``compose`` is not the emitted file for ``group``, or names others."""
    from mcgyvr.serving.servelib import ComposeError, services

    path = Path(compose) if compose else None
    if path is None or not path.is_file():
        return [
            f"{group.fleet}/{group.rig} is a compose group and no compose file was "
            "given (the step's COMPOSE argument)"
        ]
    if path.read_bytes() != emitted_compose(fleet, group.rig, group.fleet):
        return [
            f"{compose} is not byte-identical to mcgyvr.emit.emit_locked's file for "
            f"{group.fleet} on {group.rig}"
        ]
    try:
        named = sorted(service.container for service in services(path))
    except ComposeError as exc:
        return [str(exc)]
    wanted = sorted(unit.container for unit in group.units)
    if named != wanted:
        return [f"{compose} names containers {named}, and fleet.yaml names {wanted}"]
    return []


def run_args(unit: Launch, container: str, image: str) -> list[str]:
    """What follows ``run -d``: the name, the card, the host's network, the
    volumes and environment fleet.yaml states, the image and the argv."""
    args = ["--name", container, *RUN_FLAGS]
    for volume in unit.volumes:
        args += ["-v", volume]
    for key, value in sorted(unit.env.items()):
        args += ["-e", f"{key}={value}"]
    return [*args, image, *unit.argv]


def remote_file(run_id: str, suffix: str) -> str:
    """The rig-side file a run tees to, spelled for the rig's shell."""
    return f'"$HOME"/{RIG_DIR}/{shlex.quote(f"{run_id}.{suffix}")}'


def remote_dir() -> str:
    return f'"$HOME"/{RIG_DIR}'


def shell_vars(values: Mapping[str, object]) -> str:
    """``KEY=value`` lines a step's shell can ``eval``, every value quoted."""
    return "".join(
        f"{key}={shlex.quote(str(value))}\n" for key, value in values.items()
    )


def polls(group: Side) -> str:
    """``unit:engine:port`` per unit, quoted for the rig's shell."""
    return " ".join(
        shlex.quote(f"{unit.name}:{unit.engine}:{unit.port}") for unit in group.units
    )


def names_of(group: Side, run_id: str) -> list[str]:
    """The containers a side runs under: its own for a group, ``<RUN_ID>-<unit>``
    for a unit this run starts."""
    if group.compose:
        return [unit.container for unit in group.units]
    return [f"{run_id}-{unit.name}" for unit in group.units]


def render(template: str, values: Mapping[str, str]) -> str:
    """``template`` with each ``@NAME@`` replaced; an unknown name is refused."""

    def one(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise StepRefusedError(f"the move template names @{key}@, which is unset")
        return values[key]

    return PLACEHOLDER.sub(one, template)


def parse_stamps(text: str) -> dict[str, Any]:
    """The stopwatch's lines: ``t0``/``t1``/``t_compose`` and ``t2 UNIT`` as the
    rig's ``date +%s.%N``, ``rc_<step> N`` and ``timeout UNIT``. A ``###`` marker
    is not a stamp; any other line is kept as unparsed, never guessed at."""
    stamps: dict[str, Any] = {
        "t0": None,
        "t1": None,
        "t_compose": None,
        "t2": {},
        "rc": {},
        "timeout": [],
        "unparsed": [],
    }
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("###"):
            continue
        parts = line.split()
        try:
            if parts[0] in ("t0", "t1", "t_compose") and len(parts) == 2:
                stamps[parts[0]] = float(parts[1])
            elif parts[0] == "t2" and len(parts) == 3:
                stamps["t2"][parts[1]] = float(parts[2])
            elif parts[0].startswith("rc_") and len(parts) == 2:
                stamps["rc"][parts[0]] = int(parts[1])
            elif parts[0] == "timeout" and len(parts) == 2:
                stamps["timeout"].append(parts[1])
            else:
                stamps["unparsed"].append(line)
        except ValueError:
            stamps["unparsed"].append(line)
    return stamps


def move_times(
    stamps: Mapping[str, Any], targets: Sequence[str]
) -> tuple[float | None, dict[str, float]]:
    """``downtime_s`` = max(t2_u) - t0 when every target has a t2, and
    ``wake_s[u]`` = t2_u - t1 for each that has one. Filed, never judged here."""
    t0, t1 = stamps.get("t0"), stamps.get("t1")
    t2: Mapping[str, float] = stamps.get("t2") or {}
    wake = {u: round(t2[u] - t1, 3) for u in targets if u in t2 and t1 is not None}
    if t0 is None or not targets or any(u not in t2 for u in targets):
        return None, wake
    return round(max(t2[u] for u in targets) - t0, 3), wake


def key_values(text: str) -> dict[str, str]:
    """``key=value`` lines (a rig snapshot), or the fields of a ``### NAME`` marker."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        for token in line.removeprefix("###").split():
            key, sep, value = token.partition("=")
            if sep:
                out[key] = value
    return out


def vmstat(text: str) -> dict[str, int]:
    """``pswpout N`` and ``pgmajfault N``, as /proc/vmstat prints them."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in VMSTAT_FIELDS and parts[1].isdigit():
            out[parts[0]] = int(parts[1])
    return out


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(state: Path, name: str) -> str | None:
    path = state / name
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _json_or_raw(text: str | None) -> Any:
    """A harness answer as the JSON it printed, or the raw text it printed instead."""
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return {"raw": text}


def _write(out: Path, record: Mapping[str, Any]) -> None:
    out.write_text(
        json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def _common(state: Path, door: Door) -> dict[str, Any]:
    snap_start, snap_end = _text(state, "snap-start"), _text(state, "snap-end")
    vm_start, vm_end = _text(state, "vmstat-start"), _text(state, "vmstat-end")
    failure = _text(state, "failure")
    return {
        "run_id": door.run_id,
        "host": door.host,
        "round": os.environ.get("RUN_ROUND"),
        "product_sha256": os.environ.get("RUN_PRODUCT_SHA256"),
        "snapshots": {
            "start": None if snap_start is None else key_values(snap_start),
            "end": None if snap_end is None else key_values(snap_end),
        },
        "markers": {
            "start": (_text(state, "marker-start") or "").strip() or None,
            "end": (_text(state, "marker-end") or "").strip() or None,
            "on_rig": _text(state, "readback"),
        },
        "vmstat": {
            "start": None if vm_start is None else vmstat(vm_start),
            "end": None if vm_end is None else vmstat(vm_end),
        },
        "started_at": (_text(state, "started_at") or "").strip() or None,
        "ended_at": _now(),
        "failure": None if failure is None else failure.strip(),
    }


def write_unit(state: Path, out: Path, door: Door) -> None:
    """``_unit.sh``'s artifact, whole, from what the step left in ``state``."""
    facts = json.loads(_text(state, "unit.json") or "{}")
    wake = (_text(state, "wake_s") or "").strip()
    restarts = (_text(state, "restarts") or "").strip()
    _write(
        out,
        {
            "schema": UNIT_SCHEMA,
            **_common(state, door),
            "unit": facts.get("unit"),
            "image": {
                "tag": facts.get("image"),
                "digest": (_text(state, "digest") or "").strip() or None,
            },
            "argv": facts.get("argv"),
            "env": facts.get("env"),
            "container_id": (_text(state, "container_id") or "").strip() or None,
            "wake_s": float(wake) if wake else None,
            "harness": _json_or_raw(_text(state, "harness.json")),
            "load": _json_or_raw(_text(state, "load.json")),
            "restarts": int(restarts) if restarts.isdigit() else None,
        },
    )


def write_move(state: Path, out: Path, door: Door) -> None:
    """``_move.sh``'s artifact, whole, from what the step left in ``state``."""
    facts = json.loads(_text(state, "move.json") or "{}")
    readback, timed = _text(state, "readback"), _text(state, "timed.out")
    stamp_text = readback if readback and readback.strip() else timed
    stamps = parse_stamps(stamp_text or "")
    targets = [str(u) for u in (facts.get("to_units") or [])]
    downtime, wake = move_times(stamps, targets)
    compose = facts.get("compose")
    compose_sha = (
        hashlib.sha256(Path(compose).read_bytes()).hexdigest()
        if isinstance(compose, str) and compose and Path(compose).is_file()
        else None
    )
    ssh_exit = (_text(state, "ssh_exit") or "").strip()
    source_exit = (_text(state, "source_exit") or "").strip()
    _write(
        out,
        {
            "schema": MOVE_SCHEMA,
            **_common(state, door),
            "rig": facts.get("rig"),
            "from_fleet": facts.get("from_fleet"),
            "to_fleet": facts.get("to_fleet"),
            "from": facts.get("from"),
            "to": facts.get("to"),
            "target_kind": facts.get("target_kind"),
            "images": facts.get("images"),
            "stamps": stamps,
            "rc": stamps["rc"],
            "compose_sha256": compose_sha,
            "source_up": {
                "exit": int(source_exit) if source_exit.lstrip("-").isdigit() else None,
                "said": _text(state, "source.out"),
            },
            "downtime_s": downtime,
            "wake_s": wake,
            "stamp_text": stamp_text,
            "ssh_exit": int(ssh_exit) if ssh_exit.lstrip("-").isdigit() else None,
        },
    )


# --------------------------------------------------------------------------
# the commands the step bodies run
# --------------------------------------------------------------------------


def _unit_facts(root: Path, state: Path, name: str) -> str:
    door = Door.from_env(os.environ)
    fleet = load(root)
    unit, refused = unit_refusals(root, fleet, name, door)
    if unit is None:
        return shell_vars({"UNIT_REFUSED": "; ".join(refused)})
    from mcgyvr.fleet.read import _pace_counter

    pace_path = _pace_counter((fleet.get("units") or {})[name])[0]
    (state / "unit.json").write_text(
        json.dumps(
            {
                "unit": unit.name,
                "image": unit.image,
                "argv": list(unit.argv),
                "env": unit.env,
                "engine": unit.engine,
                "port": unit.port,
                "width": unit.width,
                "window": unit.window,
                "pace_path": pace_path,
            }
        ),
        encoding="utf-8",
    )
    fields = recorded(root, unit.rig, name) if not refused else {}
    return shell_vars(
        {
            "UNIT_REFUSED": "; ".join(refused),
            "UNIT_IMAGE": unit.image,
            "UNIT_RECORDED_IMAGE": recorded_image(fields),
            "UNIT_PORT": unit.port,
            "RIG_DIR_REMOTE": remote_dir(),
            "RIG_FILE_REMOTE": remote_file(door.run_id, "unit"),
        }
    )


def _run_args_nul(root: Path, name: str, container: str, image: str) -> str:
    unit = launch(load(root), name)
    return "".join(f"{arg}\0" for arg in run_args(unit, container, image))


def _harness_command(state: Path, mode: str, container: str, poll_file: str) -> str:
    from mcgyvr.fleet.harness import HARNESS_WORD

    facts = json.loads((state / "unit.json").read_text(encoding="utf-8"))
    spec: dict[str, Any] = {
        "mode": mode,
        "engine": facts["engine"],
        "port": facts["port"],
    }
    if mode == "load":
        spec |= {
            "width": facts["width"],
            "window": facts["window"],
            "container": container,
            "poll": Path(poll_file).read_text(encoding="utf-8"),
            "pace_path": facts["pace_path"],
        }
    return f"python3 - {HARNESS_WORD} {shlex.quote(json.dumps(spec))}"


def _move_facts(
    root: Path, state: Path, rig: str, from_fleet: str, to_fleet: str, compose: str
) -> str:
    door = Door.from_env(os.environ)
    refused: list[str] = []
    if rig != door.host:
        refused.append(f"the move is on {rig}, and this run is on {door.host}")
    try:
        fleet = load(root)
        source, target = move_sides(fleet, rig, from_fleet, to_fleet)
    except StepRefusedError as exc:
        return shell_vars({"MOVE_REFUSED": "; ".join([*refused, str(exc)])})
    groups = [s for s in (source, target) if s.compose]
    if len(groups) > 1:
        refused.append(
            f"both sides of {from_fleet} -> {to_fleet} on {rig} are compose groups, "
            "and this step takes one compose file"
        )
    runs = [unit for s in (target, source) if not s.compose for unit in s.units]
    named = [unit for unit in runs if unit.model == door.model]
    if not named:
        models = ", ".join(unit.model for unit in runs) or "none"
        refused.append(
            f"--model {door.model} is no llama.cpp unit of this move (its units' "
            f"--model: {models})"
        )
    else:
        refused += door_refusals(named[0], door)
    for unit in (*source.units, *target.units):
        refused += launch_refusals(root, unit)
    for group in groups[:1]:
        refused += compose_refusals(fleet, group, compose)
    images = sorted(
        {
            (unit.image, recorded_image(recorded(root, rig, unit.name)))
            for unit in (*source.units, *target.units)
            if not launch_refusals(root, unit)
        }
    )
    run_id = door.run_id
    (state / "move.json").write_text(
        json.dumps(
            {
                "rig": rig,
                "from_fleet": from_fleet,
                "to_fleet": to_fleet,
                "from": source.slots,
                "to": target.slots,
                "from_units": [u.name for u in source.units],
                "to_units": [u.name for u in target.units],
                "source_kind": "compose" if source.compose else "run",
                "target_kind": "compose" if target.compose else "run",
                "compose": compose if groups else None,
                "images": [list(pair) for pair in images],
            }
        ),
        encoding="utf-8",
    )
    all_names = names_of(source, run_id) + names_of(target, run_id)
    return shell_vars(
        {
            "MOVE_REFUSED": "; ".join(refused),
            "MOVE_SOURCE_KIND": "compose" if source.compose else "run",
            "MOVE_TARGET_KIND": "compose" if target.compose else "run",
            "MOVE_SOURCE_UNIT": "" if source.compose else source.units[0].name,
            "MOVE_TARGET_UNIT": "" if target.compose else target.units[0].name,
            "MOVE_IMAGES": " ".join(tag for tag, _ in images),
            "MOVE_ALL_NAMES": " ".join(all_names),
            "RIG_DIR_REMOTE": remote_dir(),
            "RIG_FILE_REMOTE": remote_file(run_id, "move"),
        }
    )


def _move_values(root: Path, state: Path, digests: str) -> str:
    """The template's values, once each image has resolved to its digest.

    ``digests`` is ``TAG=DIGEST`` per line, as the step's ``image_digest`` read
    them; a digest that is not the one the digests file recorded is refused.
    """
    door = Door.from_env(os.environ)
    facts = json.loads((state / "move.json").read_text(encoding="utf-8"))
    resolved = dict(
        line.split("=", 1) for line in digests.splitlines() if "=" in line.strip()
    )
    refused = [
        f"image {tag} resolves to {resolved.get(tag) or 'nothing'}, and "
        f"digests-{facts['rig']}.json records {want}"
        for tag, want in facts["images"]
        if digest_part(resolved.get(tag, "")) != want
    ]
    fleet = load(root)
    source, target = move_sides(
        fleet, facts["rig"], facts["from_fleet"], facts["to_fleet"]
    )
    values = {
        "RUN_ID": shlex.quote(door.run_id),
        "RIG_DIR": remote_dir(),
        "PROJECT": shlex.quote(_project()),
        "SOURCE_NAMES": " ".join(shlex.quote(n) for n in names_of(source, door.run_id)),
        "ALL_NAMES": " ".join(
            shlex.quote(n)
            for n in names_of(source, door.run_id) + names_of(target, door.run_id)
        ),
        "SOURCE_POLLS": polls(source),
        "TARGET_POLLS": polls(target),
    }
    for key, group in (("SOURCE", source), ("TARGET", target)):
        if not group.compose:
            unit = group.units[0]
            args = run_args(
                unit, f"{door.run_id}-{unit.name}", resolved.get(unit.image, "")
            )
            values[f"{key}_RUN_ARGS"] = shlex.join(args)
    (state / "values.json").write_text(json.dumps(values), encoding="utf-8")
    return shell_vars({"MOVE_REFUSED": "; ".join(refused)})


def _project() -> str:
    from mcgyvr.serving.servelib import PROJECT

    return PROJECT


def _render(state: Path, suffix: str) -> str:
    values = json.loads((state / "values.json").read_text(encoding="utf-8"))
    run_id = shlex.quote(Door.from_env(os.environ).run_id)
    values["RIG_FILE"] = f'"$HOME"/{RIG_DIR}/{run_id}.{suffix}'
    return render(sys.stdin.read(), values)


def main(argv: list[str]) -> int:
    """The commands ``_unit.sh`` and ``_move.sh`` run. A refusal is exit 2."""
    command, args = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
    door = Door.from_env(os.environ)
    try:
        if command == "unit-facts" and len(args) == 3:
            sys.stdout.write(_unit_facts(Path(args[0]), Path(args[1]), args[2]))
        elif command == "run-args" and len(args) == 4:
            sys.stdout.write(_run_args_nul(Path(args[0]), *args[1:]))
        elif command == "harness-command" and len(args) == 4:
            sys.stdout.write(_harness_command(Path(args[0]), *args[1:]))
        elif command == "harness-path" and not args:
            from mcgyvr.fleet import harness

            sys.stdout.write(f"{harness.__file__}\n")
        elif command == "move-facts" and len(args) == 6:
            sys.stdout.write(_move_facts(Path(args[0]), Path(args[1]), *args[2:]))
        elif command == "move-values" and len(args) == 3:
            sys.stdout.write(_move_values(Path(args[0]), Path(args[1]), args[2]))
        elif command == "render" and len(args) == 2:
            sys.stdout.write(_render(Path(args[0]), args[1]))
        elif command == "write-unit" and len(args) == 2:
            write_unit(Path(args[0]), Path(args[1]), door)
        elif command == "write-move" and len(args) == 2:
            write_move(Path(args[0]), Path(args[1]), door)
        else:
            print(
                f"lockfleets.py: no command {command!r} of {len(args)}", file=sys.stderr
            )
            return 2
    except StepRefusedError as exc:
        print(f"lockfleets.py: REFUSED — {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
