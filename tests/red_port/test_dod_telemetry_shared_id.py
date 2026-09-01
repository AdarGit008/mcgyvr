"""A4 — ``fold`` must not silently delete attempt rows that share an id.

:func:`mcgyvr.telemetry.fold` keyed attempts on ``attempt_id`` alone and let a
repeat supersede: the second row replaced the first in the dict, and the first
vanished without a trace. A row is a measurement; throwing one away because
another happened to carry the same key turns a collision into missing data, and
it does so silently — a report built on the fold cannot tell a collision
happened.

The fix keeps every attempt row, and binds a correction to the latest row that
carries the id it names — the one a corrector most plausibly just corrected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.red_port.conftest import required

OBSERVE = (
    "record every attempt it runs — exactly once, whether the attempt "
    "returned or raised"
)
FOLD = "read attempt records back with their corrections folded in, latest wins"


def _observe() -> Any:
    return required(
        OBSERVE, lambda: __import__("mcgyvr.telemetry", fromlist=["observe"]).observe
    )


def _fold() -> Any:
    return required(
        FOLD, lambda: __import__("mcgyvr.telemetry", fromlist=["fold"]).fold
    )


def _completion(model: str) -> Any:
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    return Completion(
        text="def f():\n    return 1\n",
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model=model,
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=1.5,
        input_tokens=812,
        output_tokens=96,
    )


def test_two_attempts_that_share_an_id_both_survive_the_fold(tmp_path: Path) -> None:
    """A shared key is a collision, not a reason to throw a row away."""
    observe = _observe()
    sink = tmp_path / "attempts.jsonl"
    observe(
        lambda: _completion("qwen2.5-coder:7b"),
        path=sink,
        attempt_id="dup",
        orchestrator="orch-a",
        rung="local/qwen",
    )
    observe(
        lambda: _completion("qwen2.5-coder:32b"),
        path=sink,
        attempt_id="dup",
        orchestrator="orch-a",
        rung="local/qwen",
    )

    folded = _fold()(path=sink)
    dup = [r for r in folded if r.get("attempt_id") == "dup"]
    assert len(dup) == 2, (
        f"fold kept {len(dup)} of two attempts that share an id; a row was "
        "silently deleted"
    )
    assert {r.get("model") for r in dup} == {"qwen2.5-coder:7b", "qwen2.5-coder:32b"}, (
        "the row that survived is not distinguishable from the one that was "
        f"deleted: {dup}"
    )
