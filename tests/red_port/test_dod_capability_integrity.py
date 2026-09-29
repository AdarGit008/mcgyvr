"""F7/F9 — the capability table is read honestly, bounded, and immutable.

F7: a table missing a required key such as ``params_b`` is refused with a named
:class:`~mcgyvr.capability.CapabilityTableError`, not a bare ``KeyError``. F9: a
loaded table is structurally immutable — a caller cannot mutate a model and
change what every later reader of the same table sees.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from tests.table_fixture import CLASSES, reading, table_document, write_table

CLASS = str(CLASSES[0]["id"])


def _table(tmp_path: Path, models: list[dict[str, Any]]) -> Path:
    return write_table(tmp_path, table_document(rows=models))


def _model(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "m1",
        "family": "api",
        "params_b": 7.0,
        "vram_gb_working": 5.0,
        "weights_gb": 4.0,
        "throughput_tok_s": [reading(CLASS, value=100.0)],
    }
    row.update(overrides)
    return row


def test_a_missing_required_key_is_a_named_error(tmp_path: Path) -> None:
    from mcgyvr.capability import CapabilityTableError, load

    row = _model()
    del row["params_b"]

    with pytest.raises(CapabilityTableError, match="params_b"):
        load(_table(tmp_path, [row]))


def test_a_loaded_table_is_structurally_immutable(tmp_path: Path) -> None:
    from mcgyvr.capability import load

    table = load(_table(tmp_path, [_model()]))

    assert isinstance(table.models, tuple)
    assert isinstance(table.caveats, tuple)
    model = table.models[0]
    assert isinstance(model.throughput, tuple)
    # A model is a frozen record; assignment is refused at runtime.
    with pytest.raises(dataclasses.FrozenInstanceError):
        model.vram_gb_working = 0.5  # type: ignore[misc]
