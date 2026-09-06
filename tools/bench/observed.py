#!/usr/bin/env python3
"""What the endpoint will answer about itself, captured once and compared by nothing.

ADR-0027 **D7**, issue `#286 <https://github.com/AdarGit008/mcgyvr/issues/286>`_.

**Nothing reads this file for comparison, and nothing may.** ``run.json`` is the
compared block: ``identity.KEY`` is its admitted subset, ``require_comparable``
refuses on it, and both rigs' resume checks drift on it. This is the *other*
block — everything the serving endpoint will say about itself, captured as
comprehensively as it will answer, written beside ``run.json`` and read by
people. A guard wired to a field in here would be a guard nobody declared, on a
field nobody admitted; if a value in this file turns out to be worth refusing a
table over, its path into the key is D7's — the owner promotes it into
:data:`identity.GROUPS`, and the promotion is visible in that module's diff.

**Why a separate file rather than more ``run.json`` fields.** The two blocks
have opposite failure modes. ``run.json`` has to stay small enough that a human
diffs two of them and sees what moved; this one has to be comprehensive, and on
the 1.5B the raw ``/api/show`` document is **7.7 MB of JSON** (measured against
srv2, ollama 0.32.5, 2026-08-18 — three tokenizer arrays of 151,936, 151,387 and
151,936 entries account for essentially all of it). Merging them would imply
everything in the file is compared, which is the "a guard that names five fields
permits the sixth silently" defect approached from the other side.

**The four probe-set fields.** :data:`identity.GROUPS` declares ``quantization``,
``context_length``, ``concurrency`` and ``seed``, and until this module nothing
in the repository wrote them — they carried ``PENDING_REASON`` =
``AWAITING_PROBE_SET``. None can be derived from the tree; only the server at
request time can answer them, and on the surfaces this build talks to it
answers two of the four (one of them dev-mode only). That is the honest result
and it is recorded as such, per D2: a field
the endpoint will not answer is ``null`` **with a reason**, never a sentinel
string, and never a plausible substitute:

``quantization``
    Answered. ``details.quantization_level`` on both calls (``Q4_K_M`` for
    `qwen2.5-coder:1.5b` on srv2). The same tag serves different quants on
    different rigs, so the tag is not the answer and this is.

``context_length``
    The **effective** serving window, which is a serving flag and not a model
    property. Both calls report the model's *trained* window — ``32768`` for
    every `qwen2.5-coder` tag on srv2, under ``details.context_length`` and
    ``model_info["<arch>.context_length"]`` on the native surface measured
    2026-08-18 — while the window actually being served was a serving flag that
    neither call reported unless a Modelfile pinned it. Recording the trained
    window would put a number on disk that the run did not have, which is worse
    than the null it replaces. vLLM answers this one directly, from the model
    card, and it matched the ``--max-model-len`` each server was launched with.

``concurrency``
    What decides whether greedy is reproducible at all — ADR-0027 settled that
    greedy decoding is not deterministic under continuous batching (vLLM #23138:
    one client deterministic over 70+ rounds, ~1/3 of pairs differing under
    concurrency), so ``verified`` never means "reproduces" and a run that did not
    record its concurrency cannot be read on even that weaker signal. No
    endpoint served here reports it — it is the width the server was launched
    with, and neither engine publishes that — so it refuses here, and the
    refusal is a true statement about the surface it is about.

    **It is not the last word on the field.** The refusal names where the answer
    is, and a run with host access reads it there: see :func:`resolve` and the
    ``resolved`` source, which carries the served width beside the width this
    run dispatched at, and states what the pair does and does not license. The
    number never enters the block labelled ``native``, because a host reading
    sitting under that label would destroy the one distinction this file's
    sources exist to make.

``seed``
    **Observed, never set.** Greedy bypasses the sampler RNG, so no dispatch in
    this tree sends one (``OpenAIRunner._payload`` sends ``max_tokens`` and
    ``temperature`` and nothing else) and *setting* one would be a different
    experiment that
    silently re-baselines every prior measurement (#276's perturbation set, item
    9). Recording ``null`` states a fact. Where a Modelfile pins a seed
    server-side this records the value it finds, because then the fact is
    different.

**Two engines, and they answer opposite halves of the probe set.** ollama and
vLLM are both first-class here (``detect.PORT_CONVENTIONS`` has carried both
since #164), and which one is talking decides what a null means — so the engine
is identified from what answers, never from the port, and recorded in the block:

==================  ==================  ==================================
field               native (2026-08-18) vLLM 0.26.0
==================  ==================  ==================================
``quantization``    ``Q4_K_M``          ``auto_awq`` (dev mode only)
``context_length``  ``4096``, resident  ``8192`` / ``16384``
``concurrency``     refused             refused
``seed``            refused             ``0`` (dev mode only)
==================  ==================  ==================================

Every cell above was measured on 2026-08-18 against four servers — ollama 0.32.4
on srv1 and 0.32.5 on srv2, vLLM 0.26.0 on both — and each is the reason the
derivation is written the way it is:

``context_length`` **was answerable on both, and on neither of the endpoints
the obvious guess would use.** On the native surface measured 2026-08-18 the two
describing calls reported 32768 — the model's *trained* window — while the
loaded instance was being served with 4096, and only the residency listing said
so, which is why that field read the residency listing and refused when the
model was not resident rather than writing down a window no run had. vLLM
answers from the model card unconditionally, and it matched the
``--max-model-len`` each server was launched with.

``concurrency`` **is on neither engine's surface, and the lookalike is worse than
the null.** It decides whether greedy is reproducible at all — ADR-0027 settled
that greedy decoding is not deterministic under continuous batching, and the
evidence it cites *is vLLM* (#23138). The native surface did not publish the
width its daemon was configured with. vLLM does not expose ``max_num_seqs``
anywhere: not on
``/server_info``'s full engine config, not in any of the 122 ``/metrics`` series,
not on ``/v1/models`` — searched across every parameterless GET in each server's
own ``/openapi.json`` route table. ``vllm:cache_config_info`` carries
``kv_cache_max_concurrency``, which looks like the answer and is KV-cache
capacity: srv1 ran ``--max-num-seqs 8`` and reported 16.004, srv2 ran 16 and
reported 5.314. It moves *opposite* to the quantity it resembles.

``seed`` **is where "observed, never set" needed splitting in two.** It is a
statement about what this tree dispatches, and it is not a statement about the
server: vLLM 0.26.0 defaults to ``seed=0`` on both rigs, so a vLLM run whose seed
went unrecorded was seeded by something nobody wrote down. The native surface
measured 2026-08-18 reported none.

**Dev mode is the biggest single lever.** ``/server_info`` carries the
quantization, the seed and the window, and exists only when the server was
launched with ``VLLM_SERVER_DEV_MODE=1``. With it, vLLM answers three of four;
without it, one. So those refusals name the flag: they are facts about how the
server was started, not limits on what vLLM can say.

``/collective_rpc`` is not called, and that is a decision rather than an
oversight. It exists under the same dev flag and would very likely reach the
scheduler config, but it executes a method inside the running engine — which is
not the endpoint describing itself, and a measurement rig that runs arbitrary RPC
against the server it is about to measure is a seam nobody should have to reason
about later.

**A third engine is a table entry, not a rewrite.** llama-server exposes
``/props`` — ``n_ctx``, ``total_slots`` and a model path — and ``total_slots``
would be the one place any of these three engines states its own concurrency. It
is not implemented here because nothing has asked for it and none was running to
verify it against; the arm it would need is the shape of the two above.

**The rest of the OpenAI-compatible world.** ADR-0027 measured ``/v1/models`` as
identity-free on 136 of 139 manifests, and an endpoint that answers it without
looking like vLLM is recorded as exactly that. One that answers nothing gets the
same shape as any other: four nulls, four reasons, an empty native capture. The
schema does not change under a protocol that answers almost nothing — it says so.

**Redaction runs on capture, before write.** ``run.json`` holds one URL; this
holds a server's whole self-description, and a generated Modelfile carried a
host filesystem path — measured on srv2, 2026-08-18: a ``FROM`` line naming a
blob under a service account's home, which on a home-directory install names a
user. So
every string is scrubbed on the way in: credential-bearing URLs through
``bundle.redact`` (the one redactor both rigs already use), home-directory
prefixes, and the high-confidence credential shapes. Over-redaction is free
here, because nothing compares this file.

**One capture per run directory, written when the directory is opened.** A
resume leaves the existing file alone rather than overwriting it: the block
describes the endpoint the rows were started against, and a resume against a
materially different server is refused by ``run.json``'s keyed drift, which is
where a refusal belongs.
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

    Two loads of the contract would be the five-lists problem one level down.
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
    """The bundle rig, for :func:`redact` — ``tools/`` is not a package.

    Imported for one function, and imported rather than copied: a second
    redactor is the shape ADR-0026 lens 3 exists to catch, and the one thing
    worse than a redactor with a gap is two of them with different gaps. The
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


