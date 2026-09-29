"""A capability table of another shape is refused, and the refusal says why.

Promises:

* A table of any version but the one this code reads is refused, and the
  refusal names the version it found and the version this code reads. A reader
  that ignored unknown keys would read an older table's rows as if they meant
  what this version's rows mean, and nothing would say so.
* Every reading names the card class it was taken for, and that class is one
  the table declares. A reading keyed by a class nobody declared is an estimate
  for nothing the table can describe, and it is refused by that class's name.
  The same holds wherever else the table gives something for a class: a
  backend and a finding.
* A class is declared with a non-empty id, a non-empty label a user reads and
  its nominal memory as a positive number; one that leaves any of these out,
  or gives one of another shape, is refused by the name of the entry.
* A key the code does not declare for its level is refused by name, at every
  level of the table: the loader ignores nothing silently.
* Every refusal names the file it refused, and none is a raw ``TypeError`` or
  ``ValueError`` out of the loader's insides.

Every table here is generated (:mod:`tests.table_fixture`), with invented
classes, model ids and numbers, over more than one shape of class set.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import capability
from mcgyvr.capability import CapabilityTableError, load
from tests.table_fixture import (
    CLASS_SHAPES,
    CLASSES,
    reading,
    row,
    table_document,
    table_document_with_every_block,
    write_table,
)

#: A class id no generated document declares.
STRAY = "77gb"


def _refusal(tmp_path: Path, document: dict[str, Any]) -> str:
    """The refusal of ``document``, which always names the file it refused."""
    path = write_table(tmp_path, document)
    with pytest.raises(CapabilityTableError) as refused:
        load(path)
    said = str(refused.value)
    assert str(path) in said, said
    return said


@pytest.mark.parametrize("shape", sorted(CLASS_SHAPES))
def test_a_table_of_the_shape_this_code_reads_loads_with_its_classes(
    tmp_path: Path, shape: str
) -> None:
    """The control: without it every refusal below could be a loader that
    refuses everything."""
    classes = CLASS_SHAPES[shape]
    document = table_document(
        classes=classes,
        rows=[
            row(f"invented-model-{c['id']}", card_class=str(c["id"])) for c in classes
        ],
    )
    table = load(write_table(tmp_path, document))

    assert [(c.id, c.label, c.memory_gb) for c in table.card_classes] == [
        (c["id"], c["label"], c["memory_gb"]) for c in classes
    ]
    declared = {c.id for c in table.card_classes}
    readings = [
        m for model in table.models for m in (*model.quality, *model.throughput)
    ]
    assert readings
    assert {m.card_class for m in readings} == declared


@pytest.mark.parametrize("shape", sorted(CLASS_SHAPES))
def test_a_table_with_an_entry_at_every_level_loads(tmp_path: Path, shape: str) -> None:
    """The control for the refusals that change one level of this document."""
    document = table_document_with_every_block(classes=CLASS_SHAPES[shape])

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


# --- readings ----------------------------------------------------------------


@pytest.mark.parametrize("field", capability.READING_LISTS)
def test_a_reading_keyed_by_an_undeclared_class_is_refused_by_that_name(
    tmp_path: Path, field: str
) -> None:
    assert STRAY not in {c["id"] for c in CLASSES}
    model = row("invented-model-a")
    figure = "value" if field == "throughput_tok_s" else "humaneval_plus_pass1"
    model[field] = [*model.get(field, []), reading(STRAY, **{figure: 0.5})]

    said = _refusal(tmp_path, table_document(rows=[model]))

    assert repr(STRAY) in said, said
    assert "invented-model-a" in said, said
    assert field in said, said


def test_a_reading_that_names_no_class_is_refused(tmp_path: Path) -> None:
    model = row("invented-model-a")
    del model["quality"][0]["card_class"]

    said = _refusal(tmp_path, table_document(rows=[model]))

    assert "card_class" in said, said
    assert "invented-model-a" in said, said


def _class_as_list(model: dict[str, Any]) -> None:
    model["quality"][0]["card_class"] = [CLASSES[0]["id"]]


def _class_as_number(model: dict[str, Any]) -> None:
    model["quality"][0]["card_class"] = 5


def _reading_as_number(model: dict[str, Any]) -> None:
    model["quality"] = [0.5]


def _readings_as_null(model: dict[str, Any]) -> None:
    model["quality"] = None


def _readings_as_object(model: dict[str, Any]) -> None:
    model["throughput_tok_s"] = {"value": 3.0}


@pytest.mark.parametrize(
    "spoil",
    [
        _class_as_list,
        _class_as_number,
        _reading_as_number,
        _readings_as_null,
        _readings_as_object,
    ],
)
def test_a_reading_of_another_shape_is_refused_by_its_row(
    tmp_path: Path, spoil: Callable[[dict[str, Any]], None]
) -> None:
    model = row("invented-model-a")
    spoil(model)

    said = _refusal(tmp_path, table_document(rows=[model]))

    assert "invented-model-a" in said, said


def test_a_model_row_that_is_not_an_object_is_refused_by_its_place(
    tmp_path: Path,
) -> None:
    document = table_document()
    document["models"].append("invented-model-b")

    said = _refusal(tmp_path, document)

    assert "models[1]" in said, said


# --- classes -----------------------------------------------------------------


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


#: A declared class spoiled one way at a time: the whole entry, or one value.
SPOILED_CLASSES: dict[str, Any] = {
    "an-entry-that-is-text": "some class",
    "an-entry-that-is-a-number": 7,
    "memory-as-text": {"memory_gb": "seven"},
    "memory-as-null": {"memory_gb": None},
    "memory-as-true": {"memory_gb": True},
    "memory-of-zero": {"memory_gb": 0},
    "memory-below-zero": {"memory_gb": -3},
    "an-empty-id": {"id": ""},
    "an-id-that-is-a-number": {"id": 7},
    "a-blank-label": {"label": "  "},
    "a-label-that-is-null": {"label": None},
}


@pytest.mark.parametrize("spoiled", sorted(SPOILED_CLASSES))
def test_a_class_of_another_shape_is_refused_by_its_place(
    tmp_path: Path, spoiled: str
) -> None:
    change = SPOILED_CLASSES[spoiled]
    classes: list[Any] = [dict(c) for c in CLASSES]
    classes[-1] = {**classes[-1], **change} if isinstance(change, dict) else change
    document = table_document(classes=classes)

    said = _refusal(tmp_path, document)

    assert f"card_classes[{len(classes) - 1}]" in said, said


# --- a backend and a finding are given for a declared class ------------------


def _backend(document: dict[str, Any]) -> dict[str, Any]:
    backend: dict[str, Any] = document["backends"]["some-server"]
    return backend


def _finding(document: dict[str, Any]) -> dict[str, Any]:
    finding: dict[str, Any] = document["concurrency_findings"][0]
    return finding


@pytest.mark.parametrize("where", [_backend, _finding], ids=["backend", "finding"])
def test_a_backend_or_a_finding_for_an_undeclared_class_is_refused(
    tmp_path: Path, where: Callable[[dict[str, Any]], dict[str, Any]]
) -> None:
    document = table_document_with_every_block()
    where(document)["card_class"] = STRAY

    said = _refusal(tmp_path, document)

    assert repr(STRAY) in said, said


# --- the loader ignores nothing silently -------------------------------------

#: An invented key no level of the table declares.
UNDECLARED = "invented_key"


def _entry_at(level: str, document: dict[str, Any]) -> dict[str, Any]:
    """The one entry of ``document`` at the level the product calls ``level``."""
    model = document["models"][0]
    entries: dict[str, Any] = {
        "table": document,
        "quality metric": document["quality_metric"],
        "card class": document["card_classes"][0],
        "harness caveat": document["harness_caveats"][0],
        "model row": model,
        "reading": model["disputed_measurements"][0],
        "backends block": document["backends"],
        "backend": document["backends"]["some-server"],
        "concurrency finding": document["concurrency_findings"][0],
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


@pytest.mark.parametrize("field", capability.READING_LISTS)
def test_an_undeclared_key_on_any_reading_is_refused(
    tmp_path: Path, field: str
) -> None:
    document = table_document_with_every_block()
    document["models"][0][field][0][UNDECLARED] = "anything"

    said = _refusal(tmp_path, document)

    assert repr(UNDECLARED) in said, said
    assert field in said, said


# --- an object sits only where the table declares entries --------------------

#: A value that would carry keys of its own under a key that holds a value, not
#: entries, one way per nesting the refusal must see through.
NESTED_OBJECTS: dict[str, Callable[[], Any]] = {
    "an-object": lambda: {UNDECLARED: "anything"},
    "a-list-holding-an-object": lambda: ["text", {UNDECLARED: "anything"}],
    "a-list-holding-a-list-holding-an-object": lambda: [[{UNDECLARED: "anything"}]],
}


def test_every_container_is_a_declared_key_of_its_level() -> None:
    containers = capability.CONTAINER_KEYS  # type: ignore[attr-defined]

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
    containers = capability.CONTAINER_KEYS[level]  # type: ignore[attr-defined]
    values = sorted(capability.DECLARED_KEYS[level] - containers)
    assert values, level
    for key in values:
        document = table_document_with_every_block()
        _entry_at(level, document)[key] = NESTED_OBJECTS[nested]()

        said = _refusal(tmp_path, document)

        # The version is refused by its own check, before any other.
        assert repr(key) in said if key != "schema_version" else key in said, said
