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
import os
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


#: The provenance stamp every row written by this process carries (#325):
#: :func:`contract.provenance`, computed once by :func:`main` when the run
#: begins. Filled on first use when nothing set it, so a row written outside
#: `main` -- a test driving one phase -- is stamped too rather than stamped
#: differently.
STAMP: dict[str, Any] | None = None


def _stamp() -> dict[str, Any]:
    global STAMP
    if STAMP is None:
        STAMP = contract.provenance(argv=sys.argv[1:])
    return STAMP


def emit(out: Path, row: dict[str, Any]) -> None:
    """One sample, appended and put on the disk. Written now, not at the end.

    **Stamped here, at the sink (#325).** Every row carries the commit, the
    harness digest, the argv and the run's start, under
    :data:`contract.PROVENANCE_DISPOSITION`'s keys. At the sink and not in
    each builder because there are nineteen builders and one sink, and the
    census in ``tests/test_sink_conformance.py`` proves every write passes
    through here. A row's own keys win, which none of them overlap.

    ``fsync``, not just ``flush``. A flush hands the bytes to the kernel, which
    is enough to survive this process dying and not enough to survive the box
    going down — and the box going down eight hours into an unattended campaign
    is precisely the case this exists for. A sample costs a model load; a sync
    costs microseconds.
    """
    with out.open("a", encoding="utf-8") as handle:
        # Heal a torn tail before appending — see the note above.
        if _ends_mid_line(out):
            handle.write("\n")
        handle.write(json.dumps({**_stamp(), **row}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _ends_mid_line(path: Path) -> bool:
    """Whether the file's last byte is something other than a newline.

    One byte is read, not the whole file — see the note on `run.py`'s twin.
    """
    if not path.stat().st_size:
        return False
    with path.open("rb") as tail:
        tail.seek(-1, os.SEEK_END)
        return tail.read(1) != b"\n"


def key(row: dict[str, Any]) -> tuple[Any, ...]:
    """What identifies a sample, so a resumed run knows it already has it.

    Deliberately the *conditions*, not the result: a row that refused is still an
    answer about this rig at these settings, and paying for it twice buys the
    same refusal. `--retry-failed` is how you say otherwise.
    """
    return (
        row.get("phase"),
        row.get("host"),
        row.get("engine"),
        # **DE-K.** The ramp's model is chosen at RUNTIME (`_smallest`, `_awq`),
        # not passed in, so two runs of the identical command can measure
        # different weights — and E7 pre-warmed a checkpoint into the directory
        # `_awq` ranks. Without the model in the key, a resume skipped work
        # whose rows name a model that is no longer the one that would run.
        row.get("model"),
        row.get("arm"),
        row.get("configured_width", row.get("width")),
        row.get("tokens"),
    )


def _succeeded(row: dict[str, Any]) -> bool:
    """Whether a sample is an answer rather than a failure to get one."""
    return not (
        row.get("error")
        or row.get("refused")
        or row.get("saturation_refused")
        or row.get("failed")
    )


def _raised(row: dict[str, Any]) -> bool:
    """Whether an exception escaped, as opposed to the cell refusing.

    The two were treated identically by :func:`completed` and they are not the
    same thing. A **refusal** is an answer about this rig at these settings --
    BL-4 declining a curve that never rises, srv1 declining to start vLLM with
    ``--enable-sleep-mode`` inside 900 s -- and re-running it buys the same
    refusal, which is why :func:`key` is the conditions and why
    ``--retry-failed`` exists to override that.

    An **exception** is not an answer. Nothing was learned, the cell is still
    owed, and the console line for it says nothing at all. Counting it as done
    made a cell lost to a transient error unrecoverable by the ``--resume`` the
    campaign driver actually runs -- recoverable only by knowing to add a flag
    whose name says "failed" for a cell that never reported failing.
    """
    return bool(row.get("error"))


def completed(out: Path, retry_failed: bool = False) -> set[tuple[Any, ...]]:
    """Every sample already on disk, by :func:`key`.

    **This is what makes an eleven-hour run restartable.** Without it a crash at
    hour eight costs eight hours, which for a campaign with no time limit is the
    difference between a setback and a run nobody dares start.
    """
    if not out.exists():
        return set()
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for line in out.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            # A half-written last line is what a crash mid-append looks like.
            # Ignoring it re-does exactly that one sample, which is right.
            continue
        # **DE-C.** This used to test `error` or `refused` only, which are set
        # when an EXCEPTION escaped — so the two refusal paths the previous
        # review installed were unreachable by `--retry-failed`: a ramp refused
        # by BL-4's "the curve was not measured to its end", and a sleep arm
        # that set `failed` because the card never dropped. Those are precisely
        # the rows a second look might resolve.
        # #325: the phase row is the phase's own span, not a cell. Its key
        # would be (phase, None, ...) and a resumed run must never count it as
        # a sample -- "resuming: N samples" is a count of cells.
        if row.get("metric") == "phase":
            continue
        rows[key(row)] = row
    # **DE-D, mirrored from `run.py.completed`.** Filtering DURING the scan let
    # an older `ok` line survive a newer failed one for the same key, so
    # `--retry-failed` counted the cell done and skipped the very retry it was
    # asked for — reporting the superseded success as the cell's answer. Last
    # write wins first; only then are the failures dropped.
    # An exception is re-done ALWAYS, not only under `--retry-failed`: see
    # `_raised`. Applied after the scan for the same DE-D reason as the filter
    # below -- last write wins first, so a newer exception cannot be masked by
    # an older success for the same key.
    rows = {k: row for k, row in rows.items() if not _raised(row)}
    if retry_failed:
        rows = {k: row for k, row in rows.items() if _succeeded(row)}
    return set(rows)


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
                started_at = contract.now()
                began = time.monotonic()
                try:
                    claimed = ollama.claim(host, base, model)
                    ok, why = True, None
                except Exception as error:
                    claimed, ok, why = {}, False, f"{type(error).__name__}: {error}"
                seconds = round(time.monotonic() - began, 3)
                row = _load_row(host, model, index, seconds, ok, why, claimed)
                row["started_at"], row["ended_at"] = started_at, contract.now()
                emit(out, row)
                if row["vram_fraction"] is not None:
                    emit(
                        out,
                        {
                            "phase": "load",
                            "metric": "vram_fraction",
                            "host": host,
                            "model": model,
                            "index": index,
                            "value": row["vram_fraction"],
                        },
                    )


def ramp(
    out: Path,
    hosts: list[str],
    engines: tuple[str, ...] = ("ollama", "vllm"),
    done: set[tuple[Any, ...]] | None = None,
) -> None:
    """The concurrency matrix: configured width x token count, both engines."""
    done = done if done is not None else set()
    ollama = contract.load_backend("ollama")
    vllm = contract.load_backend("vllm")
    for host in hosts:
        # Ollama first: its width is whatever the host is configured for, so the
        # only axis here is the token count.
        vllm.release(host)
        base = ollama.probe(host) if "ollama" in engines else None
        if "ollama" in engines and not base:
            # **BL-A.** `probe` returns None for an unreachable engine AND for a
            # transient ssh or HTTP failure, and this used to `continue` with no
            # row and no message. A phase that skips a host in silence and exits
            # 0 is indistinguishable from one that had nothing to do.
            emit(
                out,
                {
                    "phase": "ramp",
                    "host": host,
                    "engine": "ollama",
                    "refused": "the engine did not answer its probe on this host",
                },
            )
        if base:
            inventory = ollama.inventory(host, base)
            if not inventory:
                # DE-H: `_smallest([])` raised IndexError and took the whole
                # phase down for BOTH hosts. `ollama.release` restarts the
                # service, so an empty inventory mid-restart is realistic.
                emit(
                    out,
                    {
                        "phase": "ramp",
                        "host": host,
                        "engine": "ollama",
                        "refused": "the engine reported an empty inventory",
                    },
                )
                continue
            model = _smallest(inventory)
            # **A4.** Read once per model rather than per token count: it is one
            # ssh and the answer cannot change between token budgets. Without
            # it every ollama ramp row carried `declared_slots: null` while the
            # survey read the same number off /props on the same host.
            try:
                ollama_declared = ollama.slots_now(host)
            except Exception as error:
                ollama_declared = {
                    "value": None,
                    "provenance": None,
                    "refused": f"{type(error).__name__}: {error}",
                }
            for tokens in TOKEN_COUNTS:
                probe = key(
                    {
                        "phase": "ramp",
                        "host": host,
                        "engine": "ollama",
                        "model": model,
                        "tokens": tokens,
                    }
                )
                if probe in done:
                    print(f"  {host}/ollama tokens={tokens} — already done", flush=True)
                    continue
                started_at = contract.now()
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
                            "started_at": started_at,
                            "ended_at": contract.now(),
                        },
                    )
                    continue
                _one_ramp(
                    out,
                    base,
                    model,
                    host,
                    "ollama",
                    None,
                    tokens,
                    declared=ollama_declared,
                )

        # vLLM: launch at each configured width, ramp at each token count.
        model = _awq(host, vllm) if "vllm" in engines else None
        if "vllm" in engines and not model:
            # **BL-A, and this is the expensive half.** `_awq` shells out to
            # `ls ~/.cache/huggingface/hub`, and `contract.ssh` returns None for
            # a connect timeout, a loaded box and an empty listing alike. A bare
            # `continue` here deleted D7 items 2 and 6 — the five-width matrices,
            # ~4.7 h and the campaign's headline result — from a transient drop,
            # emitted nothing, and exited 0. Demonstrated: the phase printed
            # "finished in 0s" and never created its output file.
            emit(
                out,
                {
                    "phase": "ramp",
                    "host": host,
                    "engine": "vllm",
                    "refused": (
                        "no AWQ checkpoint could be listed on this host. NOTE "
                        "this is also what a failed ssh looks like, so it is a "
                        "refusal to be investigated rather than a fact about "
                        "the host"
                    ),
                },
            )
        if not model:
            continue
        # **DE-9.** `vllm.release` runs at the TOP of each host's iteration and
        # nowhere at the end, so after the last width the server keeps the card.
        # That is exactly the leftover step 0.1 found: a `--max-num-seqs 16`
        # instrument holding 4954 of srv1's 6144 MiB, never shut down after the
        # phase-3 ramps. It bites between phases and at the end of the campaign
        # — which is precisely when the record says "both rigs left idle".
        try:
            _widths(out, model, host, vllm, ollama, done)
        finally:
            vllm.release(host)


