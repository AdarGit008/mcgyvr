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

``describe(host, base, model, serve=None) -> dict``
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
#:
#: **D3, 2026-08-19.** 128 was too short to be a throughput measurement: at that
#: length the per-request fixed costs — scheduling, prefill, the first token —
#: are a large share of the reply, so the curve reads the overhead as much as
#: the rate. 475 was chosen from the measured matrix as the point where the
#: plateau is stable and the run still fits the campaign's budget; it is a
#: judgement against measured curves, not a derived constant.
#:
#: One model on the roster spends this budget differently. ``gpt-oss:20b``
#: emits hidden ``reasoning_content`` — roughly half the output even at low
#: reasoning — so its ``completion_tokens`` counts reasoning tokens and 475
#: buys about half that in visible text. Throughput is still throughput; the
#: quantity simply is not comparable to another model's visible-token rate.
RAMP_TOKENS = 475

#: Long enough that no reply ends early. Unequal replies are what sank the
#: first concurrency method: it read the CLUSTERING of completion times, which
#: recovered a known width on a cold server and dissolved once warm, because
#: the probe prompt hit EOS at different lengths per request.
RAMP_PROMPT = (
    "Write a long, detailed technical description of a sorting algorithm. "
    "Do not stop early. Keep writing continuous prose until you are cut off."
)

#: **The definition of** :func:`saturation_n`, not a tolerance around it.
#:
#: ``saturation_n`` is the lowest offered concurrency whose throughput reaches
#: this fraction of the curve's peak. There is no separate ground truth it is
#: approximating — a throughput curve does not contain a "true" saturation
#: point that this rounds to. Changing this number changes what the field
#: means, so it is stated once, here, and every emitted value carries it.
#:
#: **D2, 2026-08-19.** 0.92 rather than the previous inline 0.95: at 0.95 a
#: curve that is still creeping upward by a percent or two per level reads its
#: saturation point later than the hardware reaches it.
PLATEAU_FRACTION = 0.92

#: Informational only — reported beside the latency plateau, never a gate.
#:
#: Kept because the disagreement between the two plateaus is itself readable:
#: on a wide server they differ by design, since a larger batch is slower per
#: request before any queueing starts. A reader who saw only one could not tell
#: that from a broken measurement.
LATENCY_TOLERANCE = 0.10

#: The floor for **inferring** a saturation point, and it applies to nothing
#: else.
#:
#: **D1, 2026-08-19.** Formerly ``BATCHING_SPEEDUP = 2.0``, which was used to
#: decide whether a server "batches" and, through that, to suppress its width
#: entirely. Recomputed from ``samples.jsonl`` at 512 tokens: a ``> 1.0`` gate
#: reads four of five vLLM widths correctly and declines the fifth with **no
#: wrong answer**, where 2.0 suppresses three correct ones. The 2.0 threshold
#: was separating vLLM at 4 from ollama at 2 — and that is not the job. A
#: declared limit and an inferred saturation point are different quantities
#: and are now different fields; this constant governs only the inferred one.
#:
#: At 1.0 it excludes exactly the degenerate case: a curve whose peak never
#: exceeds its own single-request rate has no rise, so nothing about it can be
#: called a saturation point.
INFERRED_SATURATION_MIN_SPEEDUP = 1.0

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
        "saturation": saturation(rows),
        "readings": readings(rows),
        "method": (
            "aggregate throughput against offered concurrency. The lowest level "
            "reaching PLATEAU_FRACTION of peak is the SATURATION POINT, which "
            "is a property of this host under this load — not a slot count, and "
            "not comparable across token budgets"
        ),
    }


