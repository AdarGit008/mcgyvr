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

import datetime
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import threading
import time
import types
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

#: Offered-concurrency levels: the KNEE ladder. Dense at the low end, because
#: that is where a narrow server's knee sits, and it is the default for a
#: survey entry that declares no ladder of its own.
#:
#: **#356, 2026-08-24: the top of this ladder is NOT above every plausible
#: width, and it never was.** The sentence that used to stand here said the
#: server's own limit bounds the curve rather than this number. Measured on
#: 2026-08-24 (`records/evidence/2026-08-24-config-sweep/`): with
#: `--max-num-seqs 256` and CUDA graphs on, srv1 peaks at n=128 and srv2 at
#: n=256, and n=384 was offered on srv2 and read lower than 256. A ladder that
#: stops at 24 cannot see either ceiling. It was never wrong for the D7 width
#: matrices, whose widest server was configured at 16 -- and that is the
#: point: the right top is a function of the width the server was launched
#: with, not a constant. :func:`ladder` is that function; this tuple is its
#: base and stays the survey default because a roster entry that has not
#: declared a width (ollama reports `total_slots = 1` for every model) has no
#: business being offered 384 queued requests -- on srv2's deep-spill models a
#: single level of 24 already costs 6-9 minutes per repeat
#: (`configs/d7-campaign.json`, E13).
RAMP_LEVELS: tuple[int, ...] = (1, 2, 3, 4, 6, 8, 12, 16, 24)

#: The knee ladder's continuation, in the same ~1.5x steps, for a server whose
#: configured width is past 16. Ends where both rigs' measured maxima end
#: (#356): 256 is the widest anything here has been launched at, and 384 is
#: the level that showed it was the top on srv2.
RAMP_LADDER_EXTENSION: tuple[int, ...] = (32, 48, 64, 96, 128, 192, 256, 384)


def ladder(width: int | None) -> tuple[int, ...]:
    """The levels to offer a server launched at ``width`` slots (#356).

    The knee ladder, continued by :data:`RAMP_LADDER_EXTENSION` until the
    first level at or past ``1.5 * width``, so the curve is measured past the
    point where the scheduler stops admitting -- the BL-4 rule that a curve is
    measured to its END or refused needs a level beyond the limit to be
    offered at all. A width of 16 or less, or no declared width, gets exactly
    :data:`RAMP_LEVELS`, which keeps every D7 row re-takeable as the cell it
    was.

    Measured 2026-08-24: a width-256 server peaks at 128 (srv1) and 256
    (srv2), and 384 -- this ladder's top for that width -- read below 256 on
    the rig that reached it, which is what "measured to its end" looks like.

    **What the wider ladder costs**, from the same sweep's wall-clocks at one
    repeat: srv1's levels 32..384 sum to roughly 33 minutes, so a two-repeat
    ramp at width 256 is about an hour on srv1 and about ten minutes on srv2.
    That is the price of seeing the ceiling and it is paid only by a server
    configured wide enough to have one.
    """
    if not width or width <= RAMP_LEVELS[-1] / 1.5:
        return RAMP_LEVELS
    levels = list(RAMP_LEVELS)
    for level in RAMP_LADDER_EXTENSION:
        levels.append(level)
        if level >= 1.5 * width:
            break
    return tuple(levels)


#: Each level runs twice and the better throughput is kept: one level can be
#: spoiled by an unlucky scheduler moment, and the knee is read off a curve.
#:
#: **#356, 2026-08-24: a variance guard, not a rate-derived number, and the
#: only spread on record is eager.** The D7 journal holds no losing repeat
#: (the `repeats` field landed after it ran), so the first `repeat_spread`
#: rows are 2026-08-23's cross-rig ramp, taken WITH `--enforce-eager`: the
#: second attempt won 4 of 9 levels on each rig, and max/min per level was at
#: most 1.015 on srv1 and 1.072 on srv2. That 7% is inside the 8% margin
#: :data:`PLATEAU_FRACTION` leaves, which is why `max` over two is kept: one
#: unlucky repeat at one level would move the saturation read. No spread has
#: been measured with graphs on -- the sweep ran one repeat -- so this is
#: invariant by construction (it does not read a rate) and unmeasured in the
#: new regime, and both halves of that are the record.
RAMP_REPEATS = 2

#: The orders a ramp may offer its levels in (#327). The readers sort by ``n``
#: before reading, so the curve is the same whichever was run; the order is
#: written on the row so a card that warmed across the ramp can be told from
#: one that did not.
RAMP_ORDERS: tuple[str, ...] = ("ascending", "descending", "shuffled")

