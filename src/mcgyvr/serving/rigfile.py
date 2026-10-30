"""The rig file: one machine as a scan read it, kept under the rig's own name.

A rig file is one reading of one machine, taken by ``mcgyvr scan --rig`` and
stored as json at ``<rigs dir>/<rig>.json`` — the rigs folder named by
``$MCGYVR_RIGS``, else ``rigs`` under the mcgyvr home. It keeps the reading
whole, the rig name it was read under and when it was read, and it is written
through a part file renamed onto the target, so a half-written rig file is never
read.

A caller asks the record through :class:`Rig`, which parses the stored reading
into a :class:`mcgyvr.scan.Scan` once and answers from it: the cards, RAM, CPU,
measured memory bandwidth, disk, models on disk, docker, notes, the private IPv4
a worker may listen on, and the recorded snapshot tokens. A section the scan did
not determine is None here, never a zero.

A rig file also keeps the addresses a person stated its units are reached at
(``mcgyvr setup --rig-address``), apart from the reading, since nobody read
them off the machine. :func:`resolve_hosts` finds a rig under any of its names:
its rig name, the hostname its scan recorded, an address its scan recorded or a
person stated, or a name that resolves to one of those addresses here.

Two comparisons hold a rig to its file. :func:`moved` lists what differs from
what the file recorded, which is printed and not acted on; :func:`misfits` names
the cards the fleet uses that are gone or smaller, which stops a run.
:func:`save` does not replace a file that knew its cards with a reading that
could not read them, and :func:`required` refuses a run on a rig that has no
file at all.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Any

from mcgyvr import atomic
from mcgyvr import scan as scan_module
from mcgyvr.fleet.roots import FolderError, rigs_dir
from mcgyvr.scan import BRIDGE_PREFIXES, ModelOnDisk, Network, Scan

#: A rig is named as ssh names it, so the name is a plain one: letters, digits,
#: '.', '_' and '-', not starting with '.', which is also a file name.
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
#: The command a refusal names to write the rig file it wanted: a read-only ssh
#: scan of the rig, its name filled in.
MAKE = "mcgyvr scan --rig {rig}"
#: The rig name a scan of this machine is filed under when no host was named.
LOCAL = "localhost"
#: The snapshot tokens compared as text, one token each: the CPU's model and max
#: MHz, the measured DDR speed, the power limits, the first card's compute
#: capability and slot, the further cards' names, the driver and the kernel. They
#: are read from the reading's own snapshot rather than from the parsed Scan, so a
#: token the reader could not fill is absent here, and a key the file never held
#: says nothing about the machine.
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
#: The fields whose change is a change of the rig's hardware rather than of what
#: runs on it: RAM, cores, threads, and the measured memory bandwidth. The cards
#: are compared card by card under names like "card 0", so they are not listed.
#: Bandwidth is a measurement, so it has moved only past this fraction of the
#: figure the file recorded; a figure either reading lacked is not compared.
HARDWARE = ("ram_total_gb", "cpu_cores", "cpu_threads", "bandwidth_gbps")
BANDWIDTH_TOLERANCE = 0.15
#: Docker's default bridge network. An address in it is taken for docker's own
#: only when the reading names no interface it sits on; a named interface
#: decides by its name, so a LAN numbered inside this network is kept.
DOCKER_BRIDGE = ipaddress.IPv4Network("172.17.0.0/16")
#: The flag that states the address a rig's units are reached at, for a rig
#: whose scan recorded none; a refusal names it with the rig filled in.
STATE = "mcgyvr setup --rig-address {rig}={address}"
#: Seconds a name is given to resolve to addresses here before it is taken to
#: resolve to none, so a resolver that hangs never holds a run.
RESOLVE_S = 2.0


class RigFileError(Exception):
    """A rig file that cannot be named, written, read, or understood.

    Raised for a rig name that is not a plain name, a rigs folder that cannot be
    named, a file that cannot be read, and a document no :class:`Rig` can be made
    from, so a caller never acts on a partial record.
    """


@dataclass(frozen=True)
class Card:
    """One card of a rig, as the reading records it.

    ``index`` is the card's own index, ``name`` the tool's name for it, and
    ``total_mib`` its whole VRAM in MiB — the figures :meth:`said` puts into a
    message and :func:`misfits` compares against.
    """

    index: int
    name: str
    total_mib: int

    def said(self) -> str:
        return f"{self.name}, {self.total_mib} MiB"


@dataclass(frozen=True)
class Rig:
    """One rig's file: the name it was read under, when, and the reading itself.

    ``reading`` is the scan's document exactly as it was printed, and every
    property here answers through :attr:`scan`, so a caller asks the record about
    its machine without parsing json. A section the scan did not determine is
    None, never a default.

    ``addresses`` are the IPv4 addresses a person stated the rig's units are
    reached at, kept apart from the reading because no scan read them.

    :meth:`to_json` and :func:`from_json` are the file's own shape: a mapping of
    ``rig``, ``read_at`` and ``reading``, and ``addresses`` once one is stated.
    """

    rig: str
    read_at: str
    reading: Mapping[str, Any]
    addresses: tuple[str, ...] = ()

    @cached_property
    def scan(self) -> Scan:
        return Scan.from_json(json.dumps(self.reading))

    @property
    def hostname(self) -> str:
        return self.scan.machine.host

    @property
    def os(self) -> str | None:
        """The system the reading states (``host.os``), or None for a reading
        taken before readers stated one."""
        return self.scan.host.os if self.scan.host is not None else None

    @property
    def machine_id(self) -> str:
        return self.scan.machine.id

    @property
    def rig_id(self) -> str | None:
        """The ``rig-`` id the reading hashes to, or None when it is refused.

        A reading holding a field :func:`mcgyvr.fleet.ids.rig_id` will not hash —
        a card whose size was never read, say — has no id, so a caller comparing
        rigs reads None instead of failing.
        """
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
        """The recorded snapshot tokens the reading carries, folded to strings.

        Only the keys in ``RECORDED``, and only those the reading's own
        ``snapshot`` mapping holds: a token the reader could not fill is absent
        rather than empty, and a key absent here is one the file never had.
        """
        said = self.reading.get("snapshot")
        said = said if isinstance(said, Mapping) else {}
        return {key: str(said[key]) for key in RECORDED if key in said}

    @property
    def private_ipv4(self) -> str | None:
        """The private IPv4 a worker on this rig may listen on, or None.

        Picked from the reading's network section each time it is asked, by
        :func:`private_ipv4`; :attr:`private_ipv4_how` says why that one.
        """
        return private_ipv4(self.scan.network)[0]

    @property
    def private_ipv4_how(self) -> str:
        """How the address above was picked, or why no address is recorded.

        Every branch of :func:`private_ipv4` returns a sentence saying what the
        reading held, so this is printed beside the address or in its place.
        """
        return private_ipv4(self.scan.network)[1]

    @property
    def reached_at(self) -> tuple[str, ...]:
        """Every address this rig answers at: those stated, then those scanned."""
        return tuple(dict.fromkeys((*self.addresses, *scanned_addresses(self.scan))))

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "rig": self.rig,
            "read_at": self.read_at,
            "reading": self.reading,
        }
        if self.addresses:
            payload["addresses"] = list(self.addresses)
        return json.dumps(payload, indent=2) + "\n"


def from_json(text: str) -> Rig:
    """One rig file's text as a :class:`Rig`, or :class:`RigFileError`.

    The document must be json holding ``rig``, ``read_at`` and ``reading``, and
    the reading must parse into a :class:`mcgyvr.scan.Scan`. ``addresses`` is
    optional, and each one it holds must be an address :func:`stated_address`
    takes. Anything else — text that is not json, a mapping without one of those
    keys, a reading whose fields are of the wrong type — is refused with the
    name of the failure.
    """
    try:
        raw = json.loads(text)
        rig = Rig(
            rig=str(raw["rig"]),
            read_at=str(raw["read_at"]),
            reading=dict(raw["reading"]),
            addresses=tuple(
                stated_address(str(one)) for one in raw.get("addresses") or ()
            ),
        )
        rig.scan  # noqa: B018 -- a reading Scan does not take is no rig file
        return rig
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RigFileError(f"not a rig file ({type(exc).__name__}: {exc})") from None


def _listenable(stated: object) -> ipaddress.IPv4Address | None:
    """The IPv4 address ``stated`` names, when a worker may listen on it.

    None for everything else: text that is not an address, an IPv6 address that
    is not the mapped form of an IPv4 one, and any address the door's own rule
    (:func:`mcgyvr.serving.llamacpp.worker_may_listen`) excludes — every
    interface, loopback, or one the internet can reach.
    """
    from mcgyvr.serving.llamacpp import worker_may_listen

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


def _bridged(address: str, interfaces: Iterable[str]) -> bool:
    """Whether ``address`` is a docker or virtual bridge's rather than the rig's.

    It is when every interface the reading names for it is a bridge or a
    bridge's pair (:data:`mcgyvr.scan.BRIDGE_PREFIXES`). When the reading
    names no interface for it, it is when it lies in :data:`DOCKER_BRIDGE`.
    """
    names = [name for name in interfaces if name]
    if names:
        return all(name.startswith(BRIDGE_PREFIXES) for name in names)
    return ipaddress.IPv4Address(address) in DOCKER_BRIDGE


def stated_address(said: str) -> str:
    """The IPv4 address ``said`` names, as a rig's units may be reached at.

    ``ValueError`` for text that is not an IPv4 address, and for one no other
    machine reaches a rig at: loopback, link-local, or every interface.
    """
    try:
        address = ipaddress.IPv4Address(said.strip())
    except ValueError:
        raise ValueError(f"{said!r} is not an IPv4 address") from None
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ValueError(
            f"{said!r} is a loopback, link-local or every-interface address, "
            "which no other machine reaches a rig at"
        )
    return str(address)


def scanned_addresses(scan: Scan) -> tuple[str, ...]:
    """The IPv4 addresses a scan found its machine at, other machines may use.

    The address it was reached at over ssh, then the addresses on its
    interfaces, with loopback, link-local and docker or virtual bridge
    addresses (:func:`_bridged`) left out: every machine running docker holds
    the same bridge address, so it names none of them.
    """
    network = scan.network
    if network is None:
        return ()
    held: dict[str, list[str]] = {}
    for one in network.ipv4:
        held.setdefault(one.address, []).append(one.interface)
    found: list[str] = []
    for said in (network.reached_at, *held):
        if said is None:
            continue
        try:
            address = stated_address(said)
        except ValueError:
            continue
        if not _bridged(address, held.get(address, [])):
            found.append(address)
    return tuple(dict.fromkeys(found))


def private_ipv4(network: Network | None) -> tuple[str | None, str]:
    """The rig's private IPv4 and how it was chosen, from its network section.

    Docker and virtual bridge addresses (:func:`_bridged`) are set aside first,
    since no other machine reaches the rig there. Of the rest: the address the
    rig was reached at over ssh, when a worker may listen there, because that is
    the one its other machines use. Otherwise its one listenable interface
    address. Otherwise none, with the sentence saying why: a rig holding several
    private addresses has none of them guessed, and the sentence says which they
    are. Whenever a bridge address was set aside, the sentence names it.
    """
    if network is None:
        return None, "the scan read no network (a scan from before addresses)"
    held: dict[str, list[str]] = {}
    for one in network.ipv4:
        listens = _listenable(one.address)
        if listens is not None:
            held.setdefault(str(listens), []).append(one.interface)
    reached = _listenable(network.reached_at)
    if reached is not None and not _bridged(str(reached), held.get(str(reached), [])):
        return str(reached), "the address the rig was reached at over ssh"
    if network.reached_at is None:
        why = "it was not reached over ssh"
    elif reached is not None:
        why = (
            f"it was reached at {network.reached_at}, a docker or virtual bridge "
            "address"
        )
    else:
        why = f"it was reached at {network.reached_at}, not a private IPv4 address"
    bridges = [address for address, names in held.items() if _bridged(address, names)]
    found = {
        address: names for address, names in held.items() if address not in bridges
    }
    aside = ""
    if bridges:
        listed = ", ".join(
            f"{address} on {', '.join(held[address])}" for address in bridges
        )
        aside = (
            f" once the docker and virtual bridge addresses are set aside ({listed})"
        )
    if len(found) == 1:
        ((only, names),) = found.items()
        return (
            only,
            f"the one private IPv4 on its interfaces ({', '.join(names)})"
            f"{aside}; {why}",
        )
    if not found:
        return None, f"{why}, and no private IPv4 is on its interfaces{aside}"
    said = ", ".join(
        f"{address} ({', '.join(names)})" for address, names in found.items()
    )
    return None, (
        f"{why}, and it holds several private IPv4 addresses ({said}){aside}; "
        "none is guessed. Reach it over ssh at the one its other machines use (its "
        "ssh HostName) and scan it again"
    )


def from_reading(
    rig: str, reading: Mapping[str, Any], read_at: str | None = None
) -> Rig:
    """A rig named ``rig`` around ``reading``, or :class:`RigFileError`.

    ``read_at`` is the time stated, or this moment in UTC stamped as
    ``YYYY-MM-DDTHH:MM:SSZ``. The reading is parsed as a :class:`Scan` at once,
    so a reading this cannot take is refused here, before anything is written.
    """
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
    """Where the rig file of ``rig`` is: ``<rigs dir>/<rig>.json``.

    The name must be a plain one, and the rigs folder must be one that can be
    named; either failing is a :class:`RigFileError`, so nothing is read from or
    written to a path guessed from a name that is not a rig's.
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
    """Write ``rig``'s file over whatever was there, and return its path.

    The rigs folder is made when it is missing, and the file is replaced whole
    (:func:`mcgyvr.atomic.write`), so a reader never sees a half-written rig
    file.
    """
    target = path(rig.rig)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic.write(target, rig.to_json())
    return target


