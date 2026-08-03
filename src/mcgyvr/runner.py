"""Dispatch — two wire protocols behind one runner interface.

This is the first code *below* the seam :mod:`mcgyvr.pool` draws. A caller above
it holds a :class:`~mcgyvr.pool.Rung` — a name and a model — and cannot say
where work runs. Here a rung has already been resolved to an
:class:`~mcgyvr.pool.Endpoint`, and the only remaining question is which shape
to ask in. There are two, and #21 requires that the choice change nothing a
caller can observe:

* **The same contract executes identically on either protocol.** Both runners
  produce the same :class:`Completion`, assembled in one place from a small
  per-protocol :class:`_Parsed`. A protocol supplies a URL path, a request body
  and how to read an answer; it does not get to decide what a completion *is*.
  The fields that differ between two runs of the same request are the ones that
  name where it ran — ``source``, ``protocol`` — and the measurements.
* **The cap is sent by both, and checked afterwards.** ``max_output_tokens`` is
  required on every :class:`Request` and is translated into each protocol's own
  parameter (``options.num_predict``, ``max_tokens``). Nothing streams, so a
  client cannot cut a response off mid-generation; what it can do is refuse to
  issue an uncapped request and then compare the backend's own reported token
  count against the ceiling it was given. A backend that overran says so
  through :attr:`Completion.overran_cap` rather than passing for a short answer.
* **No stop sequences are sent, by decision.** ADR-0009 settled that v1 bounds a
  reply with the cap and a named truncation and nothing else: a stop sequence is
  consumed by the server and stripped from the answer, so it turns a reply that
  ran long into a *shorter valid-looking file* rather than into an error. Under
  ``whole_file`` — the default reply shape — every member of the inherited set
  cut a conforming Python file before its first definition, and the gate would
  have passed the remains. When a safe set exists it is a function of the
  contract's ``output_schema`` and belongs to #25's parser, "never a constant in
  a runner". So there is no ``stop`` parameter on :class:`Request` to fill in;
  the absence is the decision, and a test holds it.
* **Truncation is read, never inferred.** Ollama's ``done_reason`` and the
  OpenAI-compatible ``finish_reason`` are the only evidence used. Output that
  merely *looks* cut off is not truncation, and a response whose stop reason is
  absent or unrecognised becomes :attr:`StopReason.UNKNOWN` — which is not read
  as a complete answer. Guessing from output shape is how a truncated patch
  gets applied as a whole one.
* **Every dispatch is measured.** Latency is wall-clock and host-side, so it is
  the same quantity on both protocols; token counts are the backend's own, and
  are ``None`` when it did not report them. An absent count never becomes zero —
  a zero would average into telemetry as a real measurement of nothing.

**CAV-01, which is why this module has an opinion about Ollama.** Ollama's
native ``/api/generate`` returned invalid HumanEval+ scores — 32.3% against a
true 84.1% for Qwen2.5-Coder 7B (``data/README.md``, CLM-0002). The path is
implemented here because it is what a default Ollama install offers, but it is
marked: every completion from it carries ``quality_safe=False`` and a note, and
a :class:`Request` that declares itself ``quality_sensitive`` is refused
outright with :class:`QualityCaveatError`. That is the whole of #21's third
acceptance bullet — the dependency is allowed, the *silence* is not. The remedy
is a config edit rather than a code change, because Ollama also serves the
OpenAI-compatible shape: point the same host at ``api: openai``.

**On credentials.** The key is resolved from the environment at the moment of
dispatch through :meth:`~mcgyvr.pool.Endpoint.credential` and lives only in the
``Authorization`` header of one request. A keyless endpoint — the ordinary case
for a local backend — gets no header at all rather than an empty one, so a
local OpenAI-compatible server needs no API key and is never sent an
unauthenticated-looking credential. No error message here interpolates a key.

**What is deliberately not here.** Whether an endpoint is answering at all is
#22's question and needs probing; this module reports a failure to reach one
and does not cache that judgement. Bounding how many dispatches run at once is
#23's, and acquires at this same seam. Choosing *which* rung to send a contract
to, and escalating when it fails, are #24's. Assembling the prompt and parsing a
worker's file-shaped answer are #25's — a :class:`Request` here carries text.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

from mcgyvr.pool import Endpoint, Protocol, SourceMap, UnknownRungError

# Local models on modest hardware are slow rather than broken: a 7B answering a
# capped generation on a 6 GB card can take minutes. This is the ceiling on one
# dispatch, not a health check — #22 owns "is anything there", with a timeout
# three orders of magnitude shorter.
GENERATE_TIMEOUT_S = 120.0

# How much of a failed response body an error message quotes. Enough to carry a
# backend's own explanation, short enough not to paste a model's whole answer
# into a traceback.
_ERROR_BODY_CHARS = 400

CAV_01_NOTE = (
    "Served by Ollama's native /api/generate, which CAV-01 records as returning "
    "invalid quality measurements (32.3% against a true 84.1% for "
    "qwen2.5-coder:7b). Usable for work, not for measuring a model. Declare the "
    "same host with api: openai to get the OpenAI-compatible path instead."
)


class RunnerError(Exception):
    """A dispatch did not produce a completion."""


class TransportError(RunnerError):
    """The endpoint could not be reached, or did not answer in time."""


class BackendError(RunnerError):
    """The endpoint answered with an HTTP error status."""


class ProtocolError(RunnerError):
    """The endpoint answered, but not in a shape this protocol can read."""


class QualityCaveatError(RunnerError):
    """A quality-sensitive request was routed at a path a caveat invalidates."""


class StopReason(StrEnum):
    """Why generation stopped, as reported by the backend.

    ``UNKNOWN`` is a real answer and the reason this is not a boolean: a backend
    that reported nothing, or reported a word this module does not recognise,
    has not said the answer is complete. Treating that as completion is the
    failure mode #21 asks to be designed out, so the mapping is deliberately
    unoptimistic and the backend's own word is kept alongside in
    :attr:`Completion.raw_stop_reason`.
    """

    COMPLETE = "complete"
    TRUNCATED = "truncated"
    FILTERED = "filtered"
    UNKNOWN = "unknown"


# The words the two protocols and the servers that speak them actually use.
# Anything absent from this table becomes UNKNOWN rather than being guessed at:
# a new backend inventing a word should surface as "it did not say", not as a
# clean finish. `eos_token` is TGI's; `max_tokens` appears on some
# OpenAI-compatible servers where the reference implementation says `length`.
_STOP_REASONS: dict[str, StopReason] = {
    "stop": StopReason.COMPLETE,
    "eos_token": StopReason.COMPLETE,
    "length": StopReason.TRUNCATED,
    "max_tokens": StopReason.TRUNCATED,
    "content_filter": StopReason.FILTERED,
}


@dataclass(frozen=True)
class Request:
    """One generation, described without reference to who will serve it.

    No model and no endpoint: the model comes from the rung being dispatched to
    and the endpoint from the seam, so the same ``Request`` can be sent at any
    step of the ladder. That is what makes "the same contract executes
    identically on either protocol" checkable rather than a claim.

    ``max_output_tokens`` has no default on purpose — an uncapped request is
    exactly the mistake CAV-03 is a record of, and a caller that has not thought
    about the ceiling should have to. ``temperature`` defaults to 0.0 because a
    worker's output is judged by a deterministic gate; sampling is a decision to
    be made explicitly, not inherited from a backend's default.

    There is no ``stop`` field. ADR-0009 decided that v1 bounds a reply with the
    cap and a named truncation, because a stop sequence makes a bad reply
    shorter where the cap makes it *named* — and a shorter whole-file reply is
    still valid Python that the gate will accept. Adding the field back is
    re-opening that record, not filling in an omission.

    ``quality_sensitive`` marks benchmarking and any other path whose output is
    read as a measurement of the model rather than as work. It does not change
    what is sent; it decides whether a caveated path is allowed to serve it at
    all.
    """

    prompt: str
    max_output_tokens: int
    system: str = ""
    temperature: float = 0.0
    timeout_s: float = GENERATE_TIMEOUT_S
    quality_sensitive: bool = False

    def __post_init__(self) -> None:
        if self.max_output_tokens < 1:
            raise ValueError(
                f"max_output_tokens must be at least 1, got "
                f"{self.max_output_tokens}. An uncapped dispatch is not "
                f"expressible here by design."
            )
        if self.timeout_s <= 0:
            raise ValueError(f"timeout_s must be positive, got {self.timeout_s}")


@dataclass(frozen=True)
class Completion:
    """What came back, how it ended, and what it cost — the same on both paths.

    Carries the cap it was issued under so that :attr:`overran_cap` is
    answerable from the record alone, without the request that produced it: a
    telemetry row that cannot say what ceiling it was measured against cannot be
    compared with another one.

    ``input_tokens`` and ``output_tokens`` are the backend's own counts and are
    ``None`` when it reported none. ``latency_s`` is measured host-side around
    the request, which is the only quantity both protocols express the same way
    — a server-reported duration excludes queueing and is not comparable across
    backends.
    """

    text: str
    stop_reason: StopReason
    raw_stop_reason: str
    model: str
    source: str
    protocol: Protocol
    max_output_tokens: int
    latency_s: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    quality_safe: bool = True
    notes: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """Whether the backend said it finished. ``UNKNOWN`` is not this."""
        return self.stop_reason is StopReason.COMPLETE

    @property
    def truncated(self) -> bool:
        """Whether the backend said it hit the ceiling. Never inferred."""
        return self.stop_reason is StopReason.TRUNCATED

    @property
    def overran_cap(self) -> bool | None:
        """Whether more tokens came back than were allowed, or ``None``.

        ``None`` means the backend reported no count, so the cap it was sent
        cannot be checked — distinct from a checked cap that held.
        """
        if self.output_tokens is None:
            return None
        return self.output_tokens > self.max_output_tokens


@dataclass(frozen=True)
class _Parsed:
    """The per-protocol part of an answer, before it becomes a completion.

    Everything a protocol is allowed to decide, and nothing more. The
    completion itself is assembled once, in :meth:`Runner.generate`, which is
    what keeps the two paths from drifting into two different meanings of
    "truncated".
    """

    text: str
    raw_stop_reason: str
    input_tokens: int | None
    output_tokens: int | None


class Runner(ABC):
    """Dispatch against one endpoint in one wire protocol.

    Construct through :func:`runner_for`, which picks the implementation from
    the endpoint's protocol; nothing here should be selected by name at a call
    site, because that is the dependency on a backend the seam exists to
    prevent.

    A subclass supplies three things — the path it posts to, the body it sends,
    and how to read an answer — and declares whether its path is safe to measure
    a model through. Timing, credentials, transport, the stop-reason mapping and
    the cap check are shared, so neither protocol can quietly mean something
    different by them.
    """

    protocol: ClassVar[Protocol]
    path: ClassVar[str]
    # False marks a path a caveat invalidates for measurement (CAV-01). It
    # decides both the flag on every completion and whether a
    # quality-sensitive request is refused.
    quality_safe: ClassVar[bool] = True

    def __init__(self, endpoint: Endpoint) -> None:
        self.endpoint = endpoint

    def generate(self, model: str, request: Request) -> Completion:
        """Run one request against this endpoint and return what came back.

        Raises :class:`QualityCaveatError` before sending anything when the
        request is quality-sensitive and this path is caveated,
        :class:`TransportError` when the endpoint cannot be reached,
        :class:`BackendError` on an HTTP error status, and
        :class:`ProtocolError` when the answer cannot be read.
        """
        if request.quality_sensitive and not self.quality_safe:
            raise QualityCaveatError(
                f"refusing a quality-sensitive request on the "
                f"{self.protocol} path of source {self.endpoint.source!r}. "
                f"{CAV_01_NOTE}"
            )

        url = _url_for(self.endpoint.base_url, self.path)
        started = time.monotonic()
        document = _post_json(
            url, self._payload(model, request), self._headers(), request.timeout_s
        )
        latency_s = time.monotonic() - started

        parsed = self._parse(document)
        stop_reason = _STOP_REASONS.get(parsed.raw_stop_reason, StopReason.UNKNOWN)
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
            quality_safe=self.quality_safe,
            notes=self._notes(parsed, stop_reason, request),
        )

    def _notes(
        self, parsed: _Parsed, stop_reason: StopReason, request: Request
    ) -> tuple[str, ...]:
        """Anything about this dispatch that a caller should not have to infer."""
        notes: list[str] = []
        if not self.quality_safe:
            notes.append(CAV_01_NOTE)
        if stop_reason is StopReason.TRUNCATED:
            notes.append(
                f"the reply hit the {request.max_output_tokens}-token cap and "
                f"is incomplete. Under ADR-0009 that is a named failure, not a "
                f"short answer: it must not be applied to a file."
            )
        if stop_reason is StopReason.UNKNOWN:
            reported = parsed.raw_stop_reason or "nothing"
            notes.append(
                f"{self.endpoint.source!r} reported {reported} as the reason "
                f"generation stopped, which is not a word this runner knows. "
                f"The answer is not being read as complete."
            )
        if parsed.output_tokens is not None and (
            parsed.output_tokens > request.max_output_tokens
        ):
            notes.append(
                f"the backend returned {parsed.output_tokens} output tokens "
                f"against a cap of {request.max_output_tokens}; it did not "
                f"honour the ceiling it was sent."
            )
        return tuple(notes)

    def _headers(self) -> dict[str, str]:
        """Request headers, with the key read at this moment and not before.

        A keyless endpoint gets no ``Authorization`` header at all — an empty
        one is a different request, and some servers reject it.
        """
        headers = {"Content-Type": "application/json"}
        key = self.endpoint.credential()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    @abstractmethod
    def _payload(self, model: str, request: Request) -> dict[str, Any]:
        """The request body in this protocol's shape, cap included."""

    @abstractmethod
    def _parse(self, document: dict[str, Any]) -> _Parsed:
        """Read an answer, raising :class:`ProtocolError` if it cannot be."""


