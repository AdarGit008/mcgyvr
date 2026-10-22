"""Whether a fleet may run live, and what a live run must do on its rigs first.

Live is production, so it is admitted only for a fleet the setup names and a
lock pins: :func:`admit_live` re-derives the layout's digest, refuses a layout
that left its pin, refuses a rig whose observed id is not the locked one,
refuses a rig a foreign process holds or whose units' sleep state could not be
read, and returns the units of ours to clean plus the fleet's own units to
restore. The remaining helpers answer the narrower question the live gate and
the waker ask of a lock with no sample behind it: which containers and which
host it covers.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.fleet.layout import combination_id, layout_sha256
from mcgyvr.fleet.roots import LOCK_DIR


class LiveRefusedError(Exception):
    """A live run is refused: the fleet, its lock, a rig, or a process on it says no."""


@dataclass
class Plan:
    """What a live run must do on the rigs before the fleet may serve.

    ``clean`` pairs a rig name with a unit id of ours that the fleet's layout
    does not place on that rig; ``restore`` triples a rig name with a unit id
    the layout does place there and the sleep state the layout gives it, for a
    unit found in some other state.
    """

    clean: list[tuple[str, str]]
    restore: list[tuple[str, str, str]]


def _unit_ids(fleet: dict[str, Any]) -> dict[str, str]:
    return {
        name: unit["unit_id"]
        for name, unit in fleet.get("units", {}).items()
        if unit.get("unit_id") is not None
    }


def layout_ids(fleet: dict[str, Any], layout: dict[str, Any]) -> dict[str, str]:
    """Map each rig id to the combination id of the slots the layout gives it.

    Slots are spelled with unit names in the setup and with unit ids here, so
    the digest follows the units rather than the names they happen to have;
    this map is what a lock pins as its ``layout_sha256``.
    """
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
    """Decide whether a live run of ``fleet_name`` is admitted, and what it must fix.

    Refuses when no fleet is named, when the name is not a fleet of this setup,
    when the fleet has no lock in ``root``, and when the layout no longer hashes
    to the ``layout_sha256`` its lock pinned. Then, for each rig of the layout,
    it refuses an observed rig id that is not the locked one, a rig a process
    that is not ours holds, and a unit whose sleep state was read as
    ``unread``, since whether it would serve is then unknown.

    ``observed`` is the door's reading keyed by rig name, each with ``rig_id``,
    a ``units`` map of unit id to state, and ``foreign`` process names. The
    returned plan lists the units of ours on a rig that this fleet does not
    place there as ``clean``, and this fleet's own units found in a state other
    than their locked one as ``restore``.
    """
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
            # Unread is neither of the two states a layout can lock, so no
            # restore can honestly promise to reach it: the rig is refused.
            # Nothing is planned for it, since a run never acts on a rig it
            # was not admitted on.
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


def _given(root: Path) -> Any:
    """``root``'s ``fleet.yaml`` read strictly, or None if it cannot be read.

    A strict refusal (a duplicate key) is a ``FleetFileError``, not a
    ``yaml.YAMLError``, so both are caught here: an unreadable file reads as no
    fleet, and every caller then fails closed.
    """
    from mcgyvr.fleet.files import FleetFileError, _yaml

    try:
        return _yaml((root / "fleet.yaml").read_text(encoding="utf-8"))
    except (OSError, FleetFileError):
        return None


def _pinned_rig_id(root: Path, host: str) -> str | None:
    """The rig id ``root``'s ``fleet.yaml`` pins for ``host``, or None if none."""
    given = _given(root)
    rigs = given.get("rigs") if isinstance(given, dict) else None
    rig = rigs.get(host) if isinstance(rigs, dict) else None
    rig_id = rig.get("rig_id") if isinstance(rig, dict) else None
    return rig_id if isinstance(rig_id, str) and rig_id else None


def _unsampled_slots(root: Path, host: str) -> Iterator[tuple[str | None, bool]]:
    """Yield ``(container, pinned)`` per slot ``host`` carries in an unsampled fleet.

    A fleet qualifies when its layout places units on ``host`` and its lock was
    approved on no evidence and still hashes to the layout's pin as the setup
    lays it out now. Each yielded entry is the container the setup gives that
    slot's unit, and whether it is the container the lock recorded for
    ``host``. A fleet, layout, or lock that cannot be read or resolved is
    skipped rather than refused.
    """
    from mcgyvr.fleet.lock import approved_on_no_evidence, pinned_containers

    given = _given(root)
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
    """True when each slot ``host`` carries in an unsampled locked fleet is pinned."""
    found = list(_unsampled_slots(root, host))
    return bool(found) and all(pinned for _container, pinned in found)


def unsampled_containers(root: Path, host: str) -> set[str]:
    """The containers a live lock with no sample pins on ``host``, as now laid out."""
    return {
        container
        for container, pinned in _unsampled_slots(root, host)
        if pinned and container
    }


def host_is_locked(root: Path, host: str) -> bool:
    """Whether a live fleet's lock covers ``host``.

    True when ``host`` carries slots only of fleets approved on no evidence,
    each still the container its lock recorded. Otherwise a combination record
    under the lock's ``rigs`` folder that names ``host`` as its rig, looked for
    under the rig id the setup pins for ``host`` when there is one and under
    every folder when there is not.
    """
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
