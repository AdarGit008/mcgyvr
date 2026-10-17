""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from mcgyvr.fleet.admit import layout_ids
from mcgyvr.fleet.roots import LOCK_DIR


class AllPulledError(Exception):
    ""


#
#
#
_JUDGED: dict[str, tuple[str, str]] = {
    "warm_decode_tok_s": ("down", "pct"),
    "prefill_tok_s": ("down", "pct"),
    "card_steady_mib": ("up", "abs"),
    "card_peak_mib": ("up", "abs"),
    "l2_wake_s": ("up", "s"),
    "downtime_s": ("up", "s"),
    #
    #
    "card_mib": ("up", "room"),
    #
    #
    "load_peak_mib": ("up", "room"),
}


def _number(value: Any) -> float | None:
    ""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _plain_pct(entries: Mapping[str, Any], field: str) -> float | None:
    ""
    by_field = entries.get("tolerance_pct")
    if not isinstance(by_field, Mapping):
        return None
    return _number(by_field.get(field))


def _plain_hit(
    entry: Any, entries: Mapping[str, Any], field: str, kind: str, value: float
) -> bool | None:
    ""
    if kind == "room":
        room = _number(entries.get("room_mib"))
        return None if room is None else value > room
    if kind == "pct":
        expected = _number(entry)
        pct = _plain_pct(entries, field)
        if expected is None or pct is None:
            return None
        return value < expected * (1.0 - pct / 100.0)
    return None


#ll
#
_RUN_AT = re.compile(r"run-(\d{8}T\d{6})")


def _run_at(run_id: str) -> str | None:
    match = _RUN_AT.match(run_id)
    if not match:
        return None
    s = match.group(1)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}"


def _short(identifier: str) -> str:
    ""
    return identifier if len(identifier) <= 12 else f"{identifier[:12]}…"


def _warning(
    observed: Mapping[str, Any], stamp: Mapping[str, str], unit_id: str | None
) -> str:
    ""
    who = observed.get("unit") or observed.get("switch") or _short(str(unit_id))
    where = [stamp["rig"]] if stamp.get("rig") else []
    where.append(_short(stamp["combination_id"]))
    return (
        f"warning: {who} {observed['field']} pulled {stamp['fleet']} "
        f"({', '.join(where)}) — see `mcgyvr fleet alerts`"
    )


def _journal_file(journal: Path, combination_id: str, key: str) -> Path:
    where = journal / combination_id
    where.mkdir(parents=True, exist_ok=True)
    return where / f"{key}.jsonl"


def _append(path: Path, row: dict[str, Any]) -> Path:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def record(journal: Path, stamp: Mapping[str, str], values: Mapping[str, Any]) -> Path:
    ""
    path = _journal_file(journal, stamp["combination_id"], stamp["unit_id"])
    return _append(path, {**dict(stamp), **dict(values)})


def _judge(
    observed: Mapping[str, Any], approved: Mapping[str, Any]
) -> dict[str, Any] | None:
    field = observed["field"]
    value = observed["observed"]

    #
    if field == "restarts":
        if int(value) != 0:
            alert: dict[str, Any] = {"field": "restarts", "direction": "up"}
            if "unit_id" in observed:
                alert["unit_id"] = observed["unit_id"]
            if "switch" in observed:
                alert["switch"] = observed["switch"]
            return alert
        return None

    rule = _JUDGED.get(field)
    if rule is None:
        return None

    scope_key = "switch" if "switch" in observed else "unit_id"
    scope = observed.get(scope_key)
    if scope is None:
        return None
    entries = approved.get(scope) or {}
    entry = entries.get(field)
    direction, kind = rule
    if isinstance(entry, Mapping):
        if "expected" not in entry or kind == "room":
            return None
        expected = float(entry["expected"])
        tolerance = entry.get("tolerance") or {}
        bound: float
        if kind == "pct":
            bound = expected * (1.0 - float(tolerance.get("pct", 0.0)) / 100.0)
            hit = float(value) < bound
        elif kind == "abs":
            bound = expected + float(tolerance.get("abs", 0.0))
            hit = float(value) > bound
        else:  #
            bound = expected + float(tolerance.get("s", 0.0))
            hit = float(value) > bound
    else:
        plain = _plain_hit(entry, entries, field, kind, float(value))
        if plain is None:
            return None
        hit = plain

    if not hit:
        return None
    out: dict[str, Any] = {"field": field, "direction": direction}
    if "unit_id" in observed:
        out["unit_id"] = observed["unit_id"]
    if "switch" in observed:
        out["switch"] = observed["switch"]
    return out


def _judged_pct(
    observed: Mapping[str, Any], approved: Mapping[str, Any]
) -> float | None:
    ""
    field = observed["field"]
    rule = _JUDGED.get(field)
    if rule is None or rule[1] != "pct":
        return None
    scope = observed.get("switch" if "switch" in observed else "unit_id")
    if scope is None:
        return None
    entries = approved.get(scope) or {}
    entry = entries.get(field)
    if isinstance(entry, Mapping):
        if "expected" not in entry:
            return None
        return float((entry.get("tolerance") or {}).get("pct", 0.0))
    if _number(entry) is None:
        return None
    return _plain_pct(entries, field)


def _already_alerted(path: Path, field: str) -> bool:
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("field") == field and row.get("alert"):
            return True
    return False


