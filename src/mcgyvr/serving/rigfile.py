"""The rig as its user described it: the one record of a machine.

Owner, 2026-10-07 (Round 5): a door run from an install has no lab checkout,
so there is no lab ``hosts.json`` declaring the rig. What it has instead is
the rig file ``<rig-file folder>/<rig>.json`` (:func:`path`): one reading of
the rig by the one reader (:mod:`mcgyvr.serving.rigscan`), kept whole. It is
the only record of a machine mcgyvr keeps (owner, 2026-10-14: one record per
machine): ``mcgyvr scan`` writes this machine's as ``localhost``, ``mcgyvr
scan --rig`` a remote rig's over the read-only ssh line, and ``mcgyvr setup``
each rig it serves on; ``emit`` sizes from them. The rig-file folder is
``$MCGYVR_RIGS`` when the user named one, else the config folder's ``rigs``.

What a door run holds a rig to is read off that reading (:class:`Rig`): its
hostname, machine id and rig id (:func:`mcgyvr.fleet.ids.rig_id`), its cards
and their memory, its RAM, cores and bandwidth, its free disk, its docker
version, the snapshot's facts of the machine (:data:`RECORDED`: the CPU's
model, clock and power limits, the DDR speed, the first card's slot and
compute capability, the cards beyond it, the driver and the kernel), and its
private IPv4 address (:func:`private_ipv4`, owner Round 9: the address an RPC
worker of a unit spanning machines listens on, as the rig reported it;
nothing is resolved).

Each user-mode door run reads the rig again with the same reader and holds the
reading to the file (:func:`door_check`): it says what moved (:func:`moved`),
and it refuses only when the fleet no longer fits -- a card the fleet's
compose file reserves is gone, or holds less memory than the file records.
Anything else that moved (RAM, docker, the driver, the kernel, the hostname, a
card the fleet does not use) is said and admitted: a driver upgrade is a
machine that changed, which the gate says, not another machine. The file is
the user's record and the door never rewrites it: a rig that changed for good
is scanned again.
"""

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

#: What a rig name may be: a plain file name, as an ssh alias is.
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
#: The command that writes a rig file, as a refusal names it.
MAKE = "mcgyvr scan --rig {rig}"
#: The rig name this machine's own record is kept under.
LOCAL = "localhost"
#: The snapshot keys a rig file holds the rig to: the facts of the machine that
#: are not in its rig id and do not move run to run. Volatile readings (the
#: boot time, free memory, the reserve the firmware takes per boot) are left
#: out, as is what :class:`Rig` reads elsewhere (the card's name and size, and
#: docker).
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
#: The facts a change in which is the hardware changing under the machine —
#: what ``mcgyvr scan`` exits 4 for. A bandwidth reading repeats to within 9%
#: of itself run to run (:mod:`mcgyvr.serving.rigscan`), so it has moved only
#: past :data:`BANDWIDTH_TOLERANCE`: memory that lost a channel roughly halves.
HARDWARE = ("ram_total_gb", "cpu_cores", "cpu_threads", "bandwidth_gbps")
BANDWIDTH_TOLERANCE = 0.15


class RigFileError(Exception):
    """A rig name that cannot name a file, or a rig file that cannot be read."""


@dataclass(frozen=True)
class Card:
    """One card of the rig, by the facts that do not move between two scans."""

    index: int
    name: str
    total_mib: int

    def said(self) -> str:
        return f"{self.name}, {self.total_mib} MiB"


@dataclass(frozen=True)
class Rig:
    """One rig file: one reading of the rig, and when it was taken.

    Every fact is read off :attr:`reading` (the one reader's document), so the
    file holds each fact once.
    """

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
        """The rig id the reading names, or ``None`` when it names none."""
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
        """The :data:`RECORDED` snapshot keys the reading read."""
        said = self.reading.get("snapshot")
        said = said if isinstance(said, Mapping) else {}
        return {key: str(said[key]) for key in RECORDED if key in said}

    @property
    def private_ipv4(self) -> str | None:
        """The private IPv4 address a worker on this rig listens on, or None."""
        return private_ipv4(self.scan.network)[0]

    @property
    def private_ipv4_how(self) -> str:
        """How :attr:`private_ipv4` was picked, or why none was."""
        return private_ipv4(self.scan.network)[1]

    def to_json(self) -> str:
        payload = {"rig": self.rig, "read_at": self.read_at, "reading": self.reading}
        return json.dumps(payload, indent=2) + "\n"


def from_json(text: str) -> Rig:
    """A rig file read back, or :class:`RigFileError` naming what is wrong."""
    try:
        raw = json.loads(text)
        rig = Rig(
            rig=str(raw["rig"]),
            read_at=str(raw["read_at"]),
            reading=dict(raw["reading"]),
        )
        rig.scan  # noqa: B018 -- a reading Scan does not take is no rig file
        return rig
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RigFileError(f"not a rig file ({type(exc).__name__}: {exc})") from None


