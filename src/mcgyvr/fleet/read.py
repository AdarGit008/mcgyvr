""

from __future__ import annotations

import base64
import binascii
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mcgyvr.fleet import alerts, ids
from mcgyvr.fleet.admit import layout_ids
from mcgyvr.serving.servelib import PROJECT

#
OURS_PREFIX = "mcgyvr-"
#
#
#
BACKEND_LINE_MAX = 400
#
RIG_ROWS = "rig.jsonl"
#
UNIT_FIELDS = ("card_mib", "restarts")
#
#
#
#
PACE_COUNTERS: dict[str, tuple[str, str]] = {
    "vllm": ("/metrics", "vllm:prompt_tokens_total"),
}
#
NO_PACE_COUNTER = (
    "none: llama-server answers /metrics 501 unless started with --metrics "
    "(src/mcgyvr/pool.py), and this unit's launch has no --metrics; the slot "
    "JSON build 10644 logs (/slots) carries id, n_ctx, speculative and "
    "is_processing, and no prompt token count"
)

#
Measure = Callable[[str, str], str | None]


class ReadError(Exception):
    ""


@dataclass(frozen=True)
class Container:
    ""

    name: str
    id: str
    project: str
    #
    restarts: int | None

    @property
    def ours(self) -> bool:
        return self.project == PROJECT or self.name.startswith(OURS_PREFIX)


@dataclass(frozen=True)
class Holder:
    ""

    pid: int
    mib: int | None
    #
    container: str | None
    #
    attributed: bool
    process: str


@dataclass
class Reading:
    ""

    #
    machine: dict[str, Any] = field(default_factory=dict)
    containers: list[Container] = field(default_factory=list)
    holders: list[Holder] = field(default_factory=list)
    #
    #
    sleeping: dict[int, bool | None] = field(default_factory=dict)
    #
    #
    sleep_unread: set[int] = field(default_factory=set)
    #
    status: dict[int, str] = field(default_factory=dict)
    #
    #
    #
    backend: dict[int, str | None] = field(default_factory=dict)
    #
    #
    backend_line: dict[int, str] = field(default_factory=dict)


def _digits(value: str) -> int | None:
    return int(value) if value.isascii() and value.isdigit() else None


def reading(machine: Mapping[str, Any], text: str) -> Reading:
    ""
    if not isinstance(machine, Mapping) or not isinstance(
        machine.get("snapshot"), Mapping
    ):
        raise ReadError("the machine's reading is not one the reader prints")
    found = parse(text)
    found.machine = dict(machine)
    return found


def parse(text: str) -> Reading:
    ""
    reading = Reading()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key, sep, value = line.partition("=")
        if not sep or " " in line:
            raise ReadError(f"the reader printed {line!r}, not one key=value")
        parts = value.split(",")
        if key == "container":
            if len(parts) != 4:
                raise ReadError(
                    f"a container row is NAME,ID,PROJECT,RESTARTS: {line!r}"
                )
            name, ident, project, restarts = parts
            reading.containers.append(
                Container(name, ident, project, _digits(restarts))
            )
        elif key == "gpu_app":
            if len(parts) != 4 or _digits(parts[0]) is None:
                raise ReadError(
                    f"a card holder row is PID,MIB,CONTAINER,PROCESS: {line!r}"
                )
            pid, mib, cid, process = parts
            reading.holders.append(
                Holder(
                    pid=int(pid),
                    mib=_digits(mib),
                    container=None if cid in ("none", "unread") else cid,
                    attributed=cid != "unread",
                    process=process,
                )
            )
        elif key == "sleeping":
            port = _digits(parts[0])
            if len(parts) != 2 or port is None:
                raise ReadError(f"a sleeping row is PORT,STATE: {line!r}")
            states: dict[str, bool | None] = {
                "true": True,
                "false": False,
                "none": None,
            }
            if parts[1] in states:
                reading.sleeping[port] = states[parts[1]]
            else:
                reading.sleep_unread.add(port)
        elif key == "status":
            port = _digits(parts[0])
            if len(parts) != 2 or port is None:
                raise ReadError(f"a status row is PORT,BASE64: {line!r}")
            try:
                reading.status[port] = base64.b64decode(parts[1]).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise ReadError(f"the status page of :{port} does not decode") from exc
        elif key == "backend":
            port = _digits(parts[0])
            if len(parts) != 2 or port is None:
                raise ReadError(f"a backend row is PORT,BACKEND: {line!r}")
            reading.backend[port] = None if parts[1] in ("", "none") else parts[1]
        elif key == "backend_line":
            port = _digits(parts[0])
            if len(parts) != 2 or port is None:
                raise ReadError(f"a backend line row is PORT,BASE64: {line!r}")
            try:
                said = base64.b64decode(parts[1]).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise ReadError(f"the backend line of :{port} does not decode") from exc
            reading.backend_line[port] = said[:BACKEND_LINE_MAX]
        else:
            raise ReadError(f"the reader printed {line!r}, not a line it prints")
    return reading