def _widths(
    out: Path,
    model: str,
    host: str,
    vllm: types.ModuleType,
    ollama: types.ModuleType,
    done: set[tuple[Any, ...]],
) -> None:
    """Every configured width for one host, ramped at every token count."""
    for width in WIDTHS:
        # Checked BEFORE the launch, not before each ramp: a width whose token
        # counts are all recorded needs no server, and the launch is the
        # expensive part — 33 s on srv1 and 109 s on srv2, plus the teardown.
        if all(
            key(
                {
                    "phase": "ramp",
                    "host": host,
                    "engine": "vllm",
                    "model": model,
                    "configured_width": width,
                    "tokens": tokens,
                }
            )
            in done
            for tokens in TOKEN_COUNTS
        ):
            print(f"  {host}/vllm width={width} — already done", flush=True)
            continue
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
        started_at = contract.now()
        try:
            ollama.release(host)
            # **A1.** The return value used to be discarded. `vllm.claim` times
            # every launch and hands back `checks.started.start_seconds` with a
            # comment saying D6 wants it -- and ten launches computed it and
            # threw it away, leaving START_TIMEOUT_S = 900 s resting on nothing
            # after the campaign that was commissioned to measure it. The
            # MARKERS guard passed the whole time: it asserts that vllm.py
            # contains the string "start_seconds", which it does.
            claimed = vllm.claim(host, f"http://{host}:{vllm.PORT}", model, serve)
            # **DE-F, and this is the whole of E5's vLLM half.** `launched_width`
            # was only reachable from `describe`, whose only caller is the
            # survey — and the campaign config has no vLLM entries at all. So
            # every width row would have carried the value this run DISPATCHED,
            # unverified against the host, which is the state E5 was revised to
            # leave behind. Read here, where the server was just launched.
            declared = vllm.declared_slots(serve, host)
            emit(out, _launch_row(host, model, width, claimed))
        except Exception as error:
            emit(
                out,
                {
                    "phase": "ramp",
                    "engine": "vllm",
                    "host": host,
                    "width": width,
                    "error": str(error)[:200],
                    "started_at": started_at,
                    "ended_at": contract.now(),
                },
            )
            continue
        for tokens in TOKEN_COUNTS:
            if (
                key(
                    {
                        "phase": "ramp",
                        "host": host,
                        "engine": "vllm",
                        "model": model,
                        "configured_width": width,
                        "tokens": tokens,
                    }
                )
                in done
            ):
                continue
            if declared.get("provenance") == "contradicted":
                # A server whose argv does not match what we asked for is not
                # the server this row would claim to describe. Refused rather
                # than recorded beside the number, because the number would be
                # about a configuration nobody chose.
                emit(
                    out,
                    {
                        "phase": "ramp",
                        "host": host,
                        "engine": "vllm",
                        "model": model,
                        "width": width,
                        "tokens": tokens,
                        "refused": declared.get("refused"),
                        "declared_slots": declared,
                        # Refused before anything ran: an instant, not a span.
                        "started_at": (refused_at := contract.now()),
                        "ended_at": refused_at,
                    },
                )
                continue
            _one_ramp(
                out,
                f"http://{host}:{vllm.PORT}",
                model,
                host,
                "vllm",
                width,
                tokens,
                declared,
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


def _sleep_unmeasured(row: dict[str, Any]) -> str | None:
    """Why this sleep cell measured nothing, or ``None`` if it measured.

    **A5.** Three paths recorded a transient failure as a clean measurement, and
    all three are the same mistake as the sink defects above: a value that was
    not obtained being written as a value that was.

    1. ``_card_mib`` returning ``None`` -- the ssh or nvidia-smi failed -- left
       ``freed_mib`` null, ``actually_freed`` null, and on a CONTROL arm
       ``failed: false``, because DE-12 correctly says only the enabled arm can
       fail. A control that read nothing is indistinguishable in the row from a
       control that read a card which did not move, which is the entire finding
       the control exists to establish.
    2. ``/is_sleeping`` not answering made ``endpoint_claimed_asleep`` ``False``
       via ``(None or {}).get(...)``, so ``endpoint_lied`` computed ``False`` --
       "the endpoint told the truth" -- from an endpoint that said nothing.
       ``endpoint_lied`` is phase 1's headline and it was reachable by silence.
    3. A non-200 from ``POST /sleep`` was never checked, and the card delta was
       scored anyway. Nothing was asked to sleep, and the row reports on how
       much sleeping happened.

    None of the three fired on the 2026-08-19/20 campaign -- every cell produced
    real readings -- and all three were un-retryable once written, because a row
    with no failure marked is a row ``--resume`` treats as done.
    """
    if row.get("awake_mib") is None or row.get("asleep_mib") is None:
        return (
            "the card was not read (nvidia-smi or its ssh returned nothing), so "
            "there is no VRAM delta to score and no arm can be judged on it"
        )
    status = (row.get("sleep_call") or {}).get("status")
    if status != 200:
        return (
            f"POST /sleep answered {status!r}, so nothing was asked to sleep "
            "and the card delta is not a measurement of sleeping"
        )
    if row.get("is_sleeping_after") is None:
        return (
            "/is_sleeping did not answer after the sleep call, so whether the "
            "endpoint CLAIMED to be asleep is unknown -- and endpoint_lied is a "
            "statement about that claim, not about the card alone"
        )
    return None


def sleep_state(
    out: Path, hosts: list[str], done: set[tuple[Any, ...]] | None = None
) -> None:
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
            # `engine` is in the key (DE-K), and since #324 the row carries it
            # -- so the lookup must carry it too, or a finished cell is never
            # recognised on --resume and vLLM is relaunched for every arm.
            if key(
                {
                    "phase": "sleep",
                    "host": host,
                    "engine": vllm.NAME,
                    "model": model,
                    "arm": arm,
                }
            ) in (done or set()):
                print(f"  {host}/{arm} — already done", flush=True)
                continue
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
                "engine": vllm.NAME,
                "host": host,
                "arm": arm,
                "model": model,
                "flags": flags,
                # #325: the arm's own span, from the release that makes room
                # to the write. The claim's span is carried beside it as
                # `claim_started_at`/`claim_ended_at` by `_claim_fields`.
                "started_at": contract.now(),
            }
            try:
                ollama.release(host)
                # **#324.** A1's defect one function down: `claim` times the
                # launch and the return was discarded here too, so the three
                # sleep-arm launches that came up on 2026-08-19/20 recorded no
                # `start_seconds`. Assigned and merged, under the same
                # disposition the launch row is held to.
                claimed = vllm.claim(host, base, model, serve)
                row.update(_claim_fields(claimed))
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
                # **A5.** Decided BEFORE any verdict is computed: a cell that
                # measured nothing must not report on what it measured.
                unmeasured = _sleep_unmeasured(row)
                if unmeasured:
                    row["actually_freed"] = None
                    row["endpoint_claimed_asleep"] = None
                    row["endpoint_lied"] = None
                    row["failed"] = None
                    # `error`, not `refused`: nothing was learned and the cell
                    # is still owed, so a plain --resume re-does it. See
                    # `_raised` -- srv1 declining to start vLLM with the sleep
                    # flag inside 900 s IS an answer and stays a refusal; a card
                    # read that returned nothing is not.
                    row["error"] = unmeasured
                    row["ended_at"] = contract.now()
                    emit(out, row)
                    print(f"  {host}/{arm}: UNMEASURED — {unmeasured}", flush=True)
                    continue
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
            row["ended_at"] = contract.now()
            emit(out, row)
            print(
                f"  {host}/{arm}: {'FAILED ' if row.get('failed') else ''}"
                f"awake={row.get('awake_mib')} "
                f"asleep={row.get('asleep_mib')} freed={row.get('freed_mib')} "
                f"actually_freed={row.get('actually_freed')} "
                f"endpoint_lied={row.get('endpoint_lied')}",
                flush=True,
            )


