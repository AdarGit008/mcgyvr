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
request time can answer them, and on ollama's native surface it answers one of
the four. That is the honest result and it is recorded as such, per D2: a field
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
    ``model_info["<arch>.context_length"]`` — and ollama serves ``num_ctx``,
    which defaults to the server's own setting and is reported by neither call
    unless a Modelfile pins it. `qwen2.5-coder:1.5b` has no ``parameters`` key
    at all. So this reads ``num_ctx`` where a Modelfile states it and refuses
    otherwise: recording ``32768`` would put a number on disk that the run did
    not have, which is worse than the null it replaces. The trained window is
    still on disk, in :data:`NATIVE` below, under the name the endpoint gave it.

``concurrency``
    What decides whether greedy is reproducible at all — ADR-0027 settled that
    greedy decoding is not deterministic under continuous batching (vLLM #23138:
    one client deterministic over 70+ rounds, ~1/3 of pairs differing under
    concurrency), so ``verified`` never means "reproduces" and a run that did not
    record its concurrency cannot be read on even that weaker signal. Neither
    native call reports it — it is the server's own ``OLLAMA_NUM_PARALLEL``,
    which ollama does not expose — so it refuses, and the refusal is itself the
    fact a later reader needs.

``seed``
    **Observed, never set.** Greedy bypasses the sampler RNG, so no dispatch in
    this tree sends one (``runner.OllamaRunner._payload`` sends ``num_predict``
    and ``temperature``; ``OpenAIRunner._payload`` sends ``max_tokens`` and
    ``temperature``) and *setting* one would be a different experiment that
    silently re-baselines every prior measurement (#276's perturbation set, item
    9). Recording ``null`` states a fact. Where a Modelfile pins a seed
    server-side this records the value it finds, because then the fact is
    different.

