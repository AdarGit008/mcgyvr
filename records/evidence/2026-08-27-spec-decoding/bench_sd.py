#!/usr/bin/env python3
"""
BYOB speculative-decoding harness for vLLM 0.26.0 (offline, no server).

Measures:
  - target ALONE (baseline) throughput
  - target + DRAFT (speculative decoding) throughput + acceptance metrics

Run once per (target, draft, num_spec, temp) via docker (vllm/vllm-openai:v0.26.0).
Output is a single-line JSON summary for easy comparison/recording.

Usage (inside the vllm container):
  python3 /harness/bench_sd.py --target <hf-id> [--draft <hf-id>] [options]

Grounding: vLLM official offline example
  examples/features/speculative_decoding/spec_decode_offline.py
  (template + metric names pulled from there; dataset/sampling simplified).
"""

import argparse
import json
import time

from vllm import LLM, SamplingParams


# Short, distinct code prompts -> decode-dominated (SD helps decode, not prefill),
# so the spec-decode speedup is visible. Greedy (temp=0) gives max acceptance rate.
def make_prompts(n: int) -> list[list[dict]]:
    tasks = [
        "fibonacci", "quicksort", "binary_search", "json_parse", "levenshtein",
        "lru_cache", "regex_match", "topo_sort", "dijkstra", "mergesort",
        "stack_balanced", "hex_decode", "csv_escape", "url_encode", "sha_check",
        "matrix_mul", "trie_insert", "heap_push", "prime_sieve", "bubble_sort",
        "graph_bfs", "union_find", "tokenizer", "retry_backoff", "rate_limiter",
        "base64_decode", "string_perm", "linked_list", "bst_insert", "run_len",
    ]
    prompts = []
    for i in range(n):
        name = tasks[i % len(tasks)]
        body = (
            f"Write a clean, correct Python implementation of `{name}` that solves "
            f"the described problem, with a docstring, input validation, and edge cases."
        )
        prompts.append([{"role": "user", "content": body}])
    return prompts


def build_spec_config(args):
    if args.draft is None:
        return None
    cfg = {
        "method": args.method,
        "model": args.draft,
        "num_speculative_tokens": args.num_spec,
        "enforce_eager": args.enforce_eager,
        "max_model_len": args.max_model_len,
    }
    if args.method == "draft_model":
        cfg["parallel_drafting"] = args.parallel_drafting
        cfg["use_heterogeneous_vocab"] = args.use_heterogeneous_vocab
    return cfg


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True, help="HF repo id of the TARGET big model")
    p.add_argument("--draft", default=None, help="HF repo id of the DRAFT small model (omit for baseline)")
    p.add_argument("--method", default="draft_model", choices=["draft_model", "ngram"])
    p.add_argument("--num-spec", type=int, default=4, help="num_speculative_tokens")
    p.add_argument("--max-model-len", type=int, default=8192)
    p.add_argument("--gpu-mem", type=float, default=0.90, help="gpu_memory_utilization")
    p.add_argument("--max-num-seqs", type=int, default=8)
    p.add_argument("--max-tokens", type=int, default=256, help="output tokens per prompt")
    p.add_argument("--num-prompts", type=int, default=30)
    p.add_argument("--temp", type=float, default=0.0)
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--enforce-eager", action="store_true")
    p.add_argument("--parallel-drafting", action="store_true")
    p.add_argument("--use-heterogeneous-vocab", action="store_true")
    args = p.parse_args()

    spec_cfg = build_spec_config(args)

    llm = LLM(
        model=args.target,
        trust_remote_code=True,
        tensor_parallel_size=1,
        gpu_memory_utilization=args.gpu_mem,
        max_model_len=args.max_model_len,
        max_num_seqs=args.max_num_seqs,
        enforce_eager=args.enforce_eager,
        speculative_config=spec_cfg,
        disable_log_stats=False,
    )

    prompts = make_prompts(args.num_prompts)
    sp = SamplingParams(temperature=args.temp, top_p=args.top_p, max_tokens=args.max_tokens)

    # warmup (also loads weights/compiles)
    _ = llm.chat(prompts[:2], sampling_params=sp)

    start = time.time()
    outputs = llm.chat(prompts, sampling_params=sp)
    elapsed = time.time() - start

    total_out = sum(len(o.outputs[0].token_ids) for o in outputs)

    result = {
        "target": args.target,
        "draft": args.draft,
        "method": "auto" if spec_cfg is None else args.method,
        "num_spec": args.num_spec,
        "temp": args.temp,
        "enforce_eager": args.enforce_eager,
        "num_prompts": args.num_prompts,
        "max_tokens": args.max_tokens,
        "total_output_tokens": total_out,
        "elapsed_s": round(elapsed, 3),
        "tokens_per_sec": round(total_out / elapsed, 2) if elapsed > 0 else 0.0,
    }

    if spec_cfg is not None:
        num_drafts = num_draft_tokens = num_accepted = 0
        acceptance_counts = [0] * args.num_spec
        for m in llm.get_metrics():
            name = getattr(m, "name", "")
            if name == "vllm:spec_decode_num_drafts":
                num_drafts += m.value
            elif name == "vllm:spec_decode_num_draft_tokens":
                num_draft_tokens += m.value
            elif name == "vllm:spec_decode_num_accepted_tokens":
                num_accepted += m.value
            elif name == "vllm:spec_decode_num_accepted_tokens_per_pos":
                for pos in range(len(m.values)):
                    acceptance_counts[pos] += m.values[pos]
        mean_acceptance_length = 1 + (num_accepted / num_drafts) if num_drafts > 0 else 1.0
        per_pos = {}
        for i in range(len(acceptance_counts)):
            per_pos[f"pos_{i}"] = round(acceptance_counts[i] / num_drafts, 3) if num_drafts > 0 else 0.0
        result["num_drafts"] = num_drafts
        result["num_draft_tokens"] = num_draft_tokens
        result["num_accepted_tokens"] = num_accepted
        result["mean_acceptance_length"] = round(mean_acceptance_length, 3)
        result["per_pos_acceptance"] = per_pos

    print("RESULT_JSON=" + json.dumps(result))


if __name__ == "__main__":
    main()
