"""A2 — clock skew must not defeat latest-wins.

:func:`mcgyvr.telemetry.fold` ordered corrections by their own wall-clock ``ts``
and then by position, so the position tiebreak fired only when two timestamps
were exactly equal. Two hosts writing one sink have two clocks, so a correction
written later can carry an earlier ``ts`` and lose to the one written before it.

The file's own order is the order the corrections were appended — the ``flock``
serialises writers and append mode puts each write at the end — so position is
the authoritative "latest", and ``ts`` is metadata a reader can inspect, not a
ranking to fold by.
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


def test_the_later_written_correction_wins_even_when_its_clock_is_earlier(
    tmp_path: Path,
) -> None:
    """Position on disk is the order; the clock is not a ranking."""
    sink = tmp_path / "attempts.jsonl"
    attempt = {
        "record_kind": "attempt",
        "version": 1,
        "ts": 100.0,
        "attempt_id": "a1",
    }
    first = {
        "record_kind": "correction",
        "version": 1,
        "ts": 900.0,  # a skewed clock that runs ahead
        "attempt_id": "a1",
        "outcome": "merged",
        "detail": "first on disk, later clock",
    }
    second = {
        "record_kind": "correction",
        "version": 1,
        "ts": 10.0,  # a skewed clock that runs behind
        "attempt_id": "a1",
        "outcome": "reverted",
        "detail": "second on disk, earlier clock",
    }
    sink.write_text(
        "\n".join(json.dumps(r) for r in (attempt, first, second)) + "\n",
        encoding="utf-8",
    )

    folded = _fold()(path=sink)
    mine = [r for r in folded if r.get("attempt_id") == "a1"]
    assert len(mine) == 1
    assert mine[0].get("outcome") == "reverted", (
        "the correction written later lost to an earlier clock; the fold "
        f"ranked by ts instead of position: {mine}"
    )
