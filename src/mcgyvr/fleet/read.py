"""One reading of a rig, taken through the door, filed once and read back.

Owner, 2026-09-15 (D2, F2b): ``python -m mcgyvr.serving.run read`` ships one
reader to a rig — ``rig-snapshot.sh`` and ``rig-units.sh`` as one text — and
hands what comes back to :func:`record`. Nothing on the rig is started,
stopped or leased.

* :func:`parse` turns the reader's ``key=value`` lines into a :class:`Reading`.
* :func:`observe` says what the reading means for the live fleet on that rig:
  the rig id its snapshot names (:func:`mcgyvr.fleet.ids.rig_id`), our units and
  their state, and every card holder that is in no container of ours. A
  container is ours when it is in the ``mcgyvr`` compose project or is named
  ``mcgyvr-`` (``records/plans/fleet-identity.md`` §2). A unit of the fleet is
  found by the container name the lock records for it.
* :func:`record` files it under ``<journal.dir>/fleet`` with the usual stamps:
  one rig row per read (``<combination>/rig.jsonl``), and per unit its card MiB
  judged against its ``room_mib`` and its restarts judged against 0
  (:func:`mcgyvr.fleet.alerts.check`). A count the reader could not read is
  filed as not read, never as 0. With ``probe``, the lock's own harness runs on
  the rig at 127.0.0.1 on an idle unit only (:mod:`mcgyvr.fleet.harness`), and
  its figures are judged.
* :func:`observations` reads the rig rows of one read back, which is all live
  admission (:mod:`mcgyvr.fleet.admission`) and ``mcgyvr fleet probe`` ask of it.
* :func:`spawn_read` is the one place a command opens the door's ``read``.
"""

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

#: The name every unit ``mcgyvr emit`` writes starts with.
OURS_PREFIX = "mcgyvr-"
#: The rig row of every read, beside the unit rows of its combination.
RIG_ROWS = "rig.jsonl"
#: The fields a read judges per unit.
UNIT_FIELDS = ("card_mib", "restarts")

#: ``(unit name, harness spec)`` -> what the harness printed on the rig.
Measure = Callable[[str, str], str | None]


class ReadError(Exception):
    """The reading cannot be taken, understood or filed."""


@dataclass(frozen=True)
class Container:
    """One running container, as the reader listed it."""

    name: str
    id: str
    project: str
    #: docker's RestartCount, or ``None`` when the reader could not read it.
    restarts: int | None

    @property
    def ours(self) -> bool:
        return self.project == PROJECT or self.name.startswith(OURS_PREFIX)


@dataclass(frozen=True)
class Holder:
    """One process holding the card."""

    pid: int
    mib: int | None
    #: The container id its cgroup names, ``None`` for no container.
    container: str | None
    #: Whether its cgroup could be read at all.
    attributed: bool
    process: str


@dataclass
class Reading:
    """Everything one reader printed."""

    snapshot: dict[str, str] = field(default_factory=dict)
    containers: list[Container] = field(default_factory=list)
    holders: list[Holder] = field(default_factory=list)
    #: port -> what ``/is_sleeping`` said, ``None`` when it could not say.
    sleeping: dict[int, bool | None] = field(default_factory=dict)
    #: port -> the unit's in-flight page, as served.
    status: dict[int, str] = field(default_factory=dict)


def _digits(value: str) -> int | None:
    return int(value) if value.isascii() and value.isdigit() else None


def parse(text: str) -> Reading:
    """The reader's ``key=value`` lines as a :class:`Reading`, or refused."""
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
            reading.sleeping[port] = {"true": True, "false": False}.get(parts[1])
        elif key == "status":
            port = _digits(parts[0])
            if len(parts) != 2 or port is None:
                raise ReadError(f"a status row is PORT,BASE64: {line!r}")
            try:
                reading.status[port] = base64.b64decode(parts[1]).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise ReadError(f"the status page of :{port} does not decode") from exc
        else:
            reading.snapshot[key] = value
    return reading


@dataclass(frozen=True)
class Live:
    """The fleet ``~/.mcgyvr/live.json`` names, and its folder."""

    name: str
    folder: Path
    fleet: dict[str, Any]

    def slots(self, rig: str) -> list[tuple[str, Mapping[str, Any], str]]:
        """``(unit name, unit block, state)`` for each unit the layout puts on a rig."""
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
    """The live fleet, or :class:`ReadError` saying why there is none."""
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


