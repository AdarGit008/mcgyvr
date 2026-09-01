"""F7/F8/F9 — the capability table is read honestly, bounded, and immutable.

Three defects on one file. F7: ``params_b`` became a required key while
``schema_version`` stayed 1, so a v1 table that predates the field dies with a
bare ``KeyError`` instead of a named table error. F8: a ``NaN`` ``params_b``
fails every size comparison, so :func:`mcgyvr.orchestrator.read.budget_for_model`
raises ``StopIteration`` where it should answer conservatively. F9:
``shipped_table()`` returns one shared mutable instance, so a caller that mutates
a model changes every later selection process-wide.
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


def test_a_nan_params_b_is_not_a_stop_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.capability as capability
    from mcgyvr.orchestrator.read import budget_for_model

    monkeypatch.setattr(
        capability, "table_path", lambda: _table(tmp_path, [_model(params_b="nan")])
    )
    capability.shipped_table.cache_clear()

    # A NaN size fits no ceiling; the conservative answer is the smallest budget.
    assert budget_for_model("m1") == 4096


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
