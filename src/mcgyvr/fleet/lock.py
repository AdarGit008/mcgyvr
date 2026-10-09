"""The fleet lock: what production may run, written only from passing dev runs.

``mcgyvr fleet lock`` writes two kinds of file (the lab's fleet-identity plan,
§4):

* one fleet lock file — the layout's sha256, the fleet's ``next`` list, and
  each switch's dev evidence;
* one combination record per rig — a combination's validation, shared by
  every fleet that lists it.

Committing them is the approval. Locking refuses, naming what failed, because a
lock that could not prove a fact must not pretend it did. Every check here is
arithmetic on the fleet file and the dev evidence; nothing reads a rig.

A unit that spans cards or rigs (:mod:`mcgyvr.fleet.spans`) is locked rig by
rig, as every unit is: its room on a rig is the sum of its shards' there, and a
layout that splits it is refused before anything is written. A rig whose dev
evidence states ``cards`` — each card's own MiB, beside ``card_mib`` — is held
to each card, and then every unit on it names its cards.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcgyvr.fleet import ids
from mcgyvr.fleet.layout import (
    FleetError,
    combination_id,
    layout_sha256,
    mcorch_units,
)
from mcgyvr.fleet.spans import (
    Span,
    SpanError,
    check_spans,
    room_on,
    shard_rooms,
    spans,
)
from mcgyvr.fleet.tolerance import tolerance_class


class LockRefusedError(Exception):
    """The lock cannot be written: a dev run did not prove what it must."""


def wake_limit_s(wake_s: float, tolerance: dict[str, Any]) -> float:
    """The validated wake plus the lock's tolerance."""
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


def _warm_decode_tolerance_pct(
    unit: dict[str, Any], tolerances: dict[str, Any]
) -> float | None:
    """The percent ``unit``'s warm decode may lose to NVMe, or ``None``.

    Read by the unit's tolerance class
    (:func:`mcgyvr.fleet.tolerance.tolerance_class`) from
    ``tolerances["warm_decode_class_pct"]``, the class a live probe is judged by
    too.
    """
    by_class = tolerances.get("warm_decode_class_pct")
    if not isinstance(by_class, dict):
        return None
    value = by_class.get(tolerance_class(unit))
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


def _card_figures(fleet_name: str, rig_name: str, raw: Any) -> dict[int, int]:
    """``gpu -> MiB`` from a rig's evidence ``cards``, refused unless every card
    is a whole index with a figure."""
    if not isinstance(raw, dict) or not raw:
        raise LockRefusedError(
            f"{fleet_name}: {rig_name} states `cards` in dev as {raw!r}; it is a "
            'mapping of card index to MiB, e.g. {"0": 12288}'
        )
    out: dict[int, int] = {}
    for key, figure in raw.items():
        text = str(key)
        if not text.isascii() or not text.isdigit():
            raise LockRefusedError(
                f"{fleet_name}: {rig_name} names card {key!r} in dev; a card is "
                "its index on the rig, a whole number from 0"
            )
        if not isinstance(figure, (int, float)) or isinstance(figure, bool):
            raise LockRefusedError(
                f"{fleet_name}: {rig_name} card {key} has no measured MiB in dev "
                f"({figure!r})"
            )
        out[int(text)] = int(figure)
    return out


def _unit_rooms(
    fleet_name: str,
    rig_name: str,
    slots: Any,
    units: dict[str, Any],
    found: dict[str, Span],
) -> dict[str, int]:
    """Each slot unit's room on ``rig_name``, MiB: a spanning unit's is the sum
    of its shards' there, any other unit's is its ``room_mib``."""
    rooms: dict[str, int] = {}
    for slot in slots:
        if slot is None:
            continue
        unit_name, _state = slot
        unit = units.get(unit_name)
        if unit is None:
            raise LockRefusedError(
                f"{fleet_name}: {unit_name} is not a unit of this fleet"
            )
        span = found.get(unit_name)
        if span is not None:
            try:
                rooms[unit_name] = room_on(unit_name, unit, span, rig_name)
            except SpanError as exc:
                raise LockRefusedError(f"{fleet_name}: {exc}") from exc
            continue
        room = unit.get("room_mib")
        if not isinstance(room, (int, float)) or isinstance(room, bool):
            raise LockRefusedError(
                f"{fleet_name}: {unit_name} has no room_mib to fit against its card"
            )
        rooms[unit_name] = int(room)
    return rooms