def prepare(host: str, probe: Sequence[str] = ()) -> Live:
    """The live fleet a read of ``host`` is filed under, refused before any rig read.

    ``host`` must be a rig of the live fleet's layout, and every unit to probe an
    awake unit of it on that rig.
    """
    fleet = live()
    layout = fleet.fleet["fleets"][fleet.name].get("layout", {})
    if host not in layout:
        raise ReadError(f"{host} is not a rig of the live fleet {fleet.name}")
    awake = {name for name, _, state in fleet.slots(host) if state == "awake"}
    strangers = [name for name in probe if name not in awake]
    if strangers:
        raise ReadError(
            f"{', '.join(strangers)}: not an awake unit of {fleet.name} on {host}, "
            "so there is nothing of the lock's to measure there"
        )
    return fleet


def reader_args(fleet: Live, host: str) -> list[str]:
    """``ENGINE:PORT`` for each unit the layout puts on ``host``: ``rig-units.sh``'s."""
    return [f"{engine_of(unit)}:{port_of(unit)}" for _, unit, _ in fleet.slots(host)]


@dataclass
class Observed:
    """What one reading means for the live fleet on its rig."""

    rig_id: str
    #: unit id -> awake | asleep; a container of ours the fleet does not name is
    #: keyed by its container name.
    units: dict[str, str]
    #: every card holder in no container of ours, named.
    foreign: list[str]
    #: unit name -> MiB its container holds on the card, ``None`` when unread.
    card_mib: dict[str, int | None]
    #: unit name -> restarts, ``None`` when unread.
    restarts: dict[str, int | None]
    #: unit name -> what its own status page says it has in flight.
    in_flight: dict[str, int | None]


def observe(fleet: Live, host: str, reading: Reading) -> Observed:
    """The rig id, our units, their state and card, and what else holds the card."""
    from mcgyvr.runner import status_busy

    try:
        rig_id = ids.rig_id(reading.snapshot)
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
        asleep = reading.sleeping.get(port) is True
        observed.units[str(unit["unit_id"])] = "asleep" if asleep else "awake"
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


@dataclass
class Recorded:
    """What one read filed, for the door to print and a caller to act on."""

    observed: Observed
    probed: dict[str, dict[str, float]] = field(default_factory=dict)
    busy: dict[str, int] = field(default_factory=dict)
    contended: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    not_read: dict[str, list[str]] = field(default_factory=dict)
    alerts: list[dict[str, Any]] = field(default_factory=list)


def _at(run_id: str) -> str:
    from mcgyvr.serving.run import READ_ID

    match = READ_ID.match(run_id)
    if match is None:
        raise ReadError(f"{run_id!r} is not a read id (run-YYYYMMDDTHHMMSS-xxxxxxxx)")
    s = match.group(1)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}"


def record(
    host: str,
    text: str,
    *,
    run_id: str,
    profile: str,
    probe: Sequence[str] = (),
    measure: Measure | None = None,
) -> Recorded:
    """File one reading of ``host`` under the live fleet's journal, and judge it.

    A dev profile raises :class:`mcgyvr.fleet.alerts.AlertError` on an alert,
    after the rig row is filed.
    """
    from mcgyvr.fleet.probe import journal_dir

    fleet = prepare(host, probe)
    at = _at(run_id)
    lease_id = f"read-{run_id.rsplit('-', 1)[1]}"
    observed = observe(fleet, host, parse(text))
    journal = journal_dir(fleet.folder)
    stamp = {
        "fleet": fleet.name,
        "rig": host,
        "rig_id": fleet.locked_rig_id(host),
        "combination_id": fleet.combination(host),
    }
    done = Recorded(observed)
    stamps = {"run_id": run_id, "lease_id": lease_id, "at": at}
    raised: alerts.AlertError | None = None
    try:
        _judge_units(fleet, host, observed, journal, stamp, stamps, profile, done)
        for name in probe:
            _probe(fleet, host, name, measure, journal, stamp, stamps, profile, done)
    except alerts.AlertError as exc:
        raised = exc
    row = {
        **stamp,
        **stamps,
        "observed_rig_id": observed.rig_id,
        "units": observed.units,
        "foreign": observed.foreign,
        "probed": done.probed,
        "busy": done.busy,
        "contended": done.contended,
        "failed": done.failed,
        "not_read": done.not_read,
    }
    where = journal / stamp["combination_id"]
    where.mkdir(parents=True, exist_ok=True)
    with (where / RIG_ROWS).open("a", encoding="utf-8") as rows:
        rows.write(json.dumps(row, sort_keys=True) + "\n")
    if raised is not None:
        raise raised
    return done