#: What becomes of every key :func:`contract.ramp` returns, when this module
#: writes a ramp row. A tuple names the row keys the field reaches; ``None``
#: means the field is deliberately not carried and ``RAMP_ROW_DROPPED`` says
#: why. ``tests/test_sink_conformance.py`` compares this table against the
#: producer's real key set and against the row really written, so a field added
#: to :func:`contract.ramp` without a decision here goes red.
#:
#: **This table exists because four fields were dropped here for a whole
#: campaign and no check could see it.** ``launch.py``'s MARKERS entry
#: ``'"repeats": attempts'`` passed throughout, because it asserts that
#: ``contract.py`` contains that string -- which it does. The value never
#: reached a file. A guard over source text cannot catch a sink.
RAMP_ROW_DISPOSITION: dict[str, tuple[str, ...] | None] = {
    "levels": ("levels",),
    "saturation": (
        "saturation_n",
        "saturation_refused",
        "ramp_tokens",
        "plateau_fraction",
        "levels_dropped",
    ),
    "readings": ("throughput_plateau_n", "latency_plateau_n", "max_speedup_vs_n1"),
    # **D6/D7 item 7, restored.** The survey has carried these since it was
    # written; the ramp journal -- where every headline speedup figure lives --
    # did not. `contract.ramp` states the cost of dropping them: the bias `max`
    # introduces over repeats is "unrecoverable afterwards", and the campaign
    # of 2026-08-19/20 measured it 149 times in the survey and zero times for
    # the twelve ramp cells D1 and D2 were decided on.
    "repeats": ("repeats",),
    "repeat_spread": ("repeat_spread",),
    # The per-level ratio the plateau is read from. Recomputable from `levels`,
    # carried anyway: a reader checking a plateau should not have to reproduce
    # the arithmetic to see the curve the plateau was read off.
    "speedup_vs_n1": ("speedup_vs_n1",),
    "method": None,
}

