"""The shipped hardware table carries every field its kind declares.

The table's shape is declared once, in ``tools/hardware-table/schema.json``,
beside the script that builds it. The shipped table must be of that schema, be
read by the loader without refusal, and give each row every field its kind (and
its vendor) declares, so a reader can tell a field the pages left unknown from a
field the table forgot.
"""

from __future__ import annotations

import json
from typing import Any

from mcgyvr import hardware_table
from tests._paths import REPO

SCHEMA_FILE = REPO / "tools" / "hardware-table" / "schema.json"
SHIPPED = REPO / "data" / hardware_table.TABLE_FILENAME


def _schema() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    return loaded


def test_the_loader_reads_the_schema_the_build_declares() -> None:
    schema = _schema()
    assert schema["schema"] == hardware_table.SCHEMA
    assert tuple(schema["shipped"]["cell"]) == hardware_table.CELL_KEYS
    assert tuple(schema["shipped"]["source"]) == hardware_table.SOURCE_KEYS
    assert tuple(schema["kinds"]) == hardware_table.KINDS


def test_the_shipped_table_is_read_without_refusal() -> None:
    table = hardware_table.load(SHIPPED)
    raw = json.loads(SHIPPED.read_text(encoding="utf-8"))
    assert raw["schema"] == hardware_table.SCHEMA
    assert table.built.isoformat() == raw["built"]
    assert len(table.rows) == len(raw["rows"])
    assert {row.kind for row in table.rows} == set(hardware_table.KINDS)


def test_every_row_carries_the_fields_of_its_kind_and_vendor() -> None:
    kinds = _schema()["kinds"]
    missing = []
    for row in hardware_table.load(SHIPPED).rows:
        spec = kinds[row.kind]
        assert row.vendor in spec["vendors"], row.id
        wanted = [*spec["fields"], *spec["vendor_fields"].get(row.vendor, [])]
        missing += [f"{row.id} {field}" for field in wanted if field not in row.cells]
    assert not missing, missing[:20]


def test_a_row_carries_no_field_its_kind_does_not_declare() -> None:
    kinds = _schema()["kinds"]
    stray = []
    for row in hardware_table.load(SHIPPED).rows:
        spec = kinds[row.kind]
        declared = {
            *spec["fields"],
            *spec["optional"],
            *(f for fields in spec["vendor_fields"].values() for f in fields),
        }
        stray += [f"{row.id} {field}" for field in row.cells if field not in declared]
    assert not stray, stray[:20]
