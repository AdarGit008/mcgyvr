"""The lock's own measurement of a unit, in one module the rig can run as it is.

``records/measurements/fleet-setup-2026-09-13/srv2/measure_vllm.py`` and
``records/measurements/fleet-setup-2026-09-13/srv1/harness_llama.py`` measured
the numbers the fleet lock holds. This is their method, once:

* vLLM: one 64-token warm-up, five 256-token decodes with ``ignore_eos``
  (``completion_tokens`` over wall seconds) and three 16-token requests of the
  long prompt (``prompt_tokens`` over wall seconds);
* llama.cpp: ``/completion`` with a 64-token warm-up, five 256-token decodes read
  from ``timings.predicted_per_second`` and three 16-token long prompts read from
  ``timings.prompt_per_second``, with ``cache_prompt`` off.

Both take the median. :mod:`mcgyvr.fleet.probe` asks it of a unit at its
address. ``python -m mcgyvr.serving.run read --probe`` ships this very file to
the rig as ``python3 - mcgyvr-harness SPEC`` and runs it at 127.0.0.1, where the
lock's wall clock ran (owner, 2026-09-15: "vLLM stopwatch on the rig"). So it
imports the standard library and nothing else, and runs on any Python 3.8 a rig
has: the rig has no mcgyvr to import.
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

#: The word the door's ``read --probe`` names this harness by on the rig.
HARNESS_WORD = "mcgyvr-harness"

_SHORT_TEXT = "Write a Python function that reverses a singly linked list in place.\n"
_LONG_BLOCK = (
    "You are a precise software engineer. Explain step by step how to compute "
    "the size in bytes of every expert weight in a GGUF file, then write a "
    "Python function that opens the file, walks the metadata, and prints a "
    "table of tensor name, shape, and byte size for every tensor that has an "
    "expert dimension. Be complete and correct.\n\n"
)
#: ``measure_vllm.py``'s ``SHORT`` and ``LONG``, as written there.
VLLM_SHORT: list[dict[str, str]] = [{"role": "user", "content": _SHORT_TEXT}]
VLLM_LONG = _LONG_BLOCK * 28
#: ``harness_llama.py``'s ``SHORT_PROMPT`` and ``LONG_PROMPT``, as written there.
LLAMA_SHORT_PROMPT = _SHORT_TEXT
LLAMA_LONG_PROMPT = (_LONG_BLOCK * 28).strip()

WARMUP_TOKENS = 64
DECODE_TOKENS = 256
PREFILL_TOKENS = 16
DECODE_SAMPLES = 5
PREFILL_SAMPLES = 3
#: The harnesses' own request timeouts: 10 s for the model list, 900 s a sample.
MODELS_TIMEOUT_S = 10.0
REQUEST_TIMEOUT_S = 900.0
#: Where each engine publishes what it has in flight, read after a measurement.
STATUS_PATHS = {"vllm": "/metrics", "llama.cpp": "/slots"}
#: The two gauges vLLM's ``/metrics`` counts a unit's requests in flight by.
VLLM_RUNNING = "vllm:num_requests_running"
VLLM_WAITING = "vllm:num_requests_waiting"
#: A load leaves this many tokens of each window to generation and fills the rest
#: with prompt: the window is full either way, and a prompt fills it fastest.
LOAD_OUTPUT_TOKENS = 64
#: How often a load samples the unit's container on the card while it runs.
LOAD_SAMPLE_S = 0.5
#: How long a load runs from when its requests start (owner ruling NB5, "measure
#: pace for 30 seconds then verdict"): at this many seconds every unfinished
#: request's connection is closed. It is the only limit a load is held to.
LOAD_LIMIT_S = 30


class HarnessError(Exception):
    """One unit's measurement could not be taken."""


class Transport(Protocol):
    """JSON over HTTP to a unit's address."""

    def get(self, url: str, timeout: float) -> Any:
        """The JSON document at ``url``."""

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> Any:
        """The JSON answer to ``payload`` posted at ``url``."""


class LoadTransport(Protocol):
    """JSON over HTTP to a unit's address, with no timeout a load does not set.

    A load is held to ``LOAD_LIMIT_S`` and no other number (owner ruling NB5), so
    its model list and tokenize calls pass ``timeout=None``; the probes keep
    :class:`Transport`'s.
    """

    def get(self, url: str, timeout: float | None) -> Any:
        """The JSON document at ``url``."""

    def post(self, url: str, payload: dict[str, Any], timeout: float | None) -> Any:
        """The JSON answer to ``payload`` posted at ``url``."""


class HttpTransport:
    """The harnesses' own requests, sent to a unit's address with ``urllib``."""

    def get(self, url: str, timeout: float | None) -> Any:
        """The JSON document at ``url``."""
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, url: str, payload: dict[str, Any], timeout: float | None) -> Any:
        """The JSON answer to ``payload`` posted at ``url``."""
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))


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
    """``measure_vllm.py``'s decode and prefill, asked of the unit at ``address``.

    With ``with_samples``, every sample is kept beside its median, in the order
    taken (owner ruling N7): ``decode_samples`` and ``prefill_samples``.
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
    """``harness_llama.py``'s decode and prefill, asked of the unit at ``address``.

    With ``with_samples``, every sample is kept beside its median, in the order
    taken (owner ruling N7): ``decode_samples`` and ``prefill_samples``.
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
    try:
        with urllib.request.urlopen(url, timeout=MODELS_TIMEOUT_S) as response:
            text: str = response.read().decode("utf-8", "replace")
            return text
    except (OSError, ValueError):
        return None


