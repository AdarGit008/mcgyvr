"""A capability table of another shape is refused, and the refusal says why.

Promises:

* A table of any version but the one this code reads is refused, and the
  refusal names the version it found and the version this code reads. A reader
  that ignored unknown keys would read an older table's rows as if they meant
  what this version's rows mean, and nothing would say so.
* Every reading names the card class it was taken for, and that class is one
  the table declares. A reading keyed by a class nobody declared is an estimate
  for nothing the table can describe, and it is refused by that class's name.
* A class is declared with an id, a label a user reads and its nominal memory;
  one that leaves any of these out is refused by the name of what is missing.

Every table here is generated (:mod:`tests.table_fixture`), with invented
classes, model ids and numbers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr import capability
from mcgyvr.capability import CapabilityTableError, load
from tests.table_fixture import CLASSES, reading, row, table_document, write_table


def _refusal(tmp_path: Path, document: dict[str, Any]) -> str:
    with pytest.raises(CapabilityTableError) as refused:
        load(write_table(tmp_path, document))
    return str(refused.value)


def test_a_table_of_the_shape_this_code_reads_loads_with_its_classes(
    tmp_path: Path,
) -> None:
    """The control: without it every refusal below could be a loader that
    refuses everything."""
    document = table_document(
        rows=[
            row("invented-model-a", card_class="10gb"),
            row("invented-model-b", card_class="20gb"),
        ]
    )
    table = load(write_table(tmp_path, document))

    assert [(c.id, c.label, c.memory_gb) for c in table.card_classes] == [
        (c["id"], c["label"], c["memory_gb"]) for c in CLASSES
    ]
    declared = {c.id for c in table.card_classes}
    readings = [
        m for model in table.models for m in (*model.quality, *model.throughput)
    ]
    assert readings
    assert {m.card_class for m in readings} == declared


@pytest.mark.parametrize("offset", [-1, 1])
def test_a_table_of_another_version_is_refused_naming_both_versions(
    tmp_path: Path, offset: int
) -> None:
    found = capability.SCHEMA_VERSION + offset
    said = _refusal(tmp_path, table_document(version=found))

    assert "schema_version" in said
    assert repr(found) in said, said
    assert f"version {capability.SCHEMA_VERSION}" in said, said


def test_a_version_written_as_text_is_another_version(tmp_path: Path) -> None:
    found = str(capability.SCHEMA_VERSION)
    said = _refusal(tmp_path, table_document(version=found))

    assert repr(found) in said, said


def test_a_table_that_states_no_version_is_refused(tmp_path: Path) -> None:
    document = table_document()
    del document["schema_version"]
    said = _refusal(tmp_path, document)

    assert "schema_version" in said
    assert f"version {capability.SCHEMA_VERSION}" in said, said


@pytest.mark.parametrize("field", ["quality", "throughput_tok_s"])
def test_a_reading_keyed_by_an_undeclared_class_is_refused_by_that_name(
    tmp_path: Path, field: str
) -> None:
    stray = "30gb"
    assert stray not in {c["id"] for c in CLASSES}
    model = row("invented-model-a")
    figure = "humaneval_plus_pass1" if field == "quality" else "value"
    model[field] = [*model[field], reading(stray, **{figure: 0.5})]

    said = _refusal(tmp_path, table_document(rows=[model]))

    assert repr(stray) in said, said
    assert "invented-model-a" in said, said


def test_a_reading_that_names_no_class_is_refused(tmp_path: Path) -> None:
    model = row("invented-model-a")
    del model["quality"][0]["card_class"]

    said = _refusal(tmp_path, table_document(rows=[model]))

    assert "card_class" in said, said
    assert "invented-model-a" in said, said


def test_a_table_that_declares_no_classes_is_refused_by_that_name(
    tmp_path: Path,
) -> None:
    document = table_document()
    del document["card_classes"]

    assert "card_classes" in _refusal(tmp_path, document)


@pytest.mark.parametrize("key", ["id", "label", "memory_gb"])
def test_a_class_missing_a_key_is_refused_by_that_key(tmp_path: Path, key: str) -> None:
    classes = [dict(c) for c in CLASSES]
    del classes[0][key]

    said = _refusal(tmp_path, table_document(classes=classes))

    assert repr(key) in said, said


def test_a_class_declared_twice_is_refused_by_its_id(tmp_path: Path) -> None:
    twice = [dict(CLASSES[0]), dict(CLASSES[0])]

    said = _refusal(tmp_path, table_document(classes=twice))

    assert repr(CLASSES[0]["id"]) in said, said