def _fit_cards(
    fleet_name: str,
    rig_name: str,
    slots: Any,
    units: dict[str, Any],
    found: dict[str, Span],
    figures: dict[int, int],
    overhead_mib: Any,
) -> None:
    """Hold each card of a rig to its own figure.

    Every unit in a slot names its cards through ``launch.shards`` (a one-entry
    list pins a single-card unit), because a rig of several cards has no one
    figure a unit's room can be added to. Each card's rooms, asleep units'
    included, plus the combination's overhead must fit that card.
    """
    used: dict[int, int] = {}
    for slot in slots:
        if slot is None:
            continue
        unit_name, _state = slot
        span = found.get(unit_name)
        if span is None:
            raise LockRefusedError(
                f"{fleet_name}: {unit_name} names no card in launch.shards, and "
                f"{rig_name}'s dev evidence states each card's MiB; name the "
                "card it occupies (a one-entry list pins a single-card unit)"
            )
        try:
            wanted = shard_rooms(unit_name, units[unit_name], span, rig_name)
        except SpanError as exc:
            raise LockRefusedError(f"{fleet_name}: {exc}") from exc
        for gpu, room in wanted.items():
            if gpu not in figures:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} occupies card {gpu} of "
                    f"{rig_name}, which its dev evidence states no MiB for"
                )
            used[gpu] = used.get(gpu, 0) + room
    for gpu, room_sum in sorted(used.items()):
        if room_sum + int(overhead_mib) > figures[gpu]:
            raise LockRefusedError(
                f"{fleet_name}: {rig_name} card {gpu} units' room {room_sum} MiB "
                f"plus overhead {overhead_mib} MiB exceeds the measured card "
                f"{figures[gpu]} MiB"
            )


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

    found = spans(fleet)
    card = (evidence.get("rigs") or {}).get(rig_name)
    card_figures = (
        _card_figures(fleet_name, rig_name, card["cards"])
        if card is not None and "cards" in card
        else None
    )
    if card is None or ("card_mib" not in card and card_figures is None):
        raise LockRefusedError(
            f"{fleet_name}: {rig_name} has no measured card_mib in dev"
        )
    card_mib = card.get("card_mib")

    if "overhead_mib" not in comb:
        raise LockRefusedError(
            f"{fleet_name}: the combination on {rig_name} has no measured overhead_mib"
        )
    overhead_mib = comb["overhead_mib"]

    rooms = _unit_rooms(fleet_name, rig_name, slots, units, found)
    if card_figures is not None:
        _fit_cards(
            fleet_name, rig_name, slots, units, found, card_figures, overhead_mib
        )
    else:
        room_sum = sum(rooms.values())
        if room_sum + int(overhead_mib) > int(card_mib):
            raise LockRefusedError(
                f"{fleet_name}: {rig_name} units' room {room_sum} MiB plus overhead "
                f"{overhead_mib} MiB exceeds the measured card {card_mib} MiB"
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

        # A unit that names its cards records the ones it holds on this rig, and
        # a unit that does not records nothing new.
        span = found.get(unit_name)
        if span is not None:
            entry["cards"] = {
                str(gpu): room
                for gpu, room in shard_rooms(unit_name, unit, span, rig_name).items()
            }
        # What a spanning unit's head measures is not measured on a worker.
        measured_here = span is None or span.head == rig_name

        # A live gate 1 matches the compose file's container names against the
        # lock offline, before any rig is read, so the lock records how each
        # unit is named on the daemon and reached on the wire.
        container = unit.get("container")
        if isinstance(container, str) and container:
            entry["container"] = container
        address = unit.get("address")
        if isinstance(address, str) and address:
            entry["address"] = address

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
            room = rooms[unit_name]
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
            if warm is None and measured_here:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} has no warm_decode_tok_s in its "
                    "dev validation"
                )
            if warm is not None:
                entry["warm_decode_tok_s"] = warm

            prefill = (comb.get("prefill_tok_s") or {}).get(unit_name)
            if prefill is None and measured_here:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} has no prefill_tok_s in its dev "
                    "validation"
                )
            if prefill is not None:
                entry["prefill_tok_s"] = prefill

            output_tokens = unit.get("output_tokens")
            request_timeout_s = unit.get("request_timeout_s")
            if (output_tokens is None or request_timeout_s is None) and measured_here:
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} states no output_tokens or "
                    "request_timeout_s"
                )
            if (
                warm is not None
                and output_tokens is not None
                and request_timeout_s is not None
                and float(output_tokens) / float(warm) > float(request_timeout_s)
            ):
                raise LockRefusedError(
                    f"{fleet_name}: {unit_name} reply of {output_tokens} tokens "
                    f"at {warm} tok/s cannot finish inside request_timeout_s "
                    f"{request_timeout_s}s"
                )

            baselines = comb.get("baseline_tok_s") or {}
            if unit_name in baselines and warm is not None:
                baseline = baselines[unit_name]
                if baseline is None:
                    entry["nvme"] = "no baseline: NVMe required"
                else:
                    entry["baseline_tok_s"] = baseline
                    pct = _warm_decode_tolerance_pct(unit, tolerances)
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
        "overhead_mib": overhead_mib,
        "restarts": dict(restarts),
        "approved": approved,
        "validated_at": comb.get("validated_at"),
        "envelope": comb.get("envelope"),
    }
    if card_figures is not None:
        record["cards"] = {str(gpu): mib for gpu, mib in sorted(card_figures.items())}
        if card_mib is None:
            del record["card_mib"]
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

    ``root`` is the dev root the lock tree is written under — the checkout,
    where committing the lock is the approval. A live lock is never written
    here: ``mcgyvr fleet promote`` copies it (:mod:`mcgyvr.fleet.promote`).
    """
    units = fleet.get("units", {})
    fleets = fleet.get("fleets", {})

    if policy is not None:
        for name in policy.get("ladder", []):
            if name not in units:
                raise LockRefusedError(
                    f"policy ladder names {name!r}, a unit this fleet does not have"
                )
        # An mcorch policy needs its agent and its jev unit awake in every
        # fleet it may run on, so a fleet that lacks either is not locked.
        try:
            for fleet_name, block in fleets.items():
                mcorch_units(policy, block.get("layout", {}), name=fleet_name)
        except FleetError as exc:
            raise LockRefusedError(str(exc)) from exc

    # A unit's span is declared, and a layout holds it whole, before anything
    # is written: a unit split across a fleet's rigs is refused by name.
    try:
        spans(fleet)
        for fleet_name, block in fleets.items():
            check_spans(fleet, block.get("layout", {}), name=fleet_name)
    except SpanError as exc:
        raise LockRefusedError(str(exc)) from exc

    # A rig is named by the snapshot it prints (owner, 2026-09-15, D1). A dev
    # run that filed its rig's reading beside the card proves which rig it ran
    # on, so a pinned id that reading does not name is refused. Evidence that
    # carries no reading locks against the pinned id as before.
    for rig_name, block in (fleet.get("rigs") or {}).items():
        snapshot = ((evidence.get("rigs") or {}).get(rig_name) or {}).get("snapshot")
        if snapshot is None:
            continue
        try:
            named = ids.rig_id(snapshot)
        except ValueError as exc:
            raise LockRefusedError(f"{rig_name}: {exc}") from exc
        pinned = block.get("rig_id")
        if pinned != named:
            raise LockRefusedError(
                f"{rig_name}: fleet.yaml pins {pinned}, and its dev run's snapshot "
                f"names {named}. Pin the id the rig's snapshot names "
                "(mcgyvr.fleet.ids.rig_id), or re-read the rig"
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
