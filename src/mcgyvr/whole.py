"""Assemble a streamed chat completion into the one answer a client asked for.

A relay may have to ask an OpenAI-protocol server to stream even when its
client wants a single JSON body: `asking` rewrites such a request, `Whole`
feeds on the server-sent events and joins each choice's deltas, and `answer`
returns the status, content type and body of the equivalent non-streamed
response. An error reported inside the stream is carried out as an error body,
and the text and logprobs taken in are counted in `size` so a caller can stop
on a reply that grows too large.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: The most one event may hold before it counts as one that never ended: a chat
#: completion's events are far smaller, so reaching this means the blank line
#: separating events never arrived. `feed` raises rather than buffer without
#: end.
MAX_EVENT_BYTES = 64 * 1024
#: The content type of an answer dumped back as one JSON body.
JSON_TYPE = "application/json; charset=utf-8"
#: The media type a chat completion is streamed as.
EVENT_STREAM = "text/event-stream"

#: The chunk keys not carried into the answer verbatim: the choices are joined
#: across events, the object is restated as a non-streamed completion's, and the
#: usage is held aside to be added after the choices.
_ASSEMBLED = frozenset({"choices", "object", "usage"})


def media(content_type: str) -> str:
    """The bare media type of a Content-Type value: parameters dropped, lowercased."""
    return content_type.split(";")[0].strip().lower()


def dump(value: Any) -> bytes:
    """The value as compact JSON, keys sorted, non-ASCII kept as itself."""
    try:
        text = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return text.encode()
    except UnicodeEncodeError:  # text UTF-8 cannot carry, so escape it instead
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def asking(request: dict[str, Any]) -> dict[str, Any]:
    """The request made to stream, keeping any stream options it already had and
    turning on the last event's usage report."""
    options = request.get("stream_options")
    return {
        **request,
        "stream": True,
        "stream_options": {
            **(options if isinstance(options, dict) else {}),
            "include_usage": True,
        },
    }


def as_stream(body: bytes) -> bytes | None:
    """The request body rewritten to stream, or None when the body is not a JSON
    object or holds text UTF-8 cannot carry, which the caller relays as it is."""
    try:
        asked = json.loads(body)
    except ValueError:
        return None
    if not isinstance(asked, dict):
        return None
    try:
        return json.dumps(
            asking(asked), ensure_ascii=False, separators=(",", ":")
        ).encode()
    except UnicodeEncodeError:  # text UTF-8 cannot carry, so stream nothing
        return None


@dataclass
class _ToolCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class _Choice:
    """One choice's fragments joined as they arrive: text, reasoning, tool calls,
    logprobs, and the finish reason once the stream reports it."""

    text: str = ""  # the content fragments joined so far
    reasoning: str = ""
    tool_calls: dict[int, _ToolCall] = field(default_factory=dict)
    logprobs: list[Any] = field(default_factory=list)
    finish_reason: str | None = None

    def whole(self, index: int) -> dict[str, Any]:
        """This choice as one entry of a non-streamed answer, its tool calls in
        index order and its content null only when the reply is tool calls alone."""
        message: dict[str, Any] = {"role": "assistant"}
        if self.reasoning:
            message["reasoning_content"] = self.reasoning
        message["content"] = None if not self.text and self.tool_calls else self.text
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                    "id": call.id,
                }
                for _, call in sorted(self.tool_calls.items())
            ]
        choice: dict[str, Any] = {
            "finish_reason": self.finish_reason,
            "index": index,
            "message": message,
        }
        if self.logprobs:
            choice["logprobs"] = {"content": self.logprobs}
        return choice