@dataclass(frozen=True)
class Live:
    ""

    name: str
    folder: Path
    fleet: dict[str, Any]
    locked: bool = True

    def slots(self, rig: str) -> list[tuple[str, Mapping[str, Any], str]]:
        ""
        layout = self.fleet["fleets"][self.name].get("layout", {})
        units = self.fleet.get("units", {})
        return [
            (str(slot[0]), units[slot[0]], str(slot[1]))
            for slot in layout.get(rig) or []
            if slot is not None
        ]

    def combination(self, rig: str) -> str:
        layout = self.fleet["fleets"][self.name].get("layout", {})
        return layout_ids(self.fleet, layout)[self.locked_rig_id(rig)]

    def locked_rig_id(self, rig: str) -> str:
        return str(self.fleet["rigs"][rig]["rig_id"])


def live() -> Live:
    ""
    from mcgyvr.fleet.probe import ProbeError, _live

    try:
        name, folder, fleet = _live(None)
    except ProbeError as exc:
        raise ReadError(str(exc)) from exc
    return Live(name, folder, fleet)


def port_of(unit: Mapping[str, Any]) -> int:
    port = urlsplit(str(unit.get("address") or "")).port
    if port is None:
        raise ReadError(f"{unit.get('address')!r} names no port")
    return port


def engine_of(unit: Mapping[str, Any]) -> str:
    engine = unit.get("engine")
    return engine if isinstance(engine, str) and engine else "llama.cpp"