@dataclass(frozen=True)
class Saved:
    """What :func:`save` made of one reading, and where it went.

    ``now`` is the rig as the reading was read, ``before`` the rig file that was
    there (None when there was none, it could not be read, or it is not a rig
    file), ``path`` where the file is, and ``kept`` whether the file that was
    there was left as it was.
    """

    now: Rig
    before: Rig | None
    path: Path
    #: Whether the rig file that was there was left untouched: it knew its cards
    #: and this reading could not read them, so replacing it would lose the record
    #: of cards the machine has.
    kept: bool


def save(rig: str, reading: Mapping[str, Any]) -> Saved:
    """Record ``reading`` under ``rig``, unless that would lose the cards it knew.

    A rig file that knows its cards is not replaced by a reading whose card list
    was not determined: that reading says nothing about the cards, and writing it
    would make the next healthy scan report every recorded card as new. The
    reading is still returned in ``now`` for comparison, with ``kept`` saying the
    file was left as it was. The addresses a person stated are carried over: a
    scan does not read them, so a new reading says nothing against them.
    """
    now = from_reading(rig, reading)
    try:
        before = read(rig)
    except RigFileError:
        before = None
    if before is not None and before.addresses:
        now = replace(now, addresses=before.addresses)
    target = path(rig)
    known = before is not None and before.scan.gpus_determined
    if known and not now.scan.gpus_determined:
        return Saved(now=now, before=before, path=target, kept=True)
    return Saved(now=now, before=before, path=write(now), kept=False)


