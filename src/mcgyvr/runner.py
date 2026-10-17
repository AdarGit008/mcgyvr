""

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

#
#
#ng
#
#
#
#
#
GENERATE_TIMEOUT_S = DEFAULT_REQUEST_TIMEOUT_S

#he
#he
#
#
HOSTED_CONNECT_TIMEOUT_S = 30.0

#
#
#
_ERROR_BODY_CHARS = 400

#
#
#
#
_RESPONSE_SCHEMA_NAME = "reply"

#
#
# a
#
CAVEAT_NOTE = (
    "Served by a path this build marks as unable to carry a quality "
    "measurement. Usable for work, not for measuring a model."
)


class RunnerError(Exception):
    ""


class TransportError(RunnerError):
    ""


class RefusedConnectionError(TransportError):
    ""


class HungUpError(TransportError):
    ""


class Hangup:
    ""

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
        ""
        with self._lock:
            self.hung_up = True
            open_now = list(self._open)
        for sock in open_now:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

    def _hold(self, sock: socket.socket) -> bool:
        ""
        with self._lock:
            if self.hung_up:
                return False
            self._open.add(sock)
            return True

    def _drop(self, sock: socket.socket) -> None:
        with self._lock:
            self._open.discard(sock)


#
_dispatching = threading.local()

#
#
_every = Hangup()


def _under() -> list[Hangup]:
    stack: list[Hangup] | None = getattr(_dispatching, "stack", None)
    if stack is None:
        stack = _dispatching.stack = []
    return stack


def hang_up_all() -> None:
    ""
    _every.hang_up()


class BackendError(RunnerError):
    ""

    def __init__(
        self, message: str, *, status: int | None = None, code: str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class ReliefUnavailableError(SlotUnavailableError):
    ""


class ModelUnplacedError(SlotUnavailableError):
    ""


#
#
#
MODEL_UNPLACED: tuple[int, str] = (503, "model_unplaced")


class UnknownModelError(SlotUnavailableError):
    ""


#
#
#
UNKNOWN_MODEL: tuple[int, str] = (404, "model_not_found")


class ProtocolError(RunnerError):
    ""


class QualityCaveatError(RunnerError):
    ""


class WrongWeightsError(RunnerError):
    ""


class StopReason(StrEnum):
    ""

    COMPLETE = "complete"
    TRUNCATED = "truncated"
    FILTERED = "filtered"
    #
    #
    TOOL_CALLS = "tool_calls"
    UNKNOWN = "unknown"


#
#
#
#
#
#
#
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
    ""

    id: str
    name: str
    arguments: str


#
#
#
_TURN_ROLES = frozenset({"user", "assistant", "tool"})


@dataclass(frozen=True)
class Request:
    ""

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
    ""

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
    #
    #
    #
    #
    #
    #
    #
    draft_n: int | None = None
    draft_n_accepted: int | None = None
    #
    #
    tool_calls: tuple[ToolCall, ...] = ()
    #
    #
    #
    reasoning_tokens: int | None = None
    #
    cap_basis: str = ""

    @property
    def complete(self) -> bool:
        ""
        return self.stop_reason is StopReason.COMPLETE

    @property
    def wants_tools(self) -> bool:
        ""
        return self.stop_reason is StopReason.TOOL_CALLS or bool(self.tool_calls)

    @property
    def truncated(self) -> bool:
        ""
        return self.stop_reason is StopReason.TRUNCATED

    @property
    def overran_cap(self) -> bool | None:
        ""
        if self.output_tokens is None or self.max_output_tokens is None:
            return None
        return self.output_tokens > self.max_output_tokens


@dataclass(frozen=True)
class _Parsed:
    ""

    text: str
    raw_stop_reason: str
    input_tokens: int | None
    output_tokens: int | None
    #
    #le
    #
    #
    served_model: str | None
    #
    #
    decode_tok_s: float | None = None
    prefill_tok_s: float | None = None
    #
    draft_n: int | None = None
    draft_n_accepted: int | None = None
    #
    tool_calls: tuple[ToolCall, ...] = ()
    #
    reasoning_tokens: int | None = None


class Runner(ABC):
    ""

    protocol: ClassVar[Protocol]
    path: ClassVar[str]
    #
    #
    #
    quality_safe: ClassVar[bool] = True
    #
    #e,
    #ng
    #
    honours_response_schema: ClassVar[bool] = False

    def __init__(self, endpoint: Endpoint) -> None:
        self.endpoint = endpoint

    def generate(self, model: str, request: Request) -> Completion:
        ""
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
        ""
        if served is None or is_model(served, asked):
            return
        raise WrongWeightsError(
            f"{self.endpoint.source!r} was asked for {asked!r} and answered "
            f"with {served!r}. Those are different weights, so this is not a "
            f"completion for {asked!r} and must not be recorded as one — the "
            f"rung is pointed at a model that is not the one resident."
        )

    def _refuse_another_host_model(self, served: str | None) -> None:
        ""
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
        ""
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
        ""
        headers = {"Content-Type": "application/json"}
        key = self.endpoint.credential()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    @abstractmethod
    def _payload(self, model: str, request: Request) -> dict[str, Any]:
        ""

    @abstractmethod
    def _parse(self, document: dict[str, Any]) -> _Parsed:
        ""


class OpenAIRunner(Runner):
    ""

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
            #
            #
            #
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            #
            #
            #
            payload["max_tokens"] = request.max_output_tokens
        if request.response_schema is not None:
            #
            #
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": _RESPONSE_SCHEMA_NAME,
                    #
                    #
                    #
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        if request.tools:
            #
            #
            payload["tools"] = list(request.tools)
            payload["tool_choice"] = "auto"
        #
        #
        #
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
        #
        #
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
        #
        #
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
            #
            #
            draft_n=_as_int(timings.get("draft_n")),
            draft_n_accepted=_as_int(timings.get("draft_n_accepted")),
            tool_calls=tool_calls,
            reasoning_tokens=_reasoning_tokens(usage),
        )

    def _tool_calls(self, entries: object) -> tuple[ToolCall, ...]:
        ""
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
    ""
    return _RUNNERS[endpoint.protocol](endpoint)


