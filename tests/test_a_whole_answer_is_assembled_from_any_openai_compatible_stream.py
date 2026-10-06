"""A whole answer is assembled from any OpenAI-compatible stream, in product core.

A model server notices that whoever asked has gone only when it writes, and an
answer not streamed is written once, at its end. So the product asks every
unit for a stream behind the scenes and assembles the whole answer itself, in
one product-core module (:mod:`mcgyvr.whole`) the runner uses and the rig
agent's relay reuses: never two copies. What is held here:

* the request's JSON object is asked for a stream and its counts, its own
  stream options kept (``asking`` on the object, ``as_stream`` on its bytes;
  bytes that are no JSON object are left to go as they came);
* the assembly takes each choice by index, joins its deltas (content,
  reasoning, tool calls, token probabilities), reads the finish reason, the
  usage and the standard fields from the last event that names them, and
  passes what else the last event carries at its top through (llama.cpp's
  ``timings``; any engine's own field), so a non-llama engine's answer keeps
  what its own whole answer would have had;
* an error is the status its code says and the error as the body, whether
  written as llama.cpp's ``error:`` line or as a hosted API's ``data:`` object
  that is an error and no completion;
* a stream that ends with neither answer nor error is no answer, an event
  split across reads is read whole, and an event longer than any of a chat
  completion's is a ``ValueError``.
"""

from __future__ import annotations

import json

import pytest

from mcgyvr import whole as whole_module
from mcgyvr.whole import JSON_TYPE, MAX_EVENT_BYTES, Whole, as_stream, asking

REQUEST = {
    "model": "a-model",
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 300,
}


def _event(**fields: object) -> bytes:
    return b"data: " + json.dumps(fields).encode() + b"\n\n"


def _finish(index: int = 0, reason: str = "stop", **more: object) -> bytes:
    return _event(
        choices=[{"index": index, "delta": {}, "finish_reason": reason}], **more
    )


# -- asking for the stream ----------------------------------------------------


def test_a_request_is_asked_for_a_stream_and_its_counts_keeping_its_own_options() -> (
    None
):
    asked = asking(REQUEST | {"stream_options": {"include_obfuscation": False}})
    assert asked == REQUEST | {
        "stream": True,
        "stream_options": {"include_obfuscation": False, "include_usage": True},
    }
    assert asking(REQUEST | {"stream": False}) == REQUEST | {
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    given = dict(REQUEST)
    asking(given)
    assert given == REQUEST  # a new object; the given one is not changed


def test_a_body_is_asked_for_a_stream_and_one_that_is_no_json_object_is_left() -> None:
    streamed = as_stream(json.dumps(REQUEST).encode())
    assert streamed is not None
    assert json.loads(streamed) == asking(REQUEST)
    for body in (b"[1, 2]", b"not json", b'"\\ud800"'):
        assert as_stream(body) is None


# -- the assembly -------------------------------------------------------------


def test_the_whole_answer_takes_each_choice_by_index_and_skips_what_is_no_event() -> (
    None
):
    whole = Whole()
    for piece in (
        b": a comment\n\n",
        b"data: not json\n\n",
        b'data: {"choices": [{"index": 1, "delta": {"content": "two"}}]}\n\n',
        b'data: {"choices": [{"index": 0, "delta": {"content": "one"}}]}\n\n',
        b'data: {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"},'
        b' {"index": 1, "delta": {}, "finish_reason": "length"}],'
        b' "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},'
        b' "created": 5, "id": "x", "model": "m", "system_fingerprint": "f"}\n\n',
        b"data: [DONE]\n\n",
    ):
        whole.feed(piece)
    answer = whole.answer()
    assert answer is not None
    status, kind, body = answer
    assert (status, kind) == (200, JSON_TYPE)
    assert json.loads(body) == {
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {"role": "assistant", "content": "one"},
            },
            {
                "finish_reason": "length",
                "index": 1,
                "message": {"role": "assistant", "content": "two"},
            },
        ],
        "created": 5,
        "id": "x",
        "model": "m",
        "object": "chat.completion",
        "system_fingerprint": "f",
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }
    assert whole.size == len(b"onetwo")


def test_what_else_the_last_event_carries_passes_through_as_it_says_it() -> None:
    """``timings`` is llama.cpp's; another engine has fields of its own. The
    standard's are assembled, the rest pass through, the last word winning,
    and ``null`` usage along the way (vLLM's) is no usage."""
    whole = Whole()
    whole.feed(
        _event(
            choices=[{"index": 0, "delta": {"content": "a"}}],
            usage=None,
            prompt_logprobs=[{"tok": -0.1}],
            service_tier="default",
            timings={"predicted_n": 1},
        )
    )
    whole.feed(
        _finish(
            usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            timings={"predicted_n": 7, "predicted_per_second": 56.7},
            service_tier=None,
        )
    )
    answer = whole.answer()
    assert answer is not None
    assert json.loads(answer[2]) == {
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {"role": "assistant", "content": "a"},
            }
        ],
        "object": "chat.completion",
        "prompt_logprobs": [{"tok": -0.1}],
        "service_tier": None,
        "timings": {"predicted_n": 7, "predicted_per_second": 56.7},
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
    }


