"""The Anthropic Messages API shape, read from a harness and written back to it.

mcorch is a model to its harness and a client to its rung, and the two speak
different dialects: the harness (Claude Code, pi) sends Messages API requests —
``system``, ``messages`` whose content is text, ``tool_use`` and ``tool_result``
blocks, ``tools`` with an ``input_schema`` — and the rung (llama.cpp, vLLM)
speaks OpenAI chat/completions, where a call is ``tool_calls`` with JSON-text
arguments and a result is a ``role: tool`` turn. This module is the one place
the two meet, in both directions, so nothing else has to know either shape.

Three rules are structural:

* **Nothing the rung cannot read is forwarded.** Images, documents and thinking
  blocks are dropped and counted (:func:`to_openai_turns` returns the kinds
  dropped), never passed through as text the rung would have to guess at.
* **A tool result follows its call.** OpenAI requires a ``tool`` turn directly
  after the assistant turn that called it; the Messages API puts results in the
  next user message, before any text. Results are emitted first, in block order,
  and the user's text after them.
* **The harness gets only what it can run.** A call whose arguments are not
  JSON is named by :func:`unreadable_calls` and never becomes a ``tool_use``
  block, because a ``tool_use`` with no object input is a request the harness
  cannot carry out and the rung would never learn why.

The streaming shape is the documented one: ``message_start``, then per content
block ``content_block_start`` / ``content_block_delta`` / ``content_block_stop``,
then ``message_delta`` carrying ``stop_reason`` and the output count, then
``message_stop``; ``ping`` events keep the connection open while the loop
works. The text behind the events is complete before the first event is
written — buffered, by design — and a reader depends on the sequence and the
shapes, not the pacing.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr.mcorch.wire import RungReply
from mcgyvr.orchestrator.read import estimate_tokens

#: The API version header every Messages request carries.
API_VERSION = "2023-06-01"

#: The roles a Messages request may carry; a facade accepts no others.
_ROLES = frozenset({"user", "assistant"})

#: The block types this module can translate. Every other block is dropped and
#: counted by kind.
_TEXT = "text"
_TOOL_USE = "tool_use"
_TOOL_RESULT = "tool_result"


@dataclass(frozen=True)
class ApiError:
    """A refusal in the API's own shape: a status and a typed error object."""

    status: int
    kind: str
    message: str

    def body(self) -> bytes:
        return json.dumps(
            {"type": "error", "error": {"type": self.kind, "message": self.message}}
        ).encode("utf-8")


def invalid(message: str) -> ApiError:
    """A 400 ``invalid_request_error`` with ``message``."""
    return ApiError(400, "invalid_request_error", message)


@dataclass(frozen=True)
class MessagesRequest:
    """A Messages request as the loop reads it: the fields mcorch acts on."""

    model: str
    max_tokens: int
    messages: tuple[Mapping[str, Any], ...]
    system: str = ""
    tools: tuple[Mapping[str, Any], ...] = ()
    stream: bool = False
    metadata: Mapping[str, Any] | None = None


def parse_request(body: bytes) -> MessagesRequest | ApiError:
    """Read a Messages request body, or say which field refused it.

    Fields the loop does not act on (``temperature``, ``stop_sequences``,
    ``thinking``, ``tool_choice``, ``cache_control`` …) are accepted and
    ignored: a facade that refused every harness extension would refuse every
    harness.
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
    """The system prompt as one string, or ``None`` when it is neither shape."""
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


# --- harness -> rung ---------------------------------------------------------


def to_openai_turns(
    messages: Sequence[Mapping[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    """The conversation as OpenAI turns, and the kinds of block dropped.

    A user message's ``tool_result`` blocks come first, each as a ``tool`` turn,
    then its text as one ``user`` turn. An assistant message's text is its
    ``content`` and its ``tool_use`` blocks are its ``tool_calls``. A block of
    any other kind is dropped and its kind recorded, in order of appearance.
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
    """A tool result's content as text; nested non-text blocks are dropped."""
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
    """Messages API tool definitions as OpenAI function tools."""
    functions: list[dict[str, Any]] = []
    for tool in tools:
        function: dict[str, Any] = {
            "name": str(tool.get("name", "")),
            "description": str(tool.get("description", "")),
            "parameters": tool.get("input_schema") or {"type": "object"},
        }
        functions.append({"type": "function", "function": function})
    return tuple(functions)


# --- rung -> harness ---------------------------------------------------------


def unreadable_calls(reply: RungReply) -> tuple[str, ...]:
    """The ids of the reply's calls whose arguments are not a JSON object."""
    unreadable: list[str] = []
    for call in reply.tool_calls:
        if _arguments(call.arguments) is None:
            unreadable.append(call.id)
    return tuple(unreadable)


def _arguments(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def new_id(prefix: str) -> str:
    """A fresh id in the API's spelling: a prefix and hex nobody else minted."""
    return f"{prefix}_{secrets.token_hex(12)}"


def message_from(
    reply: RungReply,
    *,
    model: str,
    message_id: str,
    input_tokens: int | None = None,
) -> dict[str, Any]:
    """The rung's reply as a Messages API ``message`` object.

    Text first, then one ``tool_use`` block per readable call, each under an
    id minted here (the rung's own ids are its wire, not the harness's). The
    stop reason is ``tool_use`` when the message calls, ``max_tokens`` when the
    rung was cut, else ``end_turn``. Token counts are the rung's where it
    reported them and the product's estimate where it did not — a usage object
    is required by the shape, and an estimate says so by being an estimate.
    """
    content: list[dict[str, Any]] = []
    if reply.text:
        content.append({"type": _TEXT, "text": reply.text})
    for call in reply.tool_calls:
        arguments = _arguments(call.arguments)
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
    """The SSE events a complete ``message`` streams as: (event name, JSON data)."""
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
    """One server-sent event on the wire: its name, its data, a blank line."""
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n".encode()


#: The keep-alive a facade sends while it has nothing to say yet.
PING = sse("ping", {"type": "ping"})
