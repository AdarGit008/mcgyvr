"""This rig's lending settings: what it offers the fleet and where it listens.

A small JSON file names the roles and hardware the rig lends (cards whole, host
memory in MiB, cores), the image and container limits its sessions run under,
and the endpoints and ports a tunnel is reached on. Reading refuses anything
the fleet could not act on, an amount under the hub's lending floor among them,
so a settings file that parses is a setting every other part of the rig may
rely on. :meth:`Sharing.lent` turns the settings and a hardware report into
the resources a hello advertises (:mod:`mcgyvr.hubwire`'s contract).
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from mcgyvr import atomic, hostos, hubwire
from mcgyvr.fleet import roots
from mcgyvr.hubwire import (
    CARD_KINDS,
    LEND_FLOOR_CORES,
    LEND_FLOOR_MB,
    RESOURCE_CPU,
    RESOURCE_GPU,
    RESOURCE_RAM,
    RESOURCE_UNIFIED,
)
from mcgyvr.propose import DEFAULT_HEADROOM_GB
from mcgyvr.rig import hardware, protocol, sessionwire

#: The settings file's name inside the rig's home folder; `path()` joins the two.
SHARING_FILE = "rig-sharing.json"
#: A file larger than this is refused unread, so a stray file cannot be parsed.
MAX_SHARING_BYTES = 16384
#: The first tunnel port, and the one named when the settings name no other.
DEFAULT_LISTEN_PORT = 51820
#: The tunnel ports a rig may take, one per session it reports at once.
#: A range that would pass the last port stops at it instead.
TUNNEL_PORTS = protocol.MAX_SESSIONS_REPORTED
#: The memory a container is given when the settings name no other figure.
DEFAULT_CONTAINER_MB = 8192
#: How large the tensor cache may grow when the settings name no other size.
DEFAULT_CACHE_MAX_MB = 16384
#: The binaries a head and a worker start inside the engine image.
DEFAULT_HEAD_BINARY = "/app/llama-server"
DEFAULT_WORKER_BINARY = "/app/ggml-rpc-server"
#: The cards a rig may lend, whole, by vendor and kind: an NVIDIA card, and a
#: Mac's unified GPU (its memory with it, as one device).
LENT_KINDS = frozenset({("nvidia", RESOURCE_GPU), ("apple", RESOURCE_UNIFIED)})
#: The cards a session's container runs on, each by the vendor's own index
#: rather than by its place in the report: a CUDA worker or head, which a
#: unified GPU cannot be (no Metal in a container).
CONTAINER_KINDS = frozenset({("nvidia", RESOURCE_GPU)})
#: The systems this rig's sessions run on: Linux, in pooled containers. A Mac
#: or Windows rig offers no session role until a session host runs there (the
#: native one, P6), so it advertises nothing as lent.
SESSION_SYSTEMS = frozenset({hostos.LINUX})
#: Memory a lend leaves the owner beyond what is available: the headroom a fit
#: keeps on a card.
RAM_HEADROOM_MB = round(DEFAULT_HEADROOM_GB * 1024)
#: Logical cores a lend leaves the owner.
CORES_KEPT = 1
#: The lowest port the settings may name: below it a port needs privilege to take.
LOWEST_PORT = 1024
#: The shape of a binary path inside the image: absolute, plain segments, no "..".
BINARY = re.compile(r"/[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*")
#: Settings that once parsed and no longer do, each with the note shown in its
#: place. A file naming one still loads, and the note travels on `notes` so that
#: `rig share` can say what became of the setting.
RETIRED = {
    "max_vram_mb": "max_vram_mb: no longer a setting; a lent card is lent whole",
}


class SharingError(Exception):
    """Lending settings that could not be read, understood or written."""


#: The fields of a resource in the hub's contract, as a hardware report keeps
#: each resource.
_RESOURCE_FIELDS = tuple(hubwire.Resource.__dataclass_fields__)


@dataclass(frozen=True, kw_only=True)
class Sharing:
    """What this rig lends to the fleet, and the limits its sessions run under.

    `enabled` turns lending on at all; `roles` says which of head and worker are
    offered, `image` which engine image the containers run, `cards` which cards
    are lent (`None` for every one of them) and `max_ram_mb` how much memory a
    container may use. `ram_mb` is the host memory lent and `cpu_cores` the
    cores lent to whole models a head serves, 0 for none. A head serves models
    from `models_dir`, and `endpoints` names the hosts a tunnel is reached on.
    `notes` carries what the reader said about retired settings, and takes no
    part in comparison.
    """

    enabled: bool = False
    roles: tuple[str, ...] = ("worker",)
    image: str | None = None
    cards: tuple[int, ...] | None = None
    max_ram_mb: int | None = None
    models_dir: str | None = None
    endpoints: tuple[str, ...] = ()
    listen_port: int = DEFAULT_LISTEN_PORT
    cache: bool = True
    cache_max_mb: int = DEFAULT_CACHE_MAX_MB
    head_binary: str = DEFAULT_HEAD_BINARY
    worker_binary: str = DEFAULT_WORKER_BINARY
    ram_mb: int = 0
    cpu_cores: int = 0
    notes: tuple[str, ...] = field(default=(), compare=False)

    def offered_roles(self) -> tuple[str, ...]:
        """The roles this rig really offers: none unless lending is on with an
        image, and the head only when a models folder is named."""
        if not self.enabled or self.image is None:
            return ()
        return tuple(
            role
            for role in protocol.ROLES
            if role in self.roles and (role != "head" or self.models_dir)
        )

    def tunnel_ports(self) -> range:
        """The UDP ports sessions may listen on, one per session, running from
        `listen_port` up to the count of sessions reported or the last port."""
        return range(
            self.listen_port,
            min(self.listen_port + TUNNEL_PORTS, sessionwire.MAX_PORT + 1),
        )

    def container_mb(self) -> int:
        """The memory each container is given: the cap the settings name, or the
        default when they name none."""
        return self.max_ram_mb if self.max_ram_mb is not None else DEFAULT_CONTAINER_MB

    def lends(self, card_index: int, report: hardware.Report) -> int | None:
        """The vendor's index for the card lent as `card_index` to a session's
        container, or `None` when this rig does not lend that card to one.

        Lending off lends nothing, and a `cards` choice lends only the indexes it
        names. The card is looked up by its place in the report, since that is
        where the vendor and its index are kept alongside it.
        """
        return self._lent_card(card_index, report, CONTAINER_KINDS)

    def _lent_card(
        self,
        card_index: int,
        report: hardware.Report,
        kinds: frozenset[tuple[str, str]],
    ) -> int | None:
        if not self.enabled or (
            self.cards is not None and card_index not in self.cards
        ):
            return None
        for number, card in enumerate(report.cards):
            if card.index != card_index or number >= len(report.sources):
                continue
            vendor, index = report.sources[number]
            kind = report.kinds[number] if number < len(report.kinds) else RESOURCE_GPU
            return index if (vendor, kind) in kinds else None
        return None

    def session_roles(self, report: hardware.Report) -> tuple[str, ...]:
        """The roles this rig offers the hub's sessions on the machine `report`
        reads: none on a system no session runs on (:data:`SESSION_SYSTEMS`),
        and the head alone when no card is lent to a container, since memory
        and cores serve whole models only, never a pipeline stage."""
        system = report.host.os if report.host is not None else hostos.os_name()
        if system not in SESSION_SYSTEMS:
            return ()
        roles = self.offered_roles()
        if not any(self.lends(card.index, report) is not None for card in report.cards):
            roles = tuple(role for role in roles if role != "worker")
        return roles

    def lent(self, report: hardware.Report) -> tuple[hubwire.Resource, ...]:
        """What this rig lends of the machine `report` reads, as its hello
        advertises it: nothing unless it offers a session role
        (:meth:`session_roles`); then each lent card whole, and beside the head
        role `ram_mb` of host memory and `cpu_cores` cores, each held to what
        the machine has. A resource under its kind's lending floor
        (:func:`mcgyvr.hubwire.counts_as_lent`), or one the wire would refuse,
        is left out."""
        roles = self.session_roles(report)
        if not roles:
            return ()
        head = "head" in roles
        found: list[hubwire.Resource] = []
        for raw in report.resources:
            kind = raw.get("kind")
            fields: dict[str, Any] = {name: raw.get(name) for name in _RESOURCE_FIELDS}
            if kind in CARD_KINDS:
                index = raw.get("index")
                if not isinstance(index, int) or (
                    self._lent_card(index, report, LENT_KINDS) is None
                ):
                    continue
            elif kind == RESOURCE_RAM and head and self.ram_mb:
                total = min(self.ram_mb, int(raw.get("total_mb") or 0))
                free = raw.get("free_mb")
                fields["total_mb"] = total
                fields["free_mb"] = None if free is None else min(int(free), total)
            elif kind == RESOURCE_CPU and head and self.cpu_cores:
                fields["cores"] = min(self.cpu_cores, int(raw.get("cores") or 0))
            else:
                continue
            resource = hubwire.Resource(**fields)
            try:
                resource.validate()
            except (TypeError, ValueError):
                continue
            if hubwire.counts_as_lent(resource):
                found.append(resource)
        return tuple(found[: hubwire.MAX_RESOURCES])

    def lendable(self, report: hardware.Report) -> hardware.Report:
        """The report as this rig may lend it: what it lends (:meth:`lent`), a
        card it does not lend reporting no free VRAM, and free RAM held down to
        `max_ram_mb` when one is named."""
        if not self.enabled:
            return report
        cards = []
        for card in report.cards:
            free = (
                card.vram_free_mb if self.lends(card.index, report) is not None else 0
            )
            cards.append(replace(card, vram_free_mb=free))
        ram_free = report.ram_free_mb
        if ram_free is not None and self.max_ram_mb is not None:
            ram_free = min(ram_free, self.max_ram_mb)
        return replace(
            report, cards=tuple(cards), ram_free_mb=ram_free, lent=self.lent(report)
        )

    def refusals(self, report: hardware.Report) -> list[str]:
        """Why this lend is more than the machine `report` reads can give, one
        line each: memory past what is available less `RAM_HEADROOM_MB`, cores
        past all but `CORES_KEPT` of the logical ones, and a listed card under
        its kind's lending floor. Empty when it fits."""
        said: list[str] = []
        by_kind = {raw.get("kind"): raw for raw in report.resources}
        if self.ram_mb:
            available = report.ram_free_mb
            if available is None:
                said.append(
                    "ram_mb: this machine's available memory was not read, so "
                    "no memory can be lent"
                )
            elif self.ram_mb > available - RAM_HEADROOM_MB:
                most = max(0, available - RAM_HEADROOM_MB)
                said.append(
                    f"ram_mb: {self.ram_mb} MiB is more than this machine can "
                    f"lend: {available} MiB available less {RAM_HEADROOM_MB} MiB "
                    f"kept for you leaves {most} MiB"
                )
        if self.cpu_cores:
            logical = (by_kind.get(RESOURCE_CPU) or {}).get("cores")
            if not isinstance(logical, int):
                said.append(
                    "cpu_cores: this machine's cores were not read, so none can be lent"
                )
            elif self.cpu_cores > logical - CORES_KEPT:
                said.append(
                    f"cpu_cores: {self.cpu_cores} cores is more than this machine "
                    f"lends: {max(0, logical - CORES_KEPT)} of its {logical} "
                    f"(all but {CORES_KEPT}, kept for you)"
                )
        for raw in report.resources:
            kind, index = raw.get("kind"), raw.get("index")
            if kind not in CARD_KINDS or self.cards is None or index not in self.cards:
                continue
            floor = LEND_FLOOR_MB[str(kind)]
            total = int(raw.get("total_mb") or 0)
            if total < floor:
                said.append(
                    f"cards: card {index} has {total} MiB, under the {floor} MiB "
                    f"floor the hub counts a {kind} as lent at"
                )
        return said