def named(fleet_name: str, setup: Path | None) -> Live:
    ""
    from mcgyvr.fleet.files import FleetFileError, load_fleet

    if setup is None:
        raise ReadError(
            f"--fleet {fleet_name} names a fleet of a setup, and this read ran "
            "under no config: set MCGYVR_CONFIG to the setup that declares it"
        )
    folder = setup if setup.is_dir() else setup.parent
    path = folder / "fleet.yaml"
    try:
        fleet = load_fleet(path.read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise ReadError(f"{path} cannot be read: {exc}") from exc
    if fleet_name not in (fleet.get("fleets") or {}):
        raise ReadError(f"{path} declares no fleet {fleet_name!r}")
    return Live(fleet_name, folder, fleet, locked=False)


def prepare(
    host: str,
    probe: Sequence[str] = (),
    load: str | None = None,
    *,
    fleet_name: str | None = None,
    setup: Path | None = None,
) -> Live:
    ""
    if load is not None:
        if not probe:
            raise ReadError(
                "--load needs --probe: a load runs on the units a probe names"
            )
        load_spec(load)
    fleet = live() if fleet_name is None else named(fleet_name, setup)
    which = "the live fleet" if fleet.locked else f"the setup {fleet.folder}'s fleet"
    layout = fleet.fleet["fleets"][fleet.name].get("layout", {})
    if host not in layout:
        raise ReadError(f"{host} is not a rig of {which} {fleet.name}")
    awake = {name for name, _, state in fleet.slots(host) if state == "awake"}
    strangers = [name for name in probe if name not in awake]
    if strangers:
        raise ReadError(
            f"{', '.join(strangers)}: not an awake unit of {fleet.name} on {host}, "
            "so there is nothing of the fleet's to measure there"
        )
    return fleet


def reader_args(fleet: Live, host: str) -> list[str]:
    ""
    args: list[str] = []
    for _, unit, _ in fleet.slots(host):
        parts = [engine_of(unit), str(port_of(unit)), str(unit.get("container") or "")]
        args.append(":".join(part for part in parts if part))
    return args


@dataclass
class Observed:
    ""

    rig_id: str
    #
    #
    #
    units: dict[str, str]
    #
    foreign: list[str]
    #
    card_mib: dict[str, int | None]
    #
    restarts: dict[str, int | None]
    #
    in_flight: dict[str, int | None]
    #
    containers: dict[str, str] = field(default_factory=dict)
    #
    backend: dict[str, str | None] = field(default_factory=dict)
    #
    backend_line: dict[str, str] = field(default_factory=dict)


def observe(fleet: Live, host: str, reading: Reading) -> Observed:
    ""
    from mcgyvr.runner import status_busy

    try:
        rig_id = ids.rig_id(reading.machine)
    except ValueError as exc:
        raise ReadError(f"{host}: {exc}") from exc
    by_name = {container.name: container for container in reading.containers}
    ours = {container.id for container in reading.containers if container.ours}
    named = {str(unit.get("container")) for _, unit, _ in fleet.slots(host)}

    observed = Observed(rig_id, {}, [], {}, {}, {})
    for name, unit, _state in fleet.slots(host):
        port = port_of(unit)
        observed.in_flight[name] = status_busy(
            engine_of(unit), reading.status.get(port)
        )
        container = by_name.get(str(unit.get("container")))
        if container is None:
            continue
        observed.units[str(unit["unit_id"])] = _sleep_state(
            engine_of(unit), port, reading
        )
        observed.containers[name] = container.id
        if engine_of(unit) == "vllm":
            observed.backend[name] = reading.backend.get(port)
            observed.backend_line[name] = reading.backend_line.get(port, "")
        held = [h for h in reading.holders if h.container == container.id]
        observed.card_mib[name] = (
            None if any(h.mib is None for h in held) else sum(h.mib or 0 for h in held)
        )
        observed.restarts[name] = container.restarts
    for container in reading.containers:
        if container.id in ours and container.name not in named:
            observed.units[container.name] = "awake"
    names = {container.id: container.name for container in reading.containers}
    for holder in reading.holders:
        mib = "unread" if holder.mib is None else f"{holder.mib} MiB"
        if not holder.attributed:
            observed.foreign.append(
                f"{holder.process} (pid {holder.pid}, {mib}, its cgroup unreadable)"
            )
        elif holder.container is None or holder.container not in ours:
            inside = names.get(holder.container or "")
            where = f", in container {inside}" if inside else ""
            observed.foreign.append(
                f"{holder.process} (pid {holder.pid}, {mib}{where})"
            )
    return observed


def _sleep_state(engine: str, port: int, reading: Reading) -> str:
    ""
    said = reading.sleeping.get(port)
    if said is True:
        return "asleep"
    unread = port in reading.sleep_unread or port not in reading.sleeping
    if engine == "vllm" and unread:
        return "unread"
    return "awake"


@dataclass
class Recorded:
    ""

    observed: Observed
    probed: dict[str, dict[str, float]] = field(default_factory=dict)
    #
    samples: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    busy: dict[str, int] = field(default_factory=dict)
    contended: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    not_read: dict[str, list[str]] = field(default_factory=dict)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    #
    loads: dict[str, dict[str, Any]] = field(default_factory=dict)
    #
    unloaded: dict[str, str] = field(default_factory=dict)


def _at(run_id: str) -> str:
    from mcgyvr.serving.run import READ_ID

    match = READ_ID.match(run_id)
    if match is None:
        raise ReadError(f"{run_id!r} is not a read id (run-YYYYMMDDTHHMMSS-xxxxxxxx)")
    s = match.group(1)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}"


def load_spec(spec: str) -> tuple[int, int]:
    ""
    from mcgyvr.serving.run import LOAD_SPEC

    match = LOAD_SPEC.match(spec)
    if match is None:
        raise ReadError(f"--load {spec!r} is not WxN, e.g. 8x4096")
    return int(match.group(1)), int(match.group(2))


