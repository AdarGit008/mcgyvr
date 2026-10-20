"""Dispatch one generation request at one endpoint, and read the answer back.

A runner speaks one protocol path (today the OpenAI-compatible
`/v1/chat/completions`) on the endpoint a rung or role names. `dispatch` and
`dispatch_role` pick the runner and, when a `Capacity` is given, hold the unit's
slot for the whole request. `Runner.generate` builds the body, posts it, parses
the reply, and refuses an answer that is not the one asked for: other weights,
another host's model, or a shape the protocol does not allow. Every failure
becomes a named subclass of `RunnerError`, so a caller can tell a rung that is
full from one that is misconfigured from one that is unreachable.

Around each request the endpoint's status page is polled (`/metrics` for vLLM,
`/slots` otherwise), which is where the derived throughput and in-flight figures
on a `Completion` come from. `Hangup` is how a caller abandons a request it no
longer wants: it shuts down the sockets of every dispatch made under it.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

from mcgyvr import whole
from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.fleet.harness import (
    VLLM_RUNNING,
    VLLM_WAITING,
    in_flight,
    prometheus_totals,
    slots_in_flight,
)
from mcgyvr.local_pool import Endpoint, Protocol, SourceMap, UnknownRungError
from mcgyvr.redact import safe_url
from mcgyvr.weights import is_model

# The request timeout a dispatch is given when nothing more specific is stated:
# what a unit that sends no credential is bound by. A credentialed (hosted) unit
# is not bound by this but by the timeout its endpoint states, which may be
# `None` — a hosted reply is then waited for however long it takes.
GENERATE_TIMEOUT_S = DEFAULT_REQUEST_TIMEOUT_S

#: Seconds allowed to reach an address when the dispatch states no overall
#: timeout: it bounds the connect and the writing of the request, and nothing
#: after that. With no overall timeout there is no read deadline either, so a
#: reply that is slow to start is waited for rather than failed.
HOSTED_CONNECT_TIMEOUT_S = 30.0

# How much of a backend's error body is quoted in a raised message. An error
# can be answered with a whole page; its opening names the problem, and the rest
# would only make the message longer.
_ERROR_BODY_CHARS = 400

# The name a pinned response schema is sent under. The chat completions schema
# form asks for one, and nothing reads it back: the schema beside it is what the
# backend holds the reply to.
_RESPONSE_SCHEMA_NAME = "reply"

#: The sentence carried by a reply from a path that cannot back a quality
#: measurement. It is put in a `Completion`'s notes, and is quoted when a
#: quality-sensitive request is refused on such a path rather than answered.
CAVEAT_NOTE = (
    "Served by a path this build marks as unable to carry a quality "
    "measurement. Usable for work, not for measuring a model."
)


class RunnerError(Exception):
    """Base of every error one dispatch at one endpoint can raise."""


class TransportError(RunnerError):
    """The address was not reached, or the connection broke or could not be read
    before a whole reply arrived."""


class RefusedConnectionError(TransportError):
    """The connection was refused outright, which usually means nothing is
    listening on that address."""


class HungUpError(TransportError):
    """The asker hung up — on this thread or process-wide — before the request
    was sent, or while its reply was still arriving."""


class Hangup:
    """A handle a caller trips to abandon the dispatches made under it.

    Entered as a context manager it pushes itself onto the current thread's
    stack, so every request made inside the block is recorded under it.
    `hang_up` shuts the sockets of those requests down, which fails their blocked
    reads at once instead of leaving a caller waiting for an answer it no longer
    wants.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open: set[socket.socket] = set()
        self.hung_up = False

    def __enter__(self) -> Hangup:
        _under().append(self)
        return self

    def __exit__(self, *_: object) -> None:
        _under().remove(self)

    def hang_up(self) -> None:
        """Trip this hangup and shut down every socket held under it.

        `hung_up` is set before the sockets are shut, so a request that has not
        opened one yet is refused rather than sent, and one already waiting on a
        read is woken with an error.
        """
        with self._lock:
            self.hung_up = True
            open_now = list(self._open)
        for sock in open_now:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

    def _hold(self, sock: socket.socket) -> bool:
        """Take a socket under this hangup, unless it has been tripped already.

        `True` means this socket is shut down if the hangup trips; `False` means
        it has tripped, and the caller raises `HungUpError` rather than letting
        the request go on.
        """
        with self._lock:
            if self.hung_up:
                return False
            self._open.add(sock)
            return True

    def _drop(self, sock: socket.socket) -> None:
        with self._lock:
            self._open.discard(sock)


#: The dispatches in force on this thread: a hangup entered as a context manager
#: is on this stack, and any request made while it is there is recorded under it.
_dispatching = threading.local()

#: The hangup every dispatch is under, on every thread, so `hang_up_all` reaches
#: requests no per-thread hangup would.
_every = Hangup()


def _under() -> list[Hangup]:
    stack: list[Hangup] | None = getattr(_dispatching, "stack", None)
    if stack is None:
        stack = _dispatching.stack = []
    return stack


def hang_up_all() -> None:
    """Hang up every dispatch in flight, whichever thread made it."""
    _every.hang_up()


