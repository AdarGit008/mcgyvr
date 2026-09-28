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

:func:`use` names the fleet live runs in ``~/.mcgyvr/live.json``: any
promoted folder whose layout still matches its own lock. It says whether the
move from the fleet that was live is one that fleet's lock measured
(:class:`Switch`), and starts nothing. Nothing here writes the dev root.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.config import FLEET_FILENAME, POLICY_FILENAME, ConfigError, parse
from mcgyvr.fleet.admit import layout_ids
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import layout_sha256
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

#: Where a lock sits under the dev root and under a live fleet folder alike.
LOCK_DIR = Path("records") / "fleet"


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
    """Write ``~/.mcgyvr/fleets/<name>@<lock date>/`` from the dev lock; that folder.

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

    fleets_dir().mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=fleets_dir()))
    try:
        (staging / FLEET_FILENAME).write_text(fleet_text, encoding="utf-8")
        (staging / POLICY_FILENAME).write_text(policy_text, encoding="utf-8")
        for relative in (LOCK_DIR / f"{name}.json", *records):
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((dev_root / relative).read_bytes())
        if folder.exists() or folder.is_symlink():
            raise PromoteRefusedError(
                f"{folder} appeared while it was being built; it is left as it is"
            )
        os.rename(staging, folder)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return folder


@dataclass(frozen=True)
class Switch:
    """What ``use`` did: the pointer it wrote, and what the lock knows of the move."""

    #: ``~/.mcgyvr/live.json``, as written.
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
    """Name ``name`` the fleet live runs, in ``~/.mcgyvr/live.json``.

    Refused when ``~/.mcgyvr/fleets/<name>/`` does not exist or its layout no
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
    """Rename ``~/.mcgyvr/fleets/<name>/`` to ``<name>@<its lock date>/``; the folder.

    For a folder promoted before the ruling. A rename and nothing else: the
    files inside are what they were, and ``~/.mcgyvr/live.json`` follows when
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