#: Why a field in :data:`RAMP_ROW_DISPOSITION` is not carried. Dropping is
#: allowed; dropping silently is not.
RAMP_ROW_DROPPED: dict[str, str] = {
    "method": (
        "prose, identical on every row, and it is a constant in "
        "contract.ramp's own source where a reader can cite it by line. "
        "Repeating it per row would grow the journal without making any "
        "figure more interpretable."
    ),
}


#: What becomes of every key :func:`vllm.claim` returns, when this module writes
#: a launch row. Same contract as :data:`RAMP_ROW_DISPOSITION` and enforced by
#: the same test -- see ``tests/test_sink_conformance.py``.
LAUNCH_ROW_DISPOSITION: dict[str, tuple[str, ...] | None] = {
    "backend": ("engine",),
    "model": ("model",),
    "verified": ("verified",),
    "checks": (
        # #325: the claim's span, `checks.started_at`/`ended_at`, carried
        # under the claim's name so a sink with a wider unit (the sleep arm)
        # can hold its own `started_at` beside it.
        "claim_started_at",
        "claim_ended_at",
        "start_seconds",
        "launcher",
        "restarted",
        "reason",
        "gpu_used_mib",
        "allocation_present",
        "served_models",
        "weights_sha256",
        "digest_seconds",
    ),
    "declarations_ignored": ("declarations_ignored",),
}

