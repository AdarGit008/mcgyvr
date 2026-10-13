"""An empty reply cut at its cap is named as reasoning that used the cap up.

On DeepSeek's reasoning models the e2e run of 2026-10-13 got back a reply
whose text was empty (``reply_sha256`` the hash of ``""``), every token of the
1024 cap spent, stop ``length`` — and the failure read "a truncated file can
parse cleanly and still be missing its tail", which says nothing of an empty
reply or of reasoning, and sends the reader to the wrong repair. The refusal
now names the hidden reasoning, the tokens spent and the cap, and the keys
that raise it. A reply that wrote something before the cap keeps the
truncated-file refusal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.local_pool import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.worker.reply import empty_at_cap
from tests import livejournal as lj


def _reply(text: str, stop: StopReason, **extra: Any) -> Completion:
    fields: dict[str, Any] = {
        "max_output_tokens": 1024,
        "output_tokens": 1024,
        **extra,
    }
    return Completion(
        text=text,
        stop_reason=stop,
        raw_stop_reason="length" if stop is StopReason.TRUNCATED else "stop",
        model="deepseek-reasoner",
        source="deepseek",
        protocol=Protocol.OPENAI,
        latency_s=1.0,
        **fields,
    )


def test_an_empty_reply_at_the_cap_names_reasoning_the_tokens_and_the_cap() -> None:
    refused = empty_at_cap(_reply("", StopReason.TRUNCATED, reasoning_tokens=1024))
    assert refused is not None
    assert refused.code == "empty-reply"
    said = str(refused)
    assert (
        "the model used all 1024 output tokens of its 1024-token cap on hidden "
        "reasoning (1024 reported as reasoning) and returned no visible reply"
    ) in said
    assert "limits.max_output_tokens" in said
    assert "output_tokens" in said
    assert "missing its tail" not in said


def test_whitespace_is_no_visible_reply_either() -> None:
    refused = empty_at_cap(_reply("\n  \n", StopReason.TRUNCATED))
    assert refused is not None
    assert "(1024 reported" not in str(refused), "no count reported, none claimed"


def test_a_count_the_backend_did_not_report_falls_back_to_the_cap() -> None:
    refused = empty_at_cap(_reply("", StopReason.TRUNCATED, output_tokens=None))
    assert refused is not None
    assert "all 1024 output tokens of its 1024-token cap" in str(refused)


@pytest.mark.parametrize(
    ("text", "stop"),
    [
        ("```python\nx = 1\n", StopReason.TRUNCATED),  # wrote something: a cut file
        ("", StopReason.COMPLETE),  # the model's own empty answer
    ],
)
def test_only_an_empty_reply_the_backend_cut_qualifies(
    text: str, stop: StopReason
) -> None:
    assert empty_at_cap(_reply(text, stop)) is None


def test_a_run_whose_replies_come_back_empty_says_so(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Through ``mcgyvr run``: the attempt's detail is the new refusal."""

    def reasons_until_the_cap(
        source_map: Any, rung: str, request: Any, **_: Any
    ) -> Completion:
        return _reply(
            "",
            StopReason.TRUNCATED,
            max_output_tokens=request.max_output_tokens,
            output_tokens=request.max_output_tokens,
        )

    lj.patch_dispatch(monkeypatch, reasons_until_the_cap)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    out = capsys.readouterr().out
    result = json.loads(lj.result_path(out).read_text())
    details = [attempt["detail"] for attempt in result["attempts"]]
    assert details, result
    for detail in details:
        assert "reply[empty-reply]" in detail, detail
        assert "on hidden reasoning" in detail, detail
        assert "missing its tail" not in detail, detail