def read(rig: str) -> Rig | None:
    """The rig file of ``rig``, or None when there is no file there.

    A file that is there but cannot be read, or is not a rig file this takes, is
    a :class:`RigFileError` naming its path: absent and broken are told apart by
    None against an exception, and neither is a rig.
    """
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


def state_addresses(rig: str, addresses: Iterable[str]) -> Path:
    """Record ``addresses`` as where ``rig``'s units are reached at, and the path.

    They replace any addresses stated before, and each must be one
    :func:`stated_address` takes. A rig with no file is :class:`RigFileError`
    naming the scan that writes one: an address is kept beside a reading, so
    there must be a reading to keep it beside.
    """
    try:
        stated = tuple(dict.fromkeys(stated_address(one) for one in addresses))
    except ValueError as exc:
        raise RigFileError(f"{rig}: {exc}") from None
    saved = read(rig)
    if saved is None:
        raise RigFileError(
            f"there is no rig file for {rig} ({path(rig)}) to state its address "
            f"in: write it with `{MAKE.format(rig=rig)}` first"
        )
    return write(replace(saved, addresses=stated))


@dataclass(frozen=True)
class Moved:
    """One field that differs from what the rig file recorded of the rig.

    ``field`` names it as a message would (``hostname``, ``bandwidth_gbps``,
    ``card 0``), ``was`` what the file recorded and ``now`` what the later
    reading found; both are untyped, so a number, a name and ``"absent"`` are
    held the same way.
    """

    field: str
    was: object
    now: object

    def said(self) -> str:
        return f"{self.field} {self.was} -> {self.now}"


