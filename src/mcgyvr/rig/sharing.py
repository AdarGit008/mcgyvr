""

from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from mcgyvr import atomic
from mcgyvr.fleet import roots
from mcgyvr.rig import hardware, protocol, sessionwire

#
SHARING_FILE = "rig-sharing.json"
#
MAX_SHARING_BYTES = 16384
#
DEFAULT_LISTEN_PORT = 51820
#
#
TUNNEL_PORTS = protocol.MAX_SESSIONS_REPORTED
#
DEFAULT_CONTAINER_MB = 8192
#
DEFAULT_CACHE_MAX_MB = 16384
#
DEFAULT_HEAD_BINARY = "/app/llama-server"
DEFAULT_WORKER_BINARY = "/app/ggml-rpc-server"
#
LENT_VENDOR = "nvidia"
#
LOWEST_PORT = 1024
#
BINARY = re.compile(r"/[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*")
#
#
#
RETIRED = {
    "max_vram_mb": "max_vram_mb: no longer a setting; a lent card is lent whole",
}


class SharingError(Exception):
    ""


@dataclass(frozen=True, kw_only=True)
class Sharing:
    ""

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
        ""
        if not self.enabled or self.image is None:
            return ()
        return tuple(
            role
            for role in protocol.ROLES
            if role in self.roles and (role != "head" or self.models_dir)
        )

    def tunnel_ports(self) -> range:
        ""
        return range(
            self.listen_port,
            min(self.listen_port + TUNNEL_PORTS, sessionwire.MAX_PORT + 1),
        )

    def container_mb(self) -> int:
        ""
        return self.max_ram_mb if self.max_ram_mb is not None else DEFAULT_CONTAINER_MB

    def lends(self, card_index: int, report: hardware.Report) -> int | None:
        ""
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
        ""
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
    ""
    return roots.home() / SHARING_FILE


def _refuse(field_name: str, why: str) -> SharingError:
    return SharingError(f"{path()}: {field_name}: {why}")


def _whole(value: object, field_name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise _refuse(field_name, f"not a whole number of {low} to {high}")
    return value


def read(data: object) -> Sharing:
    ""
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
    ""
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
    ""
    data = asdict(sharing)
    data.pop("notes")
    for name in ("roles", "cards", "endpoints"):
        if data[name] is not None:
            data[name] = list(data[name])
    read(data)  #
    target = path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic.write(target, json.dumps(data, indent=2) + "\n")
    return target