#: Why a field in :data:`LAUNCH_ROW_DISPOSITION` is not carried.
LAUNCH_ROW_DROPPED: dict[str, str] = {}


#: What becomes of what a sleep cell's producers return. The claim half is the
#: launch row's, because :func:`_claim_fields` writes both; the other four are
#: the documents ``POST /sleep``, ``POST /wake_up`` and ``GET /is_sleeping``
#: answered, carried whole under the key the row has always used. Held to the
#: producers by ``tests/test_sink_conformance.py``.
SLEEP_ROW_DISPOSITION: dict[str, tuple[str, ...] | None] = {
    **LAUNCH_ROW_DISPOSITION,
    "sleep_call": ("sleep_call",),
    "wake_call": ("wake_call",),
    "is_sleeping_before": ("is_sleeping_before",),
    "is_sleeping_after": ("is_sleeping_after",),
}

#: Why a field in :data:`SLEEP_ROW_DISPOSITION` is not carried.
SLEEP_ROW_DROPPED: dict[str, str] = {}


#: What becomes of every key of the attempt record ``ollama.claim`` returns
#: (the last entry of ``attempts`` on success), when the load phase writes its
#: row. Before #324 the row kept three of the twenty-one and no check could say
#: so. Same contract as :data:`RAMP_ROW_DISPOSITION`.
LOAD_ROW_DISPOSITION: dict[str, tuple[str, ...] | None] = {
    # D6's "does a second attempt ever rescue a first": the ordinal of the
    # attempt whose record this is (on a success, the one that succeeded).
    "attempt": ("attempt",),
    # #325: the attempt's own span; the row's `started_at`/`ended_at` spans
    # every attempt, so the two are named apart.
    "started_at": ("attempt_started_at",),
    "ended_at": ("attempt_ended_at",),
    "card_idle_before_load": ("card_idle_before_load",),
    "card_used_mib_before_load": ("card_used_mib_before_load",),
    "card_used_mib_after_load": ("card_used_mib_after_load",),
    "load_http_status": ("load_http_status",),
    "resident_names": ("resident_names",),
    "sole_resident": ("sole_resident",),
    "size": ("size",),
    "size_vram": ("size_vram",),
    "vram_fraction": ("vram_fraction",),
    "placement_expected": ("placement_expected",),
    "placement_meets_expectation": ("placement_meets_expectation",),
    "residency_contradicts_card": ("residency_contradicts_card",),
    "model_sha256": ("model_sha256",),
    "server": ("server",),
    "ok": None,
    "coresidency_allowed": None,
    "coresident_with": None,
    "coresident_loads": None,
    "coresidency_arranged": None,
    "model_sha256_expected": None,
}