#: The file, beside ``run.json``. Named in exactly three places — here, the two
#: runner call sites — so ``git grep`` answers "does anything read it" honestly.
OBSERVED_FILE = "observed.json"

#: The four fields :data:`identity.GROUPS` declares and nothing wrote before
#: this module. Under the names ``GROUPS`` gives them, so a reader who finds a
#: null here and a null there is looking at one field and not two.
PROBE_SET: tuple[str, ...] = (
    "quantization",
    "context_length",
    "concurrency",
    "seed",
)

#: The two moments a capture is taken. `at_open` describes the server the rows
#: were started against; `at_close` is the one that can actually answer
#: `context_length`, because by then the model is resident.
CAPTURES = "captures"
AT_OPEN = "at_open"
AT_CLOSE = "at_close"

#: The two SOURCES a capture can draw on, labelled apart because they prove
#: different things. `native` is what the endpoint this run dispatched to said
#: about itself; `host` is what the machine said. They coincide when the
#: endpoint resolves straight to that machine with nothing in between —
#: measured true on these rigs — and diverge behind a proxy or a load balancer.
NATIVE_SOURCE = "native"
HOST_SOURCE = "host"

#: The third source: neither what the endpoint said nor what the machine said,
#: but what the two together settle. Kept apart from both, because a value that
#: arrived from the host must never sit inside the block labelled `native` — a
#: reader has to be able to tell which kind of evidence a number is, and that
#: separation is the whole reason this file has sources at all.
RESOLVED_SOURCE = "resolved"

