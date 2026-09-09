"""An attempt that raised still names what it was asked, and does not invent a reply.

The journal's first rule (``telemetry`` module docstring) is *exactly one record
per attempt, including the attempt that raised* — a store holding only the
attempts that returned describes only the runs that went well. The brief's live
journal extends the row with ``prompt_sha256`` and ``reply_sha256``, and the
raised path is where those two are easiest to get wrong in opposite directions:

* the prompt WAS sent, so ``prompt_sha256`` is a fact of the attempt and is
  recorded whether or not anything came back — a failed dispatch that cannot
  say what it asked is the hole quality review exists to fill;
* no reply came back, so ``reply_sha256`` is **absent** — not ``null``, not the
  hash of the empty string. The module's own absent-is-honest rule for token
  counts applies verbatim: "a key present in some rows and null in others
  invites a reader to coerce it", and an empty-string digest looks exactly
  like a model that answered with nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from mcgyvr.telemetry import fold, observe

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

# RED-phase typing: ``messages`` and ``endpoint`` are the keyword arguments this
# change adds to ``observe``; the alias keeps mypy strict clean before and after.
_observe = cast("Callable[..., Any]", observe)

MESSAGES = [
    {"role": "system", "content": "You are a careful worker."},
    {"role": "user", "content": "Set VALUE to 1 in src/pkg/messy.py."},
]


def test_a_raised_attempt_records_its_prompt_and_has_no_reply_key(
    tmp_path: Path,
) -> None:
    sink = tmp_path / "journal" / "agent-a.jsonl"

    def dies() -> object:
        raise RuntimeError("the endpoint closed the connection")

    with pytest.raises(RuntimeError, match="closed the connection"):
        _observe(
            dies,
            path=sink,
            attempt_id="agent-a:impl:local_qwen-7b:1",
            orchestrator="agent-a",
            rung="local_qwen-7b",
            model="qwen2.5-coder:7b",
            messages=MESSAGES,
            endpoint="http://localhost:11434",
        )

    (row,) = fold(path=sink)
    assert row["ok"] is False
    assert row["error"] == "RuntimeError"
    # What was asked is known even though nothing answered.
    assert "prompt_sha256" in row, sorted(row)
    assert (sink.parent / "blobs" / row["prompt_sha256"]).is_file()
    # Nothing answered, so nothing is named: absent, never null, never the
    # digest of an empty string.
    assert "reply_sha256" not in row, f"reply_sha256 = {row.get('reply_sha256')!r}"
