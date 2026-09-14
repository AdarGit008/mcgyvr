"""The engine-keyed warm-decode tolerances resolved, and an absent one was refused.

Moved from ``tests/test_derived_numbers.py`` with
``archive/src/mcgyvr/derived_engine_tolerances.py`` on 2026-09-15, when the
tolerance became the unit's class (``mcgyvr.derived.class_tolerances``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from archive.src.mcgyvr import derived_engine_tolerances as derived  # type: ignore[import-not-found]

REPO = Path(__file__).resolve().parents[2]
DERIVED = REPO / "tools" / "runs" / "derived.json"


def test_the_engine_tolerances_resolve() -> None:
    assert derived.warm_decode_tolerances() == {"vllm": 3.0, "llama.cpp": 5.0}


def test_a_missing_engine_tolerance_is_refused_by_name(tmp_path: Path) -> None:
    mutated = json.loads(DERIVED.read_text(encoding="utf-8"))
    del mutated["engine"]["warm_decode_pct"]
    path = tmp_path / "derived.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError, match="warm_decode_pct"):
        derived.warm_decode_tolerances(path=path)
