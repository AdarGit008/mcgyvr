"""A dev lock becomes a live fleet by promotion: a new folder, never in place.

Owner, 2026-09-15: "stamped for live = another fleet setup available for live
(no overwrite, not in place of, new folder new files)"; "~/.mcgyvr/fleets/
<name>/   live can switch between fleets runtime". Owner, 2026-09-16: "all
fleets get tagged with date - promote with the date in fleet name - switching
between verified fleets is a common action during runtime".

:func:`promote` reads one fleet's dev lock from the dev root and writes
``~/.mcgyvr/fleets/<fleet>@<date>/`` — a setup of its own that ``mcgyvr
config`` loads: ``fleet.yaml`` (profile live, that fleet's units, rigs and
fleet block), ``policy.yaml`` (the dev policy, its ladder filtered to those
units) and the fleet's lock under ``records/fleet/``. The date is the lock's
own (:func:`lock_date`) and the folder's name is the only place it is
spelled: inside, the fleet keeps its plain name, so a re-lock on a new date
is a new folder beside the old, which stays as a verified config, and a
folder promoted before the ruling is tagged by a rename (:func:`tag`). Every
refusal is decided before anything is written, the folder is built beside its
place and renamed into it, and an existing folder is never touched.

:func:`use` names the fleet live runs in the config folder's ``live.json``: any
promoted folder whose layout still matches its own lock. It says whether the
move from the fleet that was live is one that fleet's lock measured
(:class:`Switch`), and starts nothing. Nothing here writes the dev root.

:func:`approve_own` is the one other way a folder is written: ``mcgyvr init``
approves the user's own fleet of hosted units, which lays out no rig and so
needs no dev lock, and names it live through :func:`use` like any other.
"""

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

from mcgyvr.config import FLEET_FILENAME, POLICY_FILENAME, ConfigError, parse
from mcgyvr.fleet.admit import layout_ids
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import FleetError, layout_sha256, mcorch_units
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

#: Where a lock sits under the dev root and under a live fleet folder alike.
LOCK_DIR = Path("records") / "fleet"
#: The fleet ``mcgyvr init`` approves from the setup it wrote (:func:`approve_own`),
#: and who its lock says approved it.
OWN_FLEET = "own"
OWN_APPROVER = "mcgyvr init"
#: An IPv4 address in a spelling ``inet_aton`` reads and ``ipaddress`` does not:
#: one to four parts, each decimal, octal (a leading 0) or hexadecimal (0x).
_OLD_IPV4 = re.compile(r"^(?:0x[0-9a-f]*|\d+)(?:\.(?:0x[0-9a-f]*|\d+)){0,3}$")
#: The NAT64 well-known prefix (RFC 6052) as its first 12 bytes; the last 4 of
#: an address under it are an IPv4 address.
_NAT64 = bytes.fromhex("0064ff9b 00000000 00000000")
#: Names only a local network answers: ``localhost`` and its subdomains (RFC
#: 6761), multicast DNS (RFC 6762), the home network (RFC 8375) and names kept
#: for private use. A name with no dot at all is one too.
LOCAL_SUFFIXES = (".localhost", ".local", ".home.arpa", ".internal")


class PromoteRefusedError(Exception):
    """A promotion, a live switch or a tag was refused, naming what is in the way."""


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
    """``rig id -> combination id`` for ``name``, refused unless it matches ``lock``."""
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
    """The combination records a layout's pins name, relative to a lock root."""
    return [LOCK_DIR / "rigs" / rig / f"{cmb}.json" for rig, cmb in sorted(ids.items())]


def _date_of(root: Path, name: str, records: list[Path]) -> str:
    """The latest ``validated_at`` day among ``records``, refused if any has none."""
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