#: Tokens per request, capped so every request is the SAME amount of work.
#:
#: **D3, 2026-08-19.** 128 was too short to be a throughput measurement: at that
#: length the per-request fixed costs — scheduling, prefill, the first token —
#: are a large share of the reply, so the curve reads the overhead as much as
#: the rate. 475 is an **interpolation** between the two measured columns of the
#: calibration matrix (128 and 512) — a judgement against measured curves, and
#: not itself a measured point. D7 item 6 re-runs srv1 at this budget precisely
#: to confirm the interpolation on the host whose matrix is already known.
#:
#: **Two** models on the roster spend this budget differently, not one.
#: ``gpt-oss:20b`` emits hidden reasoning — measured at ~72% of its output on a
#: readiness probe, heavier than the ~52% on record — and
#: ``nemotron-3-nano:4b``, which is on **both** rigs' rosters, ran ~69% hidden
#: ``thinking`` (54 tokens for a 17-token visible reply). For both,
#: ``completion_tokens`` counts reasoning tokens, so 475 buys roughly a third of
#: that in visible text. Throughput is still throughput; the quantity simply is
#: not comparable to a non-reasoning model's visible-token rate.
#:
#: **#356, 2026-08-24: re-derived with CUDA graphs on, and it survives.**
#: D3's matrix was taken under `--enforce-eager`, worth 5.02x on srv2, so the
#: rate its overhead argument was made against was 5x low there. Measured
#: at 128/256/475/1024 tokens on both rigs
#: (`records/evidence/2026-08-24-ramp-tokens/`): at a single stream 475
#: reads 97% (srv1) / 95% (srv2) of the 1024-token rate and 128 reads 81% /
#: 77%. The per-request overhead is not fixed in seconds -- 0.79 s on srv1,
#: 0.22 s on srv2 -- so its share of a 475-token reply is 6.9% / 8.3% on
#: both rigs, and a budget chosen against a share survives the rate moving.
#: Past the knee, 1024 reads 6-10% BELOW 475: a longer sequence is more KV to
#: attend over per step, a different regime rather than a better reading.
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
#:
#: **#356, 2026-08-24: re-read on curves that are not 5x depressed.** The 104
#: launched cells of `records/evidence/2026-08-24-config-sweep/` -- 68 with
#: `--enforce-eager`, 36 with graphs on -- were read at 0.90, 0.92 and 0.95.
#: 0.92 and 0.95 agree on every one of the 104; 0.90 disagrees on two srv2
#: graph cells (`g-1.5B-seqs384`: 128 against 256). The plateau this defines
#: is the same object with graphs on. One caveat the sweep cannot remove: its
#: ladder is powers of two, so a knee between levels is invisible to it where
#: D7's dense low end would see it -- the agreement is at the sweep's
#: resolution.
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
#:
#: **#356, 2026-08-24: the boundary is far from every graphs-on curve.** D7
#: showed 0.02 separating "excluded" from "valid" (srv1 width 1 at 1.00
#: against srv2's 1.02,
#: `archive/docs/archive/evidence-prose/calibration-2026-08-19/README.md:996-1000`)
#: -- both were width-1 servers under eager. On the 2026-08-24 sweep the lowest max
#: speedup over n=1 is 3.39 (srv1, eager) and 3.61 (srv1, graphs); srv2's
#: lowest is 7.5. Nothing is within a factor of three of the floor, so the
#: constant excludes nothing in the new regime and its sensitivity stays a
#: width-1 property, which no re-derivation of the number moves.
INFERRED_SATURATION_MIN_SPEEDUP = 1.0

#: The floor aggregate rate a level is given time to achieve, in tokens/second.
#:
#: **BL-4, 2026-08-19.** The per-request cap was a flat 600 s, set when
#: :data:`RAMP_TOKENS` was 128. D3 raised the budget to 475 — 3.7x — without
#: revisiting it. A level of ``n`` requests on a one-slot server finishes in
#: roughly ``n * RAMP_TOKENS / rate``, so at 475 tokens a flat 600 s silently
#: required 12.7 tok/s at n=16 and **19.0 at n=24**. The two deep-spill models
#: on the roster sit near or below that line — and D4's withdrawal is precisely
#: what admits them to a ramp for the first time. Their top levels would have
#: timed out, been dropped, and (before this same fix) produced a truncated
#: saturation point reported clean.
#:
#: 4 tok/s is deliberately below anything measured on these rigs: the cap exists
#: to bound a hung request, not to score a slow one.
#:
#: **#356, 2026-08-24: checked against the wider ladder, where it could bind.**
#: The 2026-08-24 sweep offered up to n=384; at n=256 on srv1 a single stream
#: ran 0.79 tok/s, which is BELOW this floor per stream -- and the floor is an
#: aggregate: the level's budget is ``n * RAMP_TOKENS / 4 + 90``, 30,490 s at
#: n=256, against a measured level wall of 413 s. Across all 104 launched
#: cells the slowest request used 14.9% of its budget (srv1, n=2,
#: `linear-triton`). A rate 5x higher makes the cap looser still; the
#: direction of the misconfiguration runs away from this constant.
RAMP_FLOOR_TOKENS_PER_S = 4.0

#: Added to every per-request budget, for connection setup and prefill.
#: **#356:** the prompt is short and identical, prefill is milliseconds on
#: either rig, and the first graph replay is paid by the discarded warm-up
#: request in :func:`ramp`, not by a timed level. Invariant to the serving
#: configuration by construction.
RAMP_TIMEOUT_BASE_S = 90.0

#: A card holding less than this is idle: a few hundred MiB is display and
#: compositor overhead on these headless rigs, and a model is gigabytes.
IDLE_GPU_MIB = 500

#: How long a cleanup or reading step may take. Generous on purpose — at 30s a
#: step timed out on a box thrashing with a 36 GB model in page cache and
#: returned nothing, and a cleanup step that fails SILENTLY is worse than none.
#: **#356:** bounds ssh steps -- `nvidia-smi`, `docker rm`, `pgrep`, a page
#: cache drop -- none of which runs inside the engine or reads its rate.
#: Invariant to the serving configuration by construction.
STEP_TIMEOUT_S = 180.0