def test_the_body_is_written_as_llama_cpp_writes_it_compact_with_keys_in_order() -> (
    None
):
    whole = Whole()
    whole.feed(_event(id="x", choices=[{"index": 0, "delta": {"content": "é"}}]))
    whole.feed(_finish())
    answer = whole.answer()
    assert answer is not None
    assert answer[2] == (
        b'{"choices":[{"finish_reason":"stop","index":0,'
        b'"message":{"content":"\xc3\xa9","role":"assistant"}}],'
        b'"id":"x","object":"chat.completion"}'
    )


def test_reasoning_tool_calls_and_token_probabilities_join_by_their_index() -> None:
    whole = Whole()
    whole.feed(
        _event(
            choices=[
                {
                    "index": 0,
                    "delta": {"reasoning_content": "Let me", "content": None},
                    "logprobs": {"content": [{"token": "a", "logprob": -0.1}]},
                }
            ]
        )
    )
    whole.feed(
        _event(
            choices=[
                {
                    "index": 0,
                    "delta": {
                        "reasoning_content": " think.",
                        "tool_calls": [
                            {
                                "index": 1,
                                "id": "call_2",
                                "type": "function",
                                "function": {"name": "count", "arguments": "{"},
                            },
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "lookup", "arguments": '{"q":'},
                            },
                        ],
                    },
                    "logprobs": {"content": [{"token": "b", "logprob": -0.2}]},
                }
            ]
        )
    )
    whole.feed(
        _event(
            choices=[
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"arguments": ' "x"}'}},
                            {"index": 1, "function": {"arguments": "}"}},
                        ]
                    },
                }
            ]
        )
    )
    whole.feed(_finish(reason="tool_calls"))
    answer = whole.answer()
    assert answer is not None
    assert json.loads(answer[2])["choices"] == [
        {
            "finish_reason": "tool_calls",
            "index": 0,
            "message": {
                "role": "assistant",
                "reasoning_content": "Let me think.",
                "content": None,
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {"name": "lookup", "arguments": '{"q": "x"}'},
                        "id": "call_1",
                    },
                    {
                        "type": "function",
                        "function": {"name": "count", "arguments": "{}"},
                        "id": "call_2",
                    },
                ],
            },
            "logprobs": {
                "content": [
                    {"token": "a", "logprob": -0.1},
                    {"token": "b", "logprob": -0.2},
                ]
            },
        }
    ]


def test_an_event_split_across_reads_is_read_whole() -> None:
    event = b'data: {"choices": [{"index": 0, "delta": {"content": "ab"}}]}\n\n'
    whole = Whole()
    for n in range(len(event)):
        whole.feed(event[n : n + 1])
    whole.feed(_finish())
    answer = whole.answer()
    assert answer is not None
    assert json.loads(answer[2])["choices"][0]["message"]["content"] == "ab"


def test_a_stream_with_no_finish_reason_and_no_error_is_no_answer() -> None:
    whole = Whole()
    whole.feed(b'data: {"choices": [{"index": 0, "delta": {"content": "ab"}}]}\n\n')
    assert whole.answer() is None
    whole.feed(b"data: [DONE]\n\n")
    assert whole.answer() is None
    assert Whole().answer() is None


# -- errors -------------------------------------------------------------------


def test_an_error_line_is_the_status_its_code_says_and_the_error_as_the_body() -> None:
    """llama.cpp writes an error mid-stream as an ``error:`` line."""
    error = {"code": 503, "message": "slot unavailable", "type": "unavailable_error"}
    whole = Whole()
    whole.feed(_event(choices=[{"index": 0, "delta": {"content": "a"}}]))
    whole.feed(b"error: " + json.dumps(error).encode() + b"\n\n")
    assert whole.answer() == (503, JSON_TYPE, whole_module.dump({"error": error}))

    unreadable = Whole()
    unreadable.feed(b"error: not json\n\n")
    assert unreadable.answer() == (
        500,
        JSON_TYPE,
        whole_module.dump({"error": {"message": "not json"}}),
    )


def test_a_data_event_that_is_an_error_and_no_completion_is_the_error() -> None:
    """The hosted APIs and vLLM write an error mid-stream as a ``data:``
    object holding ``error`` and no ``choices``; its code is a word, so the
    status is the server's own failure."""
    error = {"message": "rate limited", "type": "rate_limit_error", "code": "rate"}
    whole = Whole()
    whole.feed(_event(choices=[{"index": 0, "delta": {"content": "a"}}]))
    whole.feed(_event(error=error))
    assert whole.answer() == (500, JSON_TYPE, whole_module.dump({"error": error}))


@pytest.mark.parametrize("code", [399, 600, True, "500", None])
def test_an_error_whose_code_is_no_status_is_a_server_error(code: object) -> None:
    whole = Whole()
    whole.feed(
        b"error: " + json.dumps({"code": code, "message": "x"}).encode() + b"\n\n"
    )
    answer = whole.answer()
    assert answer is not None
    assert answer[0] == 500


def test_an_event_too_long_to_be_one_is_a_unit_that_speaks_no_stream() -> None:
    whole = Whole()
    whole.feed(b"data: " + b"x" * (MAX_EVENT_BYTES - 6))  # just the bound
    with pytest.raises(ValueError):
        whole.feed(b"y")
