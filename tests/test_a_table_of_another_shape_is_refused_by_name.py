"""A capability table of another shape is refused, and the refusal says why.

Promises:

* A table of any version but the one this code reads is refused, and the
  refusal names the version it found and the version this code reads. A reader
  that ignored unknown keys would read an older table's rows as if they meant
  what this version's rows mean, and nothing would say so.
* A key the code does not declare for its level is refused by name, at every
  level of the table: the loader ignores nothing silently. An object stands
  only where the table holds entries; under a key that holds a value it is
  refused by that key, at every level and however deep in a list, since its
  own keys would be keys nobody declared.
* A model row without a key it needs, and a model's size that is not a
  number, are refused by the name of the entry and the key.
* Every refusal names the file it refused, and none is a raw ``TypeError`` or
  ``ValueError`` out of the loader's insides.

Every table here is generated (:mod:`tests.table_fixture`), with invented
model ids and numbers.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import capability
from mcgyvr.capability import CapabilityTableError, load
from tests.table_fixture import (
    row,
    table_document,
    table_document_with_every_block,
    write_table,
)


def _refusal(tmp_path: Path, document: dict[str, Any]) -> str:
    """The refusal of ``document``, which always names the file it refused."""
    path = write_table(tmp_path, document)
    with pytest.raises(CapabilityTableError) as refused:
        load(path)
    said = str(refused.value)
    assert str(path) in said, said
    return said


def test_a_table_of_the_shape_this_code_reads_loads_its_rows(tmp_path: Path) -> None:
    """The control: without it every refusal below could be a loader that
    refuses everything."""
    ids = ["invented-model-a", "invented-model-b"]
    document = table_document(rows=[row(model_id) for model_id in ids])

    assert [m.id for m in load(write_table(tmp_path, document)).models] == ids


def test_a_table_with_an_entry_at_every_level_loads(tmp_path: Path) -> None:
    """The control for the refusals that change one level of this document."""
    document = table_document_with_every_block()

    assert load(write_table(tmp_path, document)).models


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


# --- model rows --------------------------------------------------------------


def test_a_model_row_that_is_not_an_object_is_refused_by_its_place(
    tmp_path: Path,
) -> None:
    document = table_document()
    document["models"].append("invented-model-b")

    said = _refusal(tmp_path, document)

    assert "models[1]" in said, said


# --- the loader ignores nothing silently -------------------------------------

#: An invented key no level of the table declares.
UNDECLARED = "invented_key"


def _entry_at(level: str, document: dict[str, Any]) -> dict[str, Any]:
    """The one entry of ``document`` at the level the product calls ``level``."""
    entries: dict[str, Any] = {
        "table": document,
        "model row": document["models"][0],
        "backends block": document["backends"],
        "backend": document["backends"]["some-server"],
    }
    entry: dict[str, Any] = entries[level]
    return entry


@pytest.mark.parametrize("level", sorted(capability.DECLARED_KEYS))
def test_a_key_the_code_does_not_declare_is_refused_at_every_level(
    tmp_path: Path, level: str
) -> None:
    document = table_document_with_every_block()
    assert UNDECLARED not in capability.DECLARED_KEYS[level]
    _entry_at(level, document)[UNDECLARED] = "anything"

    said = _refusal(tmp_path, document)

    assert repr(UNDECLARED) in said, said


# --- an object sits only where the table declares entries --------------------

#: A value that would carry keys of its own under a key that holds a value, not
#: entries, one way per nesting the refusal must see through.
NESTED_OBJECTS: dict[str, Callable[[], Any]] = {
    "an-object": lambda: {UNDECLARED: "anything"},
    "a-list-holding-an-object": lambda: ["text", {UNDECLARED: "anything"}],
    "a-list-holding-a-list-holding-an-object": lambda: [[{UNDECLARED: "anything"}]],
}


def test_every_container_is_a_declared_key_of_its_level() -> None:
    containers = capability.CONTAINER_KEYS

    assert set(containers) == set(capability.DECLARED_KEYS)
    for level, keys in containers.items():
        assert keys <= capability.DECLARED_KEYS[level], level


@pytest.mark.parametrize("nested", sorted(NESTED_OBJECTS))
@pytest.mark.parametrize("level", sorted(capability.DECLARED_KEYS))
def test_an_object_under_a_key_that_holds_a_value_is_refused_at_every_level(
    tmp_path: Path, level: str, nested: str
) -> None:
    """Every declared key of the level that is not a container, one at a time:
    were an object accepted there, its keys would be keys nobody declared."""
    containers = capability.CONTAINER_KEYS[level]
    values = sorted(capability.DECLARED_KEYS[level] - containers)
    assert values, level
    for key in values:
        document = table_document_with_every_block()
        _entry_at(level, document)[key] = NESTED_OBJECTS[nested]()

        said = _refusal(tmp_path, document)

        # The version is refused by its own check, before any other.
        assert repr(key) in said if key != "schema_version" else key in said, said


# --- every refusal is by name, never a raw error out of the loader -----------

#: Values a number cannot be given as.
NOT_NUMBERS: dict[str, Any] = {
    "text": "fast",
    "a-number-written-as-text": "0.5",
    "null": None,
    "a-boolean": True,
}


@pytest.mark.parametrize("given", sorted(NOT_NUMBERS))
@pytest.mark.parametrize(
    "key", ["params_b", "active_params_b", "vram_gb_working", "weights_gb"]
)
def test_a_model_size_that_is_not_a_number_is_refused_by_its_row(
    tmp_path: Path, key: str, given: str
) -> None:
    model = row("invented-model-a", **{key: NOT_NUMBERS[given]})

    said = _refusal(tmp_path, table_document(rows=[model]))

    assert "models[0] ('invented-model-a')" in said, said
    assert repr(key) in said, said


def test_a_model_with_numbers_where_it_carries_numbers_loads(tmp_path: Path) -> None:
    """The control: whole numbers and fractions both load."""
    model = row("invented-model-a", params_b=5, active_params_b=1.5)

    loaded = load(write_table(tmp_path, table_document(rows=[model])))

    assert loaded.models[0].params_b == 5.0


@pytest.mark.parametrize(
    "key", ["id", "family", "params_b", "vram_gb_working", "weights_gb"]
)
def test_a_model_row_missing_a_required_key_is_refused_by_its_place(
    tmp_path: Path, key: str
) -> None:
    model = row("invented-model-a")
    del model[key]

    said = _refusal(tmp_path, table_document(rows=[model]))

    assert "models[0]" in said, said
    assert repr(key) in said, said


def test_a_file_that_is_not_text_is_refused_by_its_name(tmp_path: Path) -> None:
    path = tmp_path / "capability-table.json"
    path.write_bytes(b"\xff\xfe{")

    with pytest.raises(CapabilityTableError) as refused:
        load(path)

    assert str(path) in str(refused.value), refused.value
