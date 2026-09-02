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
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from mcgyvr.pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import observe

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
        protocol=Protocol.OLLAMA,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def test_a_blob_store_that_is_a_file_makes_observe_raise(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    # Where `blobs/` must be, a regular file already is.
    (journal / "blobs").write_text("not a directory", encoding="utf-8")
    sink = journal / "agent-a.jsonl"

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
