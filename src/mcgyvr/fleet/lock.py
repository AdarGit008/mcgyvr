"""The fleet lock: what production may run, written only from passing dev runs.

``mcgyvr fleet lock`` writes two kinds of file (``records/plans/fleet-identity.md``
§4):

* ``records/fleet/<fleet>.json`` — the layout's sha256, the fleet's ``next``
  list, and each switch's dev evidence;
* ``records/fleet/rigs/<rig->/<cmb->.json`` — one combination's validation,
  shared by every fleet that lists it.

Committing them is the approval. Locking refuses, naming what failed, because a
lock that could not prove a fact must not pretend it did. Every check here is
arithmetic on the fleet file and the dev evidence; nothing reads a rig.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcgyvr.fleet.layout import combination_id, layout_sha256


class LockRefusedError(Exception):
    """The lock cannot be written: a dev run did not prove what it must."""


def wake_limit_s(wake_s: float, tolerance: dict[str, Any]) -> float:
    """The Waker's wait limit: the validated wake plus the lock's tolerance."""
    return wake_s + float(tolerance["s"])


def _slots_key(slots: Any) -> tuple[Any, ...]:
    """A hashable spelling of a slot list, preserving slot position."""
    return tuple(tuple(slot) if slot is not None else None for slot in slots)


def _switch_moves(
    before: dict[str, Any], after: dict[str, Any]
) -> list[tuple[str, Any, Any]]:
    """The per-rig moves of one switch, as (rig, from slots, to slots)."""
    moves: list[tuple[str, Any, Any]] = []
    for rig in sorted(set(before) | set(after)):
        from_slots = before.get(rig, [])
        to_slots = after.get(rig, [])
        if from_slots != to_slots:
            moves.append((rig, from_slots, to_slots))
    return moves


def _warm_decode_tolerance_pct(engine: Any, tolerances: dict[str, Any]) -> float | None:
    """The percentage a unit's warm decode may lose to NVMe, or ``None``."""
    by_engine = tolerances.get("warm_decode_pct")
    if not isinstance(by_engine, dict):
        return None
    value = by_engine.get(engine)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _combination_id_for(
    rig_ids: dict[str, Any],
    unit_ids: dict[str, Any],
    rig_name: str,
    slots: Any,
) -> str:
    """``cmb-`` for one rig's slots, named by rig id and unit id."""
    plain: list[Any] = []
    for slot in slots:
        if slot is None:
            plain.append(None)
            continue
        unit_name, state = slot
        plain.append((unit_ids[unit_name], state))
    return combination_id(rig_ids[rig_name], plain)


