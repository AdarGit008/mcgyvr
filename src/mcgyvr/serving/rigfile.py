"""The rig as its user described it: what the door's user mode holds a run to.

Owner, 2026-10-07 (Round 5): a door run from an install has no lab checkout,
so there is no lab ``hosts.json`` declaring the rig. What it has
instead is the rig file ``<rig-file folder>/<rig>.json`` (:func:`path`): the
rig's read-only ssh scan (:mod:`mcgyvr.serving.rigscan`, the one scanner),
saved by ``mcgyvr scan --rig`` -- its hostname, its cards and their memory,
its RAM, its free disk, its docker version, and its private IPv4 address
(:func:`private_ipv4`, owner Round 9: the address an RPC worker of a unit
spanning machines listens on, as the rig reported it; nothing is resolved).
The rig-file folder is ``$MCGYVR_RIGS`` when the user named one, else the
config folder's ``rigs``. ``mcgyvr setup`` will write the file on a first run.

Each user-mode door run reads the rig again with the same scanner and holds
the reading to the file (:func:`door_check`): it says what moved, and it
refuses only when the fleet no longer fits -- a card the fleet's compose file
reserves is gone, or holds less memory than the file records. Anything else
that moved (RAM, docker, the hostname, a card the fleet does not use) is said
and admitted. The file is the user's description and the door never rewrites
it: a rig that changed for good is scanned again.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcgyvr.fleet.roots import FolderError, rigs_dir
from mcgyvr.scan import SSH_TIMEOUT_S, Network, Scan

#: What a rig name may be: a plain file name, as an ssh alias is.
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
#: The command that writes a rig file, as a refusal names it.
MAKE = "mcgyvr scan --rig {rig}"


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
    """One rig file: the rig's scan, kept to the facts the door holds a run to."""

    rig: str
    read_at: str
    hostname: str
    machine_id: str
    cards: tuple[Card, ...] = ()
    ram_total_gb: float | None = None
    disk_path: str | None = None
    disk_free_gb: float | None = None
    docker: str | None = None
    notes: tuple[str, ...] = ()
    #: The private IPv4 address a worker on this rig listens on, or None.
    private_ipv4: str | None = None
    #: How :attr:`private_ipv4` was picked, or why none was.
    private_ipv4_how: str = ""

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "rig": self.rig,
            "read_at": self.read_at,
            "hostname": self.hostname,
            "machine_id": self.machine_id,
            "cards": [
                {"index": card.index, "name": card.name, "total_mib": card.total_mib}
                for card in self.cards
            ],
            "ram_total_gb": self.ram_total_gb,
            "disk": (
                None
                if self.disk_path is None
                else {"path": self.disk_path, "free_gb": self.disk_free_gb}
            ),
            "docker": self.docker,
            "private_ipv4": self.private_ipv4,
            "private_ipv4_how": self.private_ipv4_how,
            "notes": list(self.notes),
        }
        return json.dumps(payload, indent=2) + "\n"


def from_json(text: str) -> Rig:
    """A rig file read back, or :class:`RigFileError` naming what is wrong."""
    try:
        raw = json.loads(text)
        disk = raw.get("disk")
        ram = raw.get("ram_total_gb")
        address = raw.get("private_ipv4")
        if address is not None and _listenable(address) is None:
            raise ValueError(
                f"private_ipv4 is {address!r}, not a private IPv4 address a "
                "worker may listen on"
            )
        return Rig(
            rig=str(raw["rig"]),
            read_at=str(raw["read_at"]),
            hostname=str(raw["hostname"]),
            machine_id=str(raw.get("machine_id", "")),
            cards=tuple(
                Card(
                    index=int(card["index"]),
                    name=str(card["name"]),
                    total_mib=int(card["total_mib"]),
                )
                for card in raw.get("cards") or ()
            ),
            ram_total_gb=None if ram is None else float(ram),
            disk_path=None if not disk else str(disk["path"]),
            disk_free_gb=None if not disk else float(disk["free_gb"]),
            docker=None if raw.get("docker") is None else str(raw["docker"]),
            notes=tuple(str(note) for note in raw.get("notes") or ()),
            private_ipv4=None if address is None else str(address),
            private_ipv4_how=str(raw.get("private_ipv4_how") or ""),
        )
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


def from_scan(rig: str, scan: Scan, read_at: str | None = None) -> Rig:
    """The rig file of ``rig`` from one scan of it."""
    address, how = private_ipv4(scan.network)
    return Rig(
        rig=rig,
        read_at=read_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        hostname=scan.machine.host,
        machine_id=scan.machine.id,
        cards=tuple(
            Card(index=gpu.index, name=gpu.name, total_mib=gpu.vram.total_mib)
            for gpu in scan.gpus
        ),
        ram_total_gb=None if scan.memory is None else scan.memory.total_gb,
        disk_path=None if scan.disk is None else str(scan.disk.path),
        disk_free_gb=None if scan.disk is None else scan.disk.free_gb,
        docker=scan.docker,
        notes=scan.notes,
        private_ipv4=address,
        private_ipv4_how=how,
    )


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
    difference in it says nothing about the machine.
    """
    found = [
        Moved(field, getattr(saved, field), getattr(now, field))
        for field in (
            "hostname",
            "machine_id",
            "ram_total_gb",
            "docker",
            "private_ipv4",
        )
        if getattr(saved, field) != getattr(now, field)
    ]
    before = {card.index: card for card in saved.cards}
    after = {card.index: card for card in now.cards}
    for index in sorted(before.keys() | after.keys()):
        was, is_now = before.get(index), after.get(index)
        if was != is_now:
            found.append(
                Moved(
                    f"card {index}",
                    "absent" if was is None else was.said(),
                    "absent" if is_now is None else is_now.said(),
                )
            )
    return tuple(found)


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


def door_check(host: str, saved: Rig, used: Iterable[int] | None, what: str) -> Rig:
    """Read ``host`` again under the door, say what moved, refuse a fleet that no
    longer fits. Returns the reading.

    The scan goes through :func:`mcgyvr.serving.gatelib.ssh`, so only a process
    the door started reaches the rig, and only the rig the door was opened for.
    """
    from mcgyvr.serving import gatelib

    try:
        done = gatelib.ssh(host, gatelib.scan_read_command(), timeout=SSH_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        gatelib.refuse(
            f"{what}: {host} did not answer the rig scan in {SSH_TIMEOUT_S:.0f}s; "
            "a rig that cannot be read is not compared, and nothing is started on it"
        )
    if done.returncode != 0:
        gatelib.refuse(
            f"{what}: the rig scan could not run on {host}: "
            f"{done.stderr.strip()[:300] or '(no stderr)'}"
        )
    try:
        now = from_scan(host, Scan.from_json(done.stdout))
    except (ValueError, KeyError, TypeError):
        gatelib.refuse(f"{what}: the rig scan on {host} printed no scan this reads")
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
