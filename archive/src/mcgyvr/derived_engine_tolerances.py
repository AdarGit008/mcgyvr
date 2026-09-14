"""The engine-keyed warm-decode tolerances — superseded 2026-09-15.

Moved here from ``src/mcgyvr/derived.py`` when a unit's tolerance became its
class (owner, 2026-09-15: the measured classes of
``records/measurements/fleet-identity-2026-09-11/tolerances.json`` — vLLM 1%,
llama.cpp 1%, CPU-experts 48% — moved into ``tools/runs/derived.json``). The
provisional per-engine values this read (``engine.warm_decode_pct``: vllm 3.0,
llama.cpp 5.0) are gone from the file, and :func:`mcgyvr.derived.class_tolerances`
reads ``engine.warm_decode_class_pct`` instead. Its only tests are
``archive/tests/test_the_engine_warm_decode_tolerances.py``.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.derived import DerivedNumbersError, _load, _number


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