def _combination_record(
    fleet_name: str,
    fleet: dict[str, Any],
    evidence: dict[str, Any],
    rig_name: str,
    slots: Any,
    comb: dict[str, Any],
    tolerances: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Validate one combination and return ``(combination id, record)``."""
    units = fleet.get("units", {})
    rig_ids = {name: block["rig_id"] for name, block in fleet.get("rigs", {}).items()}
    unit_ids = {
        name: unit["unit_id"]
        for name, unit in units.items()
        if unit.get("unit_id") is not None
    }

    card = (evidence.get("rigs") or {}).get(rig_name)
    if card is None or "card_mib" not in card:
        raise LockRefusedError(
            f"{fleet_name}: {rig_name} has no measured card_mib in dev"
        )
    card_mib = card["card_mib"]

    if "headroom_mib" not in comb:
        raise LockRefusedError(
            f"{fleet_name}: the combination on {rig_name} has no measured headroom_mib"
        )
    headroom_mib = comb["headroom_mib"]

    room_sum = 0
    for slot in slots:
        if slot is None:
            continue
        unit_name, _state = slot
        unit = units.get(unit_name)
        if unit is None:
            raise LockRefusedError(
                f"{fleet_name}: {unit_name} is not a unit of this fleet"
            )
        room = unit.get("room_mib")
        if not isinstance(room, (int, float)) or isinstance(room, bool):
            raise LockRefusedError(
                f"{fleet_name}: {unit_name} has no room_mib to fit against its card"
            )
        room_sum += int(room)

    if room_sum + int(headroom_mib) > int(card_mib):
        raise LockRefusedError(
            f"{fleet_name}: {rig_name} units' room {room_sum} MiB plus headroom "
            f"{headroom_mib} MiB exceeds the measured card {card_mib} MiB"
        )

    approved: dict[str, Any] = {}
    restarts = comb.get("restarts") or {}
    for slot in slots:
        if slot is None:
            continue
        unit_name, state = slot
        unit = units[unit_name]
        engine = unit.get("engine")

        restarts_for_unit = restarts.get(unit_name, 0)
        if restarts_for_unit and int(restarts_for_unit) > 0:
            raise LockRefusedError(
                f"{fleet_name}: {unit_name} has restarts ({restarts_for_unit}) "
                "in its dev validation"
            )

        entry: dict[str, Any] = {}
        if engine is not None:
            entry["engine"] = engine

        if engine == "vllm":
            if "kv_cache_memory_bytes" not in unit:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} is vLLM and does not pin "
                    "kv_cache_memory_bytes"
                )
            entry["kv_cache_memory_bytes"] = unit["kv_cache_memory_bytes"]
            if "attention_backend" not in unit:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} is vLLM and does not pin "
                    "attention_backend"
                )
            reported = (comb.get("attention_backend") or {}).get(unit_name)
            if reported is None:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} reported no attention_backend "
                    "in its dev validation"
                )
            if reported != unit["attention_backend"]:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} reported attention backend "
                    f"{reported!r}, not the pinned {unit['attention_backend']!r}"
                )
            entry["attention_backend"] = reported
        elif engine == "llama.cpp":
            peaks = comb.get("card_peak_mib") or {}
            if unit_name not in peaks:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} has no measured card_peak_mib"
                )
            peak = peaks[unit_name]
            room = unit.get("room_mib")
            if int(peak) > int(room):
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} card peak {peak} MiB exceeds its "
                    f"room {room} MiB"
                )
            entry["card_peak_mib"] = peak
            steady = (comb.get("card_steady_mib") or {}).get(unit_name)
            if steady is not None:
                entry["card_steady_mib"] = steady

        if state == "awake":
            warm = (comb.get("warm_decode_tok_s") or {}).get(unit_name)
            if warm is None:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} has no warm_decode_tok_s in its "
                    "dev validation"
                )
            entry["warm_decode_tok_s"] = warm

            prefill = (comb.get("prefill_tok_s") or {}).get(unit_name)
            if prefill is None:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} has no prefill_tok_s in its dev "
                    "validation"
                )
            entry["prefill_tok_s"] = prefill

            output_tokens = unit.get("output_tokens")
            request_timeout_s = unit.get("request_timeout_s")
            if output_tokens is None or request_timeout_s is None:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} states no output_tokens or "
                    "request_timeout_s"
                )
            if float(output_tokens) / float(warm) > float(request_timeout_s):
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} reply of {output_tokens} tokens "
                    f"at {warm} tok/s cannot finish inside request_timeout_s "
                    f"{request_timeout_s}s"
                )

            baselines = comb.get("baseline_tok_s") or {}
            if unit_name in baselines:
                baseline = baselines[unit_name]
                if baseline is None:
                    entry["nvme"] = "no baseline: NVMe required"
                else:
                    entry["baseline_tok_s"] = baseline
                    pct = _warm_decode_tolerance_pct(engine, tolerances)
                    if pct is not None and float(warm) < float(baseline):
                        slowdown = (float(baseline) - float(warm)) / float(baseline)
                        if slowdown > pct / 100.0:
                            raise LockRefusedError(
                                f"{fleet_name}: {unit_name} warm decode {warm} "
                                f"tok/s costs {slowdown * 100.0:.1f}% against its "
                                f"no-NVMe baseline {baseline} tok/s"
                            )

        approved[unit_name] = entry

    combination = _combination_id_for(rig_ids, unit_ids, rig_name, slots)
    record: dict[str, Any] = {
        "rig": rig_name,
        "card_mib": card_mib,
        "headroom_mib": headroom_mib,
        "restarts": dict(restarts),
        "approved": approved,
        "validated_at": comb.get("validated_at"),
        "envelope": comb.get("envelope"),
    }
    return combination, record


def write(
    root: Path,
    fleet: dict[str, Any],
    evidence: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    tolerances: dict[str, Any],
) -> None:
    """Write the fleet lock from passing dev runs, refusing what it cannot pin.

    ``root`` is the repository the ``records/fleet/`` tree is written under.
    """
    units = fleet.get("units", {})
    fleets = fleet.get("fleets", {})

    if policy is not None:
        for name in policy.get("ladder", []):
            if name not in units:
                raise LockRefusedError(
                    f"policy ladder names {name!r}, a unit this fleet does not have"
                )

    rig_addresses = {
        unit.get("address")
        for name, unit in units.items()
        if "rig" in unit and unit.get("address") is not None
    }
    for _name, unit in units.items():
        if "rig" not in unit:
            address = unit.get("address")
            if address is not None and address in rig_addresses:
                raise LockRefusedError(
                    f"an outside unit answers at a rig unit's address {address!r}"
                )

    combinations = evidence.get("combinations", [])
    moves = evidence.get("moves", [])
    comb_by_key = {
        (comb.get("rig"), _slots_key(comb.get("slots", []))): comb
        for comb in combinations
    }
    move_by_key = {
        (
            move.get("rig"),
            _slots_key(move.get("from", [])),
            _slots_key(move.get("to", [])),
        ): move
        for move in moves
    }

    fleet_switches: dict[str, Any] = {}
    written: dict[str, dict[str, Any]] = {}
    for fleet_name, block in fleets.items():
        layout = block.get("layout", {})
        next_list = block.get("next", [])

        switches: list[dict[str, Any]] = []
        for target in next_list:
            target_block = fleets.get(target)
            if target_block is None:
                raise LockRefusedError(
                    f"{fleet_name}: switch to {target}, which is not a fleet"
                )
            switch_moves: list[dict[str, Any]] = []
            for rig_name, from_slots, to_slots in _switch_moves(
                layout, target_block.get("layout", {})
            ):
                move = move_by_key.get(
                    (rig_name, _slots_key(from_slots), _slots_key(to_slots))
                )
                if move is None:
                    raise LockRefusedError(
                        f"{fleet_name} → {target}: the rig move on {rig_name} "
                        "never ran in dev"
                    )
                if not move.get("passed", False):
                    raise LockRefusedError(
                        f"{fleet_name} → {target}: the rig move on {rig_name} "
                        "did not pass in dev"
                    )
                if "downtime_s" not in move:
                    raise LockRefusedError(
                        f"{fleet_name} → {target}: the rig move on {rig_name} "
                        "recorded no downtime_s"
                    )
                if "wake_s" not in move:
                    raise LockRefusedError(
                        f"{fleet_name} → {target}: the rig move on {rig_name} "
                        "recorded no wake_s"
                    )
                switch_moves.append(
                    {
                        "rig": rig_name,
                        "downtime_s": move.get("downtime_s"),
                        "wake_s": move.get("wake_s"),
                    }
                )
            switches.append({"to": target, "moves": switch_moves})
        fleet_switches[fleet_name] = switches

        for rig_name, slots in layout.items():
            comb = comb_by_key.get((rig_name, _slots_key(slots)))
            if comb is None:
                raise LockRefusedError(
                    f"{fleet_name}: the combination on {rig_name} has no dev run"
                )
            if not comb.get("passed", False):
                raise LockRefusedError(
                    f"{fleet_name}: the combination on {rig_name} did not pass "
                    "its dev run"
                )
            combination, record = _combination_record(
                fleet_name, fleet, evidence, rig_name, slots, comb, tolerances
            )
            written.setdefault(combination, record)

    fleet_dir = root / "records" / "fleet"
    fleet_dir.mkdir(parents=True, exist_ok=True)
    rig_ids = {name: block["rig_id"] for name, block in fleet.get("rigs", {}).items()}
    unit_ids = {
        name: unit["unit_id"]
        for name, unit in units.items()
        if unit.get("unit_id") is not None
    }

    for fleet_name, block in fleets.items():
        layout = block.get("layout", {})
        layout_ids = {
            rig_ids[rig_name]: _combination_id_for(rig_ids, unit_ids, rig_name, slots)
            for rig_name, slots in layout.items()
        }
        record = {
            "layout_sha256": layout_sha256(layout_ids),
            "next": list(block.get("next", [])),
            "switches": fleet_switches[fleet_name],
        }
        path = fleet_dir / f"{fleet_name}.json"
        path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    for combination, record in written.items():
        rig_name = record["rig"]
        rig_id = rig_ids[rig_name]
        rig_dir = root / "records" / "fleet" / "rigs" / rig_id
        rig_dir.mkdir(parents=True, exist_ok=True)
        (rig_dir / f"{combination}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