def on_the_rig(spec: Mapping[str, Any]) -> dict[str, Any]:
    """The lock's measurement of the unit at ``127.0.0.1:<port>``, then its status.

    ``spec`` is ``{"engine": "vllm" | "llama.cpp", "port": N}``. The status page
    is read after the measurement so the door can tell a unit that took work
    during it from one that did not; before it, the door read it already.
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
    # timezone.utc, not datetime.UTC (3.11+): this file runs on the rig's own
    # python3, which the module docstring holds to 3.8.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")  # noqa: UP017


def _tokens(
    engine: str, base: str, transport: LoadTransport, model: str | None, text: str
) -> int:
    """How many tokens the unit's own tokenizer makes of ``text``."""
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
    """The long block, repeated to leave ``LOAD_OUTPUT_TOKENS`` of the window."""
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
    """``rig-units.sh`` run on this rig in one of its single-reading modes."""
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
    """A page read with no timeout: a load is held to its own limit and no other."""
    try:
        with urllib.request.urlopen(url) as response:
            text: str = response.read().decode("utf-8", "replace")
            return text
    except (OSError, ValueError):
        return None


def prometheus_totals(
    page: str | None, names: tuple[str, ...]
) -> dict[str, float] | None:
    """The named samples in a Prometheus text page, summed over label sets.

    Summed, so a server naming its model or engine in the labels still reads
    as one series. ``None`` for a missing page or a sample whose value is not a
    number; a name that is simply absent is absent from the result. The one reader
    of such a page: the runner reads a unit's page beside a dispatch with it, and
    a load reads it here, on the rig (owner ruling NBc).
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
    """One named sample on a Prometheus page, summed over label sets, or ``None``."""
    totals = prometheus_totals(page, (name,))
    return None if totals is None else totals.get(name)


def slots_in_flight(page: str | None) -> int | None:
    """llama-server's ``/slots``: how many slots are ``is_processing``, or ``None``.

    ``None`` for anything that is not a non-empty list of slots each saying
    ``is_processing`` as a boolean — a disabled endpoint answers an error
    object, and a half-read list is not a count.
    """
    if page is None:
        return None
    try:
        slots = json.loads(page)
    except ValueError:
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
    """vLLM's ``/metrics``: requests running plus waiting, ``None`` without both."""
    totals = prometheus_totals(page, (VLLM_RUNNING, VLLM_WAITING))
    if totals is None or VLLM_RUNNING not in totals or VLLM_WAITING not in totals:
        return None
    return int(totals[VLLM_RUNNING] + totals[VLLM_WAITING])


def in_flight(engine: str | None, page: str | None) -> int | None:
    """What a unit's own status page says it has in flight, read by its engine."""
    return vllm_in_flight(page) if engine == "vllm" else slots_in_flight(page)


class Batch(Protocol):
    """A load's requests, running: finished or not, counted, closed at the limit."""

    def done(self) -> bool:
        """Whether no request is still running."""

    def completed(self) -> int:
        """How many requests the unit answered."""

    def errors(self) -> list[str]:
        """What failed, other than the load's own close."""

    def close(self) -> int:
        """Close every unfinished request's connection; how many it closed."""


class Requests:
    """W requests, each on an ``http.client`` connection of its own, with no timeout.

    A load is held to ``LOAD_LIMIT_S`` and no other number. At that limit
    :meth:`close` shuts each unfinished connection's socket, which ends the read
    its thread is blocked in; a failure that follows the close is the close, not
    an error. Whether the unit then stops the work is the engine's to do, and the
    load reads the unit's status page afterwards to see.
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
        # One connection per request, paired as it is made: no zip(strict=),
        # which this file cannot use on the rig's Python 3.8.
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
    """W concurrent requests filling the unit's N-token window, for at most 30 s.

    Owner rulings B1 and NB5, 2026-09-15. ``spec`` is ``{"mode": "load",
    "engine", "port", "width": W, "window": N, "container": ID, "poll":
    <rig-units.sh>, "pace_path": <page> | None}``.

    * Each request's prompt is the long block counted by the unit's own
      tokenizer, up to ``N - LOAD_OUTPUT_TOKENS``, and its ``max_tokens`` is the
      rest of the window.
    * ``rig-units.sh --card-holders`` is sampled every ``LOAD_SAMPLE_S`` until
      every request has finished or ``LOAD_LIMIT_S`` has passed since they
      started; then every unfinished request's connection is closed.
    * The pace counter page (``pace_path``) is read just before the requests
      start and again once they have ended, with the seconds between.
    * Then the unit's own status page is read every ``LOAD_SAMPLE_S`` until the
      unit reads idle, with no time limit on the wait (owner ruling NBc); a page
      that cannot be read ends it. ``idle_after_close`` says whether the first
      reading was already idle, and ``idle_after_s`` how long idle took.
    * The card is sampled beside every one of those readings too (owner ruling,
      2026-09-15: "Sample the card until idle"): ``samples`` holds every sample,
      the first ``samples_before_close`` taken before the close, and
      ``sampled_until_idle`` says whether they run through to an idle reading.
    * Nothing here has a timeout but ``LOAD_LIMIT_S``.

    ``transport``, ``fetch``, ``poll``, ``start``, ``clock`` and ``sleep`` stand in
    for the unit, its pages, the rig's poll, the requests, the time and the wait.
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
    # Owner ruling NBc: read the unit's own status page until it reads idle, with
    # no time limit on the wait. A page that cannot be read at all ends it.
    after_page: str | None = None
    idle_after_close: bool | None = None
    idle_after_s: float | None = None
    idle_error: str | None = None
    readings = 0
    while True:
        # Owner ruling, 2026-09-15: "Sample the card until idle". A close does not
        # cancel the unit's work (``records/measurements/lock-fleets``), so the
        # card is sampled beside every status reading, the idle one included.
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
    """``python3 - mcgyvr-harness SPEC``: one JSON line on stdout, always."""
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
