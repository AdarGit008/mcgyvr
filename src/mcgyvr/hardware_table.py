"""The hardware capabilities table: what a chip can do, from its vendor's pages.

One row per graphics card, processor or Apple chip; each fact of a row is a cell
that names its source, how the value was got and whether the vendor published
it. The table holds only facts a machine cannot report about itself, and no
reading of anyone's machine. It is built from the inputs under
``tools/hardware-table/`` (``build_db.py``), where every cell keeps the page's
own words; the package carries the table without them.

A cell is in one of three states (:attr:`Cell.state`), and they are never
confused: :data:`VALUE` (a page gives the value), :data:`NO` (a page states the
thing is not there: false, an empty list, or no value with a source cited), and
:data:`UNKNOWN` (no page read gives it). A field a row does not carry is
unknown. Unknown is never read as no.

`load` reads the table and checks it against the shape declared here, refusing
another schema or a key this code does not declare; `shipped_table` reads the
packaged copy once.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from mcgyvr.shipped import shipped_file

TABLE_FILENAME = "hardware-capabilities.json"

#: The version of the table's format this code reads.
SCHEMA = 1

#: The kinds of row: a graphics card or integrated GPU, a processor, an Apple chip.
KINDS = ("gpu", "cpu", "soc")

#: The keys a shipped cell may carry; ``v`` is the one every cell has.
CELL_KEYS = ("v", "src", "how", "official", "scope")
#: The keys every shipped source carries.
SOURCE_KEYS = ("id", "url", "publisher", "official", "read")
_TOP_KEYS = frozenset({"schema", "built", "sources", "rows"})
_ROW_KEYS = ("id", "vendor", "kind")

State = Literal["value", "no", "unknown"]
#: A page gives the value.
VALUE: State = "value"
#: A page states the thing is not there.
NO: State = "no"
#: No page read gives the value.
UNKNOWN: State = "unknown"


class HardwareTableError(Exception):
    """The table cannot be read, or is not the shape declared here."""


@dataclass(frozen=True)
class Source:
    """A page the table's cells were read from, and the day it was read."""

    id: str
    url: str
    publisher: str
    official: bool
    read: datetime.date


@dataclass(frozen=True)
class Cell:
    """One fact of a row: the value, its source, how it was got."""

    value: Any = None
    source: str | None = None
    how: str | None = None
    official: bool | None = None
    #: What the value is said of when not the product alone (an architecture,
    #: a compute capability, a family, a driver); None for the product itself.
    scope: str | None = None

    @property
    def state(self) -> State:
        if self.value is None:
            return NO if self.source is not None else UNKNOWN
        if self.value is False or self.value == []:
            return NO
        return VALUE


#: The cell of a field no page read gives, or that a row does not carry.
UNKNOWN_CELL = Cell()


@dataclass(frozen=True)
class Row:
    """One card, processor or chip, its cells keyed by dotted field name."""

    id: str
    vendor: str
    kind: str
    cells: Mapping[str, Cell]

    def cell(self, field: str) -> Cell:
        """The row's cell for ``field`` (``memory.bandwidth_gbps``); unknown when
        the row does not carry it."""
        return self.cells.get(field, UNKNOWN_CELL)


@dataclass(frozen=True)
class HardwareTable:
    """The whole table: its build date, its sources and its rows."""

    built: datetime.date
    sources: Mapping[str, Source]
    rows: tuple[Row, ...]

    def row(self, row_id: str) -> Row | None:
        return next((one for one in self.rows if one.id == row_id), None)


def table_path() -> Path:
    """Where the shipped table is: the package's copy, else the checkout's."""
    found = shipped_file(TABLE_FILENAME)
    if found is None:
        raise HardwareTableError(f"{TABLE_FILENAME} not found")
    return found


def _date(raw: Any, what: str, where: Path) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(raw))
    except ValueError as exc:
        raise HardwareTableError(f"{where}: {what} is not a date: {raw!r}") from exc