def request_timeout(endpoint: Endpoint, stated: float | None) -> float | None:
    ""
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
    ""
    endpoint = source_map.bind(rung)
    step = source_map.get(rung)
    if step is None:  #
        raise UnknownRungError(f"no rung named {rung!r}")
    if capacity is None:
        return runner_for(endpoint).generate(step.model, request)
    #
    #
    #
    #
    with capacity.hold(endpoint, rung=rung):
        return runner_for(endpoint).generate(step.model, request)


def dispatch_role(
    source_map: SourceMap,
    role: str,
    request: Request,
    *,
    capacity: Capacity | None = None,
) -> Completion | None:
    ""
    binding = source_map.role(role)
    if binding is None:
        return None
    if capacity is None:
        return runner_for(binding.endpoint).generate(binding.model, request)
    with capacity.hold(binding.endpoint):
        return runner_for(binding.endpoint).generate(binding.model, request)


#

#
#
#
DECODE_FROM_TIMINGS = "timings"
DECODE_FROM_USAGE_LATENCY = "usage_latency"
PREFILL_FROM_TIMINGS = "timings"
PREFILL_FROM_METRICS_TTFT = "metrics_ttft"
IN_FLIGHT_FROM_SLOTS = "slots"
IN_FLIGHT_FROM_VLLM_METRICS = "vllm_metrics"

#
#
#er
#
#
SLOTS_PATH = "/slots"
METRICS_PATH = "/metrics"
STATUS_TIMEOUT_S = 10.0
_STATUS_BYTES = 4 * 1024 * 1024
_TTFT = "vllm:time_to_first_token_seconds"
_RUNNING = VLLM_RUNNING
_WAITING = VLLM_WAITING


@dataclass(frozen=True)
class _Status:
    ""

    busy: int
    source: str
    #
    ttft: tuple[float, int] | None = None


def _reasoning_tokens(usage: Mapping[str, Any]) -> int | None:
    ""
    details = usage.get("completion_tokens_details")
    if isinstance(details, Mapping):
        nested = _as_int(details.get("reasoning_tokens"))
        if nested is not None:
            return nested
    return _as_int(usage.get("reasoning_tokens"))


