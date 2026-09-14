"""A dev lock becomes a live fleet by promotion: a new folder, never in place.

Owner, 2026-09-15: "stamped for live = another fleet setup available for live
(no overwrite, not in place of, new folder new files)"; "~/.mcgyvr/fleets/
<name>/   live can switch between fleets runtime".

:func:`promote` reads one fleet's dev lock from the dev root and writes
``~/.mcgyvr/fleets/<fleet>/`` — a setup of its own that ``mcgyvr config``
loads: ``fleet.yaml`` (profile live, that fleet's units, rigs and fleet
block), ``policy.yaml`` (the dev policy, its ladder filtered to those units)
and the fleet's lock under ``records/fleet/``. Every refusal is decided before
anything is written, the folder is built beside its place and renamed into
it, and an existing folder is never touched. :func:`use` names the fleet live
runs in ``~/.mcgyvr/live.json``. Nothing here writes the dev root.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.config import FLEET_FILENAME, POLICY_FILENAME, ConfigError, parse
from mcgyvr.fleet.admit import layout_ids
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import layout_sha256
from mcgyvr.fleet.roots import (
    LiveFleetError,
    fleets_dir,
    home,
    is_fleet_name,
    live_file,
    live_fleet,
)

#: Where a lock sits under the dev root and under a live fleet folder alike.
LOCK_DIR = Path("records") / "fleet"


class PromoteRefusedError(Exception):
    """A promotion or a live switch was refused, naming what is in the way."""


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


def promote(dev_root: Path, setup: Path, name: str) -> Path:
    """Write ``~/.mcgyvr/fleets/<name>/`` from the dev lock; the folder written.

    ``setup`` is the dev setup directory holding the ``fleet.yaml`` and
    ``policy.yaml`` the dev lock was written from. Refused, with nothing
    written, when the folder already exists, ``name`` is not a fleet of that
    ``fleet.yaml``, it has no dev lock, its layout no longer matches the dev
    lock, a combination record is missing, or the folder would not load as a
    setup.
    """
    if not is_fleet_name(name):
        raise PromoteRefusedError(f"{name!r} cannot name a fleet folder")
    folder = fleets_dir() / name
    if folder.exists() or folder.is_symlink():
        raise PromoteRefusedError(
            f"{folder} already exists: a promoted fleet is a new folder, never "
            "written over or in place of another"
        )

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

    records = [
        LOCK_DIR / "rigs" / rig / f"{cmb}.json" for rig, cmb in sorted(ids.items())
    ]
    for record in records:
        if not (dev_root / record).is_file():
            raise PromoteRefusedError(
                f"{name}: the dev lock holds no combination record {record}"
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


def use(name: str) -> Path:
    """Name ``name`` the fleet live runs, in ``~/.mcgyvr/live.json``; that file.

    Refused when ``~/.mcgyvr/fleets/<name>/`` does not exist or its layout no
    longer matches its own lock, and — once a fleet is live — when ``name`` is
    neither that fleet nor one its locked ``next`` lists.
    """
    if not is_fleet_name(name):
        raise PromoteRefusedError(f"{name!r} cannot name a fleet folder")
    folder = fleets_dir() / name
    if not folder.is_dir():
        raise PromoteRefusedError(
            f"{name} has no live fleet folder {folder}: `mcgyvr fleet promote "
            f"{name} --setup DIR` first"
        )
    fleet = _read_setup(folder / FLEET_FILENAME, load_fleet)
    if name not in (fleet.get("fleets") or {}):
        raise PromoteRefusedError(f"{folder / FLEET_FILENAME} holds no fleet {name}")
    _pinned(fleet, name, _read_json(folder / LOCK_DIR / f"{name}.json"), str(folder))

    try:
        current = live_fleet()
    except LiveFleetError as exc:
        raise PromoteRefusedError(str(exc)) from exc
    if current is not None and current != name:
        current_lock = fleets_dir() / current / LOCK_DIR / f"{current}.json"
        listed = _read_json(current_lock).get("next") or []
        if name not in listed:
            raise PromoteRefusedError(
                f"{current} is live and its lock lists no switch to {name}"
            )

    home().mkdir(parents=True, exist_ok=True)
    pointer = live_file()
    staged = pointer.with_name(f".{pointer.name}.tmp")
    staged.write_text(
        json.dumps(
            {"fleet": name, "since": datetime.now(UTC).isoformat(timespec="seconds")},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(staged, pointer)
    return pointer
