"""Where the Anthropic Messages shape and the OpenAI chat shape meet.

mcorch serves the Messages API to a harness and calls its rung with OpenAI
chat turns, so both translations live here: :func:`parse_request` reads an
inbound body into a :class:`MessagesRequest` (or an :class:`ApiError` naming
the field that made it unreadable), :func:`to_openai_turns` and
:func:`tools_to_openai` rewrite that request for the rung, and
:func:`message_from` turns the rung's :class:`~mcgyvr.mcorch.wire.RungReply`
back into a Messages message, whose streaming form :func:`events_for` lays out
as the event sequence :mod:`mcgyvr.mcorch.serve` writes.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr.mcorch import guard
from mcgyvr.mcorch.wire import RungReply
from mcgyvr.orchestrator.read import estimate_tokens

# The only roles a message may carry; `system` is a separate field.
_ROLES = frozenset({"user", "assistant"})

# The block types carried across to the OpenAI shape; every other type is
# dropped from a message block and recorded by name, never forwarded.
_TEXT = "text"
_TOOL_USE = "tool_use"
_TOOL_RESULT = "tool_result"


@dataclass(frozen=True)
class ApiError:
    """A refusal in the Messages API's own error shape.

    Returned rather than raised, so a caller can answer it as a body:
    ``status`` is the HTTP code, ``kind`` the error type, ``message`` the text
    that names the field at fault.
    """

    status: int
    kind: str
    message: str

    def body(self) -> bytes:
        return json.dumps(
            {"type": "error", "error": {"type": self.kind, "message": self.message}}
        ).encode("utf-8")


def invalid(message: str) -> ApiError:
    """A request the API refuses before any rung is called.

    Always 400 ``invalid_request_error``; ``message`` names the field at
    fault.
    """
    return ApiError(400, "invalid_request_error", message)


@dataclass(frozen=True)
class MessagesRequest:
    """A Messages request that passed validation, in the fields this facade
    reads: ``system`` already flattened to one string, ``tools`` still the raw
    definitions, ``metadata`` kept only when it was an object."""

    model: str
    max_tokens: int
    messages: tuple[Mapping[str, Any], ...]
    system: str = ""
    tools: tuple[Mapping[str, Any], ...] = ()
    stream: bool = False
    metadata: Mapping[str, Any] | None = None


def parse_request(body: bytes) -> MessagesRequest | ApiError:
    """Read a JSON body as a :class:`MessagesRequest`, or as an
    :class:`ApiError` naming the field that made it unreadable.

    ``messages`` must be a non-empty list of objects whose ``role`` is one of
    :data:`_ROLES` and whose ``content`` is a string or a list of blocks;
    ``system`` may be absent, a string, or a list of text blocks. A missing
    ``tools`` is empty, a missing ``stream`` is false, and ``metadata`` that is
    not an object is dropped rather than refused.
    """
    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return invalid(f"the body is not JSON: {exc}")
    if not isinstance(raw, dict):
        return invalid("the body must be a JSON object")
    model = raw.get("model")
    if not isinstance(model, str) or not model:
        return invalid("model: a non-empty string is required")
    max_tokens = raw.get("max_tokens")
    if (
        isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or max_tokens < 1
    ):
        return invalid("max_tokens: a whole number of at least 1 is required")
    messages = raw.get("messages")
    if not isinstance(messages, list) or not messages:
        return invalid("messages: a non-empty list is required")
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            return invalid(f"messages[{index}]: each message is an object")
        if message.get("role") not in _ROLES:
            roles = ", ".join(sorted(_ROLES))
            return invalid(f"messages[{index}].role: one of {roles} is required")
        if not isinstance(message.get("content"), (str, list)):
            return invalid(f"messages[{index}].content: a string or a list of blocks")
    system = _system_text(raw.get("system"))
    if system is None:
        return invalid("system: a string or a list of text blocks")
    tools_raw = raw.get("tools", [])
    if not isinstance(tools_raw, list):
        return invalid("tools: a list of tool definitions")
    tools: list[Mapping[str, Any]] = []
    for index, tool in enumerate(tools_raw):
        if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
            return invalid(f"tools[{index}].name: a string is required")
        tools.append(tool)
    stream = raw.get("stream", False)
    if not isinstance(stream, bool):
        return invalid("stream: true or false")
    metadata = raw.get("metadata")
    return MessagesRequest(
        model=model,
        max_tokens=max_tokens,
        messages=tuple(messages),
        system=system,
        tools=tuple(tools),
        stream=stream,
        metadata=metadata if isinstance(metadata, dict) else None,
    )


def _system_text(system: object) -> str | None:
    """Flatten a ``system`` field to one string, or None when it cannot be read.

    Absent is the empty string; a list is accepted only when every entry is a
    ``text`` block with a string ``text``, and those texts are joined by blank
    lines.
    """
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    if not isinstance(system, list):
        return None
    parts: list[str] = []
    for block in system:
        if not isinstance(block, dict) or block.get("type") != _TEXT:
            return None
        text = block.get("text")
        if not isinstance(text, str):
            return None
        parts.append(text)
    return "\n\n".join(parts)


# The request going out to the rung: Anthropic blocks written as OpenAI turns.


def to_openai_turns(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    """Rewrite the request's messages as OpenAI chat turns.

    Returns the turns and, in the order they were met, the block types that
    were dropped on the way, so a trace can say what the rung never saw.
    """
    turns: list[dict[str, Any]] = []
    dropped: list[str] = []
    for message in messages:
        role = str(message.get("role"))
        content = message.get("content")
        if isinstance(content, str):
            turns.append({"role": role, "content": content})
            continue
        blocks = [block for block in content or () if isinstance(block, dict)]
        if role == "user":
            turns.extend(_user_turns(blocks, dropped))
        else:
            turns.append(_assistant_turn(blocks, dropped))
    return tuple(turns), tuple(dropped)


def _user_turns(
    blocks: Sequence[Mapping[str, Any]], dropped: list[str]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    texts: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind == _TOOL_RESULT:
            text = _result_text(block.get("content"), dropped)
            if block.get("is_error"):
                text = f"error: {text}"
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": str(block.get("tool_use_id", "")),
                    "content": text,
                }
            )
        elif kind == _TEXT and isinstance(block.get("text"), str):
            texts.append(block["text"])
        else:
            dropped.append(str(kind))
    if texts:
        results.append({"role": "user", "content": "\n".join(texts)})
    return results


def _result_text(content: object, dropped: list[str]) -> str:
    """The text of a ``tool_result``: a string as it stands, or a list's
    ``text`` blocks joined by newlines, with its other object blocks recorded
    as dropped.
    """
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content if isinstance(content, list) else ():
        if isinstance(block, dict) and block.get("type") == _TEXT:
            parts.append(str(block.get("text", "")))
        elif isinstance(block, dict):
            dropped.append(str(block.get("type")))
    return "\n".join(parts)


def _assistant_turn(
    blocks: Sequence[Mapping[str, Any]], dropped: list[str]
) -> dict[str, Any]:
    texts: list[str] = []
    calls: list[dict[str, Any]] = []
    for block in blocks:
        kind = block.get("type")
        if kind == _TEXT and isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif kind == _TOOL_USE:
            arguments = block.get("input")
            calls.append(
                {
                    "id": str(block.get("id", "")),
                    "type": "function",
                    "function": {
                        "name": str(block.get("name", "")),
                        "arguments": json.dumps(
                            arguments if isinstance(arguments, dict) else {}
                        ),
                    },
                }
            )
        else:
            dropped.append(str(kind))
    turn: dict[str, Any] = {"role": "assistant", "content": "\n".join(texts)}
    if calls:
        turn["tool_calls"] = calls
    return turn


def tools_to_openai(
    tools: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Rewrite tool definitions as OpenAI function tools.

    A definition's ``input_schema`` becomes the function's ``parameters``, and
    a definition that carries none gets an empty object schema.
    """
    functions: list[dict[str, Any]] = []
    for tool in tools:
        function: dict[str, Any] = {
            "name": str(tool.get("name", "")),
            "description": str(tool.get("description", "")),
            "parameters": tool.get("input_schema") or {"type": "object"},
        }
        functions.append({"type": "function", "function": function})
    return tuple(functions)