#: Where every number above came from (#356). A constant can be pinned by a
#: marker in `launch.py` while the run behind it is void, and nothing said so:
#: the D7 campaign's every ramp ran under `--enforce-eager`, worth 5.02x on
#: srv2, and the constants it produced kept governing the next campaign.
#: This table is the fix. Each entry names the run a constant was derived
#: from or re-read against, the date, and whether it was **derived** from
#: that run's curves or is **invariant** to the serving configuration for a
#: stated reason. `tests/test_serving.py` refuses a numeric constant in this
#: module with no entry, an entry naming no run on disk, and an entry naming
#: a constant that does not exist.
PROVENANCE: dict[str, dict[str, str]] = {
    "RAMP_LEVELS": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-24",
        "kind": "derived",
        "note": "knee ladder kept as the survey default; ladder() extends it "
        "to 384 for a width past 16, because both rigs' maxima sit at 128-256",
    },
    "RAMP_LADDER_EXTENSION": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-24",
        "kind": "derived",
        "note": "ends at 384, the level that read below 256 on srv2",
    },
    "PROBE_INTERVAL_S": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-31",
        "kind": "invariant",
        "note": "reads no rate: it samples an endpoint beside the measurement "
        "and never enters it. Sized against the levels in that run, whose "
        "shortest is tens of seconds, so a 2 s period samples every level "
        "many times over while adding one GET per period to a server that is "
        "already serving n streams",
    },
    "RAMP_REPEATS": {
        "run": "records/evidence/2026-08-23-cross-rig",
        "date": "2026-08-24",
        "kind": "invariant",
        "note": "reads no rate; the only spread on record is eager, max/min "
        "1.015 srv1 / 1.072 srv2, second attempt won 4 of 9 levels each",
    },
    "RAMP_TOKENS": {
        "run": "records/evidence/2026-08-24-ramp-tokens",
        "date": "2026-08-24",
        "kind": "derived",
        "note": "re-measured with graphs on at 128/256/475/1024 tokens on "
        "both rigs; see that directory's README for the reading",
    },
    "PLATEAU_FRACTION": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-24",
        "kind": "derived",
        "note": "0.92 and 0.95 agree on all 104 launched cells, eager or not; "
        "0.90 differs on two",
    },
    "LATENCY_TOLERANCE": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-24",
        "kind": "invariant",
        "note": "informational, never a gate; nothing downstream reads it",
    },
    "INFERRED_SATURATION_MIN_SPEEDUP": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-24",
        "kind": "derived",
        "note": "lowest graphs-on max speedup is 3.61; the 0.02 boundary case "
        "is a width-1 property and no graphs-on cell is within 3x of it",
    },
    "RAMP_FLOOR_TOKENS_PER_S": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-24",
        "kind": "derived",
        "note": "slowest request used 14.9% of its budget across 104 cells "
        "and a ladder to 384; a faster rig loosens it further",
    },
    "RAMP_TIMEOUT_BASE_S": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-24",
        "kind": "invariant",
        "note": "short identical prompt; the first graph replay is the "
        "discarded warm-up's",
    },
    "IDLE_GPU_MIB": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-24",
        "kind": "invariant",
        "note": "a released card reads 1 MiB on both rigs after every one of "
        "140 cells; the engine's configuration does not touch an idle card",
    },
    "STEP_TIMEOUT_S": {
        "run": "records/evidence/2026-08-24-config-sweep",
        "date": "2026-08-24",
        "kind": "invariant",
        "note": "bounds ssh steps outside the engine",
    },
}


class NotCleanError(RuntimeError):
    """A backend could not reach a state worth measuring, so nothing was.

    Raised, never warned. Every discarded reading in this instrument's history
    came from a measurement that ran anyway on a machine that was not ready,
    and each looked plausible until its baseline was read.
    """