@dataclass
class _Filing:
    ""

    journal: Path
    stamp: dict[str, str]
    stamps: dict[str, str]
    done: Recorded

    def unit_stamp(self, unit_id: str) -> dict[str, str]:
        return {**self.stamp, "unit_id": unit_id}

    def record(self, unit_id: str, values: Mapping[str, Any]) -> None:
        ""
        alerts.record(self.journal, self.unit_stamp(unit_id), {**self.stamps, **values})

    def check(
        self,
        unit_id: str,
        observations: Sequence[Mapping[str, Any]],
        approved: Mapping[str, Any],
    ) -> None:
        ""
        self.done.alerts.extend(
            alerts.check(
                observations,
                approved=approved,
                journal_dir=self.journal,
                stamp=self.unit_stamp(unit_id),
                run_id=self.stamps["run_id"],
                lease_id=self.stamps["lease_id"],
            )
        )


def record(
    host: str,
    machine: Mapping[str, Any],
    text: str,
    *,
    run_id: str,
    probe: Sequence[str] = (),
    measure: Measure | None = None,
    load: str | None = None,
    fleet_name: str | None = None,
    setup: Path | None = None,
) -> Recorded:
    ""
    from mcgyvr.fleet.probe import journal_dir

    fleet = prepare(host, probe, load, fleet_name=fleet_name, setup=setup)
    width, window = load_spec(load) if load is not None else (0, 0)
    at = _at(run_id)
    taken = reading(machine, text)
    observed = observe(fleet, host, taken)
    done = Recorded(observed)
    filing = _Filing(
        journal=journal_dir(fleet.folder),
        stamp={
            "fleet": fleet.name,
            "rig": host,
            "rig_id": fleet.locked_rig_id(host),
            "combination_id": fleet.combination(host),
            #
            **({} if fleet.locked else {"locked": "false", "setup": str(fleet.folder)}),
        },
        stamps={
            "run_id": run_id,
            "lease_id": f"read-{run_id.rsplit('-', 1)[1]}",
            "at": at,
        },
        done=done,
    )

    probes: dict[str, dict[str, Any]] = {}
    for name in probe:
        answer = _measure_probe(fleet, name, measure, done)
        if answer is not None:
            probes[name] = answer
    loads: dict[str, dict[str, Any]] = {}
    for name in probe if load is not None else ():
        answer = _measure_load(
            fleet, name, measure, done, probes.get(name), width, window
        )
        if answer is not None:
            loads[name] = answer

    _file_units(fleet, host, filing)
    for name, answer in probes.items():
        _file_probe(fleet, host, name, answer, filing)
    for name, answer in loads.items():
        _file_load(fleet, name, answer, width, window, filing)

    row = {
        **filing.stamp,
        **filing.stamps,
        "observed_rig_id": observed.rig_id,
        "snapshot": taken.machine.get("snapshot") or {},
        "units": observed.units,
        "foreign": observed.foreign,
        "probed": done.probed,
        "busy": done.busy,
        "contended": done.contended,
        "failed": done.failed,
        "not_read": done.not_read,
        "loaded": sorted(done.loads),
        "unloaded": done.unloaded,
    }
    where = filing.journal / filing.stamp["combination_id"]
    where.mkdir(parents=True, exist_ok=True)
    with (where / RIG_ROWS).open("a", encoding="utf-8") as rows:
        rows.write(json.dumps(row, sort_keys=True) + "\n")
    return done


def _answer(text: str | None) -> dict[str, Any] | None:
    ""
    try:
        answer = json.loads(text or "")
    except ValueError:
        return None
    return answer if isinstance(answer, dict) else None


