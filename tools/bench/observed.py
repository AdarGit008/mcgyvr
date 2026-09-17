#!/usr/bin/env python3
"""What the endpoint will answer about itself: recorded, and compared by nothing.

**Nothing reads this file for comparison, and nothing may.** ``run.json`` is the
compared block: ``identity.KEY`` is its admitted subset, ``require_comparable``
refuses on it, and both rigs' resume checks drift on it. This is the *other*
block — everything the serving endpoint will say about itself, captured as
comprehensively as it will answer, written beside ``run.json`` and read by
people. A guard wired to a field in here would be a guard nobody declared, on a
field nobody admitted; if a value in this file turns out to be worth refusing a
table over, its path into the key is the owner's — the owner promotes it into
:data:`identity.GROUPS`, and the promotion is visible in that module's diff.

**Why a separate file rather than more ``run.json`` fields.** The two blocks
have opposite failure modes. ``run.json`` has to stay small enough that a human
diffs two of them and sees what moved; this one has to be comprehensive, and it
carries a raw ``/metrics`` body. Merging them would imply everything in the file
is compared.

**The four probe-set fields.** :data:`identity.GROUPS` declares ``quantization``,
``context_length``, ``concurrency`` and ``seed``. None can be derived from the
tree; only the server at request time can answer them. A field the endpoint
will not answer is ``null`` **with a reason**, never a sentinel string, and
never a plausible substitute:

``quantization``
    Answered on vLLM from ``/server_info`` (dev mode only); refused otherwise.

``context_length``
    The **effective** serving window, which is a serving flag and not a model
    property. Read from ``max_model_len`` on the ``/v1/models`` card, else from
    ``max_seq_len`` on ``/server_info``.

``concurrency``
    What decides whether greedy is reproducible at all: greedy decoding is not
    deterministic under continuous batching, so ``verified`` never means
    "reproduces" and a run that did not record its concurrency cannot be read on
    even that weaker signal. It is the width the server was launched with, and
    this capture does not read it, so it refuses here; the vLLM backend reads
    the launched width off the host.

    **It is not the last word on the field.** A run with host access reads it:
    see :func:`resolve` and the ``resolved`` source, which carries the served
    width beside the width this run dispatched at, and states what the pair does
    and does not license. The number never enters the block labelled ``native``,
    because a host reading sitting under that label would destroy the one
    distinction this file's sources exist to make.

``seed``
    **Observed, never set.** Greedy bypasses the sampler RNG, so no dispatch in
    this tree sends one (``OpenAIRunner._payload`` carries no seed) and
    *setting* one would be a different experiment. Recording ``null`` states a
    fact. Where the server reports the seed it was launched with
    (``/server_info``, dev mode), that value is recorded.

**The engine is identified from what answers, never from the port**, and
recorded in the block, because which server is talking decides what a null
means.

``concurrency`` **has a lookalike that is worse than the null.**
``vllm:cache_config_info`` carries ``kv_cache_max_concurrency``, which looks
like the answer and is KV-cache capacity.

``seed`` **is where "observed, never set" needed splitting in two.** It is a
statement about what this tree dispatches, and it is not a statement about the
server: vLLM 0.26.0 defaults to ``seed=0``, so a vLLM run whose seed went
unrecorded was seeded by something nobody wrote down.

**Dev mode is the biggest single lever.** ``/server_info`` carries the
quantization, the seed and the window, and exists only when the server was
launched with ``VLLM_SERVER_DEV_MODE=1``. With it, vLLM answers three of four;
without it, one. So those refusals name the flag: they are facts about how the
server was started, not limits on what vLLM can say.

``/collective_rpc`` is not called, and that is a decision rather than an
oversight. It exists under the same dev flag, but it executes a method inside
the running engine — which is not the endpoint describing itself, and a
measurement rig that runs arbitrary RPC against the server it is about to
measure is a seam nobody should have to reason about later.

**llama-server would land in the ``openai-compatible`` arm.** Its ``/props``
(``n_ctx``, ``total_slots``) is read by ``tools/bench/serving/backends/llamacpp.py``,
not here.

**The rest of the OpenAI-compatible world.** An endpoint that answers
``/v1/models`` without looking like vLLM is recorded as exactly that. One that
answers nothing gets the same shape as any other: four nulls, four reasons, an
empty native capture.

**Redaction runs on capture, before write.** ``run.json`` holds one URL; this
holds a server's whole self-description. So every string is scrubbed on the way
in: credential-bearing URLs through ``bundle.redact`` (the one redactor both
rigs already use), home-directory prefixes, and the high-confidence credential
shapes. Over-redaction is free here, because nothing compares this file.

**Two captures per run directory, ``at_open`` and ``at_close``, each written
once.** A resume adds neither: the block describes the endpoint the rows were
started against, and a resume against a materially different server is refused
by ``run.json``'s keyed drift, which is where a refusal belongs.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _bench_identity() -> types.ModuleType:
    """The identity contract, through the slot both rigs already share (#287).

    Two loads of the contract would be two copies of it that could disagree.
    """
    cached = sys.modules.get("bench_identity")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "bench_identity", HERE / "identity.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


identity = _bench_identity()


def _bundle_rig() -> types.ModuleType:
    """The bundle rig, for :func:`redact` — ``tools/`` has no ``__init__.py``.

    Imported for one function, and imported rather than copied: a second
    redactor is a second place to have a gap, and the one thing worse than a
    redactor with a gap is two of them with different gaps. The
    slot is the one the breadth rig fills at import time, so in a dispatch this
    is always a cache hit.
    """
    cached = sys.modules.get("bundle_measure")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "bundle_measure", REPO / "tools" / "bundle" / "measure.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: The file, beside ``run.json``. Only :func:`write` names it.
OBSERVED_FILE = "observed.json"

#: The four fields :data:`identity.GROUPS` declares and this module writes.
#: Under the names ``GROUPS`` gives them, so a reader who finds a
#: null here and a null there is looking at one field and not two.
PROBE_SET: tuple[str, ...] = (
    "quantization",
    "context_length",
    "concurrency",
    "seed",
)

#: The two moments a capture is taken. `at_open` describes the server the rows
#: were started against; `at_close` is the far edge of the completions window.
CAPTURES = "captures"
AT_OPEN = "at_open"
AT_CLOSE = "at_close"

#: The two SOURCES a capture can draw on, labelled apart because they prove
#: different things. `native` is what the endpoint this run dispatched to said
#: about itself; `host` is what the machine said. They coincide when the
#: endpoint resolves straight to that machine with nothing in between, and
#: diverge behind a proxy or a load balancer.
NATIVE_SOURCE = "native"
HOST_SOURCE = "host"

#: The third source: neither what the endpoint said nor what the machine said,
#: but what the two together settle. Kept apart from both, because a value that
#: arrived from the host must never sit inside the block labelled `native` — a
#: reader has to be able to tell which kind of evidence a number is, and that
#: separation is the whole reason this file has sources at all.
RESOLVED_SOURCE = "resolved"

#: The two facts about batching, under the names they are recorded by. **Two
#: fields, never one, and never substituted for one another.**
#: `served_width` is a ceiling the SERVER was started with;
#: `dispatch_max_parallel` is how many requests THIS run had in flight.
SERVED_WIDTH = "served_width"
DISPATCH_MAX_PARALLEL = "dispatch_max_parallel"

#: The third term, and it is named for what it holds rather than for the
#: conclusion it supports. `dispatch_max_parallel` bounds the realised batch
#: only if this run was the sole client; this is how many requests the SERVER
#: finished between the open and close captures, from the server's own counter.
#: Subtract the run's own dispatched rows and the remainder is foreign traffic.
#: **Never a boolean.** A field reading `sole_client: true` because nothing was
#: detected is the failure this field exists to avoid.
SERVER_COMPLETIONS = "server_completions_in_window"

#: The series that answers it on vLLM, and the label it is summed over. On
#: vLLM 0.26.0 only a request that reached the engine moves it: `/health`,
#: `/metrics`, `/ping`, `/v1/models` and a request that fails at the API layer
#: do not. **The reading does not perturb the counter it reads**, so the
#: arithmetic needs no correction term for the harness's own traffic.
#:
#: Summed over `finished_reason` — a request that reached the engine and ended
#: for any reason is counted once.
VLLM_COMPLETIONS_SERIES = "vllm:request_success_total"

#: The broader view, kept for the refusal to cite rather than read here. It
#: counts instrumented HTTP including `/v1/models` and every 4xx, and excludes
#: `/health`, `/metrics` and `/ping`. A foreign client that only listed models
#: shows here and not in the counter above, which is correct for the batching
#: question: a request that never reached the engine never entered a batch.
VLLM_HTTP_SERIES = "http_requests_total"

#: Whether the host readings provably describe THIS run's server (serving/pin).
PIN = "pin"

#: Where the comprehensive capture lives, under the endpoint's own key names.
#: Everything else in the file is this module's reading of it.
NATIVE = "native"

#: Which server answered, identified from what it said rather than from its
#: port. On the block because a refusal cannot be read without it: `null` for
#: `context_length` means "this vLLM did not list max_model_len" rather than
#: "the endpoint was not reachable", and those are different facts about a run.
ENGINE = "engine"

VLLM = "vllm"
OPENAI_COMPATIBLE = "openai-compatible"
UNREACHABLE = "unreachable"

ENGINES: tuple[str, ...] = (VLLM, OPENAI_COMPATIBLE, UNREACHABLE)

#: Engines whose shapes this module has been run against a LIVE endpoint. Every
#: number in this module — in the docstring, in the refusal reasons, in the test
#: fixtures — is a measurement from one of these runs, not a documented shape.
VERIFIED_LIVE: dict[str, str] = {
    VLLM: (
        "srv1 (0.26.0, Qwen2.5-Coder-1.5B-Instruct-AWQ, --max-model-len 8192 "
        "--max-num-seqs 8 --enforce-eager) and srv2 (0.26.0 in the "
        "vllm/vllm-openai container, 7B-Instruct-AWQ, --max-model-len 16384 "
        "--max-num-seqs 16 --enable-prefix-caching --enable-sleep-mode), both "
        "with VLLM_SERVER_DEV_MODE=1, 2026-08-18. Enumerated by asking each "
        "server for its own /openapi.json route table and fetching every "
        "parameterless GET: 11 answered of the 43 routes declared"
    ),
    UNREACHABLE: (
        "the degenerate arm, exercised by every offline test in the suite and "
        "by the port sweep that found nothing on 8000 or 8080 before the two "
        "vLLMs above were started"
    ),
}

#: Engines built from documented shapes and NOT yet exercised against a live
#: endpoint, with what it would take to discharge each. The contingency is
#: recorded where the code is, not in a PR body, and
#: `test_every_engine_says_whether_it_has_been_run_live` fails if an engine
#: appears in neither dict — so a third arm cannot arrive unmarked, and this one
#: cannot be quietly promoted without someone deleting a line that says why.
UNVERIFIED: dict[str, str] = {
    OPENAI_COMPATIBLE: (
        "the fallback arm: an endpoint that answers /v1/models and does not "
        "look like vLLM, which is where llama-server, LM Studio and TGI would "
        "land. It refuses every field its /v1/models card does not carry — at "
        "most context_length answers — so the untested part is the "
        "identification, not a derivation"
    ),
}

#: The `/metrics` body is the one read that can be large; it alone gets this
#: budget.
CAPTURE_TIMEOUT_S = 30.0

#: Every other read, which returns kilobytes at most. Short on purpose: a
#: capture runs immediately before a sweep's first draw, and an endpoint that
#: drops rather than refuses would otherwise put minutes of silence in front of
#: the run.
DISCOVERY_TIMEOUT_S = 5.0


def _url(base: str, path: str) -> str:
    """Join a base URL to a path, tolerating a base that already ends in ``/v1``.

    The same rule as :func:`mcgyvr.runner._url_for`, and for the same reason: a
    ``base_url`` copied from a hosted provider's own page carries ``/v1``.
    Without this, ``https://host/v1`` is probed at ``/v1/v1/models`` — a 404
    that this module would then record as "nothing there described itself at
    all" about a server answering perfectly well. Restated here rather than
    imported because ``_url_for`` is private to a module inside
    ``product.SURFACE`` and this tool must not move that digest to reuse eight
    lines.

    The strip is unconditional, which is where this diverges from ``_url_for``:
    that function is only ever handed one path per protocol and both start with
    ``/v1/``, while ``VLLM_READS`` mixes ``/v1/models`` with six root-level
    paths and ``_capture_served`` adds ``/metrics``. Stripping only for ``/v1/``
    paths would send every root path to ``/v1/version``, ``/v1/server_info`` and
    so on — 404s recorded as refusals blaming an unset
    ``VLLM_SERVER_DEV_MODE``, sending a reader after a flag when the cause is
    the URL. Every path here is written from the root, so the base's ``/v1``
    is redundant in all cases, not just some.
    """
    base = base.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + path


#: Elide BY NAME, with a length backstop: the GGUF tokenizer arrays are elided
#: for what they are; any other list only above :data:`MAX_INLINE_ITEMS`. The
#: summary keeps the count and :func:`identity.digest` of the array.
ELIDE_BY_NAME: frozenset[str] = frozenset(
    {
        "tokenizer.ggml.tokens",
        "tokenizer.ggml.merges",
        "tokenizer.ggml.token_type",
        "tokenizer.ggml.scores",
    }
)

#: The backstop, for a list this does not know by name. Deliberately high, so it
#: catches an unforeseen array without quietly eliding a structural list. A
#: list hitting this is worth noticing, not just shrinking.
MAX_INLINE_ITEMS = 4096

#: What an elided list is replaced by. A dict rather than a truncated list, so
#: no reader can mistake it for the array itself.
ELIDED = "elided"

_REDACTED = "<redacted>"

# A URL carrying credentials, found *inside* a longer string as well as alone.
# `bundle.redact` does the removal — this only locates the URLs it is given,
# because `urlsplit` over a long free-text string finds no netloc at all.
_CREDENTIAL_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s\"'<>]*@[^\s\"'<>]*")

# A home-directory prefix, which names a user. The rest of the path stays.
_HOME_PATH = re.compile(r"(?P<root>/(?:home|Users))/[^/\s\"']+")

# High-confidence credential shapes, following each issuer's published format.
# The PEM header is assembled from two fragments on purpose: written whole it
# would be a literal secret-shaped string in a tracked file, which this repo's
# own scanners and GitHub's push protection both flag (and rightly).
_TOKEN_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z ]{0,12}PRIVATE" + r" KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
)


def scrub(value: Any) -> Any:
    """``value`` with every string in it redacted, however deeply nested.

    Recursive because the risk is not at the top level: a server-supplied
    string can sit inside any key or list. A non-string leaf — a number, a bool,
    ``null`` — is returned as it is, and a dict key is scrubbed too, since a
    captured document's keys are server-supplied strings.
    """
    if isinstance(value, str):
        return _scrub_text(value)
    if isinstance(value, dict):
        return {_scrub_text(str(k)): scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def _scrub_text(text: str) -> str:
    """One string, through the three redactions, in the order they compose.

    ``bundle.redact`` reads ``urlsplit(...).port``, which **raises** on a port
    outside 0-65535 or an unbalanced bracket. That is fine for the one endpoint
    URL ``run.json`` holds and not fine here: this runs over every string a
    server sent, including raw Prometheus text, any of which can contain
    something URL-shaped and invalid. Left unguarded, a raise would reach
    `record_run` after `run.json` is already on disk — no rows and a traceback,
    which is exactly the "worst of both" :func:`capture` promises not to be. An
    unparseable candidate is redacted wholesale: it cannot be shown to be safe.
    """
    bundle = _bundle_rig()
    text = _CREDENTIAL_URL.sub(lambda m: _redact_one(bundle, m.group(0)), text)
    text = _HOME_PATH.sub(lambda m: f"{m.group('root')}/{_REDACTED}", text)
    for shape in _TOKEN_SHAPES:
        text = shape.sub(_REDACTED, text)
    return text


def _redact_one(bundle: types.ModuleType, url: str) -> str:
    """``bundle.redact(url)``, or ``<redacted>`` if it will not parse."""
    try:
        return str(bundle.redact(url))
    except Exception:
        return _REDACTED


def elide(value: Any, key: str | None = None) -> Any:
    """``value`` with tokenizer arrays summarised by name, plus a length backstop.

    A list is elided when its KEY names it a tokenizer array
    (:data:`ELIDE_BY_NAME`), or — failing that — when it exceeds
    :data:`MAX_INLINE_ITEMS`. Each summary records which rule fired, because
    "this was elided because we know what it is" and "this was elided because it
    was surprisingly long" are different facts about a run.

    The summary is the count and :func:`identity.digest` of the whole array —
    the same digest convention ``run.json`` uses.
    """
    if isinstance(value, dict):
        return {k: elide(v, k) for k, v in value.items()}
    if isinstance(value, list):
        named = key is not None and key.lower() in ELIDE_BY_NAME
        if named or len(value) > MAX_INLINE_ITEMS:
            return {
                ELIDED: True,
                "rule": "name" if named else "length",
                "count": len(value),
                "sha256": identity.digest(value),
            }
        return [elide(v, key) for v in value]
    return value


def capture(
    endpoint: str, model: str, *, timeout: float = CAPTURE_TIMEOUT_S
) -> dict[str, Any]:
    """The whole block, ready to write: engine, probe set, reasons, capture.

    **The engine is identified from what answers, never from the port.**
    ``detect.PORT_CONVENTIONS`` guesses identity from a port because what it
    needs downstream is the wire protocol; this needs the *server*, because the
    server decides what a refusal means. ``_identify`` tells vLLM from a bare
    OpenAI-compatible server from an endpoint that said nothing, and those are
    three different facts about a run.

    The arm reaches the identity module's fetchers by attribute lookup rather
    than copying them, so a test that patches the seam patches this path too.

    Never raises. An endpoint that is down, slow or speaking another protocol
    produces the same shape as one that answers — that is what makes the shape
    readable — and a manifest that could not be written because the probe threw
    would be the worst of both.
    """
    base = endpoint.rstrip("/")
    native, engine = _capture_served(base, timeout=timeout)
    fields, reasons = _served_probe_set(base, model, native, engine)
    block: dict[str, Any] = {
        "endpoint": _bundle_rig().redact(endpoint),
        "model": model,
        ENGINE: engine,
        **fields,
        NATIVE: native,
    }
    if reasons:
        block[identity.REFUSALS] = reasons
    scrubbed: dict[str, Any] = scrub(elide(block))
    return scrubbed


#: The parameterless GETs this capture reads, chosen from the routes vLLM
#: 0.26.0 lists in its own ``/openapi.json``.
#:
#: ``/collective_rpc`` is deliberately NOT here. It exists (dev mode), but it
#: executes a method inside the running engine, which is not the endpoint
#: describing itself, and a measurement rig that runs arbitrary RPC against the
#: server it is about to measure is a seam nobody should have to reason about
#: later.
VLLM_READS: tuple[tuple[str, str], ...] = (
    ("models", "/v1/models"),
    ("version", "/version"),
    ("server_info", "/server_info"),
    ("load", "/load"),
    ("is_sleeping", "/is_sleeping"),
    ("is_paused", "/is_paused"),
    ("world_size", "/get_world_size"),
)


def _capture_served(
    base: str, *, timeout: float = CAPTURE_TIMEOUT_S
) -> tuple[dict[str, Any], str]:
    """Everything the OpenAI-compatible surface will answer, vLLM's extras too.

    ``/metrics`` is Prometheus text rather than JSON, and it is captured raw:
    parsing it here would decide, today, which series a reader may ever ask
    about. A raw body in a file nothing compares is a cheap price for a later
    question about queue depth or cache blocks being answerable off a run
    already on disk instead of needing the rig back.
    """
    native: dict[str, Any] = {}
    for name, path in VLLM_READS:
        answer = identity._get_json(_url(base, path), timeout=DISCOVERY_TIMEOUT_S)
        if answer is not None:
            native[name] = answer
    # The one body that can be large, and so the one call that gets the long
    # budget. Everything else here returns kilobytes at the discovery budget,
    # which matters because this capture runs immediately before the first
    # draw.
    metrics = _get_text(_url(base, "/metrics"), timeout=timeout)
    if metrics is not None:
        native["metrics"] = metrics
    return native, _identify(native)


def _identify(native: dict[str, Any]) -> str:
    """Which server this is, from what it said.

    Three independent tells, any of which is enough: vLLM labels its own metrics
    with a ``vllm:`` prefix, stamps ``owned_by`` on every model card, and serves
    ``/version`` where the bare OpenAI shape has no such route. Any one of them
    on its own would be a thin test; the point of taking all three is that a
    build which has turned metrics off is still identified.
    """
    metrics = native.get("metrics")
    if isinstance(metrics, str) and "vllm:" in metrics:
        return VLLM
    if isinstance(native.get("version"), dict) and native.get("models") is not None:
        return VLLM
    for row in _model_rows(native):
        if str(row.get("owned_by", "")).lower() == VLLM:
            return VLLM
    if native.get("models") is not None:
        return OPENAI_COMPATIBLE
    return UNREACHABLE


def _counter_total(metrics: Any, series: str) -> float | None:
    """One Prometheus counter, summed over every label set it carries.

    Summed rather than read: `vllm:request_success_total` is emitted once per
    `finished_reason`, so any single line is a fraction of the count. Returns
    `None` — never `0.0` — when the body is absent or carries no such series,
    because a counter that was not read and a counter reading zero are the two
    things this whole block exists to keep apart.

    Text, not JSON. `/metrics` is Prometheus exposition format and is captured
    raw for exactly this reason (`_capture_served`); a body that has been
    through a JSON parser is not one this can read.
    """
    if not isinstance(metrics, str):
        return None
    total: float | None = None
    for line in metrics.split("\n"):
        if not line.startswith(series) or line.startswith("#"):
            continue
        head, _, value = line.rpartition(" ")
        # `series` must match a whole metric name, not a prefix of a longer one:
        # `vllm:request_success_total` and a hypothetical
        # `vllm:request_success_total_bytes` would otherwise be added together.
        if head[len(series) :][:1] not in ("", "{"):
            continue
        try:
            total = (total or 0.0) + float(value)
        except ValueError:
            continue
    return total


def _server_completions(
    native: dict[str, Any] | None,
    opened: dict[str, Any] | None,
    when: str,
) -> dict[str, Any]:
    """How many requests the SERVER finished between the two captures.

    **Recorded, not concluded.** The value is the server's own counter delta.
    Foreign traffic is that minus the rows this run dispatched, and the
    subtraction is deliberately NOT done here: the dispatched-row count is a
    property of the runner, it is not passed to this module, and passing it
    would touch both runner call sites, which are SURFACE. It is in `run.json`
    beside this file, so a reader has both terms and the arithmetic is written
    down in the note. **Zero difference is measured sole-clientness; anything
    else names how much else the server served.**

    Three states, not two: a number is *measured*; a refusal on an engine with
    no counter is *looked in a way that cannot see*; a refusal at the open
    capture is *not looked yet*. None of them is a boolean.
    """
    engine = (native or {}).get(ENGINE)

    def counter(capture: dict[str, Any] | None) -> float | None:
        return _counter_total(
            ((capture or {}).get(NATIVE) or {}).get("metrics"),
            VLLM_COMPLETIONS_SERIES,
        )

    reading = counter(native)
    if reading is None:
        return {
            "value": None,
            identity.REFUSALS: (
                f"the capture holds no {VLLM_COMPLETIONS_SERIES} to read: "
                f"the engine answered as {engine!r} and either served no "
                "/metrics body or serves a build without that series. A "
                "counter that was not read is not a counter reading zero"
            ),
        }

    if when != AT_CLOSE:
        return {
            "value": None,
            "counter": VLLM_COMPLETIONS_SERIES,
            "reading": reading,
            identity.REFUSALS: (
                "an open capture has nothing to difference against; the "
                "reading it took is kept here so the close capture can"
            ),
        }

    before = counter((opened or {}).get(NATIVE_SOURCE))
    if before is None:
        return {
            "value": None,
            "counter": VLLM_COMPLETIONS_SERIES,
            "reading": reading,
            identity.REFUSALS: (
                "the open capture carries no reading of this counter, so the "
                "window has no near edge. A run whose file holds only a close "
                "capture did not finish the way this block assumes"
            ),
        }
    return {
        "value": reading - before,
        "counter": VLLM_COMPLETIONS_SERIES,
        "at_open": before,
        "at_close": reading,
        # The window is named by the two captures rather than stamped with an
        # instant: they ARE its edges, and `run.json`'s provenance beside this
        # file already carries the clock (#325). A second timestamp here would
        # be a third thing to keep in agreement with those two.
        "window": f"{AT_OPEN} to {AT_CLOSE}",
        "source": "the server's own counter, read twice",
    }


def resolve(
    host: dict[str, Any],
    dispatch_max_parallel: int | None,
    *,
    native: dict[str, Any] | None = None,
    opened: dict[str, Any] | None = None,
    when: str = AT_OPEN,
) -> dict[str, Any]:
    """The two batching facts that decide whether a re-run can reproduce.

    **Why this block exists.** ``concurrency`` in :data:`PROBE_SET` is refused on
    the native surface, and the refusal is correct: this capture does not read
    the width. The ``host`` block written beside it in this
    same file is produced by ``tools/bench/serving/``, with host access. This is
    where the two meet, and the native refusal stays, because it remains a true
    statement about what this capture reads.

    **What the pair does and does not license.** They are bounds on the realised
    batch, and the realised batch is what determines reproducibility:

    * ``served_width`` of 1 licenses "the batch was 1". A server that cannot
      batch does not batch, whatever else was on it.
    * ``dispatch_max_parallel`` of 1 does **not**. It says this run had one
      request in flight, which bounds the batch only if this run was the sole
      client — and nothing in this tree establishes that. Another client on the
      same server batches with it, breaks greedy determinism, and leaves no
      trace.
    * Neither field alone establishes reproducibility, and a width above 1 does
      not refute it: the run may still have been serial in fact.

    Sole-clientness is the third term, a recorded measurement with a window
    rather than a boolean. ``server_completions_in_window`` is the server's own
    count of requests it finished between the two captures; subtract the rows
    this run dispatched and the remainder is foreign traffic. A server with no
    such counter refuses the field.

    **The dispatch side is passed in, never read from a constant here.** It is a
    property of the endpoint the runner actually built (computed, never
    typed); a literal in this module would describe a dispatcher it cannot
    see and would keep agreeing after that dispatcher changed.
    """
    reading = (host or {}).get("width") or {}
    served: dict[str, Any] = {"value": reading.get("value")}
    if reading.get("source"):
        served["source"] = reading["source"]
    if served["value"] is None:
        served[identity.REFUSALS] = reading.get("refused") or (
            "no host block was captured, so the one place this number is "
            "readable was not read; the native surface does not carry it"
        )

    dispatch: dict[str, Any] = {"value": dispatch_max_parallel}
    if dispatch_max_parallel is None:
        dispatch[identity.REFUSALS] = (
            "the runner did not pass the width it dispatched at; it is a "
            "property of the endpoint that runner built and cannot be "
            "recovered from anything this module can reach"
        )
    else:
        dispatch["source"] = "the endpoint the runner dispatched through"

    return {
        SERVED_WIDTH: served,
        DISPATCH_MAX_PARALLEL: dispatch,
        SERVER_COMPLETIONS: _server_completions(native, opened, when),
        "note": (
            "three terms on the realised batch, never substituted for one "
            "another. A served_width of 1 licenses 'the batch was 1'; a "
            "dispatch_max_parallel of 1 does not, because it bounds the batch "
            "only if this run was the sole client. server_completions_in_window "
            "is what settles that, and it is a count rather than a verdict: it "
            "is the server's own tally of requests finished between the open "
            "and close captures, so FOREIGN traffic is that value minus the "
            "rows this run dispatched (in run.json beside this file), and zero "
            "is measured sole-clientness. Where the engine serves no counter "
            "the field refuses, which is a fact about reach and not about the "
            "run. Nothing compares this block"
        ),
    }


def write(
    out: Path,
    endpoint: str,
    model: str,
    *,
    when: str = AT_OPEN,
    host: dict[str, Any] | None = None,
    dispatch_max_parallel: int | None = None,
    timeout: float = CAPTURE_TIMEOUT_S,
) -> Path | None:
    """Add a capture to :data:`OBSERVED_FILE` beside ``run.json``.

    **Two captures per run directory, not one.** ``at_open`` is written before
    the first draw and describes the server the rows were started against;
    ``at_close`` is written when the run finishes.

    The close capture is what gives ``server_completions_in_window`` its far
    edge, and it records what the server looked like *under* the load the run
    applied, which nothing else does.

    Each capture is written **once**. A resume adds neither: the open capture
    describes rows this invocation did not measure, and re-writing the close one
    would restate a server state that has moved on. A file with only an open
    capture is a run that did not finish, which is itself worth knowing.
    """
    path = out / OBSERVED_FILE
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            # Not only a decode error: invalid UTF-8 or an unreadable mode
            # raises out of `write`, past `record_run`, past `main`'s
            # `except MeasureError` — aborting the sweep with a traceback on the
            # one path outside the `capture()` guard. Nothing compares this
            # block; it may never be the reason a run produces no rows.
            existing = {}
        # A single-capture file (no `captures` key) is migrated forward rather
        # than overwritten: it is an `at_open` capture.
        if existing and CAPTURES not in existing:
            existing = {CAPTURES: {AT_OPEN: existing}}
        if when in (existing.get(CAPTURES) or {}):
            return None
    out.mkdir(parents=True, exist_ok=True)
    try:
        block = capture(endpoint, model, timeout=timeout)
    except Exception as error:
        # Scrubbed like any other path. An exception message is server-derived
        # text — it routinely carries the URL that failed, and that URL may
        # carry a credential — so the one branch that skipped `scrub` was the
        # one most likely to be holding one.
        block = scrub(
            {
                "endpoint": endpoint,
                "model": model,
                ENGINE: UNREACHABLE,
                **dict.fromkeys(PROBE_SET),
                NATIVE: {},
                identity.REFUSALS: dict.fromkeys(
                    PROBE_SET,
                    f"the capture itself failed: {type(error).__name__}: "
                    f"{error}. Recorded rather than raised, because nothing "
                    "compares this block and it must never be the reason a "
                    "sweep produces no rows",
                ),
            }
        )
    # `host` is SUPPLIED, never gathered here. This module answers "what did
    # the endpoint say about itself" — one HTTP round trip to the thing being
    # measured — which is what lets it work unchanged against an endpoint nobody
    # can log into. Host-side readings are a different kind of evidence and are
    # labelled as such, so a later reader can always tell which is which.
    captures = dict(existing.get(CAPTURES) or {})
    captures[when] = {
        NATIVE_SOURCE: block,
        HOST_SOURCE: host or {},
        RESOLVED_SOURCE: resolve(
            host or {},
            dispatch_max_parallel,
            native=block,
            # The capture already on disk, which at close is the open one. It
            # is read from `existing` rather than re-probed: the near edge of
            # the window is the reading that was taken then, and taking it
            # again now would measure a different moment.
            opened=(existing.get(CAPTURES) or {}).get(AT_OPEN),
            when=when,
        ),
    }
    path.write_text(json.dumps({CAPTURES: captures}, indent=2) + "\n", encoding="utf-8")
    return path


def _served_probe_set(
    base: str, model: str, native: dict[str, Any], engine: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """The four declared fields off the OpenAI-compatible surface.

    A refusal names the engine it is a fact about, so ``null`` is never just
    "unavailable".
    """
    if engine is UNREACHABLE:
        return (
            dict.fromkeys(PROBE_SET),
            dict.fromkeys(
                PROBE_SET,
                f"{base} did not answer /v1/models; nothing there described "
                "itself at all",
            ),
        )

    # Every measured claim below is a fact about vLLM 0.26.0, so it may only be
    # written when vLLM is what answered. An `openai-compatible` server is any
    # server that serves /v1/models and does not look like vLLM — llama-server,
    # LM Studio or TGI. Telling that reader its quantization is missing
    # because VLLM_SERVER_DEV_MODE is unset would be a stated reason that is
    # simply untrue, and a null is required to carry a TRUE reason.
    vllm = engine is VLLM
    where = "vLLM" if vllm else "this OpenAI-compatible server"
    unmeasured = (
        f"{where} was identified by what it answered, not by a version, so "
        "nothing here has been measured against it — this refusal records that "
        "the field was not on the surface it does serve, and nothing more"
    )
    config = _engine_config(native)
    fields: dict[str, Any] = {}
    reasons: dict[str, str] = {}

    quantization = config.get("quantization")
    if quantization is not None:
        fields["quantization"] = quantization
    else:
        fields["quantization"] = None
        reasons["quantization"] = (
            f"{where} does not describe the weights it loaded on any endpoint "
            "this reads. On vLLM it is on /server_info, which exists only when "
            "the server was launched with VLLM_SERVER_DEV_MODE=1 — measured "
            "`quantization=auto_awq` on srv1 and srv2 with the flag set, and "
            "the endpoint 404s without it, so there it is a fact about how the "
            "server was started rather than a limit on what it can say"
            if vllm
            else f"{where} served no endpoint carrying the quantization. {unmeasured}"
        )

    max_model_len = _model_field(native, model, "max_model_len")
    if isinstance(max_model_len, int):
        fields["context_length"] = max_model_len
    elif isinstance(config.get("max_seq_len"), int):
        fields["context_length"] = config["max_seq_len"]
    else:
        fields["context_length"] = None
        reasons["context_length"] = (
            f"{where} listed no max_model_len on the model card for {model!r}"
            + (" and no max_seq_len on /server_info" if vllm else f". {unmeasured}")
        )

    fields["concurrency"] = None
    reasons["concurrency"] = (
        "`max_num_seqs` — the scheduler's batch width, which is what this "
        "field means — is not read by this capture; the vLLM backend reads "
        "the launched width off the host. "
        "`vllm:cache_config_info.kv_cache_max_concurrency` "
        "looks like the answer and is NOT: it is KV-cache capacity, and it "
        "moves opposite to the flag — srv1 ran --max-num-seqs 8 and reported "
        "16.004, srv2 ran 16 and reported 5.314. "
        f"The raw metrics are under {NATIVE}"
        if vllm
        else f"the batch width is not on any endpoint {where} served. {unmeasured}"
    )

    seed = config.get("seed")
    if seed is not None:
        fields["seed"] = seed
    else:
        fields["seed"] = None
        reasons["seed"] = (
            "no dispatch in this tree sends a seed (greedy bypasses the "
            f"sampler RNG), and {where} did not report the one it was launched "
            "with — /server_info carries it and exists only under "
            "VLLM_SERVER_DEV_MODE=1. Note that vLLM 0.26.0 defaults to "
            "`seed=0` rather than to none, measured on both rigs: on this "
            "engine an unrecorded seed is a set seed nobody wrote down"
            if vllm
            else "no dispatch in this tree sends a seed (greedy bypasses the "
            f"sampler RNG), and {where} reported none. Whether it holds one "
            f"server-side is unknown here. {unmeasured}"
        )
    return fields, reasons


# `vllm_config` on /server_info is a Python repr rather than a JSON object, so
# the settings that live only there are lifted by name. Narrow on purpose: the
# whole string is captured verbatim beside this, so a value this pattern misses
# is still on disk, and a repr that changes shape in a later vLLM degrades to a
# refusal with a reason rather than to a wrong number.
_CONFIG_FIELDS: tuple[tuple[str, str], ...] = (
    ("quantization", r"\bquantization=([^,)\s]+)"),
    ("seed", r"\bseed=([^,)\s]+)"),
    ("max_seq_len", r"\bmax_seq_len=([^,)\s]+)"),
    ("dtype", r"\bdtype=([^,)\s]+)"),
)


def _engine_config(native: dict[str, Any]) -> dict[str, Any]:
    """What ``/server_info`` says the engine was configured with.

    Empty when the endpoint is not there, which is the ordinary case: it is
    gated behind ``VLLM_SERVER_DEV_MODE=1``. Whether that flag is set is the
    single biggest lever on how much of the probe set a vLLM answers — with it,
    three of four; without it, one — so the refusals above name the flag rather
    than saying the field is unobtainable.
    """
    raw = _mapping(native.get("server_info")).get("vllm_config")
    if not isinstance(raw, str):
        return {}
    found: dict[str, Any] = {}
    for name, pattern in _CONFIG_FIELDS:
        match = re.search(pattern, raw)
        if match is None:
            continue
        value = _as_number(match.group(1).strip("'\""))
        if value not in ("None", "auto", ""):
            found[name] = value
    return found


def _model_rows(native: dict[str, Any]) -> list[dict[str, Any]]:
    """The ``/v1/models`` cards, or an empty list — never a partial shape."""
    data = _mapping(native.get("models")).get("data")
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _model_field(native: dict[str, Any], model: str, field: str) -> Any:
    """``field`` off the card for ``model``, or off the only card there is.

    A served model's id is frequently the path it was loaded from rather than
    the name a config calls it, so an exact-id miss falls back to the single
    card when there is exactly one — which is the shape of every rig in this
    tree. Two cards and no id match is a refusal: guessing which of them the
    dispatch used is a plausible substitute, which a refusal exists to forbid.
    """
    rows = _model_rows(native)
    for row in rows:
        if row.get("id") == model or row.get("root") == model:
            return row.get(field)
    return rows[0].get(field) if len(rows) == 1 else None


def _get_text(url: str, *, timeout: float) -> str | None:
    """GET a text document, or None on any failure at all.

    A sibling of the identity module's JSON fetchers rather than a copy of
    them: ``/metrics`` is Prometheus text, and routing it through a JSON parser
    would report "the endpoint did not answer" for an endpoint that answered
    perfectly well in the format it documents.
    """
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return str(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def _mapping(value: Any) -> dict[str, Any]:
    """``value`` if it is a dict, else an empty one — so callers stay flat."""
    return value if isinstance(value, dict) else {}


def _as_number(raw: str) -> Any:
    """``raw`` as an int or a float where it is one, else unchanged."""
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def main(argv: list[str] | None = None) -> int:
    """Print a capture without writing one — for looking at a rig by hand."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout", type=float, default=CAPTURE_TIMEOUT_S)
    args = parser.parse_args(argv)
    block = capture(args.endpoint, args.model, timeout=args.timeout)
    print(json.dumps(block, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