def _decode(parsed: _Parsed, latency_s: float) -> tuple[float | None, str | None]:
    ""
    if parsed.decode_tok_s is not None:
        return parsed.decode_tok_s, DECODE_FROM_TIMINGS
    if parsed.output_tokens and latency_s > 0:
        return parsed.output_tokens / latency_s, DECODE_FROM_USAGE_LATENCY
    return None, None


def _in_flight(
    before: _Status | None, after: _Status | None
) -> tuple[int | None, str | None]:
    ""
    if before is None or after is None or before.source != after.source:
        return None, None
    return max(before.busy, after.busy) + 1, before.source


def _prefill(
    parsed: _Parsed, before: _Status | None, after: _Status | None
) -> tuple[float | None, str | None]:
    ""
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
    ""
    if endpoint.credential_env is not None:
        return None
    if endpoint.engine == "vllm":
        page = _get_text(_url_for(endpoint.base_url, METRICS_PATH), STATUS_TIMEOUT_S)
        return _vllm_status(page)
    page = _get_text(_url_for(endpoint.base_url, SLOTS_PATH), STATUS_TIMEOUT_S)
    return _slots_status(page)


def unit_in_flight(
    source: str, base_url: str, engine: str | None, max_parallel: int = 1
) -> int | None:
    ""
    endpoint = Endpoint(
        source=source,
        base_url=base_url,
        protocol=Protocol.OPENAI,
        max_parallel=max_parallel,
        credential_env=None,
        engine=engine,
    )
    status = _status(endpoint)
    return None if status is None else status.busy


def status_busy(engine: str | None, page: str | None) -> int | None:
    ""
    return in_flight(engine, page)


def _slots_status(page: str | None) -> _Status | None:
    ""
    busy = slots_in_flight(page)
    return None if busy is None else _Status(busy=busy, source=IN_FLIGHT_FROM_SLOTS)


def _vllm_status(page: str | None) -> _Status | None:
    ""
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
    ""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw: bytes = response.read(_STATUS_BYTES)
    except (OSError, ValueError, http.client.HTTPException):
        return None
    return raw.decode("utf-8", "replace")


#


#
#
#
_READ_BYTES = 64 * 1024


def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float | None,
) -> dict[str, Any]:
    ""
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
    #
    #
    reached = False
    try:
        connection.request("POST", path, body=body, headers=sent)
        reached = True
        sock = connection.sock
        if sock is None or not all(hangup._hold(sock) for hangup in under):
            raise HungUpError(f"{safe_url(url)} was hung up on: the asker has gone")
        if timeout is None:
            #
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
            #
            #
            #
            #
            #
            #
            #
            #
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
            #
            #
            #
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
        #
        #t to
        #
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
        #
        #
        #
        raise TransportError(
            f"{safe_url(url)} sent a reply that could not be read: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    except ValueError as exc:
        #
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
    ""
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
    ""
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
    ""
    kept = bytearray()
    try:
        for chunk in _reads(response, sock, deadline, timeout):
            kept += chunk
    except http.client.IncompleteRead as short:
        raise http.client.IncompleteRead(bytes(kept) + short.partial) from short
    if response.length:  #
        raise http.client.IncompleteRead(bytes(kept), response.length)
    return bytes(kept)


def _assembled(
    response: http.client.HTTPResponse,
    sock: socket.socket,
    deadline: float | None,
    timeout: float | None,
) -> tuple[int, str, bytes] | None:
    ""
    assembled = whole.Whole()
    with contextlib.suppress(http.client.IncompleteRead):
        for chunk in _reads(response, sock, deadline, timeout):
            assembled.feed(chunk)
    return assembled.answer()


#


def _error_code(body: str) -> str | None:
    ""
    try:
        document = json.loads(body)
    except (ValueError, RecursionError):
        return None
    error = document.get("error") if isinstance(document, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def _url_for(base_url: str, path: str) -> str:
    ""
    base = base_url.rstrip("/")
    if path.startswith("/v1/") and base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + path


def _as_str(value: object) -> str:
    ""
    return value if isinstance(value, str) else ""


def _as_rate(value: object) -> float | None:
    ""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def _as_int(value: object) -> int | None:
    ""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