def _listenable(stated: object) -> ipaddress.IPv4Address | None:
    """``stated`` as an IPv4 address a worker may listen on, else None.

    An IPv4 address spelled as IPv6 (behind the ``::ffff:`` prefix, as a dual-stack sshd
    reports one) is that IPv4 address. Nothing here resolves a name: a name
    is not an address.
    """
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
    """The rig's private IPv4 address, as the rig reported it, and how it was
    picked -- or None, and why none was.

    The address the controller reached the rig at over ssh, when a worker may
    listen there (:func:`mcgyvr.serving.shardlaunch.worker_may_listen`): it is
    on the interface the controller reaches the rig by. Reached some other
    way (a tunnel to loopback, IPv6, an address on the internet), the one
    private address on its interfaces; with several, none is guessed.
    """
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
    """The rig file of ``rig`` from one reading of it (:mod:`~.rigscan`)."""
    now = Rig(
        rig=rig,
        read_at=read_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        reading=dict(reading),
    )
    try:
        now.scan  # noqa: B018 -- a reading Scan does not take is refused here
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RigFileError(f"{rig}: the reading is not one this takes ({exc})") from exc
    return now


def path(rig: str) -> Path:
    """The rig file for ``rig``: ``<rig-file folder>/<rig>.json``, or refused.

    The rig-file folder is ``$MCGYVR_RIGS`` (default ``$MCGYVR_HOME/rigs``).
    A rig name is a plain file name: a slash, a leading dot or an empty name
    would put the file somewhere else than the folder of rig files. A value
    of ``$MCGYVR_RIGS`` that names no usable folder is refused the same way.
    """
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
    """Write ``rig``'s file whole, replacing the one before. Returns its path."""
    target = path(rig.rig)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.{os.getpid()}.part")
    partial.write_text(rig.to_json(), encoding="utf-8")
    partial.replace(target)
    return target


@dataclass(frozen=True)
class Saved:
    """What :func:`save` did: the rig file now, the one before, and where."""

    now: Rig
    before: Rig | None
    path: Path
    #: Whether the file before was kept: it knew its cards and this reading
    #: did not.
    kept: bool


def save(rig: str, reading: Mapping[str, Any]) -> Saved:
    """Record ``reading`` as ``rig``'s rig file, replacing the one before.

    Unless the one before knew its cards and this reading does not: a card
    list nvidia-smi could not give is no reading of the cards, and replacing
    a record that had one would make the next healthy read report every card
    as new — and a door run refuse a card the fleet uses as gone.
    """
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
    """``rig``'s file, or None when there is none. Unreadable is an error."""
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
    """One fact of the rig that reads differently from its rig file."""

    field: str
    was: object
    now: object

    def said(self) -> str:
        return f"{self.field} {self.was} -> {self.now}"


def moved(saved: Rig, now: Rig) -> tuple[Moved, ...]:
    """Every fact the door holds a run to that reads differently now.

    Free disk is not among them: it moves with every download, and a
    difference in it says nothing about the machine. Bandwidth has moved only
    past :data:`BANDWIDTH_TOLERANCE`. Cards are compared only when both
    readings determined them: an unanswered card tool is not a pulled card. A
    snapshot fact the record read and the rig no longer does is said as
    ``unread``; one the record never read is not held.
    """
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
    # The record says what the rig is held to: a fact it never read is no
    # fact that moved, and a fact it read that now is not is said as unread.
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
    """Whether ``change`` is the hardware changing under the machine: a card,
    RAM, cores or bandwidth (:data:`HARDWARE`)."""
    return change.field in HARDWARE or change.field.startswith("card ")


def misfits(saved: Rig, now: Rig, used: Iterable[int] | None) -> tuple[str, ...]:
    """Why the fleet no longer fits the rig, one line per card; empty when it does.

    ``used`` names the cards the fleet reserves, or None when it cannot be
    told, in which case every card of the rig file is held. A card the fleet
    uses no longer fits when it is not on the rig, or holds less memory than
    the rig file records for it.
    """
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
    """The cards a compose file's units reserve, or None when it cannot be told.

    A reservation by a card id that is not an index (a UUID) is not matched
    to a card of the rig file, so every card of the file is held then.
    """
    from mcgyvr.serving import servelib

    indexes: set[int] = set()
    for service in servelib.services(compose):
        for device in service.devices:
            if not device.isascii() or not device.isdigit():
                return None
            indexes.add(int(device))
    return tuple(sorted(indexes))


def required(host: str, what: str) -> Rig:
    """``host``'s rig file under the door, or the gate refuses naming how to make one.

    Asked before anything reaches the rig, so a run with no rig file leaves
    nothing behind.
    """
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
    """Hold ``now``, the door's one reading of ``host``, to its rig file: say what
    moved, refuse a fleet that no longer fits. Returns ``now``.

    The reading is the gate's own, taken through
    :func:`mcgyvr.serving.gatelib.ssh` (so only a process the door started
    reaches the rig, and only the rig the door was opened for); this reads
    nothing itself.
    """
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
