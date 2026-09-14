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

from mcgyvr.fleet.tolerance import CLASSES

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


def class_tolerances(*, path: Path | None = None) -> dict[str, float]:
    """Tolerance class -> the percent a unit's warm decode or prefill may fall.

    One value per class of :data:`mcgyvr.fleet.tolerance.CLASSES`, read from
    ``engine.warm_decode_class_pct``: what the fleet lock allows a unit to lose
    to NVMe against its no-NVMe baseline, and what a live probe is judged
    against (owner, 2026-09-15). Every class must be stated; an absent one is
    refused by name, so neither judge is left to guess a number.
    """
    document = _load(path)
    engine = document.get("engine")
    if not isinstance(engine, dict):
        raise DerivedNumbersError(
            "tools/runs/derived.json declares no `engine` block; the class "
            "tolerances are not stated"
        )
    by_class = engine.get("warm_decode_class_pct")
    if not isinstance(by_class, dict):
        raise DerivedNumbersError(
            "tools/runs/derived.json.engine.warm_decode_class_pct is absent; "
            "no class tolerance is guessed"
        )
    tolerances: dict[str, float] = {}
    for name in CLASSES:
        if name not in by_class:
            raise DerivedNumbersError(
                "tools/runs/derived.json.engine.warm_decode_class_pct states no "
                f"{name!r} class; a unit of that class would be judged against "
                "nothing"
            )
        tolerances[name] = _number(
            by_class[name], f"derived.json.engine.warm_decode_class_pct.{name}"
        )
    return tolerances