class RefusedError(NotCleanError):
    """A refusal whose reasons are readable without parsing the sentence.

    **D8's third recorded defect**: "a refused ``vram_fraction`` is recoverable
    only by regex over the prose in ``why``". Building a list of clean reason
    codes and then interpolating them into the message reproduces that defect
    with extra steps — the codes exist, and a consumer still has to get them
    back out of a string. They travel as a list.

    Subclasses :exc:`NotCleanError` so every existing handler is unchanged.
    """

    def __init__(
        self,
        message: str,
        reasons: list[str] | None = None,
        attempts: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.reasons = reasons or []
        # #326: the trail the refusal was decided on, as data. Before this a
        # refused load left no attempt record anywhere -- `run.py` recorded
        # the reasons and the load row recorded nothing -- so the cost side
        # of LOAD_ATTEMPTS (does a second attempt ever rescue a first?) was
        # unanswerable from either sink.
        self.attempts = attempts or []


# --- the clock, and the tree that ran (#325) ---------------------------------
#
# Every duration this harness recorded before #325 was a `time.monotonic()`
# delta. A delta cannot be placed on a timeline, so on the 2026-08-20 campaign
# 8,185 s of a 14,404 s ramp phase belonged to no row, and no journal named
# the commit, the config or the moment the run began: that the campaign ran
# from session 5's tree was inferred from the clock and recorded nowhere.
#
# One clock seam, `now`, and one stamp, `provenance`. Rows carry instants as
# UTC ISO-8601 strings so a reader can order them across files and against a
# log; tests stub `now` and drive it, which is how the remainder of a phase is
# shown to be a sum of named terms rather than a number nobody can account for.

#: The serving harness, as a surface for :func:`provenance`'s
#: ``harness_sha256`` -- ``product.digest``'s shape (path and content, derived
#: files excluded) over this directory. Not the product surface: the product
#: is what a bench measures, and this is the instrument that measures a rig.
HARNESS_SURFACE: tuple[str, ...] = ("tools/bench/serving",)


def stamp(epoch: float) -> str:
    """An instant as a UTC ISO-8601 string, millisecond precision, ``+00:00``."""
    when = datetime.datetime.fromtimestamp(epoch, datetime.UTC)
    return when.isoformat(timespec="milliseconds")


def now() -> str:
    """The wall clock, as :func:`stamp` renders it. THE seam: stub this."""
    return stamp(time.time())


def seconds_between(started_at: str, ended_at: str) -> float:
    """The span between two :func:`stamp` strings, in seconds."""
    begin = datetime.datetime.fromisoformat(started_at)
    end = datetime.datetime.fromisoformat(ended_at)
    return round((end - begin).total_seconds(), 3)


#: Every field :func:`provenance` returns, and the row key each reaches. Every
#: one is carried, so there is no ``PROVENANCE_DROPPED``. The sinks merge the
#: stamp under these keys (``calibrate.emit``, ``run._journal``) and
#: ``tests/test_sink_conformance.py`` holds the key set to this table.
PROVENANCE_DISPOSITION: dict[str, tuple[str, ...]] = {
    "commit": ("commit",),
    "commit_unknown_reason": ("commit_unknown_reason",),
    "tree_dirty": ("tree_dirty",),
    "harness_sha256": ("harness_sha256",),
    "config_sha256": ("config_sha256",),
    "argv": ("argv",),
    "run_started_at": ("run_started_at",),
}

#: The files each tree-reading provenance field answers about. :func:`provenance`
#: reads its pathspec and its digest surface from here and states neither
#: itself, so the disposition above and the computation below cannot drift
#: apart from the surface they describe.
#:
#: ``tree_dirty`` and ``harness_sha256`` are one claim in two halves -- *these
#: bytes ran*, and *a commit names them* -- so they answer about one surface or
#: they can disagree about which tree they mean. #334: ``tree_dirty`` was
#: computed over the whole working tree, which a run turns ``true`` by writing
#: its own journal under ``records/``, so every row of every future run would
#: have read ``true`` because of its own output. A field that is ``true`` on
#: every real run states no property (ADR-0026 lens 3), and it is the coarse
#: half of the pair that breaks, because the digest is exact.
#:
#: ``commit`` is deliberately absent: ``HEAD`` is the repository's, not a
#: surface's, and scoping it would be a different claim rather than a narrower
#: one.
PROVENANCE_SURFACE: dict[str, tuple[str, ...]] = {
    "tree_dirty": HARNESS_SURFACE,
    "harness_sha256": HARNESS_SURFACE,
}


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(REPO), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _product() -> types.ModuleType:
    slot = "bench_product"
    cached = sys.modules.get(slot)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        slot, REPO / "tools" / "bench" / "product.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[slot] = module
    spec.loader.exec_module(module)
    return module


def provenance(
    config_bytes: bytes | None = None, argv: list[str] | None = None
) -> dict[str, Any]:
    """What ran, from where, starting when -- stamped onto every row.

    ``commit`` is ``HEAD`` and ``tree_dirty`` says whether that names the code
    that ran -- **the harness surface, not the working tree**
    (:data:`PROVENANCE_SURFACE`, #334). A SHA on a dirty tree is worse than
    none (``product.py``), so the two travel together, and ``harness_sha256``
    is over that same surface -- ``product.digest``'s own algorithm, reused
    rather than rebuilt. A surface entry that has gone missing is silent to
    ``git status`` (a pathspec matching nothing exits 0) and raises in
    ``product.surface_files``, so the pair refuses rather than reading clean.
    No git at all is recorded as such, beside ``commit: null``, rather than
    raised: a run on a box without git is still a run whose rows deserve a
    clock.

    ``config_sha256`` is over the bytes the survey read (``run.py`` has a config
    file; ``calibrate.py`` has none and carries ``argv``, which both do).
    ``run_started_at`` is :func:`now` at the moment this is called, which the
    callers make the moment the run begins.
    """
    head = _git("rev-parse", "HEAD")
    status = _git(
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *PROVENANCE_SURFACE["tree_dirty"],
    )
    reason = None if head else "git rev-parse HEAD failed: no git, or not a repository"
    return {
        "commit": head.strip() if head else None,
        "commit_unknown_reason": reason,
        "tree_dirty": None if status is None else bool(status.strip()),
        "harness_sha256": _product().digest(REPO, PROVENANCE_SURFACE["harness_sha256"]),
        "config_sha256": (
            None if config_bytes is None else hashlib.sha256(config_bytes).hexdigest()
        ),
        "argv": list(argv) if argv is not None else None,
        "run_started_at": now(),
    }


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
    # The door's transport, imported when called and not when this module
    # loads: the tests that stub this function never touch gatelib, and outside
    # a door run gatelib refuses with SystemExit naming the door. That refusal
    # propagates -- `except Exception` is for a timeout or a dead host, which
    # are readings, and never for the door saying no.
    from mcgyvr.serving.gatelib import ssh as door_ssh

    try:
        proc = door_ssh(host, command, timeout=timeout)
    except Exception:
        return None
    return proc.stdout.strip() or None


#: Which processes hold this card, and how much of it each one holds. Declared
#: rather than inlined because it now has two readers: :func:`snapshot`, which
#: records the line, and ``vllm.placements``, which computes from it. The
#: run contract's own warning was that this tree keeps minting idle readings —
#: this string appeared once, in `snapshot`, and nothing in the tree consumed
#: it. A second inline copy is how the two would come to mean different things.
COMPUTE_APPS_COMMAND = (
    "nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader"
)

#: Printed after the reading so an EMPTY card can be told from a card that was
#: never read. :func:`ssh` returns ``None`` for empty stdout, which collapses
#: "no process holds this card" into "the host did not answer" — the same
#: direction :func:`snapshot` refuses for ``gpu_idle`` below, one reading over.
COMPUTE_APPS_END = "__compute_apps_end__"

#: What a caller that must tell those two apart runs. :func:`snapshot` keeps
#: the bare command, because its row records stdout verbatim.
#:
#: **``&&``, not ``;``.** A missing or failing ``nvidia-smi`` writes to stderr
#: and prints nothing on stdout, so a ``;`` would print the sentinel anyway and
#: the parser would read the card as EMPTY — the very collapse the sentinel is
#: here to prevent, restored by the separator. Conjunction costs nothing: the
#: query exits 0 when no process holds the card.
COMPUTE_APPS_PROBE = f"{COMPUTE_APPS_COMMAND} && echo {COMPUTE_APPS_END}"


def compute_apps(raw: str | None) -> list[dict[str, Any]] | None:
    """:data:`COMPUTE_APPS_PROBE`'s output as one row per process on the card.

    ``[{"pid": 1133972, "card_mib": 3126}, ...]``, in the order the driver
    reported them. ``None`` — never ``[]`` — when the sentinel is absent, which
    is the read not completing: an unreachable host, a missing ``nvidia-smi``,
    a timeout. ``[]`` is a card that answered and holds nothing.

    A row whose memory the driver would not state (``[N/A]`` under MIG, or
    without the permission to attribute another user's process) keeps its pid
    and carries ``card_mib: None``. A pid that is not an integer is dropped:
    it is not a process, it is a header or an error line.
    """
    if raw is None or COMPUTE_APPS_END not in raw:
        return None
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if COMPUTE_APPS_END in line:
            break
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        rows.append({"pid": int(parts[0]), "card_mib": first_int(parts[1])})
    return rows


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
        "gpu_compute_apps": COMPUTE_APPS_COMMAND,
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


#: The one hardware read the identity block is built from (#326). One
#: `nvidia-smi` line: name, total memory, driver, compute capability.
HARDWARE_COMMAND = (
    "nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap "
    "--format=csv,noheader"
)

#: Identity fields no run can answer today, each with the reason (ADR-0027 D2:
#: null plus a reason, never a blank and never a number copied from prose).
HARDWARE_UNANSWERABLE: dict[str, str] = {
    "memory_bandwidth_gb_s": (
        "not measured by any run: the 21.8 / 13.3 GB/s figures in ADR-0024:40 "
        "and records/evidence/calibration-2026-08-19/README.md were taken "
        "pre-XMP and never re-taken (step0-gaps.md:202); a run that wants "
        "the number declares it in its #322 header and measures it"
    ),
}


def hardware(host: str) -> dict[str, Any]:
    """The card, once per host: ``{"identity": {...}, "refusals": {...}}``.

    A field the host did not answer is ``null`` in ``identity`` and its
    command is in ``refusals`` under the same name, the shape
    :func:`snapshot` already uses per reading.
    """
    fields = ("gpu_name", "gpu_total_mib", "driver_version", "compute_capability")
    raw = ssh(host, HARDWARE_COMMAND)
    parts = [p.strip() for p in (raw or "").split(",")] if raw else []
    identity: dict[str, Any] = dict.fromkeys(fields)
    refusals: dict[str, str] = {}
    if len(parts) == 4:
        identity["gpu_name"] = parts[0]
        identity["gpu_total_mib"] = first_int(parts[1])
        identity["driver_version"] = parts[2]
        identity["compute_capability"] = parts[3]
    for field in fields:
        if identity[field] is None:
            refusals[field] = HARDWARE_COMMAND
    for field, why in HARDWARE_UNANSWERABLE.items():
        identity[field] = None
        refusals[field] = why
    return {"identity": identity, "refusals": refusals}


#: The card's state (#327): what the silicon was doing, read at the end of
#: every recorded ramp level and once at a vLLM claim. One `nvidia-smi` line,
#: units stripped so the fields parse as numbers; the throttle mask is kept as
#: the hex the driver prints (NVML's clocksThrottleReasons bits: ``0x1`` idle,
#: ``0x4`` the SW power cap, ``0x8`` HW slowdown, ``0x20`` SW thermal,
#: ``0x40`` HW thermal) and decoded by the reader, not here.
CARD_STATE_QUERY = "temperature.gpu,power.draw,clocks.sm,clocks_throttle_reasons.active"
#: `timeout 10`: an `nvidia-smi` that hangs on a wedged driver would otherwise
#: hold every recorded level for `STEP_TIMEOUT_S`, and the load average behind
#: the `;` would never be read. No run has shown that hang; the bound is cheap.
CARD_STATE_COMMAND = (
    f"timeout 10 nvidia-smi --query-gpu={CARD_STATE_QUERY} "
    "--format=csv,noheader,nounits"
)
CARD_FIELDS: tuple[str, ...] = (
    "temperature_c",
    "power_w",
    "sm_clock_mhz",
    "throttle_reasons",
)

#: The level reader's one ssh: the card line, then the rig's load average, as
#: two commands so a failed `nvidia-smi` still leaves the load on the record.
LEVEL_STATE_COMMAND = f"{CARD_STATE_COMMAND}; cat /proc/loadavg"

#: What the driver-side read is called in a ``why``: the load on the machine
#: whose clock ``wall_s`` comes from, which is this one, not the rig.
CLIENT_LOADAVG_COMMAND = "os.getloadavg()"


def _float(text: str | None) -> float | None:
    """``text`` as a float, or ``None`` — `nvidia-smi` prints "[N/A]"."""
    try:
        return float((text or "").strip())
    except ValueError:
        return None


def _int(text: str | None) -> int | None:
    """``text`` as an integer, or ``None`` -- whole numbers only, no "45 MiB"."""
    figure = _float(text)
    return None if figure is None or figure != int(figure) else int(figure)


def card_state(raw: str | None, command: str = CARD_STATE_COMMAND) -> dict[str, Any]:
    """One :data:`CARD_STATE_QUERY` line as the four card fields.

    A field the card did not answer is ``null`` and ``why`` names the command
    that was run — never ``0``, never an absent key (the rule
    :func:`snapshot` applies to ``gpu_idle``, applied per field). ``why`` is
    ``None`` when every field answered.
    """
    line = raw.strip().splitlines()[0] if raw and raw.strip() else ""
    parts = [p.strip() for p in line.split(",")] if line else []
    card: dict[str, Any] = dict.fromkeys(CARD_FIELDS)
    if len(parts) == 4:
        card["temperature_c"] = _int(parts[0])
        card["power_w"] = _float(parts[1])
        card["sm_clock_mhz"] = _int(parts[2])
        card["throttle_reasons"] = parts[3] if parts[3].startswith("0x") else None
    card["why"] = (
        None if all(card[field] is not None for field in CARD_FIELDS) else command
    )
    return card


def loadavg(line: str | None) -> list[float] | None:
    """``/proc/loadavg``'s three figures, or ``None`` for anything else."""
    parts = (line or "").split()
    if len(parts) < 3:
        return None
    try:
        return [float(part) for part in parts[:3]]
    except ValueError:
        return None


def client_loadavg() -> list[float] | None:
    """The driver's own load, the machine every ``wall_s`` is clocked on."""
    try:
        return [round(figure, 2) for figure in os.getloadavg()]
    except OSError:
        return None


def level_state(raw: str | None, client: list[float] | None) -> dict[str, Any]:
    """The two blocks a recorded level carries (#327), from one ssh's stdout.

    ``card`` is the rig's silicon at the level's end; ``ambient`` is the load
    on both machines -- the rig the tokens come from, and the driver whose
    clock ``wall_s`` is read from (E14, ``launch.py``). Either block's ``why``
    names what did not answer, and is ``None`` when everything did.
    """
    lines = [line for line in (raw or "").splitlines() if line.strip()]
    card_line = next((line for line in lines if line.count(",") == 3), None)
    # `nvidia-smi` reports its own failures on STDOUT ("No devices were
    # found", "Failed to initialize NVML: ..."), comma-less and three words
    # or more; `/proc/loadavg` is the LAST line and the only one that parses.
    host_load = next(
        (figures for figures in map(loadavg, reversed(lines)) if figures), None
    )
    failed = [
        command
        for reading, command in (
            (host_load, LEVEL_STATE_COMMAND),
            (client, CLIENT_LOADAVG_COMMAND),
        )
        if reading is None
    ]
    return {
        "card": card_state(card_line, LEVEL_STATE_COMMAND),
        "ambient": {
            "host_loadavg": host_load,
            "client_loadavg": client,
            "why": " and ".join(failed) or None,
        },
    }


#: How often the in-flight probe asks, while a level runs. Two seconds against
#: levels that run tens of seconds to minutes: enough samples to catch a width
#: that never opened, few enough that the probe is not itself load.
PROBE_INTERVAL_S = 2.0


def in_flight(samples: list[dict[str, Any]], offered: int) -> dict[str, Any] | None:
    """What the server said it was doing while the level was in flight.

    **The question this answers.** A ramp that offers n=32 to a server admitting
    8 at a time measures four sequential batches and records their aggregate as
    one level. The curve flatlines, `outcome` stays `ok`, and nothing in the row
    says which of the two happened -- saturation, or a queue. `max_running` is
    the most the server ever ran at once; if it is below `offered`, the level
    was never the width it is labelled.

    `null` when nothing was sampled, which is the warm-up level and any engine
    with no endpoint to ask. An unasked question is not an answer of zero.
    """
    if not samples:
        return None
    running = [int(s["running"]) for s in samples if s.get("running") is not None]
    waiting = [int(s["waiting"]) for s in samples if s.get("waiting") is not None]
    return {
        "samples": len(samples),
        "max_running": max(running) if running else None,
        "max_waiting": max(waiting) if waiting else None,
        "offered": offered,
        # The finding, precomputed, because the comparison is the whole point
        # and a reader who has to do it themselves will not.
        "reached_offered": (max(running) >= offered) if running else None,
    }


def read_level_state(host: str) -> str | None:
    """The level reader's one ssh (#327): card and load in one round trip.

    Its cost is ``len(levels) * RAMP_REPEATS`` calls per ramp -- 18 at the
    default matrix -- each one ``ssh_step_seconds`` (p50 0.956 s, p95 1.40 s
    on 2026-08-19, records/evidence/calibration-2026-08-19/README.md:20),
    against ramps of ~24 min on vLLM and ~8.1 min on ollama at 475 tokens
    (README.md:554). The warm-up level reads nothing. No budget is fixed
    here: the next run's record states what the calls cost beside the
    durations they sat inside.
    """
    return ssh(host, LEVEL_STATE_COMMAND)


def draw_seed(order: str, seed: int | None) -> int | None:
    """The seed a ``shuffled`` order runs under: the one given, or one drawn
    here so the row can carry it -- a shuffle nobody can reproduce is not a
    measurement condition. Any other order has no seed."""
    if order != "shuffled":
        return None
    return seed if seed is not None else random.SystemRandom().randrange(2**32)


def order_levels(
    levels: tuple[int, ...], order: str = "ascending", seed: int | None = None
) -> tuple[int, ...]:
    """The sequence a ramp offers its levels in (#327), from an order name."""
    if order not in RAMP_ORDERS:
        raise ValueError(f"{order!r} is not a ramp order; one of {RAMP_ORDERS}")
    ordered = sorted(levels)
    if order == "descending":
        ordered.reverse()
    elif order == "shuffled":
        random.Random(seed).shuffle(ordered)
    return tuple(ordered)


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


def get_text(target: str, timeout: float = 10.0) -> str | None:
    """GET a document that is not JSON -- a Prometheus exposition, say -- or
    ``None`` on any failure at all. Same contract as :func:`get_json`, one
    decode less: what answers here is text by design, and parsing it belongs to
    the caller that knows what it asked for."""
    try:
        with urllib.request.urlopen(target, timeout=timeout) as response:
            return str(response.read().decode("utf-8", "replace"))
    except Exception:
        return None


# --- the ramp ---------------------------------------------------------------
#
# Shared because it belongs to no engine: OpenAI-compatible chat completions and
# arithmetic over the token counts the server itself reports.


def ramp(
    base: str,
    model: str,
    levels: tuple[int, ...] = RAMP_LEVELS,
    *,
    host: str | None = None,
    reader: Callable[[], str | None] | None = None,
    probe: Callable[[], dict[str, Any] | None] | None = None,
    order: str = "ascending",
    seed: int | None = None,
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

    ``host`` is the rig the tokens come from; ``reader`` is the per-level seam
    (#327), one call at the end of every recorded level, by default
    :func:`read_level_state` on ``host`` and a read of nothing when there is no
    host. ``order`` and ``seed`` say what sequence the levels were offered in;
    the readers below sort by ``n`` first, so the curve is the same whichever
    ran, and the row says which did.
    """
    seed = draw_seed(order, seed)
    levels_run = order_levels(levels, order, seed)
    # No host and no reader: nothing is asked, and the rows say so with the
    # command that was not run -- not a refusal dressed as a read.
    read = reader
    if read is None and host:
        read = lambda: read_level_state(host)  # noqa: E731
    _level(base, model, 1)  # warm, and discard: a cold load would be charged
    # **D6/D7 item 7: keep every repeat.** `max` over repeats is what the curve
    # is read from, and that biases the PEAK — which is the denominator of
    # `saturation_n`'s whole definition. The size of that bias has never been
    # quantified, and it is quantifiable at **no rig time at all**, because the
    # losing repeat has already been paid for. Discarding it made the one
    # measurement that could settle it unrecoverable afterwards.
    attempts = [
        [_level(base, model, n, reader=read, probe=probe) for _ in range(RAMP_REPEATS)]
        for n in levels_run
    ]
    # #327: every reader below -- the n=1 baseline, the plateau scans, the
    # "measured to its end" check -- walks the list in order and assumed it
    # was ascending. Sorted ONCE here, by `n`, repeats kept in the order they
    # ran, so the same curve reads the same whichever order offered it.
    attempts = sorted(attempts, key=lambda group: group[0]["n"])
    rows = [max(group, key=lambda row: row["tokens_per_s"] or 0) for group in attempts]
    # `or 1` silently turned every speedup into a raw tokens/second figure
    # whenever the n=1 level read zero — same column, different quantity, no
    # indication which. `None` says the ratio has no baseline.
    first = rows[0]["tokens_per_s"]
    return {
        "levels": rows,
        # #327: the order the levels were OFFERED in, as run, beside the sorted
        # curve -- the only way to tell a card that warmed across the ramp
        # from one that did not.
        "levels_run": list(levels_run),
        "level_order": order,
        "level_seed": seed,
        "speedup_vs_n1": (
            None
            if not first
            else [round((row["tokens_per_s"] or 0) / first, 2) for row in rows]
        ),
        "repeats": attempts,
        "repeat_spread": [
            {
                "n": group[0]["n"],
                "tokens_per_s": [row["tokens_per_s"] for row in group],
                # The bias `max` introduces at this level, as a fraction. D6
                # wants the distribution; this is the one-number summary of it.
                "max_over_min": (
                    None
                    if not all(row["tokens_per_s"] for row in group)
                    else round(
                        max(row["tokens_per_s"] for row in group)
                        / min(row["tokens_per_s"] for row in group),
                        3,
                    )
                ),
            }
            for group in attempts
        ],
        "saturation": saturation(rows),
        # The SAME set `saturation` decided on. These two blocks land in one
        # emitted row, and computing them on different sets produced a row
        # saying `saturation_n: 4` and `throughput_plateau_n: 16` about one
        # measurement — the one-field-two-meanings defect D1 fixed, one level
        # further down. `readings` states which set it used.
        "readings": readings(rows),
        "method": (
            "aggregate throughput against offered concurrency. The lowest level "
            "reaching PLATEAU_FRACTION of peak is the SATURATION POINT, which "
            "is a property of this host under this load — not a slot count, and "
            "not comparable across token budgets"
        ),
    }


def usable(
    levels: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a ramp into the levels worth reading and the ones that are not.

    **Any** loss disqualifies a level, not total loss. The first version dropped
    a level only when NOTHING was countable, which left the halfway case as the
    dangerous one: ``completion_tokens_total`` sums the replies that carried a
    ``usage`` block while ``wall_s`` is the wall of all ``n`` of them, so a level
    where 8 of 16 replies came back without ``usage`` reports exactly half its
    true throughput, with ``errors: 0``, and reads as clean data. That is the
    "could not count becomes does not batch" defect — fixed, at first, for the
    all-or-nothing case only.

    One definition, used by :func:`saturation` and :func:`readings` both, so the
    two cannot disagree about which measurement they describe.
    """

    def unusable(row: dict[str, Any]) -> bool:
        return bool(row.get("errors")) or row.get("counted", 0) != row.get("ok", 0)

    clean = [row for row in levels if not unusable(row) and row.get("counted")]
    dropped = [
        {
            "n": row["n"],
            "errors": row.get("errors", 0),
            "error_kinds": row.get("error_kinds") or [],
            "uncounted": row.get("ok", 0) - row.get("counted", 0),
        }
        for row in levels
        if unusable(row) or not row.get("counted")
    ]
    return clean, dropped


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
    ollama ``-np 2``            4                   1.71            2
    ollama ``-np 1``            —                   —               1
    ==========================  ==================  ==============  ==========

    The ollama plateau column is stated **at the shipped**
    :data:`PLATEAU_FRACTION` **of 0.92**. It read 6 in the original record,
    which was computed at 0.95 before D2 moved the constant; the vLLM columns
    are unchanged at either value. Re-deriving it here rather than copying the
    old table forward is the point — the number is a function of the fraction,
    which is why the fraction travels with every emitted value.

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

    clean, dropped = usable(levels)
    # **Any** loss, not total loss. The first version dropped a level only
    # when NOTHING was countable, which left the halfway case as the
    # dangerous one: `tokens` sums the replies that carried a `usage` block
    # while `wall` is the wall of all `n` of them, so a level where 8 of 16
    # replies came back without `usage` reports exactly half its true
    # throughput, with `errors: 0`, and reads as clean data. That is the
    conditions = {
        "ramp_tokens": RAMP_TOKENS,
        "plateau_fraction": PLATEAU_FRACTION,
        # D8 names three parameters every derived number must ship with, and
        # this is the third: `max` over repeats biases the PEAK, which is the
        # denominator of this whole definition, so the repeat count is not
        # decoration.
        "ramp_repeats": RAMP_REPEATS,
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
    # **A curve needs more than one point.** With only n=1 surviving,
    # `_max_speedup` is exactly 1.0 by construction, the degenerate-curve guard
    # below is written against a strict comparison, and the plateau is the only
    # level there is — so a ramp in which every level but the first failed
    # reported `saturation_n: 1` as a clean answer, with the evidence of failure
    # demoted to a sibling field.
    if len(clean) < 2:
        return {
            "n": None,
            "refused": (
                f"only level n={clean[0]['n']} survived; a curve with one point "
                f"has no saturation point, and the rest were dropped: {dropped}"
            ),
            **conditions,
        }
    # **The top of the curve is the peak, and the peak is the denominator.**
    # Dropping a level from the MIDDLE is safe — the plateau is still found
    # against the true peak. Dropping the HIGHEST offered level truncates the
    # curve and recomputes the peak on what is left, so the saturation point
    # comes back lower than it is, with no refusal. This is the expected path
    # for a model whose requests time out at high concurrency, which is exactly
    # what D4's withdrawal newly admits to a ramp.
    if clean[-1]["n"] != levels[-1]["n"]:
        return {
            "n": None,
            "refused": (
                f"the curve was not measured to its end: level "
                f"n={levels[-1]['n']} was offered and dropped, so the peak this "
                f"fraction is taken against is a truncation. Dropped: {dropped}"
            ),
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
    if speedup <= INFERRED_SATURATION_MIN_SPEEDUP:
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
    clean, dropped = usable(levels)
    speedup = _max_speedup(clean)
    return {
        # Computed on the SAME set `saturation` decided on. These two blocks
        # land in one emitted row, and computing them on different sets produced
        # a row saying `saturation_n: 4` and `throughput_plateau_n: 16` about one
        # measurement — the one-field-two-meanings defect D1 fixed, one level
        # further down.
        "levels_used": [row["n"] for row in clean],
        "levels_dropped": [row["n"] for row in dropped],
        "throughput_plateau_n": _throughput_plateau(clean),
        "latency_plateau_n": _latency_plateau(clean),
        "max_speedup_vs_n1": speedup,
        "note": (
            "both plateaus are reported because their disagreement is readable: "
            "on a wide server they differ by design, since a larger batch is "
            "slower per request before any queueing starts. NEITHER is a slot "
            "count: an engine configured one slot returned a throughput plateau "
            "several times that. Computed on the levels that fully succeeded — "
            "see levels_used and levels_dropped. The former `batches` boolean "
            "is retired (D1): it claimed to say which column to believe, and "
            "the two columns measure different things"
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


def _level(
    base: str,
    model: str,
    n: int,
    reader: Callable[[], str | None] | None = None,
    probe: Callable[[], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """One level: ``n`` simultaneous completions, what they cost, and the
    state of both machines at its end (#327).

    ``reader`` is the one ssh the level pays for; ``None`` reads nothing (the
    warm-up), and the row then carries the state blocks as ``null`` with the
    command they would have needed.

    ``probe`` is asked WHILE the level runs, which ``reader`` cannot be: it is
    read at the level's end, when every request has returned and a server's
    in-flight count is zero by definition. An engine that reports how many
    requests it is running versus queueing answers the one question a plateau
    cannot -- whether the level was ever offered the concurrency it claims --
    and it has to be asked mid-flight or not at all.
    """
    out: list[dict[str, Any]] = []
    lock = threading.Lock()
    # The budget is the whole LEVEL's: every request is offered at once, so on a
    # server that serializes them the last one waits for all the others.
    budget = RAMP_TIMEOUT_BASE_S + n * RAMP_TOKENS / RAMP_FLOOR_TOKENS_PER_S
    threads = [
        threading.Thread(target=_one, args=(base, model, out, lock, budget))
        for _ in range(n)
    ]
    # What the server said about itself while the level was in flight. The
    # sampler is a daemon so a probe that hangs cannot hold the ramp; it stops
    # when the requests do, and its readings are kept as the extremes -- the
    # most the server ever ran at once, and the most it ever had waiting.
    samples: list[dict[str, Any]] = []
    running = threading.Event()

    def sample() -> None:
        while not running.is_set():
            reading = probe() if probe is not None else None
            if reading is not None:
                samples.append(reading)
            running.wait(PROBE_INTERVAL_S)

    sampler = threading.Thread(target=sample, daemon=True) if probe else None
    begin = time.monotonic()
    for thread in threads:
        thread.start()
    if sampler is not None:
        sampler.start()
    for thread in threads:
        thread.join()
    running.set()
    if sampler is not None:
        sampler.join(timeout=PROBE_INTERVAL_S * 2)
    wall = time.monotonic() - begin
    good = [row for row in out if "error" not in row]
    # A reply that arrived without a `usage` block is NOT a reply that generated
    # zero tokens. Summing it as 0 turned "we could not count" into "this server
    # is slow", which reads downstream as a plateau. Counted separately so
    # `saturation` can drop the level instead of believing it.
    counted = [row for row in good if row.get("completion_tokens") is not None]
    tokens = sum(row["completion_tokens"] for row in counted)
    latencies = [row["latency_s"] for row in good]
    # Read at the level's END: the state the last token was produced under,
    # after `n` requests' worth of load, which is what a throttle shows up as.
    state = level_state(
        reader() if reader is not None else None,
        client_loadavg() if reader is not None else None,
    )
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
        # **Concurrency, observed rather than assumed.** `n` is what was
        # offered; this is what the server said it was doing. `null` when
        # nothing was asked (the warm-up, or an engine with no such endpoint) --
        # never zero, which is a reading and not an absence.
        "in_flight": in_flight(samples, n),
        **state,
    }


def _one(
    base: str,
    model: str,
    out: list[dict[str, Any]],
    lock: threading.Lock,
    timeout: float = 600.0,
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
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
