"""A live unit is judged by a solo probe that repeats its lock's own measurement.

Owner, 2026-09-15 (F2): every dispatch row keeps its decode, prefill and
in-flight figures as data, and only a probe judges. A solo srv2_3b dispatch of
1206 tokens in and 503 out decoded 114.1 tok/s against a locked 126.7. The
lock measured a short prompt and 256 tokens out, so a dispatch is not the
lock's quantity, and the probe asks the lock's own question instead:

* a vLLM unit gets :data:`VLLM_HARNESS`: one 64-token warm-up, five 256-token
  decodes with ``ignore_eos`` (``completion_tokens`` over wall seconds) and
  three 16-token requests of the long prompt (``prompt_tokens`` over wall
  seconds, which that harness calls its TTFT);
* a llama.cpp unit gets :data:`LLAMA_HARNESS`: ``/completion`` with a 64-token
  warm-up, five 256-token decodes read from ``timings.predicted_per_second``
  and three 16-token long prompts read from ``timings.prompt_per_second``,
  with ``cache_prompt`` off.

Both take the median, as the lock's numbers were taken
(``fleet-setup/REPORT-srv1.md``, ``fleet-setup/REPORT-srv2.md``). Unlike the
harnesses, the probe does not run on the rig: it asks the unit at its address.

**A vLLM figure is recorded, not judged.** Owner, 2026-09-15: "vLLM stopwatch
on the rig; record till then". ``measure_vllm.py`` timed its requests on the
rig at 127.0.0.1. The probe times the same requests by wall clock from off the
rig, so each one carries a network round trip. The first live probe
(run-20260915T050342-42b9afd8) took about 0.12-0.15 s longer a request than
that harness's on-rig evidence (``srv2/b-small-3b.json``,
``srv2/b-small-7b.json``). That alone put srv2's decode 7.0% (3B) and 3.5% (7B)
under the lock, and pulled its combination. So a vLLM unit's decode and
prefill are filed with the probe's stamp and ``off_the_rig: true`` through
:func:`mcgyvr.fleet.alerts.record`, as a contended unit's are, and
:attr:`Report.off_the_rig` names them. They raise no alert and pull nothing. A
llama.cpp figure is the server's own ``timings``, which carry no network time,
and is judged.

**Only an idle unit is probed.** The unit's own in-flight count
(:func:`mcgyvr.runner.unit_in_flight`) is read before and after. A unit busy
before is not probed. A unit busy after — or whose count cannot be read after —
took work during the probe: its figures are filed as ``contended`` and not
judged.

**Card memory and restarts are read through the door.** Both are rig reads,
and a rig is reached only behind the door (``tests/test_one_door.py``). Given a
``reader`` — ``mcgyvr fleet probe`` passes :func:`mcgyvr.fleet.read.spawn_read`
(owner, 2026-09-15, F2b) — the probe reads each rig first with
``python -m mcgyvr.serving.run read``, which files and judges both by their
rules, card at most the unit's ``room_mib`` and restarts exactly 0. The same
read runs a vLLM unit's measurement on the rig (``read --probe``), where the
lock's stopwatch ran, and judges it there. A rig whose read filed nothing — or a
probe given no reader — names both figures as not read, and times its vLLM units
off the rig, recorded and not judged, as above.

Every figure is stamped with the live fleet, rig, rig id, combination id and
unit id, and filed under ``<journal.dir>/fleet/`` with ``at``, the moment its
unit's measurement finished. A judged figure is filed
through :func:`mcgyvr.fleet.alerts.check`, against the unit's plain locked
value and its class tolerance (:func:`mcgyvr.derived.class_tolerances`).
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mcgyvr.config import JOURNAL_DIR_DEFAULT
from mcgyvr.derived import DerivedNumbersError, class_tolerances
from mcgyvr.fleet import alerts
from mcgyvr.fleet.admit import layout_ids
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.harness import LLAMA_LONG_PROMPT as LLAMA_LONG_PROMPT
from mcgyvr.fleet.harness import LLAMA_SHORT_PROMPT as LLAMA_SHORT_PROMPT
from mcgyvr.fleet.harness import VLLM_LONG as VLLM_LONG
from mcgyvr.fleet.harness import VLLM_SHORT as VLLM_SHORT
from mcgyvr.fleet.harness import HarnessError as _UnitError
from mcgyvr.fleet.harness import HttpTransport as HttpTransport
from mcgyvr.fleet.harness import Transport as Transport
from mcgyvr.fleet.harness import measure_llamacpp as measure_llamacpp
from mcgyvr.fleet.harness import measure_vllm as measure_vllm
from mcgyvr.fleet.roots import (
    LIVE_FILE_SHOWN,
    LiveFleetError,
    live_fleet,
    live_fleet_dir,
)
from mcgyvr.fleet.tolerance import CLASS_VLLM, tolerance_class

#: Where the probe files, under the config's ``journal.dir``.
JOURNAL_SUBDIR = "fleet"

#: The two harnesses the lock's numbers were measured with. Their method is
#: :mod:`mcgyvr.fleet.harness`, which the probe asks of a unit at its address and
#: the door's ``read --probe`` runs on the rig.
VLLM_HARNESS = "records/measurements/fleet-setup-2026-09-13/srv2/measure_vllm.py"
LLAMA_HARNESS = "records/measurements/fleet-setup-2026-09-13/srv1/harness_llama.py"

#: The figures a probe cannot read from a unit's HTTP face.
NOT_READ_ON_THE_RIG: tuple[str, ...] = ("card_mib", "restarts")
NOT_READ_REASON = (
    "read on the rig, and a rig is reached only behind the door "
    "(python -m mcgyvr.serving.run; tests/test_one_door.py)"
)
#: Why a vLLM unit's figures are recorded and not judged (owner, 2026-09-15).
OFF_THE_RIG_REASON = (
    "timed by wall clock from off the rig, over the network at {address}, "
    "while the lock timed on the rig at 127.0.0.1 ({harness})"
)

InFlight = Callable[[str, Mapping[str, Any]], int | None]


class ProbeError(Exception):
    """The probe cannot run at all: no fleet is live, or its folder is unreadable."""


@dataclass
class Report:
    """What one probe did, unit by unit."""

    #: unit name -> the medians measured, by lock field.
    probed: dict[str, dict[str, float]] = field(default_factory=dict)
    #: unit name -> what it had in flight, for a unit not probed because busy.
    busy: dict[str, int] = field(default_factory=dict)
    #: units that took work during their probe: filed, not judged.
    contended: list[str] = field(default_factory=list)
    #: unit name -> why its probe could not run.
    failed: dict[str, str] = field(default_factory=dict)
    #: unit name -> (the figures not read, why).
    not_read: dict[str, tuple[tuple[str, ...], str]] = field(default_factory=dict)
    #: unit name -> (the figures filed, why): timed from off the rig, not judged.
    off_the_rig: dict[str, tuple[tuple[str, ...], str]] = field(default_factory=dict)
    #: the alerts the judge raised.
    alerts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """1 when any unit's probe could not run, else 0."""
        return 1 if self.failed else 0


