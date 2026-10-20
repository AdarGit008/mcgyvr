"""The record every language extractor emits: :class:`Symbol` and :class:`SymbolKind`.

It lives below the extractors so that each of them, and
:mod:`mcgyvr.orchestrator.symbols` which dispatches to them, can import it without
importing one another. Callers import both names from
:mod:`mcgyvr.orchestrator.symbols`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SymbolKind(StrEnum):
    """What a :class:`Symbol` represents: a definition site, a call site, an
    export site, an import site, a field on a class, or a property of an object
    shape."""

    DEFINITION = "definition"
    REFERENCE = "reference"
    EXPORT = "export"
    IMPORT = "import"
    FIELD = "field"
    PROPERTY = "property"


@dataclass(frozen=True)
class Symbol:
    """One symbol occurrence.

    ``line`` is 1-based. ``detail`` holds a kind-specific label (``"function"``,
    ``"method"``, ``"class"`` for definitions; the module path for imports) and
    ``signature`` holds the source text of the declaration header or, for
    imports, the whole unparsed statement.
    """

    name: str
    kind: SymbolKind
    path: str
    line: int
    detail: str = ""
    signature: str = ""