def _file_units(fleet: Live, host: str, filing: _Filing) -> None:
    ""
    observed = filing.done.observed
    for name, unit, _state in fleet.slots(host):
        unit_id = str(unit["unit_id"])
        if unit_id not in observed.units:
            continue
        if observed.units[unit_id] == "unread":
            filing.done.not_read.setdefault(name, []).append("sleeping")
        judged: list[dict[str, Any]] = []
        for field_name, value in (
            ("card_mib", observed.card_mib.get(name)),
            ("restarts", observed.restarts.get(name)),
        ):
            if value is None:
                filing.done.not_read.setdefault(name, []).append(field_name)
                filing.record(
                    unit_id, {"field": field_name, "observed": None, "read": False}
                )
                continue
            judged.append(
                {
                    "unit_id": unit_id,
                    "unit": name,
                    "field": field_name,
                    "observed": value,
                }
            )
        room = unit.get("room_mib")
        filing.check(
            unit_id, judged, {unit_id: {} if room is None else {"room_mib": room}}
        )
        if name in observed.backend:
            backend = observed.backend[name]
            filing.record(
                unit_id,
                {
                    "field": "attention_backend",
                    "observed": backend,
                    "attention_backend": backend,
                },
            )
            #
            #
            #
            said = observed.backend_line.get(name, "")
            filing.record(
                unit_id,
                {
                    "field": "attention_backend_line",
                    "observed": said,
                    "attention_backend_line": said,
                },
            )


def _measure_probe(
    fleet: Live, name: str, measure: Measure | None, done: Recorded
) -> dict[str, Any] | None:
    ""
    unit = fleet.fleet["units"][name]
    before = done.observed.in_flight.get(name)
    if before is None:
        done.failed[name] = "its in-flight page could not be read on the rig"
        return None
    if before > 0:
        done.busy[name] = before
        return None
    if measure is None:
        done.failed[name] = "no harness was given to run on the rig"
        return None
    spec = {"mode": "probe", "engine": engine_of(unit), "port": port_of(unit)}
    answer = _answer(measure(name, json.dumps(spec)))
    if answer is None:
        done.failed[name] = "the harness on the rig printed no answer"
        return None
    if not isinstance(answer.get("figures"), dict):
        why = answer.get("error")
        done.failed[name] = f"the harness on the rig could not measure: {why}"
        return None
    figures = answer["figures"]
    done.probed[name] = {
        str(k): float(v) for k, v in figures.items() if not isinstance(v, list)
    }
    done.samples[name] = {
        str(k): [float(s) for s in v] for k, v in figures.items() if isinstance(v, list)
    }
    return answer


def _file_probe(
    fleet: Live, host: str, name: str, answer: Mapping[str, Any], filing: _Filing
) -> None:
    ""
    from mcgyvr.derived import DerivedNumbersError, class_tolerances
    from mcgyvr.fleet.harness import HarnessError
    from mcgyvr.fleet.probe import _approved
    from mcgyvr.runner import status_busy

    unit = fleet.fleet["units"][name]
    unit_id = str(unit["unit_id"])
    figures = filing.done.probed[name]
    after = status_busy(engine_of(unit), answer.get("after_page"))
    contended = after is None or after > 0
    #
    for field_name, samples in filing.done.samples.get(name, {}).items():
        values: dict[str, Any] = {"field": field_name, "observed": samples}
        if contended:
            values |= {"contended": True, "in_flight_after": after}
        filing.record(unit_id, values)
    if contended:
        filing.done.contended.append(name)
        for field_name, value in figures.items():
            filing.record(
                unit_id,
                {
                    "field": field_name,
                    "observed": value,
                    "contended": True,
                    "in_flight_after": after,
                },
            )
        return
    if not fleet.locked:
        for field_name, value in figures.items():
            filing.record(
                unit_id,
                {
                    "field": field_name,
                    "observed": value,
                    "judged": False,
                    "why_unjudged": "a setup's fleet has no lock record to judge by",
                },
            )
        return
    try:
        approved = _approved(
            fleet.folder,
            fleet.locked_rig_id(host),
            filing.stamp["combination_id"],
            name,
            unit,
            class_tolerances(),
        )
    except (HarnessError, DerivedNumbersError) as exc:
        filing.done.failed[name] = str(exc)
        return
    filing.check(
        unit_id,
        [
            {"unit_id": unit_id, "unit": name, "field": f, "observed": v}
            for f, v in figures.items()
        ],
        approved,
    )