class OllamaRunner(Runner):
    """Ollama's native generate — implemented, and marked by CAV-01.

    ``/api/generate`` is what a default Ollama install offers and what most
    local setups already have running, so refusing to speak it would refuse the
    common machine. What it cannot do is carry a measurement: CAV-01 records
    this path scoring a model at 32.3% against a true 84.1%, and a table
    regenerated through it would route away from the best model available. So
    ``quality_safe`` is False here, which puts a note on every completion and
    refuses a request that declares itself quality-sensitive.
    """

    protocol: ClassVar[Protocol] = Protocol.OLLAMA
    path: ClassVar[str] = "/api/generate"
    quality_safe: ClassVar[bool] = False

    def _payload(self, model: str, request: Request) -> dict[str, Any]:
        options: dict[str, Any] = {
            "num_predict": request.max_output_tokens,
            "temperature": request.temperature,
        }
        payload: dict[str, Any] = {
            "model": model,
            "prompt": request.prompt,
            # Nothing here streams: a single document is what makes the stop
            # reason and the token counts readable in one place.
            "stream": False,
            "options": options,
        }
        if request.system:
            payload["system"] = request.system
        return payload

    def _parse(self, document: dict[str, Any]) -> _Parsed:
        text = document.get("response")
        if not isinstance(text, str):
            raise ProtocolError(
                f"{self.endpoint.source!r} answered /api/generate without a "
                f"string 'response' field. Keys present: "
                f"{', '.join(sorted(document)) or '(none)'}"
            )
        return _Parsed(
            text=text,
            raw_stop_reason=_as_str(document.get("done_reason")),
            input_tokens=_as_int(document.get("prompt_eval_count")),
            output_tokens=_as_int(document.get("eval_count")),
        )


