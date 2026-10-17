""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import re
import shutil
import socket
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from mcgyvr import atomic
from mcgyvr.config import FLEET_FILENAME, POLICY_FILENAME, ConfigError, parse
from mcgyvr.fleet.admit import layout_ids
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import FleetError, layout_sha256, mcorch_units

#
#
from mcgyvr.fleet.lock import LOCK_DIR as LOCK_DIR
from mcgyvr.fleet.lock import OWN_FLEET, approved_on_no_evidence
from mcgyvr.fleet.roots import (
    TAG,
    LiveFleetError,
    fleets_dir,
    home,
    is_fleet_name,
    live_file,
    live_fleet,
    split_name,
    tagged,
)
from mcgyvr.fleet.spans import SpanError, check_spans

#
#
_OLD_IPV4 = re.compile(r"^(?:0x[0-9a-f]*|\d+)(?:\.(?:0x[0-9a-f]*|\d+)){0,3}$")
#
#
_NAT64 = bytes.fromhex("0064ff9b 00000000 00000000")
#
#
#
LOCAL_SUFFIXES = (".localhost", ".local", ".home.arpa", ".internal")


class PromoteRefusedError(Exception):
    ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromoteRefusedError(f"{path} cannot be read: {exc}") from exc
    if not isinstance(loaded, dict):
        raise PromoteRefusedError(f"{path} is not a lock record")
    return loaded


