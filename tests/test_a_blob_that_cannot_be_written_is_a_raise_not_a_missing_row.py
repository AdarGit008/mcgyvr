"""A blob that cannot be written raises — the sink rule, extended to the blob store.

``observe`` already says of its line sink: "a sink that cannot be written raises
rather than being swallowed. Silence here is the failure this module was built
to end, and an unwritable path is an operator error that is cheap to fix at the
moment it happens and impossible to notice a week later, when the answer is
simply missing rows." The brief (*Live journal (WP0)*) applies the same rule to
``<sink dir>/blobs/<sha256>``: a row that names a ``prompt_sha256`` whose blob
was never written is worse than no row, because the hash reads as evidence that
exists.

The cheapest way to make the blob directory unwritable, on any account, is to
put a file where the directory must go. A read-only directory would be the
more natural fixture and is not used: as root it is writable anyway, and a
guard that passes under sudo and fails under a user account is a guard nobody
can reason about.

**Raising is half the rule; the row is the other half.** ``observe`` promises
exactly one record per call, and a dispatch that left none is one no caller can
tell from a dispatch nobody made — which is exactly how the caller that counts
an attempt's rows comes to blame the wrong draw. This file used to assert only
that the call raised, so it passed while the prompt blob, stored outside every
``try``, went on writing no row at all. It asserts both now, and the title is
true again.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from mcgyvr.pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import ATTEMPT_KIND, fold, observe

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

# RED-phase typing: ``messages`` and ``endpoint`` are the keyword arguments this
# change adds to ``observe``; the alias keeps mypy strict clean before and after.
_observe = cast("Callable[..., Any]", observe)


def _completion() -> Completion:
    return Completion(
        text="```python\nVALUE = 1\n```",
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def _unwritable(tmp_path: Path) -> Path:
    """A sink whose blob store cannot be created, and the sink path."""
    journal = tmp_path / "journal"
    journal.mkdir()
    # Where `blobs/` must be, a regular file already is.
    (journal / "blobs").write_text("not a directory", encoding="utf-8")
    return journal / "agent-a.jsonl"


def _row(sink: Path) -> dict[str, Any]:
    """The one record the call left behind, folded as a reader would read it."""
    rows = [r for r in fold(path=sink) if r.get("record_kind") == ATTEMPT_KIND]
    assert len(rows) == 1, rows
    return rows[0]


def test_a_blob_store_that_is_a_file_makes_observe_raise(tmp_path: Path) -> None:
    """The reply cannot be stored: the call raises and the row still goes down."""
    sink = _unwritable(tmp_path)

    with pytest.raises(OSError):
        _observe(
            _completion,
            path=sink,
            attempt_id="agent-a:impl:local_qwen-7b:1",
            orchestrator="agent-a",
            rung="local_qwen-7b",
            endpoint="http://localhost:11434",
        )

    row = _row(sink)
    assert row.get("ok") is False, "the dispatch happened and did not land"
    assert "reply_sha256" not in row, "no row names a blob that is not there"


def test_a_prompt_that_cannot_be_stored_leaves_a_row_too(tmp_path: Path) -> None:
    """The prompt blob is stored first, and its failure is a row like any other."""
    sink = _unwritable(tmp_path)

    with pytest.raises(OSError):
        _observe(
            _completion,
            path=sink,
            attempt_id="agent-a:impl:local_qwen-7b:1",
            orchestrator="agent-a",
            rung="local_qwen-7b",
            messages=[{"role": "user", "content": "Set VALUE to 1."}],
            endpoint="http://localhost:11434",
        )

    row = _row(sink)
    assert row.get("ok") is False
    assert "prompt_sha256" not in row, "no row names a blob that is not there"
    assert row.get("endpoint") == "http://localhost:11434", (
        "what the attempt was is known before the blob and survives its failure"
    )
