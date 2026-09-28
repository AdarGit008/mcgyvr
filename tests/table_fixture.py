"""A small capability table, generated, for tests that need one of their own.

Every class id, model id and number here is invented. None is a figure from the
shipped table, so a test built on this one keeps its meaning whatever the
shipped estimates say, and a revision of those estimates never moves it.

The schema version is read from :mod:`mcgyvr.capability` when a document is
built, never restated: a test that wants a table of another version passes
``version`` on purpose.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

#: Two invented card classes, in the shape the table declares them.
CLASSES: tuple[dict[str, Any], ...] = (
    {"id": "10gb", "label": "10 GB class", "memory_gb": 10},
    {"id": "20gb", "label": "20 GB class", "memory_gb": 20},
)

_UNSET: Any = object()


def reading(card_class: str, **figures: Any) -> dict[str, Any]:
    """One reading taken for ``card_class``, through an invented server program."""
    return {**figures, "backend": "some-server", "card_class": card_class}


def row(
    model_id: str,
    *,
    card_class: str = "10gb",
    quality: float = 0.71,
    speed: float = 43.0,
    **overrides: Any,
) -> dict[str, Any]:
    """One model row with one quality and one speed reading for ``card_class``."""
    entry: dict[str, Any] = {
        "id": model_id,
        "family": "invented",
        "params_b": 5.0,
        "quant": "q5",
        "weights_gb": 3.1,
        "vram_gb_working": 3.7,
        "quality": [reading(card_class, humaneval_plus_pass1=quality)],
        "throughput_tok_s": [reading(card_class, value=speed)],
        "notes": "an invented row",
    }
    entry.update(overrides)
    return entry


def table_document(
    *,
    classes: Sequence[dict[str, Any]] = CLASSES,
    rows: Sequence[dict[str, Any]] = (),
    version: Any = _UNSET,
) -> dict[str, Any]:
    """A whole table document. ``version`` defaults to the one the code reads."""
    if version is _UNSET:
        from mcgyvr.capability import SCHEMA_VERSION

        version = SCHEMA_VERSION
    return {
        "schema_version": version,
        "_purpose": "an invented table for a test",
        "card_classes": [dict(c) for c in classes],
        "models": [dict(r) for r in rows] or [row("invented-model-a")],
    }


def write_table(directory: Path, document: dict[str, Any]) -> Path:
    """Write ``document`` where :func:`mcgyvr.capability.load` can read it."""
    path = directory / "capability-table.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path
