"""The lock's engine-keyed NVMe tolerance lookup — superseded 2026-09-15.

Moved here from ``src/mcgyvr/fleet/lock.py`` when the lock's NVMe baseline
check began reading the unit's tolerance class
(:func:`mcgyvr.fleet.tolerance.tolerance_class`, values in
``tools/runs/derived.json`` ``engine.warm_decode_class_pct``), the same class a
live probe is judged by. It had no tests of its own.
"""

from __future__ import annotations

from typing import Any


def _warm_decode_tolerance_pct(engine: Any, tolerances: dict[str, Any]) -> float | None:
    """The percentage a unit's warm decode may lose to NVMe, or ``None``."""
    by_engine = tolerances.get("warm_decode_pct")
    if not isinstance(by_engine, dict):
        return None
    value = by_engine.get(engine)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