def saturation(levels: list[dict[str, Any]]) -> dict[str, Any]:
    """Where this host's throughput stops rising — **not** its slot count.

    **D1, 2026-08-19: a throughput plateau is not a slot limit.** A scheduler
    limit (``--max-num-seqs``, ``-np``) and a throughput saturation point
    coincide only when the limit binds before the hardware does. This lane
    measured the divergence directly: ollama on srv2 with ``-np 1`` reads a
    plateau of **2** at 512 tokens. One field cannot hold both quantities, so
    it no longer tries — ``declared_slots`` is what the server says, supplied by
    the backend, and this is what the curve does.

    Measured 2026-08-19 across four configurations:

    ==========================  ==================  ==============  ==========
    server                      throughput plateau  max speedup     declared
    ==========================  ==================  ==============  ==========
    vLLM ``--max-num-seqs 8``   8                   2.52            8
    vLLM ``--max-num-seqs 16``  16                  3.94            16
    ollama ``-np 2``            6                   1.71            2
    ollama ``-np 1``            6                   —               1
    ==========================  ==================  ==============  ==========

    The two right-hand columns agree on the engine that batches and disagree on
    the one that does not. Reporting them separately is the whole fix; the old
    ``batches`` boolean, which tried to say which column to believe, is retired.

    **The value is meaningless without its conditions**, so every result carries
    them: the token budget it was measured at and the plateau fraction that
    defines it. A saturation point at 128 tokens and one at 475 are different
    measurements of different things.

    **Levels that did not fully succeed are excluded, not averaged in.** A level
    whose requests partly failed produces a *lower* throughput — which reads as
    "the curve flattened here", i.e. a wrong saturation point rather than a
    refusal. This was live: nothing downstream read the ``errors`` count.
    """
    clean = [row for row in levels if not row.get("errors") and row.get("counted")]
    dropped = [
        {
            "n": row["n"],
            "errors": row.get("errors", 0),
            "uncounted": row.get("ok", 0) - row.get("counted", 0),
        }
        for row in levels
        if row.get("errors") or not row.get("counted")
    ]
    conditions = {
        "ramp_tokens": RAMP_TOKENS,
        "plateau_fraction": PLATEAU_FRACTION,
        "levels_offered": [row["n"] for row in levels],
        "levels_used": [row["n"] for row in clean],
        "levels_dropped": dropped,
    }
    if not clean:
        return {
            "n": None,
            "refused": "every level lost requests or returned no token count",
            **conditions,
        }
    speedup = _max_speedup(clean)
    plateau = _throughput_plateau(clean)
    if speedup is None:
        return {
            "n": None,
            "refused": "no n=1 level survived, so there is no baseline to rise from",
            **conditions,
        }
    if speedup < INFERRED_SATURATION_MIN_SPEEDUP:
        return {
            "n": None,
            "refused": (
                f"peak throughput is {speedup}x the single-request rate, at or "
                f"below INFERRED_SATURATION_MIN_SPEEDUP "
                f"({INFERRED_SATURATION_MIN_SPEEDUP}) — a curve that never rises "
                f"has no saturation point to find"
            ),
            **conditions,
        }
    return {
        "n": plateau,
        "refused": None,
        "max_speedup_vs_n1": speedup,
        **conditions,
    }


def readings(levels: list[dict[str, Any]]) -> dict[str, Any]:
    """Every statistic behind the verdict, so a reader can see WHY.

    Both plateaus are reported even though only the throughput one decides the
    width, because the disagreement between them is informative: on a 16-slot
    server they differ by design — latency rises with batch size before any
    queueing starts — and a reader who only saw the verdict could not tell that
    from a broken measurement.
    """
    speedup = _max_speedup(levels)
    return {
        "throughput_plateau_n": _throughput_plateau(levels),
        "latency_plateau_n": _latency_plateau(levels),
        "max_speedup_vs_n1": speedup,
        "note": (
            "both plateaus are reported because their disagreement is readable: "
            "on a wide server they differ by design, since a larger batch is "
            "slower per request before any queueing starts. Neither is a slot "
            "count — the throughput plateau read 6 for two ollama hosts "
            "configured one slot apart. The former `batches` boolean is retired "
            "(D1): it claimed to say which column to believe, and the two "
            "columns measure different things"
        ),
    }


def _max_speedup(levels: list[dict[str, Any]]) -> float | None:
    """Peak throughput over the single-request rate — does this server batch?"""
    single = next((row["tokens_per_s"] for row in levels if row["n"] == 1), None)
    rates = [row["tokens_per_s"] or 0 for row in levels]
    if not single or not rates:
        return None
    return round(max(rates) / single, 2)


def _throughput_plateau(levels: list[dict[str, Any]]) -> int | None:
    """The lowest offered concurrency reaching :data:`PLATEAU_FRACTION` of peak.

    Levels that did not fully succeed are excluded by the caller, not here: a
    level whose requests partly failed has a *lower* throughput and would be
    read as evidence that the curve had flattened. See :func:`saturation`.
    """
    rates = [(row["n"], row["tokens_per_s"] or 0) for row in levels]
    best = max((rate for _, rate in rates), default=0)
    if not best:
        return None
    return next((int(n) for n, rate in rates if rate >= PLATEAU_FRACTION * best), None)


def _latency_plateau(
    levels: list[dict[str, Any]], tolerance: float = LATENCY_TOLERANCE
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
    # A reply that arrived without a `usage` block is NOT a reply that generated
    # zero tokens. Summing it as 0 turned "we could not count" into "this server
    # is slow", which reads downstream as a plateau. Counted separately so
    # `saturation` can drop the level instead of believing it.
    counted = [row for row in good if row.get("completion_tokens") is not None]
    tokens = sum(row["completion_tokens"] for row in counted)
    latencies = [row["latency_s"] for row in good]
    return {
        "n": n,
        "wall_s": round(wall, 3),
        "ok": len(good),
        "counted": len(counted),
        "errors": len(out) - len(good),
        "error_kinds": sorted({row["error"] for row in out if "error" in row}),
        "completion_tokens_total": tokens,
        "tokens_per_s": (round(tokens / wall, 1) if wall and counted else None),
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