#: Why a field in :data:`LOAD_ROW_DISPOSITION` is not carried.
LOAD_ROW_DROPPED: dict[str, str] = {
    "ok": (
        "the attempt record reaches this sink only on claim's success path, "
        "where `ok` is True by construction; the row's own `ok` (did claim "
        "return at all) is the field a reader wants and the two would be "
        "confused if both were present."
    ),
    "coresidency_allowed": (
        "the load phase never passes `coresident`, so this is False on every "
        "row; the survey's co-residency entries are where the field varies "
        "and the survey row carries the whole claim."
    ),
    "coresident_with": (
        "the load phase never passes `coresident_with`, so this is None on "
        "every row it could write; see coresidency_allowed."
    ),
    "coresident_loads": (
        "the load phase loads no neighbours, so this is None on every row; "
        "see coresidency_allowed."
    ),
    "coresidency_arranged": (
        "the load phase arranges no co-residency, so this is None on every "
        "row; see coresidency_allowed."
    ),
    "model_sha256_expected": (
        "the load phase pins no digest (`expect` is never passed), so this "
        "is None on every row; the served digest itself is carried as "
        "model_sha256 so the identity is still on the record."
    ),
}


def _load_row(
    host: str,
    model: str,
    index: int,
    seconds: float,
    ok: bool,
    why: str | None,
    claimed: dict[str, Any],
) -> dict[str, Any]:
    """One ollama load, timed, with the placement the attempt record saw."""
    attempts = claimed.get("attempts") or []
    attempt = attempts[-1] if attempts else {}
    return {
        "phase": "load",
        "metric": "load_seconds",
        "host": host,
        "model": model,
        "index": index,
        "value": seconds,
        "ok": ok,
        "why": why,
        "attempt": attempt.get("attempt"),
        "attempt_started_at": attempt.get("started_at"),
        "attempt_ended_at": attempt.get("ended_at"),
        "card_idle_before_load": attempt.get("card_idle_before_load"),
        "card_used_mib_before_load": attempt.get("card_used_mib_before_load"),
        "card_used_mib_after_load": attempt.get("card_used_mib_after_load"),
        "load_http_status": attempt.get("load_http_status"),
        "resident_names": attempt.get("resident_names"),
        "sole_resident": attempt.get("sole_resident"),
        "size": attempt.get("size"),
        "size_vram": attempt.get("size_vram"),
        "vram_fraction": attempt.get("vram_fraction"),
        "placement_expected": attempt.get("placement_expected"),
        "placement_meets_expectation": attempt.get("placement_meets_expectation"),
        "residency_contradicts_card": attempt.get("residency_contradicts_card"),
        "model_sha256": attempt.get("model_sha256"),
        "server": attempt.get("server"),
    }


