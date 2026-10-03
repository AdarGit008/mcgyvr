"""What this rig's owner lends to a hub's sessions, and the file it is kept in.

Lending is off until the owner turns it on (``mcgyvr rig share --on``), and
then only what the owner allows is lent:

* ``roles`` — ``worker`` (cards run another rig's layers), ``head`` (this rig
  serves a model and the hub relays requests to it), or both;
* ``image`` — the engine image the head and the workers run in (it carries
  the model server and the RPC server);
* ``cards`` — the cards lent, by the index the hello reports them under, or
  every card; a card of a vendor the engine is not started on is never lent.
  A card is lent whole: the hello and the heartbeats report a lent card's
  free memory as it is and a card not lent as having none, so the hub plans
  on whole cards. There is no cap on part of a card (a file kept with the
  ``max_vram_mb`` there once was is read with a note, and the cap dropped);
* ``max_ram_mb`` — the memory each container may take, swap included: the
  container's own limit, so the engine is ended past it;
* ``models_dir`` — the folder models are served from, read-only; the head
  is only offered with one, and only files under it are named;
* ``endpoints`` — the LAN addresses the tunnel is published on, or the
  machine's own when none are named; ``listen_port`` — the first of the
  tunnels' UDP ports: each session the rig is in at once takes the lowest
  free one of it and the ports after it (:meth:`Sharing.tunnel_ports`), so a
  rig in one session listens on ``listen_port`` itself;
* ``cache`` — whether a worker keeps the tensors its heads sent in a cache
  folder of its own, so a reload sends only what changed, up to
  ``cache_max_mb``.

It is kept in ``$MCGYVR_HOME/rig-sharing.json`` beside the rig credentials,
written whole (a staging file, then a rename) and holding no secret. A file
that does not read as this module writes it is refused by name, never
guessed at: lending is never turned on by a file it cannot read.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from mcgyvr.fleet import roots
from mcgyvr.rig import hardware, protocol, sessionwire

#: The file's name in the config folder.
SHARING_FILE = "rig-sharing.json"
#: The largest file read back; what this module writes is far smaller.
MAX_SHARING_BYTES = 16384
#: WireGuard's own default port.
DEFAULT_LISTEN_PORT = 51820
#: How many tunnel ports a rig listens on at most: one per session it is in at
#: once, and no more sessions than a hello names (the hub resumes only those).
TUNNEL_PORTS = protocol.MAX_SESSIONS_REPORTED
#: The memory a container may take, in MiB, when the owner names none.
DEFAULT_CONTAINER_MB = 8192
#: The most a worker's tensor cache keeps, in MiB, when the owner names none.
DEFAULT_CACHE_MAX_MB = 16384
#: The engine's model server and RPC server, where the engine image keeps them.
DEFAULT_HEAD_BINARY = "/app/llama-server"
DEFAULT_WORKER_BINARY = "/app/ggml-rpc-server"
#: The vendor whose cards the engine is started on.
LENT_VENDOR = "nvidia"
#: The lowest port a tunnel may listen on: an unprivileged one.
LOWEST_PORT = 1024
#: An engine's program inside its image: an absolute path, plainly spelled.
BINARY = re.compile(r"/[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*")
#: Settings a kept file may still hold that are no longer settings, and what
#: became of each: read with a note and dropped, never refused, so a rig that
#: lent before keeps lending.
RETIRED = {
    "max_vram_mb": "max_vram_mb: no longer a setting; a lent card is lent whole",
}


class SharingError(Exception):
    """The kept file is there but does not read; the message names the field."""


@dataclass(frozen=True, kw_only=True)
class Sharing:
    """What the owner lends; the defaults lend nothing."""

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
    notes: tuple[str, ...] = field(default=(), compare=False)

    def offered_roles(self) -> tuple[str, ...]:
        """The roles this rig offers now: none when lending is off or there is
        no image, and the head only with a models folder."""
        if not self.enabled or self.image is None:
            return ()
        return tuple(
            role
            for role in protocol.ROLES
            if role in self.roles and (role != "head" or self.models_dir)
        )

    def tunnel_ports(self) -> range:
        """The UDP ports the sessions' tunnels listen on, one each:
        ``listen_port`` and the ports after it, never past the last port."""
        return range(
            self.listen_port,
            min(self.listen_port + TUNNEL_PORTS, sessionwire.MAX_PORT + 1),
        )

    def container_mb(self) -> int:
        """The memory each container may take, in MiB."""
        return self.max_ram_mb if self.max_ram_mb is not None else DEFAULT_CONTAINER_MB

    def lends(self, card_index: int, report: hardware.Report) -> int | None:
        """The vendor's own index of card ``card_index`` when it is lent, else
        ``None``."""
        if not self.enabled or (
            self.cards is not None and card_index not in self.cards
        ):
            return None
        for number, card in enumerate(report.cards):
            if card.index != card_index or number >= len(report.sources):
                continue
            vendor, index = report.sources[number]
            return index if vendor == LENT_VENDOR else None
        return None

    def lendable(self, report: hardware.Report) -> hardware.Report:
        """``report`` as the hub is told of it while lending is on: a lent
        card whole, a card not lent with none free, free RAM at most
        :attr:`max_ram_mb`."""
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
        return replace(report, cards=tuple(cards), ram_free_mb=ram_free)


def path() -> Path:
    """``$MCGYVR_HOME/rig-sharing.json`` (default ``~/.mcgyvr``)."""
    return roots.home() / SHARING_FILE


def _refuse(field_name: str, why: str) -> SharingError:
    return SharingError(f"{path()}: {field_name}: {why}")


def _whole(value: object, field_name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise _refuse(field_name, f"not a whole number of {low} to {high}")
    return value


def read(data: object) -> Sharing:
    """The settings ``data`` holds, or :class:`SharingError` naming a field."""
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
    """The kept settings; lending off when there is no file."""
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
    """Keep ``sharing``, whole; where it was kept."""
    data = asdict(sharing)
    data.pop("notes")
    for name in ("roles", "cards", "endpoints"):
        if data[name] is not None:
            data[name] = list(data[name])
    read(data)  # what is written is what reads
    target = path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = target.parent / f".{SHARING_FILE}.{os.getpid()}.part"
    try:
        staging.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, target)
    except OSError:
        staging.unlink(missing_ok=True)
        raise
    return target
