"""A file's geometry is kept with one source and date, and is read offline.

As #611 has it: "cache the GGUF header
geometry row as its own cache file per repo@revision/file, one source+date for
the whole row (so MoE can be sized offline by serving.fit)". The
plan is sized by the product's serving sizer, which reads one
``ggufscan`` row; a record's sizes alone cannot place an MoE.

Promises:

* A row is filed per file at a revision under
  ``$MCGYVR_HOME/knowledge/geometry/`` and read back as it was written, with
  one kind (a fact), one source (the header of that file at that revision,
  read over HTTP Range) and one day for every number in it.
* The shipped rows (``data/model-geometry.json``) are the headers of the
  shipped catalog's own files, each the size the catalog says, and every
  number in that file sits in a row that says its kind, source and date.
* Offline, a cached row is read before a shipped one of the same file.
* A cache file that cannot be read, or that says another file or a source that
  is not that file's header, is not read: it is named, with why, and the
  shipped rows still answer.

The files and rows here are invented, except the shipped ones, which are read.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.knowledge import geometry as kg
from mcgyvr.knowledge import store as ks
from mcgyvr.knowledge.record import KnowledgeError

#: An invented file, at an invented revision.
INVENTED = ("example-org/Invented-GGUF", "1" * 40, "invented-Q4_K_M.gguf")


def _row(file: str = INVENTED[2], size: int = 1_000_000) -> dict[str, Any]:
    return {"file": file, "size_bytes": size, "n_layer": 2, "kv_layers": []}


def _numbers(
    node: Any, where: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], Any]]:
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


def test_a_row_is_filed_per_file_and_read_back_with_one_source_and_date() -> None:
    repo, revision, file = INVENTED
    path = kg.write(repo, revision, file, _row(), today=date(2026, 10, 7))

    assert path.parent == ks.cache_dir() / "geometry"
    found = kg.load()
    one = found.rows[(repo, revision, file)]
    assert one.row == _row()
    assert one.source == f"gguf-header-range:{repo}@{revision}/{file}"
    assert one.read_at == date(2026, 10, 7)
    assert one.origin == ks.CACHE
    assert found.skipped == ()


def test_the_shipped_rows_are_the_shipped_catalogs_files() -> None:
    rows = kg.load().rows
    for record in ks.shipped():
        assert record.weights is not None
        one = rows.get(
            (record.weights.repo, record.weights.revision, record.weights.file)
        )
        assert one is not None, f"no shipped geometry for {record.model_id}"
        assert one.origin == ks.SHIPPED
        assert one.row["size_bytes"] == record.size_bytes.value
        assert Path(str(one.row["file"])).name == record.weights.file


def test_every_number_of_the_shipped_rows_sits_in_a_row_saying_where_it_came_from() -> (
    None
):
    document = json.loads(kg.shipped_path().read_text(encoding="utf-8"))
    for where, _value in _numbers(document):
        if where[-1] == "schema_version" and len(where) in (1, 3):
            continue  # the format's version, of the file and of each row
        assert where[0] == "geometries" and where[2:4] == ("geometry", "value"), where
        held = document["geometries"][int(where[1])]["geometry"]
        assert held["kind"] == "fact"
        assert held["source"].startswith("gguf-header-range:")
        date.fromisoformat(held["read_at"])


def test_a_cached_row_is_read_before_the_shipped_one() -> None:
    record = ks.shipped()[0]
    assert record.weights is not None
    w = record.weights
    shipped_row = kg.load().of(w)
    assert shipped_row is not None
    changed = dict(shipped_row.row, n_layer=-1)
    kg.write(w.repo, w.revision, w.file, changed, today=date(2099, 1, 2))

    one = kg.load().of(w)

    assert one is not None
    assert one.origin == ks.CACHE
    assert one.row["n_layer"] == -1


@pytest.mark.parametrize(
    ("document", "why"),
    [
        ("{ not json", "cannot read"),
        ({"schema_version": 99}, "schema_version"),
        (
            {
                "schema_version": 1,
                "weights": dict(
                    zip(("repo", "revision", "file"), INVENTED, strict=True)
                ),
                "geometry": {
                    "value": _row(file="another.gguf"),
                    "kind": "fact",
                    "source": "gguf-header-range:{}@{}/{}".format(*INVENTED),
                    "read_at": "2026-10-07",
                },
            },
            "another.gguf",
        ),
        (
            {
                "schema_version": 1,
                "weights": dict(
                    zip(("repo", "revision", "file"), INVENTED, strict=True)
                ),
                "geometry": {
                    "value": _row(),
                    "kind": "fact",
                    "source": "hub-api:somewhere-else",
                    "read_at": "2026-10-07",
                },
            },
            "source",
        ),
    ],
)
def test_a_cache_file_that_cannot_be_read_is_named_and_the_shipped_rows_answer(
    document: Any, why: str
) -> None:
    folder = kg.cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "broken.json"
    text = document if isinstance(document, str) else json.dumps(document)
    path.write_text(text, encoding="utf-8")

    found = kg.load()

    ((skipped, reason),) = found.skipped
    assert skipped == path
    assert why in reason
    assert {one.key for one in kg.shipped()} <= set(found.rows)


def test_a_row_written_for_another_file_is_refused_before_it_is_filed() -> None:
    repo, revision, file = INVENTED
    with pytest.raises(KnowledgeError):
        kg.write(
            repo, revision, file, _row(file="another.gguf"), today=date(2026, 10, 7)
        )
    assert not kg.cache_dir().exists() or not list(kg.cache_dir().iterdir())