def _judge_units(
    fleet: Live,
    host: str,
    observed: Observed,
    journal: Path,
    stamp: Mapping[str, str],
    stamps: Mapping[str, str],
    profile: str,
    done: Recorded,
) -> None:
    for name, unit, _state in fleet.slots(host):
        unit_id = str(unit["unit_id"])
        if unit_id not in observed.units:
            continue
        unit_stamp = {**stamp, "unit_id": unit_id}
        judged: list[dict[str, Any]] = []
        for field_name, value in (
            ("card_mib", observed.card_mib.get(name)),
            ("restarts", observed.restarts.get(name)),
        ):
            if value is None:
                done.not_read.setdefault(name, []).append(field_name)
                alerts.record(
                    journal,
                    unit_stamp,
                    {"field": field_name, "observed": None, "read": False, **stamps},
                )
                continue
            judged.append({"unit_id": unit_id, "field": field_name, "observed": value})
        room = unit.get("room_mib")
        approved = {unit_id: {} if room is None else {"room_mib": room}}
        done.alerts.extend(
            alerts.check(
                judged,
                approved=approved,
                profile=profile,
                journal_dir=journal,
                stamp=unit_stamp,
                run_id=stamps["run_id"],
                lease_id=stamps["lease_id"],
            )
        )


def _probe(
    fleet: Live,
    host: str,
    name: str,
    measure: Measure | None,
    journal: Path,
    stamp: Mapping[str, str],
    stamps: Mapping[str, str],
    profile: str,
    done: Recorded,
) -> None:
    """The lock's harness on the rig, for one idle unit, filed and judged."""
    from mcgyvr.derived import DerivedNumbersError, class_tolerances
    from mcgyvr.fleet.harness import HarnessError
    from mcgyvr.fleet.probe import _approved
    from mcgyvr.runner import status_busy

    unit = fleet.fleet["units"][name]
    before = done.observed.in_flight.get(name)
    if before is None:
        done.failed[name] = "its in-flight page could not be read on the rig"
        return
    if before > 0:
        done.busy[name] = before
        return
    if measure is None:
        done.failed[name] = "no harness was given to run on the rig"
        return
    spec = json.dumps({"engine": engine_of(unit), "port": port_of(unit)})
    try:
        answer = json.loads(measure(name, spec) or "")
    except ValueError:
        done.failed[name] = "the harness on the rig printed no answer"
        return
    if not isinstance(answer, dict) or not isinstance(answer.get("figures"), dict):
        why = answer.get("error") if isinstance(answer, dict) else None
        done.failed[name] = f"the harness on the rig could not measure: {why}"
        return
    figures = {str(k): float(v) for k, v in answer["figures"].items()}
    done.probed[name] = figures
    unit_stamp = {**stamp, "unit_id": str(unit["unit_id"])}
    after = status_busy(engine_of(unit), answer.get("after_page"))
    if after is None or after > 0:
        done.contended.append(name)
        for field_name, value in figures.items():
            alerts.record(
                journal,
                unit_stamp,
                {
                    "field": field_name,
                    "observed": value,
                    "contended": True,
                    "in_flight_after": after,
                    **stamps,
                },
            )
        return
    try:
        approved = _approved(
            fleet.folder,
            fleet.locked_rig_id(host),
            stamp["combination_id"],
            name,
            unit,
            class_tolerances(),
        )
    except (HarnessError, DerivedNumbersError) as exc:
        done.failed[name] = str(exc)
        return
    done.alerts.extend(
        alerts.check(
            [
                {"unit_id": unit_stamp["unit_id"], "field": f, "observed": v}
                for f, v in figures.items()
            ],
            approved=approved,
            profile=profile,
            journal_dir=journal,
            stamp=unit_stamp,
            run_id=stamps["run_id"],
            lease_id=stamps["lease_id"],
        )
    )


def observations(journal: Path, run_id: str) -> dict[str, dict[str, Any]]:
    """rig -> the rig row one read filed under ``journal``."""
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
    """The alerts one read filed, as :func:`mcgyvr.fleet.alerts.check` yields them."""
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


def spawn_read(host: str, run_id: str, probe: Sequence[str] = ()) -> int:
    """``python -m mcgyvr.serving.run read`` for ``host``, to completion.

    The door's own output goes to stderr: a command's stdout is its caller's.
    """
    from mcgyvr.serving.gatelib import DOOR_MODULE

    argv = [sys.executable, "-m", DOOR_MODULE, "read", "--host", host]
    argv += ["--run-id", run_id]
    if probe:
        argv += ["--probe", *probe]
    done = subprocess.run(
        argv, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False
    )
    for said in (done.stdout, done.stderr):
        if said:
            sys.stderr.write(said)
    return done.returncode
