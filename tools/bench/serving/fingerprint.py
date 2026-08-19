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
