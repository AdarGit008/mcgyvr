"""An Anthropic Messages request becomes OpenAI chat turns, and a reply goes back.

mcorch is a model to its harness and a client to its rung. The harness (Claude
Code, pi) speaks the Anthropic Messages API; the rung (llama.cpp, vLLM) speaks
OpenAI chat/completions with function tools. :mod:`mcgyvr.mcorch.anthropic` is
the one place the two shapes meet, in both directions:

* ``tool_use`` blocks in an assistant message become ``tool_calls`` with the
  input serialised as the JSON text OpenAI carries; ``tool_result`` blocks in a
  user message become ``role: tool`` turns that directly follow them, before
  any user text in the same message; text blocks are joined; images, documents
  and thinking blocks are dropped and counted, never forwarded.
* A rung's reply becomes an Anthropic message: text first, then one
  ``tool_use`` block per call with the arguments parsed back into an object,
  ``stop_reason`` ``tool_use`` when it calls and ``end_turn`` when it finishes.
* A tool definition's ``input_schema`` is an OpenAI function's ``parameters``.

A request that is not a Messages request is refused with the API's own error
shape, naming the field. Every id and path here is invented.
"""

from __future__ import annotations

import json

import pytest

from mcgyvr.mcorch import anthropic
from mcgyvr.mcorch.wire import RungReply, RungToolCall


def _body(**fields: object) -> bytes:
    base: dict[str, object] = {
        "model": "mcorch",
        "max_tokens": 512,
        "messages": [{"role": "user", "content": "hello"}],
    }
    base.update(fields)
    return json.dumps(base).encode("utf-8")


def test_a_messages_request_is_read_with_its_system_tools_and_stream_flag() -> None:
    body = _body(
        system=[
            {"type": "text", "text": "You are brief."},
            {"type": "text", "text": "Really."},
        ],
        tools=[
            {
                "name": "Read",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"file_path": {"type": "string"}},
                },
            }
        ],
        stream=True,
        metadata={"user_id": "someone"},
    )
    request = anthropic.parse_request(body)
    assert isinstance(request, anthropic.MessagesRequest)
    assert request.model == "mcorch"
    assert request.max_tokens == 512
    assert request.system == "You are brief.\n\nReally."
    assert request.stream is True
    assert [tool["name"] for tool in request.tools] == ["Read"]
    assert request.messages[0]["role"] == "user"


@pytest.mark.parametrize(
    ("fields", "names"),
    [
        ({"messages": []}, "messages"),
        ({"max_tokens": 0}, "max_tokens"),
        ({"model": 7}, "model"),
        ({"messages": [{"role": "robot", "content": "x"}]}, "messages[0].role"),
    ],
)
def test_a_malformed_request_is_refused_naming_the_field(
    fields: dict[str, object], names: str
) -> None:
    refused = anthropic.parse_request(_body(**fields))
    assert isinstance(refused, anthropic.ApiError)
    assert refused.status == 400
    assert refused.kind == "invalid_request_error"
    assert names in refused.message


def test_a_body_that_is_not_json_is_refused() -> None:
    refused = anthropic.parse_request(b"{not json")
    assert isinstance(refused, anthropic.ApiError)
    assert refused.status == 400
    assert json.loads(refused.body())["error"]["type"] == "invalid_request_error"


