"""Per-rig derived numbers, read from the one file that states them.

``tools/runs/derived.json`` is the source of truth for the numeric values
mcgyvr measures on a rig rather than reads from the rig or from the model.
It is JSON and content-addressable so a reader can digest it the way it
digests ``tools/runs/hosts.json``, and it is a sibling of that file on purpose:
``hosts.json`` declares what each rig IS, read live by the door's gate 2, and
this file declares what was MEASURED on it.

Nothing here falls back to a literal in code. A number that is absent from the
file is a named refusal (:class:`DerivedNumbersError`), because a silent inline
default is exactly the drift this file exists to end.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DERIVED = REPO / "tools" / "runs" / "derived.json"


class DerivedNumbersError(Exception):
    """A derived number was asked for and the file does not state it."""


def _load(path: Path | None = None) -> dict[str, Any]:
    """The derived-numbers document, refused by name when unreadable."""
    where = DERIVED if path is None else path
    try:
        document = json.loads(where.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DerivedNumbersError(
            f"cannot read derived numbers from {where}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise DerivedNumbersError(f"{where} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise DerivedNumbersError(f"{where} is not a JSON object")
    return document


def _number(body: Any, where: str) -> float:
    """The float a ``{value, why}`` block states, refused by name when absent."""
    if not isinstance(body, dict):
        raise DerivedNumbersError(f"{where} is not stated as a number")
    value = body.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DerivedNumbersError(
            f"{where} states no value; a rig's derived number is absent, so "
            "nothing is sized from an inline default"
        )
    return float(value)


def runtime_resident_gb(host: str, *, path: Path | None = None) -> float:
    """``host``'s runtime-resident intercept in GiB, refused by name when absent.

    The number a sizing adds to the spilled experts when an MoE keeps blocks on
    the host. It is per-rig, so the host must be named: a figure read for the
    wrong rig is a number nobody measured for the machine in hand.
    """
    document = _load(path)
    block = document.get(host)
    if not isinstance(block, dict):
        raise DerivedNumbersError(
            f"tools/runs/derived.json declares no {host!r}; its runtime "
            "resident intercept is absent, so nothing is sized from an inline "
            "default"
        )
    numbers = block.get("numbers")
    if not isinstance(numbers, dict):
        raise DerivedNumbersError(
            f"tools/runs/derived.json[{host}].numbers is absent; the rig's "
            "derived numbers are not stated"
        )
    return _number(
        numbers.get("runtime_resident_gb"),
        f"derived.json[{host}].numbers.runtime_resident_gb",
    )


def warm_decode_tolerances(*, path: Path | None = None) -> dict[str, float]:
    """Engine -> warm-decode tolerance percent, refused by name when absent.

    What a unit may lose to NVMe against its no-NVMe warm-decode baseline
    before the fleet lock refuses it. Engine-specific, so the whole mapping is
    read and returned together.
    """
    document = _load(path)
    engine = document.get("engine")
    if not isinstance(engine, dict):
        raise DerivedNumbersError(
            "tools/runs/derived.json declares no `engine` block; the "
            "engine-specific warm-decode tolerances are not stated"
        )
    by_engine = engine.get("warm_decode_pct")
    if not isinstance(by_engine, dict) or not by_engine:
        raise DerivedNumbersError(
            "tools/runs/derived.json.engine.warm_decode_pct states no "
            "engine tolerances; the fleet lock will not guess one"
        )
    tolerances: dict[str, float] = {}
    for name, body in by_engine.items():
        tolerances[name] = _number(body, f"derived.json.engine.warm_decode_pct.{name}")
    return tolerances