def check(
    observations: Iterable[Mapping[str, Any]],
    *,
    approved: Mapping[str, Any],
    journal_dir: Path,
    stamp: Mapping[str, str],
    run_id: str,
    lease_id: str,
) -> Iterator[dict[str, Any]]:
    ""
    run_at = _run_at(run_id)
    for observed in observations:
        field = observed["field"]
        unit_id = observed.get("unit_id", stamp.get("unit_id"))
        key = unit_id if "unit_id" in observed else "switch"

        path = _journal_file(journal_dir, stamp["combination_id"], key)
        warned = _already_alerted(path, field)

        row: dict[str, Any] = {
            **dict(stamp),
            "field": field,
            "observed": observed["observed"],
            "run_id": run_id,
            "lease_id": lease_id,
        }
        if "unit_id" in observed:
            row["unit_id"] = observed["unit_id"]
        if "switch" in observed:
            row["switch"] = observed["switch"]
        at = observed.get("at", run_at)
        if at is not None:
            row["at"] = at

        alert = _judge(observed, approved)
        row["alert"] = alert is not None
        pct = _judged_pct(observed, approved)
        if pct is not None:
            row["tolerance_pct"] = pct
        _append(path, row)

        if alert is None:
            continue
        if not warned:
            print(_warning(observed, stamp, unit_id), file=sys.stderr)
        yield alert


def _rows(journal: Path) -> Iterator[dict[str, Any]]:
    for path in sorted(journal.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _validated_at(
    lock_root: Path | None, rig_id: str, combination_id: str
) -> str | None:
    if lock_root is None:
        return None
    path = lock_root / LOCK_DIR / "rigs" / rig_id / f"{combination_id}.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("validated_at")
        return value if isinstance(value, str) else None
    except (OSError, json.JSONDecodeError):
        return None


def pulled(journal: Path, lock_root: Path | None) -> dict[str, list[dict[str, Any]]]:
    ""
    groups: dict[str, dict[str, Any]] = {}
    for row in _rows(journal):
        if not row.get("alert") or "unit_id" not in row:
            continue
        if row.get("locked") == "false":
            continue
        combination = row.get("combination_id")
        if not combination:
            continue
        entry = groups.setdefault(
            combination,
            {"rig_id": row.get("rig_id"), "max_at": None, "pulls": {}},
        )
        unit_field = (row["unit_id"], row["field"])
        entry["pulls"][unit_field] = entry["pulls"].get(unit_field, 0) + 1
        at = row.get("at")
        if at is not None and (entry["max_at"] is None or at > entry["max_at"]):
            entry["max_at"] = at

    out: dict[str, list[dict[str, Any]]] = {}
    for combination, entry in groups.items():
        validated = _validated_at(lock_root, entry["rig_id"], combination)
        if (
            validated is not None
            and entry["max_at"] is not None
            and validated > entry["max_at"]
        ):
            continue
        out[combination] = [
            {"unit_id": unit, "field": field, "count": count}
            for (unit, field), count in entry["pulls"].items()
        ]
    return out


class PullsUnreadableError(Exception):
    ""


def pulled_units(
    fleet: dict[str, Any], fleet_name: str, journal: Path, lock_root: Path | None
) -> dict[str, list[dict[str, Any]]]:
    ""
    units = fleet.get("units", {})
    names = {
        block.get("unit_id"): name
        for name, block in units.items()
        if isinstance(block, Mapping)
    }
    layout = fleet["fleets"][fleet_name].get("layout", {})
    rig_ids = {rig: block["rig_id"] for rig, block in fleet.get("rigs", {}).items()}
    combinations = layout_ids(fleet, layout)
    pulls = pulled(journal, lock_root)
    out: dict[str, list[dict[str, Any]]] = {}
    for rig, slots in layout.items():
        entries = pulls.get(combinations[rig_ids[rig]])
        if not entries:
            continue
        named = [
            {**entry, "unit": names.get(entry["unit_id"], entry["unit_id"])}
            for entry in entries
        ]
        for slot in slots:
            if slot is not None:
                out[str(slot[0])] = named
    return out


def live_pulled_units() -> dict[str, list[dict[str, Any]]]:
    ""
    from mcgyvr.fleet.probe import ProbeError, _live, journal_dir
    from mcgyvr.fleet.roots import LiveFleetError, live_fleet_dir

    try:
        if live_fleet_dir() is None:
            return {}
        name, folder, fleet = _live(None)
        return pulled_units(fleet, name, journal_dir(folder), folder)
    except (
        LiveFleetError,
        ProbeError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        raise PullsUnreadableError(f"{type(exc).__name__}: {exc}") from exc


def routable(
    units: Mapping[str, str], journal: Path, lock_root: Path | None
) -> list[str]:
    ""
    pulled_combs = pulled(journal, lock_root)
    free = [
        unit for unit, combination in units.items() if combination not in pulled_combs
    ]
    if not free and units:
        named = ", ".join(sorted(c for c in units.values() if c in pulled_combs))
        raise AllPulledError(
            f"live refuses all work: every combination is pulled ({named})"
        )
    return free


def rejudge(
    journal: Path, combination_id: str, approved: Mapping[str, Any]
) -> list[dict[str, Any]]:
    ""
    found: list[dict[str, Any]] = []
    for row in _rows(journal):
        if row.get("combination_id") != combination_id:
            continue
        if "field" not in row or "observed" not in row or "unit_id" not in row:
            continue
        if _judge(
            {
                "unit_id": row["unit_id"],
                "field": row["field"],
                "observed": row["observed"],
            },
            approved,
        ):
            found.append({"unit_id": row["unit_id"], "field": row["field"]})
    return found
