#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/15-vsched.sh — step 15: vLLM's scheduler
# and memory settings on the 7B AWQ split, and n-gram speculative decoding.
#
#   mnbt      --max-num-batched-tokens 512 / 8192 (default 2048): how much
#             prefill a decode step carries, TTFT against decode smoothness
#   fp8 KV    --kv-cache-dtype fp8: Ampere has no fp8 math, so it is a storage
#             format; a bigger pool, a slower read
#   gmu       --gpu-memory-utilization 0.80 / 0.94 (driver default 0.88)
#   ngram     --speculative-config ngram, 4 tokens, on the real workload levels
#             (not @knob: forced-length replies would flatter prompt lookup);
#             one card and tp2, n=1 and 4
#
# Scheduler/memory cells are @knob at n=16 and 32.
#
# RUN_ARTIFACTS: vsched.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/15-vsched.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "15-vsched.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/15-vsched.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

M="Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
K="2048:16,32:@knob"
SPEC="--speculative-config+'{\"method\":\"ngram\",\"num_speculative_tokens\":4,\"prompt_lookup_max\":4}'"
cells=(
    "s7-tp2:$M:tp2:on:$K"
    "s7-tp2-mnbt512:$M:tp2:on:$K+--max-num-batched-tokens+512"
    "s7-tp2-mnbt8192:$M:tp2:on:$K+--max-num-batched-tokens+8192"
    "s7-tp2-fp8kv:$M:tp2:on:$K+--kv-cache-dtype+fp8"
    "s7-tp2-gmu80:$M:tp2:on:$K+--gpu-memory-utilization+0.80"
    "s7-tp2-gmu94:$M:tp2:on:$K+--gpu-memory-utilization+0.94"
    "n7-g0:$M:g0:on:2048:1,4"
    "n7-g0-ngram:$M:g0:on:2048:1,4:$SPEC"
    "n7-tp2:$M:tp2:on:2048:1,4"
    "n7-tp2-ngram:$M:tp2:on:2048:1,4:$SPEC"
)
mgpu_serve vsched.tsv vllm "${cells[@]}"
