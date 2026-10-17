""

from __future__ import annotations

import ipaddress
import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Any

from mcgyvr.fleet.roots import FolderError, rigs_dir
from mcgyvr.scan import ModelOnDisk, Network, Scan

#
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
#
MAKE = "mcgyvr scan --rig {rig}"
#
LOCAL = "localhost"
#
#
#
#
#
RECORDED = (
    "cpu_model",
    "cpu_max_mhz",
    "ram_mt_s",
    "pl1_uw",
    "pl2_uw",
    "gpu_cc",
    "gpu_slot",
    "gpu_others",
    "driver",
    "kernel",
)
#€”
#
#
#
HARDWARE = ("ram_total_gb", "cpu_cores", "cpu_threads", "bandwidth_gbps")
BANDWIDTH_TOLERANCE = 0.15


class RigFileError(Exception):
    ""


@dataclass(frozen=True)
class Card:
    ""

    index: int
    name: str
    total_mib: int

    def said(self) -> str:
        return f"{self.name}, {self.total_mib} MiB"


@dataclass(frozen=True)
class Rig:
    ""

    rig: str
    read_at: str
    reading: Mapping[str, Any]

    @cached_property
    def scan(self) -> Scan:
        return Scan.from_json(json.dumps(self.reading))

    @property
    def hostname(self) -> str:
        return self.scan.machine.host

    @property
    def machine_id(self) -> str:
        return self.scan.machine.id

    @property
    def rig_id(self) -> str | None:
        ""
        from mcgyvr.fleet import ids

        try:
            return ids.rig_id(self.reading)
        except ValueError:
            return None

    @property
    def cards(self) -> tuple[Card, ...]:
        return tuple(
            Card(index=gpu.index, name=gpu.name, total_mib=gpu.vram.total_mib)
            for gpu in self.scan.gpus
        )

    @property
    def ram_total_gb(self) -> float | None:
        return None if self.scan.memory is None else self.scan.memory.total_gb

    @property
    def cpu_cores(self) -> int | None:
        return None if self.scan.cpu is None else self.scan.cpu.cores

    @property
    def cpu_threads(self) -> int | None:
        return None if self.scan.cpu is None else self.scan.cpu.threads

    @property
    def bandwidth_gbps(self) -> float | None:
        bandwidth = self.scan.bandwidth
        return None if bandwidth is None else bandwidth.measured_gbps

    @property
    def bandwidth_how(self) -> str:
        return "" if self.scan.bandwidth is None else self.scan.bandwidth.how

    @property
    def disk_path(self) -> str | None:
        return None if self.scan.disk is None else str(self.scan.disk.path)

    @property
    def disk_free_gb(self) -> float | None:
        return None if self.scan.disk is None else self.scan.disk.free_gb

    @property
    def disk_total_gb(self) -> float | None:
        return None if self.scan.disk is None else self.scan.disk.total_gb

    @property
    def disk_device(self) -> str | None:
        return None if self.scan.disk is None else self.scan.disk.device

    @property
    def models_on_disk(self) -> tuple[ModelOnDisk, ...]:
        return self.scan.models_on_disk

    @property
    def docker(self) -> str | None:
        return self.scan.docker

    @property
    def notes(self) -> tuple[str, ...]:
        return self.scan.notes

    @property
    def snapshot(self) -> dict[str, str]:
        ""
        said = self.reading.get("snapshot")
        said = said if isinstance(said, Mapping) else {}
        return {key: str(said[key]) for key in RECORDED if key in said}

    @property
    def private_ipv4(self) -> str | None:
        ""
        return private_ipv4(self.scan.network)[0]

    @property
    def private_ipv4_how(self) -> str:
        ""
        return private_ipv4(self.scan.network)[1]

    def to_json(self) -> str:
        payload = {"rig": self.rig, "read_at": self.read_at, "reading": self.reading}
        return json.dumps(payload, indent=2) + "\n"


