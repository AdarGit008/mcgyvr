"""Regenerate what the shipped catalog reads from its files' headers.

`python -m mcgyvr.knowledge.regenerate` (``make catalog``) rewrites
``data/model-catalog.json`` with each record's `architecture` read from the
shipped header row of the file it names (`record.architecture_of` over
``data/model-geometry.json``), the same law a Hub read files a record by
(`hub.build_record`). Nothing is fetched: the rows are those the catalog ships
with, so the run is reproducible offline. Every other field is written back as
it was read. With ``--check`` nothing is written; the run fails, naming the
records, when the file differs from what it would write.

A record that names no weights, or whose file has no shipped header row, is
refused: its architecture cannot be read, and the shipped catalog states one
for every record.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from mcgyvr import atomic, shipped
from mcgyvr.knowledge import geometry
from mcgyvr.knowledge.record import (
    KnowledgeError,
    ModelRecord,
    architecture_of,
    dump_record,
    parse_record,
)
from mcgyvr.knowledge.store import MODEL_CATALOG_FILENAME


def _rows() -> dict[tuple[str, str, str], geometry.Geometry]:
    return {one.key: one for one in geometry.shipped()}


def regenerated(raw: dict[str, Any]) -> dict[str, Any]:
    """The catalog document `raw` with every record's architecture read from its
    file's shipped header row, key order and every other value kept."""
    rows = _rows()
    out: list[dict[str, Any]] = []
    for entry in raw.get("models", []):
        # Read as a cache record: the field being regenerated may be absent.
        one: ModelRecord = parse_record(entry, "the shipped catalog", shipped=False)
        weights = one.weights
        if weights is None:
            raise KnowledgeError(
                f"{one.model_id} {one.quant} names no weights, so no header "
                f"says its architecture"
            )
        row = rows.get((weights.repo, weights.revision, weights.file))
        if row is None:
            raise KnowledgeError(
                f"{one.model_id} {one.quant}: no shipped header row of "
                f"{geometry.locator(weights.repo, weights.revision, weights.file)}"
            )
        out.append(dump_record(replace(one, architecture=architecture_of(row.row))))
    return {**raw, "models": out}


def _text(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.knowledge.regenerate",
        description=(
            "Regenerate data/model-catalog.json's header-read fields from "
            "data/model-geometry.json."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; fail when the file differs from what would be written",
    )
    args = parser.parse_args(argv)
    path: Path = shipped.CHECKOUT_DATA / MODEL_CATALOG_FILENAME
    before = path.read_text(encoding="utf-8")
    raw = json.loads(before)
    after = _text(regenerated(raw))
    if after == before:
        print(f"{path}: up to date")
        return 0
    if args.check:
        stale = [
            str(old.get("model_id"))
            for old, new in zip(
                raw.get("models", []), json.loads(after)["models"], strict=True
            )
            if old != new
        ]
        print(
            f"{path} is stale for {', '.join(stale)}; run make catalog",
            file=sys.stderr,
        )
        return 1
    atomic.write(path, after)
    print(f"{path}: regenerated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