# The reply coming back: what of it can be handed to a harness, and what cannot.


def unreadable_calls(reply: RungReply) -> tuple[str, ...]:
    """The ids of tool calls whose arguments did not parse into an object.

    Such a call cannot be written as a ``tool_use`` block, so the loop answers
    it itself instead of forwarding it.
    """
    unreadable: list[str] = []
    for call in reply.tool_calls:
        if guard.arguments(call.arguments) is None:
            unreadable.append(call.id)
    return tuple(unreadable)


def new_id(prefix: str) -> str:
    """An id named here rather than by the rung: the prefix, an underscore, and
    twelve random bytes as 24 hex characters."""
    return f"{prefix}_{secrets.token_hex(12)}"


def message_from(
    reply: RungReply,
    *,
    model: str,
    message_id: str,
    input_tokens: int | None = None,
) -> dict[str, Any]:
    """Build the Messages reply for a rung's answer.

    ``reply.text`` comes first, then one ``tool_use`` block per call whose
    arguments parsed into an object; a call whose arguments did not parse is
    left out. ``stop_reason`` is ``tool_use`` when the reply calls,
    ``max_tokens`` when it was truncated, and ``end_turn`` otherwise. Each
    count is the rung's own when it reported one: output falls back to an
    estimate over the serialised content, input to the caller's
    ``input_tokens`` (and then to zero).
    """
    content: list[dict[str, Any]] = []
    if reply.text:
        content.append({"type": _TEXT, "text": reply.text})
    for call in reply.tool_calls:
        arguments = guard.arguments(call.arguments)
        if arguments is None:
            continue
        content.append(
            {
                "type": _TOOL_USE,
                "id": new_id("toolu"),
                "name": call.name,
                "input": arguments,
            }
        )
    if any(block["type"] == _TOOL_USE for block in content):
        stop_reason = "tool_use"
    elif reply.truncated:
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"
    produced = (
        reply.output_tokens
        if reply.output_tokens is not None
        else estimate_tokens(json.dumps(content))
    )
    consumed = (
        reply.input_tokens
        if reply.input_tokens is not None
        else (input_tokens if input_tokens is not None else 0)
    )
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": consumed,
            "output_tokens": produced,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    }


