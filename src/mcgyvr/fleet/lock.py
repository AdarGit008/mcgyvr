"""The fleet lock: what production may run, written only from passing dev runs.

``mcgyvr fleet lock`` writes two kinds of file (the lab's fleet-identity plan,
§4):

* one fleet lock file — the layout's sha256, the fleet's ``next`` list, and
  each switch's dev evidence;
* one combination record per rig — a combination's validation, shared by
  every fleet that lists it.

This module is the one writer of a lock. :func:`write` locks from dev-run
evidence handed in; :func:`write_from_stamp` from a stamp folder
(:mod:`mcgyvr.fleet.stamp`), the setup and evidence a green sample left; and
:func:`write_unsampled` locks, on no evidence, a fleet of the user's that no
sample could run on, once the user has acknowledged that. A lock reaches live
only through :mod:`mcgyvr.fleet.promote`, whichever of the three wrote it.

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
from mcgyvr.fleet.roots import fleets_dir, split_name
from mcgyvr.fleet.spans import (
    Span,
    SpanError,
    check_spans,
    room_on,
    shard_rooms,
    spans,
)
from mcgyvr.fleet.tolerance import tolerance_class

#: Where a lock sits under the dev root and under a live fleet folder alike.
LOCK_DIR = Path("records") / "fleet"
#: The fleet :func:`write_unsampled` locks: the user's own, from the setup
#: ``mcgyvr setup`` wrote.
OWN_FLEET = "own"
#: Who a lock :func:`write_unsampled` wrote says approved it: the product itself.
OWN_APPROVER = "mcgyvr setup"
#: Every approver string a released own-fleet approval has written. ``mcgyvr
#: init`` is the pre-rename command (v0.4.2 and earlier); a fleet it approved is
#: the user's own, and is recognised as such when ``mcgyvr setup`` runs again.
OWN_APPROVERS = frozenset({OWN_APPROVER, "mcgyvr init"})


class LockRefusedError(Exception):
    """The lock cannot be written: a dev run did not prove what it must."""


def tolerances() -> dict[str, Any]:
    """The class tolerances a lock weighs, as :func:`write` takes them.

    Looked up in :mod:`mcgyvr.derived`: the rule is pinned here, the values are
    estimates the user can set. The lock weighs only warm decode against NVMe,
    so it reads decode's classes. Raises
    :class:`mcgyvr.derived.DerivedNumbersError` when they cannot be read.
    """
    from mcgyvr.derived import class_tolerances

    return {"warm_decode_class_pct": class_tolerances()["warm_decode_tok_s"]}


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

    # A rig is named by its reading (owner, 2026-09-15, D1; one id, 2026-10-14).
    # A dev run that filed the rig id its read named beside the card proves
    # which machine it ran on, so a pinned id that read does not name is
    # refused. Evidence that carries no rig id locks against the pinned id.
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
    """Write the fleet lock from the stamp folder ``stamp_dir``; the lock tree.

    A stamp folder (:func:`mcgyvr.fleet.stamp.stamp`) holds the staged setup
    (``setup/fleet.yaml``, ``setup/policy.yaml``) and the dev-run evidence a
    green sample built (``evidence.json``). The lock is written by
    :func:`write` into the stamp folder itself, as its dev root, so promoting
    it (:func:`mcgyvr.fleet.promote.promote` with ``stamp_dir`` and its
    ``setup/``) needs no lab checkout. Refused, naming what is wrong, when the
    folder is not a stamp folder (a file of it missing or unreadable, evidence
    that is not a JSON object), when the class tolerances cannot be read, or
    when :func:`write` refuses the evidence.
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
    """Whether the fleet lock ``record`` is one :func:`write_unsampled` wrote:
    approved by the product itself, on no dev evidence."""
    return record.get("approved_by") in OWN_APPROVERS


def is_own(name: str) -> bool:
    """Whether the live name ``name`` is the user's own fleet: a folder of the
    fleet :data:`OWN_FLEET` holding its lock, which ``mcgyvr setup`` wrote --
    from the stamp of its sample (:func:`write_from_stamp`) or on no evidence
    (:func:`write_unsampled`) -- and may replace with a later setup of its
    own, as it may no other live fleet."""
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
    """``unt-`` for one unit setup bound from a running backend, hashed over the
    facts that stay: its engine, where it answers and the model it serves.

    A backend setup detects is already running, so it is not launched here and
    has no image, weights, argv or env to hash. The id is the same spelling the
    lock pins (:func:`mcgyvr.fleet.ids.digest`).
    """
    engine = unit.get("engine")
    return ids.digest(
        "unt-",
        {
            "engine": engine if isinstance(engine, str) and engine else "llama.cpp",
            "address": str(unit.get("address") or ""),
            "model": str(unit.get("model") or ""),
        },
    )


def write_unsampled(
    dev_root: Path,
    setup: Path,
    *,
    rigs: Mapping[str, str],
    acknowledged: bool,
) -> Path:
    """Lock the user's own fleet :data:`OWN_FLEET` on no evidence; the lock tree.

    For a fleet no sample could run on: the setup ``mcgyvr setup`` wrote at
    ``setup``, its units hosted or on the user's own machines. Such a fleet is
    locked, approved by the product itself (:data:`OWN_APPROVER`) on empty
    evidence -- a stranger has none -- but only once the user has acknowledged
    that: ``acknowledged`` must be ``True``, and asking is the caller's.

    ``rigs`` maps each rig the caller read (through the door's own reader) to
    the rig id that read named, and may be empty. Each is laid out with every
    unit on it awake, and each such unit gets the id the lock pins; hosted
    units are carried as they are. Written under ``dev_root``, as a stamp folder
    is laid out: the fleet's setup in ``setup/`` and the lock, which pins that
    layout and says who approved it and when, in the lock tree. No combination
    record is written: nothing was validated. From there it is promoted
    (:func:`mcgyvr.fleet.promote.promote` with ``dev_root`` and its ``setup/``)
    and named live (:func:`mcgyvr.fleet.promote.use`) as any lock is.

    Refused, with nothing written, when not acknowledged; when the setup cannot
    be read, or already lays out rigs or fleets (such a fleet is locked from
    its dev evidence); when a unit sits on a rig that was not read (a machine
    is approved only by a read of it), or a rig read holds no unit; when a
    hosted unit's address is a machine of the user's
    (:func:`mcgyvr.fleet.promote.on_a_users_machine`); when an mcorch policy's
    units are not awake in the layout; or when the fleet would not load as a
    setup.
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
    own["profile"] = "live"
    if rigs:
        own["rigs"] = {rig: {"rig_id": rigs[rig]} for rig in rigs}
    own["fleets"] = {OWN_FLEET: {"layout": layout}}
    for slots in layout.values():
        for unit, _state in slots:
            own["units"][unit]["unit_id"] = _unit_id(units[unit])
    record = {
        "layout_sha256": layout_sha256(layout_ids(own, layout)),
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
    # The layout as it reads back from the file written is the one pinned.
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