#: The two facts about batching, under the names they are recorded by. **Two
#: fields, never one, and never substituted for one another** — the shape
#: ADR-0040 settled when a per-process figure and a card total were tempting to
#: collapse. `served_width` is a ceiling the SERVER was started with;
#: `dispatch_max_parallel` is how many requests THIS run had in flight.
SERVED_WIDTH = "served_width"
DISPATCH_MAX_PARALLEL = "dispatch_max_parallel"

#: The third term (#353), and it is named for what it holds rather than for the
#: conclusion it supports. `dispatch_max_parallel` bounds the realised batch
#: only if this run was the sole client; this is how many requests the SERVER
#: finished between the open and close captures, from the server's own counter.
#: Subtract the run's own dispatched rows and the remainder is foreign traffic.
#: **Never a boolean.** A field reading `sole_client: true` because nothing was
#: detected is the exact failure this issue exists to avoid.
SERVER_COMPLETIONS = "server_completions_in_window"

#: The series that answers it on vLLM, and the label it is summed over.
#: **Measured on srv1, 2026-08-23, against vllm 0.26.0 (`b1` pip launcher):**
#: five `/v1/completions` moved it by exactly five; `/health`, `/metrics`,
#: `/ping` and `/v1/models` moved it by none; a request that failed at the API
#: layer (404 unknown model, 400 over-long prompt, 400 malformed body) moved it
#: by none while moving `http_requests_total` by one each; and two full
#: :func:`capture` passes moved it by none while moving `http_requests_total`
#: by exactly seven each. **The reading does not perturb the counter it reads**,
#: so the arithmetic needs no correction term for the harness's own traffic.
#:
#: Summed over `finished_reason`, whose values on this build are `stop`,
#: `length`, `abort`, `error` and `repetition` — a request that reached the
#: engine and ended for any reason is counted once.
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
#: endpoint, with what it would take to discharge each. ADR-0033's convention:
#: the contingency is recorded where the code is, not in a PR body, and
#: `test_every_engine_says_whether_it_has_been_run_live` fails if an engine
#: appears in neither dict — so a third arm cannot arrive unmarked, and this one
#: cannot be quietly promoted without someone deleting a line that says why.
UNVERIFIED: dict[str, str] = {
    OPENAI_COMPATIBLE: (
        "the fallback arm: an endpoint that answers /v1/models and does not "
        "look like vLLM. Not exercised live, because it is what llama-server, "
        "LM Studio and TGI would land in and none was running. It refuses all "
        "four fields by construction — /v1/models carries a window and nothing "
        "else — so the untested part is the identification, not a derivation"
    ),
}