def _measure_load(
    fleet: Live,
    name: str,
    measure: Measure | None,
    done: Recorded,
    probed: Mapping[str, Any] | None,
    width: int,
    window: int,
) -> dict[str, Any] | None:
    ""
    from mcgyvr.runner import status_busy
    from mcgyvr.serving.run import GATE_SCRIPTS

    unit = fleet.fleet["units"][name]
    if done.observed.in_flight.get(name) != 0 or name in done.failed:
        done.unloaded[name] = "it was not read idle on the rig"
        return None
    if probed is not None:
        after = status_busy(engine_of(unit), probed.get("after_page"))
        if after != 0:
            done.unloaded[name] = f"it had {after} in flight after its probe"
            return None
    container = done.observed.containers.get(name)
    if container is None:
        done.unloaded[name] = "its container is not up"
        return None
    if measure is None:
        done.unloaded[name] = "no harness was given to run on the rig"
        return None
    spec = {
        "mode": "load",
        "engine": engine_of(unit),
        "port": port_of(unit),
        "width": width,
        "window": window,
        "container": container,
        "poll": (GATE_SCRIPTS / "rig-units.sh").read_text(encoding="utf-8"),
        "pace_path": _pace_counter(unit)[0],
    }
    answer = _answer(measure(name, json.dumps(spec)))
    if answer is None or not isinstance(answer.get("load"), dict):
        why = "no answer" if answer is None else answer.get("error")
        done.failed[name] = f"the load on the rig could not run: {why}"
        return None
    return answer


def _file_load(
    fleet: Live,
    name: str,
    answer: Mapping[str, Any],
    width: int,
    window: int,
    filing: _Filing,
) -> None:
    ""
    from mcgyvr.fleet.alerts import _already_alerted, _journal_file, _judge, _warning
    from mcgyvr.fleet.harness import LOAD_LIMIT_S
    from mcgyvr.runner import status_busy

    unit = fleet.fleet["units"][name]
    unit_id = str(unit["unit_id"])
    container = filing.done.observed.containers[name]
    body = answer["load"]
    samples = [s for s in body.get("samples") or [] if isinstance(s, str)]

    def held_mib(sample: str) -> int | None:
        try:
            held = [h for h in parse(sample).holders if h.container == container]
        except ReadError:
            return None
        if held and all(h.mib is not None for h in held):
            return sum(h.mib or 0 for h in held)
        return None

    #
    #
    #
    #
    mibs = [held_mib(sample) for sample in samples]
    index = body.get("samples_before_close")
    held_before = isinstance(index, int) and 0 <= index <= len(samples)
    cut = index if held_before else len(samples)
    peaks = [mib for mib in mibs if mib is not None]
    early = [mib for mib in mibs[:cut] if mib is not None]
    peak = max(peaks) if peaks else None
    errors = [str(error) for error in body.get("errors") or []]
    completed = body.get("completed") if isinstance(body.get("completed"), int) else 0
    closed = body.get("closed_unfinished")
    pace, pace_source = _pace(unit, body)
    in_flight_after = status_busy(engine_of(unit), body.get("after_page"))
    row: dict[str, Any] = {
        "field": "load_peak_mib",
        "observed": peak,
        "unit": name,
        "spec": f"{width}x{window}",
        "peak_mib": peak,
        "samples": len(samples),
        "samples_before_close": cut,
        "peak_before_close_mib": max(early) if early else None,
        "sampled_until_idle": body.get("sampled_until_idle") is True,
        "container": container,
        "started_at": body.get("started_at"),
        "finished_at": body.get("finished_at"),
        "restarts_before": _digits(str(body.get("restarts_before") or "").strip()),
        "restarts_after": _digits(str(body.get("restarts_after") or "").strip()),
        "width": width,
        "limit_s": body.get("limit_s", LOAD_LIMIT_S),
        "completed": completed,
        "closed_unfinished": closed if isinstance(closed, int) else None,
        "pace_prompt_tok_s": pace,
        "pace_source": pace_source,
        "idle_after": None if in_flight_after is None else in_flight_after == 0,
        "in_flight_after": in_flight_after,
        "idle_after_close": body.get("idle_after_close"),
        "idle_after_s": body.get("idle_after_s"),
        "idle_error": body.get("idle_error"),
        "errors": errors[:5],
        "prompt_tokens": body.get("prompt_tokens"),
        "max_tokens": body.get("max_tokens"),
    }
    if isinstance(body.get("finished_at"), str):
        row["at"] = body["finished_at"]
    filing.done.loads[name] = row
    room = unit.get("room_mib")
    if peak is None or room is None or errors:
        filing.record(unit_id, row)
        return
    observation = {
        "unit_id": unit_id,
        "unit": name,
        "field": "load_peak_mib",
        "observed": peak,
    }
    alert = _judge(observation, {unit_id: {"room_mib": room}})
    path = _journal_file(filing.journal, filing.stamp["combination_id"], unit_id)
    warned = _already_alerted(path, "load_peak_mib")
    filing.record(unit_id, {**row, "alert": alert is not None})
    if alert is None:
        return
    filing.done.alerts.append(alert)
    if not warned:
        print(
            _warning(observation, filing.unit_stamp(unit_id), unit_id), file=sys.stderr
        )


