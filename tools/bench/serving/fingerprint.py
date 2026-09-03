#!/usr/bin/env python3
"""The serving configuration, read whole and pinned as two digests.

**What this closes.** `product_sha256` pins the code, `bar_sha256` pins the bar,
`model_sha256` pins the weights — and nothing pinned *how the model is served*,
which ADR-0024 records as having already moved results twice. Two runs against
one model, one revision and one bar can still disagree because one server had
prefix caching on, or ran a different attention kernel, or enforced structured
output. None of that was on disk.

**Two digests, because one would be a tripwire nobody could leave armed.**

``serving_semantic_sha256``
    Everything that changes what the model emits: the sampler defaults, dtype
    and KV dtype, prefix caching and chunked prefill, the compilation and kernel
    choices, structured-output enforcement, the seed. This is the number a guard
    could one day key on.

``serving_operational_sha256``
    Everything that does not: metrics flags, tracing endpoints, log verbosity,
    ports. Real configuration, worth recording, and it must not re-baseline a
    round. A single digest would move when somebody enabled a counter, and a
    pin that fires on noise is one that gets switched off.

**An unrecognised key is an error, not a default.** :func:`classify` refuses to
guess. A new vLLM release adding a field would otherwise fall to whichever side
the default named — and if that side were "operational", a setting that changes
output would silently drop out of the semantic pin while the pin went on looking
green. The engines' vocabularies are declared below and
``tests/test_serving.py`` holds the live configs to them.

**Both engines land in one shape.** vLLM states its config as a Python repr on
``/server_info``; ollama's is split between its child process's command line and
that child's ``/props``. Different sources, different spellings, one normalised
structure — so the two digests mean the same thing on either engine.

**Nothing reads this for comparison.** Same discipline as the `observed` block
(ADR-0027 D7): it records, and promotion into anything that refuses a table is
the owner's decision, visible in a diff.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _contract() -> types.ModuleType:
    cached = sys.modules.get("serving_contract")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "serving_contract", HERE / "contract.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["serving_contract"] = module
    spec.loader.exec_module(module)
    return module


contract = _contract()

#: Settings that change what the model emits. A difference here makes two runs
#: incomparable on output, which is the whole reason the digest exists.
SEMANTIC: frozenset[str] = frozenset(
    {
        # weights and numerics
        "model",
        "served_model_name",
        "revision",
        "quantization",
        "quantization_config",
        "dtype",
        "kv_cache_dtype",
        "load_format",
        "model_ftype",
        "weights_path",
        # tokenizer — a different tokenizer is a different instrument
        "tokenizer",
        "tokenizer_mode",
        "tokenizer_revision",
        "skip_tokenizer_init",
        "chat_template",
        "chat_template_caps",
        "bos_token",
        "eos_token",
        "media_marker",
        # placement — where a tensor is computed. Declared output-neutral until
        # 2026-09-03 and measured not to be: `n_cpu_moe` 0 vs 99 on one build
        # moved 9 of 257 verdicts (3.50pp, own-null bound 1.47pp). Two cells
        # of one model at two offload settings are therefore incomparable on
        # output until a placement null says otherwise, and that is the
        # finding, not an inconvenience (ADR-0041).
        "n_gpu_layers",
        "n_cpu_moe",
        "threads",
        "mmap",
        # the window and how it is managed
        "max_seq_len",
        "n_ctx",
        "context_shift",
        "keep",
        # sampling — every one of these decides an emitted token
        "seed",
        "temperature",
        "top_k",
        "top_p",
        "min_p",
        "typical_p",
        "repeat_penalty",
        "repeat_last_n",
        "frequency_penalty",
        "presence_penalty",
        "mirostat",
        "mirostat_tau",
        "mirostat_eta",
        "dynatemp_range",
        "dynatemp_exponent",
        "xtc_probability",
        "xtc_threshold",
        "top_n_sigma",
        "dry_multiplier",
        "dry_base",
        "dry_allowed_length",
        "dry_penalty_last_n",
        "samplers",
        "backend_sampling",
        "min_keep",
        "n_probs",
        "post_sampling_probs",
        "ignore_eos",
        "n_discard",
        "n_keep",
        "n_predict",
        "max_tokens",
        # structured output — ADR-0009's territory: enforcement here changes
        # what a reply CAN be, so a refusal stops measuring the model
        "structured_outputs_config",
        "backend",
        "disable_any_whitespace",
        "disable_additional_properties",
        "reasoning_parser",
        "reasoning_parser_plugin",
        "enable_in_reasoning",
        "reasoning_format",
        "reasoning_in_content",
        "chat_format",
        "generation_prompt",
        "response_format",
        "guided_decoding_backend",
        # kernels and compilation — measured to move greedy deltas
        "compilation_config",
        "kernel_config",
        "enforce_eager",
        "flash_attn",
        "moe_backend",
        "linear_backend",
        "ir_op_priority",
        "custom_ops",
        "cudagraph_mode",
        "mode",
        # batching and caching — decide whether a re-run reproduces at all
        "enable_prefix_caching",
        "enable_chunked_prefill",
        "n_parallel",
        "total_slots",
        "batch_size",
        "ubatch_size",
        "block_size",
        "trust_remote_code",
        "speculative_config",
        "pooler_config",
        "lora",
        "speculative.types",
        "stream",
        # topology — changes reduction order, and so the arithmetic
        "tensor_parallel_size",
        "pipeline_parallel_size",
        "data_parallel_size",
        "decode_context_parallel_size",
        "dcp_comm_backend",
        "disable_custom_all_reduce",
        "enable_return_routed_experts",
        "device_config",
        "gpu_memory_utilization",
    }
)

#: Settings that do not change what the model emits. Recorded, never in the
#: semantic pin, so enabling a counter cannot re-baseline a round.
OPERATIONAL: frozenset[str] = frozenset(
    {
        "observability_config",
        "show_hidden_metrics_for_version",
        "otlp_traces_endpoint",
        "collect_detailed_traces",
        "kv_cache_metrics",
        "kv_cache_metrics_sample",
        "cudagraph_metrics",
        "enable_layerwise_nvtx_tracing",
        "enable_mfu_metrics",
        "enable_mm_processor_stats",
        "enable_logging_iteration_details",
        "jit_monitor_mode",
        "jit_monitor_verbose",
        "timings_per_token",
        "download_dir",
        "port",
        "host",
        "endpoint_metrics",
        "endpoint_props",
        "endpoint_slots",
        "cors_proxy_enabled",
        "ui",
        "ui_settings",
        "log_verbosity",
        "no_webui",
        "offline",
        "build_info",
        "is_sleeping",
        "modalities",
        "model_alias",
        "debug_dump_path",
        "cache_dir",
        "compile_cache_save_format",
        # Placement keys (`n_gpu_layers`, `n_cpu_moe`, `threads`, `mmap`) were
        # listed here until 2026-09-03 under the declaration that WHERE a tensor
        # is computed cannot change WHAT is emitted. Measured 2026-09-02 on
        # srv1 (records/evidence/2026-09-02-srv1-kernel-arms/placement-null.json):
        # `--n-cpu-moe` 0 against 99 on one build changed 9 of 257 verdicts,
        # 3.50pp against the build's own 1.47pp null bound. The declaration was
        # one argument for all four keys and is false for the one measured, so
        # all four are SEMANTIC now (ADR-0041): a placement key is operational
        # only after a placement null on that build has shown it neutral.
    }
)


class UnclassifiedError(RuntimeError):
    """A configuration key belongs to neither set, so no digest was computed.

    Raised rather than defaulted. A new field falling silently to "operational"
    would drop a setting that changes output out of the semantic pin while the
    pin went on looking green — the failure this whole module exists to prevent,
    reintroduced by a default.
    """


def parse_repr(text: str) -> Any:
    """A Python ``repr`` of nested config objects, as nested data.

    Splits only at bracket depth zero and honours quotes, so
    ``StructuredOutputsConfig(backend='auto', ...)`` stays one value instead of
    becoming four phantom keys. Measured on a live config: a naive split on
    commas produced **55 keys where 33 exist**, and gave the wrong value for
    every one of the four nested blocks.
    """
    text = text.strip()
    inner = _constructor_body(text)
    if inner is not None:
        return {"_type": text[: text.index("(")], **_fields(inner)}
    if text.startswith("{") and text.endswith("}"):
        return _fields(text[1:-1], separator=":")
    if text.startswith("[") and text.endswith("]"):
        return [parse_repr(part) for part in _split(text[1:-1])] if text[1:-1] else []
    return _scalar(text)


def _constructor_body(text: str) -> str | None:
    match = re.match(r"[A-Za-z_][A-Za-z0-9_.]*\(", text)
    if not match or not text.endswith(")"):
        return None
    return text[match.end() : -1]


def _fields(body: str, separator: str = "=") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for token in _split(body):
        key, found, value = token.partition(separator)
        if not found:
            continue
        out[key.strip().strip("'\"")] = parse_repr(value)
    return out


def _split(body: str) -> list[str]:
    """``body`` on commas at depth zero, outside quotes."""
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    quote: str | None = None
    for char in body:
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            # Never below zero. Counting `<`/`>` as brackets meant one stray
            # `>` in a repr — `<CompilationMode.NONE: 0>` is already common —
            # drove depth negative, after which NO top-level comma split and
            # every remaining field collapsed into one token. The dropped names
            # never reached the unknown-key check, so the semantic digest
            # silently shrank: the exact failure `UnclassifiedError` exists to
            # make loud.
            depth = max(0, depth - 1)
        if char == "," and depth == 0 and quote is None:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(char)
    out.append("".join(buf))
    return [token.strip() for token in out if token.strip()]


def _scalar(text: str) -> Any:
    if text in ("None", ""):
        return None
    if text in ("True", "False"):
        return text == "True"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text.strip("'\"")


def classify(config: dict[str, Any]) -> dict[str, Any]:
    """Split one config into its semantic and operational halves.

    Raises :exc:`UnclassifiedError` naming every key it does not recognise, so a new
    engine release fails loudly here rather than quietly shrinking the pin.
    """
    unknown = sorted(
        key
        for key in config
        if not key.startswith("_") and key not in SEMANTIC and key not in OPERATIONAL
    )
    if unknown:
        raise UnclassifiedError(
            f"{unknown} belong to neither SEMANTIC nor OPERATIONAL. Decide "
            "whether each changes what the model EMITS — if it does it belongs "
            "in the semantic pin, and if it does not it must be excluded so "
            "that enabling it cannot re-baseline a round. No digest was "
            "computed: a pin that silently drops a field is worse than none."
        )
    return {
        "semantic": {k: v for k, v in config.items() if k in SEMANTIC},
        "operational": {k: v for k, v in config.items() if k in OPERATIONAL},
    }


def fingerprint(config: dict[str, Any]) -> dict[str, Any]:
    """The two digests plus the material each was taken over."""
    split = classify(config)
    digest = contract.observed().identity.digest
    return {
        "serving_semantic_sha256": digest(split["semantic"]),
        "serving_operational_sha256": digest(split["operational"]),
        "semantic": split["semantic"],
        "operational": split["operational"],
        "note": (
            "two digests because one would move when somebody enabled a "
            "counter; the semantic half is the one a guard could key on. "
            "Nothing reads either for comparison (ADR-0027 D7)"
        ),
    }


# --- the RESOLVED configuration (#358) --------------------------------------
#
# **Everything above this line pins what was ASKED FOR.** `serving_config` reads
# `/server_info`, which is the engine restating its own arguments, and the two
# digests are taken over that restatement. Measured 2026-08-24, on the two rigs,
# from one image digest and one identical argument list:
#
#   * `/server_info` differs across the two hosts on FIVE keys, and four of them
#     are consequences of card size (`kv_cache_size_tokens`, `num_gpu_blocks`,
#     `kv_cache_max_concurrency`) or nonces (`instance_id`, and in `vllm_env` a
#     per-launch shared-memory buffer name). The fifth, `quant_config`, differs
#     only in the ITERATION ORDER of a set of layer names — same content, two
#     spellings.
#   * The two servers were nonetheless running different kernels: srv1 resolved
#     `TRITON_ATTN` and the torch sampler, srv2 `FLASH_ATTN` and FlashInfer.
#   * **Neither fact is anywhere in `/server_info`.** It carries
#     `linear_backend='auto'` and `moe_backend='auto'` — the policy word that was
#     asked for — and no attention or sampler key at all.
#
# So a digest over `/server_info` is doubly useless as an identity: it moves for
# three reasons that are not the instrument, and it does not move for the one
# reason that is. That is not a gap to widen the existing digest through. The
# resolved configuration comes from a different place — the engine's startup
# log, where it says which kernel it CHOSE and, when it could not have the one
# it was asked for, why.
#
# The fields below are the ones demonstrated to diverge under identical flags.
# The list is short on purpose: a resolved field earns its place by having been
# seen to differ, not by sounding important.

#: Each resolved field, and where the engine states it. Two sources, because
#: neither alone is enough: the log names the kernels, the config names the
#: numerics, and a field read from the wrong one would be the asked value
#: wearing the resolved value's name.
RESOLVED_READS: dict[str, str] = {
    "attention_backend": "startup log",
    "sampler_path": "startup log",
    "linear_kernel": "startup log",
    "dtype": "engine config",
    "kv_cache_dtype": "engine config",
    "compilation_mode": "engine config",
    "cudagraph_mode": "engine config",
}

#: Where each engine-config field sits, as a dotted path into ``vllm_config``.
#: Read from the nested blocks and not from a flattened view: ``dtype`` appears
#: under three different parents on one live config (``model_config.dtype``,
#: ``model_config.override_attention_dtype``, ``cache_config.mamba_cache_dtype``)
#: and a search by leaf name would return whichever came first.
RESOLVED_PATHS: dict[str, str] = {
    "dtype": "model_config.dtype",
    "kv_cache_dtype": "cache_config.cache_dtype",
    "compilation_mode": "compilation_config.mode",
    "cudagraph_mode": "compilation_config.cudagraph_mode",
}

#: Fields the engine states only as the POLICY it was given, never as the
#: outcome it reached — recorded, digested, and explicitly not evidence that two
#: servers computed alike.
#:
#: ``kv_cache_dtype`` is the whole set. Measured on both rigs 2026-08-24: a run
#: that passes no ``--kv-cache-dtype`` gets ``cache_config.cache_dtype='auto'``
#: on ``/server_info`` and ``kv_cache_dtype=auto`` in the startup log, and the
#: concrete dtype the cache ends up holding is stated on neither surface. So
#: this field refuses two runs that ASKED differently, and cannot tell two runs
#: apart that both asked ``auto`` and resolved it differently. It is in the
#: digest because the first of those is worth refusing; the second is a known
#: hole and is named here rather than left for a reader to discover.
RESOLVED_POLICY_ONLY: frozenset[str] = frozenset({"kv_cache_dtype"})

#: How each log-read field is lifted, as ``(field, pattern, value)`` where
#: ``value`` is either a group index or a literal.
#:
#: **The sampler needed two patterns and that is the whole point.** The 2026-08-24
#: sweep grepped for ``FlashInfer for top`` and matched srv2 only, which read as
#: srv1 having said nothing about its sampler. srv1 says a great deal:
#: ``FlashInfer top-p/top-k sampling unavailable: unsupported compute capability
#: 7.5; falling back.`` The engine names the fallback AND its reason, and a
#: single-shape grep turned a stated fact into an absence. Read both shapes, or
#: do not claim to read the field.
RESOLVED_SIGNATURES: tuple[tuple[str, str, Any], ...] = (
    ("attention_backend", r"Using (\S+) attention backend", 1),
    ("linear_kernel", r"Using (\S*LinearKernel) for", 1),
    ("sampler_path", r"Using FlashInfer for top-p & top-k sampling", "flashinfer"),
    (
        "sampler_path",
        r"FlashInfer top-p/top-k sampling unavailable: (.+?); falling back",
        "torch",
    ),
)

#: What a run can ASK for, per resolved field: the flag or environment variable
#: whose value the engine may or may not honour. ``None`` where a run cannot ask
#: at all — ``linear_kernel`` is chosen by the quantization method and the card,
#: and `--linear-backend` selects a POLICY (`auto`, `machete`, …) rather than
#: naming a kernel, so the two are not in one vocabulary and are never compared.
RESOLVED_ASKED_BY: dict[str, str | None] = {
    "attention_backend": "VLLM_ATTENTION_BACKEND",
    "dtype": "--dtype",
    "kv_cache_dtype": "--kv-cache-dtype",
    "sampler_path": None,
    "linear_kernel": None,
    "compilation_mode": None,
    "cudagraph_mode": None,
}

#: WHY a field is never compared against what was asked — one entry per ``None``
#: above, because "not compared" and "nobody wrote the comparison" are two
#: states and a bare ``None`` says neither.
#:
#: Every one of these is the same defect in a different costume: the request and
#: the outcome are not in one vocabulary, so an equality test between them
#: reports a disagreement whenever the engine does exactly what it was told.
#: ``--enforce-eager`` is the clearest — it is a bare boolean, the mode it
#: produces is the enum member ``0``, and ``True != 0`` would have flagged every
#: correctly-honoured run in the 2026-08-24 sweep.
RESOLVED_NOT_COMPARED: dict[str, str] = {
    "sampler_path": (
        "VLLM_USE_FLASHINFER_SAMPLER is 0/1 and the outcome is a path name; a "
        "run that sets it to 1 on a card that cannot honour it is caught by the "
        "engine's own fallback sentence, which is recorded on the field"
    ),
    "linear_kernel": (
        "--linear-backend selects a policy (auto, machete, …) and the outcome "
        "is a kernel class; the quantization method and the card choose it"
    ),
    "compilation_mode": (
        "--enforce-eager is a bare boolean and the outcome is an enum member, "
        "so True would never equal 0 on a run that honoured it exactly"
    ),
    "cudagraph_mode": (
        "no flag names it directly; it follows from --enforce-eager and from "
        "-cc.cudagraph_mode, which nothing in this repository dispatches"
    ),
}

#: Asked values that name a policy rather than an outcome. Comparing one of
#: these against a resolved value would manufacture a disagreement out of the
#: engine doing exactly what it was told.
RESOLVED_POLICY_WORDS: frozenset[str] = frozenset({"auto", "none", ""})

#: Spelling differences that are not differences. ``--dtype float16`` is honoured
#: by an engine that then reports ``torch.float16``; the prefix is the library's
#: and not the run's.
RESOLVED_PREFIXES: tuple[str, ...] = ("torch.",)


def resolved_from_log(lines: Iterable[str]) -> dict[str, dict[str, Any]]:
    """The kernel choices, lifted from the engine's own startup lines.

    Returns ``{field: {"value", "line"}}`` for every field the log states, and
    omits the ones it does not — an absent field is the caller's problem to
    record, not this function's to invent a default for.

    The verbatim line is kept beside every value for the reason #357 landed:
    when the engine explains itself, the explanation is the record, and a
    paraphrase of it is prose.
    """
    found: dict[str, dict[str, Any]] = {}
    for raw in lines:
        # `(EngineCore pid=120) INFO 08-24 08:34:49 [cuda.py:482] …` — the
        # prefix carries a pid and a timestamp, which are per-launch noise and
        # would put a nonce in anything derived from the line.
        line = raw.split("] ", 1)[-1].strip() if "] " in raw else raw.strip()
        for field, pattern, value in RESOLVED_SIGNATURES:
            if field in found:
                continue
            match = re.search(pattern, line)
            if match:
                found[field] = {
                    "value": value if isinstance(value, str) else match.group(value),
                    "line": line,
                }
    return found


def resolved_from_config(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The numerics, lifted from the engine's restated config.

    These ARE resolved on that surface even though the kernels are not — with
    the one exception :data:`RESOLVED_POLICY_ONLY` names. ``dtype`` arrives as
    ``torch.float16`` on a run that asked for nothing, so the engine has decided
    and said so; ``compilation_mode`` and ``cudagraph_mode`` arrive as integers,
    which are the resolved form of ``--enforce-eager``.

    Accepts either shape ``/server_info`` answers in: the nested object
    ``?config_format=json`` returns, and the flattened parse of the Python repr
    the bare endpoint returns. A dotted path is tried whole first, then its leaf
    — so the same reader serves both without a caller having to say which it
    holds.
    """
    out: dict[str, dict[str, Any]] = {}
    for field, path in RESOLVED_PATHS.items():
        value, where = _at_path(config, path)
        if value is not None:
            out[field] = {"value": str(value), "line": f"{where}={value}"}
    return out