def _read_setup(path: Path, loader: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    try:
        return loader(path.read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise PromoteRefusedError(f"{path} cannot be read: {exc}") from exc


def _pinned(
    fleet: dict[str, Any], name: str, lock: dict[str, Any], where: str
) -> dict[str, str]:
    ""
    layout = fleet["fleets"][name].get("layout", {})
    try:
        ids = layout_ids(fleet, layout)
    except KeyError as exc:
        raise PromoteRefusedError(
            f"{name}: {where} names {exc} in its layout but declares no id for it"
        ) from exc
    if layout_sha256(ids) != lock.get("layout_sha256"):
        raise PromoteRefusedError(
            f"{name}: the layout in {where} no longer matches its lock — re-lock "
            "from a passing dev run"
        )
    return ids


def _records(ids: dict[str, str]) -> list[Path]:
    ""
    return [LOCK_DIR / "rigs" / rig / f"{cmb}.json" for rig, cmb in sorted(ids.items())]


def _date_of(root: Path, name: str, records: list[Path]) -> str:
    ""
    latest: datetime | None = None
    for record in records:
        path = root / record
        if not path.is_file():
            raise PromoteRefusedError(
                f"{name}: the lock holds no combination record {record}"
            )
        stamp = _read_json(path).get("validated_at")
        try:
            validated = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            validated = None
        if not isinstance(stamp, str) or validated is None:
            raise PromoteRefusedError(
                f"{name}: {path} carries no validated_at to date the lock by "
                f"({stamp!r}); a fleet is promoted under the date of its lock"
            )
        if latest is None or validated > latest:
            latest = validated
    if latest is None:
        raise PromoteRefusedError(f"{name}: its layout pins no combination to date")
    return latest.date().isoformat()


def _approval_day(name: str, lock: dict[str, Any]) -> str:
    ""
    stamp = lock.get("approved_at")
    try:
        approved = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        approved = None
    if not isinstance(stamp, str) or approved is None:
        raise PromoteRefusedError(
            f"{name}: its lock, approved on no evidence, carries no approved_at "
            f"to date it by ({stamp!r})"
        )
    return approved.date().isoformat()


def _lock_day(root: Path, name: str, lock: dict[str, Any], ids: dict[str, str]) -> str:
    ""
    if approved_on_no_evidence(lock):
        return _approval_day(name, lock)
    return _date_of(root, name, _records(ids))


def lock_date(root: Path, fleet: dict[str, Any], name: str) -> str:
    ""
    if name not in (fleet.get("fleets") or {}):
        raise PromoteRefusedError(f"{name} is not a fleet of the setup handed in")
    lock_path = root / LOCK_DIR / f"{name}.json"
    if not lock_path.is_file():
        raise PromoteRefusedError(f"{name} has no lock at {lock_path}")
    lock = _read_json(lock_path)
    ids = _pinned(fleet, name, lock, "the setup handed in")
    return _lock_day(root, name, lock, ids)


def promote(dev_root: Path, setup: Path, name: str) -> Path:
    ""
    if TAG in name:
        raise PromoteRefusedError(
            f"{name!r}: promote takes the plain fleet name; the date in the "
            "folder's name is the lock's own"
        )
    if not is_fleet_name(name):
        raise PromoteRefusedError(f"{name!r} cannot name a fleet folder")

    dev_fleet = _read_setup(setup / FLEET_FILENAME, load_fleet)
    dev_policy = _read_setup(setup / POLICY_FILENAME, load_policy)
    fleets = dev_fleet.get("fleets") or {}
    if name not in fleets:
        raise PromoteRefusedError(f"{name} is not a fleet of {setup / FLEET_FILENAME}")
    try:
        check_spans(dev_fleet, fleets[name].get("layout") or {}, name=name)
    except SpanError as exc:
        raise PromoteRefusedError(
            f"{exc}; a fleet that splits a unit is not promoted"
        ) from exc
    try:
        mcorch_units(dev_policy, fleets[name].get("layout") or {}, name=name)
    except FleetError as exc:
        raise PromoteRefusedError(
            f"{exc}; a fleet that cannot serve its mcorch policy is not promoted"
        ) from exc

    lock_path = dev_root / LOCK_DIR / f"{name}.json"
    if not lock_path.is_file():
        raise PromoteRefusedError(
            f"{name} has no dev lock at {lock_path}: lock it from a passing dev "
            "run and commit it first"
        )
    lock = _read_json(lock_path)
    ids = _pinned(dev_fleet, name, lock, str(setup / FLEET_FILENAME))
    unsampled = approved_on_no_evidence(lock)
    records = [] if unsampled else _records(ids)
    for record in records:
        if not (dev_root / record).is_file():
            raise PromoteRefusedError(
                f"{name}: the dev lock holds no combination record {record}"
            )
    day = _lock_day(dev_root, name, lock, ids)
    folder = fleets_dir() / tagged(name, day)
    later = 2
    while folder.exists() or folder.is_symlink():
        if not unsampled and name != OWN_FLEET:
            raise PromoteRefusedError(
                f"{folder} already exists: a promoted fleet is a new folder, never "
                "written over or in place of another; a re-lock on a new date is "
                "a new folder"
            )
        #
        #
        #
        folder = fleets_dir() / tagged(name, f"{day}-{later}")
        later += 1

    block = fleets[name]
    layout = block.get("layout") or {}
    kept = {slot[0] for slots in layout.values() for slot in slots if slot}
    if unsampled:
        kept |= {unit for unit, body in dev_fleet["units"].items() if "rig" not in body}
    live_fleet_doc: dict[str, Any] = {
        "units": {
            unit: copy.deepcopy(body)
            for unit, body in dev_fleet["units"].items()
            if unit in kept
        },
        "rigs": {
            rig: copy.deepcopy(body)
            for rig, body in (dev_fleet.get("rigs") or {}).items()
            if rig in layout
        },
        "fleets": {name: copy.deepcopy(block)},
    }
    policy = copy.deepcopy(dev_policy)
    policy["ladder"] = [unit for unit in dev_policy.get("ladder") or [] if unit in kept]
    fleet_text = yaml.safe_dump(live_fleet_doc, sort_keys=False)
    policy_text = yaml.safe_dump(policy, sort_keys=False)
    try:
        parse(fleet_text, policy_text)
    except ConfigError as exc:
        raise PromoteRefusedError(
            f"{name}: the live fleet folder would not load as a setup: {exc}"
        ) from exc
    _pinned(load_fleet(fleet_text), name, lock, "the live fleet.yaml")

    files = {
        Path(FLEET_FILENAME): fleet_text.encode("utf-8"),
        Path(POLICY_FILENAME): policy_text.encode("utf-8"),
    }
    for relative in (LOCK_DIR / f"{name}.json", *records):
        files[relative] = (dev_root / relative).read_bytes()
    _build(folder, name, files)
    return folder


def _build(folder: Path, name: str, files: dict[Path, bytes]) -> None:
    ""
    fleets_dir().mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=fleets_dir()))
    try:
        for relative, data in files.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        if folder.exists() or folder.is_symlink():
            raise PromoteRefusedError(
                f"{folder} appeared while it was being built; it is left as it is"
            )
        os.rename(staging, folder)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def on_a_users_machine(address: str) -> str | None:
    ""
    try:
        host = urlsplit(address).hostname
    except ValueError:
        host = None
    if not host:
        return "names no host"
    if not host.isascii():
        #
        #
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return f"{host} is a name no resolver spells as a public one"
    host = host.rstrip(".").lower()
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if not _OLD_IPV4.match(host):
            if host == "localhost" or host.endswith(LOCAL_SUFFIXES) or "." not in host:
                return f"{host} is a name only a local network answers"
            return None
        try:
            ip = ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return f"{host} is a number no resolver reads as a public address"
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.packed.startswith(_NAT64):
            ip = ipaddress.IPv4Address(ip.packed[len(_NAT64) :])
    if not ip.is_global:
        return f"{host} is not a public address"
    return None