#: Long, and for :func:`identity.probe_model`'s reason: ``verbose`` returns the
#: tokenizer arrays — 151,936 of them on the 1.5B — and a timeout tuned for a
#: version string would record "unobtainable" for a server that answered
#: perfectly well, slowly. This applies to that ONE call.
CAPTURE_TIMEOUT_S = 30.0

#: Every other call, which returns kilobytes at most. Short on purpose: a
#: capture makes a dozen requests and runs immediately before a sweep's first
#: draw, so charging all of them the `/api/show` budget would put six minutes of
#: silence in front of a run against an endpoint that drops rather than refuses.
DISCOVERY_TIMEOUT_S = 5.0


def _url(base: str, path: str) -> str:
    """Join a base URL to a path, tolerating a base that already ends in ``/v1``.

    The same rule as :func:`mcgyvr.runner._url_for`, and for the same reason: a
    ``base_url`` copied from a hosted provider's own page carries ``/v1``, and
    ``tools/bundle/worker.example.json`` documents that spelling. Without this,
    ``https://host/v1`` is probed at ``/v1/v1/models`` — a 404 that this module
    would then record as "nothing there described itself at all" about a server
    answering perfectly well. Restated here rather than imported because
    ``_url_for`` is private to a module inside ``product.SURFACE`` and this tool
    must not move that digest to reuse eight lines.

    The strip is unconditional, which is where this diverges from ``_url_for``:
    that function is only ever handed one path per protocol and both start with
    ``/v1/``, while ``VLLM_READS`` mixes ``/v1/models`` with six root-level
    paths and ``_capture_served`` adds ``/metrics``. Stripping only for ``/v1/``
    paths sent every root path to ``/v1/version``, ``/v1/server_info`` and so
    on — 404s that were then recorded as refusals blaming an unset
    ``VLLM_SERVER_DEV_MODE``, sending a reader after a flag when the cause was
    the URL. Every path here is written from the root, so the base's ``/v1``
    is redundant in all cases, not just some.
    """
    base = base.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + path