def from_json(text: str) -> Rig:
    ""
    try:
        raw = json.loads(text)
        rig = Rig(
            rig=str(raw["rig"]),
            read_at=str(raw["read_at"]),
            reading=dict(raw["reading"]),
        )
        rig.scan  #
        return rig
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RigFileError(f"not a rig file ({type(exc).__name__}: {exc})") from None


def _listenable(stated: object) -> ipaddress.IPv4Address | None:
    ""
    from mcgyvr.serving.shardlaunch import worker_may_listen

    if not isinstance(stated, str):
        return None
    try:
        address = ipaddress.ip_address(stated)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is None:
            return None
        address = address.ipv4_mapped
    return address if worker_may_listen(address) else None


def private_ipv4(network: Network | None) -> tuple[str | None, str]:
    ""
    if network is None:
        return None, "the scan read no network (a scan from before addresses)"
    reached = _listenable(network.reached_at)
    if reached is not None:
        return str(reached), "the address the rig was reached at over ssh"
    if network.reached_at is None:
        why = "it was not reached over ssh"
    else:
        why = f"it was reached at {network.reached_at}, not a private IPv4 address"
    found: dict[str, list[str]] = {}
    for one in network.ipv4:
        listens = _listenable(one.address)
        if listens is not None:
            found.setdefault(str(listens), []).append(one.interface)
    if len(found) == 1:
        ((only, names),) = found.items()
        return (
            only,
            f"the one private IPv4 on its interfaces ({', '.join(names)}); {why}",
        )
    if not found:
        return None, f"{why}, and no private IPv4 is on its interfaces"
    said = ", ".join(
        f"{address} ({', '.join(names)})" for address, names in found.items()
    )
    return None, (
        f"{why}, and it holds several private IPv4 addresses ({said}); none is "
        "guessed. Reach it over ssh at the one its other machines use (its ssh "
        "HostName) and scan it again"
    )


def from_reading(
    rig: str, reading: Mapping[str, Any], read_at: str | None = None
) -> Rig:
    ""
    now = Rig(
        rig=rig,
        read_at=read_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        reading=dict(reading),
    )
    try:
        now.scan  #
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RigFileError(f"{rig}: the reading is not one this takes ({exc})") from exc
    return now


def path(rig: str) -> Path:
    ""
    if NAME.fullmatch(rig) is None:
        raise RigFileError(
            f"rig name {rig!r} is not a plain name (letters, digits, '.', '_' and "
            "'-', not starting with '.'); a rig is named as your ssh names it"
        )
    try:
        folder = rigs_dir()
    except FolderError as exc:
        raise RigFileError(str(exc)) from exc
    return folder / f"{rig}.json"


def write(rig: Rig) -> Path:
    ""
    target = path(rig.rig)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.{os.getpid()}.part")
    partial.write_text(rig.to_json(), encoding="utf-8")
    partial.replace(target)
    return target


@dataclass(frozen=True)
class Saved:
    ""

    now: Rig
    before: Rig | None
    path: Path
    #
    #
    kept: bool


def save(rig: str, reading: Mapping[str, Any]) -> Saved:
    ""
    now = from_reading(rig, reading)
    try:
        before = read(rig)
    except RigFileError:
        before = None
    target = path(rig)
    known = before is not None and before.scan.gpus_determined
    if known and not now.scan.gpus_determined:
        return Saved(now=now, before=before, path=target, kept=True)
    return Saved(now=now, before=before, path=write(now), kept=False)


def read(rig: str) -> Rig | None:
    ""
    where = path(rig)
    try:
        text = where.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RigFileError(f"{where} cannot be read: {exc}") from exc
    try:
        return from_json(text)
    except RigFileError as exc:
        raise RigFileError(f"{where}: {exc}") from None


@dataclass(frozen=True)
class Moved:
    ""

    field: str
    was: object
    now: object

    def said(self) -> str:
        return f"{self.field} {self.was} -> {self.now}"


