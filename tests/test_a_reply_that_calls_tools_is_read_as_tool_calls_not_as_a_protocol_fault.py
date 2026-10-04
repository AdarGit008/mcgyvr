"""A reply that calls tools is read as tool calls, not as a protocol fault.

A compatible server answering a request that offered tools may ask for one or
more of them instead of answering in text: ``choices[0].message.tool_calls``
carries each call's id, the tool's name and its arguments as the JSON text the
model wrote, ``content`` is then ``null`` (or absent, or a string beside the
calls), and ``finish_reason`` is ``"tool_calls"``. That reply is read as what it
is — a completion whose text is empty, whose stop reason is
:attr:`StopReason.TOOL_CALLS`, which says it wants tools and is not
``complete`` — and the arguments stay text: parsing them is the caller's
business, because a model writing malformed JSON is a fact about the model and
not about the wire.

What stays a protocol fault: ``content`` that is not a string with no tool calls
beside it (the reply an empty file would otherwise be made from), and a tool
call missing the id or name a caller needs to run and answer it — the error
names what was missing. A plain text reply comes back exactly as before, with no
tool calls; and a telemetry row records how many tool calls a reply made only
when it made some, so an absent count never reads as zero.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import runner as runner_module
from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.runner import (
    Completion,
    ProtocolError,
    Request,
    StopReason,
    ToolCall,
    runner_for,
)
from mcgyvr.telemetry import _completion_fields

ENDPOINT = Endpoint(
    source="workstation",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=1,
    credential_env=None,
)

ASK = Request(prompt="what does f return?", max_output_tokens=256)


def reply(message: dict[str, Any], finish_reason: str = "tool_calls") -> dict[str, Any]:
    return {
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 12},
    }


def call(
    call_id: str = "call-1",
    name: str = "read_file",
    arguments: str = '{"path": "a.py"}',
) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def answered_with(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> None:
    """Script the wire to answer every dispatch with ``document``."""

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        return document

    monkeypatch.setattr(runner_module, "_post_json", fake_post, raising=True)


def test_tool_calls_with_null_content_are_read_as_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answered_with(
        monkeypatch,
        reply(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    call(),
                    call("call-2", "list_dir", '{"path": "."}'),
                ],
            }
        ),
    )
    done = runner_for(ENDPOINT).generate("m", ASK)
    assert done.tool_calls == (
        ToolCall(id="call-1", name="read_file", arguments='{"path": "a.py"}'),
        ToolCall(id="call-2", name="list_dir", arguments='{"path": "."}'),
    )
    assert done.text == ""
    assert done.stop_reason is StopReason.TOOL_CALLS
    assert done.raw_stop_reason == "tool_calls"
    assert done.wants_tools is True
    assert done.complete is False
    assert done.output_tokens == 12


def test_absent_content_beside_tool_calls_is_empty_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answered_with(monkeypatch, reply({"role": "assistant", "tool_calls": [call()]}))
    done = runner_for(ENDPOINT).generate("m", ASK)
    assert done.text == ""
    assert [c.name for c in done.tool_calls] == ["read_file"]


def test_text_beside_tool_calls_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    answered_with(
        monkeypatch,
        reply(
            {
                "role": "assistant",
                "content": "Reading a.py first.",
                "tool_calls": [call()],
            }
        ),
    )
    done = runner_for(ENDPOINT).generate("m", ASK)
    assert done.text == "Reading a.py first."
    assert len(done.tool_calls) == 1


def test_absent_arguments_are_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = {"id": "call-1", "type": "function", "function": {"name": "now"}}
    answered_with(monkeypatch, reply({"content": None, "tool_calls": [entry]}))
    done = runner_for(ENDPOINT).generate("m", ASK)
    assert done.tool_calls == (ToolCall(id="call-1", name="now", arguments=""),)


def test_arguments_are_kept_as_written_even_when_they_are_not_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner does not parse them; a caller decides what bad JSON means."""
    answered_with(
        monkeypatch,
        reply({"content": None, "tool_calls": [call(arguments='{"path": ')]}),
    )
    done = runner_for(ENDPOINT).generate("m", ASK)
    assert done.tool_calls[0].arguments == '{"path": '


def test_tool_calls_under_another_finish_reason_still_want_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Some servers say ``stop`` beside the calls; the calls are the evidence."""
    answered_with(monkeypatch, reply({"content": None, "tool_calls": [call()]}, "stop"))
    done = runner_for(ENDPOINT).generate("m", ASK)
    assert done.stop_reason is StopReason.COMPLETE
    assert done.wants_tools is True


def test_a_plain_text_reply_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    answered_with(
        monkeypatch, reply({"role": "assistant", "content": "it returns 1"}, "stop")
    )
    done = runner_for(ENDPOINT).generate("m", ASK)
    assert done.text == "it returns 1"
    assert done.tool_calls == ()
    assert done.wants_tools is False
    assert done.complete is True


def test_null_tool_calls_beside_text_is_a_plain_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answered_with(
        monkeypatch,
        reply({"content": "it returns 1", "tool_calls": None}, "stop"),
    )
    done = runner_for(ENDPOINT).generate("m", ASK)
    assert done.tool_calls == ()
    assert done.wants_tools is False


@pytest.mark.parametrize(
    "message",
    [
        {"role": "assistant", "content": None},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "assistant", "content": 7, "tool_calls": None},
    ],
)
def test_no_string_content_and_no_tool_calls_stays_a_protocol_fault(
    monkeypatch: pytest.MonkeyPatch, message: dict[str, Any]
) -> None:
    answered_with(monkeypatch, reply(message, "stop"))
    with pytest.raises(ProtocolError, match="string content"):
        runner_for(ENDPOINT).generate("m", ASK)


@pytest.mark.parametrize(
    ("tool_calls", "missing"),
    [
        ("read_file", "list"),
        (["read_file"], "object"),
        ([{"type": "function", "function": {"name": "f"}}], "id"),
        ([{"id": 3, "function": {"name": "f"}}], "id"),
        ([{"id": "call-1"}], "function"),
        ([{"id": "call-1", "function": {"arguments": "{}"}}], "function.name"),
        ([{"id": "call-1", "function": {"name": None}}], "function.name"),
        (
            [{"id": "call-1", "function": {"name": "f", "arguments": {"a": 1}}}],
            "function.arguments",
        ),
    ],
)
def test_a_malformed_tool_call_is_a_protocol_fault_naming_what_is_missing(
    monkeypatch: pytest.MonkeyPatch, tool_calls: Any, missing: str
) -> None:
    answered_with(monkeypatch, reply({"content": None, "tool_calls": tool_calls}))
    with pytest.raises(ProtocolError, match="tool_calls") as raised:
        runner_for(ENDPOINT).generate("m", ASK)
    assert missing in str(raised.value)


def completion(tool_calls: tuple[ToolCall, ...]) -> Completion:
    return Completion(
        text="",
        stop_reason=StopReason.TOOL_CALLS,
        raw_stop_reason="tool_calls",
        model="m",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=256,
        latency_s=0.5,
        tool_calls=tool_calls,
    )


def test_a_telemetry_row_counts_tool_calls_only_when_there_were_some() -> None:
    asked = completion((ToolCall(id="c1", name="f", arguments="{}"),) * 2)
    assert _completion_fields(asked)["tool_calls"] == 2
    assert _completion_fields(asked)["stop_reason"] == "tool_calls"
    assert "tool_calls" not in _completion_fields(completion(()))
