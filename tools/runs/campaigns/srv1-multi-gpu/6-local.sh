#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/6-local.sh — step 6: vLLM across
# both cards on a checkpoint that lives under ~/models rather than the HF
# cache, and that no single card holds.
#
# Step 3's size axis tops out at what srv1's HF cache carries (7B AWQ);
# 14B/32B AWQ are not on the rig. nemotron-30b-awq (~17 GiB, nemotron_h,
# compressed-tensors) is, under ~/models/moe. No single card holds it, so
# there is no g0/g1/dp2 cell: tp2 against pp2 is the comparison two 12 GiB
# cards exist for.
#
# The driver reads a `/models/...` vLLM model as ~/models/... on the rig,
# mounted read-only (tools/runs/drivers/mgpu_sweep.py). The checkpoint ships
# its own configuration code, hence --trust-remote-code.
#
# WHAT THIS CHECKPOINT REFUSES, read off vLLM v0.26.0 on 2x RTX 3060:
#   plain tp2   its MoE intermediate size split two ways (928) is not a
#               multiple of the quant group (64), so the tp2 cells carry
#               --enable-expert-parallel: the experts are placed whole, one
#               set per card, and only attention and the Mamba mixers are
#               tensor-parallel
#   32 seqs     pp2 builds 25 Mamba state blocks at 0.88 utilisation and each
#               decode stream needs one, so the rungs stop at 16
#
# RUN_ARTIFACTS: vllm-local.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/6-local.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "6-local.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/6-local.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

IMG="vllm/vllm-openai:v0.26.0"
DRIVER="tools/runs/drivers/mgpu_sweep.py"
WORKLOAD="tools/runs/workload.py"
CTX=2048
LEVELS="1,4,16"
MODEL=/models/moe/nemotron-30b-awq
BASE="--trust-remote-code"
LAYOUTS=(tp2:on tp2:off pp2:on pp2:off)

mgpu_preamble vllm-local.tsv
DIGEST=$(image_digest "$IMG") || { _fail "$IMG resolves to no digest on $RUN_HOST" || true; exit 1; }
export VLLM_IMG="$DIGEST"
trap '"$DOCKER" rm -f "$RUN_ID-mgpu-a" "$RUN_ID-mgpu-b" >/dev/null 2>&1 || true' EXIT

open_tsv workload_stamp "$WORKLOAD"

cells=()
for lp in "${LAYOUTS[@]}"; do
    layout=${lp%%:*}
    p2p=${lp#*:}
    extra=$BASE
    [ "$layout" = tp2 ] && extra+="+--enable-expert-parallel"
    cells+=("vn30-$layout-$p2p:$MODEL:$layout:$p2p:$CTX:$LEVELS:$extra")
done
say "$MODEL: ${#cells[@]} cells"
emit rig_stamp
emit _py "$DRIVER" vllm "${cells[@]}"

close_tsv
say "wrote $OUT"
