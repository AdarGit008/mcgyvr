"""An alert pulls its combination at once, until a re-validation is committed.

``check`` judges observations against their locked values and files every one
under the journal, stamped with the fleet, rig, combination and unit it was
computed for. A live alert pulls its combination and warns once (the journal is
the memory, so a repeat warns nowhere); a dev run with an alert fails. A pull
clears only when the combination's validation is re-committed; ``rejudge``
re-checks the journal under a tighter rule and pulls nothing.
(``records/plans/fleet-identity.md`` §5 and §7.)
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any


class AlertError(Exception):
    """A dev run produced an alert, and a dev run must not."""


class AllPulledError(Exception):
    """Live refuses all work: every combination is pulled."""


#: A judged field maps to (direction, tolerance kind). ``direction`` is "up"
#: (alert above the bound) or "down" (alert below it). Anything not listed is
#: recorded, never alerted.
_JUDGED: dict[str, tuple[str, str]] = {
    "warm_decode_tok_s": ("down", "pct"),
    "prefill_tok_s": ("down", "pct"),
    "card_steady_mib": ("up", "abs"),
    "card_peak_mib": ("up", "abs"),
    "l2_wake_s": ("up", "s"),
    "downtime_s": ("up", "s"),
}

#: A run id of the form ``run-YYYYMMDDTHHMMSS-…`` carries its own time; a pull
#: clears against a lock validated after it.
_RUN_AT = re.compile(r"run-(\d{8}T\d{6})")


def _run_at(run_id: str) -> str | None:
    match = _RUN_AT.match(run_id)
    if not match:
        return None
    s = match.group(1)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}:{s[13:15]}"


def _journal_file(journal: Path, combination_id: str, key: str) -> Path:
    where = journal / combination_id
    where.mkdir(parents=True, exist_ok=True)
    return where / f"{key}.jsonl"


def _append(path: Path, row: dict[str, Any]) -> Path:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def record(journal: Path, stamp: Mapping[str, str], values: Mapping[str, Any]) -> Path:
    """File one reading under the journal, stamped by what it was computed for.

    Returns the file path, which is one file per combination and unit, so two
    readings of the same figure land in the same file.
    """
    path = _journal_file(journal, stamp["combination_id"], stamp["unit_id"])
    return _append(path, {**dict(stamp), **dict(values)})


def _judge(
    observed: Mapping[str, Any], approved: Mapping[str, Any]
) -> dict[str, Any] | None:
    field = observed["field"]
    value = observed["observed"]

    # A restart is judged exactly against zero: no tolerance reaches it.
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
    entry = (approved.get(scope) or {}).get(field)
    if not isinstance(entry, Mapping) or "expected" not in entry:
        return None

    direction, kind = rule
    expected = float(entry["expected"])
    tolerance = entry.get("tolerance") or {}
    bound: float
    if kind == "pct":
        bound = expected * (1.0 - float(tolerance.get("pct", 0.0)) / 100.0)
        hit = float(value) < bound
    elif kind == "abs":
        bound = expected + float(tolerance.get("abs", 0.0))
        hit = float(value) > bound
    else:  # "s"
        bound = expected + float(tolerance.get("s", 0.0))
        hit = float(value) > bound

    if not hit:
        return None
    out: dict[str, Any] = {"field": field, "direction": direction}
    if "unit_id" in observed:
        out["unit_id"] = observed["unit_id"]
    if "switch" in observed:
        out["switch"] = observed["switch"]
    return out


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
    profile: str,
    journal_dir: Path,
    stamp: Mapping[str, str],
    run_id: str,
    lease_id: str,
) -> Iterator[dict[str, Any]]:
    """Judge observations against locked values, file them, and yield alerts.

    A dev run raises :class:`AlertError` on the first alert; a live run yields
    each alert, warns once per unit-and-field, and the filed alert row is what
    :func:`pulled` reads.
    """
    at = _run_at(run_id)
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
        if at is not None:
            row["at"] = at

        alert = _judge(observed, approved)
        row["alert"] = alert is not None
        _append(path, row)

        if alert is None:
            continue
        if profile == "dev":
            raise AlertError(f"a dev run alerts on {field}")
        if not warned:
            print(
                f"warning: {field} pulled {stamp['fleet']} — see `mcgyvr fleet alerts`",
                file=sys.stderr,
            )
        yield alert


def _rows(journal: Path) -> Iterator[dict[str, Any]]:
    for path in sorted(journal.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _validated_at(lock_root: Path, rig_id: str, combination_id: str) -> str | None:
    path = lock_root / "records" / "fleet" / "rigs" / rig_id / f"{combination_id}.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("validated_at")
        return value if isinstance(value, str) else None
    except (OSError, json.JSONDecodeError):
        return None


def pulled(journal: Path, lock_root: Path) -> dict[str, list[dict[str, Any]]]:
    """The pulled combinations, with the unit, field and count of each pull.

    A combination is pulled while it has a live alert newer than its committed
    validation; a re-committed validation (a newer ``validated_at``) clears it.
    """
    groups: dict[str, dict[str, Any]] = {}
    for row in _rows(journal):
        if not row.get("alert") or "unit_id" not in row:
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


def routable(units: Mapping[str, str], journal: Path, lock_root: Path) -> list[str]:
    """The units whose combination is not pulled, or :class:`AllPulledError`."""
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
    """What a tighter rule finds in the journal for one combination; pulls nothing."""
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
