#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/12-vladder.sh — step 12: vLLM's model
# axis: the 3B rung of the AWQ size ladder, and expert-parallel against tensor-
# parallel on the two MoE checkpoints in the HF cache.
#
#   3B        fills 1.5B / 3B / 7B (step 3 holds 1.5B and 7B at the same levels)
#   qmoe      Qwen1.5-MoE-A2.7B GPTQ-Int4: 60 experts, top 4, expert FFN 1408
#   dsl       DeepSeek-V2-Lite AWQ: 64 experts, top 6, MLA attention
#             Each: one card, tp2, tp2 with --enable-expert-parallel (experts
#             placed whole, one set a card: the MoE all-reduce becomes an all-
#             to-all), pp2, and two replicas. 1408 split two ways is 704, not a
#             multiple of 128, so plain tp2 may be refused like nemotron's 928;
#             that refusal is a result.
#
# RUN_ARTIFACTS: vladder.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/12-vladder.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "12-vladder.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/12-vladder.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

L="2048:1,4,16,32"
M3="Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
QM="Qwen/Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4"
DS="TechxGenus/DeepSeek-V2-Lite-Chat-AWQ"
cells=(
    "v3b-g0:$M3:g0:on:$L"
    "v3b-tp2:$M3:tp2:on:$L"
    "v3b-pp2:$M3:pp2:on:$L"
    "v3b-dp2:$M3:dp2:on:$L"
)
for m in "qmoe=$QM=" "dsl=$DS=+--trust-remote-code"; do
    IFS='=' read -r tag path base <<<"$m"
    cells+=(
        "$tag-g0:$path:g0:on:2048:1,4,16:$base"
        "$tag-tp2:$path:tp2:on:2048:1,4,16:$base"
        "$tag-tp2ep:$path:tp2:on:2048:1,4,16:$base+--enable-expert-parallel"
        "$tag-pp2:$path:pp2:on:2048:1,4,16:$base"
        "$tag-dp2:$path:dp2:on:2048:1,4,16:$base"
    )
done
mgpu_serve vladder.tsv vllm "${cells[@]}"