def _at_path(config: Mapping[str, Any], path: str) -> tuple[Any, str]:
    """``path`` through nested mappings, falling back to its leaf name."""
    node: Any = config
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            leaf = path.rsplit(".", 1)[-1]
            return (config.get(leaf) if isinstance(config, Mapping) else None), leaf
        node = node[part]
    return node, path


def resolved(
    *,
    log_lines: Iterable[str],
    config: Mapping[str, Any],
    asked: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The resolved serving configuration, its digest, and what it contradicts.

    **The digest is computed only when every declared field was read.** A field
    the engine did not state leaves ``serving_resolved_sha256`` null with a
    reason naming it, so :func:`identity.require_comparable` refuses the row on
    absence rather than matching it against another row that also could not say.
    Two silences are not an agreement — the defect ADR-0027 D3 exists for, one
    level in: a digest taken over ``{"attention_backend": null}`` twice compares
    equal while the two servers run different kernels.

    ``asked`` maps flag or environment names to what this run requested, and is
    compared against what the engine resolved wherever the two are in the same
    vocabulary. A disagreement is RECORDED, never repaired: a run that asked for
    ``FLASHINFER`` and got ``TRITON_ATTN`` measured the second one, and the fact
    that it wanted the first is a fact about reach (ADR-0027 D2's shape — the
    value, plus the reason it is not what was asked).
    """
    asked = dict(asked or {})
    readings = {**resolved_from_log(log_lines), **resolved_from_config(config)}

    fields: dict[str, Any] = {}
    disagreements: list[dict[str, Any]] = []
    unread: list[str] = []
    for field, read in RESOLVED_READS.items():
        reading = readings.get(field)
        if reading is None:
            unread.append(field)
            fields[field] = {
                "value": None,
                "read": read,
                "refused": f"the {read} stated no {field}",
            }
            continue
        entry: dict[str, Any] = {
            "value": reading["value"],
            "read": read,
            "line": reading["line"],
            # Stated, per field, so a reader never has to know which of the two
            # a name happens to be. A `True` here is the engine reporting an
            # outcome; a `False` is it echoing the policy it was handed.
            "resolved_by_engine": field not in RESOLVED_POLICY_ONLY,
        }
        if field in RESOLVED_POLICY_ONLY:
            entry["limit"] = (
                f"the engine restates {field} as the policy it was given and "
                "never as the outcome it reached, so this refuses two runs that "
                "asked differently and cannot separate two that both asked "
                "'auto' and resolved it differently"
            )
        name = RESOLVED_ASKED_BY.get(field)
        wanted = asked.get(name) if name else None
        entry["asked_by"] = name
        entry["asked"] = wanted
        entry["agrees"] = _agrees(wanted, reading["value"])
        if name is None:
            entry["not_compared"] = RESOLVED_NOT_COMPARED[field]
        if entry["agrees"] is False:
            disagreements.append(
                {
                    "field": field,
                    "asked": wanted,
                    "resolved": reading["value"],
                    "asked_by": name,
                    "reason": reading["line"],
                }
            )
        fields[field] = entry

    digest = contract.observed().identity.digest
    material = {field: fields[field]["value"] for field in RESOLVED_READS}
    return {
        "serving_resolved_sha256": None if unread else digest(material),
        "refused": (
            None
            if not unread
            else (
                f"{sorted(unread)} could not be read, so no digest was computed. "
                "A digest over a null is a value two servers can share while "
                "running different kernels, which is the agreement-by-absence "
                "this field exists to refuse (ADR-0027 D3)."
            )
        ),
        "resolved": fields,
        "disagreements": disagreements,
        "material": material,
    }


def _agrees(asked: Any, got: Any) -> bool | None:
    """Whether a request and an outcome are the same choice.

    ``None`` — not comparable — rather than ``True`` when nothing was asked or
    the request was a policy word. An unasked field cannot be disappointed, and
    recording it as agreement would let ``auto`` vouch for whatever it produced.
    """
    if asked is None:
        return None
    text = str(asked).strip()
    if text.lower() in RESOLVED_POLICY_WORDS:
        return None
    return _bare(text) == _bare(str(got))


def _bare(text: str) -> str:
    """``text`` without a library prefix that is not part of the choice."""
    text = text.strip().strip("'\"")
    for prefix in RESOLVED_PREFIXES:
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
    return text.upper()
