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

import json
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Protocol

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
#: A load leaves this many tokens of each window to generation and fills the rest
#: with prompt: the window is full either way, and a prompt fills it fastest.
LOAD_OUTPUT_TOKENS = 64
#: How often a load samples the unit's container on the card while it runs.
LOAD_SAMPLE_S = 0.5


class HarnessError(Exception):
    """One unit's measurement could not be taken."""


class Transport(Protocol):
    """JSON over HTTP to a unit's address."""

    def get(self, url: str, timeout: float) -> Any:
        """The JSON document at ``url``."""

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> Any:
        """The JSON answer to ``payload`` posted at ``url``."""


class HttpTransport:
    """The harnesses' own requests, sent to a unit's address with ``urllib``."""

    def get(self, url: str, timeout: float) -> Any:
        """The JSON document at ``url``."""
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> Any:
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


def measure_vllm(
    address: str, transport: Transport, clock: Callable[[], float]
) -> dict[str, float]:
    """``measure_vllm.py``'s decode and prefill, asked of the unit at ``address``."""
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

    return {
        "warm_decode_tok_s": _median(decode, "decode"),
        "prefill_tok_s": _median(prefill, "prefill"),
    }


def measure_llamacpp(address: str, transport: Transport) -> dict[str, float]:
    """``harness_llama.py``'s decode and prefill, asked of the unit at ``address``."""
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
    return {
        "warm_decode_tok_s": _median(decode, "decode"),
        "prefill_tok_s": _median(prefill, "prefill"),
    }


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
        figures = measure_vllm(address, transport, time.perf_counter)
    else:
        figures = measure_llamacpp(address, transport)
    path = STATUS_PATHS.get(engine, STATUS_PATHS["llama.cpp"])
    return {"figures": figures, "after_page": _page(f"{address}{path}")}


def _now() -> str:
    # timezone.utc, not datetime.UTC (3.11+): this file runs on the rig's own
    # python3, which the module docstring holds to 3.8.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")  # noqa: UP017


def _tokens(
    engine: str, base: str, transport: Transport, model: str | None, text: str
) -> int:
    """How many tokens the unit's own tokenizer makes of ``text``."""
    if engine == "vllm":
        body = transport.post(
            f"{base}/tokenize", {"model": model, "prompt": text}, MODELS_TIMEOUT_S
        )
        count = body.get("count") if isinstance(body, Mapping) else None
    else:
        body = transport.post(
            f"{base}/tokenize", {"content": text, "add_special": True}, MODELS_TIMEOUT_S
        )
        tokens = body.get("tokens") if isinstance(body, Mapping) else None
        count = len(tokens) if isinstance(tokens, list) else None
    if isinstance(count, bool) or not isinstance(count, int):
        raise HarnessError(f"{base}/tokenize gave no token count")
    return count


def _load_prompt(
    engine: str, base: str, transport: Transport, model: str | None, window: int
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
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout if done.returncode == 0 else ""


def load(spec: Mapping[str, Any]) -> dict[str, Any]:
    """W concurrent requests filling the unit's N-token window, its card sampled.

    Owner, 2026-09-15 (B1). ``spec`` is ``{"mode": "load", "engine", "port",
    "width": W, "window": N, "container": ID, "poll": <rig-units.sh>}``. Each
    request's prompt is the long block counted by the unit's own tokenizer, and
    its ``max_tokens`` is the rest of the window, generated to the end. While the
    requests run, ``rig-units.sh --card-holders`` is sampled as it prints, for
    the door to read with the parser a read uses; the container's restart
    count is read before and after.
    """
    engine = str(spec.get("engine"))
    base = f"http://127.0.0.1:{int(spec['port'])}"
    width = int(spec["width"])
    window = int(spec["window"])
    container = str(spec["container"])
    poll = str(spec["poll"])
    if width < 1 or window < 1:
        raise HarnessError("a load is at least one request of one token")
    transport = HttpTransport()
    model: str | None = None
    if engine == "vllm":
        listing = transport.get(f"{base}/v1/models", MODELS_TIMEOUT_S)
        try:
            model = str(listing["data"][0]["id"])
        except (KeyError, IndexError, TypeError) as exc:
            raise HarnessError(f"{base}/v1/models names no model") from exc
    prompt, prompt_tokens = _load_prompt(engine, base, transport, model, window)
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
    completed: list[int] = []
    errors: list[str] = []
    guard = threading.Lock()

    def one() -> None:
        try:
            transport.post(url, dict(payload), REQUEST_TIMEOUT_S)
        except (OSError, ValueError) as exc:
            with guard:
                errors.append(f"{type(exc).__name__}: {exc}")
            return
        with guard:
            completed.append(1)

    restarts_before = _poll(poll, "--restarts", container)
    started_at = _now()
    threads = [threading.Thread(target=one, daemon=True) for _ in range(width)]
    for thread in threads:
        thread.start()
    samples: list[str] = []
    while any(thread.is_alive() for thread in threads):
        samples.append(_poll(poll, "--card-holders"))
        time.sleep(LOAD_SAMPLE_S)
    for thread in threads:
        thread.join()
    return {
        "load": {
            "prompt_tokens": prompt_tokens,
            "max_tokens": max_tokens,
            "completed": len(completed),
            "errors": errors,
            "started_at": started_at,
            "finished_at": _now(),
            "samples": samples,
            "restarts_before": restarts_before,
            "restarts_after": _poll(poll, "--restarts", container),
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
