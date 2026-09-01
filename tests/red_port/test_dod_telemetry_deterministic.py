"""S6/K5 — ``observe`` wraps any attempt, not only one that returns a ``Completion``.

:func:`mcgyvr.telemetry.observe` typed its attempt as
``Callable[[], Completion]``, so a deterministic-floor run — a tool, not a
model — could not be recorded, and passing it a non-``Completion`` answer
destroyed the answer and wrote nothing. The fix widens the seam: any callable
may be observed, the answer is returned unchanged whatever its type, and a row
is always written. The completion-only fields (latency, model, tokens) ride
along only when the answer *is* a ``Completion``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.red_port.conftest import required

OBSERVE = (
    "record every attempt it runs — exactly once, whether the attempt "
    "returned or raised"
)


def _observe() -> Any:
    return required(
        OBSERVE, lambda: __import__("mcgyvr.telemetry", fromlist=["observe"]).observe
    )


def _stream(sink: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in sink.read_text().splitlines() if line.strip()]


def test_a_non_completion_answer_is_recorded_and_returned_unchanged(
    tmp_path: Path,
) -> None:
    """A deterministic step's answer is not a `Completion`, and is not destroyed."""
    observe = _observe()
    sink = tmp_path / "attempts.jsonl"
    answer = object()

    got = observe(
        lambda: answer,
        path=sink,
        attempt_id="d1",
        orchestrator="orch-a",
        rung="deterministic",
    )

    assert got is answer, "observe swallowed or replaced a non-Completion answer"

    stream = _stream(sink)
    assert len(stream) == 1, f"the deterministic attempt left {len(stream)} records"
    record = stream[0]
    assert record["ok"] is True
    assert record["rung"] == "deterministic"
    assert record["attempt_id"] == "d1"
    assert record["orchestrator"] == "orch-a"
    # The completion-only fields are absent from a non-Completion answer.
    for field in ("latency_s", "model", "input_tokens", "stop_reason"):
        assert field not in record, (
            f"a non-Completion answer grew a completion field: {record}"
        )