class OpenAIRunner(Runner):
    """The OpenAI-compatible chat-completions shape — vLLM, llama-server, TGI,
    LM Studio, Ollama's own ``/v1``, and the hosted providers.

    One protocol rather than one integration per vendor, which is what makes
    adding a backend a config entry. It is also the path a measurement must run
    on (CAV-01), so this is the quality-safe half of the pair.
    """

    protocol: ClassVar[Protocol] = Protocol.OPENAI
    path: ClassVar[str] = "/v1/chat/completions"

    def _payload(self, model: str, request: Request) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            # `max_tokens` rather than `max_completion_tokens`: every local
            # server this protocol exists to reach accepts it, and sending both
            # is an error on several of them. A hosted reasoning model that has
            # retired it is the one case this would need to grow a branch for.
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        return payload

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
        if not isinstance(content, str):
            raise ProtocolError(
                f"{self.endpoint.source!r} answered chat completions without "
                f"string content at choices[0].message.content"
            )
        usage = document.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        raw_stop = first.get("finish_reason") if isinstance(first, dict) else None
        return _Parsed(
            text=content,
            raw_stop_reason=_as_str(raw_stop),
            input_tokens=_as_int(usage.get("prompt_tokens")),
            output_tokens=_as_int(usage.get("completion_tokens")),
        )


