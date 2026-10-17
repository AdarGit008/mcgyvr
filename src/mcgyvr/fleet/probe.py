""

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
from mcgyvr.fleet.linkread import LinkEnds, worker_address
from mcgyvr.fleet.roots import (
    LOCK_DIR,
    LiveFleetError,
    layout_of,
    live_file,
    live_fleet,
    live_fleet_dir,
)
from mcgyvr.fleet.spans import Span, SpanError, spans
from mcgyvr.fleet.tolerance import CLASS_VLLM, tolerance_class

#
JOURNAL_SUBDIR = "fleet"

#
#
#
VLLM_HARNESS = "the lock's vLLM harness"
LLAMA_HARNESS = "the lock's llama.cpp harness"

#
NOT_READ_ON_THE_RIG: tuple[str, ...] = ("card_mib", "restarts")
NOT_READ_REASON = (
    "read on the rig, and a rig is reached only behind the door "
    "(python -m mcgyvr.serving.run; tests/test_one_door.py)"
)
#
OFF_THE_RIG_REASON = (
    "timed by wall clock from off the rig, over the network at {address}, "
    "while the lock timed on the rig at 127.0.0.1 ({harness})"
)

InFlight = Callable[[str, Mapping[str, Any]], int | None]


class ProbeError(Exception):
    ""


@dataclass
class Report:
    ""

    #
    probed: dict[str, dict[str, float]] = field(default_factory=dict)
    #
    busy: dict[str, int] = field(default_factory=dict)
    #
    contended: list[str] = field(default_factory=list)
    #
    failed: dict[str, str] = field(default_factory=dict)
    #
    not_read: dict[str, tuple[tuple[str, ...], str]] = field(default_factory=dict)
    #
    off_the_rig: dict[str, tuple[tuple[str, ...], str]] = field(default_factory=dict)
    #
    alerts: list[dict[str, Any]] = field(default_factory=list)
    #
    #
    links: dict[str, str] = field(default_factory=dict)
    #
    links_failed: dict[str, str] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        ""
        return 1 if self.failed or self.links_failed else 0


def folder_policy(folder: Path | None) -> dict[str, Any]:
    ""
    policy_path = None if folder is None else folder / "policy.yaml"
    if policy_path is None or not policy_path.is_file():
        return {}
    try:
        return load_policy(policy_path.read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise ProbeError(f"{policy_path} cannot be read: {exc}") from exc


def journal_dir(folder: Path | None) -> Path:
    ""
    configured: Any = None
    block = folder_policy(folder).get("journal")
    if isinstance(block, Mapping):
        configured = block.get("dir")
    base = str(configured) if configured else JOURNAL_DIR_DEFAULT
    return Path(base).expanduser() / JOURNAL_SUBDIR


def unit_in_flight(name: str, unit: Mapping[str, Any]) -> int | None:
    ""
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
    tolerances: Mapping[str, Mapping[str, float]],
) -> dict[str, dict[str, Any]]:
    ""
    path = folder / LOCK_DIR / "rigs" / rig_id / f"{combination}.json"
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
    in_class = tolerance_class(unit)
    values["tolerance_pct"] = {
        name: by_class[in_class] for name, by_class in tolerances.items()
    }
    if unit.get("room_mib") is not None:
        values["room_mib"] = unit["room_mib"]
    return {str(unit["unit_id"]): values}


