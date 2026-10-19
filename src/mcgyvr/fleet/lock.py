"""Writes a fleet's lock from dev evidence, and reads what a lock pins.

A fleet folder's `lock/` holds two kinds of file:

* `lock/<fleet>.json` holds the fleet's layout sha256, its `next` list, for
  each switch it lists the rig moves that switch makes, and, when the fleet
  lays out a sleeper, its `swaps`: the move each way of each sleeper's swap;
* `lock/rigs/<rig_id>/<combination>.json` holds one rig combination's
  validation, which every fleet that lays that combination out shares.

Nothing is locked on a claim. :func:`write` refuses, naming the fleet, unless a
fleet's combination passed a dev run, every rig move a listed switch makes and
every sleeper's swap both ways ran and recorded its downtime and wake times,
each rig's dev read names the rig id the fleet pins, and the combination's own
measured figures hold: overhead plus every unit's room inside its card, a vLLM
unit's pinned KV size and reported attention backend, a llama.cpp unit's
measured card peak, a reply that finishes inside its request timeout at its
validated warm decode, and NVMe use that holds against its no-NVMe baseline. A
setup that no sample could run on is locked by :func:`write_unsampled` instead,
on no evidence, approved by the product itself.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.config import FLEET_FILENAME, POLICY_FILENAME, ConfigError, parse
from mcgyvr.fleet import ids
from mcgyvr.fleet.admit import layout_ids
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import (
    FleetError,
    combination_id,
    layout_sha256,
    mcorch_units,
)

# Re-exported: the folder a fleet's lock files sit in, which the modules that
# promote and admit a fleet import from here.
from mcgyvr.fleet.roots import LOCK_DIR as LOCK_DIR
from mcgyvr.fleet.roots import fleets_dir, split_name
from mcgyvr.fleet.sample import WAY_IN, WAYS, sleeper
from mcgyvr.fleet.spans import (
    Span,
    SpanError,
    check_spans,
    room_on,
    shard_rooms,
    spans,
)
from mcgyvr.fleet.tolerance import tolerance_class

#: The fleet a setup no dev sample ran on is locked under: the user's own read
#: rigs laid out awake, beside the hosted units the setup also carries.
OWN_FLEET = "own"
#: The command recorded as the approver when a setup is locked on no evidence.
OWN_APPROVER = "mcgyvr setup"
#: The commands whose word approves a lock with no dev run behind it: `mcgyvr
#: setup` writes one today, and `mcgyvr init` wrote one before it was renamed, so
#: a lock either way is the user's own fleet.
OWN_APPROVERS = frozenset({OWN_APPROVER, "mcgyvr init"})


class LockRefusedError(Exception):
    """A fleet or combination is not locked; the message names what failed."""


def tolerances() -> dict[str, Any]:
    """The warm decode tolerance of each unit class, in percent, under
    `warm_decode_class_pct`.
    """
    from mcgyvr.derived import class_tolerances

    return {"warm_decode_class_pct": class_tolerances()["warm_decode_tok_s"]}


def wake_limit_s(wake_s: float, tolerance: dict[str, Any]) -> float:
    """A wake's wall time limit: its validated wake plus the tolerance in seconds."""
    return wake_s + float(tolerance["s"])


def _slots_key(slots: Any) -> tuple[Any, ...]:
    """Slots as tuple keys, so a combination or a rig move can be looked up by
    the slots it ran.
    """
    return tuple(tuple(slot) if slot is not None else None for slot in slots)


def _switch_moves(
    before: dict[str, Any], after: dict[str, Any]
) -> list[tuple[str, Any, Any]]:
    """The rig moves between two layouts: for each rig whose slots differ, the rig
    and its slots before and after, in rig order.
    """
    moves: list[tuple[str, Any, Any]] = []
    for rig in sorted(set(before) | set(after)):
        from_slots = before.get(rig, [])
        to_slots = after.get(rig, [])
        if from_slots != to_slots:
            moves.append((rig, from_slots, to_slots))
    return moves


