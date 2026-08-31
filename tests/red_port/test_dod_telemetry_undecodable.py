"""A3 — one undecodable byte must not make the whole sink unreadable.

:func:`mcgyvr.telemetry.fold` reads the sink with ``read_text(encoding="utf-8")``
— strict — so a single byte that is not valid UTF-8 raises before the per-line
"skip a line that will not parse" logic ever runs. The append-only shape is
chosen because it survives a torn line, but the reader only actually survives
one if it can step over it; an undecodable byte is a torn line the reader cannot
even reach its own skip for. One bad byte hides every good record around it.

The fix reads bytes and decodes line by line, so a line that will not decode is
skipped the same way a line that will not parse is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.red_port.conftest import required

FOLD = "read attempt records back with their corrections folded in, latest wins"


def _fold() -> Any:
    return required(
        FOLD, lambda: __import__("mcgyvr.telemetry", fromlist=["fold"]).fold
    )


def test_an_undecodable_byte_skips_one_line_not_the_whole_sink(
    tmp_path: Path,
) -> None:
    """A good record on either side of a corrupt byte still comes back."""
    sink = tmp_path / "attempts.jsonl"
    before = {"record_kind": "attempt", "version": 1, "attempt_id": "before"}
    after = {"record_kind": "attempt", "version": 1, "attempt_id": "after"}
    sink.write_bytes(
        (json.dumps(before) + "\n").encode("utf-8")
        + b"\xff\xfe\x80\n"  # not UTF-8, in the middle of the stream
        + (json.dumps(after) + "\n").encode("utf-8")
    )

    folded = _fold()(path=sink)

    ids = [r.get("attempt_id") for r in folded]
    assert "before" in ids and "after" in ids, (
        f"one undecodable byte hid the good records around it: {ids}"
    )
