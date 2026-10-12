"""A request may carry the turns before it and the tools on offer.

A conversation with a rung is several dispatches, and each one has to send
everything said so far: the system prompt, then the earlier turns exactly as
they were exchanged (the user's, the assistant's own, including the tool calls
it asked for, and each tool's answer), then — when there is one — the new user
message last. A request that only continues a conversation after a tool
answered has no new user message, and none is invented for it.

Tools are offered as the OpenAI function tools the compatible servers read, with
``tool_choice: "auto"``; a request that offers none sends neither key, so every
single-turn request goes out exactly as it did before.

The turns are checked cheaply when the request is built: each is a mapping with
a role the protocol knows. A system turn among them is refused, because the
system prompt has one home, :attr:`Request.system`, and two would be two
different requests depending on which one a server reads.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import runner as runner_module
from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.runner import Request, runner_for

ENDPOINT = Endpoint(
    source="workstation",
    base_url="http://localhost:8080",
    protocol=Protocol.OPENAI,
    max_parallel=1,
    credential_env=None,
)

READ_FILE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read one file of the repository.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}

TURNS: tuple[dict[str, Any], ...] = (
    {"role": "user", "content": "what does f return?"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
            }
        ],
    },
    {"role": "tool", "tool_call_id": "call-1", "content": "def f():\n    return 1\n"},
)


def sent_payload(monkeypatch: pytest.MonkeyPatch, request: Request) -> dict[str, Any]:
    """Dispatch ``request`` against a stubbed wire and return the body it sent."""
    sent: list[dict[str, Any]] = []

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append(payload)
        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "1"},
                    "finish_reason": "stop",
                }
            ]
        }

    monkeypatch.setattr(runner_module, "_post_json", fake_post, raising=True)
    runner_for(ENDPOINT).generate("m", request)
    assert len(sent) == 1
    return sent[0]


def test_the_system_prompt_then_the_turns_verbatim_then_the_prompt_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = Request(
        prompt="and what does g return?",
        max_output_tokens=64,
        system="be terse",
        turns=TURNS,
    )
    payload = sent_payload(monkeypatch, request)
    assert payload["messages"] == [
        {"role": "system", "content": "be terse"},
        *TURNS,
        {"role": "user", "content": "and what does g return?"},
    ]


def test_a_request_continuing_after_a_tool_answer_appends_no_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = Request(prompt="", max_output_tokens=64, turns=TURNS)
    payload = sent_payload(monkeypatch, request)
    assert payload["messages"] == list(TURNS)


def test_an_empty_prompt_with_no_turns_is_still_the_one_user_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a request carrying turns drops the empty prompt: a single-turn
    request goes out exactly as it did before turns existed."""
    payload = sent_payload(monkeypatch, Request(prompt="", max_output_tokens=64))
    assert payload["messages"] == [{"role": "user", "content": ""}]


def test_tools_are_offered_with_tool_choice_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = Request(prompt="read a.py", max_output_tokens=64, tools=(READ_FILE,))
    payload = sent_payload(monkeypatch, request)
    assert payload["tools"] == [READ_FILE]
    assert payload["tool_choice"] == "auto"


def test_a_request_offering_no_tools_sends_neither_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = sent_payload(monkeypatch, Request(prompt="hi", max_output_tokens=64))
    assert "tools" not in payload
    assert "tool_choice" not in payload


def test_a_response_schema_and_tools_may_be_sent_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    request = Request(
        prompt="read a.py",
        max_output_tokens=64,
        tools=(READ_FILE,),
        response_schema=schema,
    )
    payload = sent_payload(monkeypatch, request)
    assert payload["tools"] == [READ_FILE]
    assert payload["response_format"]["json_schema"]["schema"] == schema


@pytest.mark.parametrize(
    "turn",
    [
        "user: hello",
        {"content": "no role"},
        {"role": "narrator", "content": "an unknown role"},
        {"role": 3, "content": "a role that is not a word"},
    ],
)
def test_a_turn_that_is_not_a_known_role_is_refused(turn: Any) -> None:
    with pytest.raises(ValueError, match="turn"):
        Request(prompt="", max_output_tokens=64, turns=(turn,))


def test_a_system_turn_is_refused_because_the_system_prompt_has_one_home() -> None:
    with pytest.raises(ValueError, match=r"Request\.system"):
        Request(
            prompt="",
            max_output_tokens=64,
            turns=({"role": "system", "content": "be terse"},),
        )
