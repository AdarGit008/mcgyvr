#!/usr/bin/env python3
"""Measure the constants this package was built on, instead of asserting them.

Every threshold and timeout in `contract.py`, `pin.py` and the two backends was
chosen from one or two observations — several from a single model on a single
host. `BATCHING_SPEEDUP` carries a docstring admitting it is a judgement
calibrated on four measurements; the others do not even do that, and two of them
(`0.95` for the throughput plateau, `0.10` for the latency plateau) were function
defaults invisible to review.

This runs the observations that decide them, across every model and both hosts,
and writes each sample as it is taken. Incremental on purpose: the ramp phase is
hours long, and a harness that only writes at the end converts a crash at hour
four into the loss of hours one through three.

**Nothing here changes a constant.** It produces the distribution; the value is
a decision, taken with the numbers visible.

Phases, cheapest first, so a short night still yields something:

``fast``
    No model is loaded. Idle-card readings, ssh step durations, discovery-call
    durations, and the array sizes in `/api/show` — which decide
    `IDLE_GPU_MIB`, `STEP_TIMEOUT_S`, `DISCOVERY_TIMEOUT_S`,
    `CAPTURE_TIMEOUT_S` and `MAX_INLINE_ITEMS`.

``load``
    One model at a time, cleared between each. Load durations and VRAM
    placement fractions — `LOAD_TIMEOUT_S` and `MIN_VRAM_FRACTION` — plus the
    checkpoint digest durations behind `DIGEST_TIMEOUT_S`.

``ramp``
    The expensive one. The concurrency ramp across a matrix of configured batch
    widths and token counts, which is the only evidence for `RAMP_TOKENS`,
    `RAMP_REPEATS`, `BATCHING_SPEEDUP` and the two plateau thresholds. Every
    level of every ramp is a row, so the thresholds can be re-derived later
    without re-running the rig.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import types
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _load(slot: str, path: Path) -> types.ModuleType:
    cached = sys.modules.get(slot)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(slot, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[slot] = module
    spec.loader.exec_module(module)
    return module


contract = _load("serving_contract", HERE / "contract.py")

#: Token counts the ramp is repeated at. The batch-width result was measured at
#: 128 and never varied; short generations weight prefill more heavily than
#: decode, so the plateau could move with this and nothing has shown it does not.
TOKEN_COUNTS: tuple[int, ...] = (32, 128, 512)

#: Configured batch widths to launch vLLM at. Spans an order of magnitude so a
#: rule that recovers the flag has to do it more than once.
WIDTHS: tuple[int, ...] = (1, 2, 4, 8, 16)


def emit(out: Path, row: dict[str, Any]) -> None:
    """One sample, appended and flushed. Written now, not at the end."""
    with out.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
        handle.flush()


def fast(out: Path, hosts: list[str], repeats: int = 30) -> None:
    """Idle readings, step durations, discovery durations, array sizes."""
    ollama = contract.load_backend("ollama")
    for host in hosts:
        for index in range(repeats):
            began = time.monotonic()
            reading = contract.ssh(
                host, "nvidia-smi --query-gpu=memory.used --format=csv,noheader"
            )
            emit(
                out,
                {
                    "phase": "fast",
                    "metric": "idle_gpu_mib",
                    "host": host,
                    "index": index,
                    "value": contract.first_int(reading),
                    "seconds": round(time.monotonic() - began, 3),
                },
            )
            began = time.monotonic()
            contract.ssh(host, "free -m | head -2; cat /proc/loadavg")
            emit(
                out,
                {
                    "phase": "fast",
                    "metric": "ssh_step_seconds",
                    "host": host,
                    "index": index,
                    "value": round(time.monotonic() - began, 3),
                },
            )

        base = ollama.probe(host)
        if not base:
            continue
        for model in ollama.inventory(host, base):
            for name, path in (
                ("tags", "/api/tags"),
                ("ps", "/api/ps"),
                ("version", "/api/version"),
            ):
                began = time.monotonic()
                contract.get_json(contract.url(base, path), timeout=30.0)
                emit(
                    out,
                    {
                        "phase": "fast",
                        "metric": "discovery_seconds",
                        "host": host,
                        "endpoint": name,
                        "model": model,
                        "value": round(time.monotonic() - began, 3),
                    },
                )
            began = time.monotonic()
            show = _show(base, model)
            emit(
                out,
                {
                    "phase": "fast",
                    "metric": "capture_show_seconds",
                    "host": host,
                    "model": model,
                    "value": round(time.monotonic() - began, 3),
                    "bytes": len(json.dumps(show)) if show else 0,
                },
            )
            for key, length in _list_lengths(show).items():
                emit(
                    out,
                    {
                        "phase": "fast",
                        "metric": "array_length",
                        "host": host,
                        "model": model,
                        "key": key,
                        "value": length,
                    },
                )


def load(out: Path, hosts: list[str], repeats: int = 2) -> None:
    """Load duration and VRAM placement, one model at a time, cleared between."""
    ollama = contract.load_backend("ollama")
    vllm = contract.load_backend("vllm")
    for host in hosts:
        base = ollama.probe(host)
        if not base:
            continue
        for model in ollama.inventory(host, base):
            for index in range(repeats):
                vllm.release(host)
                began = time.monotonic()
                try:
                    claimed = ollama.claim(host, base, model)
                    ok, why = True, None
                except Exception as error:
                    claimed, ok, why = {}, False, f"{type(error).__name__}: {error}"
                seconds = round(time.monotonic() - began, 3)
                attempt = (claimed.get("attempts") or [{}])[-1]
                emit(
                    out,
                    {
                        "phase": "load",
                        "metric": "load_seconds",
                        "host": host,
                        "model": model,
                        "index": index,
                        "value": seconds,
                        "ok": ok,
                        "why": why,
                        "vram_fraction": attempt.get("vram_fraction"),
                        "size": attempt.get("size"),
                        "size_vram": attempt.get("size_vram"),
                    },
                )
                if attempt.get("vram_fraction") is not None:
                    emit(
                        out,
                        {
                            "phase": "load",
                            "metric": "vram_fraction",
                            "host": host,
                            "model": model,
                            "index": index,
                            "value": attempt["vram_fraction"],
                        },
                    )


def ramp(
    out: Path, hosts: list[str], engines: tuple[str, ...] = ("ollama", "vllm")
) -> None:
    """The concurrency matrix: configured width x token count, both engines."""
    ollama = contract.load_backend("ollama")
    vllm = contract.load_backend("vllm")
    for host in hosts:
        # Ollama first: its width is whatever the host is configured for, so the
        # only axis here is the token count.
        vllm.release(host)
        base = ollama.probe(host) if "ollama" in engines else None
        if base:
            model = _smallest(ollama.inventory(host, base))
            for tokens in TOKEN_COUNTS:
                try:
                    ollama.claim(host, base, model)
                except Exception as error:
                    emit(
                        out,
                        {
                            "phase": "ramp",
                            "engine": "ollama",
                            "host": host,
                            "tokens": tokens,
                            "error": str(error)[:200],
                        },
                    )
                    continue
                _one_ramp(out, base, model, host, "ollama", None, tokens)

        # vLLM: launch at each configured width, ramp at each token count.
        model = _awq(host, vllm) if "vllm" in engines else None
        if not model:
            continue
        # **DE-9.** `vllm.release` runs at the TOP of each host's iteration and
        # nowhere at the end, so after the last width the server keeps the card.
        # That is exactly the leftover step 0.1 found: a `--max-num-seqs 16`
        # instrument holding 4954 of srv1's 6144 MiB, never shut down after the
        # phase-3 ramps. It bites between phases and at the end of the campaign
        # — which is precisely when the record says "both rigs left idle".
        try:
            _widths(out, model, host, vllm, ollama)
        finally:
            vllm.release(host)


def _widths(
    out: Path,
    model: str,
    host: str,
    vllm: types.ModuleType,
    ollama: types.ModuleType,
) -> None:
    """Every configured width for one host, ramped at every token count."""
    for width in WIDTHS:
        serve = {
            "max_model_len": 8192,
            "max_num_seqs": width,
            "gpu_memory_utilization": 0.85,
            # `--enforce-eager` is MANDATORY on srv1 (compute capability
            # 7.5, no CUDA graphs) and is kept on srv2 as well: item 2 is a
            # cross-host replication, and graphs on one host but not the
            # other would be an uncontrolled difference sitting inside the
            # comparison the item exists to make.
            "flags": ["--enforce-eager"],
            # **E10, 2026-08-19: `CUDA_HOME` is dropped, not repaired.**
            # It was `"$HOME/.local/lib/python3.14/site-packages/nvidia/
            # cu13"`, and `vllm._start` renders env values through
            # `shlex.quote`, so `$HOME` never expanded. Read straight off a
            # live server's /proc/<pid>/environ: the literal string, which
            # no path resolves. The expanded path does exist and 3.14 is
            # right today — but no process has ever seen a valid value, so
            # the record's claim that this env block fixed ten failed
            # launches is false; something else fixed them. Expanding it
            # correctly now would introduce an UNTESTED variable into the
            # launch path immediately before a multi-hour campaign, and its
            # effect is unmeasured precisely because it has never been set.
            "env": {"FLASHINFER_DISABLE_VERSION_CHECK": "1"},
        }
        try:
            ollama.release(host)
            vllm.claim(host, f"http://{host}:{vllm.PORT}", model, serve)
        except Exception as error:
            emit(
                out,
                {
                    "phase": "ramp",
                    "engine": "vllm",
                    "host": host,
                    "width": width,
                    "error": str(error)[:200],
                },
            )
            continue
        for tokens in TOKEN_COUNTS:
            _one_ramp(
                out,
                f"http://{host}:{vllm.PORT}",
                model,
                host,
                "vllm",
                width,
                tokens,
            )


def _card_mib(host: str) -> int | None:
    """What the card is holding, right now. The only evidence sleep produces."""
    return contract.first_int(
        contract.ssh(host, "nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    )


def _post(base: str, path: str, timeout: float = 60.0) -> dict[str, Any]:
    """POST with no body, returning the status rather than raising on it."""
    request = urllib.request.Request(contract.url(base, path), data=b"", method="POST")
    began = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "status": response.status,
                "seconds": round(time.monotonic() - began, 3),
            }
    except Exception as error:
        return {
            "status": None,
            "error": f"{type(error).__name__}: {error}",
            "seconds": round(time.monotonic() - began, 3),
        }


def sleep_state(out: Path, hosts: list[str]) -> None:
    """D7 item 5 — what a sampled sleep actually looks like on the card.

    **E3, 2026-08-19: the card is the evidence, never the status.** Measured on
    both rigs: a server launched WITHOUT ``--enable-sleep-mode`` answers
    ``POST /sleep?level=1`` with **200** and then reports
    ``{"is_sleeping": true}`` while freeing 20-22 MiB of ~5-10 GB. Every
    endpoint agrees that the model is asleep and the card says it never left.

    So both arms are run, in this order, and the negative control is the point
    rather than a formality: without the flag the endpoints lie, with it they do
    not, and a reading that cannot tell those apart is not a measurement of
    sleep. The pass condition is a VRAM drop, and it is asserted here rather
    than left for a reader to notice.
    """
    vllm = contract.load_backend("vllm")
    ollama = contract.load_backend("ollama")
    for host in hosts:
        model = _awq(host, vllm)
        if not model:
            emit(out, {"phase": "sleep", "host": host, "refused": "no AWQ checkpoint"})
            continue
        for arm, flags in (
            ("control_no_flag", ["--enforce-eager"]),
            ("enabled", ["--enforce-eager", "--enable-sleep-mode"]),
        ):
            serve = {
                "max_model_len": 8192,
                "max_num_seqs": 8,
                "gpu_memory_utilization": 0.85,
                "flags": flags,
                "env": {"FLASHINFER_DISABLE_VERSION_CHECK": "1"},
            }
            base = f"http://{host}:{vllm.PORT}"
            row: dict[str, Any] = {
                "phase": "sleep",
                "metric": "sleep",
                "host": host,
                "arm": arm,
                "model": model,
                "flags": flags,
            }
            try:
                ollama.release(host)
                vllm.claim(host, base, model, serve)
                row["awake_mib"] = _card_mib(host)
                row["is_sleeping_before"] = contract.get_json(
                    contract.url(base, "/is_sleeping")
                )
                row["sleep_call"] = _post(base, "/sleep?level=1")
                time.sleep(15)
                row["asleep_mib"] = _card_mib(host)
                row["is_sleeping_after"] = contract.get_json(
                    contract.url(base, "/is_sleeping")
                )
                row["wake_call"] = _post(base, "/wake_up")
                time.sleep(10)
                row["awake_again_mib"] = _card_mib(host)
                awake, asleep = row["awake_mib"], row["asleep_mib"]
                row["freed_mib"] = (
                    None if awake is None or asleep is None else awake - asleep
                )
                # THE verdict, and it reads the card. `>= half` rather than a
                # fixed MiB because the two rigs hold very different amounts.
                row["actually_freed"] = (
                    None
                    if row["freed_mib"] is None or not awake
                    else row["freed_mib"] >= awake * 0.5
                )
                row["endpoint_claimed_asleep"] = bool(
                    (row["is_sleeping_after"] or {}).get("is_sleeping")
                )
                # The finding, stated as a field so it can be counted: the
                # endpoint said asleep and the card disagreed.
                row["endpoint_lied"] = bool(
                    row["endpoint_claimed_asleep"] and row["actually_freed"] is False
                )
                # **DE-12.** The docstring promised an assertion and the first
                # version computed a field instead, so an `enabled` arm freeing
                # 20 MiB emitted a row indistinguishable in status from one
                # freeing 10 GB. The control arm is EXPECTED to free nothing —
                # that is what makes it a control — so only the enabled arm can
                # fail here.
                row["failed"] = bool(
                    arm == "enabled" and row["actually_freed"] is not True
                )
            except Exception as error:
                row["refused"] = f"{type(error).__name__}: {error}"
            finally:
                vllm.release(host)
            emit(out, row)
            print(
                f"  {host}/{arm}: {'FAILED ' if row.get('failed') else ''}"
                f"awake={row.get('awake_mib')} "
                f"asleep={row.get('asleep_mib')} freed={row.get('freed_mib')} "
                f"actually_freed={row.get('actually_freed')} "
                f"endpoint_lied={row.get('endpoint_lied')}",
                flush=True,
            )


def _one_ramp(
    out: Path,
    base: str,
    model: str,
    host: str,
    engine: str,
    width: int | None,
    tokens: int,
) -> None:
    """One ramp, every level recorded so thresholds can be re-derived later."""
    original = contract.RAMP_TOKENS
    contract.RAMP_TOKENS = tokens
    try:
        result = contract.ramp(base, model)
    except Exception as error:
        emit(
            out,
            {
                "phase": "ramp",
                "engine": engine,
                "host": host,
                "model": model,
                "width": width,
                "tokens": tokens,
                "error": str(error)[:200],
            },
        )
        return
    finally:
        contract.RAMP_TOKENS = original
    readings = result.get("readings") or {}
    saturated = result.get("saturation") or {}
    emit(
        out,
        {
            "phase": "ramp",
            "metric": "ramp",
            "engine": engine,
            "host": host,
            "model": model,
            "configured_width": width,
            "tokens": tokens,
            "saturation_n": saturated.get("n"),
            "saturation_refused": saturated.get("refused"),
            "ramp_tokens": saturated.get("ramp_tokens"),
            "plateau_fraction": saturated.get("plateau_fraction"),
            "levels_dropped": saturated.get("levels_dropped"),
            "throughput_plateau_n": readings.get("throughput_plateau_n"),
            "latency_plateau_n": readings.get("latency_plateau_n"),
            "max_speedup_vs_n1": readings.get("max_speedup_vs_n1"),
            "levels": result.get("levels"),
        },
    )
    print(
        f"  {host}/{engine} width={width} tokens={tokens} -> saturation_n "
        f"{saturated.get('n')} speedup {readings.get('max_speedup_vs_n1')}"
        + (f" REFUSED: {saturated['refused']}" if saturated.get("refused") else ""),
        flush=True,
    )


def _show(base: str, model: str) -> dict[str, Any] | None:
    observed = contract.observed()
    return observed.identity._post_json(
        contract.url(base, "/api/show"),
        {"model": model, "verbose": True},
        timeout=120.0,
    )


def _list_lengths(show: Any) -> dict[str, int]:
    """Every list in the document, by key — what MAX_INLINE_ITEMS separates."""
    out: dict[str, int] = {}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            out[path] = len(value)

    walk(show or {}, "")
    return out


def _smallest(models: list[str]) -> str:
    """The 1.5B where present: the ramp should not be a memory experiment."""
    for candidate in models:
        if "1.5b" in candidate.lower():
            return candidate
    return models[0]


def _awq(host: str, vllm: types.ModuleType) -> str | None:
    listing = contract.ssh(host, "ls ~/.cache/huggingface/hub 2>/dev/null || true")
    # Smallest AWQ first: the ramp is a concurrency measurement, not a memory
    # experiment, and the first alphabetical match put a 14B on a 12 GB card.
    # Delimited, and largest-first. A bare `"4B" in name` matches inside `"14B"`,
    # so a 14B sorted as a 4B and the "first alphabetical match put a 14B on a
    # 12 GB card" failure this ordering exists to prevent came back through the
    # ordering itself. Harmless today only because both rigs now hold the 1.5B,
    # which ranks first either way.
    order = ("1.5B", "3B", "4B", "7B", "14B")
    found = [
        line.strip()
        for line in (listing or "").splitlines()
        if "AWQ" in line and "models--" in line
    ]

    def rank(name: str) -> int:
        upper = name.upper()
        for index, size in enumerate(order):
            if f"-{size.upper()}-" in upper or upper.endswith(f"-{size.upper()}"):
                return index
        return len(order)

    found.sort(key=rank)
    if not found:
        return None
    return found[0].removeprefix("models--").replace("--", "/", 1)


def main(argv: list[str] | None = None) -> int:
    # Declared first because Python requires it before ANY reference in the
    # function, and the --tokens/--widths help strings quote the defaults.
    global TOKEN_COUNTS, WIDTHS

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--phase", choices=("fast", "load", "ramp", "sleep"), required=True
    )
    parser.add_argument("--hosts", default="srv1,srv2")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument(
        "--engines",
        default="ollama,vllm",
        help="restrict the ramp phase — re-running one half must not redo the other",
    )
    # **E12, 2026-08-19.** The module-level TOKEN_COUNTS is the HISTORICAL
    # matrix — (32, 128, 512) is what the calibration measured, and rewriting it
    # would make the record's own columns unreproducible. D7 wants the same five
    # widths at the single D3 budget of 475, which is three times less rig time
    # than re-running the whole matrix, so it is asked for rather than edited in.
    parser.add_argument(
        "--tokens",
        default="",
        help=(
            "ramp phase: token counts to sweep (comma separated). Default is "
            f"the historical matrix {TOKEN_COUNTS}. D7 runs --tokens 475."
        ),
    )
    parser.add_argument(
        "--widths",
        default="",
        help=f"ramp phase: vLLM launch widths. Default {WIDTHS}.",
    )
    args = parser.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    began = time.monotonic()
    if args.phase == "fast":
        fast(args.out, hosts, repeats=args.repeats)
    elif args.phase == "load":
        load(args.out, hosts, repeats=max(1, args.repeats // 15))
    elif args.phase == "sleep":
        sleep_state(args.out, hosts)
    else:
        # Rebound for the duration of this process only. `ramp` reads the
        # module globals, and every emitted row already carries its own
        # `tokens` and `configured_width`, so a narrowed sweep is legible in the
        # output rather than something a reader has to know was passed.
        if args.tokens:
            TOKEN_COUNTS = tuple(
                int(t.strip()) for t in args.tokens.split(",") if t.strip()
            )
        if args.widths:
            WIDTHS = tuple(int(w.strip()) for w in args.widths.split(",") if w.strip())
        print(f"ramp: widths={WIDTHS} tokens={TOKEN_COUNTS}", flush=True)
        ramp(args.out, hosts, tuple(e.strip() for e in args.engines.split(",")))
    print(f"{args.phase} finished in {time.monotonic() - began:.0f}s -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
