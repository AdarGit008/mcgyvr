"""F7/F9 — the capability table is read honestly, bounded, and immutable.

Two defects on one file. F7: ``params_b`` became a required key while
``schema_version`` stayed 1, so a v1 table that predates the field dies with a
bare ``KeyError`` instead of a named table error. F9: ``shipped_table()``
returns one shared mutable instance, so a caller that mutates a model changes
every later selection process-wide.

F8 was the third and is closed by deletion rather than by a fix. A ``NaN``
``params_b`` fails every size comparison, and the one size comparison in the
tree was the exploration budget ``mcgyvr.orchestrator.read`` sized from the
model being dispatched to — which had no caller under ``src/`` and has been
removed (action 18). Nothing in ``src/`` compares ``params_b`` to anything now,
so there is no ``StopIteration`` left to raise. If a size comparison comes back,
it comes back where a rung is chosen, and F8's assertion belongs there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest


def _table(tmp_path: Path, models: list[dict[str, Any]]) -> Path:
    path = tmp_path / "capability-table.json"
    path.write_text(json.dumps({"schema_version": 1, "models": models}))
    return path


def _model(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "m1",
        "family": "api",
        "params_b": 7.0,
        "vram_gb_working": 5.0,
        "weights_gb": 4.0,
        "quality": [
            {"humaneval_plus_pass1": 0.6, "backend": "b", "rig": "r", "date": "d"}
        ],
        "throughput_tok_s": [{"value": 100.0, "backend": "b", "rig": "r", "date": "d"}],
        "capabilities": {"algorithm": 0.8},
    }
    row.update(overrides)
    return row


def test_a_missing_required_key_is_a_named_error(tmp_path: Path) -> None:
    from mcgyvr.capability import CapabilityTableError, load

    row = _model()
    del row["params_b"]

    with pytest.raises(CapabilityTableError, match="params_b"):
        load(_table(tmp_path, [row]))


def test_the_shipped_table_is_structurally_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.capability as capability

    monkeypatch.setattr(capability, "table_path", lambda: _table(tmp_path, [_model()]))
    capability.shipped_table.cache_clear()
    table = capability.shipped_table()

    assert isinstance(table.models, tuple)
    assert isinstance(table.caveats, tuple)
    model = table.models[0]
    assert isinstance(model.quality, tuple)
    assert isinstance(model.throughput, tuple)
    # ``capabilities`` is a read-only mapping; assignment is refused at runtime.
    mutable = cast(dict[str, float], model.capabilities)
    with pytest.raises(TypeError):
        mutable["algorithm"] = 0.9
