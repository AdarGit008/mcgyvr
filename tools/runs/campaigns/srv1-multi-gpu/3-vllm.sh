#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/3-vllm.sh — step 3: vLLM across both
# cards, every way vLLM offers, on one AWQ family at four sizes.
#
# THE GRID (tools/runs/drivers/mgpu_sweep.py runs each cell):
#
#   model   Qwen2.5-Coder-{1.5B,7B,14B,32B}-Instruct-AWQ
#           1.5B: communication dominates, the worst case for TP
#           7B / 14B: fit one card; the question is whether TP beats ONE card
#           32B: fits only across both; the question is TP against PP
#   layout  g0, g1         one card each, the baselines
#           tp2 p2p=on     NCCL's choice of transport, custom all-reduce allowed
#           tp2 p2p=off    NCCL_P2P_DISABLE=1 --disable-custom-all-reduce
#           pp2 p2p=on/off the layer split, whose traffic is point-to-point
#           dp2            two independent replicas: throughput without any
#                          model parallelism, the thing TP has to beat at n>1
#   levels  1, 4, 16, 32   dropped past the pool by the driver, and said so
#   ctx     2048           clears the workload's worst prompt+reply (1347)
#
# MIXED CARDS. vLLM picks an AWQ kernel from the capability of the card it
# starts on; Marlin needs 8.0, and a Turing card (7.5) cannot run it. When the
# two cards report different compute capabilities every cell gets
# `--quantization awq`, so one kernel runs on both ranks and the g/tp/pp cells
# compare like with like; the card that can run Marlin gets one more cell
# (`nat`, no override) so the price of that is on file too. Equal cards get
# no override: vLLM's own choice is the measurement.
#
# Estimated wall time: ~26 launches x 2-4 min, 1.5-2 h. Cells predicted not to
# fit are SKIP rows and cost nothing.
#
# RUN_ARTIFACTS: vllm.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/3-vllm.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "3-vllm.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/3-vllm.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

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
LEVELS="1,4,16,32"
MODELS=(
    "1.5b=Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ"
    "7b=Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
    "14b=Qwen/Qwen2.5-Coder-14B-Instruct-AWQ"
    "32b=Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
)
LAYOUTS=(g0:on g1:on tp2:on tp2:off pp2:on pp2:off dp2:on)

mgpu_preamble vllm.tsv
DIGEST=$(image_digest "$IMG") || { _fail "$IMG resolves to no digest on $RUN_HOST" || true; exit 1; }
export VLLM_IMG="$DIGEST"
trap '"$DOCKER" rm -f "$RUN_ID-mgpu-a" "$RUN_ID-mgpu-b" >/dev/null 2>&1 || true' EXIT

read -r CC0 CC1 <<<"$(card_ccs)"
QUANT=""
NATIVE=()
if [ "$CC0" != "$CC1" ]; then
    QUANT="--quantization+awq"
    awk -v c="$CC0" 'BEGIN { exit !(c >= 8.0) }' && NATIVE+=(g0)
    awk -v c="$CC1" 'BEGIN { exit !(c >= 8.0) }' && NATIVE+=(g1)
fi

open_tsv workload_stamp "$WORKLOAD"
emit stamp NOTE "cards_cc=$CC0,$CC1" "quant_override=${QUANT:-none}"

for entry in "${MODELS[@]}"; do
    size=${entry%%=*}
    model=${entry#*=}
    cells=()
    for lp in "${LAYOUTS[@]}"; do
        layout=${lp%%:*}
        p2p=${lp#*:}
        cells+=("v$size-$layout-$p2p:$model:$layout:$p2p:$CTX:$LEVELS${QUANT:+:$QUANT}")
    done
    for layout in "${NATIVE[@]}"; do
        cells+=("v$size-$layout-nat:$model:$layout:on:$CTX:$LEVELS")
    done
    say "$model: ${#cells[@]} cells"
    emit rig_stamp
    emit _py "$DRIVER" vllm "${cells[@]}"
done

close_tsv
say "wrote $OUT"
