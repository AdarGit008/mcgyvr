"""A dev lock becomes a live one by promotion, and nothing flows back.

The dev lock is committed in the checkout under ``records/fleet/``; the live
lock sits under ``~/.mcgyvr`` beside the live ``config/fleet.yaml``
(:mod:`mcgyvr.fleet.roots`). :func:`promote` copies one fleet — its lock, the
combination records its layout names, and its units, rigs and fleet block —
from dev to live, and decides every refusal before it writes a byte.
:func:`use` names the promoted fleet live runs, and once one is live moves
only along its locked ``next``. Nothing here writes the dev root.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.fleet.admit import _layout_ids
from mcgyvr.fleet.files import FleetFileError, load_fleet
from mcgyvr.fleet.layout import layout_sha256

#: Where the live fleet file sits under the live root.
LIVE_FLEET_FILE = Path("config") / "fleet.yaml"
#: Where a lock sits under either root.
LOCK_DIR = Path("records") / "fleet"
#: The name of the fleet live runs, beside the live fleet locks. A fleet may
#: not be called ``live``, or its lock would be this file.
LIVE_NAME = "live"


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


def _pinned(
    fleet: dict[str, Any], name: str, lock: dict[str, Any], where: str
) -> dict[str, str]:
    """``rig id -> combination id`` for ``name``, refused unless it matches ``lock``."""
    layout = fleet["fleets"][name].get("layout", {})
    try:
        layout_ids = _layout_ids(fleet, layout)
    except KeyError as exc:
        raise PromoteRefusedError(
            f"{name}: the {where} fleet.yaml names {exc} in its layout but "
            "declares no id for it"
        ) from exc
    if layout_sha256(layout_ids) != lock.get("layout_sha256"):
        raise PromoteRefusedError(
            f"{name}: the {where} layout no longer matches its lock — re-lock "
            "from a passing dev run"
        )
    return layout_ids


def _live_fleet(live_root: Path) -> dict[str, Any] | None:
    path = live_root / LIVE_FLEET_FILE
    if not path.is_file():
        return None
    try:
        fleet = load_fleet(path.read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise PromoteRefusedError(f"{path} cannot be read: {exc}") from exc
    if fleet.get("profile") != "live":
        raise PromoteRefusedError(
            f"{path} says profile {fleet.get('profile')!r}; the live fleet file "
            "is profile live"
        )
    return fleet


def promote(
    dev_root: Path, dev_fleet: dict[str, Any], name: str, live_root: Path
) -> list[Path]:
    """Copy fleet ``name`` from the dev lock into the live root; the paths written.

    Refused, with nothing written, when ``name`` is not a fleet of
    ``dev_fleet``, has no dev lock, no longer matches its dev lock, names a
    combination the dev lock does not hold, or when the live fleet file holds
    a unit or rig of the same name with a different ``unit_id`` or ``rig_id``.
    """
    if name == LIVE_NAME:
        raise PromoteRefusedError(f"a fleet may not be called {LIVE_NAME!r}")
    fleets = dev_fleet.get("fleets", {})
    if name not in fleets:
        raise PromoteRefusedError(f"{name} is not a fleet of the dev fleet.yaml")

    lock_path = dev_root / LOCK_DIR / f"{name}.json"
    if not lock_path.is_file():
        raise PromoteRefusedError(
            f"{name} has no dev lock at {lock_path}: lock it from a passing dev "
            "run and commit it first"
        )
    layout_ids = _pinned(dev_fleet, name, _read_json(lock_path), "dev")

    combinations: list[Path] = []
    for rig_id, combination in sorted(layout_ids.items()):
        record = LOCK_DIR / "rigs" / rig_id / f"{combination}.json"
        if not (dev_root / record).is_file():
            raise PromoteRefusedError(
                f"{name}: the dev lock holds no combination record {record}"
            )
        combinations.append(record)

    layout = fleets[name].get("layout", {})
    unit_names = sorted(
        {slot[0] for slots in layout.values() for slot in slots if slot is not None}
    )
    rig_names = sorted(layout)
    live = _live_fleet(live_root) or {"profile": "live"}
    for block, names, key in (
        ("units", unit_names, "unit_id"),
        ("rigs", rig_names, "rig_id"),
    ):
        for item in names:
            ours = dev_fleet.get(block, {}).get(item, {}).get(key)
            theirs = (live.get(block) or {}).get(item)
            if theirs is not None and theirs.get(key) != ours:
                raise PromoteRefusedError(
                    f"{name}: live {block[:-1]} {item} is {theirs.get(key)}, not "
                    f"the dev {ours}; a live name is one identity"
                )

    merged: dict[str, Any] = {
        "profile": "live",
        "units": dict(live.get("units") or {}),
        "rigs": dict(live.get("rigs") or {}),
        "fleets": dict(live.get("fleets") or {}),
    }
    for item in unit_names:
        merged["units"][item] = copy.deepcopy(dev_fleet["units"][item])
    for item in rig_names:
        merged["rigs"][item] = copy.deepcopy(dev_fleet["rigs"][item])
    merged["fleets"][name] = copy.deepcopy(fleets[name])

    written: list[Path] = []
    for relative in (LOCK_DIR / f"{name}.json", *combinations):
        target = live_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((dev_root / relative).read_bytes())
        written.append(target)
    fleet_file = live_root / LIVE_FLEET_FILE
    fleet_file.parent.mkdir(parents=True, exist_ok=True)
    fleet_file.write_text(yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
    written.append(fleet_file)
    return written


def use(live_root: Path, name: str) -> Path:
    """Name ``name`` the fleet live runs; the file that says so.

    Refused when ``name`` was never promoted or its live layout no longer
    matches its live lock, and — once a fleet is live — when ``name`` is
    neither that fleet nor one its locked ``next`` lists.
    """
    lock_path = live_root / LOCK_DIR / f"{name}.json"
    live = _live_fleet(live_root)
    if (
        name == LIVE_NAME
        or live is None
        or name not in live.get("fleets", {})
        or not lock_path.is_file()
    ):
        raise PromoteRefusedError(
            f"{name} is not promoted: `mcgyvr fleet promote {name}` it first"
        )
    _pinned(live, name, _read_json(lock_path), "live")

    current_path = live_root / LOCK_DIR / f"{LIVE_NAME}.json"
    if current_path.is_file():
        current = _read_json(current_path).get("fleet")
        if isinstance(current, str) and current != name:
            listed = _read_json(live_root / LOCK_DIR / f"{current}.json").get(
                "next", []
            )
            if name not in listed:
                raise PromoteRefusedError(
                    f"{current} is live and lists no switch to {name}"
                )

    current_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.write_text(
        json.dumps(
            {"fleet": name, "since": datetime.now(UTC).isoformat(timespec="seconds")},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return current_path