def _live(units: Sequence[str] | None) -> tuple[str, Path, dict[str, Any]]:
    ""
    try:
        name = live_fleet()
        folder = live_fleet_dir()
    except LiveFleetError as exc:
        raise ProbeError(str(exc)) from exc
    if name is None or folder is None:
        raise ProbeError(
            f"no fleet is live: {live_file()} names none (`mcgyvr fleet use`)"
        )
    try:
        fleet = load_fleet((folder / "fleet.yaml").read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise ProbeError(f"{folder / 'fleet.yaml'} cannot be read: {exc}") from exc
    layout = layout_of(name)
    if layout not in fleet.get("fleets", {}):
        raise ProbeError(
            f"{folder / 'fleet.yaml'} holds no fleet {layout!r} "
            f"({live_file()} names {name!r})"
        )
    return layout, folder, fleet


#
#
#
LinkReader = Callable[[LinkEnds], Sequence[tuple[int, float]]]
#
LINK_HOW = "mcgyvr fleet probe"
#
Reader = Callable[[str, str, Sequence[str]], int]
#
UNREAD_RIG_REASON = "the door's read of {rig} exited {code} and filed no reading"
#
UNREAD_BY_THE_READER = "the door's reader on the rig could not read them"


def _read_rigs(
    reader: Reader | None,
    fleet: Mapping[str, Any],
    awake: Sequence[tuple[str, str]],
    measured: Sequence[tuple[str, str]],
    run_id: str,
    journal: Path,
    report: Report,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    ""
    filed: dict[str, dict[str, Any]] = {}
    unread: dict[str, str] = {}
    if reader is None:
        return filed, unread
    from mcgyvr.fleet import read

    for rig in sorted({rig for rig, _ in awake}):
        on_the_rig = [
            unit
            for where, unit in measured
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
    ""
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


def link_ends(
    spanning: Mapping[str, Span], measured: Sequence[tuple[str, str]]
) -> list[LinkEnds]:
    ""
    found: dict[str, list[LinkEnds]] = {}
    for unit in sorted({unit for _, unit in measured if unit in spanning}):
        span = spanning[unit]
        cards = span.cards
        for rig in sorted(cards):
            gpus = cards[rig]
            if len(gpus) >= 2:
                ends = LinkEnds(rig, gpus[0], rig, gpus[1])
                found.setdefault(ends.link_class, []).append(ends)
        for worker in span.workers:
            shard = span.shards_on(worker)[0]
            ends = LinkEnds(
                span.head,
                cards[span.head][0],
                worker,
                shard.gpu,
                worker_address(worker, shard.bind),
            )
            found.setdefault(ends.link_class, []).append(ends)
    return [
        sorted(candidates, key=lambda ends: ends.key)[0]
        for _, candidates in sorted(found.items())
    ]


def _read_links(
    link_reader: LinkReader,
    spanning: Mapping[str, Span],
    measured: Sequence[tuple[str, str]],
    moment: datetime,
    report: Report,
) -> None:
    ""
    from mcgyvr.serving import interconnect

    refused = (ValueError, OSError, interconnect.InterconnectError)
    for ends in link_ends(spanning, measured):

        def timed(
            _a: str, _b: str, ends: LinkEnds = ends
        ) -> Sequence[tuple[int, float]]:
            return link_reader(ends)

        try:
            link = interconnect.read_link(
                ends.host_a,
                ends.host_b,
                timed,
                how=LINK_HOW,
                at=f"{moment:%Y-%m-%dT%H:%M:%S}",
            )
        except refused as exc:
            report.links_failed[ends.key] = str(exc)
            continue
        report.links[ends.key] = str(link.says())


def run(
    *,
    transport: Transport | None = None,
    in_flight: InFlight | None = None,
    clock: Callable[[], float] = time.perf_counter,
    units: Sequence[str] | None = None,
    now: datetime | None = None,
    reader: Reader | None = None,
    link_reader: LinkReader | None = None,
) -> Report:
    ""
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
    try:
        spanning = spans(fleet)
    except SpanError as exc:
        raise ProbeError(str(exc)) from exc
    #
    measured = [
        (rig, unit)
        for rig, unit in awake
        if unit not in spanning or spanning[unit].head == rig
    ]

    moment = now if now is not None else datetime.now(UTC)
    started = clock()
    token = secrets.token_hex(4)
    run_id = f"run-{moment:%Y%m%dT%H%M%S}-{token}"
    lease_id = f"probe-{token}"
    journal = journal_dir(folder)
    report = Report()
    filed, unread = _read_rigs(reader, fleet, awake, measured, run_id, journal, report)

    for rig, unit_name in measured:
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
        #
        #
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
        #
        #
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
                journal_dir=journal,
                stamp=stamp,
                run_id=run_id,
                lease_id=lease_id,
            )
        )
    if link_reader is not None:
        _read_links(link_reader, spanning, measured, moment, report)
    return report
