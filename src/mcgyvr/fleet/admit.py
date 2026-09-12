"""Live admits only a locked fleet on its own rigs, and cleans what is not in it.

Live is production: mcgyvr delegating real code tasks. It runs a fleet the
operator picked from the locked set, and nothing else. ``admit_live`` checks the
lock, the pin, the rig and the holders of the card, and returns what to clean
and what to restore. ``wake`` finds the one listed switch that wakes a unit.
(``records/plans/fleet-identity.md`` §6.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.fleet.layout import combination_id, layout_sha256


class LiveRefusedError(Exception):
    """A live run was refused: not locked, not this rig, or the card is held."""


@dataclass
class Plan:
    """What live must do on a rig: clean units it does not name, restore its own."""

    clean: list[tuple[str, str]]
    restore: list[tuple[str, str, str]]


def _unit_ids(fleet: dict[str, Any]) -> dict[str, str]:
    return {
        name: unit["unit_id"]
        for name, unit in fleet.get("units", {}).items()
        if unit.get("unit_id") is not None
    }


def _layout_ids(fleet: dict[str, Any], layout: dict[str, Any]) -> dict[str, str]:
    """``rig id -> combination id``, the same spelling the lock pins."""
    rig_ids = {name: block["rig_id"] for name, block in fleet.get("rigs", {}).items()}
    unit_ids = _unit_ids(fleet)
    out: dict[str, str] = {}
    for rig_name, slots in layout.items():
        plain: list[Any] = []
        for slot in slots:
            if slot is None:
                plain.append(None)
                continue
            unit_name, state = slot
            plain.append((unit_ids[unit_name], state))
        rig_id = rig_ids[rig_name]
        out[rig_id] = combination_id(rig_id, plain)
    return out


def admit_live(
    root: Path,
    fleet: dict[str, Any],
    fleet_name: str | None,
    observed: dict[str, Any],
) -> Plan:
    """Refuse a live run the lock does not approve, else say what to do.

    ``observed`` maps each rig name to ``{rig_id, units: {unit id: state},
    foreign: [process]}`` — what is actually on the rig right now.
    """
    if fleet_name is None:
        raise LiveRefusedError("no fleet named for a live run")
    fleets = fleet.get("fleets", {})
    if fleet_name not in fleets:
        raise LiveRefusedError(f"{fleet_name} is not a fleet of this setup")

    lock_path = root / "records" / "fleet" / f"{fleet_name}.json"
    if not lock_path.is_file():
        raise LiveRefusedError(f"{fleet_name} has no lock in records/fleet/")
    lock_record = json.loads(lock_path.read_text(encoding="utf-8"))

    block = fleets[fleet_name]
    layout = block.get("layout", {})
    if layout_sha256(_layout_ids(fleet, layout)) != lock_record.get("layout_sha256"):
        raise LiveRefusedError(
            f"{fleet_name}: the layout no longer matches its pin — re-lock"
        )

    rig_ids = {name: block["rig_id"] for name, block in fleet.get("rigs", {}).items()}
    unit_ids = _unit_ids(fleet)

    clean: list[tuple[str, str]] = []
    restore: list[tuple[str, str, str]] = []
    for rig_name, slots in layout.items():
        obs = observed.get(rig_name) or {}
        obs_rig_id = obs.get("rig_id")
        if obs_rig_id is not None and obs_rig_id != rig_ids.get(rig_name):
            raise LiveRefusedError(
                f"{rig_name}: observed rig id {obs_rig_id} is not the locked "
                f"{rig_ids.get(rig_name)}"
            )
        foreign = obs.get("foreign") or []
        if foreign:
            raise LiveRefusedError(
                f"{rig_name}: a process that is not ours holds the rig: "
                f"{', '.join(foreign)}"
            )

        obs_units = obs.get("units") or {}
        fleet_unit_ids = {unit_ids[slot[0]] for slot in slots if slot is not None}
        for slot in slots:
            if slot is None:
                continue
            unit_name, state = slot
            unit_id = unit_ids[unit_name]
            if obs_units.get(unit_id) != state:
                restore.append((rig_name, unit_id, state))
        for unit_id in obs_units:
            if unit_id not in fleet_unit_ids:
                clean.append((rig_name, unit_id))

    return Plan(clean=clean, restore=restore)


def wake(
    root: Path,
    fleet: dict[str, Any],
    from_fleet: str,
    unit_name: str,
    spawn: Any,
) -> str:
    """Wake a unit along one listed switch, and say which fleet it leads to.

    ``spawn`` is called once with the door run, only for a switch ``from_fleet``
    lists toward a fleet where ``unit_name`` is awake.
    """
    fleets = fleet.get("fleets", {})
    if from_fleet not in fleets:
        raise LiveRefusedError(f"{from_fleet} is not a fleet of this setup")

    awake_in = [
        name
        for name, block in fleets.items()
        if any(
            slot is not None and slot[0] == unit_name and slot[1] == "awake"
            for slots in block.get("layout", {}).values()
            for slot in slots
        )
    ]

    for target in fleets[from_fleet].get("next", []):
        if target in awake_in:
            spawn(("serve", "up", from_fleet, target, unit_name))
            return str(target)

    raise LiveRefusedError(
        f"{from_fleet} lists no switch that wakes {unit_name}; it is awake only "
        f"in {', '.join(sorted(set(awake_in))) or 'no fleet'}"
    )


def host_is_locked(root: Path, host: str) -> bool:
    """Whether any committed combination record names ``host`` (a rig)."""
    rigs = root / "records" / "fleet" / "rigs"
    if not rigs.is_dir():
        return False
    for path in sorted(rigs.glob("*/cmb-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("rig") == host:
            return True
    return False