_RUNNERS: dict[Protocol, type[Runner]] = {
    Protocol.OLLAMA: OllamaRunner,
    Protocol.OPENAI: OpenAIRunner,
}


def runner_for(endpoint: Endpoint) -> Runner:
    """The runner that speaks this endpoint's protocol.

    The only place a protocol selects an implementation. :class:`Protocol` has
    two members and this table has two entries; a third would be a new wire
    shape, which is the one thing that is genuinely not a config entry.
    """
    return _RUNNERS[endpoint.protocol](endpoint)


def dispatch(source_map: SourceMap, rung: str, request: Request) -> Completion:
    """Send a request to a rung of the ladder, whatever is serving it.

    The intended way in, and the reason nothing above the seam needs to touch
    :meth:`~mcgyvr.pool.SourceMap.bind`: the model comes from the rung and the
    protocol from its endpoint, so a caller names a step of the ladder and
    nothing about a machine. Propagates
    :class:`~mcgyvr.pool.UnknownRungError` and
    :class:`~mcgyvr.pool.SourceUnavailableError` from the binding unchanged —
    asking for a rung that does not exist and asking for one whose source
    cannot serve it stay different mistakes.
    """
    endpoint = source_map.bind(rung)
    step = source_map.get(rung)
    if step is None:  # unreachable: bind() raises first for both causes
        raise UnknownRungError(f"no rung named {rung!r}")
    return runner_for(endpoint).generate(step.model, request)