def _launch_row(
    host: str, model: str, width: int | None, claimed: dict[str, Any]
) -> dict[str, Any]:
    """One vLLM launch, and what it cost -- D6's START_TIMEOUT_S evidence.

    A row of its own rather than fields folded into the ramp rows: one launch
    serves every token count at that width, so folding it in would repeat the
    same timing under several keys and invite someone to average them.
    """
    fields = _claim_fields(claimed)
    return {
        "phase": "ramp",
        "metric": "launch",
        "host": host,
        "model": claimed.get("model") or model,
        "configured_width": width,
        # The launch row's unit IS the claim, so its span is the claim's.
        "started_at": fields["claim_started_at"],
        "ended_at": fields["claim_ended_at"],
        **fields,
    }


def _claim_fields(claimed: dict[str, Any]) -> dict[str, Any]:
    """``vllm.claim``'s return, flattened as :data:`LAUNCH_ROW_DISPOSITION` says.

    One function for both sinks that write a launch -- the width row and the
    sleep row -- so the disposition is true of each because it is the same code.
    ``model`` is not here: each sink owns its own, so a claim return without
    one cannot overwrite the identity the row's key is built from.
    """
    checks = claimed.get("checks") or {}
    started = checks.get("started") or {}
    weights = checks.get("weights") or {}
    return {
        "engine": claimed.get("backend"),
        "verified": claimed.get("verified"),
        "claim_started_at": checks.get("started_at"),
        "claim_ended_at": checks.get("ended_at"),
        # The four D6 asked for, at the only moment anything can answer them.
        "start_seconds": started.get("start_seconds"),
        "launcher": started.get("launcher"),
        "restarted": started.get("restarted"),
        "reason": started.get("reason"),
        "gpu_used_mib": checks.get("gpu_used_mib"),
        "allocation_present": checks.get("allocation_present"),
        "served_models": checks.get("served_models"),
        "weights_sha256": weights.get("weights_sha256"),
        "digest_seconds": weights.get("digest_seconds"),
        "declarations_ignored": claimed.get("declarations_ignored"),
    }