def _pace_counter(unit: Mapping[str, Any]) -> tuple[str | None, str | None, str]:
    ""
    engine = engine_of(unit)
    if engine in PACE_COUNTERS:
        path, name = PACE_COUNTERS[engine]
        return path, name, f"{name} on {path}: its change over the load's seconds"
    launch = unit.get("launch")
    argv = launch.get("argv") if isinstance(launch, Mapping) else None
    if isinstance(argv, list) and "--metrics" in argv:
        return (
            None,
            None,
            "none: this unit launches with --metrics, and no page of llama-server's "
            "counters is recorded to name its prompt counter from",
        )
    return None, None, NO_PACE_COUNTER


def _pace(unit: Mapping[str, Any], body: Mapping[str, Any]) -> tuple[float | None, str]:
    ""
    from mcgyvr.fleet.harness import metric_total

    _, counter, source = _pace_counter(unit)
    if counter is None:
        return None, source
    first, last = body.get("pace_start_page"), body.get("pace_end_page")
    if not isinstance(first, str) or not isinstance(last, str):
        return None, f"none: the load returned no {counter} page to read"
    before, after = metric_total(first, counter), metric_total(last, counter)
    seconds = body.get("pace_seconds")
    if before is None or after is None:
        return None, f"none: {counter} is not on the page the load read"
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, int | float)
        or seconds <= 0
    ):
        return None, f"none: the load read {counter} over no measurable time"
    if after < before:
        return None, f"none: {counter} went backwards over the load (a restart?)"
    return (after - before) / float(seconds), source


def observations(journal: Path, run_id: str) -> dict[str, dict[str, Any]]:
    ""
    found: dict[str, dict[str, Any]] = {}
    if not journal.is_dir():
        return found
    for path in sorted(journal.glob(f"*/{RIG_ROWS}")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(row, dict)
                and row.get("run_id") == run_id
                and isinstance(row.get("rig"), str)
            ):
                found[row["rig"]] = row
    return found


def judged(journal: Path, run_id: str) -> list[dict[str, Any]]:
    ""
    raised: list[dict[str, Any]] = []
    if not journal.is_dir():
        return raised
    for path in sorted(journal.rglob("*.jsonl")):
        if path.name == RIG_ROWS:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("run_id") == run_id and row.get("alert") is True:
                raised.append(
                    {"unit_id": row.get("unit_id"), "field": row.get("field")}
                )
    return raised


def door_read_argv(host: str, run_id: str, probe: Sequence[str] = ()) -> list[str]:
    ""
    from mcgyvr.serving.gatelib import DOOR_MODULE

    argv = [sys.executable, "-m", DOOR_MODULE, "read"]
    argv += ["--host", host]
    argv += ["--run-id", run_id]
    if probe:
        argv += ["--probe", *probe]
    return argv


def spawn_read(host: str, run_id: str, probe: Sequence[str] = ()) -> int:
    ""
    argv = door_read_argv(host, run_id, probe)
    done = subprocess.run(
        argv, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False
    )
    for said in (done.stdout, done.stderr):
        if said:
            sys.stderr.write(said)
    return done.returncode