def journal_dir(folder: Path | None) -> Path:
    """``<journal.dir>/fleet`` for a live fleet folder, where the probe files.

    ``journal.dir`` is read from the folder's ``policy.yaml``; with no folder, or
    none stated, it is the config's default.
    """
    configured: Any = None
    policy_path = None if folder is None else folder / "policy.yaml"
    if policy_path is not None and policy_path.is_file():
        try:
            policy = load_policy(policy_path.read_text(encoding="utf-8"))
        except (OSError, FleetFileError) as exc:
            raise ProbeError(f"{policy_path} cannot be read: {exc}") from exc
        block = policy.get("journal")
        if isinstance(block, Mapping):
            configured = block.get("dir")
    base = str(configured) if configured else JOURNAL_DIR_DEFAULT
    return Path(base).expanduser() / JOURNAL_SUBDIR


def unit_in_flight(name: str, unit: Mapping[str, Any]) -> int | None:
    """The unit's own in-flight count, from ``/slots`` or vLLM's ``/metrics``."""
    from mcgyvr.runner import unit_in_flight as read

    width = unit.get("width")
    engine = unit.get("engine")
    return read(
        name,
        str(unit["address"]),
        engine if isinstance(engine, str) else None,
        width if isinstance(width, int) and width > 0 else 1,
    )