#: **D5, 2026-08-19: elide BY NAME, with a length backstop.**
#:
#: The three tokenizer arrays are elided because of *what they are*, not because
#: of how long they happen to be. A size threshold was doing the right thing for
#: the wrong reason, and the reason is what generalises: at 512 the same
#: constant decided both "this is a tokenizer array" and "this list is too long
#: to read", which are different judgements. The 1.5B's ``tensors`` is 338 rows
#: and sits inline; a 30B's is thousands and would have been elided by length —
#: silently losing a STRUCTURAL list that a reader can act on, while the
#: tokenizer arrays it was aimed at were already covered by name.
#:
#: The arrays are hashed into ``run.json``'s ``vocabulary_sha256`` and
#: ``merges_sha256`` regardless, so an elided array's digest is a join key back
#: to those and its count is the fact worth keeping.
#: The two arrays named here are exactly the ones ``identity`` hashes into
#: ``vocabulary_sha256`` and ``merges_sha256``, so an elided array's digest is
#: a join key back to a field that already exists rather than a new one. The
#: rest are the sibling GGUF tokenizer arrays, which are the same KIND of thing
#: and are elided for the same reason.
ELIDE_BY_NAME: frozenset[str] = frozenset(
    {
        "tokenizer.ggml.tokens",
        "tokenizer.ggml.merges",
        "tokenizer.ggml.token_type",
        "tokenizer.ggml.scores",
    }
)

#: The backstop, for a list this does not know by name. Deliberately far above
#: any structural list these models produce — the largest seen is in the low
#: thousands — so it catches an unforeseen array without quietly eliding a
#: tensor table. A list hitting this is worth noticing, not just shrinking.
MAX_INLINE_ITEMS = 4096

#: What an elided list is replaced by. A dict rather than a truncated list, so
#: no reader can mistake it for the array itself.
ELIDED = "elided"

_REDACTED = "<redacted>"

# A URL carrying credentials, found *inside* a longer string as well as alone.
# `bundle.redact` does the removal — this only locates the URLs it is given,
# because `urlsplit` over a 13 KB Modelfile finds no netloc at all.
_CREDENTIAL_URL = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s\"'<>]*@[^\s\"'<>]*")