def _swap_move(
    moves: list[Any], rig: str, unit: str, way: str, slots: Any
) -> dict[str, Any] | None:
    """The newest dev move of one way of `unit`'s swap on `rig`, or None.

    The way in starts from the fleet's own slots on the rig and the way back
    returns to them, which is how a move is told to be this fleet's.
    """
    side = "from" if way == WAY_IN else "to"
    found: dict[str, Any] | None = None
    for move in moves:
        if (
            isinstance(move, dict)
            and (move.get("rig"), move.get("unit"), move.get("way")) == (rig, unit, way)
            and _slots_key(move.get(side, [])) == _slots_key(slots)
        ):
            found = move
    return found


def _swaps(
    fleet_name: str, layout: dict[str, Any], units: dict[str, Any], moves: list[Any]
) -> list[dict[str, Any]]:
    """The moves of every sleeper's swap the fleet lays out, each way in turn.

    A sleeper is a unit laid out asleep whose role is `sleeps-until-needed`.
    Each way must have run in dev, passed and recorded its downtime and wake
    times, as a switch's rig move must; each is kept as its rig, unit and way
    with those times.
    """
    swaps: list[dict[str, Any]] = []
    for rig_name, slots in layout.items():
        for slot in slots or ():
            if slot is None or not sleeper(units.get(slot[0]) or {}, slot[1]):
                continue
            unit_name = slot[0]
            for way in WAYS:
                where = f"{fleet_name}: the swap of {unit_name} on {rig_name}, {way},"
                move = _swap_move(moves, rig_name, unit_name, way, slots)
                if move is None:
                    raise LockRefusedError(f"{where} never ran in dev")
                if not move.get("passed", False):
                    raise LockRefusedError(f"{where} did not pass in dev")
                for figure in ("downtime_s", "wake_s"):
                    if figure not in move:
                        raise LockRefusedError(f"{where} recorded no {figure}")
                swaps.append(
                    {
                        "rig": rig_name,
                        "unit": unit_name,
                        "way": way,
                        "downtime_s": move.get("downtime_s"),
                        "wake_s": move.get("wake_s"),
                    }
                )
    return swaps