def moved(saved: Rig, now: Rig) -> tuple[Moved, ...]:
    ""
    found = [
        Moved(field, getattr(saved, field), getattr(now, field))
        for field in (
            "hostname",
            "machine_id",
            "ram_total_gb",
            "cpu_cores",
            "cpu_threads",
            "docker",
            "private_ipv4",
        )
        if getattr(saved, field) != getattr(now, field)
    ]
    was_gbps, now_gbps = saved.bandwidth_gbps, now.bandwidth_gbps
    if (
        was_gbps is not None
        and now_gbps is not None
        and was_gbps > 0
        and abs(now_gbps - was_gbps) > BANDWIDTH_TOLERANCE * was_gbps
    ):
        found.append(Moved("bandwidth_gbps", was_gbps, now_gbps))
    #
    #
    for key in RECORDED:
        was, is_now = saved.snapshot.get(key), now.snapshot.get(key)
        if was is not None and was != is_now:
            found.append(Moved(key, was, is_now or "unread"))
    if not (saved.scan.gpus_determined and now.scan.gpus_determined):
        return tuple(found)
    before = {card.index: card for card in saved.cards}
    after = {card.index: card for card in now.cards}
    for index in sorted(before.keys() | after.keys()):
        was_card, now_card = before.get(index), after.get(index)
        if was_card != now_card:
            found.append(
                Moved(
                    f"card {index}",
                    "absent" if was_card is None else was_card.said(),
                    "absent" if now_card is None else now_card.said(),
                )
            )
    return tuple(found)


def is_hardware(change: Moved) -> bool:
    ""
    return change.field in HARDWARE or change.field.startswith("card ")


def misfits(saved: Rig, now: Rig, used: Iterable[int] | None) -> tuple[str, ...]:
    ""
    before = {card.index: card for card in saved.cards}
    after = {card.index: card for card in now.cards}
    held = sorted(set(used)) if used is not None else sorted(before)
    found: list[str] = []
    for index in held:
        was, is_now = before.get(index), after.get(index)
        if is_now is None:
            recorded = f" ({was.said()} in the rig file)" if was is not None else ""
            found.append(f"card {index}{recorded}, which the fleet uses, is not there")
        elif was is not None and is_now.total_mib < was.total_mib:
            found.append(
                f"card {index} holds {is_now.total_mib} MiB, less than the "
                f"{was.total_mib} MiB the rig file records"
            )
    return tuple(found)


def cards_used(compose: Path) -> tuple[int, ...] | None:
    ""
    from mcgyvr.serving import servelib

    indexes: set[int] = set()
    for service in servelib.services(compose):
        for device in service.devices:
            if not device.isascii() or not device.isdigit():
                return None
            indexes.add(int(device))
    return tuple(sorted(indexes))


def required(host: str, what: str) -> Rig:
    ""
    from mcgyvr.serving import gatelib

    try:
        saved = read(host)
        where = path(host)
    except RigFileError as exc:
        gatelib.refuse(f"{what}: {exc}. Nothing is started on a rig nobody described")
    if saved is None:
        gatelib.refuse(
            f"{what}: there is no rig file for {host} ({where}). A door run from an "
            "install holds the rig to the rig as you described it: write it with "
            f"`{MAKE.format(rig=host)}` (a read-only ssh scan of the rig), then run "
            "again"
        )
    return saved


def door_check(
    host: str, saved: Rig, now: Rig, used: Iterable[int] | None, what: str
) -> Rig:
    ""
    from mcgyvr.serving import gatelib

    changes = moved(saved, now)
    for change in changes:
        print(f"{what}: moved since the rig file of {saved.read_at}: {change.said()}")
    if not changes:
        print(f"{what}: {host} reads as its rig file ({path(host)})")
    reasons = misfits(saved, now, used)
    if reasons:
        gatelib.refuse(
            f"{what}: the fleet no longer fits {host}: {'; '.join(reasons)}. "
            "Nothing is started on it. If the rig changed for good, "
            f"`{MAKE.format(rig=host)}` records it as it is now, and the fleet is "
            "planned again for it"
        )
    return now
