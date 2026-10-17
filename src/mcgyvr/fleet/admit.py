""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.fleet.layout import (
    FleetError,
    combination_id,
    layout_sha256,
    mcorch_units,
)
from mcgyvr.fleet.roots import LOCK_DIR


class LiveRefusedError(Exception):
    ""


@dataclass
class Plan:
    ""

    clean: list[tuple[str, str]]
    restore: list[tuple[str, str, str]]


def _unit_ids(fleet: dict[str, Any]) -> dict[str, str]:
    return {
        name: unit["unit_id"]
        for name, unit in fleet.get("units", {}).items()
        if unit.get("unit_id") is not None
    }


def layout_ids(fleet: dict[str, Any], layout: dict[str, Any]) -> dict[str, str]:
    ""
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
    *,
    policy: Mapping[str, Any] | None = None,
) -> Plan:
    ""
    if fleet_name is None:
        raise LiveRefusedError("no fleet named for a live run")
    fleets = fleet.get("fleets", {})
    if fleet_name not in fleets:
        raise LiveRefusedError(f"{fleet_name} is not a fleet of this setup")

    lock_path = root / LOCK_DIR / f"{fleet_name}.json"
    if not lock_path.is_file():
        raise LiveRefusedError(f"{fleet_name} has no lock in its fleet folder")
    lock_record = json.loads(lock_path.read_text(encoding="utf-8"))

    block = fleets[fleet_name]
    layout = block.get("layout", {})
    if layout_sha256(layout_ids(fleet, layout)) != lock_record.get("layout_sha256"):
        raise LiveRefusedError(
            f"{fleet_name}: the layout no longer matches its pin — re-lock"
        )
    if policy is not None:
        try:
            mcorch_units(policy, layout, name=fleet_name)
        except FleetError as exc:
            raise LiveRefusedError(str(exc)) from exc

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
        unread = sorted(uid for uid, said in obs_units.items() if said == "unread")
        if unread:
            #
            #
            raise LiveRefusedError(
                f"{rig_name}: the sleep state of {', '.join(unread)} could not "
                "be read, so whether it would serve is unknown"
            )
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
    ""
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


def _pinned_rig_id(root: Path, host: str) -> str | None:
    ""
    import yaml

    try:
        given = yaml.safe_load((root / "fleet.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    rigs = given.get("rigs") if isinstance(given, dict) else None
    rig = rigs.get(host) if isinstance(rigs, dict) else None
    rig_id = rig.get("rig_id") if isinstance(rig, dict) else None
    return rig_id if isinstance(rig_id, str) and rig_id else None


def _unsampled_slots(root: Path, host: str) -> Iterator[tuple[str | None, bool]]:
    ""
    import yaml

    from mcgyvr.fleet.lock import approved_on_no_evidence, pinned_containers

    try:
        given = yaml.safe_load((root / "fleet.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return
    fleets = given.get("fleets") if isinstance(given, dict) else None
    if not isinstance(fleets, dict):
        return
    for name, block in fleets.items():
        layout = block.get("layout") if isinstance(block, dict) else None
        if not isinstance(layout, dict) or host not in layout:
            continue
        try:
            lock = json.loads(
                (root / LOCK_DIR / f"{name}.json").read_text(encoding="utf-8")
            )
            pinned = layout_sha256(layout_ids(given, layout))
            now = pinned_containers(given, {host: layout[host]})[host]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if not (
            isinstance(lock, dict)
            and approved_on_no_evidence(lock)
            and lock.get("layout_sha256") == pinned
        ):
            continue
        held = lock.get("containers")
        then = held.get(host) if isinstance(held, dict) else None
        then = then if isinstance(then, dict) else {}
        for slot in layout[host] or ():
            if not isinstance(slot, list | tuple) or not slot:
                continue
            unit = str(slot[0])
            yield now.get(unit), now.get(unit) == then.get(unit)


def _laid_out_unsampled(root: Path, host: str) -> bool:
    ""
    found = list(_unsampled_slots(root, host))
    return bool(found) and all(pinned for _container, pinned in found)


def unsampled_containers(root: Path, host: str) -> set[str]:
    ""
    return {
        container
        for container, pinned in _unsampled_slots(root, host)
        if pinned and container
    }


def host_is_locked(root: Path, host: str) -> bool:
    ""
    if _laid_out_unsampled(root, host):
        return True
    rigs = root / LOCK_DIR / "rigs"
    if not rigs.is_dir():
        return False
    pinned = _pinned_rig_id(root, host)
    paths = (rigs / pinned).glob("cmb-*.json") if pinned else rigs.glob("*/cmb-*.json")
    for path in sorted(paths):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and record.get("rig") == host:
            return True
    return False