# A home-directory prefix, which names a user. The rest of the path stays: the
# blob filename under it is `sha256-<hex>`, and that digest is the one piece of
# weights identity the native surface exposes.
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

    Recursive because the risk is not at the top level: the Modelfile is one
    string inside one key, and the tensor rows are dicts inside a list. A
    non-string leaf — a number, a bool, ``null`` — is returned as it is, and a
    dict key is scrubbed too, since a native ``model_info``'s keys are model-
    supplied strings.
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
    server sent, including a free-text Modelfile and 58 KB of Prometheus text,
    any of which can contain something URL-shaped and invalid. Left unguarded it
    took down the whole sweep — `record_run` calls the writer after `run.json` is
    already on disk, so a raise there means no rows and a traceback, which is
    exactly the "worst of both" :func:`capture` promises not to be. An
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

    D5: a list is elided when its KEY names it a tokenizer array
    (:data:`ELIDE_BY_NAME`), or — failing that — when it exceeds
    :data:`MAX_INLINE_ITEMS`. Each summary records which rule fired, because
    "this was elided because we know what it is" and "this was elided because it
    was surprisingly long" are different facts about a run.

    The summary is the count and :func:`identity.digest` of the whole array —
    the same digest convention ``run.json`` uses, so a reader can join an elided
    array here to ``vocabulary_sha256`` there without rehashing anything.
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
    server decides what a refusal means. A native pair used to be tried first —
    it was the only surface that described the weights — and anything that did
    not answer it was asked the OpenAI-compatible questions instead. That arm
    went with its backend on 2026-09-06 (``archive/forensic-ollama/``), so
    there is one arm and the identification still happens from what answered:
    ``_identify`` tells vLLM from a bare OpenAI-compatible server from an
    endpoint that said nothing, and those are three different facts about a run.

    The arm reaches the identity module's fetchers by attribute lookup rather
    than copying them, so a test that patches the seam patches this path too,
    and no fifth ``urllib`` wrapper joins the four already in this tree.

    Never raises. An endpoint that is down, slow or speaking another protocol
    produces the same shape as one that answers — that is what makes the shape
    readable — and a manifest that could not be written because the probe threw
    would be the worst of both.
    """
    base = endpoint.rstrip("/")
    native, engine = _capture_served(base)
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
    return scrub(elide(block))


#: Every read-only endpoint vLLM 0.26.0 answers, measured by asking the server
#: for its own route table (``/openapi.json``) and taking each parameterless
#: GET — 11 of them on both srv1 and srv2. Discovered rather than listed from
#: documentation, which is why ``/is_paused``, ``/load`` and ``/get_world_size``
#: are here at all.
#:
#: ``/collective_rpc`` is deliberately NOT here. It exists (dev mode), and it
#: would very likely reach the scheduler config that :data:`UNVERIFIED` used to
#: guess at — but it executes a method inside the running engine, which is not
#: the endpoint describing itself, and a measurement rig that runs arbitrary
#: RPC against the server it is about to measure is a seam nobody should have
#: to reason about later.
VLLM_READS: tuple[tuple[str, str], ...] = (
    ("models", "/v1/models"),
    ("version", "/version"),
    ("server_info", "/server_info"),
    ("load", "/load"),
    ("is_sleeping", "/is_sleeping"),
    ("is_paused", "/is_paused"),
    ("world_size", "/get_world_size"),
)


# `_capture_ollama` and the three read-only endpoints it enumerated stood
# here. One arm remains, and `capture` no longer has to decide which surface it
# is looking at before it can ask a question. The removed arm, its endpoints
# and the readings it took are in `archive/forensic-ollama/`.


def _capture_served(base: str) -> tuple[dict[str, Any], str]:
    """Everything the OpenAI-compatible surface will answer, vLLM's extras too.

    ``/metrics`` is Prometheus text rather than JSON, and it is captured raw:
    parsing it here would decide, today, which of 122 series a reader may ever
    ask about. 58 KB in a file nothing compares is a cheap price for a later
    question about queue depth or cache blocks being answerable off a run
    already on disk instead of needing the rig back.
    """
    native: dict[str, Any] = {}
    for name, path in VLLM_READS:
        answer = identity._get_json(_url(base, path), timeout=DISCOVERY_TIMEOUT_S)
        if answer is not None:
            native[name] = answer
    metrics = _get_text(_url(base, "/metrics"), timeout=DISCOVERY_TIMEOUT_S)
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


#: What a refusal says on the engine that has no route at all. **Measured on
#: srv1, 2026-08-23**, and it is a statement about the ENGINE rather than about
#: this reading: ollama serves no `/metrics` on 11434 (404, both rigs), and its
#: child `llama-server` answers `501 {"message": "This server does not support
#: metrics endpoint. Start it with `--metrics`"}` while its own `/props`
# A refusal constant stood here naming why one engine served no request
# counter to difference -- 404 on /metrics, a llama-server child answering 501
# and naming the flag its parent did not pass, and a /slots `id_task` that is
# monotonic but increments by neither 1 nor a stable number per request
# (measured 5.0, 7.0, 7.0, 5.67 on srv1 2026-08-23). That engine is in
# `archive/forensic-ollama/` and the refutation of `/slots` with it. Every
# engine served here answers /metrics.


def _server_completions(
    native: dict[str, Any] | None,
    opened: dict[str, Any] | None,
    when: str,
) -> dict[str, Any]:
    """How many requests the SERVER finished between the two captures (#353).

    **Recorded, not concluded.** The value is the server's own counter delta.
    Foreign traffic is that minus the rows this run dispatched, and the
    subtraction is deliberately NOT done here: the dispatched-row count is a
    property of the runner, it is not passed to this module, and passing it
    would touch both runner call sites, which are SURFACE. It is in `run.json`
    beside this file, so a reader has both terms and the arithmetic is written
    down in the note. **Zero difference is measured sole-clientness; anything
    else names how much else the server served.**

    Three states, not two (ADR-0027 D2 applied to a claim rather than to a
    reading): a number is *measured*; a refusal on an engine with no counter is
    *looked in a way that cannot see*; a refusal at the open capture is *not
    looked yet*. None of them is a boolean.
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
    every engine above, and the refusal is correct: the width is on no network
    surface any of them serves. The refusal ends by naming where the answer
    *is* — "obtainable only with access to the serving host
    (``tools/bench/serving/``)" — and the ``host`` block written beside it in
    this same file is produced by exactly that module, with exactly that access.
    So the record held the number and the field declared for it read ``null``.
    This is where the two meet, and the native refusal stays exactly as it was,
    because it remains a true statement about the surface it is about.

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

    Sole-clientness is the third term, and **as of #353 one engine can state
    it and the other cannot** — which is why it is a recorded measurement with
    a window rather than a boolean. On vLLM,
    ``server_completions_in_window`` is the server's own count of requests it
    finished between the two captures; subtract the rows this run dispatched
    and the remainder is foreign traffic. An engine that serves no counter to
    difference refuses the field, naming where the answer would be.

    **The dispatch side is passed in, never read from a constant here.** It is a
    property of the endpoint the runner actually built (ADR-0027 D4: computed,
    never typed); a literal in this module would describe a dispatcher it cannot
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
            "the field refuses and names where the answer would be, which is a "
            "fact about reach and not about the run. Nothing compares this "
            "block (ADR-0027 D7)"
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

    The close capture is not a nicety. ``context_length`` — the field this whole
    block exists to record, and the one whose measured value (4096 served
    against 32768 advertised) is the lane's finding — reads ``/api/ps``, which
    lists only models that are RESIDENT. At open, on a fresh directory, nothing
    is loaded yet, so the field was structurally refused on every first run: the
    capture was taken before the model arrived and then noted that it was not
    there. At close the model is certainly resident, so the field answers.

    The close capture also records what the server looked like *under* the load
    the run applied, which nothing else does.

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
        # A pre-#286 single-capture file is migrated forward rather than
        # overwritten: it was an `at_open` capture before the key existed.
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
    """The four declared fields off the OpenAI-compatible surface (D2).

    The only arm now. It was written as the other half of a pair — vLLM answers
    the field the native surface could not and cannot answer the one it could —
    and what survives that pairing is the rule each refusal is held to: a
    refusal names the engine it is a fact about, so ``null`` is never just
    "unavailable".

    **Unverified against a live vLLM** — see :data:`UNVERIFIED`. Every branch
    here is tested against the documented shapes; none has been run against a
    server that produced them.
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
        "field means — is not on vLLM 0.26.0's HTTP surface. Searched "
        "exhaustively on 2026-08-18: every parameterless GET in the server's "
        "own /openapi.json route table (11 answered) on srv1 and srv2, "
        "including /server_info's full engine config, all 122 /metrics series, "
        "and /v1/models. `vllm:cache_config_info.kv_cache_max_concurrency` "
        "looks like the answer and is NOT: it is KV-cache capacity, and it "
        "moves opposite to the flag — srv1 ran --max-num-seqs 8 and reported "
        "16.004, srv2 ran 16 and reported 5.314. It is not unknowable, only "
        "unaskable: a concurrency ramp recovers it, and on srv1 it read the "
        "knee at exactly 8 — throughput plateauing at 106.5 tok/s and "
        "per-request latency flat at ~9.5s through n=8 before the queue forms. "
        "That is a measurement this capture must not make, because it would "
        f"perturb the run it describes. The raw metrics are under {NATIVE}"
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


# `vllm_config` on /server_info is a Python repr rather than a JSON object —
# measured, 3,118 characters on srv1 — so the three settings that live only
# there are lifted by name. Narrow on purpose: the whole string is captured
# verbatim beside this, so a value this pattern misses is still on disk, and a
# repr that changes shape in a later vLLM degrades to a refusal with a reason
# rather than to a wrong number.
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
    dispatch used is the sort of plausible substitute D2 exists to forbid.
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


# A native-surface probe set stood here, with `_resident_row`, `_tag_row` and
# `_parameters` -- the four declared fields read off a native surface, and the
# three row-matchers that dug them out of an inventory listing, a residency
# listing and a Modelfile's PARAMETER text. One engine answers the probe set
# now, through `_served_probe_set`. All of it is in `archive/forensic-ollama/`,
# with the reasoning for each field's refusal.


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