def _approved(
    folder: Path,
    rig_id: str,
    combination: str,
    unit_name: str,
    unit: Mapping[str, Any],
    tolerances: Mapping[str, float],
) -> dict[str, dict[str, Any]]:
    """The judge's view of one unit: its locked values, class percent and room."""
    path = folder / "records" / "fleet" / "rigs" / rig_id / f"{combination}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        entry = record["approved"][unit_name]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise _UnitError(f"its lock record {path} cannot be read: {exc}") from exc
    values: dict[str, Any] = {
        name: entry[name]
        for name in ("warm_decode_tok_s", "prefill_tok_s")
        if name in entry
    }
    values["tolerance_pct"] = tolerances[tolerance_class(unit)]
    if unit.get("room_mib") is not None:
        values["room_mib"] = unit["room_mib"]
    return {str(unit["unit_id"]): values}


def _live(units: Sequence[str] | None) -> tuple[str, Path, dict[str, Any]]:
    try:
        name = live_fleet()
        folder = live_fleet_dir()
    except LiveFleetError as exc:
        raise ProbeError(str(exc)) from exc
    if name is None or folder is None:
        raise ProbeError(
            f"no fleet is live: {LIVE_FILE_SHOWN} names none (`mcgyvr fleet use`)"
        )
    try:
        fleet = load_fleet((folder / "fleet.yaml").read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise ProbeError(f"{folder / 'fleet.yaml'} cannot be read: {exc}") from exc
    if name not in fleet.get("fleets", {}):
        raise ProbeError(f"{folder / 'fleet.yaml'} holds no fleet {name!r}")
    return name, folder, fleet


#: A read of one rig through the door: ``(rig, run id, units to probe) -> exit``.
Reader = Callable[[str, str, Sequence[str]], int]
#: Why a rig's figures are not read when its read through the door filed none.
UNREAD_RIG_REASON = "the door's read of {rig} exited {code} and filed no reading"
#: Why a figure the door's reader could not read is not read.
UNREAD_BY_THE_READER = "the door's reader on the rig could not read them"


def _read_rigs(
    reader: Reader | None,
    fleet: Mapping[str, Any],
    awake: Sequence[tuple[str, str]],
    run_id: str,
    journal: Path,
    report: Report,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Each rig's read through the door, filed under ``run_id``, and why not."""
    filed: dict[str, dict[str, Any]] = {}
    unread: dict[str, str] = {}
    if reader is None:
        return filed, unread
    from mcgyvr.fleet import read

    for rig in sorted({rig for rig, _ in awake}):
        on_the_rig = [
            unit
            for where, unit in awake
            if where == rig and tolerance_class(fleet["units"][unit]) == CLASS_VLLM
        ]
        code = reader(rig, run_id, on_the_rig)
        row = read.observations(journal, run_id).get(rig) if code == 0 else None
        if row is None:
            unread[rig] = UNREAD_RIG_REASON.format(rig=rig, code=code)
        else:
            filed[rig] = row
    report.alerts.extend(read.judged(journal, run_id))
    return filed, unread


def _from_the_rig(report: Report, unit: str, row: Mapping[str, Any]) -> None:
    """What ``read --probe`` measured of ``unit`` on the rig, into the report."""
    probed = (row.get("probed") or {}).get(unit)
    if isinstance(probed, Mapping):
        report.probed[unit] = {str(k): float(v) for k, v in probed.items()}
    busy = (row.get("busy") or {}).get(unit)
    if isinstance(busy, int):
        report.busy[unit] = busy
    if unit in (row.get("contended") or []):
        report.contended.append(unit)
    failed = (row.get("failed") or {}).get(unit)
    if failed:
        report.failed[unit] = str(failed)


def run(
    *,
    transport: Transport | None = None,
    in_flight: InFlight | None = None,
    clock: Callable[[], float] = time.perf_counter,
    units: Sequence[str] | None = None,
    now: datetime | None = None,
    reader: Reader | None = None,
) -> Report:
    """Probe the live fleet's awake units, file every figure, judge the solo ones.

    Raises :class:`ProbeError` when nothing can be probed at all (no live
    fleet, an unreadable folder, a unit named that is not awake in it); a unit
    whose own probe cannot run is in :attr:`Report.failed`. With ``reader``,
    every rig is read through the door first (module docstring).
    """
    name, folder, fleet = _live(units)
    transport = transport if transport is not None else HttpTransport()
    in_flight = in_flight if in_flight is not None else unit_in_flight
    try:
        tolerances = class_tolerances()
    except DerivedNumbersError as exc:
        raise ProbeError(str(exc)) from exc

    layout = fleet["fleets"][name].get("layout", {})
    rig_ids = {rig: block["rig_id"] for rig, block in fleet.get("rigs", {}).items()}
    combinations = layout_ids(fleet, layout)
    awake = [
        (rig, slot[0])
        for rig, slots in layout.items()
        for slot in slots
        if slot is not None and slot[1] == "awake"
    ]
    if units:
        unknown = sorted(set(units) - {unit for _, unit in awake})
        if unknown:
            raise ProbeError(f"not an awake unit of {name}: {', '.join(unknown)}")
        awake = [(rig, unit) for rig, unit in awake if unit in units]

    moment = now if now is not None else datetime.now(UTC)
    started = clock()
    token = secrets.token_hex(4)
    run_id = f"run-{moment:%Y%m%dT%H%M%S}-{token}"
    lease_id = f"probe-{token}"
    journal = journal_dir(folder)
    profile = str(fleet.get("profile", "live"))
    report = Report()
    filed, unread = _read_rigs(reader, fleet, awake, run_id, journal, report)

    for rig, unit_name in awake:
        unit = fleet["units"][unit_name]
        row = filed.get(rig)
        if row is None:
            reason = unread.get(rig, NOT_READ_REASON)
            report.not_read[unit_name] = (NOT_READ_ON_THE_RIG, reason)
        else:
            missing = tuple((row.get("not_read") or {}).get(unit_name) or ())
            if missing:
                report.not_read[unit_name] = (missing, UNREAD_BY_THE_READER)
            if tolerance_class(unit) == CLASS_VLLM:
                _from_the_rig(report, unit_name, row)
                continue
        before = in_flight(unit_name, unit)
        if before is None:
            report.failed[unit_name] = (
                "its in-flight count could not be read (/slots or /metrics)"
            )
            continue
        if before > 0:
            report.busy[unit_name] = before
            continue
        rig_id = rig_ids[rig]
        combination = combinations[rig_id]
        address = str(unit["address"])
        # measure_vllm's wall clock runs here, off the rig; llama.cpp's
        # timings are the server's own.
        timed_off_the_rig = tolerance_class(unit) == CLASS_VLLM
        try:
            approved = _approved(
                folder, rig_id, combination, unit_name, unit, tolerances
            )
            if timed_off_the_rig:
                figures = measure_vllm(address, transport, clock)
            else:
                figures = measure_llamacpp(address, transport)
        except (_UnitError, OSError, ValueError) as exc:
            report.failed[unit_name] = str(exc)
            continue
        # Each unit's rows carry the moment its own measurement finished, not
        # the run's start: a pull clears against the newest alert's time.
        finished = moment + timedelta(seconds=clock() - started)
        at = f"{finished:%Y-%m-%dT%H:%M:%S}"
        report.probed[unit_name] = figures
        after = in_flight(unit_name, unit)
        stamp = {
            "fleet": name,
            "rig": rig,
            "rig_id": rig_id,
            "combination_id": combination,
            "unit_id": str(unit["unit_id"]),
        }
        not_judged: dict[str, Any] = {}
        if after is None or after > 0:
            report.contended.append(unit_name)
            not_judged |= {"contended": True, "in_flight_after": after}
        if timed_off_the_rig:
            report.off_the_rig[unit_name] = (
                tuple(figures),
                OFF_THE_RIG_REASON.format(address=address, harness=VLLM_HARNESS),
            )
            not_judged["off_the_rig"] = True
        if not_judged:
            for field_name, value in figures.items():
                alerts.record(
                    journal,
                    stamp,
                    {
                        "field": field_name,
                        "observed": value,
                        "run_id": run_id,
                        "lease_id": lease_id,
                        "at": at,
                        **not_judged,
                    },
                )
            continue
        observations = [
            {
                "unit_id": stamp["unit_id"],
                "unit": unit_name,
                "field": field_name,
                "observed": value,
                "at": at,
            }
            for field_name, value in figures.items()
        ]
        report.alerts.extend(
            alerts.check(
                observations,
                approved=approved,
                profile=profile,
                journal_dir=journal,
                stamp=stamp,
                run_id=run_id,
                lease_id=lease_id,
            )
        )
    return report