def dispatch_role(
    source_map: SourceMap, role: str, request: Request
) -> Completion | None:
    """Send a request to a non-ladder role, or ``None`` when it has none.

    ``None`` mirrors :meth:`~mcgyvr.pool.SourceMap.role`: a keyless install runs
    with no verifier at all, and that is an ordinary state rather than a
    failure. A role whose source is declared but unusable still raises.
    """
    binding = source_map.role(role)
    if binding is None:
        return None
    return runner_for(binding.endpoint).generate(binding.model, request)


# --- transport --------------------------------------------------------------


def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    """POST a JSON document and return the JSON answer.

    Every failure is named rather than folded into one: unreachable is not the
    same as a 401, and neither is the same as an answer this runner cannot
    read. No message interpolates a credential — the key is in ``headers``,
    which is never quoted.
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()[:_ERROR_BODY_CHARS]
        raise BackendError(
            f"{url} answered HTTP {exc.code}: {detail or '(empty body)'}"
        ) from exc
    except OSError as exc:
        # URLError and the socket timeout are both OSError; to a caller they
        # mean the same thing — nothing usable answered within the timeout.
        raise TransportError(
            f"could not reach {url} within {timeout:g}s: {exc}"
        ) from exc

    try:
        document = json.loads(raw)
    except ValueError as exc:
        raise ProtocolError(
            f"{url} answered with something that is not JSON: "
            f"{raw.strip()[:_ERROR_BODY_CHARS] or '(empty body)'}"
        ) from exc
    if not isinstance(document, dict):
        raise ProtocolError(f"{url} answered with JSON {type(document).__name__}")
    return document


# --- small deterministic helpers -------------------------------------------


def _url_for(base_url: str, path: str) -> str:
    """Join a source's base URL to a protocol path, tolerating a doubled ``/v1``.

    The config reference documents ``base_url`` as where the source answers —
    a root, ``http://localhost:11434`` — and that is what the local backends
    want. But every hosted provider documents its own endpoint *with* ``/v1``
    on the end, so a user pasting the URL from the page they got their key from
    would otherwise be sent to ``/v1/v1/chat/completions``: a 404 whose message
    points at the model or the key rather than at the extra path segment. Both
    spellings are accepted here rather than in the loader, because appending
    the path is this module's business and #20's ``Endpoint`` is shared with
    callers that append nothing.
    """
    base = base_url.rstrip("/")
    if path.startswith("/v1/") and base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + path


def _as_str(value: object) -> str:
    """A reported word as a string, with anything else read as unreported."""
    return value if isinstance(value, str) else ""


def _as_int(value: object) -> int | None:
    """A reported count, or ``None`` when it was not reported.

    ``None`` rather than ``0``: a backend that said nothing about tokens has
    not said zero, and a zero would average into telemetry as a measurement.
    ``bool`` is excluded because it is an ``int`` and never a count.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
