"""A small capability table, generated, for tests that need one of their own.

Every model id and number here is invented. None is a figure from the shipped
table, so a test built on this one keeps its meaning whatever the shipped
estimates say, and a revision of those estimates never moves it.

:data:`CARD_SIZES` are invented card sizes a fit listing is asked about, in no
simple ratio to each other, so a test that passes at one size is not passing
because of the size.

The schema version is read from :mod:`mcgyvr.capability` when a document is
built, never restated: a test that wants a table of another version passes
``version`` on purpose.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: Invented card sizes, in GB, no two of them in a 1:2 relation.
CARD_SIZES: tuple[float, ...] = (5.0, 9.0, 14.0, 40.0)

_UNSET: Any = object()


def row(model_id: str, **overrides: Any) -> dict[str, Any]:
    """One model row: the facts a row states."""
    entry: dict[str, Any] = {
        "id": model_id,
        "family": "invented",
        "params_b": 5.0,
        "quant": "q5",
        "weights_gb": 3.1,
        "vram_gb_working": 3.7,
        "notes": "an invented row",
    }
    entry.update(overrides)
    return entry


def table_document(
    *, rows: Sequence[dict[str, Any]] = (), version: Any = _UNSET
) -> dict[str, Any]:
    """A whole table document. ``version`` defaults to the one the code reads."""
    if version is _UNSET:
        from mcgyvr.capability import SCHEMA_VERSION

        version = SCHEMA_VERSION
    return {
        "schema_version": version,
        "_purpose": "an invented table for a test",
        "models": [dict(r) for r in rows] or [row("invented-model-a")],
    }


def table_document_with_every_block() -> dict[str, Any]:
    """A document carrying at least one entry at every level the table declares.

    A row with a reason to keep it out of fit listings, and a backend. A test
    that changes one level of it knows every other level is well formed.
    """
    model = row("invented-model-a", not_for_fit="an invented reason")
    document = table_document(rows=[model])
    document["backends"] = {
        "_doc": "invented backends",
        "some-server": {
            "wire_protocol": "openai",
            "strengths": ["invented"],
            "limits": ["invented"],
        },
    }
    return document


def write_table(directory: Path, document: dict[str, Any]) -> Path:
    """Write ``document`` where :func:`mcgyvr.capability.load` can read it."""
    path = directory / "capability-table.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path