def _source(raw: Any, where: Path) -> Source:
    if not isinstance(raw, dict) or set(raw) != set(SOURCE_KEYS):
        raise HardwareTableError(
            f"{where}: a source does not carry exactly {SOURCE_KEYS}: {raw!r}"
        )
    sid = raw["id"]
    if not str(raw["url"]).startswith("https://"):
        raise HardwareTableError(f"{where}: source {sid!r} has no https URL")
    if not isinstance(raw["official"], bool):
        raise HardwareTableError(f"{where}: source {sid!r} official is not a bool")
    return Source(
        id=str(sid),
        url=str(raw["url"]),
        publisher=str(raw["publisher"]),
        official=raw["official"],
        read=_date(raw["read"], f"source {sid!r} read", where),
    )


def _leaves(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Every cell under ``node`` with its dotted field name: a dict with a ``v``
    is a cell, any other dict a group of fields."""
    if isinstance(node, dict) and "v" not in node:
        for key, value in node.items():
            yield from _leaves(value, f"{path}.{key}" if path else key)
    else:
        yield path, node


def _cell(raw: Any, at: str, sources: Mapping[str, Source], where: Path) -> Cell:
    if not isinstance(raw, dict):
        raise HardwareTableError(f"{where}: {at} is not a cell: {raw!r}")
    unknown = sorted(set(raw) - set(CELL_KEYS))
    if unknown:
        raise HardwareTableError(f"{where}: {at} carries undeclared {unknown}")
    src = raw.get("src")
    if src is not None and src not in sources:
        raise HardwareTableError(f"{where}: {at} names no listed source: {src!r}")
    if raw["v"] is not None and src is None:
        raise HardwareTableError(f"{where}: {at} has a value and no source")
    official = raw.get("official")
    if official is not None and not isinstance(official, bool):
        raise HardwareTableError(f"{where}: {at} official is not a bool")
    return Cell(
        value=raw["v"],
        source=src,
        how=raw.get("how"),
        official=official,
        scope=raw.get("scope"),
    )


def _row(raw: Any, sources: Mapping[str, Source], where: Path) -> Row:
    if not isinstance(raw, dict):
        raise HardwareTableError(f"{where}: a row is not an object: {raw!r}")
    rid = raw.get("id")
    for key in _ROW_KEYS:
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise HardwareTableError(f"{where}: row {rid!r} has no {key}")
    if raw["kind"] not in KINDS:
        raise HardwareTableError(f"{where}: row {rid!r} kind is not one of {KINDS}")
    body = {k: v for k, v in raw.items() if k not in _ROW_KEYS}
    cells = {
        field: _cell(cell, f"row {rid!r} {field}", sources, where)
        for field, cell in _leaves(body)
    }
    return Row(
        id=rid,
        vendor=raw["vendor"],
        kind=raw["kind"],
        cells=MappingProxyType(cells),
    )


def load(path: Path | None = None) -> HardwareTable:
    """Read and check the table at ``path``, defaulting to :func:`table_path`."""
    where = path or table_path()
    try:
        raw = json.loads(where.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HardwareTableError(f"cannot read {where}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise HardwareTableError(f"{where}: not schema {SCHEMA}")
    if set(raw) != _TOP_KEYS:
        raise HardwareTableError(f"{where}: keys are not {sorted(_TOP_KEYS)}")
    if not isinstance(raw["sources"], list) or not isinstance(raw["rows"], list):
        raise HardwareTableError(f"{where}: needs a sources list and a rows list")
    found = [_source(one, where) for one in raw["sources"]]
    sources = {one.id: one for one in found}
    if len(sources) != len(found):
        raise HardwareTableError(f"{where}: a source id is stated twice")
    rows = tuple(_row(one, sources, where) for one in raw["rows"])
    if len({one.id for one in rows}) != len(rows):
        raise HardwareTableError(f"{where}: a row id is stated twice")
    return HardwareTable(
        built=_date(raw["built"], "built", where),
        sources=MappingProxyType(sources),
        rows=rows,
    )


@cache
def shipped_table() -> HardwareTable:
    """The shipped table, read once."""
    return load()
