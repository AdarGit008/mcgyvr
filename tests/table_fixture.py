"""A small capability table, generated, for tests that need one of their own.

Every class id, model id and number here is invented. None is a figure from the
shipped table, so a test built on this one keeps its meaning whatever the
shipped estimates say, and a revision of those estimates never moves it.

The class sets come in more than one shape (:data:`CLASS_SHAPES`): one class,
and several classes whose sizes stand in no simple ratio to each other, so a
test that passes on one shape of table is not passing because of the shape.

The schema version is read from :mod:`mcgyvr.capability` when a document is
built, never restated: a test that wants a table of another version passes
``version`` on purpose.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _class(memory_gb: int) -> dict[str, Any]:
    return {
        "id": f"{memory_gb}gb",
        "label": f"{memory_gb} GB class",
        "memory_gb": memory_gb,
    }


#: One invented card class.
ONE_CLASS: tuple[dict[str, Any], ...] = (_class(9),)

#: Several invented card classes, no two of them in a 1:2 relation.
SEVERAL_CLASSES: tuple[dict[str, Any], ...] = (_class(5), _class(14), _class(40))

#: Every shape of class set a test may run over, by a name a test id can carry.
CLASS_SHAPES: dict[str, tuple[dict[str, Any], ...]] = {
    "one-class": ONE_CLASS,
    "several-classes": SEVERAL_CLASSES,
}

#: The class set a document carries when a test does not ask for another.
CLASSES = SEVERAL_CLASSES

_UNSET: Any = object()


def reading(card_class: str, **figures: Any) -> dict[str, Any]:
    """One reading taken for ``card_class``, through an invented server program."""
    return {**figures, "backend": "some-server", "card_class": card_class}


def row(
    model_id: str,
    *,
    card_class: str = str(CLASSES[0]["id"]),
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
    default = row("invented-model-a", card_class=str(classes[0]["id"]))
    return {
        "schema_version": version,
        "_purpose": "an invented table for a test",
        "card_classes": [dict(c) for c in classes],
        "models": [dict(r) for r in rows] or [default],
    }


def table_document_with_every_block(
    *, classes: Sequence[dict[str, Any]] = CLASSES
) -> dict[str, Any]:
    """A document carrying at least one entry at every level the table declares.

    A quality metric, a caveat, a row with a valid, an invalid and a disputed
    reading, a backend given for a class, and a finding given for a class. A
    test that changes one level of it knows every other level is well formed.
    """
    first = str(classes[0]["id"])
    model = row("invented-model-a", card_class=first)
    model["invalid_measurements"] = [
        reading(first, humaneval_plus_pass1=0.11, caveat="CAV-X")
    ]
    model["disputed_measurements"] = [
        reading(first, humaneval_plus_pass1=0.22, caveat="CAV-X")
    ]
    document = table_document(classes=classes, rows=[model])
    document["quality_metric"] = {
        "name": "humaneval_plus_pass1",
        "dataset": "an invented set",
        "decoding": "greedy",
        "framework": "an invented harness",
        "_caveat": "a proxy",
    }
    document["harness_caveats"] = [
        {
            "id": "CAV-X",
            "severity": "low",
            "summary": "an invented caveat",
            "detail": "invented",
            "consequence": "none",
        }
    ]
    document["backends"] = {
        "_doc": "invented backends",
        "some-server": {
            "wire_protocol": "openai",
            "strengths": ["invented"],
            "limits": ["invented"],
            "card_class": first,
        },
    }
    document["concurrency_findings"] = [
        {
            "id": "CON-X",
            "summary": "an invented finding",
            "detail": "invented",
            "consequence": "none",
            "card_class": first,
        }
    ]
    return document


def write_table(directory: Path, document: dict[str, Any]) -> Path:
    """Write ``document`` where :func:`mcgyvr.capability.load` can read it."""
    path = directory / "capability-table.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path
