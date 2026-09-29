"""A capability table that carries a quality figure is refused, by the key's name.

Promise: a key that holds a quality figure or a benchmark score, put at any
closed level of the table in the shape such a figure would take there, is
refused, and the refusal names the key and the file. The loader has no level
whose keys describe a quality metric, so no such figure can enter the table
without first being declared in code, where a reviewer reads it.

A level is closed when every key of it is one the product declares
(:data:`mcgyvr.capability.DECLARED_KEYS`). Under ``backends`` a key names a
backend rather than a fact, so that block is not closed, and each backend
under it is.

Every table here is generated (:mod:`tests.table_fixture`), with invented
classes, model ids and numbers.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import capability
from mcgyvr.capability import CapabilityTableError, load
from tests.table_fixture import table_document_with_every_block, write_table

#: The level whose keys name backends, not facts.
OPEN_LEVEL = "backends block"


def _first_class(document: dict[str, Any]) -> str:
    return str(document["card_classes"][0]["id"])


#: Where each closed level's entry sits in a document with an entry at every level.
ENTRY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "table": lambda d: d,
    "card class": lambda d: d["card_classes"][0],
    "harness caveat": lambda d: d["harness_caveats"][0],
    "model row": lambda d: d["models"][0],
    "reading": lambda d: d["models"][0]["throughput_tok_s"][0],
    "backend": lambda d: d["backends"]["some-server"],
    "concurrency finding": lambda d: d["concurrency_findings"][0],
}


def _reading(document: dict[str, Any], figure: str) -> dict[str, Any]:
    return {figure: 0.5, "backend": "some-server", "card_class": _first_class(document)}


#: A quality figure under each name such a figure has been given, in the shape
#: it would take: a list of readings, a map of scores, a metric's description,
#: or the figure itself.
QUALITY: dict[str, Callable[[dict[str, Any]], Any]] = {
    "quality": lambda d: [_reading(d, "humaneval_plus_pass1")],
    "invalid_measurements": lambda d: [_reading(d, "humaneval_plus_pass1")],
    "disputed_measurements": lambda d: [_reading(d, "humaneval_plus_pass1")],
    "capabilities": lambda d: {"invented": 0.5},
    "quality_metric": lambda d: {"name": "invented", "dataset": "invented"},
    "humaneval_plus_pass1": lambda d: 0.5,
    "humaneval_pass1": lambda d: 0.5,
    "pass_at_1": lambda d: 0.5,
    "benchmark_score": lambda d: 0.5,
}


def test_every_closed_level_is_tried() -> None:
    """Without it a level that does declare a quality key would go untried."""
    closed = set(capability.DECLARED_KEYS) - {OPEN_LEVEL}

    assert set(ENTRY) == closed


def test_a_document_with_an_entry_at_every_level_loads(tmp_path: Path) -> None:
    """The control: without it every refusal below could be a loader that
    refuses everything."""
    assert load(write_table(tmp_path, table_document_with_every_block())).models


@pytest.mark.parametrize("key", sorted(QUALITY))
@pytest.mark.parametrize("level", sorted(ENTRY))
def test_a_quality_key_at_any_closed_level_is_refused_by_its_name(
    tmp_path: Path, level: str, key: str
) -> None:
    document = table_document_with_every_block()
    ENTRY[level](document)[key] = QUALITY[key](document)
    path = write_table(tmp_path, document)

    with pytest.raises(CapabilityTableError) as refused:
        load(path)

    said = str(refused.value)
    assert repr(key) in said, said
    assert str(path) in said, said