def events_for(message: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """The events a streamed reply is sent as, each with its payload already
    serialised to JSON.

    ``message_start`` carries the message with empty content, no stop reason
    and a zero output count; each content block then gets a
    ``content_block_start`` (empty text, or a ``tool_use`` with empty input), a
    single ``content_block_delta`` (all the text, or the input as one
    ``input_json_delta``) and a ``content_block_stop``; ``message_delta``
    repeats the stop reason with the output count, and ``message_stop`` ends
    the stream.
    """
    opening = dict(message)
    opening["content"] = []
    opening["stop_reason"] = None
    usage = dict(message["usage"])
    opening["usage"] = {**usage, "output_tokens": 0}
    events: list[tuple[str, dict[str, Any]]] = [
        ("message_start", {"type": "message_start", "message": opening})
    ]
    for index, block in enumerate(message["content"]):
        if block["type"] == _TEXT:
            start: dict[str, Any] = {"type": _TEXT, "text": ""}
            delta: dict[str, Any] = {"type": "text_delta", "text": block["text"]}
        else:
            start = {
                "type": _TOOL_USE,
                "id": block["id"],
                "name": block["name"],
                "input": {},
            }
            delta = {
                "type": "input_json_delta",
                "partial_json": json.dumps(block["input"]),
            }
        events.append(
            (
                "content_block_start",
                {"type": "content_block_start", "index": index, "content_block": start},
            )
        )
        events.append(
            (
                "content_block_delta",
                {"type": "content_block_delta", "index": index, "delta": delta},
            )
        )
        events.append(
            ("content_block_stop", {"type": "content_block_stop", "index": index})
        )
    events.append(
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": message["stop_reason"], "stop_sequence": None},
                "usage": {"output_tokens": usage["output_tokens"]},
            },
        )
    )
    events.append(("message_stop", {"type": "message_stop"}))
    return tuple((name, json.dumps(data)) for name, data in events)


def sse(event: str, data: Mapping[str, Any] | str) -> bytes:
    """One server-sent event: its name, its data on a single ``data:`` line,
    and a blank line. A string is data already serialised and is passed
    through."""
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n".encode()


# The keep-alive `serve` writes while a turn is still running.
PING = sse("ping", {"type": "ping"})