@dataclass(frozen=True)
class Switch:
    ""

    #
    pointer: Path
    #
    name: str
    #
    layout: str
    #
    previous: str | None
    #
    locked: bool
    #
    #
    moves: list[dict[str, Any]] = field(default_factory=list)
    #
    unmeasured: str | None = None


def _measured(previous: str, layout: str) -> tuple[bool, list[dict[str, Any]], str]:
    ""
    from_layout = split_name(previous)[0]
    lock_path = fleets_dir() / previous / LOCK_DIR / f"{from_layout}.json"
    if not lock_path.is_file():
        return (
            False,
            [],
            f"{previous} has no folder or lock at {lock_path} to measure it by",
        )
    lock = _read_json(lock_path)
    if layout not in (lock.get("next") or []):
        return False, [], f"{from_layout}'s lock lists no switch to {layout}"
    for switch in lock.get("switches") or []:
        if isinstance(switch, dict) and switch.get("to") == layout:
            return True, list(switch.get("moves") or []), ""
    return True, [], ""


def use(name: str) -> Switch:
    ""
    if not is_fleet_name(name):
        raise PromoteRefusedError(f"{name!r} cannot name a fleet folder")
    layout, _tag = split_name(name)
    folder = fleets_dir() / name
    if not folder.is_dir():
        raise PromoteRefusedError(
            f"{name} has no live fleet folder {folder}: `mcgyvr setup` promotes "
            "the fleet it locks"
        )
    fleet = _read_setup(folder / FLEET_FILENAME, load_fleet)
    if layout not in (fleet.get("fleets") or {}):
        raise PromoteRefusedError(f"{folder / FLEET_FILENAME} holds no fleet {layout}")
    lock = _read_json(folder / LOCK_DIR / f"{layout}.json")
    _pinned(fleet, layout, lock, str(folder))

    try:
        current = live_fleet()
    except LiveFleetError as exc:
        raise PromoteRefusedError(str(exc)) from exc
    locked, unmeasured = False, None
    moves: list[dict[str, Any]] = []
    if current is not None and current != name:
        locked, moves, why = _measured(current, layout)
        unmeasured = None if locked else why

    home().mkdir(parents=True, exist_ok=True)
    pointer = live_file()
    _point(pointer, name, datetime.now(UTC).isoformat(timespec="seconds"))
    return Switch(
        pointer=pointer,
        name=name,
        layout=layout,
        previous=current,
        locked=locked,
        moves=moves,
        unmeasured=unmeasured,
    )


def _point(pointer: Path, name: str, since: str) -> None:
    atomic.write(
        pointer,
        json.dumps({"fleet": name, "since": since}, indent=2, sort_keys=True) + "\n",
    )