def lock_date(root: Path, fleet: dict[str, Any], name: str) -> str:
    """The day the lock under ``root`` validated ``name``'s layout, ``YYYY-MM-DD``.

    The latest ``validated_at`` among the combination records the lock wrote
    for the layout (``records/fleet/rigs/<rig>/<cmb>.json``, one per rig of
    the layout). ``root`` is a dev root or a promoted folder, and ``fleet``
    the loaded ``fleet.yaml`` the lock was written from — the dev setup's, or
    the folder's own — which names the layout's pins.
    """
    if name not in (fleet.get("fleets") or {}):
        raise PromoteRefusedError(f"{name} is not a fleet of the setup handed in")
    lock_path = root / LOCK_DIR / f"{name}.json"
    if not lock_path.is_file():
        raise PromoteRefusedError(f"{name} has no lock at {lock_path}")
    ids = _pinned(fleet, name, _read_json(lock_path), "the setup handed in")
    return _date_of(root, name, _records(ids))


def promote(dev_root: Path, setup: Path, name: str) -> Path:
    """Write ``<config folder>/fleets/<name>@<lock date>/`` from the dev lock;
    that folder.

    ``name`` is the plain fleet name; the date is the lock's
    (:func:`lock_date`), never today's. ``setup`` is the dev setup directory
    holding the ``fleet.yaml`` and ``policy.yaml`` the dev lock was written
    from. Refused, with nothing written, when ``name`` carries a tag, is not
    a fleet of that ``fleet.yaml``, has no dev lock, its layout no longer
    matches the dev lock, a combination record is missing or undated, the
    tagged folder already exists, or the folder would not load as a setup.
    """
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
    records = _records(ids)
    for record in records:
        if not (dev_root / record).is_file():
            raise PromoteRefusedError(
                f"{name}: the dev lock holds no combination record {record}"
            )
    folder = fleets_dir() / tagged(name, _date_of(dev_root, name, records))
    if folder.exists() or folder.is_symlink():
        raise PromoteRefusedError(
            f"{folder} already exists: a promoted fleet is a new folder, never "
            "written over or in place of another; a re-lock on a new date is a "
            "new folder"
        )

    block = fleets[name]
    layout = block.get("layout") or {}
    in_layout = {slot[0] for slots in layout.values() for slot in slots if slot}
    live_fleet_doc: dict[str, Any] = {
        "profile": "live",
        "units": {
            unit: copy.deepcopy(body)
            for unit, body in dev_fleet["units"].items()
            if unit in in_layout
        },
        "rigs": {
            rig: copy.deepcopy(body)
            for rig, body in (dev_fleet.get("rigs") or {}).items()
            if rig in layout
        },
        "fleets": {name: copy.deepcopy(block)},
    }
    policy = copy.deepcopy(dev_policy)
    policy["ladder"] = [
        unit for unit in dev_policy.get("ladder") or [] if unit in in_layout
    ]
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
    """Write ``files`` (path in the folder -> bytes) as ``folder``: built beside
    its place under the fleets directory and renamed into it, never over it."""
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
    """Why ``address`` is a machine of the user's rather than a hosted service,
    or ``None`` when it does not say so.

    Read from the address as written, and nothing is looked up: an IP address
    that is not public (loopback, private, link-local, shared, reserved), in
    any spelling a resolver reads as one (``inet_aton``'s octal, hexadecimal
    and short forms; an IPv4 address mapped into IPv6 or behind the NAT64
    prefix, judged as that IPv4 address), or a name only a local network
    answers (:data:`LOCAL_SUFFIXES`, ``localhost``, or a name with no dot). A
    public name that a local resolver points at a machine of the user's is not
    caught here: resolving would ask the network from an offline install, and
    the answer may differ at the run.
    """
    try:
        host = urlsplit(address).hostname
    except ValueError:
        host = None
    if not host:
        return "names no host"
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


def is_own(name: str) -> bool:
    """Whether the live name ``name`` is a folder :func:`approve_own` wrote."""
    layout = split_name(name)[0]
    if layout != OWN_FLEET:
        return False
    lock = fleets_dir() / name / LOCK_DIR / f"{OWN_FLEET}.json"
    try:
        return bool(_read_json(lock).get("approved_by") == OWN_APPROVER)
    except PromoteRefusedError:
        return False


