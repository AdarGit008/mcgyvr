#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/13-vctx.sh — step 13: vLLM 7B AWQ at
# 8k and 32k windows (2k is step 3), with a PREFILL prompt of ~90% of the
# window (@prefill, ~0.54 tokens a character).
#
#   what it isolates
#   prefill   a prompt's all-reduces grow with its length (8k tokens x 3584 x
#             2 B = 58 MB each, 56 of them): tp2's prefill edge over one card
#             should shrink with length, and pp2 should hold up
#   pool      kv_tok and maxconc per window: how much of the second card a long
#             window eats
#
# RUN_ARTIFACTS: vctx.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/13-vctx.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "13-vctx.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/13-vctx.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

M="Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
cells=()
for w in "8192=13600" "32768=54600"; do
    ctx=${w%%=*}; chars=${w#*=}
    for layout in g0 tp2 pp2; do
        cells+=("c7-$layout-$ctx:$M:$layout:on:$ctx:1,4:@prefill=$chars")
    done
done
mgpu_serve vctx.tsv vllm "${cells[@]}"