class Whole:
    """One streamed answer being assembled: `feed` it the bytes as they arrive
    and `answer` returns the whole body once every choice has finished."""

    def __init__(self) -> None:
        self._held = b""  # the event so far, short of its blank-line separator
        self._choices: dict[int, _Choice] = {}
        self._last: dict[str, Any] = {}  # chunk fields kept for the answer, later wins
        self._usage: dict[str, Any] | None = None
        self._error: Any = None
        self.size = 0

    def feed(self, chunk: bytes) -> None:
        self._held += chunk
        while (cut := self._held.find(b"\n\n")) >= 0:
            event, self._held = self._held[:cut], self._held[cut + 2 :]
            self._event(event)
        if len(self._held) > MAX_EVENT_BYTES:
            raise ValueError("an event longer than any of a chat completion's")

    def answer(self) -> tuple[int, str, bytes] | None:
        """The answer as status, content type and body, or None while any choice
        still lacks a finish reason; an error met in the stream becomes an error
        body, carrying its code as the status when that code is one."""
        if self._error is not None:
            code = self._error.get("code") if isinstance(self._error, dict) else None
            status = 500
            if (
                isinstance(code, int)
                and not isinstance(code, bool)
                and 400 <= code <= 599
            ):
                status = code
            return status, JSON_TYPE, dump({"error": self._error})
        if not self._choices or any(
            choice.finish_reason is None for choice in self._choices.values()
        ):
            return None
        answer: dict[str, Any] = {
            **self._last,
            "choices": [
                choice.whole(index) for index, choice in sorted(self._choices.items())
            ],
            "object": "chat.completion",
        }
        if self._usage is not None:
            answer["usage"] = self._usage
        return 200, JSON_TYPE, dump(answer)

    def _event(self, event: bytes) -> None:
        data: list[bytes] = []
        error: list[bytes] = []
        for line in event.split(b"\n"):
            line = line.rstrip(b"\r")
            if line.startswith(b"data:"):
                data.append(line[5:].removeprefix(b" "))
            elif line.startswith(b"error:"):
                error.append(line[6:].removeprefix(b" "))
        if error:
            self._fail(b"\n".join(error))
        if data:
            self._data(b"\n".join(data))

    def _fail(self, text: bytes) -> None:
        try:
            self._error = json.loads(text)
        except ValueError:
            self._error = {"message": text.decode("utf-8", errors="replace")}

    def _data(self, data: bytes) -> None:
        if data.strip() == b"[DONE]":
            return
        try:
            event = json.loads(data)
        except ValueError:
            return
        if not isinstance(event, dict):
            return
        choices = event.get("choices")
        if "choices" not in event and isinstance(event.get("error"), dict):
            # an error event with no choices alongside it ends the assembly here
            self._error = event["error"]
            return
        for key, value in event.items():
            if key not in _ASSEMBLED:
                self._last[key] = value
        if isinstance(event.get("usage"), dict):
            self._usage = event["usage"]
        if isinstance(choices, list):
            for choice in choices:
                self._choice(choice)

    def _choice(self, given: Any) -> None:
        if not isinstance(given, dict):
            return
        index = given.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            return
        choice = self._choices.setdefault(index, _Choice())
        finish = given.get("finish_reason")
        if isinstance(finish, str):
            choice.finish_reason = finish
        delta = given.get("delta")
        if isinstance(delta, dict):
            choice.text += self._text(delta.get("content"))
            choice.reasoning += self._text(delta.get("reasoning_content"))
            calls = delta.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    self._tool_call(choice, call)
        logprobs = given.get("logprobs")
        if isinstance(logprobs, dict) and isinstance(logprobs.get("content"), list):
            self.size += len(dump(logprobs["content"]))
            choice.logprobs.extend(logprobs["content"])

    def _tool_call(self, choice: _Choice, given: Any) -> None:
        if not isinstance(given, dict):
            return
        index = given.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            return
        call = choice.tool_calls.setdefault(index, _ToolCall())
        call.id += self._text(given.get("id"))
        function = given.get("function")
        if isinstance(function, dict):
            call.name += self._text(function.get("name"))
            call.arguments += self._text(function.get("arguments"))

    def _text(self, value: Any) -> str:
        """The fragment as text, empty when it is not a string, its UTF-8 length
        added to `size`."""
        if not isinstance(value, str):
            return ""
        self.size += len(value.encode("utf-8", errors="replace"))
        return value
