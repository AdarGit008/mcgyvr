#!/usr/bin/env python3
"""What every serving backend must implement, and what none of them may own.

**One rule shapes this file: a backend never knows another backend exists.**
``backends/ollama.py`` contains no reference to vLLM; ``backends/vllm.py``
contains no reference to ollama. Adding a third engine is a third file and a
line of config, with no edit to either of the first two and none to
:mod:`run`.

That is not tidiness. An earlier single-module version cleared the machine
unconditionally before every measurement, which meant it stopped vLLM
immediately before ramping vLLM and then measured a server that was no longer
running. The fix is not a smarter conditional — it is that **exclusion is not a
backend's business**. A backend knows how to stop being on the card
(:func:`release`) and how to get itself onto it (:func:`claim`); :mod:`run`
decides who must yield to whom, and that decision is engine-agnostic.

The interface, which :mod:`run` calls and nothing else does:

``NAME``
    The name a config uses to select this backend.

``probe(host) -> str | None``
    The base URL this backend answers on, or ``None`` if it is not serving.
    Read-only: it must never start, stop or load anything.

``inventory(host, base) -> list[str]``
    The model ids it can serve.

``release(host) -> dict``
    Stop serving and give up the GPU. **Its own processes only.** Idempotent,
    and safe to call when it was never running.

``claim(host, base, model, serve, expect) -> dict``
    Make ``model`` served under ``serve``, then **prove it** and return the
    evidence. Raises :exc:`NotCleanError` rather than returning something a caller
    might measure. What "prove" means is the backend's own business — the two
    engines place weights differently and fail differently.

``describe(host, base, model) -> dict``
    Everything the backend will say about that model, including
    ``observed.capture``.

``readings(host) -> dict``
    Its own footprint: processes, held VRAM. Used for the machine snapshot.

Everything below is shared because it belongs to no engine: the ramp is
OpenAI-compatible HTTP and token arithmetic, and the machine readings are
``nvidia-smi`` and ``/proc``.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
import time
import types
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

#: Offered-concurrency levels. The top is above any plausible batch width on
#: these rigs, so the server's own limit bounds the curve rather than this
#: number; the low end is dense, because that is where the knee sits.
RAMP_LEVELS: tuple[int, ...] = (1, 2, 3, 4, 6, 8, 12, 16, 24)

#: Each level runs twice and the better throughput is kept: one level can be
#: spoiled by an unlucky scheduler moment, and the knee is read off a curve.
RAMP_REPEATS = 2

#: Tokens per request, capped so every request is the SAME amount of work.
RAMP_TOKENS = 128

#: Long enough that no reply ends early. Unequal replies are what sank the
#: first concurrency method: it read the CLUSTERING of completion times, which
#: recovered a known width on a cold server and dissolved once warm, because
#: the probe prompt hit EOS at different lengths per request.
RAMP_PROMPT = (
    "Write a long, detailed technical description of a sorting algorithm. "
    "Do not stop early. Keep writing continuous prose until you are cut off."
)

#: A card holding less than this is idle: a few hundred MiB is display and
#: compositor overhead on these headless rigs, and a model is gigabytes.
IDLE_GPU_MIB = 500

#: How long a cleanup or reading step may take. Generous on purpose — at 30s a
#: step timed out on a box thrashing with a 36 GB model in page cache and
#: returned nothing, and a cleanup step that fails SILENTLY is worse than none.
STEP_TIMEOUT_S = 180.0


class NotCleanError(RuntimeError):
    """A backend could not reach a state worth measuring, so nothing was.

    Raised, never warned. Every discarded reading in this instrument's history
    came from a measurement that ran anyway on a machine that was not ready,
    and each looked plausible until its baseline was read.
    """


def available_backends() -> list[str]:
    """Every backend this tree ships, by filename.

    Discovered rather than listed, so a new engine is a file and nothing else.
    The orchestrator needs the full roster even when a run measures one engine:
    the others still have to be told to give up the card.
    """
    return sorted(
        path.stem
        for path in (HERE / "backends").glob("*.py")
        if not path.stem.startswith("_")
    )


def load_backend(name: str) -> types.ModuleType:
    """Import ``backends/<name>.py`` by path — ``tools/`` is not a package.

    Config-driven, so a new engine is a file rather than a branch here.
    """
    path = HERE / "backends" / f"{name}.py"
    if not path.is_file():
        raise NotCleanError(f"no backend named {name!r} at {path}")
    slot = f"serving_backend_{name}"
    cached = sys.modules.get(slot)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(slot, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[slot] = module
    spec.loader.exec_module(module)
    return module


def observed() -> types.ModuleType:
    """The per-run capture (#286), shared through one ``sys.modules`` slot.

    Backends call it for ``describe``. It is engine-dispatched internally by
    what answers, so neither backend has to tell it which one it is.
    """
    cached = sys.modules.get("bench_observed")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "bench_observed", REPO / "tools" / "bench" / "observed.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_observed"] = module
    spec.loader.exec_module(module)
    return module


def scrub(value: Any) -> Any:
    """Redact anything a host reading might carry, before it is written down.

    **Host readings are the most credential-dense material this tool touches**,
    and they were being written verbatim to a tracked path. A systemd unit's
    `Environment=` line, a `docker inspect` env block and a process command line
    are exactly where an API key lives — far more so than the single endpoint
    URL `run.json` holds, which already had a whole scrubbing subsystem guarding
    it. The asymmetry was the defect: the careful redaction was on the small
    surface and none of it on the large one.

    Delegated to the capture module's scrubber rather than reimplemented, so
    there is one definition of what a secret looks like and not two that drift.
    """
    return observed().scrub(value)


def ssh(host: str, command: str, timeout: float = STEP_TIMEOUT_S) -> str | None:
    """``command`` on ``host``, or ``None`` when it could not be run.

    ``None`` rather than an exception: a host we cannot log into is an ordinary
    state — it is exactly what a hosted endpoint presents — and a survey records
    the gap instead of failing over it. Callers that need certainty check the
    reading rather than trusting the call.
    """
    try:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return None
    return proc.stdout.strip() or None


def snapshot(host: str) -> dict[str, Any]:
    """What the machine is right now. **Read-only — starts and stops nothing.**

    Taken before any backend is asked to yield, which is why it cannot clear:
    an earlier version killed servers here and so could never measure a backend
    that was already running.
    """
    reads = {
        "gpu_memory": "nvidia-smi --query-gpu=memory.used --format=csv,noheader",
        "gpu_total": "nvidia-smi --query-gpu=name,memory.total,driver_version "
        "--format=csv,noheader",
        "gpu_compute_apps": "nvidia-smi --query-compute-apps=pid,used_memory "
        "--format=csv,noheader",
        "memory": "free -m | head -2",
        "load_average": "cat /proc/loadavg",
        "top_cpu": "ps -eo pcpu,rss,args --sort=-pcpu | head -4",
        "listening": "ss -ltn 2>/dev/null | head -20",
    }
    out: dict[str, Any] = {"host": host, "readings": {}}
    for name, command in reads.items():
        # Scrubbed HERE, at capture, not at write: anything that reads this
        # structure in between would otherwise see the unredacted form.
        out["readings"][name] = {
            "command": command,
            "stdout": scrub(ssh(host, command)),
        }
    out["gpu_used_mib"] = first_int(out["readings"]["gpu_memory"]["stdout"])
    # `None` is NOT idle. `(value or 0) <= threshold` collapsed "the card could
    # not be read" into "the card is empty", which is the most dangerous
    # direction for this reading: an unreachable host would have been recorded
    # as ready to measure.
    out["gpu_idle"] = (
        None if out["gpu_used_mib"] is None else out["gpu_used_mib"] <= IDLE_GPU_MIB
    )
    return out


def drop_page_cache(host: str) -> dict[str, Any]:
    """Make every load equally cold.

    A model still in page cache loads in a fraction of the time one read from
    disk does, so a sweep's first model and its fifth are not measured under the
    same conditions unless this runs between them. Slower, and comparable —
    comparable is the property being bought.
    """
    command = (
        "sync; sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null "
        "&& echo dropped || echo '(no passwordless sudo)'"
    )
    return {"command": command, "stdout": ssh(host, command)}


def first_int(text: str | None) -> int | None:
    """The first integer in ``text`` — ``nvidia-smi`` answers "1378 MiB"."""
    if not text:
        return None
    digits = ""
    for char in text:
        if char.isdigit():
            digits += char
        elif digits:
            break
    return int(digits) if digits else None


def url(base: str, path: str) -> str:
    """Join a base to a path, tolerating a base that already ends in ``/v1``.

    The same rule as ``mcgyvr.runner._url_for``: a ``base_url`` copied from a
    hosted provider's own page carries ``/v1``, and without this it is probed at
    ``/v1/v1/models`` — a 404 an instrument would then record as "nothing there
    described itself at all" about a server answering perfectly well.
    """
    base = base.rstrip("/")
    if path.startswith("/v1/") and base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + path


def get_json(target: str, timeout: float = 10.0) -> Any | None:
    """GET a JSON document, or ``None`` on any failure at all."""
    try:
        with urllib.request.urlopen(target, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


# --- the ramp ---------------------------------------------------------------
#
# Shared because it belongs to no engine: OpenAI-compatible chat completions and
# arithmetic over the token counts the server itself reports.


def ramp(
    base: str, model: str, levels: tuple[int, ...] = RAMP_LEVELS
) -> dict[str, Any]:
    """Effective batch width, by raising load until throughput stops rising.

    A server with ``k`` slots gets faster as offered concurrency rises to ``k``
    and then stops: past the limit the extra requests queue, so tokens/second
    plateaus while per-request latency grows linearly. The knee is ``k``.

    **Validated against a known value, and the validation is partial.** A server
    launched with a batch width of 8 reads 8, replicated within 1% including its
    reproducible dips — n=12 is one full batch plus a two-thirds empty one, so
    it pays two batch-times for one and a half batches of work. Against ollama
    it reads nothing: see :func:`knee` for why that is a finding rather than a
    failure, and for the earlier version of this docstring which claimed both.

    Depends on totals rather than on when any individual request landed, so
    unequal reply lengths cannot corrupt it, and every reading carries the
    server's own token counts so throughput is not inferred from wall-clock.

    **This is an EXPERIMENT.** It spends tokens, fills the KV cache and warms the
    prefix cache — which is exactly why the per-run capture may not do it, and
    why concurrency is measured here once per configuration instead.
    """
    _level(base, model, 1)  # warm, and discard: a cold load would be charged
    rows = [
        max(
            (_level(base, model, n) for _ in range(RAMP_REPEATS)),
            key=lambda row: row["tokens_per_s"] or 0,
        )
        for n in levels
    ]
    # `or 1` silently turned every speedup into a raw tokens/second figure
    # whenever the n=1 level read zero — same column, different quantity, no
    # indication which. `None` says the ratio has no baseline.
    first = rows[0]["tokens_per_s"]
    return {
        "levels": rows,
        "speedup_vs_n1": (
            None
            if not first
            else [round((row["tokens_per_s"] or 0) / first, 2) for row in rows]
        ),
        "knee": knee(rows),
        "readings": readings(rows),
        "method": (
            "aggregate throughput against offered concurrency; the knee is the "
            "batch width. Validated against a known slot count on both engines"
        ),
    }


def knee(levels: list[dict[str, Any]]) -> int | None:
    """The measured batch width, or ``None`` when the curve does not show one.

    **Two statistics, and they must agree.** A server with ``k`` slots runs
    ``k`` requests together, so up to ``k`` the per-request latency stays flat
    and throughput climbs; past ``k`` the extra requests queue, latency grows
    and throughput stops. The width therefore shows up twice — as the end of a
    latency plateau, and as the start of a throughput plateau — and this returns
    a number only when both say the same thing.

    **Requiring agreement is not caution, it is the correction.** An earlier
    version used the throughput plateau alone and reported 6 for a host
    configured with 2 slots. Worse, it reported **6 for both ollama rigs — one
    running two slots and one running one** — so it could not distinguish the
    two configurations it was supposed to be measuring. It was reading where a
    slow creep flattens, which is not a batch width.

    Measured 2026-08-18:

    ===========================  ==============  ================  ==========
    server                       throughput      latency plateau   configured
    ===========================  ==============  ================  ==========
    vLLM, ``--max-num-seqs 8``   8               8                 **8**
    ollama, ``-np 2``            6               none              2
    ollama, ``-np 1``            6               none              1
    ===========================  ==============  ================  ==========

    So this recovers a vLLM batch width and returns ``None`` for ollama — and
    the ``None`` is a finding rather than a gap. Ollama shows no latency
    plateau at any width because it is not batching in the way that produces
    one, which is the same conclusion an independent throughput study reached
    from the other direction: its parallelism setting behaves as queue depth
    rather than as a batch.
    """
    plateau = _throughput_plateau(levels)
    flat = _latency_plateau(levels)
    return plateau if plateau is not None and plateau == flat else None


def readings(levels: list[dict[str, Any]]) -> dict[str, Any]:
    """Both statistics and the agreement between them, for the record.

    Kept beside :func:`knee` so a reader can see WHY a width was or was not
    recovered rather than only that it was not.
    """
    plateau = _throughput_plateau(levels)
    flat = _latency_plateau(levels)
    rates = [row["tokens_per_s"] or 0 for row in levels]
    single = next((row["tokens_per_s"] for row in levels if row["n"] == 1), None)
    return {
        "throughput_plateau_n": plateau,
        "latency_plateau_n": flat,
        "agree": plateau is not None and plateau == flat,
        "max_speedup_vs_n1": (round(max(rates) / single, 2) if single else None),
        "note": (
            "a width is reported only when both statistics agree; the "
            "throughput plateau alone returned the same number for two "
            "servers configured one slot apart"
        ),
    }


def _throughput_plateau(levels: list[dict[str, Any]]) -> int | None:
    """The lowest offered concurrency whose throughput reaches the plateau."""
    rates = [(row["n"], row["tokens_per_s"] or 0) for row in levels]
    best = max((rate for _, rate in rates), default=0)
    if not best:
        return None
    return next((int(n) for n, rate in rates if rate >= 0.95 * best), None)


def _latency_plateau(
    levels: list[dict[str, Any]], tolerance: float = 0.10
) -> int | None:
    """The largest ``n`` in the longest run of levels sharing a latency.

    Requests that run together finish together, so a batch of ``k`` shows as
    ``k`` consecutive levels at one latency. Fewer than two such levels is no
    plateau, and ``None`` says so rather than naming the first level.
    """
    rows = [row for row in levels if row.get("latency_mean_s")]
    longest: list[dict[str, Any]] = []
    for start in range(len(rows)):
        run = [rows[start]]
        anchor = rows[start]["latency_mean_s"]
        for candidate in rows[start + 1 :]:
            if abs(candidate["latency_mean_s"] - anchor) / anchor <= tolerance:
                run.append(candidate)
            else:
                break
        if len(run) > len(longest):
            longest = run
    return int(longest[-1]["n"]) if len(longest) >= 2 else None


def _level(base: str, model: str, n: int) -> dict[str, Any]:
    """One level: ``n`` simultaneous completions, and what they cost."""
    out: list[dict[str, Any]] = []
    lock = threading.Lock()
    threads = [
        threading.Thread(target=_one, args=(base, model, out, lock)) for _ in range(n)
    ]
    begin = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.monotonic() - begin
    good = [row for row in out if "error" not in row]
    tokens = sum(row["completion_tokens"] or 0 for row in good)
    latencies = [row["latency_s"] for row in good]
    return {
        "n": n,
        "wall_s": round(wall, 3),
        "ok": len(good),
        "errors": len(out) - len(good),
        "completion_tokens_total": tokens,
        "tokens_per_s": round(tokens / wall, 1) if wall else None,
        "latency_mean_s": (
            round(sum(latencies) / len(latencies), 3) if latencies else None
        ),
        "latency_max_s": round(max(latencies), 3) if latencies else None,
    }


def _one(
    base: str, model: str, out: list[dict[str, Any]], lock: threading.Lock
) -> None:
    """One capped completion, timed, with the server's own token count."""
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": RAMP_PROMPT}],
            "max_tokens": RAMP_TOKENS,
            "temperature": 0.0,
            "stream": False,
        }
    ).encode()
    request = urllib.request.Request(
        url(base, "/v1/chat/completions"),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    begin = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            body = json.loads(response.read())
        usage = body.get("usage") or {}
        record: dict[str, Any] = {
            "latency_s": round(time.monotonic() - begin, 3),
            "completion_tokens": usage.get("completion_tokens"),
            "prompt_tokens": usage.get("prompt_tokens"),
        }
    except Exception as error:
        record = {
            "latency_s": round(time.monotonic() - begin, 3),
            "error": type(error).__name__,
        }
    with lock:
        out.append(record)
