"""A journal that keeps the hash and not the text can be counted, never reviewed.

``telemetry.observe`` today drops ``Completion.text`` and never sees the prompt
(brief, *Live journal (WP0)*): a row can say a rung answered in 1.2 s and cannot
say what it was asked or what it said, so nothing dispatched by the product is
ever reviewable for quality. The change is that ``observe`` takes the rendered
prompt — the messages, as sent — and keeps the reply, both stored
content-addressed under the sink's ``blobs/`` directory and named on the row by
``prompt_sha256`` / ``reply_sha256`` (the names ``tools/bench/identity.py``
already declares).

Three properties, each pinned here because each is cheap to lose:

* the blob is what the hash names — a reader that opens ``blobs/<sha>`` and
  hashes it gets ``<sha>`` back, or the store is a lookup table and not a store;
* the same text dispatched twice is one blob — a journal that copied every
  prompt per attempt would grow by the prompt size per row, which is the cost
  the old docstring used to refuse keeping text at all;
* the text is scrubbed **before** it is hashed — ``redact.scrub`` names
  "telemetry rows" as a sink an operator pastes into an issue, and a credential
  that survives into a blob has left the machine the moment the blob is shared.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from mcgyvr.pool import Protocol
from mcgyvr.redact import REDACTED
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import fold, observe

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

# RED-phase typing: ``messages`` and ``endpoint`` are the keyword arguments this
# change adds to ``observe``. Calling through an untyped alias keeps mypy strict
# clean both before the kwargs exist and after — the runtime failure is the pin.
_observe = cast("Callable[..., Any]", observe)

SYSTEM = "You are a careful worker. Answer with one fenced block."
USER = "Set VALUE to 1 in src/pkg/messy.py."
REPLY = "```python\nVALUE = 1\n```"


def _completion(text: str) -> Completion:
    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OLLAMA,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def _messages(user: str = USER) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]


def _record(sink: Path, attempt_id: str, user: str = USER, reply: str = REPLY) -> None:
    _observe(
        lambda: _completion(reply),
        path=sink,
        attempt_id=attempt_id,
        orchestrator="agent-a",
        rung="local_qwen-7b",
        messages=_messages(user),
        endpoint="http://localhost:11434",
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_the_prompt_and_the_reply_are_stored_by_content_and_named_on_the_row(
    tmp_path: Path,
) -> None:
    sink = tmp_path / "journal" / "agent-a.jsonl"
    _record(sink, "agent-a:impl:local_qwen-7b:1")

    (row,) = fold(path=sink)
    blobs = sink.parent / "blobs"
    prompt_blob = blobs / row["prompt_sha256"]
    reply_blob = blobs / row["reply_sha256"]

    assert prompt_blob.is_file(), f"no prompt blob under {blobs}"
    assert reply_blob.is_file(), f"no reply blob under {blobs}"
    # Content-addressed means the name IS the digest of the bytes, so a reader
    # can verify a blob without trusting the row that named it.
    assert _sha256(prompt_blob.read_bytes()) == row["prompt_sha256"]
    assert _sha256(reply_blob.read_bytes()) == row["reply_sha256"]
    # The prompt blob carries the messages as sent — both halves of them.
    prompt_text = prompt_blob.read_text(encoding="utf-8")
    assert USER in prompt_text
    assert SYSTEM in prompt_text
    # The reply blob is the reply, scrubbed — which for a clean reply is the
    # reply byte for byte.
    assert reply_blob.read_text(encoding="utf-8") == REPLY


def test_the_same_text_dispatched_twice_is_one_blob(tmp_path: Path) -> None:
    sink = tmp_path / "journal" / "agent-a.jsonl"
    _record(sink, "agent-a:impl:local_qwen-7b:1")
    _record(sink, "agent-a:impl:local_qwen-7b:2")

    first, second = fold(path=sink)
    assert first["prompt_sha256"] == second["prompt_sha256"]
    assert first["reply_sha256"] == second["reply_sha256"]
    blobs = sorted(p.name for p in (sink.parent / "blobs").iterdir())
    assert blobs == sorted({first["prompt_sha256"], first["reply_sha256"]}), (
        f"two identical attempts left {len(blobs)} blobs; expected exactly two"
    )


def test_a_credential_in_the_prompt_never_reaches_the_blob(tmp_path: Path) -> None:
    sink = tmp_path / "journal" / "agent-a.jsonl"
    secret = "s3cr3t-key-7f3a"
    leaking = f"Use the source at https://svc:{secret}@host.example/v1 for this."
    _record(sink, "agent-a:impl:local_qwen-7b:1", user=leaking)

    (row,) = fold(path=sink)
    blob = (sink.parent / "blobs" / row["prompt_sha256"]).read_bytes()
    assert secret.encode() not in blob, "the credential reached the blob"
    assert REDACTED.encode() in blob, "the URL was dropped rather than redacted"
    # Scrubbed BEFORE hashing: the digest names the scrubbed bytes, so a reader
    # who hashes the blob gets the row's name back.
    assert _sha256(blob) == row["prompt_sha256"]
    # And the line itself carries no text at all — the row is the measurement,
    # the blob is the evidence.
    line = sink.read_text(encoding="utf-8")
    assert secret not in line
    assert USER not in line
