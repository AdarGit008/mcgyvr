"""A1 — a torn line must not swallow the next complete record.

:func:`mcgyvr.telemetry._append` writes one JSON object per line and assumes the
sink already ends on a line boundary. A crash mid-write — or a full disk that
accepts only part of a line — leaves a stump: bytes with no trailing newline.
The next append glues its record onto that stump, and the reader skips the whole
glued line, so one torn line destroys a record that was written perfectly well.
The writer is the one place that can both cause a stump (a short write) and
repair one (a newline before the next line), and it currently does neither.

The fix checks the boundary under the lock before writing, and treats a write it
cannot complete as a failure rather than a silent stump.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.red_port.conftest import required

CORRECT = (
    "append how the work finally landed without rewriting the attempt's own record"
)


def _correct() -> Any:
    return required(
        CORRECT, lambda: __import__("mcgyvr.telemetry", fromlist=["correct"]).correct
    )


def test_a_torn_line_does_not_swallow_the_next_record(tmp_path: Path) -> None:
    """A stump already on disk stays a stump; the next record is still its own line."""
    sink = tmp_path / "attempts.jsonl"
    # A torn line: the write that produced it crashed after the comma.
    sink.write_bytes(b'{"record_kind": "attempt", "attempt_id": "torn", ')

    _correct()(path=sink, attempt_id="a1", outcome="merged", orchestrator="orch-a")

    records: list[dict[str, Any]] = []
    for line in sink.read_bytes().split(b"\n"):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            # The torn stump itself still will not parse; what must survive is
            # the record that came after it.
            continue
    assert any(r.get("attempt_id") == "a1" for r in records), (
        "the torn line swallowed the next record; it is no longer its own line "
        f"on disk: {records}"
    )


def test_a_short_write_is_a_failure_not_a_silent_stump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full disk that accepts only part of a line is signalled, not kept quiet.

    ``os.write`` is narrowed to accept half of a telemetry line and then make no
    progress, which is what a disk filling mid-write looks like. The writer must
    raise rather than declare the line written, because a silent stump is the
    exact thing the next append would glue its record onto.
    """
    sink = tmp_path / "attempts.jsonl"
    real_write = os.write
    state = {"started": False, "writes": 0}

    def full_disk(fd: int, data: Any) -> int:
        if not data:
            return real_write(fd, data)
        if data[0] == 0x7B:  # b"{" — the start of a telemetry line
            state["started"] = True
        if state["started"]:
            state["writes"] += 1
            return len(data) // 2 if state["writes"] == 1 else 0
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", full_disk)

    with pytest.raises(OSError, match="sink accepted"):
        _correct()(path=sink, attempt_id="a1", outcome="merged", orchestrator="orch-a")
