"""A hardware cell is a value, a stated no, or unknown, and never one for another.

The loader of the hardware table tells the three states of a cell apart: a page
gives the value; a page states the thing is not there (false, an empty list, or
no value with the page cited); or no page read gives it (no value, no page, or
a field the row does not carry). It refuses a table that is not the shape it
declares rather than read it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hardware_table
from mcgyvr.hardware_table import NO, UNKNOWN, VALUE, HardwareTableError
from tests._paths import REPO

SOURCE = {
    "id": "s1",
    "url": "https://vendor.example/card",
    "publisher": "vendor.example",
    "official": True,
    "read": "2026-01-02",
}


def _table(cells: dict[str, Any], **top: Any) -> dict[str, Any]:
    row = {"id": "card-1", "vendor": "acme", "kind": "gpu", **cells}
    return {
        "schema": 1,
        "built": "2026-01-03",
        "sources": [SOURCE],
        "rows": [row],
        **top,
    }


def _write(tmp_path: Path, table: dict[str, Any]) -> Path:
    path = tmp_path / hardware_table.TABLE_FILENAME
    path.write_text(json.dumps(table), encoding="utf-8")
    return path


def _load(tmp_path: Path, table: dict[str, Any]) -> hardware_table.HardwareTable:
    return hardware_table.load(_write(tmp_path, table))


CELLS = {
    "memory": {
        "size_gb": {"v": 16, "src": "s1", "how": "stated", "official": True},
        "type": {"v": None},
    },
    "formats": {
        "fp16": {"v": False, "src": "s1"},
        "matrix": {
            "precisions": {"v": [], "src": "s1"},
            "name": {"v": None, "src": "s1"},
        },
        "int8_dot": {"v": True, "src": "s1", "scope": "architecture"},
    },
}


def test_each_cell_is_read_in_its_own_state(tmp_path: Path) -> None:
    row = _load(tmp_path, _table(CELLS)).rows[0]
    assert row.cell("memory.size_gb").state == VALUE
    assert row.cell("memory.size_gb").value == 16
    assert row.cell("formats.int8_dot").state == VALUE
    assert row.cell("formats.int8_dot").scope == "architecture"
    assert row.cell("formats.fp16").state == NO
    assert row.cell("formats.matrix.precisions").state == NO
    assert row.cell("formats.matrix.name").state == NO
    assert row.cell("memory.type").state == UNKNOWN


def test_a_field_the_row_does_not_carry_is_unknown_not_no(tmp_path: Path) -> None:
    row = _load(tmp_path, _table(CELLS)).rows[0]
    absent = row.cell("api.vulkan")
    assert absent.state == UNKNOWN
    assert absent.value is None and absent.source is None


def test_a_cell_keeps_its_source_how_and_official(tmp_path: Path) -> None:
    table = _load(tmp_path, _table(CELLS))
    cell = table.rows[0].cell("memory.size_gb")
    assert (cell.source, cell.how, cell.official) == ("s1", "stated", True)
    assert table.sources["s1"].url == SOURCE["url"]
    assert table.sources["s1"].read.isoformat() == "2026-01-02"
    assert table.built.isoformat() == "2026-01-03"
    assert table.row("card-1") is table.rows[0]
    assert table.row("no-such-card") is None


def test_the_shipped_table_holds_all_three_states() -> None:
    table = hardware_table.load(REPO / "data" / hardware_table.TABLE_FILENAME)
    states = {cell.state for row in table.rows for cell in row.cells.values()}
    assert states == {VALUE, NO, UNKNOWN}


@pytest.mark.parametrize(
    ("change", "says"),
    [
        ({"schema": 2}, "not schema 1"),
        ({"extra": 1}, "keys are not"),
        ({"built": "soon"}, "built is not a date"),
        ({"sources": [{**SOURCE, "url": "http://vendor.example"}]}, "no https URL"),
        ({"sources": [{**SOURCE, "quote": "x"}]}, "does not carry exactly"),
        ({"sources": [SOURCE, SOURCE]}, "source id is stated twice"),
    ],
)
def test_a_table_not_of_the_declared_shape_is_refused(
    tmp_path: Path, change: dict[str, Any], says: str
) -> None:
    with pytest.raises(HardwareTableError, match=says):
        _load(tmp_path, _table(CELLS, **change))


@pytest.mark.parametrize(
    ("cell", "says"),
    [
        ({"v": 1, "src": "s1", "quote": "the page"}, "undeclared"),
        ({"v": 1, "src": "s9"}, "names no listed source"),
        ({"v": 1}, "has a value and no source"),
        ({"v": 1, "src": "s1", "official": "yes"}, "official is not a bool"),
    ],
)
def test_a_cell_not_of_the_declared_shape_is_refused(
    tmp_path: Path, cell: dict[str, Any], says: str
) -> None:
    with pytest.raises(HardwareTableError, match=says):
        _load(tmp_path, _table({"memory": {"size_gb": cell}}))


def test_a_row_of_an_undeclared_kind_is_refused(tmp_path: Path) -> None:
    table = _table(CELLS)
    table["rows"][0]["kind"] = "tpu"
    with pytest.raises(HardwareTableError, match="kind is not one of"):
        _load(tmp_path, table)


def test_a_file_that_is_not_json_is_refused_by_its_path(tmp_path: Path) -> None:
    path = tmp_path / hardware_table.TABLE_FILENAME
    path.write_text("{", encoding="utf-8")
    with pytest.raises(HardwareTableError, match="cannot read"):
        hardware_table.load(path)
