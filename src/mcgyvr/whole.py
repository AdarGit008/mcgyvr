"""A chat completion asked of a unit as a stream, and assembled whole.

A model server notices that whoever asked has gone only when it writes to
them, and an answer not streamed is written once, at its end: a slot asked for
one and left mid-answer decodes the rest for nobody. A stream is written a
token at a time, so a hang-up on it stops the slot within a token. So the
product asks every unit for a stream whatever the caller asked (:func:`asking`
on a request's JSON object, :func:`as_stream` on its bytes: ``stream`` and the
counts in the last event, ``stream_options.include_usage``, the rest as it
came) and, where the caller wanted the whole answer, assembles it itself
(:class:`Whole`), as the unit would have written one not streamed.

The shape assembled is the OpenAI chat completion's, as llama.cpp's
``to_json_oaicompat_chat`` writes it and the other compatible engines agree:
each choice's deltas joined into its message (content, reasoning, tool calls
by index, the probabilities of each token), its finish reason, the ``usage``
of the event that carries one, and the ``id``, ``model``, ``created`` and
``system_fingerprint`` as the last event that names them does. What else an
event carries at its top (llama.cpp's ``timings``, say) is no field of the
standard and passes through as the last event that carries it says it, so an
engine's own additions reach the caller as they would have. An error event
(``error:`` as llama.cpp writes it, or a ``data:`` object that is an ``error``
and no completion, as the hosted APIs write one) is the status its code says
and the error as the body, as a request not streamed is answered; a stream
that ends with neither its answer nor an error is the unit's failure, and
:meth:`Whole.answer` says so with ``None``. Hostile input safe: what is no
event, no JSON or not the shape is skipped, and an event longer than any of a
chat completion's (:data:`MAX_EVENT_BYTES`) is a ``ValueError``, since a
server writing one speaks no stream.

The runner uses this for every dispatch (:mod:`mcgyvr.runner`); the rig
agent's relay reuses it for the hub's pool requests and for rides
(:mod:`mcgyvr.rig.relay`), never a copy of its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: The longest one event of a unit's stream may be, in bytes, when the answer
#: is assembled: a token's event is under a kilobyte and the last, with the
#: counts and timings, a few; a stream with a longer one is not a chat
#: completion's.
MAX_EVENT_BYTES = 64 * 1024
#: The type of a whole answer, as llama.cpp writes it.
JSON_TYPE = "application/json; charset=utf-8"
#: The type of a stream.
EVENT_STREAM = "text/event-stream"

#: The top-level fields of a chat completion's event that are assembled, not
#: passed through: the choices build the messages, the object is the whole's
#: own, the usage is the one event's that carries it.
_ASSEMBLED = frozenset({"choices", "object", "usage"})


def media(content_type: str) -> str:
    """The media type of ``content_type``, without its parameters, lowered."""
    return content_type.split(";")[0].strip().lower()


def dump(value: Any) -> bytes:
    """``value`` as llama.cpp writes its JSON: compact, keys in order."""
    try:
        text = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return text.encode()
    except UnicodeEncodeError:  # a lone surrogate from the unit: escaped
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def asking(request: dict[str, Any]) -> dict[str, Any]:
    """``request``, a chat completion's JSON object, asking for a stream and
    for its counts (``stream_options.include_usage``) in the last event; its
    own stream options are kept beside the one set. A new object: the given
    one is not changed."""
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
    """``body``, a chat completion request, asking for a stream and its counts
    (:func:`asking`), the rest as it came; ``None`` when it is no JSON object,
    to go as it came."""
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
    except UnicodeEncodeError:  # a lone surrogate: not a body to rewrite
        return None


@dataclass
class _ToolCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class _Choice:
    """One choice of the answer, as its deltas build it."""

    text: str = ""  # the message's content
    reasoning: str = ""
    tool_calls: dict[int, _ToolCall] = field(default_factory=dict)
    logprobs: list[Any] = field(default_factory=list)
    finish_reason: str | None = None

    def whole(self, index: int) -> dict[str, Any]:
        """The choice as ``to_json_oaicompat_chat`` writes it: the message
        with its reasoning when there is any, its content (``null`` when
        there is none and there are tool calls), its tool calls."""
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
    """A chat completion streamed from a unit, assembled as the unit writes
    one not streamed (the module's docstring says how). Fed the stream's bytes
    as they come (:meth:`feed`); :meth:`answer` is the whole once a finish
    reason or an error has come. ``size`` is how much text the answer holds so
    far, in bytes, for a caller with a bound on it."""

    def __init__(self) -> None:
        self._held = b""  # the start of an event, until its end comes
        self._choices: dict[int, _Choice] = {}
        self._last: dict[str, Any] = {}  # the fields passed through, last wins
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
        """The whole answer: status, type and body; ``None`` while no choice
        has its finish reason and no error came."""
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
            # An error in place of a completion, as the hosted APIs write one.
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
        """``value`` when it is text, counted; else nothing."""
        if not isinstance(value, str):
            return ""
        self.size += len(value.encode("utf-8", errors="replace"))
        return value
