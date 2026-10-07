"""Every number in the model knowledge says its source and its date.

Owner, 2026-10-07: "Every number records its source and date. Offline falls
back to the shipped catalog."

Promises:

* Every number of the shipped catalog, at any depth, is the ``value`` of an
  object that says what kind of number it is (a fact, an estimate or a
  reading), where it came from (a source the knowledge layer names, then
  where at that source) and the day it was read. The walk is over the file,
  not over the fields the code knows, so a number added under a new key fails
  here until it says the same.
* The shipped catalog holds no reading. A reading is a number taken on a
  machine, and the only machines a shipped number could have been read on are
  the project's own.
* A record that leaves any of that out is refused by name when it is read:
  a bare number, a number with no source or no date, a date that is not a
  day, a source the layer does not name, a kind outside the closed list, a
  key the record does not have, a score from a board the layer does not name
  or under another metric than that board's.
* What the cache writer files passes the same walk, so the cache cannot hold
  a number the catalog could not.

The records here are invented; the shipped catalog is read, never restated.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks

#: The one number of a knowledge document that is not knowledge: the version
#: of the format, at the top of the document.
FORMAT_KEY = "schema_version"


def _numbers(
    node: Any, where: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Every number in a JSON document, with the path to it."""
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        yield where, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _numbers(value, (*where, str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _numbers(value, (*where, str(index)))


def _at(document: Any, where: tuple[str, ...]) -> Any:
    node = document
    for step in where:
        node = node[int(step)] if isinstance(node, list) else node[step]
    return node


def _unsaid(document: dict[str, Any]) -> list[str]:
    """The numbers of ``document`` that do not say their kind, source and date."""
    unsaid: list[str] = []
    for where, _value in _numbers(document):
        if where == (FORMAT_KEY,):
            continue
        shown = "/".join(where)
        if where[-1] != "value":
            unsaid.append(f"{shown}: a bare number")
            continue
        holder = _at(document, where[:-1])
        if holder.get("kind") not in kr.KINDS:
            unsaid.append(f"{shown}: kind {holder.get('kind')!r}")
        source = holder.get("source")
        if not isinstance(source, str) or source.partition(":")[0] not in kr.SOURCES:
            unsaid.append(f"{shown}: source {source!r}")
        elif not source.partition(":")[2]:
            unsaid.append(f"{shown}: source {source!r} says no where")
        read_at = holder.get("read_at")
        try:
            date.fromisoformat(str(read_at))
        except ValueError:
            unsaid.append(f"{shown}: read_at {read_at!r}")
    return unsaid


def _shipped_document() -> dict[str, Any]:
    loaded = json.loads(ks.catalog_path().read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_every_number_of_the_shipped_catalog_says_its_kind_source_and_date() -> None:
    document = _shipped_document()
    assert list(_numbers(document)), "the shipped catalog holds no number at all"
    assert _unsaid(document) == []


def test_the_shipped_catalog_holds_no_reading() -> None:
    document = _shipped_document()
    readings = [
        "/".join(where)
        for where, _value in _numbers(document)
        if where[-1] == "value" and _at(document, where[:-1]).get("kind") == "reading"
    ]
    assert readings == []


def test_the_shipped_catalog_is_read_as_records_whose_numbers_all_say_so() -> None:
    records = ks.shipped()
    assert records
    for one in records:
        for name, number in one.numbers():
            assert number.kind in kr.KINDS, (one.key, name)
            assert number.source.partition(":")[0] in kr.SOURCES, (one.key, name)
            assert isinstance(number.read_at, date), (one.key, name)


# --- refusals -----------------------------------------------------------------

#: An invented record, valid as it stands. Each refusal below breaks one thing.
_INVENTED: dict[str, Any] = {
    "model_id": "invented-org/Invented-7B",
    "quant": "Q4_K_M",
    "engines": ["llama.cpp"],
    "weights": {
        "repo": "invented-org/Invented-7B-GGUF",
        "revision": "0" * 40,
        "file": "invented-7b-q4_k_m.gguf",
        "sha256": "f" * 64,
    },
    "size_bytes": {
        "value": 4_000_000_000,
        "kind": "fact",
        "source": "hub-api:invented-org/Invented-7B-GGUF@" + "0" * 40,
        "read_at": "2026-10-07",
    },
    "context_length": {
        "value": 32768,
        "kind": "fact",
        "source": "hub-config:invented-org/Invented-7B@" + "0" * 40,
        "read_at": "2026-10-07",
    },
    "kv_bytes_per_token": {
        "value": 57344,
        "kind": "fact",
        "source": "gguf-header-range:invented-org/Invented-7B-GGUF@" + "0" * 40,
        "read_at": "2026-10-07",
    },
    "recurrent_bytes_per_slot": {
        "value": 0,
        "kind": "fact",
        "source": "gguf-header-range:invented-org/Invented-7B-GGUF@" + "0" * 40,
        "read_at": "2026-10-07",
    },
    "scores": [
        {
            "board": "bfcl",
            "metric": "overall_acc",
            "value": 0.5,
            "kind": "fact",
            "source": "board:bfcl@2026-10-07",
            "read_at": "2026-10-07",
        }
    ],
}


def _document(model: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": kr.SCHEMA_VERSION, "models": [model]}


def test_the_invented_record_is_read() -> None:
    (one,) = kr.parse_document(_document(_INVENTED), "invented", shipped=True)
    assert one.size_bytes.value == _INVENTED["size_bytes"]["value"]
    assert _unsaid(kr.dump_document((one,))) == []


def _broken(path: tuple[str | int, ...], value: Any) -> dict[str, Any]:
    """The invented record with the field at ``path`` set to ``value``
    (removed when ``value`` is ``...``)."""
    model = copy.deepcopy(_INVENTED)
    node: Any = model
    for step in path[:-1]:
        node = node[step]
    if value is ...:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return model


@pytest.mark.parametrize(
    ("path", "value", "named"),
    [
        (("size_bytes",), 4_000_000_000, "size_bytes"),
        (("size_bytes", "source"), ..., "source"),
        (("size_bytes", "read_at"), ..., "read_at"),
        (("size_bytes", "read_at"), "last week", "read_at"),
        (("size_bytes", "source"), "a friend:told me", "source"),
        (("size_bytes", "source"), "hub-api:", "source"),
        (("size_bytes", "kind"), "guess", "kind"),
        (("size_bytes", "value"), True, "size_bytes"),
        (("context_length", "value"), 0, "context_length"),
        (
            ("params_b",),
            {
                "value": 7,
                "kind": "fact",
                "source": "hub-api:x",
                "read_at": "2026-10-07",
            },
            "params_b",
        ),
        (("scores", 0, "board"), "a-board-nobody-names", "board"),
        (("scores", 0, "metric"), "rating", "metric"),
        (("scores", 0, "source"), ..., "source"),
        (("size_bytes", "kind"), "reading", "reading"),
    ],
)
def test_a_number_that_does_not_say_where_and_when_is_refused_by_name(
    path: tuple[str | int, ...], value: Any, named: str
) -> None:
    with pytest.raises(kr.KnowledgeError, match=named):
        kr.parse_document(_document(_broken(path, value)), "invented", shipped=True)


def test_a_reading_must_say_it_was_measured_and_a_measurement_must_be_a_reading() -> (
    None
):
    reading = {
        "value": 4_000_000_000,
        "kind": "reading",
        "source": "measured:a-rig",
        "read_at": "2026-10-07",
    }
    (one,) = kr.parse_document(
        _document(_broken(("size_bytes",), reading)), "a cache file", shipped=False
    )
    assert one.size_bytes.kind == "reading"
    with pytest.raises(kr.KnowledgeError, match="reading"):
        kr.parse_document(
            _document(_broken(("size_bytes",), {**reading, "source": "hub-api:x"})),
            "a cache file",
            shipped=False,
        )
    with pytest.raises(kr.KnowledgeError, match="measured"):
        kr.parse_document(
            _document(_broken(("size_bytes",), {**reading, "kind": "fact"})),
            "a cache file",
            shipped=False,
        )


def test_a_self_reported_score_is_an_estimate() -> None:
    score = {**_INVENTED["scores"][0], "source": "model-card:invented-org/Invented-7B"}
    with pytest.raises(kr.KnowledgeError, match="estimate"):
        kr.parse_document(
            _document(_broken(("scores", 0), score)), "invented", shipped=True
        )
    (one,) = kr.parse_document(
        _document(_broken(("scores", 0), {**score, "kind": "estimate"})),
        "invented",
        shipped=True,
    )
    assert one.scores[0].value.kind == "estimate"


def test_what_the_cache_writer_files_says_its_source_and_date() -> None:
    (one,) = kr.parse_document(_document(_INVENTED), "invented", shipped=True)
    written: Path = ks.write(one)
    document = json.loads(written.read_text(encoding="utf-8"))
    assert _unsaid(document) == []
    assert written.parent == ks.cache_dir()
