"""Measure a serving unit from the rig it runs on, and hold a load against it.

The door pipes this file's text to the rig as ``python3 - mcgyvr-harness
SPEC``: :func:`main` reads one JSON spec from argv and prints one JSON answer,
an ``error`` object plus a nonzero status when the unit or the rig could not be
read. Two things are asked of a unit, at the loopback address of the ``port``
its spec names:

* a measurement (:func:`on_the_rig`): a warmup request, then ``DECODE_SAMPLES``
decodes and ``PREFILL_SAMPLES`` prefills, filed as median decode and prefill
tokens per second, with every sample beside them when asked for;
* a load (:func:`load`): ``width`` requests, each a prompt of the unit's own
window and generation to fill the rest of it, held for at most
``LOAD_LIMIT_S`` while the rig's card is sampled every ``LOAD_SAMPLE_S``, then
the unit's status page read until it shows nothing in flight.

A unit that does not answer as asked is a :class:`HarnessError` naming the
address and quoting a bounded part of what it sent; a status page that cannot
be read is ``None``, the way an unreachable one already is.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, overload

#: The word every real run carries as argv[1]; anything else is refused as a
#: usage error before a spec is read.
HARNESS_WORD = "mcgyvr-harness"

_SHORT_TEXT = "Write a Python function that reverses a singly linked list in place.\n"
_LONG_BLOCK = (
    "You are a precise software engineer. Explain step by step how to compute "
    "the size in bytes of every expert weight in a GGUF file, then write a "
    "Python function that opens the file, walks the metadata, and prints a "
    "table of tensor name, shape, and byte size for every tensor that has an "
    "expert dimension. Be complete and correct.\n\n"
)
#: vLLM is asked in chat messages: the short prompt as one user turn, the long
#: prefill prompt as the long block repeated 28 times.
VLLM_SHORT: list[dict[str, str]] = [{"role": "user", "content": _SHORT_TEXT}]
VLLM_LONG = _LONG_BLOCK * 28
#: llama.cpp takes the same two texts as a bare prompt string instead.
LLAMA_SHORT_PROMPT = _SHORT_TEXT
LLAMA_LONG_PROMPT = (_LONG_BLOCK * 28).strip()

WARMUP_TOKENS = 64
DECODE_TOKENS = 256
PREFILL_TOKENS = 16
DECODE_SAMPLES = 5
PREFILL_SAMPLES = 3
#: Naming the model is a quick read; a completion may take the minutes a long
#: prefill needs.
MODELS_TIMEOUT_S = 10.0
REQUEST_TIMEOUT_S = 900.0
#: The page each engine publishes its in-flight count on.
STATUS_PATHS = {"vllm": "/metrics", "llama.cpp": "/slots"}
#: The two vLLM metrics that together are the requests it holds in flight.
VLLM_RUNNING = "vllm:num_requests_running"
VLLM_WAITING = "vllm:num_requests_waiting"
#: How much of the unit's window a load leaves for generation: each request's
#: prompt fills the window less these tokens, so the load keeps decoding while it
#: runs.
LOAD_OUTPUT_TOKENS = 64
#: Seconds between two samples of the rig's card: during the load, and after the
#: close while the unit is waited on for idle.
LOAD_SAMPLE_S = 0.5
#: The most a load runs (owner ruling NB5): at thirty seconds every unfinished
#: request's connection is closed, and the wait for an idle status page takes
#: over with no limit of its own.
LOAD_LIMIT_S = 30


class HarnessError(Exception):
    """A unit or rig did not answer as asked; the message says which address and why."""


class Transport(Protocol):
    """What a measurement asks of an endpoint: a JSON GET and a JSON POST."""

    def get(self, url: str, timeout: float) -> Any:
        """The JSON document at url, read within timeout."""

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> Any:
        """The JSON answer to payload posted to url, read within timeout."""


class LoadTransport(Protocol):
    """The same two calls as Transport, with the timeout a load may drop."""

    def get(self, url: str, timeout: float | None) -> Any:
        """The JSON document at url; a timeout of None waits as long as it takes."""

    def post(self, url: str, payload: dict[str, Any], timeout: float | None) -> Any:
        """The JSON answer to payload posted to url; a timeout of None waits as
        long as it takes."""


#: What reading a reply from a server that answers badly raises: no connection or
#: a broken socket (OSError, which urllib.error.URLError is), a body cut short or
#: a status line that is not one (http.client.HTTPException), bytes that are not
#: UTF-8 or not JSON (ValueError, which json.JSONDecodeError and
#: UnicodeDecodeError are), and a document nested deeper than the JSON reader
#: follows (RecursionError). Each is a reply that did not arrive properly.
_UNREADABLE_REPLY = (OSError, ValueError, http.client.HTTPException, RecursionError)

#: How many characters of a bad reply's repr an error quotes back, so a server
#: answering with megabytes cannot flood the message: a longer repr keeps its first
#: and last half, joined by " ... ".
REPLY_QUOTED_AT_MOST = 200


def _bounded(text: str) -> str:
    """text's repr, cut to REPLY_QUOTED_AT_MOST characters with " ... " between
    its ends."""
    shown = repr(text)
    if len(shown) <= REPLY_QUOTED_AT_MOST:
        return shown
    keep = (REPLY_QUOTED_AT_MOST - len(" ... ")) // 2
    return f"{shown[:keep]} ... {shown[-keep:]}"


def _json_answer(request: str | urllib.request.Request, timeout: float | None) -> Any:
    """The JSON document request answers with, or a HarnessError naming its URL."""
    url = request if isinstance(request, str) else request.full_url
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except _UNREADABLE_REPLY as exc:
        raise HarnessError(
            f"{url} did not answer properly: {type(exc).__name__}: {_bounded(str(exc))}"
        ) from exc


class HttpTransport:
    """The real transport: urllib against the unit's address, a connection per call."""

    def get(self, url: str, timeout: float | None) -> Any:
        """The JSON document at url, read within timeout."""
        return _json_answer(url, timeout)

    def post(self, url: str, payload: dict[str, Any], timeout: float | None) -> Any:
        """payload as a JSON body posted to url; the JSON answer is returned."""
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return _json_answer(request, timeout)