def moved(saved: Rig, now: Rig) -> tuple[Moved, ...]:
    """Every field of ``now`` that differs from ``saved``, in a fixed order.

    The identity and capacity fields are compared as they are, the measured
    bandwidth only past :data:`BANDWIDTH_TOLERANCE` of the figure the file
    recorded, and the recorded snapshot tokens as text, a token the reading lost
    counting as ``"unread"``. The cards are compared card by card, and only when
    both readings determined the card list: a card list that was not determined
    would otherwise report every recorded card as pulled.
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
    # A recorded token that is gone from this reading is a move ("unread" is said
    # for it); a token the file never held says nothing about the machine.
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
    """Whether ``change`` is a change of the rig's hardware, not of what it runs.

    True for the fields in :data:`HARDWARE` and for any card, which :func:`moved`
    names ``card N``; a new kernel, driver or docker version is not one.
    """
    return change.field in HARDWARE or change.field.startswith("card ")


def misfits(saved: Rig, now: Rig, used: Iterable[int] | None) -> tuple[str, ...]:
    """The ways ``now`` no longer fits the fleet, one sentence each.

    ``used`` holds the card indexes the fleet's compose file reserves, and None
    means every card the rig file records. A used card that is absent now, or
    holds less VRAM than the file records, is answered with a sentence naming it;
    a card that is new, or larger than recorded, fits and says nothing.
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
    """The card indexes a compose file's services reserve, or None when unreadable.

    Every ``device_ids`` entry of every service is read as a card index. One that
    is not an ASCII number — ``all``, a UUID, a card name — makes the whole
    answer None, since the set of cards would then be a guess; an empty tuple
    says the file reserves no card.
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
    """The rig file of ``host``, or a gate refusal when there is no file to hold it to.

    ``what`` names the gate in the messages. A rig name or rigs folder this
    cannot read, and a rig with no file, both stop the run here through
    :func:`mcgyvr.serving.gatelib.refuse`: a door holds a rig to the rig as the
    user described it, so nothing is started on a rig nobody described, and the
    refusal says which command writes that file.
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
    """Print how ``host`` moved since its rig file, and refuse one that no longer fits.

    Every move :func:`moved` finds is printed against the time the file was read,
    and a move alone is reported and never acted on. The refusals come from
    :func:`misfits` — a card the fleet uses that is gone or smaller — and stop
    the run with :func:`mcgyvr.serving.gatelib.refuse`, since the fleet was
    planned for cards this rig no longer has. ``now`` is returned, so a caller
    that passes the check goes on with the reading that was checked.
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


def recorded_scans() -> dict[str, Scan]:
    """Every scan the fleet's rig files record, keyed by rig name, by hostname,
    and by each address a person stated for the rig.

    A rigs folder that cannot be resolved gives no scans, and a rig file that
    cannot be read or parsed is skipped. Every key of one rig points at the
    same scan, so a lookup by any of its names finds it.
    """
    try:
        folder = rigs_dir()
    except FolderError:
        return {}
    found: dict[str, Scan] = {}
    for path in sorted(folder.glob("*.json")):
        try:
            recorded = from_json(path.read_text(encoding="utf-8"))
        except (OSError, RigFileError):
            continue
        found.setdefault(recorded.rig, recorded.scan)
        if recorded.hostname:
            found.setdefault(recorded.hostname, recorded.scan)
        for address in recorded.addresses:
            found.setdefault(address, recorded.scan)
    return found


_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


def _names_this_machine(name: str) -> bool:
    """Whether a hostname names this machine: a localhost alias, or a local IP address.

    Anything else, including a name that is not an IP address at all, is another
    host's name as far as this check can tell.
    """
    lowered = name.strip().lower().rstrip(".")
    if lowered in _LOCAL_NAMES:
        return True
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _same_host(recorded: str, wanted: str) -> bool:
    """Whether two hostnames name one host, either being the other's full form.

    The comparison ignores case and a trailing dot; an empty name on either side
    matches nothing.
    """
    left = recorded.strip().lower().rstrip(".")
    right = wanted.strip().lower().rstrip(".")
    if not left or not right:
        return False
    return left == right or left.startswith(f"{right}.") or right.startswith(f"{left}.")


def resolve_hosts(scans: dict[str, Scan], wanted: Iterable[str]) -> dict[str, Scan]:
    """The scans, plus an entry for each wanted host that no key already names.

    A name for this machine is resolved by the id of the machine it runs on; an
    IPv4 address by the addresses the scans recorded; any other name by the
    hostnames the rig files recorded, and failing that by the addresses it
    resolves to here (:func:`addresses_of`). A name that finds no scan, or more
    than one machine, is left out of the result.
    """
    resolved = dict(scans)
    local: str | None = None
    for name in wanted:
        if name in resolved:
            continue
        if _names_this_machine(name):
            if local is None:
                local = scan_module.local_machine_id()
            match = _local_scan(scans, local)
        elif _is_ipv4(name):
            match = _addressed_scan(scans, (name,))
        else:
            match = _named_scan(scans, name)
            if match is None:
                match = _addressed_scan(scans, addresses_of(name))
        if match is not None:
            resolved[name] = match
    return resolved


def addresses_of(name: str) -> tuple[str, ...]:
    """The IPv4 addresses ``name`` resolves to here, or none.

    The resolver is given :data:`RESOLVE_S` seconds on a thread of its own; a
    name it cannot resolve, or does not resolve in time, has no addresses, so a
    resolver that is down or hangs leaves a host unmatched rather than failing.
    """
    found: list[tuple[str, ...]] = []

    def look() -> None:
        found.append(_resolve(name))

    worker = threading.Thread(target=look, name=f"resolve {name}", daemon=True)
    worker.start()
    worker.join(RESOLVE_S)
    return found[0] if found else ()


def _resolve(name: str) -> tuple[str, ...]:
    """The IPv4 addresses the resolver answers for ``name``, none when it cannot."""
    try:
        answers = socket.getaddrinfo(name, None, socket.AF_INET, socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return ()
    return tuple(dict.fromkeys(str(answer[4][0]) for answer in answers))


def _is_ipv4(name: str) -> bool:
    try:
        ipaddress.IPv4Address(name)
    except ValueError:
        return False
    return True


def _addressed_scan(scans: dict[str, Scan], addresses: Iterable[str]) -> Scan | None:
    """The scan of the one machine found at any of ``addresses``, else none.

    An address is found as a key a person stated (:func:`recorded_scans`) or
    among the addresses a scan recorded (:func:`scanned_addresses`). Matches
    are counted by machine id, so addresses landing on two machines are
    refused rather than guessed at.
    """
    wanted = set(addresses)
    if not wanted:
        return None
    matched = [scans[address] for address in wanted if address in scans]
    matched += [
        recorded
        for recorded in scans.values()
        if wanted.intersection(scanned_addresses(recorded))
    ]
    if len({recorded.machine.id for recorded in matched}) != 1:
        return None
    return matched[0]


def _local_scan(scans: dict[str, Scan], os_machine_id: str) -> Scan | None:
    """The first scan taken on the machine with this id, else none."""
    for recorded in scans.values():
        if recorded.machine.id == os_machine_id:
            return recorded
    return None


def _named_scan(scans: dict[str, Scan], name: str) -> Scan | None:
    """The scan recorded under a hostname naming `name`, or none when ambiguous.

    Several keys can point at one scan, so the matches are counted by machine id:
    a name matching more than one machine is refused rather than guessed at.
    """
    matched = [recorded for host, recorded in scans.items() if _same_host(host, name)]
    if len({recorded.machine.id for recorded in matched}) != 1:
        return None
    return matched[0]