class BackendError(RunnerError):
    """A backend answered with an error status rather than a reply.

    `status` is the HTTP status it answered with, and `code` the error code its
    body named, where it named one.
    """

    def __init__(
        self, message: str, *, status: int | None = None, code: str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class ReliefUnavailableError(SlotUnavailableError):
    """A lent rung cannot take the request now, so it is passed over as full: it
    answered busy, or from another model than the one it was matched to."""


class ModelUnplacedError(SlotUnavailableError):
    """The rung asks for a model its hub cannot place at the moment, which makes
    the rung unavailable for now rather than misconfigured."""


#: The answer that says the hub behind a rung cannot place the rung's model right
#: now. It is read as width being unavailable, not as a broken rung.
MODEL_UNPLACED: tuple[int, str] = (503, "model_unplaced")


class UnknownModelError(SlotUnavailableError):
    """The rung's address does not know the model the rung asks for: the rung's
    `model` is wrong, and the rung is passed over with a note saying so."""


#: The answer that says the address was asked for a model it does not know. It is
#: a mistake in the rung's `model`, so the rung is passed over and a note is
#: printed; asking again would put the same unknown name to the same address.
UNKNOWN_MODEL: tuple[int, str] = (404, "model_not_found")


class ProtocolError(RunnerError):
    """The answer is not the shape the protocol promises: no choices, content that
    is not a string, malformed tool calls, or a body that is not JSON."""


class QualityCaveatError(RunnerError):
    """A quality-sensitive request was refused because the path it would run on
    cannot carry a quality measurement."""


class WrongWeightsError(RunnerError):
    """The endpoint answered from weights other than the model it was asked for,
    so the reply is not a completion for that model and must not be recorded as
    one."""


class StopReason(StrEnum):
    """Why generation stopped, in this build's own words.

    Each backend names it differently; `_STOP_REASONS` maps the words this build
    knows onto these members, and a word it does not know lands on `UNKNOWN`
    rather than being read as a finished answer.
    """

    COMPLETE = "complete"
    TRUNCATED = "truncated"
    FILTERED = "filtered"
    #: The model stopped to ask for tool calls rather than to finish. It is a stop
    #: reason of its own, so such a reply is not read as done.
    TOOL_CALLS = "tool_calls"
    UNKNOWN = "unknown"


#: The `sampling` value a unit states when the server behind it fixes the
#: sampling parameters itself and refuses the ones a request names. A request to
#: such a unit carries no `temperature` at all, because sending one is answered
#: with an error. Any other value (the default is `request`) means the endpoint
#: takes the temperature the request states, which is what a deterministic first
#: draw needs of a local unit.
SERVER_SAMPLED = "server"

_STOP_REASONS: dict[str, StopReason] = {
    "stop": StopReason.COMPLETE,
    "eos_token": StopReason.COMPLETE,
    "length": StopReason.TRUNCATED,
    "max_tokens": StopReason.TRUNCATED,
    "content_filter": StopReason.FILTERED,
    "tool_calls": StopReason.TOOL_CALLS,
}


@dataclass(frozen=True)
class ToolCall:
    """One tool call a model asked for: the id a caller answers with, the
    function's name, and the arguments as the JSON text the backend sent.

    `arguments` is left as text: it is the backend's encoding of the call, and
    parsing it is the caller's business.
    """

    id: str
    name: str
    arguments: str


# The roles a turn may carry. `system` is left out on purpose: the system prompt
# is `Request.system`, and a system turn among the turns would be a second one,
# which different servers would read differently.
_TURN_ROLES = frozenset({"user", "assistant", "tool"})


@dataclass(frozen=True)
class Request:
    """One generation request, as a runner is handed it.

    `prompt` is the user text of a single-shot ask; `turns` carries a
    conversation instead, and `prompt` is then sent only if it is non-empty or
    there are no turns at all. `__post_init__` refuses a cap below 1, a
    non-positive timeout, and a turn that is not a chat message, so a request
    that cannot be sent as stated never reaches an endpoint.
    """

    prompt: str
    max_output_tokens: int | None
    system: str = ""
    temperature: float = 0.0
    timeout_s: float | None = None
    quality_sensitive: bool = False
    response_schema: dict[str, Any] | None = None
    turns: tuple[Mapping[str, Any], ...] = ()
    tools: tuple[Mapping[str, Any], ...] = ()
    cap_basis: str = ""

    def __post_init__(self) -> None:
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise ValueError(
                f"max_output_tokens must be at least 1, got "
                f"{self.max_output_tokens}. A cap below 1 is not a ceiling; "
                f"use None for an uncapped raw-text dispatch."
            )
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ValueError(f"timeout_s must be positive, got {self.timeout_s}")
        for index, turn in enumerate(self.turns):
            role = turn.get("role") if isinstance(turn, Mapping) else None
            if role == "system":
                raise ValueError(
                    f"turn {index} is a system turn; the system prompt is "
                    f"Request.system, and a second one among the turns would "
                    f"be a different request depending on which a server reads."
                )
            if role not in _TURN_ROLES:
                raise ValueError(
                    f"turn {index} is not a chat message with a role in "
                    f"{sorted(_TURN_ROLES)}: {type(turn).__name__} with role "
                    f"{role!r}"
                )


@dataclass(frozen=True)
class Completion:
    """One dispatch's answer: the text, why it stopped, what the backend said
    about tokens, and the rates measured around the request.

    `notes` carries the caveats that have to travel with it, and `quality_safe`
    says whether it may be used as a quality measurement at all.
    """

    text: str
    stop_reason: StopReason
    raw_stop_reason: str
    model: str
    source: str
    protocol: Protocol
    max_output_tokens: int | None
    latency_s: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    served_model: str | None = None
    quality_safe: bool = True
    notes: tuple[str, ...] = ()
    decode_tok_s: float | None = None
    decode_source: str | None = None
    prefill_tok_s: float | None = None
    prefill_source: str | None = None
    in_flight: int | None = None
    in_flight_source: str | None = None
    #: Measured rates, each with a label saying where the number came from,
    #: because a backend's own timing and a figure derived from wall-clock latency
    #: are not the same fact: `decode_tok_s` is output tokens per second,
    #: `prefill_tok_s` input tokens per second of prefill, and `in_flight` how many
    #: requests the unit carried, this one included.
    draft_n: int | None = None
    draft_n_accepted: int | None = None
    #: The tool calls the model asked for, in the order it asked for them, each
    #: naming a function and carrying its arguments as unparsed JSON text.
    tool_calls: tuple[ToolCall, ...] = ()
    #: Hidden reasoning tokens the backend reported, where it reports them: they
    #: count towards `output_tokens`, so a cap can be spent entirely on them and
    #: leave no visible text.
    reasoning_tokens: int | None = None
    #: What the cap was derived from, as the caller stated it, so a record can say
    #: why the reply had the room it had.
    cap_basis: str = ""

    @property
    def complete(self) -> bool:
        """Whether the model finished on its own, with nothing cut off."""
        return self.stop_reason is StopReason.COMPLETE

    @property
    def wants_tools(self) -> bool:
        """Whether the reply asks for tool calls, by its stop reason or by naming
        calls."""
        return self.stop_reason is StopReason.TOOL_CALLS or bool(self.tool_calls)

    @property
    def truncated(self) -> bool:
        """Whether the reply was cut off at a length limit."""
        return self.stop_reason is StopReason.TRUNCATED

    @property
    def overran_cap(self) -> bool | None:
        """Whether the reported output tokens exceeded the cap that was sent.

        `None` where either count is unknown, which is not the same answer as
        `False`.
        """
        if self.output_tokens is None or self.max_output_tokens is None:
            return None
        return self.output_tokens > self.max_output_tokens


@dataclass(frozen=True)
class _Parsed:
    """What one backend reply yielded, before it is dressed as a `Completion`.

    Nothing here has been checked against the request yet: the runner does that
    once it has this, and raises rather than returning a reply that is not the
    one that was asked for.
    """

    text: str
    raw_stop_reason: str
    input_tokens: int | None
    output_tokens: int | None
    #: The model the backend said it answered with, as it named itself, and `None`
    #: where it named none. It is what the runner checks against the model it asked
    #: for, so a rung pointed at other weights is caught before the reply is used.
    served_model: str | None
    #: The backend's own timing figures, where it reports them (llama.cpp's
    #: `timings` block does); a backend without them leaves these unknown.
    decode_tok_s: float | None = None
    prefill_tok_s: float | None = None
    #: Speculative-decoding counters from the same block: drafts made, and drafts
    #: accepted.
    draft_n: int | None = None
    draft_n_accepted: int | None = None
    #: Tool calls the model asked for, already checked into `ToolCall`s.
    tool_calls: tuple[ToolCall, ...] = ()
    #: Hidden reasoning tokens, where the usage block reports them.
    reasoning_tokens: int | None = None


class Runner(ABC):
    """One protocol path on one endpoint.

    A subclass states which path it speaks (`protocol`, `path`), whether a reply
    on it can back a quality measurement (`quality_safe`), and whether it can be
    sent a pinned schema (`honours_response_schema`), and it builds and reads its
    own payload. This class does the dispatch: it refuses a request the path
    cannot carry, posts the body, and maps every answer that is not the one asked
    for onto a `RunnerError`.
    """

    protocol: ClassVar[Protocol]
    path: ClassVar[str]
    # Whether a reply on this path may be recorded as a quality measurement. It is
    # `True` where the path carries the model's own sampling and its token counts;
    # a path that drops either cannot back a measurement.
    quality_safe: ClassVar[bool] = True
    # Whether this path has a parameter to send a pinned response schema. Where
    # there is none, the schema is not sent, the reply is prose the parser falls
    # back to reading, and `_notes` says so on the reply rather than letting it
    # pass as schema-checked.
    honours_response_schema: ClassVar[bool] = False

    def __init__(self, endpoint: Endpoint) -> None:
        self.endpoint = endpoint

    def generate(self, model: str, request: Request) -> Completion:
        """Dispatch the request at this endpoint and read the answer back.

        The status page is polled before and after the request, so the derived
        throughput and in-flight figures cover the window the reply came from.
        Raises `QualityCaveatError` before anything is sent when the path cannot
        carry a quality-sensitive request, and otherwise one of the `RunnerError`
        subclasses for every answer that is not the one asked for.
        """
        if request.quality_sensitive and not self.quality_safe:
            raise QualityCaveatError(
                f"refusing a quality-sensitive request on the "
                f"{self.protocol} path of source {self.endpoint.source!r}. "
                f"{CAVEAT_NOTE}"
            )

        url = _url_for(self.endpoint.base_url, self.path)
        before = _status(self.endpoint)
        started = time.monotonic()
        try:
            document = _post_json(
                url,
                self._payload(model, request),
                self._headers(),
                request_timeout(self.endpoint, request.timeout_s),
            )
        except BackendError as exc:
            busy = self.endpoint.busy_answers
            if (
                self.endpoint.relief
                and busy is not None
                and (exc.status, exc.code) in busy
            ):
                raise ReliefUnavailableError(
                    f"relief rung {self.endpoint.source!r} cannot take the "
                    f"request now: {exc}"
                ) from exc
            if (exc.status, exc.code) == MODEL_UNPLACED:
                raise ModelUnplacedError(
                    f"rung {self.endpoint.source!r} names a model its hub "
                    f"cannot place now: {exc}"
                ) from exc
            if (exc.status, exc.code) == UNKNOWN_MODEL:
                said = (
                    f"rung {self.endpoint.source!r} asked for model {model!r}, "
                    f"which its address does not know (HTTP 404 "
                    f"model_not_found); the rung is passed over. Check the "
                    f"rung's `model`"
                )
                print(f"note: {said}", file=sys.stderr)
                raise UnknownModelError(said) from exc
            raise
        latency_s = time.monotonic() - started
        after = _status(self.endpoint)

        parsed = self._parse(document)
        if self.endpoint.relief:
            self._refuse_another_host_model(parsed.served_model)
        else:
            self._refuse_other_weights(model, parsed.served_model)
        stop_reason = _STOP_REASONS.get(parsed.raw_stop_reason, StopReason.UNKNOWN)
        decode_tok_s, decode_source = _decode(parsed, latency_s)
        in_flight, in_flight_source = _in_flight(before, after)
        prefill_tok_s, prefill_source = _prefill(parsed, before, after)
        return Completion(
            text=parsed.text,
            stop_reason=stop_reason,
            raw_stop_reason=parsed.raw_stop_reason,
            model=model,
            source=self.endpoint.source,
            protocol=self.protocol,
            max_output_tokens=request.max_output_tokens,
            latency_s=latency_s,
            input_tokens=parsed.input_tokens,
            output_tokens=parsed.output_tokens,
            served_model=parsed.served_model,
            quality_safe=self.quality_safe,
            notes=self._notes(parsed, stop_reason, request),
            decode_tok_s=decode_tok_s,
            decode_source=decode_source,
            prefill_tok_s=prefill_tok_s,
            prefill_source=prefill_source,
            in_flight=in_flight,
            in_flight_source=in_flight_source,
            draft_n=parsed.draft_n,
            draft_n_accepted=parsed.draft_n_accepted,
            tool_calls=parsed.tool_calls,
            reasoning_tokens=parsed.reasoning_tokens,
            cap_basis=request.cap_basis,
        )

    def _refuse_other_weights(self, asked: str, served: str | None) -> None:
        """Refuse a reply that came from weights other than the model asked for.

        A backend that names no model in its answer cannot be caught this way and
        passes: there is nothing to compare.
        """
        if served is None or is_model(served, asked):
            return
        raise WrongWeightsError(
            f"{self.endpoint.source!r} was asked for {asked!r} and answered "
            f"with {served!r}. Those are different weights, so this is not a "
            f"completion for {asked!r} and must not be recorded as one — the "
            f"rung is pointed at a model that is not the one resident."
        )

    def _refuse_another_host_model(self, served: str | None) -> None:
        """Pass a relief rung over as full when it answered from another model.

        The reply is kept only if both the model the rung was matched to and the
        model it answered from are known and name the same weights; otherwise a
        note is printed and `ReliefUnavailableError` is raised, which is what
        makes passing the rung over cost nothing.
        """
        expected = self.endpoint.served_model
        if expected is not None and served is not None and is_model(served, expected):
            return
        said = (
            f"relief rung {self.endpoint.source!r} answered from "
            f"{served or 'no named model'!r}, not the {expected or 'unstated'!r} it "
            f"was matched to; it is passed over as full"
        )
        print(f"note: {said}", file=sys.stderr)
        raise ReliefUnavailableError(said)

    def _notes(
        self, parsed: _Parsed, stop_reason: StopReason, request: Request
    ) -> tuple[str, ...]:
        """The caveats that have to travel with this reply, in the order listed.

        The quality caveat, a schema the path could not send, the three ways a
        length stop is read, an unrecognised stop reason, and a backend that went
        over the cap it was sent.
        """
        notes: list[str] = []
        if not self.quality_safe:
            notes.append(CAVEAT_NOTE)
        if request.response_schema is not None and not self.honours_response_schema:
            notes.append(
                f"a response schema was pinned and the {self.protocol} path has "
                f"no parameter to send it, so this reply is prose rather than "
                f"the pinned object. It is still readable — the parser falls "
                f"back to the fenced shape — but it was not schema-checked by "
                f"the backend."
            )
        if stop_reason is StopReason.TRUNCATED:
            if request.max_output_tokens is None:
                notes.append(
                    "the backend reported it stopped at its own length limit "
                    "(the request was uncapped)."
                )
            elif not parsed.text.strip():
                notes.append(
                    f"the reply hit the {request.max_output_tokens}-token cap "
                    f"with no visible text: the cap went to hidden reasoning."
                )
            else:
                notes.append(
                    f"the reply hit the {request.max_output_tokens}-token cap and "
                    f"is incomplete. That is a named failure, not a short "
                    f"answer: it must not be applied to a file."
                )
        if stop_reason is StopReason.UNKNOWN:
            reported = parsed.raw_stop_reason or "nothing"
            notes.append(
                f"{self.endpoint.source!r} reported {reported} as the reason "
                f"generation stopped, which is not a word this runner knows. "
                f"The answer is not being read as complete."
            )
        if (
            request.max_output_tokens is not None
            and parsed.output_tokens is not None
            and parsed.output_tokens > request.max_output_tokens
        ):
            notes.append(
                f"the backend returned {parsed.output_tokens} output tokens "
                f"against a cap of {request.max_output_tokens}; it did not "
                f"honour the ceiling it was sent."
            )
        return tuple(notes)

    def _headers(self) -> dict[str, str]:
        """The headers to send: JSON, plus a bearer token when the endpoint's
        credential resolves to a key. An endpoint naming no credential env sends
        none."""
        headers = {"Content-Type": "application/json"}
        key = self.endpoint.credential()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    @abstractmethod
    def _payload(self, model: str, request: Request) -> dict[str, Any]:
        """Build the request body for one dispatch at this endpoint."""

    @abstractmethod
    def _parse(self, document: dict[str, Any]) -> _Parsed:
        """Read the reply document back into `_Parsed`.

        Raises `ProtocolError` where it is not this protocol's shape, rather than
        filling in what a missing field would have said.
        """


class OpenAIRunner(Runner):
    """The OpenAI-compatible chat completions path every backend behind a unit
    serves.

    Every request is sent as a stream and the reply is assembled locally, so a
    backend that streams and one that answers in a single body are read the same
    way, and usage is always reported.
    """

    protocol: ClassVar[Protocol] = Protocol.OPENAI
    path: ClassVar[str] = "/v1/chat/completions"
    honours_response_schema: ClassVar[bool] = True

    def _payload(self, model: str, request: Request) -> dict[str, Any]:
        messages: list[Mapping[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.turns)
        if request.prompt or not request.turns:
            messages.append({"role": "user", "content": request.prompt})
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if self.endpoint.sampling != SERVER_SAMPLED:
            # A unit whose server fixes its own sampling refuses the parameters a
            # request names, so none is sent: the field is left out rather than
            # given a value the backend would reject.
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            # The cap is sent as `max_tokens`, the chat completions ceiling on the
            # reply. An uncapped request sends nothing and leaves the backend's own
            # length limit to stop it.
            payload["max_tokens"] = request.max_output_tokens
        if request.response_schema is not None:
            # A pinned schema goes as a strict `json_schema` response format, which
            # is the only way this path can ask for more than prose.
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": _RESPONSE_SCHEMA_NAME,
                    # Strict asks the backend to hold the reply to the schema rather
                    # than merely suggest it, which is what makes sending the schema
                    # worth anything.
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        if request.tools:
            # Tool definitions are forwarded as given, and the model is left to
            # decide whether to call one.
            payload["tools"] = list(request.tools)
            payload["tool_choice"] = "auto"
        # The payload is turned into a streamed ask, with usage included in the
        # stream, so one read path serves every backend behind a unit.
        return whole.asking(payload)

    def _parse(self, document: dict[str, Any]) -> _Parsed:
        choices = document.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProtocolError(
                f"{self.endpoint.source!r} answered chat completions with no "
                f"choices. Keys present: "
                f"{', '.join(sorted(document)) or '(none)'}"
            )
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        tool_calls = self._tool_calls(
            message.get("tool_calls") if isinstance(message, dict) else None
        )
        # A message that only asks for tool calls carries null content, which
        # reads as empty text on a reply that does have calls.
        if content is None and tool_calls:
            content = ""
        if not isinstance(content, str):
            raise ProtocolError(
                f"{self.endpoint.source!r} answered chat completions without "
                f"string content at choices[0].message.content"
            )
        usage = document.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        raw_stop = first.get("finish_reason") if isinstance(first, dict) else None
        served = document.get("model")
        # llama.cpp reports its own `timings` block; a backend without one leaves
        # the rates to be measured from wall-clock latency.
        timings = document.get("timings")
        if not isinstance(timings, dict):
            timings = {}
        return _Parsed(
            text=content,
            raw_stop_reason=_as_str(raw_stop),
            input_tokens=_as_int(usage.get("prompt_tokens")),
            output_tokens=_as_int(usage.get("completion_tokens")),
            served_model=served if isinstance(served, str) and served else None,
            decode_tok_s=_as_rate(timings.get("predicted_per_second")),
            prefill_tok_s=_as_rate(timings.get("prompt_per_second")),
            # Speculative-decoding counters, for the backends that report them;
            # anything else leaves both unknown.
            draft_n=_as_int(timings.get("draft_n")),
            draft_n_accepted=_as_int(timings.get("draft_n_accepted")),
            tool_calls=tool_calls,
            reasoning_tokens=_reasoning_tokens(usage),
        )

    def _tool_calls(self, entries: object) -> tuple[ToolCall, ...]:
        """Read `choices[0].message.tool_calls` into `ToolCall`s.

        `None` means the message asked for no calls. Anything malformed raises
        `ProtocolError` naming the position it was found at, since a call that
        cannot be read whole must not be half-answered.
        """
        if entries is None:
            return ()
        where = f"{self.endpoint.source!r} answered chat completions with"
        if not isinstance(entries, list):
            raise ProtocolError(
                f"{where} choices[0].message.tool_calls that is not a list "
                f"({type(entries).__name__})"
            )
        calls: list[ToolCall] = []
        for index, entry in enumerate(entries):
            at = f"choices[0].message.tool_calls[{index}]"
            if not isinstance(entry, dict):
                raise ProtocolError(f"{where} {at} that is not an object")
            call_id = entry.get("id")
            if not isinstance(call_id, str):
                raise ProtocolError(f"{where} {at} without a string id")
            function = entry.get("function")
            if not isinstance(function, dict):
                raise ProtocolError(f"{where} {at} without a function object")
            name = function.get("name")
            if not isinstance(name, str):
                raise ProtocolError(f"{where} {at} without a string function.name")
            arguments = function.get("arguments", "")
            if not isinstance(arguments, str):
                raise ProtocolError(
                    f"{where} {at} whose function.arguments is not a string"
                )
            calls.append(ToolCall(id=call_id, name=name, arguments=arguments))
        return tuple(calls)


_RUNNERS: dict[Protocol, type[Runner]] = {
    Protocol.OPENAI: OpenAIRunner,
}


def runner_for(endpoint: Endpoint) -> Runner:
    """The runner that speaks this endpoint's protocol, built on that endpoint."""
    return _RUNNERS[endpoint.protocol](endpoint)


def request_timeout(endpoint: Endpoint, stated: float | None) -> float | None:
    """The timeout to give one dispatch.

    The request's own when it states one; else the endpoint's stated
    `request_timeout_s` where the unit sends a credential, which may be `None` and
    then waits for the reply however long it takes; else `GENERATE_TIMEOUT_S`,
    which is what a unit that sends no credential is bound by whatever timeout its
    endpoint states.
    """
    if stated is not None:
        return stated
    if endpoint.requires_credential:
        return endpoint.request_timeout_s
    return GENERATE_TIMEOUT_S


def dispatch(
    source_map: SourceMap,
    rung: str,
    request: Request,
    *,
    capacity: Capacity | None = None,
) -> Completion:
    """Dispatch a request at a rung by name.

    Binds the rung's endpoint, reads the model the rung asks for, and generates
    one reply. With a `capacity` the unit's slot is held for the whole dispatch, so
    the width the rung declares is respected; without one the request is sent
    unclaimed.
    """
    endpoint = source_map.bind(rung)
    step = source_map.get(rung)
    if step is None:  # bound, but no rung of this name carries a model to ask for
        raise UnknownRungError(f"no rung named {rung!r}")
    if capacity is None:
        return runner_for(endpoint).generate(step.model, request)
    # Holding the unit's slot for the whole dispatch is what makes the width it
    # declares mean anything: the claim is taken before the request is sent and
    # released when the reply is in, or when the dispatch raises. `rung` names the
    # rung being dispatched, so the claim is made against the width reserved for
    # that rung where one was, rather than the whole unit's.
    with capacity.hold(endpoint, rung=rung):
        return runner_for(endpoint).generate(step.model, request)


def dispatch_role(
    source_map: SourceMap,
    role: str,
    request: Request,
    *,
    capacity: Capacity | None = None,
) -> Completion | None:
    """Dispatch a request at whatever unit a role is bound to.

    `None` when the config binds no role of that name, which is how a caller tells
    "not configured" from "configured and answered". A `capacity` holds the unit's
    slot for the whole dispatch, as `dispatch` does.
    """
    binding = source_map.role(role)
    if binding is None:
        return None
    if capacity is None:
        return runner_for(binding.endpoint).generate(binding.model, request)
    with capacity.hold(binding.endpoint):
        return runner_for(binding.endpoint).generate(binding.model, request)


# Measured figures, and where each one came from.

#: The labels carried beside a measured figure on a `Completion`: the backend's own
#: `timings` block, usage over wall-clock latency, a TTFT counter delta, or the
#: unit's slots page against its Prometheus metrics. Each label says where one
#: number came from, so a figure this build derived is never read as the backend's
#: own.
DECODE_FROM_TIMINGS = "timings"
DECODE_FROM_USAGE_LATENCY = "usage_latency"
PREFILL_FROM_TIMINGS = "timings"
PREFILL_FROM_METRICS_TTFT = "metrics_ttft"
IN_FLIGHT_FROM_SLOTS = "slots"
IN_FLIGHT_FROM_VLLM_METRICS = "vllm_metrics"

#: The status pages a dispatch polls around a request, and the bounds a poll is
#: given. vLLM reports through Prometheus metrics, llama.cpp through its slots
#: page. A poll never fails a dispatch — an unreadable page only leaves the figures
#: unknown — so its timeout and its read size are small and fixed. The TTFT metric
#: is summed and counted across instances, which is what makes a delta between two
#: polls a rate.
SLOTS_PATH = "/slots"
METRICS_PATH = "/metrics"
STATUS_TIMEOUT_S = 10.0
_STATUS_BYTES = 4 * 1024 * 1024
_TTFT = "vllm:time_to_first_token_seconds"
_RUNNING = VLLM_RUNNING
_WAITING = VLLM_WAITING


@dataclass(frozen=True)
class _Status:
    """One status poll's reading: how many requests the endpoint was carrying,
    which page said so, and the TTFT counters where that page reports them."""

    busy: int
    source: str
    #: Cumulative time-to-first-token seconds and the number of requests behind it,
    #: kept as a pair so two polls can be differenced into a prefill rate.
    ttft: tuple[float, int] | None = None


def _reasoning_tokens(usage: Mapping[str, Any]) -> int | None:
    """The hidden reasoning token count in a usage block.

    The nested `completion_tokens_details.reasoning_tokens` is preferred, with a
    top-level `reasoning_tokens` as the fallback; `None` where neither is there.
    """
    details = usage.get("completion_tokens_details")
    if isinstance(details, Mapping):
        nested = _as_int(details.get("reasoning_tokens"))
        if nested is not None:
            return nested
    return _as_int(usage.get("reasoning_tokens"))


def _decode(parsed: _Parsed, latency_s: float) -> tuple[float | None, str | None]:
    """The decode rate for a reply, with the label saying where it came from.

    The backend's own figure when it reported one, else output tokens over the
    request's wall-clock latency. `None` when there is neither, which is not the
    same as a slow reply.
    """
    if parsed.decode_tok_s is not None:
        return parsed.decode_tok_s, DECODE_FROM_TIMINGS
    if parsed.output_tokens and latency_s > 0:
        return parsed.output_tokens / latency_s, DECODE_FROM_USAGE_LATENCY
    return None, None


def _in_flight(
    before: _Status | None, after: _Status | None
) -> tuple[int | None, str | None]:
    """How many requests the unit was carrying during this dispatch.

    The larger of the two polls, plus one for the request that was just made.
    `None` when either poll is missing or the two came from different pages, so a
    count is never made of numbers that do not belong together.
    """
    if before is None or after is None or before.source != after.source:
        return None, None
    return max(before.busy, after.busy) + 1, before.source


def _prefill(
    parsed: _Parsed, before: _Status | None, after: _Status | None
) -> tuple[float | None, str | None]:
    """The prefill rate for a reply, with the label saying where it came from.

    The backend's own figure when it reported one. Otherwise it is derived from
    the TTFT counters either side of the request, and only when both polls found
    the unit idle, exactly one request was served between them, and the elapsed
    time is positive; anything else leaves it unknown.
    """
    if parsed.prefill_tok_s is not None:
        return parsed.prefill_tok_s, PREFILL_FROM_TIMINGS
    if before is None or after is None or not parsed.input_tokens:
        return None, None
    if before.busy or after.busy or before.ttft is None or after.ttft is None:
        return None, None
    seconds = after.ttft[0] - before.ttft[0]
    if after.ttft[1] - before.ttft[1] != 1 or seconds <= 0:
        return None, None
    return parsed.input_tokens / seconds, PREFILL_FROM_METRICS_TTFT


def _status(endpoint: Endpoint) -> _Status | None:
    """Poll this endpoint's status page, or `None` where it cannot be read.

    An endpoint that sends a credential is not polled at all: the status path is
    fetched without a key, and a unit that needs one is not going to answer it.
    """
    if endpoint.credential_env is not None:
        return None
    if endpoint.engine == "vllm":
        page = _get_text(_url_for(endpoint.base_url, METRICS_PATH), STATUS_TIMEOUT_S)
        return _vllm_status(page)
    page = _get_text(_url_for(endpoint.base_url, SLOTS_PATH), STATUS_TIMEOUT_S)
    return _slots_status(page)


def unit_in_flight(
    source: str,
    base_url: str,
    engine: str | None,
    max_parallel: int = 1,
    credential_env: str | None = None,
) -> int | None:
    """How many requests an address is carrying, from what a probe knows about it.

    The endpoint is assembled here so the same poll a dispatch uses can be made
    against a unit that is not being dispatched at, which is what a capacity gauge
    needs. `credential_env` is the unit's own: a unit that needs a key is not
    polled, as `_status` never polls one.
    """
    endpoint = Endpoint(
        source=source,
        base_url=base_url,
        protocol=Protocol.OPENAI,
        max_parallel=max_parallel,
        credential_env=credential_env,
        engine=engine,
    )
    status = _status(endpoint)
    return None if status is None else status.busy


def status_busy(engine: str | None, page: str | None) -> int | None:
    """How many requests a status page reports, read as the engine names it."""
    return in_flight(engine, page)


def _slots_status(page: str | None) -> _Status | None:
    """Read a llama.cpp slots page into a status, or `None` when it cannot be."""
    busy = slots_in_flight(page)
    return None if busy is None else _Status(busy=busy, source=IN_FLIGHT_FROM_SLOTS)


def _vllm_status(page: str | None) -> _Status | None:
    """Read a vLLM metrics page into a status.

    The running and waiting gauges give the count; the TTFT totals are carried
    only when both are present, and a page missing the running or the waiting
    gauge reads as no status at all.
    """
    totals = prometheus_totals(
        page, (_RUNNING, _WAITING, f"{_TTFT}_sum", f"{_TTFT}_count")
    )
    if totals is None or _RUNNING not in totals or _WAITING not in totals:
        return None
    ttft = (
        (totals[f"{_TTFT}_sum"], int(totals[f"{_TTFT}_count"]))
        if f"{_TTFT}_sum" in totals and f"{_TTFT}_count" in totals
        else None
    )
    return _Status(
        busy=int(totals[_RUNNING] + totals[_WAITING]),
        source=IN_FLIGHT_FROM_VLLM_METRICS,
        ttft=ttft,
    )


def _get_text(url: str, timeout: float) -> str | None:
    """Fetch a page as text, or `None` when it cannot be fetched or read.

    Errors are swallowed on purpose: a status poll is a measurement, never a
    reason to fail the dispatch it is measuring.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw: bytes = response.read(_STATUS_BYTES)
    except (OSError, ValueError, http.client.HTTPException):
        return None
    return raw.decode("utf-8", "replace")


# The transport one dispatch is carried over.


#: How many bytes one read of a reply body asks for: an event at a time, so a
#: streamed reply is assembled as it arrives rather than buffered whole.
_READ_BYTES = 64 * 1024


def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float | None,
) -> dict[str, Any]:
    """POST a JSON body and return the document that answered it.

    A request that asked to be streamed is sent an event stream and its reply is
    assembled back into one document, so the caller reads a single answer either
    way. An answer of 300 or above is raised as `BackendError` carrying the status
    and the error code the body named.

    Raises `HungUpError` when a hangup under this dispatch has tripped,
    `TransportError` when the address could not be reached or the reply did not
    arrive whole, and `ProtocolError` when what arrived is not the JSON object a
    reply is supposed to be.
    """
    body = json.dumps(payload).encode("utf-8")
    streamed = payload.get("stream") is True
    sent = {
        **headers,
        "Accept": whole.EVENT_STREAM if streamed else "application/json",
    }
    deadline = None if timeout is None else time.monotonic() + timeout
    connect_s = HOSTED_CONNECT_TIMEOUT_S if timeout is None else timeout
    under = [*_under(), _every]

    def gone() -> bool:
        return any(hangup.hung_up for hangup in under)

    if gone():
        raise HungUpError(f"{safe_url(url)} was not asked: the asker has gone")
    connection, path = _open(url, connect_s)
    sock: socket.socket | None = None
    response: http.client.HTTPResponse | None = None
    # Whether the request has been written to the connection. An OSError raised
    # before that point is a failure to reach the address; after it, the address
    # was reached and something else went wrong — which is what decides both the
    # exception and the message a caller reads.
    reached = False
    try:
        connection.request("POST", path, body=body, headers=sent)
        reached = True
        sock = connection.sock
        if sock is None or not all(hangup._hold(sock) for hangup in under):
            raise HungUpError(f"{safe_url(url)} was hung up on: the asker has gone")
        if timeout is None:
            # No overall timeout means no read deadline either: a hosted reply is
            # waited for however long it takes.
            sock.settimeout(None)
        response = connection.getresponse()
        status = response.status
        media = whole.media(response.getheader("Content-Type", "") or "")
        if status == 200 and streamed and media == whole.EVENT_STREAM:
            answered = _assembled(response, sock, deadline, timeout)
            if answered is None:
                if gone():
                    raise HungUpError(
                        f"{safe_url(url)} was hung up on: the asker has gone"
                    )
                raise TransportError(
                    f"{safe_url(url)} sent a stream that ended before its answer"
                )
            status, _, raw_bytes = answered
            if status != 200:
                text = raw_bytes.decode("utf-8", "replace").strip()
                raise BackendError(
                    f"{safe_url(url)} answered HTTP {status}: "
                    f"{text[:_ERROR_BODY_CHARS] or '(empty body)'}",
                    status=status,
                    code=_error_code(text),
                )
            raw = raw_bytes.decode("utf-8", "replace")
        elif status >= 300:
            # A non-2xx answer is an error, and its body is where the backend says
            # why. The body is read in full — a truncated error is still an error —
            # and the opening of it is quoted in the message, with the status kept
            # and the error code read from the body where it names one. A body that
            # ends early or cannot be read does not turn this into a transport
            # failure: the backend did answer, and its status is the fact worth
            # keeping, so it is raised as a `BackendError` saying what could not be
            # read.
            answered_with = f"{safe_url(url)} answered HTTP {status}"
            try:
                raw_detail = _body(response, sock, deadline, timeout)
            except http.client.IncompleteRead as short:
                kept = short.partial.decode("utf-8", "replace").strip()
                raise BackendError(
                    f"{answered_with}, and its body ended before it was complete "
                    f"(kept: {kept[:_ERROR_BODY_CHARS] or 'nothing readable'})",
                    status=status,
                ) from short
            except (OSError, http.client.HTTPException) as lost:
                raise BackendError(
                    f"{answered_with}, and its body could not be read "
                    f"({type(lost).__name__}: {lost})",
                    status=status,
                ) from lost
            text = raw_detail.decode("utf-8", "replace").strip()
            detail = text[:_ERROR_BODY_CHARS]
            raise BackendError(
                f"{answered_with}: {detail or '(empty body)'}",
                status=status,
                code=_error_code(text),
            )
        else:
            raw = _body(response, sock, deadline, timeout).decode("utf-8", "replace")
    except OSError as exc:
        if gone():
            raise HungUpError(
                f"{safe_url(url)} was hung up on: the asker has gone"
            ) from exc
        if reached and timeout is not None and isinstance(exc, TimeoutError):
            # The connection was made, so this is not a reachability failure: the
            # bound that was given ran out before the reply was whole.
            raise TransportError(
                f"{safe_url(url)} was reached but did not reply within "
                f"{timeout:g}s ({exc}); the bound is the unit's "
                f"`request_timeout_s`: raise it, or unset it on a hosted unit "
                f"to wait for the reply however long it takes"
            ) from exc
        if reached:
            raise TransportError(
                f"{safe_url(url)} was reached, and the connection failed before "
                f"its reply was whole: {exc}"
            ) from exc
        # The request never got a reply because the address was not reached at all,
        # so this is a reachability failure. An outright refusal is called out as
        # such, since it usually means nothing is listening on that address.
        reason = getattr(exc, "reason", exc)
        kind = (
            RefusedConnectionError
            if isinstance(reason, ConnectionRefusedError)
            else TransportError
        )
        raise kind(
            f"could not reach {safe_url(url)} within {connect_s:g}s: {exc}"
        ) from exc
    except http.client.HTTPException as exc:
        if gone():
            raise HungUpError(
                f"{safe_url(url)} was hung up on: the asker has gone"
            ) from exc
        # The reply broke the HTTP protocol while it was being read, which is a
        # transport failure rather than a shape this build can complain about.
        raise TransportError(
            f"{safe_url(url)} sent a reply that could not be read: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    except ValueError as exc:
        # `whole.Whole.feed` raises `ValueError` for a stream that is not a chat
        # completion's, so the answer is the wrong shape rather than unreadable.
        raise ProtocolError(
            f"{safe_url(url)} answered with something that is not a chat "
            f"completion's stream: {exc}"
        ) from exc
    finally:
        if sock is not None:
            for hangup in under:
                hangup._drop(sock)
        if response is not None:
            response.close()
        connection.close()

    try:
        document = json.loads(raw)
    except ValueError as exc:
        raise ProtocolError(
            f"{safe_url(url)} answered with something that is not JSON: "
            f"{raw.strip()[:_ERROR_BODY_CHARS] or '(empty body)'}"
        ) from exc
    if not isinstance(document, dict):
        raise ProtocolError(
            f"{safe_url(url)} answered with JSON {type(document).__name__}"
        )
    return document


def _open(url: str, timeout: float) -> tuple[http.client.HTTPConnection, str]:
    """Turn a URL into a connection and the path to ask for on it.

    TLS is chosen by the scheme and a missing port is the scheme's default, so an
    address written without one is still reachable.
    """
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        raise TransportError(f"{safe_url(url)} is not an http(s) address")
    tls = scheme == "https"
    port = parts.port or (443 if tls else 80)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    if tls:
        return http.client.HTTPSConnection(parts.hostname, port, timeout=timeout), path
    return http.client.HTTPConnection(parts.hostname, port, timeout=timeout), path


def _reads(
    response: http.client.HTTPResponse,
    sock: socket.socket,
    deadline: float | None,
    timeout: float | None,
) -> Iterator[bytes]:
    """Yield a reply body as it arrives, in reads of `_READ_BYTES`.

    With an overall deadline the socket timeout is set to whatever is left of it
    before each read, so the deadline holds across the whole body rather than per
    read, and passing it raises `TimeoutError`.
    """
    while not response.isclosed():
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"no whole answer within {timeout:g}s")
            sock.settimeout(left)
        chunk = response.read1(_READ_BYTES)
        if not chunk:
            return
        yield chunk


def _body(
    response: http.client.HTTPResponse,
    sock: socket.socket,
    deadline: float | None,
    timeout: float | None,
) -> bytes:
    """Read a whole reply body, raising `IncompleteRead` if it ends early.

    The bytes read so far are carried on the exception, so a caller reporting an
    error can still quote the part that arrived.
    """
    kept = bytearray()
    try:
        for chunk in _reads(response, sock, deadline, timeout):
            kept += chunk
    except http.client.IncompleteRead as short:
        raise http.client.IncompleteRead(bytes(kept) + short.partial) from short
    if response.length:  # the headers stated a length the body did not reach
        raise http.client.IncompleteRead(bytes(kept), response.length)
    return bytes(kept)


def _assembled(
    response: http.client.HTTPResponse,
    sock: socket.socket,
    deadline: float | None,
    timeout: float | None,
) -> tuple[int, str, bytes] | None:
    """Assemble a streamed reply into the one document it stands for.

    `None` when the stream ended before that document was complete, which the
    caller reads as a reply that stopped early. A read that raises `IncompleteRead`
    is not an error here: whatever arrived is assembled and the answer decides.
    """
    assembled = whole.Whole()
    with contextlib.suppress(http.client.IncompleteRead):
        for chunk in _reads(response, sock, deadline, timeout):
            assembled.feed(chunk)
    return assembled.answer()


# Small helpers: reading an error code out of a body, joining a path on a base URL,
# and coercing values out of a JSON document.


def _error_code(body: str) -> str | None:
    """The error code a JSON error body names, or `None` where it names none.

    A body that is not JSON, or an error without a string code, reads as no code
    rather than as a failure: the status is the fact that matters, and the code
    only sharpens it.
    """
    try:
        document = json.loads(body)
    except (ValueError, RecursionError):
        return None
    error = document.get("error") if isinstance(document, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def _url_for(base_url: str, path: str) -> str:
    """Join a path on a base URL, which may or may not already end in `/v1`.

    A base stating `/v1` and a path stating it too would ask for `/v1/v1/...`, so
    the base's copy is dropped rather than sent.
    """
    base = base_url.rstrip("/")
    if path.startswith("/v1/") and base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + path


def _as_str(value: object) -> str:
    """The value when it is a string, else the empty string."""
    return value if isinstance(value, str) else ""


def _as_rate(value: object) -> float | None:
    """A positive number as a float, or `None`.

    Zero, a negative, a bool and a non-number are no figure at all: a rate of zero
    from a backend that did not measure one would read as a measured zero.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def _as_int(value: object) -> int | None:
    """The value when it is an int and not a bool, else `None`: `True` is not a
    token count."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