def _median(samples: list[float], what: str) -> float:
    if not samples:
        raise HarnessError(f"no {what} sample could be read")
    return float(statistics.median(samples))


def _count(body: Any, key: str) -> int | None:
    usage = body.get("usage") if isinstance(body, Mapping) else None
    value = usage.get(key) if isinstance(usage, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _timing(body: Any, key: str) -> float | None:
    timings = body.get("timings") if isinstance(body, Mapping) else None
    value = timings.get(key) if isinstance(timings, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value)


@overload
def measure_vllm(
    address: str,
    transport: Transport,
    clock: Callable[[], float],
    *,
    with_samples: Literal[False] = ...,
) -> dict[str, float]: ...


@overload
def measure_vllm(
    address: str,
    transport: Transport,
    clock: Callable[[], float],
    *,
    with_samples: Literal[True],
) -> dict[str, Any]: ...


def measure_vllm(
    address: str,
    transport: Transport,
    clock: Callable[[], float],
    *,
    with_samples: bool = False,
) -> dict[str, Any]:
    """Measure a vLLM unit's decode and prefill tokens per second at address.

    The model is the first id ``/v1/models`` names, and one short warmup request
    is sent before anything is timed. Each decode sample is a chat completion of
    ``DECODE_TOKENS`` tokens, timed by ``clock`` and divided by the
    ``completion_tokens`` its reply reports; each prefill sample sends the long
    block and is divided by the ``prompt_tokens`` it reports. The answer holds
    the medians as ``warm_decode_tok_s`` and ``prefill_tok_s``, with every sample
    in ``decode_samples`` and ``prefill_samples`` when ``with_samples`` is set.
    A listing that names no model, and a set with no readable sample, are both a
    HarnessError.
    """
    base = address.rstrip("/")
    listing = transport.get(f"{base}/v1/models", MODELS_TIMEOUT_S)
    try:
        model = listing["data"][0]["id"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HarnessError(f"{base}/v1/models names no model") from exc
    url = f"{base}/v1/chat/completions"
    warmup = {"max_tokens": WARMUP_TOKENS, "temperature": 0, "ignore_eos": False}
    transport.post(
        url, {"model": model, "messages": VLLM_SHORT, **warmup}, REQUEST_TIMEOUT_S
    )

    decode: list[float] = []
    for _ in range(DECODE_SAMPLES):
        payload = {
            "model": model,
            "messages": VLLM_SHORT,
            "max_tokens": DECODE_TOKENS,
            "temperature": 0,
            "ignore_eos": True,
        }
        started = clock()
        body = transport.post(url, payload, REQUEST_TIMEOUT_S)
        seconds = clock() - started
        tokens = _count(body, "completion_tokens")
        if tokens is not None and seconds > 0:
            decode.append(tokens / seconds)

    prefill: list[float] = []
    for _ in range(PREFILL_SAMPLES):
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": VLLM_LONG}],
            "max_tokens": PREFILL_TOKENS,
            "temperature": 0,
            "ignore_eos": False,
        }
        started = clock()
        body = transport.post(url, payload, REQUEST_TIMEOUT_S)
        seconds = clock() - started
        tokens = _count(body, "prompt_tokens")
        if tokens is not None and seconds > 0:
            prefill.append(tokens / seconds)

    figures: dict[str, Any] = {
        "warm_decode_tok_s": _median(decode, "decode"),
        "prefill_tok_s": _median(prefill, "prefill"),
    }
    if with_samples:
        figures["decode_samples"] = list(decode)
        figures["prefill_samples"] = list(prefill)
    return figures


@overload
def measure_llamacpp(
    address: str, transport: Transport, *, with_samples: Literal[False] = ...
) -> dict[str, float]: ...


@overload
def measure_llamacpp(
    address: str, transport: Transport, *, with_samples: Literal[True]
) -> dict[str, Any]: ...


def measure_llamacpp(
    address: str, transport: Transport, *, with_samples: bool = False
) -> dict[str, Any]:
    """Measure a llama.cpp unit's decode and prefill tokens per second at address.

    A short warmup request goes to ``/completion`` first. Each decode sample asks
    for ``DECODE_TOKENS`` tokens with ``cache_prompt`` off and takes the
    ``predicted_per_second`` its reply reports; each prefill sample sends the long
    block and takes its ``prompt_per_second``. Both rates are the unit's own
    timing, so unlike vLLM nothing here is clocked. The answer holds the medians
    as ``warm_decode_tok_s`` and ``prefill_tok_s``, with every sample beside them
    when ``with_samples`` is set, and no readable sample is a HarnessError.
    """
    url = f"{address.rstrip('/')}/completion"
    transport.post(
        url,
        {"prompt": LLAMA_SHORT_PROMPT, "n_predict": WARMUP_TOKENS, "temperature": 0},
        REQUEST_TIMEOUT_S,
    )
    decode: list[float] = []
    for _ in range(DECODE_SAMPLES):
        body = transport.post(
            url,
            {
                "prompt": LLAMA_SHORT_PROMPT,
                "n_predict": DECODE_TOKENS,
                "temperature": 0,
                "cache_prompt": False,
            },
            REQUEST_TIMEOUT_S,
        )
        rate = _timing(body, "predicted_per_second")
        if rate is not None:
            decode.append(rate)
    prefill: list[float] = []
    for _ in range(PREFILL_SAMPLES):
        body = transport.post(
            url,
            {
                "prompt": LLAMA_LONG_PROMPT,
                "n_predict": PREFILL_TOKENS,
                "temperature": 0,
                "cache_prompt": False,
            },
            REQUEST_TIMEOUT_S,
        )
        rate = _timing(body, "prompt_per_second")
        if rate is not None:
            prefill.append(rate)
    figures: dict[str, Any] = {
        "warm_decode_tok_s": _median(decode, "decode"),
        "prefill_tok_s": _median(prefill, "prefill"),
    }
    if with_samples:
        figures["decode_samples"] = list(decode)
        figures["prefill_samples"] = list(prefill)
    return figures


def _page(url: str) -> str | None:
    """The text url answers with within MODELS_TIMEOUT_S, or None when it is not
    readable."""
    try:
        with urllib.request.urlopen(url, timeout=MODELS_TIMEOUT_S) as response:
            text: str = response.read().decode("utf-8", "replace")
            return text
    except _UNREADABLE_REPLY:
        return None


def on_the_rig(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Measure the unit a probe spec names, at the loopback address of its port.

    A ``vllm`` unit is measured by ``measure_vllm``, anything else by
    ``measure_llamacpp``, both keeping every sample. Once measured, the unit's
    status page is read as ``after_page``, so the door can see what the
    measurement left in flight.
    """
    engine = str(spec.get("engine"))
    port = int(spec["port"])
    address = f"http://127.0.0.1:{port}"
    transport = HttpTransport()
    if engine == "vllm":
        figures = measure_vllm(address, transport, time.perf_counter, with_samples=True)
    else:
        figures = measure_llamacpp(address, transport, with_samples=True)
    path = STATUS_PATHS.get(engine, STATUS_PATHS["llama.cpp"])
    return {"figures": figures, "after_page": _page(f"{address}{path}")}


def _now() -> str:
    # The second a load was filed at, in UTC, without fraction or zone: the shape
    # the journal keeps its timestamps in.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")  # noqa: UP017


def _tokens(
    engine: str, base: str, transport: LoadTransport, model: str | None, text: str
) -> int:
    """How many tokens the unit counts in text, asked of its own /tokenize endpoint."""
    if engine == "vllm":
        body = transport.post(
            f"{base}/tokenize", {"model": model, "prompt": text}, None
        )
        count = body.get("count") if isinstance(body, Mapping) else None
    else:
        body = transport.post(
            f"{base}/tokenize", {"content": text, "add_special": True}, None
        )
        tokens = body.get("tokens") if isinstance(body, Mapping) else None
        count = len(tokens) if isinstance(tokens, list) else None
    if isinstance(count, bool) or not isinstance(count, int):
        raise HarnessError(f"{base}/tokenize gave no token count")
    return count


def _load_prompt(
    engine: str, base: str, transport: LoadTransport, model: str | None, window: int
) -> tuple[str, int]:
    """The long block repeated to the most of the window a load's prompt may take.

    A prompt gets ``window - LOAD_OUTPUT_TOKENS`` tokens at most, leaving every
    request that many to generate. One block is tokenized to learn how many
    blocks would reach the target, and blocks are dropped one at a time until
    the unit's own count of the whole prompt fits. The prompt and the count the
    unit gave it are returned; a window too small to hold one block is a
    HarnessError.
    """
    target = window - LOAD_OUTPUT_TOKENS
    one = _tokens(engine, base, transport, model, _LONG_BLOCK)
    blocks = max(1, target // max(1, one))
    while True:
        prompt = _LONG_BLOCK * blocks
        count = _tokens(engine, base, transport, model, prompt)
        if count <= target or blocks == 1:
            break
        blocks -= 1
    if count >= window:
        raise HarnessError(
            f"a {window}-token window holds no prompt of the long block ({count})"
        )
    return prompt, count


def _poll(poll: str, *args: str) -> str:
    """The stdout of the rig's poll script run by bash, or the empty string when
    it did not run cleanly."""
    try:
        done = subprocess.run(
            ["bash", "-s", "--", *args],
            input=poll,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return done.stdout if done.returncode == 0 else ""


def _unbounded_page(url: str) -> str | None:
    """The text url answers with, waited on with no timeout, or None when it
    cannot be read."""
    try:
        with urllib.request.urlopen(url) as response:
            text: str = response.read().decode("utf-8", "replace")
            return text
    except _UNREADABLE_REPLY:
        return None


def prometheus_totals(
    page: str | None, names: tuple[str, ...]
) -> dict[str, float] | None:
    """The summed value of each named metric in a Prometheus page, or None.

    Comment lines and blanks are skipped; a sample line's name is what stands before
    its ``{labels}`` or its value, and every line of one name is added up, so a metric
    labelled per process arrives as one total. A page that could not be read (None) and
    a value that is not a float both give None; a page naming none of the names gives
    an empty mapping.
    """
    if page is None:
        return None
    totals: dict[str, float] = {}
    for line in page.splitlines():
        if not line or line.startswith("#"):
            continue
        if "{" in line and "}" in line:
            name = line[: line.index("{")]
            tail = line[line.rindex("}") + 1 :].split()
        else:
            name, *tail = line.split()
        if name not in names or not tail:
            continue
        try:
            totals[name] = totals.get(name, 0.0) + float(tail[0])
        except ValueError:
            return None
    return totals


def metric_total(page: str | None, name: str) -> float | None:
    """The value of one Prometheus metric in a page, or None when the page or the
    metric cannot be read."""
    totals = prometheus_totals(page, (name,))
    return None if totals is None else totals.get(name)


def slots_in_flight(page: str | None) -> int | None:
    """How many of a llama.cpp unit's slots are processing, from its ``/slots`` page.

    None when the page cannot be read or is not a non-empty list of objects that each
    say whether they are processing.
    """
    if page is None:
        return None
    try:
        slots = json.loads(page)
    except (ValueError, RecursionError):
        return None
    if not isinstance(slots, list) or not slots:
        return None
    busy = 0
    for slot in slots:
        processing = slot.get("is_processing") if isinstance(slot, dict) else None
        if not isinstance(processing, bool):
            return None
        busy += int(processing)
    return busy


def vllm_in_flight(page: str | None) -> int | None:
    """Running plus waiting requests from a vLLM /metrics page, or None when
    either metric is missing."""
    totals = prometheus_totals(page, (VLLM_RUNNING, VLLM_WAITING))
    if totals is None or VLLM_RUNNING not in totals or VLLM_WAITING not in totals:
        return None
    return int(totals[VLLM_RUNNING] + totals[VLLM_WAITING])


def in_flight(engine: str | None, page: str | None) -> int | None:
    """What a unit holds in flight, read from its status page: a vllm unit from
    its metrics, anything else from its slots."""
    return vllm_in_flight(page) if engine == "vllm" else slots_in_flight(page)


class Batch(Protocol):
    """A load's requests in flight: started, then asked until they are all done."""

    def done(self) -> bool:
        """Whether every request has stopped, whether it finished or not."""

    def completed(self) -> int:
        """How many requests got a response that was not an HTTP error."""

    def errors(self) -> list[str]:
        """What went wrong for the requests that did not, one message each."""

    def close(self) -> int:
        """Close the connections of the requests still running, and return how
        many were left unfinished."""


class Requests:
    """A batch of payloads posted to one url at once: a connection and a thread
    per request.

    Each request reads its whole response, counts as completed with a status under
    400, and files anything else as an error unless the batch is being closed.
    Closing shuts the connections down and joins the threads.
    """

    def __init__(self, url: str, payloads: Sequence[Mapping[str, Any]]) -> None:
        split = urllib.parse.urlsplit(url)
        self._path = split.path or "/"
        self._lock = threading.Lock()
        self._completed = 0
        self._errors: list[str] = []
        self._closing = False
        self._connections: list[http.client.HTTPConnection] = []
        self._threads: list[threading.Thread] = []
        # One connection and one thread per request, made before any of them
        # starts, so the whole width is in flight at the same moment.
        for payload in payloads:
            connection = http.client.HTTPConnection(
                split.hostname or "127.0.0.1", split.port
            )
            self._connections.append(connection)
            self._threads.append(
                threading.Thread(
                    target=self._one, args=(connection, dict(payload)), daemon=True
                )
            )
        for thread in self._threads:
            thread.start()

    def _one(
        self, connection: http.client.HTTPConnection, payload: dict[str, Any]
    ) -> None:
        try:
            connection.request(
                "POST",
                self._path,
                body=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
            if response.status >= 400:
                raise OSError(f"HTTP {response.status} from {self._path}")
        except (OSError, http.client.HTTPException) as exc:
            with self._lock:
                if not self._closing:
                    self._errors.append(f"{type(exc).__name__}: {exc}")
            return
        with self._lock:
            self._completed += 1

    def done(self) -> bool:
        return not any(thread.is_alive() for thread in self._threads)

    def completed(self) -> int:
        with self._lock:
            return self._completed

    def errors(self) -> list[str]:
        with self._lock:
            return list(self._errors)

    def close(self) -> int:
        with self._lock:
            self._closing = True
        for connection in self._connections:
            if connection.sock is not None:
                with contextlib.suppress(OSError):
                    connection.sock.shutdown(socket.SHUT_RDWR)
            connection.close()
        for thread in self._threads:
            thread.join()
        with self._lock:
            return len(self._threads) - self._completed - len(self._errors)


def load(
    spec: Mapping[str, Any],
    *,
    transport: LoadTransport | None = None,
    fetch: Callable[[str], str | None] | None = None,
    poll: Callable[..., str] | None = None,
    start: Callable[[str, Sequence[Mapping[str, Any]]], Batch] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Hold a load against a unit and file what the rig saw while it ran.

    Each of the ``width`` requests asks its prompt plus generation to fill the unit's
    ``window``: the prompt is the long block cut to ``window - LOAD_OUTPUT_TOKENS``
    tokens by the unit's own tokenizer, and ``max_tokens`` is what the window has
    left. The requests start together and the rig's card is sampled through the
    poll script every ``LOAD_SAMPLE_S`` until they are all done or ``LOAD_LIMIT_S``
    has passed, at which point whatever is still running has its connections
    closed. The unit's status page is then read until it shows nothing in flight,
    with no limit on that wait and the card sampled beside every reading.

    The ``load`` in the answer carries the prompt and generation sizes, the limit,
    how many requests completed, how many were closed unfinished and the errors,
    the start and finish times, every sample with ``samples_before_close``, the
    container's restart counts before and after, the pace page read at both ends of
    the run with the seconds between them, and the status readings with
    ``idle_after_close``, ``idle_after_s`` and ``idle_error``.

    The engine, port, width, window, container, poll script and pace path come from
    the spec; a width or window below one, a vLLM unit whose listing names no model,
    and a window too small for the long block are HarnessErrors. ``transport``,
    ``fetch``, ``poll``, ``start``, ``clock`` and ``sleep`` are the seams a test
    replaces, so nothing here reaches a rig of its own accord.
    """
    engine = str(spec.get("engine"))
    base = f"http://127.0.0.1:{int(spec['port'])}"
    width = int(spec["width"])
    window = int(spec["window"])
    container = str(spec["container"])
    if width < 1 or window < 1:
        raise HarnessError("a load is at least one request of one token")
    named = spec.get("pace_path")
    pace_path = str(named) if named else None
    script = str(spec.get("poll") or "")
    ask = transport if transport is not None else HttpTransport()
    page = fetch if fetch is not None else _unbounded_page
    begin = start if start is not None else Requests

    def read_rig(*args: str) -> str:
        return poll(*args) if poll is not None else _poll(script, *args)

    model: str | None = None
    if engine == "vllm":
        listing = ask.get(f"{base}/v1/models", None)
        try:
            model = str(listing["data"][0]["id"])
        except (KeyError, IndexError, TypeError) as exc:
            raise HarnessError(f"{base}/v1/models names no model") from exc
    prompt, prompt_tokens = _load_prompt(engine, base, ask, model, window)
    max_tokens = window - prompt_tokens
    if engine == "vllm":
        url = f"{base}/v1/completions"
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": 0,
            "ignore_eos": True,
        }
    else:
        url = f"{base}/completion"
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": 0,
            "ignore_eos": True,
            "cache_prompt": False,
        }

    restarts_before = read_rig("--restarts", container)
    started_at = _now()
    pace_start = page(f"{base}{pace_path}") if pace_path else None
    began = clock()
    batch = begin(url, [dict(payload) for _ in range(width)])
    samples: list[str] = []
    while True:
        samples.append(read_rig("--card-holders"))
        if batch.done() or clock() - began >= LOAD_LIMIT_S:
            break
        sleep(LOAD_SAMPLE_S)
    samples_before_close = len(samples)
    closed = 0 if batch.done() else batch.close()
    ended = clock()
    pace_end = page(f"{base}{pace_path}") if pace_path else None
    status_url = f"{base}{STATUS_PATHS.get(engine, STATUS_PATHS['llama.cpp'])}"
    # The unit's status page, read after the close and then until it shows nothing
    # in flight: what it last said, and the idle verdict and seconds taken from it.
    after_page: str | None = None
    idle_after_close: bool | None = None
    idle_after_s: float | None = None
    idle_error: str | None = None
    readings = 0
    while True:
        # Sample the card beside every status reading, since closing a request does
        # not cancel llama.cpp's work on it. The first reading files
        # idle_after_close, and the wait ends at the first reading that is idle.
        samples.append(read_rig("--card-holders"))
        after_page = page(status_url)
        busy = in_flight(engine, after_page)
        readings += 1
        if busy is None:
            idle_error = f"{status_url} could not be read as a status page"
            break
        if readings == 1:
            idle_after_close = closed == 0 or busy == 0
        if busy == 0:
            idle_after_s = clock() - ended
            break
        sleep(LOAD_SAMPLE_S)
    return {
        "load": {
            "prompt_tokens": prompt_tokens,
            "max_tokens": max_tokens,
            "limit_s": LOAD_LIMIT_S,
            "completed": batch.completed(),
            "closed_unfinished": closed,
            "errors": batch.errors(),
            "started_at": started_at,
            "finished_at": _now(),
            "samples": samples,
            "restarts_before": restarts_before,
            "restarts_after": read_rig("--restarts", container),
            "pace_path": pace_path,
            "pace_start_page": pace_start,
            "pace_end_page": pace_end,
            "pace_seconds": ended - began,
            "after_page": after_page,
            "idle_after_close": idle_after_close,
            "idle_after_s": idle_after_s,
            "idle_error": idle_error,
            "status_readings": readings,
            "samples_before_close": samples_before_close,
            "sampled_until_idle": idle_after_s is not None,
        }
    }


def main(argv: list[str]) -> int:
    """Run one spec and print its answer as JSON: the harness as the rig runs it.

    A spec whose mode is ``load`` is a load, anything else a measurement. Usage is
    the harness word then the spec, so any other argv prints a usage error and
    returns 2. A HarnessError, an unreadable spec or a spec of the wrong shape
    prints an ``error`` object and returns 1; a good answer is printed and
    returns 0.
    """
    if len(argv) != 3 or argv[1] != HARNESS_WORD:
        print(json.dumps({"error": f"usage: python3 - {HARNESS_WORD} SPEC"}))
        return 2
    try:
        spec = json.loads(argv[2])
        answer = load(spec) if spec.get("mode") == "load" else on_the_rig(spec)
    except (HarnessError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps(answer))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