def path() -> Path:
    """Where this rig keeps its lending settings: the file in its home folder."""
    return roots.home() / SHARING_FILE


def _refuse(field_name: str, why: str) -> SharingError:
    return SharingError(f"{path()}: {field_name}: {why}")


def _whole(value: object, field_name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise _refuse(field_name, f"not a whole number of {low} to {high}")
    return value


def _floored(value: int, field_name: str, floor: int, unit: str) -> int:
    """`value`, unless it lends something under the hub's lending floor
    (:data:`mcgyvr.hubwire.LEND_FLOOR_MB`, :data:`LEND_FLOOR_CORES`)."""
    if 0 < value < floor:
        raise _refuse(
            field_name,
            f"{value} is under the floor of {floor} {unit} the hub counts as "
            f"lent; lend 0 or at least {floor}",
        )
    return value


def read(data: object) -> Sharing:
    """The settings a parsed JSON object names, refusing what cannot be used.

    A setting the object leaves out keeps its default, so `{}` yields the
    defaults and the object need only name what it changes. A setting the rig no
    longer takes is turned into a note rather than refused; a name the rig never
    had, or a value of the wrong shape, is refused with the file's path.
    """
    if not isinstance(data, dict):
        raise _refuse("the file", "not an object")
    known = {f for f in Sharing.__dataclass_fields__ if f != "notes"}
    unknown = sorted(set(data) - known - set(RETIRED))
    if unknown:
        raise _refuse(unknown[0], "not a setting")
    kept = Sharing()
    out: dict[str, Any] = {}
    notes = tuple(note for name, note in RETIRED.items() if name in data)
    if notes:
        out["notes"] = notes
    if "enabled" in data:
        if type(data["enabled"]) is not bool:
            raise _refuse("enabled", "not true or false")
        out["enabled"] = data["enabled"]
    if "cache" in data:
        if type(data["cache"]) is not bool:
            raise _refuse("cache", "not true or false")
        out["cache"] = data["cache"]
    if "roles" in data:
        roles = data["roles"]
        if (
            not isinstance(roles, list)
            or not all(role in protocol.ROLES for role in roles)
            or len(set(roles)) != len(roles)
        ):
            raise _refuse("roles", "not a list of distinct roles: head, worker")
        out["roles"] = tuple(roles)
    if data.get("image") is not None:
        image = data["image"]
        if not isinstance(image, str) or not protocol.RUNTIME.fullmatch(image):
            raise _refuse("image", "not an image reference")
        out["image"] = image
    for name in ("head_binary", "worker_binary"):
        if name in data:
            value = data[name]
            if (
                not isinstance(value, str)
                or not BINARY.fullmatch(value)
                or "/../" in f"{value}/"
            ):
                raise _refuse(name, "not an absolute path inside the image")
            out[name] = value
    if data.get("cards") is not None:
        cards = data["cards"]
        if not isinstance(cards, list):
            raise _refuse("cards", "not a list of card indexes")
        out["cards"] = tuple(
            _whole(card, "cards", 0, protocol.MAX_CARD_INDEX) for card in cards
        )
    if data.get("max_ram_mb") is not None:
        out["max_ram_mb"] = _whole(data["max_ram_mb"], "max_ram_mb", 1, protocol.MAX_MB)
    if "ram_mb" in data:
        out["ram_mb"] = _floored(
            _whole(data["ram_mb"], "ram_mb", 0, protocol.MAX_MB),
            "ram_mb",
            LEND_FLOOR_MB[RESOURCE_RAM],
            "MiB of RAM",
        )
    if "cpu_cores" in data:
        out["cpu_cores"] = _floored(
            _whole(data["cpu_cores"], "cpu_cores", 0, hubwire.MAX_RESOURCE_CORES),
            "cpu_cores",
            LEND_FLOOR_CORES,
            "cores",
        )
    if "cache_max_mb" in data:
        out["cache_max_mb"] = _whole(
            data["cache_max_mb"], "cache_max_mb", 0, protocol.MAX_MB
        )
    if "listen_port" in data:
        out["listen_port"] = _whole(
            data["listen_port"], "listen_port", LOWEST_PORT, sessionwire.MAX_PORT
        )
    if data.get("models_dir") is not None:
        folder = data["models_dir"]
        if not isinstance(folder, str) or not os.path.isabs(folder):
            raise _refuse("models_dir", "not an absolute folder")
        out["models_dir"] = folder
    if "endpoints" in data:
        hosts = data["endpoints"]
        if not isinstance(hosts, list) or len(hosts) > protocol.MAX_ENDPOINTS:
            raise _refuse("endpoints", f"not a list of up to {protocol.MAX_ENDPOINTS}")
        for host in hosts:
            try:
                ipaddress.IPv4Address(host)
            except (ValueError, TypeError) as exc:
                raise _refuse("endpoints", "not IPv4 addresses") from exc
        out["endpoints"] = tuple(hosts)
    return replace(kept, **out)


def load() -> Sharing:
    """The lending settings kept on disk, or the defaults when no file exists.

    A file that cannot be read, is larger than `MAX_SHARING_BYTES`, or is not
    JSON is refused with its path; one that parses is handed to `read`.
    """
    target = path()
    try:
        with target.open("rb") as handle:
            raw = handle.read(MAX_SHARING_BYTES + 1)
    except FileNotFoundError:
        return Sharing()
    except OSError as exc:
        raise SharingError(f"{target}: not readable: {exc.strerror}") from exc
    if len(raw) > MAX_SHARING_BYTES:
        raise SharingError(f"{target}: larger than {MAX_SHARING_BYTES} bytes")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise SharingError(f"{target}: not JSON") from exc
    return read(data)


def save(sharing: Sharing) -> Path:
    """Write the settings and return the file they were kept in.

    The object about to be written is parsed again first, so settings the rig
    would refuse on the next read are refused now and never reach the disk. The
    file is written atomically into a folder only its owner may enter.
    """
    data = asdict(sharing)
    data.pop("notes")
    for name in ("roles", "cards", "endpoints"):
        if data[name] is not None:
            data[name] = list(data[name])
    read(data)  # refuse settings that would not parse back before writing them
    target = path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic.write(target, json.dumps(data, indent=2) + "\n")
    return target