def test_tool_use_and_tool_result_blocks_become_tool_calls_and_tool_turns() -> None:
    messages = (
        {"role": "user", "content": "format src/a.py"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Reading it."},
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "Read",
                    "input": {"file_path": "src/a.py"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_01",
                    "content": "x = 1\n",
                },
                {"type": "text", "text": "go on"},
            ],
        },
    )
    turns, dropped = anthropic.to_openai_turns(messages)
    assert dropped == ()
    assert turns[0] == {"role": "user", "content": "format src/a.py"}
    assistant = turns[1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "Reading it."
    calls = assistant["tool_calls"]
    assert calls[0]["id"] == "toolu_01"
    assert calls[0]["type"] == "function"
    assert calls[0]["function"]["name"] == "Read"
    assert json.loads(calls[0]["function"]["arguments"]) == {"file_path": "src/a.py"}
    # The tool turn directly follows the call, before the user's text.
    assert turns[2] == {
        "role": "tool",
        "tool_call_id": "toolu_01",
        "content": "x = 1\n",
    }
    assert turns[3] == {"role": "user", "content": "go on"}


def test_a_tool_result_may_carry_blocks_and_an_error_flag() -> None:
    messages = (
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_02",
                    "is_error": True,
                    "content": [{"type": "text", "text": "no such file"}],
                }
            ],
        },
    )
    turns, _ = anthropic.to_openai_turns(messages)
    assert turns[0]["role"] == "tool"
    assert turns[0]["tool_call_id"] == "toolu_02"
    assert "no such file" in turns[0]["content"]
    assert turns[0]["content"].startswith("error:")


def test_images_documents_and_thinking_are_dropped_and_counted_not_forwarded() -> None:
    messages = (
        {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "data": "AAAA"}},
                {"type": "text", "text": "what is this"},
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "hmm", "signature": "sig"},
                {"type": "text", "text": "a picture"},
            ],
        },
    )
    turns, dropped = anthropic.to_openai_turns(messages)
    assert dropped == ("image", "thinking")
    assert turns[0] == {"role": "user", "content": "what is this"}
    assert turns[1] == {"role": "assistant", "content": "a picture"}
    assert all("AAAA" not in json.dumps(turn) for turn in turns)


def test_an_anthropic_tool_is_an_openai_function() -> None:
    schema = {"type": "object", "properties": {"command": {"type": "string"}}}
    tools = anthropic.tools_to_openai(
        ({"name": "Bash", "description": "Run a command", "input_schema": schema},)
    )
    assert tools == (
        {
            "type": "function",
            "function": {
                "name": "Bash",
                "description": "Run a command",
                "parameters": schema,
            },
        },
    )


def test_a_rung_reply_that_calls_a_tool_becomes_a_tool_use_message() -> None:
    reply = RungReply(
        text="I will read it.",
        tool_calls=(
            RungToolCall(id="call_7", name="Read", arguments='{"file_path": "a.py"}'),
        ),
    )
    message = anthropic.message_from(reply, model="mcorch", message_id="msg_01")
    assert message["type"] == "message"
    assert message["role"] == "assistant"
    assert message["model"] == "mcorch"
    assert message["stop_reason"] == "tool_use"
    assert message["content"][0] == {"type": "text", "text": "I will read it."}
    use = message["content"][1]
    assert use["type"] == "tool_use"
    assert use["name"] == "Read"
    assert use["input"] == {"file_path": "a.py"}
    assert use["id"].startswith("toolu_")
    assert set(message["usage"]) >= {"input_tokens", "output_tokens"}


def test_a_rung_reply_with_text_alone_ends_the_turn() -> None:
    message = anthropic.message_from(
        RungReply(text="done", tool_calls=()), model="mcorch", message_id="msg_02"
    )
    assert message["stop_reason"] == "end_turn"
    assert message["content"] == [{"type": "text", "text": "done"}]


def test_a_truncated_reply_says_max_tokens() -> None:
    message = anthropic.message_from(
        RungReply(text="partial", tool_calls=(), truncated=True),
        model="mcorch",
        message_id="msg_03",
    )
    assert message["stop_reason"] == "max_tokens"


def test_a_tool_call_whose_arguments_are_not_json_is_not_sent_to_the_harness() -> None:
    reply = RungReply(
        text="",
        tool_calls=(RungToolCall(id="call_8", name="Bash", arguments="{broken"),),
    )
    assert anthropic.unreadable_calls(reply) == ("call_8",)