def _warm_decode_tolerance_pct(
    unit: dict[str, Any], tolerances: dict[str, Any]
) -> float | None:
    """The unit's class tolerance in percent, or None when the lock states none
    for its class.
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
    """The combination id of one rig's slots, hashed over the rig and unit ids the
    fleet pins rather than the names it spells.
    """
    plain: list[Any] = []
    for slot in slots:
        if slot is None:
            plain.append(None)
            continue
        unit_name, state = slot
        plain.append((unit_ids[unit_name], state))
    return combination_id(rig_ids[rig_name], plain)


def _card_figures(fleet_name: str, rig_name: str, raw: Any) -> dict[int, int]:
    """The rig's measured MiB per card, keyed by card index, from a dev reading
    that states its cards one by one.
    """
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
    """Each unit's room on this rig: its shards' rooms summed where it declares
    shards, else its stated `room_mib`; an asleep unit keeps its room.
    """
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
    """Refuse unless each card holds the room of the units' shards on it plus the
    combination's overhead.
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
    """The combination id and the record the lock keeps for one rig's slots: what
    the dev run validated, checked against the fleet and the measured card.
    """
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

        # A unit that declares shards is pinned card by card: the room each of its
        # shards needs on this rig, so a live run can check what it sits on.
        span = found.get(unit_name)
        if span is not None:
            entry["cards"] = {
                str(gpu): room
                for gpu, room in shard_rooms(unit_name, unit, span, rig_name).items()
            }
        # A spanning unit is measured on its head rig, so a worker slot needs none.
        measured_here = span is None or span.head == rig_name

        # The container the unit runs in, and the address it answered on when
        # its combination was validated, recorded with the unit so a rewired or
        # re-imaged unit is not read as the one that passed.
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
    """
    Lock one setup's fleets from the dev evidence its sample recorded.

    Refuses, naming the fleet, unless every combination a fleet lays out passed
    a dev run, every rig move a listed switch makes and every way of every
    sleeper's swap ran and recorded its downtime and wake times, each rig's
    dev read names the rig id the fleet pins, no outside unit answers at a rig
    unit's address, the policy ladder names only units the fleet has, every
    fleet serves the policy's mcorch units, and every spanning unit holds a
    room slot in one state on each rig it spans. Then writes each fleet's
    `lock/<fleet>.json` and one `lock/rigs/<rig_id>/<combination>.json` per
    combination, a combination two fleets lay out being written once.
    """
    units = fleet.get("units", {})
    fleets = fleet.get("fleets", {})

    if policy is not None:
        for name in policy.get("ladder", []):
            if name not in units:
                raise LockRefusedError(
                    f"policy ladder names {name!r}, a unit this fleet does not have"
                )
        # A fleet that serves an mcorch policy with no orchestrator or jev unit
        # awake is not locked: no run could start on it.
        try:
            for fleet_name, block in fleets.items():
                mcorch_units(policy, block.get("layout", {}), name=fleet_name)
        except FleetError as exc:
            raise LockRefusedError(str(exc)) from exc

    # Every unit's shards must make one whole span, and a unit that spans rigs
    # must hold a room slot in the same state on each of them.
    try:
        spans(fleet)
        for fleet_name, block in fleets.items():
            check_spans(fleet, block.get("layout", {}), name=fleet_name)
    except SpanError as exc:
        raise LockRefusedError(str(exc)) from exc

    # The rig id a fleet pins is the id a live read knows the machine by, so it
    # must be the id the rig's own dev reading names; a lock that pinned another
    # would admit the wrong machine, or none. A rig no dev run read passes here,
    # and a fleet that lays one out is refused below for having no dev run.
    for rig_name, block in (fleet.get("rigs") or {}).items():
        named = ((evidence.get("rigs") or {}).get(rig_name) or {}).get("rig_id")
        if named is None:
            continue
        pinned = block.get("rig_id")
        if pinned != named:
            raise LockRefusedError(
                f"{rig_name}: fleet.yaml pins {pinned}, and its dev run's read "
                f"names {named}. Pin the id the rig's reading names "
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
    fleet_swaps: dict[str, list[dict[str, Any]]] = {}
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
        fleet_swaps[fleet_name] = _swaps(fleet_name, layout, units, moves)

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

    fleet_dir = root / LOCK_DIR
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
        # Only a fleet that lays out a sleeper keeps swaps, so the lock of a
        # fleet with none reads as it always did.
        if fleet_swaps[fleet_name]:
            record["swaps"] = fleet_swaps[fleet_name]
        path = fleet_dir / f"{fleet_name}.json"
        path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    for combination, record in written.items():
        rig_name = record["rig"]
        rig_id = rig_ids[rig_name]
        rig_dir = root / LOCK_DIR / "rigs" / rig_id
        rig_dir.mkdir(parents=True, exist_ok=True)
        (rig_dir / f"{combination}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def write_from_stamp(stamp_dir: Path) -> Path:
    """
    Lock the fleets of a stamped sample, and name the `lock/` folder of its stamp.

    The stamp holds `setup/fleet.yaml`, `setup/policy.yaml` and `evidence.json`;
    a folder that is no stamp, or whose setup or evidence cannot be read, is
    refused. The warm decode tolerances come from the derived numbers; a branch
    that cannot weigh them refuses the lock. What is written is written into
    the stamp folder.
    """
    from mcgyvr.derived import DerivedNumbersError
    from mcgyvr.fleet.stamp import EVIDENCE_FILE, SETUP_DIR

    if not stamp_dir.is_dir():
        raise LockRefusedError(f"{stamp_dir} is not a stamp folder: it is no folder")
    setup = stamp_dir / SETUP_DIR
    try:
        fleet = load_fleet((setup / FLEET_FILENAME).read_text(encoding="utf-8"))
        policy = load_policy((setup / POLICY_FILENAME).read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise LockRefusedError(
            f"{stamp_dir} is not a stamp folder: its setup cannot be read: {exc}"
        ) from exc
    evidence_path = stamp_dir / EVIDENCE_FILE
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LockRefusedError(
            f"{stamp_dir} is not a stamp folder: {evidence_path} cannot be read: {exc}"
        ) from exc
    if not isinstance(evidence, dict):
        raise LockRefusedError(
            f"{stamp_dir} is not a stamp folder: {evidence_path} holds no "
            "dev-run evidence object"
        )
    try:
        weighed = tolerances()
    except DerivedNumbersError as exc:
        raise LockRefusedError(str(exc)) from exc
    write(stamp_dir, fleet, evidence, policy=policy, tolerances=weighed)
    return stamp_dir / LOCK_DIR


def approved_on_no_evidence(record: Mapping[str, Any]) -> bool:
    """Whether the lock's approver is a command that approves one on no evidence."""
    return record.get("approved_by") in OWN_APPROVERS


def is_own(name: str) -> bool:
    """
    Whether a fleet name is the fleet `own`, with a lock in its folder.

    The name's fleet part must be `own`, dated tag and all, and that folder
    must hold `lock/own.json`: a lock approved on no evidence, or one that
    pins the layout sha256 a sample's lock wrote.
    """
    if split_name(name)[0] != OWN_FLEET:
        return False
    path = fleets_dir() / name / LOCK_DIR / f"{OWN_FLEET}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(record, dict) and (
        approved_on_no_evidence(record) or "layout_sha256" in record
    )


def _unit_id(unit: Mapping[str, Any]) -> str:
    """The id `own` pins a rig unit by: a digest of its engine, address and model,
    a missing engine read as llama.cpp."""
    engine = unit.get("engine")
    return ids.digest(
        "unt-",
        {
            "engine": engine if isinstance(engine, str) and engine else "llama.cpp",
            "address": str(unit.get("address") or ""),
            "model": str(unit.get("model") or ""),
        },
    )


def pinned_containers(
    fleet: Mapping[str, Any], layout: Mapping[str, Any]
) -> dict[str, dict[str, str]]:
    """The container each laid-out unit names, per rig, pinned so a live read can
    find the unit by the container it was approved with.
    """
    units = fleet.get("units") or {}
    pinned: dict[str, dict[str, str]] = {}
    for rig, slots in layout.items():
        on_rig: dict[str, str] = {}
        for slot in slots or ():
            if not isinstance(slot, list | tuple) or not slot:
                continue
            body = units.get(slot[0])
            container = body.get("container") if isinstance(body, Mapping) else None
            if isinstance(container, str) and container:
                on_rig[str(slot[0])] = container
        pinned[str(rig)] = on_rig
    return pinned


def write_unsampled(
    dev_root: Path,
    setup: Path,
    *,
    rigs: Mapping[str, str],
    acknowledged: bool,
) -> Path:
    """
    Lock the fleet `own` for a setup no sample ran on, on no evidence.

    Refuses unless the caller passes `acknowledged`, the setup lays out no
    rigs or fleets of its own, every unit on a rig sits on a read rig, each
    read rig holds a unit, no hosted unit points at a machine of the user's,
    and the layout serves the policy's mcorch units. Lays each read rig's
    units out awake, pins their unit ids and their containers, and stages the
    fleet, the policy and `lock/own.json` under `dev_root`; returns the
    `lock/` folder.
    """
    from mcgyvr.fleet.promote import on_a_users_machine
    from mcgyvr.fleet.stamp import SETUP_DIR

    if acknowledged is not True:
        raise LockRefusedError(
            f"{OWN_FLEET}: a fleet no sample ran on is locked on no evidence only "
            "once you acknowledge that, and it was not acknowledged"
        )
    fleet_path, policy_path = setup / FLEET_FILENAME, setup / POLICY_FILENAME
    try:
        fleet = load_fleet(fleet_path.read_text(encoding="utf-8"))
        policy = load_policy(policy_path.read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise LockRefusedError(f"{setup}: the setup cannot be read: {exc}") from exc
    if fleet.get("rigs") or fleet.get("fleets"):
        raise LockRefusedError(
            f"{fleet_path} lays out rigs or fleets of its own; a fleet laid out "
            "on rigs is locked from its dev evidence"
        )
    units = fleet.get("units") or {}
    unread = sorted(
        f"{unit} (on {body['rig']})"
        for unit, body in units.items()
        if "rig" in body and str(body["rig"]) not in rigs
    )
    if unread:
        raise LockRefusedError(
            f"{', '.join(unread)} sits on a rig that was not read, and a machine "
            "is not approved for live work until it is read"
        )
    layout: dict[str, list[list[str]]] = {}
    for rig in rigs:
        on_rig = [
            unit
            for unit, body in units.items()
            if "rig" in body and str(body["rig"]) == rig
        ]
        if not on_rig:
            raise LockRefusedError(
                f"{fleet_path} lays out no unit on {rig}; nothing is approved"
            )
        layout[rig] = [[unit, "awake"] for unit in on_rig]
    local = sorted(
        f"{unit} ({why})"
        for unit, body in units.items()
        if "rig" not in body
        and (why := on_a_users_machine(str(body.get("address") or ""))) is not None
    )
    if local:
        raise LockRefusedError(
            f"{', '.join(local)}: a hosted unit there is a machine of yours, and "
            "a machine is not approved for live work until it is read"
        )
    try:
        mcorch_units(policy, layout, name=OWN_FLEET)
    except FleetError as exc:
        raise LockRefusedError(
            f"{exc}; a fleet that cannot serve its mcorch policy is not approved"
        ) from exc

    own = copy.deepcopy(fleet)
    if rigs:
        own["rigs"] = {rig: {"rig_id": rigs[rig]} for rig in rigs}
    own["fleets"] = {OWN_FLEET: {"layout": layout}}
    for slots in layout.values():
        for unit, _state in slots:
            own["units"][unit]["unit_id"] = _unit_id(units[unit])
    record = {
        "layout_sha256": layout_sha256(layout_ids(own, layout)),
        # The container each laid-out unit names is pinned beside the layout, so a
        # live read matches the unit by the container it was approved in and a
        # rewritten one is not admitted. No combination record is written: there
        # is no dev run to record, and the approval is the whole of the evidence.
        "containers": pinned_containers(own, layout),
        "next": [],
        "switches": [],
        "approved_by": OWN_APPROVER,
        "approved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    fleet_text = yaml.safe_dump(own, sort_keys=False)
    policy_text = yaml.safe_dump(policy, sort_keys=False)
    try:
        parse(fleet_text, policy_text)
    except ConfigError as exc:
        raise LockRefusedError(
            f"{OWN_FLEET}: the fleet would not load as a setup: {exc}"
        ) from exc
    # Read the fleet back as it will load: the layout must come back as the one pinned.
    written = load_fleet(fleet_text)
    if layout_sha256(layout_ids(written, layout)) != record["layout_sha256"]:
        raise LockRefusedError(
            f"{OWN_FLEET}: the layout written does not read back as the one pinned"
        )

    staged = dev_root / SETUP_DIR
    staged.mkdir(parents=True, exist_ok=True)
    (staged / FLEET_FILENAME).write_text(fleet_text, encoding="utf-8")
    (staged / POLICY_FILENAME).write_text(policy_text, encoding="utf-8")
    tree = dev_root / LOCK_DIR
    tree.mkdir(parents=True, exist_ok=True)
    (tree / f"{OWN_FLEET}.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return tree