**Two engines, and they answer opposite halves of the probe set.** ollama and
vLLM are both first-class here (``detect.PORT_CONVENTIONS`` has carried both
since #164), and which one is talking decides what a null means — so the engine
is identified from what answers, never from the port, and recorded in the block:

==================  ==================  ==================================
field               ollama              vLLM 0.26.0
==================  ==================  ==================================
``quantization``    ``Q4_K_M``          ``auto_awq`` (dev mode only)
``context_length``  ``4096``, resident  ``8192`` / ``16384``
``concurrency``     refused             refused
``seed``            refused             ``0`` (dev mode only)
==================  ==================  ==================================

Every cell above was measured on 2026-08-18 against four servers — ollama 0.32.4
on srv1 and 0.32.5 on srv2, vLLM 0.26.0 on both — and each is the reason the
derivation is written the way it is:

``context_length`` **is answerable on both, and on neither of the endpoints the
obvious guess would use.** ollama's ``/api/tags`` and ``/api/show`` report 32768,
which is the model's *trained* window; the loaded instance is being served with
4096, and only ``/api/ps`` says so — so the field reads ``/api/ps`` and refuses
when the model is not resident, rather than writing down a window no run had.
vLLM answers from the model card unconditionally, and it matched the
``--max-model-len`` each server was launched with.

``concurrency`` **is on neither engine's surface, and the lookalike is worse than
the null.** It decides whether greedy is reproducible at all — ADR-0027 settled
that greedy decoding is not deterministic under continuous batching, and the
evidence it cites *is vLLM* (#23138). ollama does not expose
``OLLAMA_NUM_PARALLEL``. vLLM does not expose ``max_num_seqs`` anywhere: not on
``/server_info``'s full engine config, not in any of the 122 ``/metrics`` series,
not on ``/v1/models`` — searched across every parameterless GET in each server's
own ``/openapi.json`` route table. ``vllm:cache_config_info`` carries
``kv_cache_max_concurrency``, which looks like the answer and is KV-cache
capacity: srv1 ran ``--max-num-seqs 8`` and reported 16.004, srv2 ran 16 and
reported 5.314. It moves *opposite* to the quantity it resembles.

``seed`` **is where "observed, never set" needed splitting in two.** It is a
statement about what this tree dispatches, and it is not a statement about the
server: vLLM 0.26.0 defaults to ``seed=0`` on both rigs, so a vLLM run whose seed
went unrecorded was seeded by something nobody wrote down. ollama reports none.

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
holds a server's whole self-description, and the generated Modelfile carries a
host filesystem path — measured on srv2: ``FROM /usr/share/ollama/.ollama/
models/blobs/sha256-…``, which on a home-directory install names a user. So
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

#: Where the comprehensive capture lives, under the endpoint's own key names.
#: Everything else in the file is this module's reading of it.
NATIVE = "native"

#: Which server answered, identified from what it said rather than from its
#: port. On the block because a refusal cannot be read without it: `null` for
#: `context_length` means "ollama does not expose num_ctx" on one engine and
#: "this vLLM did not list max_model_len" on the other, and those are different
#: facts about a run.
ENGINE = "engine"

OLLAMA = "ollama"
VLLM = "vllm"
OPENAI_COMPATIBLE = "openai-compatible"
UNREACHABLE = "unreachable"

ENGINES: tuple[str, ...] = (OLLAMA, VLLM, OPENAI_COMPATIBLE, UNREACHABLE)

#: Engines whose shapes this module has been run against a LIVE endpoint. Every
#: number in this module — in the docstring, in the refusal reasons, in the test
#: fixtures — is a measurement from one of these runs, not a documented shape.
VERIFIED_LIVE: dict[str, str] = {
    OLLAMA: (
        "srv1 (0.32.4) and srv2 (0.32.5), qwen2.5-coder:1.5b and :7b, "
        "2026-08-18. 5 of 13 tried endpoints answered; the read-only ones are "
        "OLLAMA_READS plus the /api/show POST"
    ),
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
#: tokenizer arrays, and a timeout tuned for a version string would record
#: "unobtainable" for a server that answered perfectly well, slowly.
CAPTURE_TIMEOUT_S = 30.0

#: A list longer than this is recorded as its length and its digest rather than
#: inline. Comprehensive means nothing a reader can act on is lost, not that
#: 151,936 tokenizer entries are copied into every run directory: the arrays are
#: already hashed into ``run.json``'s ``vocabulary_sha256`` and
#: ``merges_sha256``, so the digest here is a join key and the count is the fact.
#: 512 keeps every structural list inline — the 1.5B's ``tensors`` is 338 rows —
#: and elides only the three tokenizer arrays.
MAX_INLINE_ITEMS = 512

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
    dict key is scrubbed too, since ollama's ``model_info`` keys are model-
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
    """One string, through the three redactions, in the order they compose."""
    bundle = _bundle_rig()
    text = _CREDENTIAL_URL.sub(lambda m: bundle.redact(m.group(0)), text)
    text = _HOME_PATH.sub(lambda m: f"{m.group('root')}/{_REDACTED}", text)
    for shape in _TOKEN_SHAPES:
        text = shape.sub(_REDACTED, text)
    return text


def elide(value: Any) -> Any:
    """``value`` with any list over :data:`MAX_INLINE_ITEMS` summarised.

    The summary is the count and :func:`identity.digest` of the whole array —
    the same digest convention ``run.json`` uses, so a reader can join an elided
    array here to ``vocabulary_sha256`` there without rehashing anything.
    """
    if isinstance(value, dict):
        return {k: elide(v) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > MAX_INLINE_ITEMS:
            return {ELIDED: True, "count": len(value), "sha256": identity.digest(value)}
        return [elide(v) for v in value]
    return value


def capture(
    endpoint: str, model: str, *, timeout: float = CAPTURE_TIMEOUT_S
) -> dict[str, Any]:
    """The whole block, ready to write: engine, probe set, reasons, capture.

    **The engine is identified from what answers, never from the port.**
    ``detect.PORT_CONVENTIONS`` guesses identity from a port because what it
    needs downstream is the wire protocol; this needs the *server*, because the
    server decides what a refusal means. So ollama's native pair is tried first
    — it is the only surface that describes the weights — and anything that does
    not answer it is asked the OpenAI-compatible questions instead.

    Ollama's two calls are exactly :func:`identity.probe_model`'s. Both arms
    reach the identity module's fetchers by attribute lookup rather than copying
    them, so a test that patches the seam patches this path too, and no fifth
    ``urllib`` wrapper joins the four already in this tree.

    Never raises. An endpoint that is down, slow or speaking another protocol
    produces the same shape as one that answers — that is what makes the shape
    readable — and a manifest that could not be written because the probe threw
    would be the worst of both.
    """
    base = endpoint.rstrip("/")
    native, engine = _capture_ollama(base, model, timeout)
    if engine is OLLAMA:
        fields, reasons = _ollama_probe_set(native, model)
    else:
        native, engine = _capture_served(base, timeout)
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


#: Every read-only endpoint ollama answers, as measured on srv1 (0.32.4) and
#: srv2 (0.32.5) on 2026-08-18. ``/api/show`` is the POST that reads and is
#: made separately because it needs the model in its body. Nothing that
#: generates, pulls, copies or deletes is here: a capture must not move the
#: thing it is capturing.
OLLAMA_READS: tuple[tuple[str, str], ...] = (
    ("tags", "/api/tags"),
    ("ps", "/api/ps"),
    ("version", "/api/version"),
)

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


def _capture_ollama(
    base: str, model: str, timeout: float
) -> tuple[dict[str, Any], str | None]:
    """Everything ollama will answer, and whether this is an ollama at all.

    One endpoint answering is enough to call it ollama: a build that has dropped
    one still describes an inventory nothing else does, and falling through to
    the OpenAI arm would throw that away for a stricter test that buys nothing.
    """
    native: dict[str, Any] = {}
    for name, path in OLLAMA_READS:
        answer = identity._get_json(f"{base}{path}", timeout=timeout)
        if answer is not None:
            native[name] = answer
    show = identity._post_json(
        f"{base}/api/show", {"model": model, "verbose": True}, timeout=timeout
    )
    if show is not None:
        native["show"] = show
    if not native:
        return {}, None
    return native, OLLAMA


def _capture_served(base: str, timeout: float) -> tuple[dict[str, Any], str]:
    """Everything the OpenAI-compatible surface will answer, vLLM's extras too.

    ``/metrics`` is Prometheus text rather than JSON, and it is captured raw:
    parsing it here would decide, today, which of 122 series a reader may ever
    ask about. 58 KB in a file nothing compares is a cheap price for a later
    question about queue depth or cache blocks being answerable off a run
    already on disk instead of needing the rig back.
    """
    native: dict[str, Any] = {}
    for name, path in VLLM_READS:
        answer = identity._get_json(f"{base}{path}", timeout=timeout)
        if answer is not None:
            native[name] = answer
    metrics = _get_text(f"{base}/metrics", timeout=timeout)
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


def write(
    out: Path, endpoint: str, model: str, *, timeout: float = CAPTURE_TIMEOUT_S
) -> Path | None:
    """Write :data:`OBSERVED_FILE` beside ``run.json``, once per directory.

    Returns the path written, or ``None`` when the file was already there — a
    resume keeps the capture the directory was opened with rather than restating
    it, because this block is not a comparison and overwriting it would lose the
    only record of what the endpoint said when the rows started.
    """
    path = out / OBSERVED_FILE
    if path.exists():
        return None
    out.mkdir(parents=True, exist_ok=True)
    block = capture(endpoint, model, timeout=timeout)
    path.write_text(json.dumps(block, indent=2) + "\n", encoding="utf-8")
    return path


def _served_probe_set(
    base: str, model: str, native: dict[str, Any], engine: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """The four declared fields off the OpenAI-compatible surface (D2).

    vLLM answers the one ollama cannot and cannot answer the one ollama does,
    so this is not a degraded copy of the arm above — it is the other half of
    the probe set, and each refusal names the engine it is a fact about.

    **Unverified against a live vLLM** — see :data:`UNVERIFIED`. Every branch
    here is tested against the documented shapes; none has been run against a
    server that produced them.
    """
    if engine is UNREACHABLE:
        return (
            dict.fromkeys(PROBE_SET),
            dict.fromkeys(
                PROBE_SET,
                f"{base} answered neither ollama's native pair nor /v1/models; "
                "nothing there described itself at all",
            ),
        )

    where = "vLLM" if engine is VLLM else "this OpenAI-compatible server"
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
            "this reads. It is on /server_info, which exists only when the "
            "server was launched with VLLM_SERVER_DEV_MODE=1 — measured "
            "`quantization=auto_awq` on srv1 and srv2 with the flag set, and "
            "the endpoint 404s without it. This is therefore a fact about how "
            "the server was started, not about what vLLM can say"
        )

    max_model_len = _model_field(native, model, "max_model_len")
    if isinstance(max_model_len, int):
        fields["context_length"] = max_model_len
    elif isinstance(config.get("max_seq_len"), int):
        fields["context_length"] = config["max_seq_len"]
    else:
        fields["context_length"] = None
        reasons["context_length"] = (
            f"{where} listed no max_model_len on the model card for {model!r} "
            "and no max_seq_len on /server_info"
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
        "unaskable: a concurrency ramp recovers it (tools/bench/census.py "
        "--concurrency), and on srv1 it read the knee at exactly 8 — "
        "throughput plateauing at 106.5 tok/s and per-request latency flat at "
        "~9.5s through n=8 before the queue forms. That is a measurement this "
        f"capture must not make, because it would perturb the run it describes. "
        f"The raw metrics are recorded under {NATIVE}, so the material is on disk"
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


def _config_info(native: dict[str, Any], label: str) -> Any:
    """``label`` from any Prometheus ``*_config_info`` label set, or ``None``.

    vLLM publishes engine configuration as Info metrics — a series whose value
    is always 1 and whose labels are the settings. Which series carries which
    setting has moved between releases, so this scans every ``_config_info``
    series rather than naming one, and returns the first match as a number
    where it is one. Read narrowly on purpose: the raw text is captured whole,
    so a reader is never limited to what this function knows how to find.
    """
    metrics = native.get("metrics")
    if not isinstance(metrics, str):
        return None
    for line in metrics.splitlines():
        line = line.strip()
        if line.startswith("#") or "_config_info{" not in line:
            continue
        labels = line[line.index("{") + 1 : line.rindex("}")] if "}" in line else ""
        for pair in labels.split(","):
            name, _, raw = pair.partition("=")
            if name.strip() == label:
                return _as_number(raw.strip().strip('"'))
    return None


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


def _ollama_probe_set(
    native: dict[str, Any], model: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """The four declared fields off ollama's read-only surface (D2).

    Every field in :data:`PROBE_SET` is always present. An **absent** key would
    mean the record predates the contract, identically to ``run.json``, so a
    capture made from here on never produces one.
    """
    tags = native.get("tags")
    show = native.get("show")
    show_details = _mapping(show).get("details")
    tags_details = _mapping(_tag_row(tags, model)).get("details")
    details = _mapping(show_details) or _mapping(tags_details)
    parameters = _parameters(show)
    resident = _mapping(_resident_row(native, model))

    fields: dict[str, Any] = {}
    reasons: dict[str, str] = {}

    quantization = details.get("quantization_level")
    if isinstance(quantization, str) and quantization:
        fields["quantization"] = quantization
    else:
        fields["quantization"] = None
        reasons["quantization"] = (
            "neither /api/show nor /api/tags gave details.quantization_level"
        )

    # `/api/ps` — and ONLY `/api/ps` — reports the window a loaded model is
    # actually being served with. Measured on both rigs, 2026-08-18: 4096,
    # against a trained window of 32768 that `/api/tags` and `/api/show` both
    # report. Recording the 32768 would have put a window on disk that no run
    # ever had; the loaded model's own number is the effective one, and it is
    # ollama's `num_ctx` default rather than anything this tree sets.
    loaded_window = resident.get("context_length")
    pinned = parameters.get("num_ctx")
    if isinstance(loaded_window, int):
        fields["context_length"] = loaded_window
    elif pinned is not None:
        fields["context_length"] = pinned
    else:
        fields["context_length"] = None
        reasons["context_length"] = (
            f"the effective window is on /api/ps, which lists only models that "
            f"are RESIDENT, and {model!r} was not loaded when this was "
            "captured. The window /api/tags and /api/show report is the "
            f"model's TRAINED one — recorded under {NATIVE}, never here, "
            "because it is not the window a run gets. A capture taken once the "
            "model is in memory answers this field"
        )

    # Both of the refusals below are refusals of REACH, not of existence, and
    # they say so. Ollama does not serve models itself: it runs llama.cpp's
    # `llama-server` per loaded model and proxies to it, and that child answers
    # both fields on its own `/props` and `/slots` — bound to 127.0.0.1 on a
    # port chosen at load time. A capture written by the dispatching client
    # cannot reach 127.0.0.1 on the serving host, ever. So the answer exists,
    # it is not here, and the reason names where it is rather than implying
    # nobody can know. `tools/bench/census.py` reads it with host access.
    fields["concurrency"] = None
    reasons["concurrency"] = (
        "not on any endpoint ollama serves over the network. It is "
        "OLLAMA_NUM_PARALLEL, and it reaches `llama-server`'s /props as "
        "`total_slots` on 127.0.0.1 — measured 2026-08-18 as 2 on srv1 and 1 "
        "on srv2, which is two rigs serving at different widths. Obtainable "
        "only with access to the serving host (tools/bench/census.py), never "
        "from here. Recorded as a refusal because it is the term ADR-0027 "
        "needs: greedy is not deterministic under continuous batching, so a "
        "run without it cannot be read as reproducing even weakly"
    )

    seed = parameters.get("seed")
    if seed is not None:
        fields["seed"] = seed
    else:
        fields["seed"] = None
        reasons["seed"] = (
            "no dispatch in this tree sends a seed, no Modelfile on this model "
            "pins one, and ollama's network API reports none. It IS observable "
            "on `llama-server`'s /slots as `params.seed`, on 127.0.0.1 and so "
            "out of this capture's reach: measured 4294967295 on both rigs "
            "2026-08-18, which is llama.cpp's `draw a fresh random seed per "
            "request`. Greedy does not read it; the sampled arm does, so those "
            "draws are irreproducible by construction on this engine — unlike "
            "vLLM, which defaults to seed=0. Setting one is a different "
            "experiment that would re-baseline every prior measurement (#276, "
            "item 9)"
        )

    return fields, reasons


def _resident_row(native: dict[str, Any], model: str) -> Any:
    """The ``/api/ps`` row for ``model``, or None if it is not in memory.

    Matched on ``name`` and ``model`` like the ``/api/tags`` row, and for the
    same reason: both are carried, both were the same string on every row
    measured here, and taking whichever is present costs nothing.
    """
    rows = _mapping(native.get("ps")).get("models")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and model in (row.get("name"), row.get("model")):
            return row
    return None


def _mapping(value: Any) -> dict[str, Any]:
    """``value`` if it is a dict, else an empty one — so callers stay flat."""
    return value if isinstance(value, dict) else {}


def _tag_row(tags: Any, model: str) -> Any:
    """The ``/api/tags`` row for ``model``, matched on ``name`` and ``model``.

    Both are carried and both are the same string on every row measured here;
    taking whichever is present costs nothing against a build that drops one.
    """
    rows = _mapping(tags).get("models")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and model in (row.get("name"), row.get("model")):
            return row
    return None


def _parameters(show: Any) -> dict[str, Any]:
    """``/api/show``'s ``parameters`` blob, parsed into a mapping.

    ollama returns the Modelfile's ``PARAMETER`` lines as one text field —
    ``name value`` per line, values quoted where they contain spaces, repeated
    names for list-valued parameters like ``stop`` — and omits the key entirely
    when the model pins nothing, which is the case for every `qwen2.5-coder` tag
    on srv2. Ints and floats are converted so a window reads as a number;
    everything else stays the string the server sent. A repeated name keeps the
    first value, which is only ever ``stop`` and is not read here.
    """
    text = _mapping(show).get("parameters")
    if not isinstance(text, str):
        return {}
    parsed: dict[str, Any] = {}
    for line in text.splitlines():
        name, _, raw = line.strip().partition(" ")
        raw = raw.strip().strip('"')
        if not name or not raw or name in parsed:
            continue
        parsed[name] = _as_number(raw)
    return parsed


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