def _one_ramp(
    out: Path,
    base: str,
    model: str,
    host: str,
    engine: str,
    width: int | None,
    tokens: int,
    declared: dict[str, Any] | None = None,
) -> None:
    """One ramp, every level recorded so thresholds can be re-derived later."""
    original = contract.RAMP_TOKENS
    contract.RAMP_TOKENS = tokens
    started_at = contract.now()
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
                "started_at": started_at,
                "ended_at": contract.now(),
            },
        )
        return
    finally:
        contract.RAMP_TOKENS = original
    ended_at = contract.now()
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
            # #325: the curve on a timeline. `levels[].wall_s` sums to what
            # the requests took; this is when the ramp ran, so the phase's
            # remaining minutes can be attributed to the seams between rows.
            "started_at": started_at,
            "ended_at": ended_at,
            # D1: what the server SAYS, beside what the curve did, each with
            # its provenance. `configured_width` above is what this run asked
            # for; this is what the host reports it is running.
            "declared_slots": declared,
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
            # The three fields the sink dropped for a whole campaign. See
            # RAMP_ROW_DISPOSITION: `repeat_spread` is the only error bar any
            # speedup figure in this file will ever have.
            "speedup_vs_n1": result.get("speedup_vs_n1"),
            "repeats": result.get("repeats"),
            "repeat_spread": result.get("repeat_spread"),
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
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "skip samples already in --out. This is what makes a multi-hour "
            "phase restartable after a crash instead of restartable from zero."
        ),
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="with --resume, re-run samples that errored or refused",
    )
    args = parser.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    # #325: stamped once, when the run begins; `emit` puts it on every row.
    global STAMP
    STAMP = contract.provenance(argv=list(argv) if argv is not None else sys.argv[1:])
    started_at = STAMP["run_started_at"]
    began = time.monotonic()
    # Only the two phases that CONSULT `done` are told to resume. `fast` and
    # `load` ignore it, and printing "resuming: N samples" while re-running
    # everything is a message that is simply false.
    resumable = args.phase in ("ramp", "sleep")
    done = (
        completed(args.out, args.retry_failed) if args.resume and resumable else set()
    )
    if args.resume and not resumable:
        print(
            f"--resume has no effect on the {args.phase} phase: it does not "
            "consult prior samples",
            flush=True,
        )
    if done:
        print(f"resuming: {len(done)} samples already on disk", flush=True)
    if args.phase == "fast":
        fast(args.out, hosts, repeats=args.repeats)
    elif args.phase == "load":
        load(args.out, hosts, repeats=max(1, args.repeats // 15))
    elif args.phase == "sleep":
        sleep_state(args.out, hosts, done)
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
        ramp(
            args.out,
            hosts,
            tuple(e.strip() for e in args.engines.split(",")),
            done,
        )
    # #325: the phase's duration is a ROW, not only a print. The print went
    # to a log that no reader of the journal holds, and the journal could not
    # say how long the phase it records took, nor when. One row per
    # invocation: a phase `--resume`d twice holds two spans, which is true.
    ended_at = contract.now()
    emit(
        args.out,
        {
            "phase": args.phase,
            "metric": "phase",
            "started_at": started_at,
            "ended_at": ended_at,
            "seconds": contract.seconds_between(started_at, ended_at),
        },
    )
    print(f"{args.phase} finished in {time.monotonic() - began:.0f}s -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
