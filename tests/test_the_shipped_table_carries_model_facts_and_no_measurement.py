"""The shipped table carries a model's facts and no measurement.

Promises:

* No level of the capability table declares a reading, a card class, a
  harness caveat or a concurrency finding (:data:`MEASUREMENT_KEYS`). Those
  are measurements of the cards they were taken on, and they are the lab's,
  not the product's.
* The shipped table carries none of them, at any depth.
* A table that carries one is refused by that key's name, as any key the code
  does not declare is.
* What the table does carry for each model is its facts: its size, its
  weights and the memory it takes to serve.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import capability
from mcgyvr.capability import CapabilityTableError, load, table_path
from tests.table_fixture import row, table_document, write_table

#: The keys that held measurements, at the level each one sat at.
MEASUREMENT_KEYS: dict[str, tuple[str, ...]] = {
    "table": ("card_classes", "harness_caveats", "concurrency_findings"),
    "model row": ("throughput_tok_s", "seconds_per_image", "seconds_per_clip"),
    "backend": ("card_class",),
}


def _keys(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _keys(value)


@pytest.mark.parametrize("level", sorted(MEASUREMENT_KEYS))
def test_no_level_declares_a_measurement(level: str) -> None:
    declared = capability.DECLARED_KEYS[level]

    assert not declared & set(MEASUREMENT_KEYS[level]), sorted(declared)


def test_the_shipped_table_carries_no_measurement_at_any_depth() -> None:
    document = json.loads(table_path().read_text(encoding="utf-8"))
    measured = {key for keys in MEASUREMENT_KEYS.values() for key in keys}

    assert not measured & set(_keys(document))


@pytest.mark.parametrize(
    ("where", "key"),
    [
        ("table", "card_classes"),
        ("table", "harness_caveats"),
        ("table", "concurrency_findings"),
        ("model row", "throughput_tok_s"),
    ],
)
def test_a_table_that_carries_a_measurement_is_refused_by_its_name(
    tmp_path: Path, where: str, key: str
) -> None:
    document = table_document()
    entry = document if where == "table" else document["models"][0]
    entry[key] = []

    with pytest.raises(CapabilityTableError) as refused:
        load(write_table(tmp_path, document))

    assert repr(key) in str(refused.value), refused.value


def test_each_shipped_model_states_its_size_its_weights_and_its_memory() -> None:
    for model in load().models:
        assert model.params_b > 0, model.id
        assert model.weights_gb > 0, model.id
        assert model.vram_gb_working > 0, model.id


def test_a_row_of_facts_alone_loads(tmp_path: Path) -> None:
    """The control: a row with no reading is a whole row."""
    loaded = load(write_table(tmp_path, table_document(rows=[row("invented-a")])))

    assert [m.id for m in loaded.models] == ["invented-a"]