def approve_own(setup: Path) -> Path:
    """Write ``<config folder>/fleets/own@<today>/`` from the setup ``mcgyvr
    init`` wrote at ``setup``; that folder.

    The user's own fleet, approved by the product itself and by no dev
    evidence: a stranger has none. Only a setup whose every unit is hosted is
    approved: on no ``rig``, at an address that is not a machine of the user's
    (:func:`on_a_users_machine`). Its fleet :data:`OWN_FLEET` lays out no rig,
    so live admission reads none, and a machine of the user's is approved only
    by a read of it, which ``init`` does not take. Its lock pins that empty
    layout and says who approved it; the date in the folder's name is the day
    of the approval, and a later folder of the same day is ``<date>-2``, then
    ``-3``. Refused, with nothing written, when the setup cannot be read, holds
    a unit on a rig or at a machine of the user's, already lays out rigs or
    fleets, names an mcorch orchestrator (whose units a fleet with no rig
    cannot hold awake), or would not load as a setup. It names nothing live:
    :func:`use` does that, as for any promoted folder.
    """
    fleet = _read_setup(setup / FLEET_FILENAME, load_fleet)
    policy = _read_setup(setup / POLICY_FILENAME, load_policy)
    units = fleet.get("units") or {}
    on_rigs = sorted(
        f"{unit} (on {body['rig']})" for unit, body in units.items() if "rig" in body
    )
    if on_rigs:
        raise PromoteRefusedError(
            f"{', '.join(on_rigs)} sits on a rig, and a machine is not approved "
            "for live work until it is read"
        )
    local = sorted(
        f"{unit} ({why})"
        for unit, body in units.items()
        if (why := on_a_users_machine(str(body.get("address") or ""))) is not None
    )
    if local:
        raise PromoteRefusedError(
            f"{', '.join(local)}: a hosted unit there is a machine of yours, and "
            "a machine is not approved for live work until it is read"
        )
    if fleet.get("rigs") or fleet.get("fleets"):
        raise PromoteRefusedError(
            f"{setup / FLEET_FILENAME} lays out rigs or fleets of its own; a "
            "fleet laid out on rigs is promoted from its lock"
        )
    try:
        mcorch_units(policy, {}, name=OWN_FLEET)
    except FleetError as exc:
        raise PromoteRefusedError(
            f"{exc}; a fleet that cannot serve its mcorch policy is not approved"
        ) from exc
    approved = datetime.now(UTC)
    own = {**fleet, "profile": "live", "fleets": {OWN_FLEET: {"layout": {}}}}
    lock = {
        "layout_sha256": layout_sha256({}),
        "next": [],
        "switches": [],
        "approved_by": OWN_APPROVER,
        "approved_at": approved.isoformat(timespec="seconds"),
    }
    fleet_text = yaml.safe_dump(own, sort_keys=False)
    policy_text = yaml.safe_dump(policy, sort_keys=False)
    try:
        parse(fleet_text, policy_text)
    except ConfigError as exc:
        raise PromoteRefusedError(
            f"{OWN_FLEET}: the live fleet folder would not load as a setup: {exc}"
        ) from exc
    _pinned(load_fleet(fleet_text), OWN_FLEET, lock, "the live fleet.yaml")
    day = approved.date().isoformat()
    folder = fleets_dir() / tagged(OWN_FLEET, day)
    later = 2
    while folder.exists() or folder.is_symlink():
        folder = fleets_dir() / tagged(OWN_FLEET, f"{day}-{later}")
        later += 1
    _build(
        folder,
        OWN_FLEET,
        {
            Path(FLEET_FILENAME): fleet_text.encode("utf-8"),
            Path(POLICY_FILENAME): policy_text.encode("utf-8"),
            LOCK_DIR / f"{OWN_FLEET}.json": (
                json.dumps(lock, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8"),
        },
    )
    return folder


@dataclass(frozen=True)
class Switch:
    """What ``use`` did: the pointer it wrote, and what the lock knows of the move."""

    #: the config folder's ``live.json``, as written.
    pointer: Path
    #: The live name now: ``<fleet>@<date>``, or a plain pre-ruling name.
    name: str
    #: The layout ``name`` is a promotion of.
    layout: str
    #: The live name before, ``None`` when no fleet was live.
    previous: str | None
    #: Whether the previous fleet's lock lists ``layout`` in its ``next``.
    locked: bool
    #: The lock's measured moves for a locked switch: one per rig, with
    #: ``downtime_s`` and ``wake_s`` as the lock recorded them.
    moves: list[dict[str, Any]] = field(default_factory=list)
    #: Why the move is unmeasured, when it is and a fleet was live.
    unmeasured: str | None = None
    #: The lock date of an untagged folder, ``None`` for a tagged one.
    untagged_date: str | None = None


def _measured(previous: str, layout: str) -> tuple[bool, list[dict[str, Any]], str]:
    """Whether ``previous``'s lock lists a switch to ``layout``; its moves, else why."""
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
    """Name ``name`` the fleet live runs, in the config folder's ``live.json``.

    Refused when ``<config folder>/fleets/<name>/`` does not exist or its layout no
    longer matches its own lock. Any other promoted folder may be named — a
    verified fleet is one the lock approved — and the :class:`Switch` says
    whether the move from the fleet that was live is one its lock measured.
    Nothing is started.
    """
    if not is_fleet_name(name):
        raise PromoteRefusedError(f"{name!r} cannot name a fleet folder")
    layout, tag = split_name(name)
    folder = fleets_dir() / name
    if not folder.is_dir():
        raise PromoteRefusedError(
            f"{name} has no live fleet folder {folder}: `mcgyvr fleet promote "
            f"{layout} --setup DIR` first"
        )
    fleet = _read_setup(folder / FLEET_FILENAME, load_fleet)
    if layout not in (fleet.get("fleets") or {}):
        raise PromoteRefusedError(f"{folder / FLEET_FILENAME} holds no fleet {layout}")
    lock = _read_json(folder / LOCK_DIR / f"{layout}.json")
    ids = _pinned(fleet, layout, lock, str(folder))
    untagged_date = None if tag is not None else _date_of(folder, layout, _records(ids))

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
        untagged_date=untagged_date,
    )


def _point(pointer: Path, name: str, since: str) -> None:
    staged = pointer.with_name(f".{pointer.name}.tmp")
    staged.write_text(
        json.dumps({"fleet": name, "since": since}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(staged, pointer)


def tag(name: str) -> Path:
    """Rename ``<config folder>/fleets/<name>/`` to ``<name>@<its lock date>/``;
    the folder.

    For a folder promoted before the ruling. A rename and nothing else: the
    files inside are what they were, and the config folder's ``live.json`` follows when
    it named the folder. Refused when ``name`` already carries a tag, has no
    folder, or the tagged name is taken.
    """
    if TAG in name:
        raise PromoteRefusedError(f"{name} already carries the date of its lock")
    if not is_fleet_name(name):
        raise PromoteRefusedError(f"{name!r} cannot name a fleet folder")
    folder = fleets_dir() / name
    if not folder.is_dir():
        raise PromoteRefusedError(f"{name} has no live fleet folder {folder}")
    fleet = _read_setup(folder / FLEET_FILENAME, load_fleet)
    target = fleets_dir() / tagged(name, lock_date(folder, fleet, name))
    if target.exists() or target.is_symlink():
        raise PromoteRefusedError(f"{target} already exists; {folder} is left as it is")
    try:
        current = live_fleet()
    except LiveFleetError as exc:
        raise PromoteRefusedError(str(exc)) from exc
    os.rename(folder, target)
    if current == name:
        # The same config under its dated name: `since` is kept.
        since = json.loads(live_file().read_text(encoding="utf-8")).get("since")
        _point(
            live_file(),
            target.name,
            str(since) if since else datetime.now(UTC).isoformat(timespec="seconds"),
        )
    return target
