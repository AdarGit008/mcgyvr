#!/usr/bin/env python3
"""Mechanical check of a table or wave file: does each cell's quote carry its value?

  verify_values.py FILE...

``verify_quotes.py`` says the quote's words are on the page. This says the value
is in the quote: a number appears as written (also as 1,408, as 2.97 for 2970 or
as 1.2 for 1200, since pages write GHz and TB/s), a word appears ignoring case and
punctuation, every element of a list appears. Cells it cannot judge are named,
not passed: "derived" (a formula in ``how``), "truth" (true or false: needs
reading), "check" (the value was not seen in the quote). Writes
``<file>.values.json`` and prints a tally. Reads no page.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from collections.abc import Iterator
from typing import Any


def cells(node: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(node, dict):
        if "v" in node and ("src" in node or "why" in node or "quote" in node):
            yield path, node
            return
        for key, value in node.items():
            yield from cells(value, f"{path}.{key}" if path else key)


def squash(text: Any) -> str:
    return re.sub(r"[^a-z0-9.]+", "", str(text).lower())


def number_forms(value: float) -> set[str]:
    forms = set()
    for scaled in (value, value / 1000, value * 1000, value / 1024, value * 1024):
        if scaled == int(scaled):
            whole = int(scaled)
            forms.update({str(whole), f"{whole:,}"})
        for digits in (1, 2, 3):
            text = f"{scaled:.{digits}f}"
            forms.update({text, text.rstrip("0").rstrip(".")})
    return {f for f in forms if f and f != "0"}


def _all_of(verdicts: list[bool | None]) -> bool | None:
    if any(v is None for v in verdicts) and all(v is not False for v in verdicts):
        return None
    return all(v is not False for v in verdicts)


def seen(value: Any, quote: str) -> bool | None:
    """True, False, or None when this value is not one a text search can judge."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        spaced = re.sub(r"\s+", " ", quote)
        return any(
            re.search(rf"(?<![\d.]){re.escape(form)}(?![\d])", spaced)
            for form in number_forms(value)
        )
    if isinstance(value, str):
        return squash(value) in squash(quote) or value.lower() in quote.lower()
    if isinstance(value, list):
        return _all_of([seen(item, quote) for item in value])
    if isinstance(value, dict):
        return _all_of(
            [seen(item, quote) for item in value.values() if item is not None]
        )
    return None


def main(path: str) -> None:
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    tally: dict[str, int] = {}
    out = []
    for row in doc.get("rows", []):
        body = {k: v for k, v in row.items() if k not in ("id", "vendor", "kind")}
        for field, cell in cells(body):
            if cell.get("v") is None:
                continue
            quote = cell.get("quote") or ""
            if str(cell.get("how", "")).startswith("derived"):
                verdict = "derived"
            elif not quote:
                verdict = "check"
            else:
                judged = seen(cell["v"], quote)
                verdict = "truth" if judged is None else ("ok" if judged else "check")
            tally[verdict] = tally.get(verdict, 0) + 1
            if verdict != "ok":
                out.append(
                    {
                        "id": row.get("id"),
                        "field": field,
                        "verdict": verdict,
                        "v": cell["v"],
                        "quote": quote[:300],
                        "how": cell.get("how"),
                    }
                )
    pathlib.Path(path).with_suffix(".values.json").write_text(
        json.dumps({"file": str(path), "tally": tally, "cells": out}, indent=1)
    )
    print(f"{path}: {sum(tally.values())} cells: {tally}")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        main(arg)
