"""A live row names what answered it, what it was asked, and under which round.

``tools/bench/identity.py`` states what a measurement records — four groups,
one block. A journal row that said only ``rung`` and ``model`` could not be laid
beside a bench cell, because it would not say which endpoint served it, which
system prompt it carried or which product revision dispatched it. So each live
row carries the identity fields it can know at dispatch time:

* ``endpoint``, ``model``, ``protocol``, ``condition == "stock"``,
  ``orchestrator``, ``rung``, ``bundle_sha256`` (the system prompt, hashed the
  way ``tools/bundle/measure.py`` hashes it) — always;
* the round and the product revision — when whoever started the run says them,
  in ``$MCGYVR_RUN_TAGS``, under ``run_tags``
  (``tests/test_a_row_carries_the_run_tags_its_environment_names.py``). The
  product does not look them up, so a row nobody tagged carries neither.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from mcgyvr.local_pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import fold, observe

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

# ``observe`` called through an untyped alias.
_observe = cast("Callable[..., Any]", observe)

SYSTEM = "You are a careful worker. Answer with one fenced block."
USER = "Set VALUE to 1 in src/pkg/messy.py."
ENDPOINT = "http://localhost:8080"


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


def _record(sink: Path) -> dict[str, Any]:
    _observe(
        _completion,
        path=sink,
        attempt_id="agent-a:impl:local_qwen-7b:1",
        orchestrator="agent-a",
        rung="local_qwen-7b",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        endpoint=ENDPOINT,
    )
    (row,) = fold(path=sink)
    return row


def test_a_row_names_the_endpoint_the_model_the_protocol_and_the_condition(
    tmp_path: Path,
) -> None:
    row = _record(tmp_path / "journal" / "agent-a.jsonl")

    assert row["endpoint"] == ENDPOINT
    assert row["model"] == "qwen2.5-coder:7b"
    assert row["protocol"] == "openai"
    # Live work is the stock product, never an ablation; the field is what lets
    # a live row and a bench cell be told apart by content rather than by path.
    assert row["condition"] == "stock"
    assert row["orchestrator"] == "agent-a"
    assert row["rung"] == "local_qwen-7b"
    # The system prompt, hashed the way the bench hashes it (sha256 over utf-8).
    assert row["bundle_sha256"] == hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest()
