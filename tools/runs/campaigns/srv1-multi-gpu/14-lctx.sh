#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/14-lctx.sh — step 14: llama.cpp at long
# windows, one stream (-np 1, so -c is the window), PREFILL at ~90% of it up
# to 32k tokens.
#
#   14B       g0 / layer / tensor at 16k and 32k. At 32k the q8_0 KV is ~3.3 GiB
#             and one card has ~2.3 GiB left after weights: g0 predicted
#             REFUSED, the split fits. The case where the window alone forces
#             the second card
#   32B       layer / tensor at 8k, 16k, 24k: ~2.8 GiB left after weights, so
#             ~16k is predicted to be the ceiling
#   a3b/nemo  layer at 128k: 10 of 40 layers hold full attention (Qwen3.6) and
#             nemotron is mostly Mamba, so both are predicted to fit
#
# RUN_ARTIFACTS: lctx.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/14-lctx.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "14-lctx.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/14-lctx.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

D=/models/dense
X=/models/moe
cells=()
for w in "16384=27300" "32768=54600"; do
    ctx=${w%%=*}; chars=${w#*=}
    for layout in g0 layer tensor; do
        cells+=("x14-$layout-$ctx:$D/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf:$layout:built:$ctx:1:@prefill=$chars")
    done
done
for w in "8192=13600" "16384=27300" "24576=40900"; do
    ctx=${w%%=*}; chars=${w#*=}
    for layout in layer tensor; do
        cells+=("x32-$layout-$ctx:$D/Qwen2.5-Coder-32B-Instruct-Q4_K_M.gguf:$layout:built:$ctx:1:@prefill=$chars")
    done
done
cells+=(
    "xa3b-layer-131072:$X/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf:layer:built:131072:1:@prefill=54600"
    "xnemo-layer-131072:$X/nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf:layer:built:131072:1:@prefill=54600"
)
mgpu_serve lctx.tsv lcp "${cells[@]}"
