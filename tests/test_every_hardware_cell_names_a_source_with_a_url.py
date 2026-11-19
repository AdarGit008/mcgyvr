"""Every hardware cell names a source with a URL.

A cell of the shipped hardware table that carries a value, or states that a
thing is not there, names the page it was read from; that id must be one of the
table's listed sources, and every listed source has an https URL and the day it
was read. The table lists no source that no cell cites.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Iterator
from typing import Any

from mcgyvr import hardware_table
from tests._paths import REPO

SHIPPED = REPO / "data" / hardware_table.TABLE_FILENAME


def _cells(node: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(node, dict) and "v" in node:
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            if path or key not in ("id", "vendor", "kind"):
                yield from _cells(value, f"{path}.{key}" if path else key)


def _raw() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(SHIPPED.read_text(encoding="utf-8"))
    return loaded


def test_every_listed_source_has_an_https_url_and_a_read_date() -> None:
    sources = _raw()["sources"]
    assert sources
    for source in sources:
        assert set(source) == set(hardware_table.SOURCE_KEYS), source
        assert source["url"].startswith("https://"), source
        assert source["publisher"], source
        datetime.date.fromisoformat(source["read"])


def test_every_cell_with_a_value_names_a_listed_source() -> None:
    raw = _raw()
    listed = {source["id"] for source in raw["sources"]}
    unsourced, unlisted = [], []
    for row in raw["rows"]:
        for field, cell in _cells(row):
            src = cell.get("src")
            if cell["v"] is not None and src is None:
                unsourced.append(f"{row['id']} {field}")
            if src is not None and src not in listed:
                unlisted.append(f"{row['id']} {field} {src}")
    assert not unsourced, unsourced[:20]
    assert not unlisted, unlisted[:20]


def test_every_listed_source_is_cited_by_a_cell() -> None:
    raw = _raw()
    cited = {
        cell["src"]
        for row in raw["rows"]
        for _, cell in _cells(row)
        if cell.get("src") is not None
    }
    assert {source["id"] for source in raw["sources"]} == cited


def test_the_loader_resolves_every_cited_source_to_its_url() -> None:
    table = hardware_table.load(SHIPPED)
    for row in table.rows:
        for cell in row.cells.values():
            if cell.source is not None:
                assert table.sources[cell.source].url.startswith("https://")
