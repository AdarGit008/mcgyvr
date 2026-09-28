#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/4-lcp.sh — step 4: llama-server across
# both cards, served and measured the way step 3 measures vLLM.
#
# THE GRID (tools/runs/drivers/mgpu_sweep.py runs each cell):
#
#   model   dense  Qwen2.5-Coder-7B IQ4_XS, 14B Q4_K_M, 32B Q4_K_M
#           MoE    Qwen3.6-35B-A3B UD-IQ3_XXS, Qwen3-Coder-30B-A3B UD-IQ3_XXS
#                  — both are served today with experts in host RAM
#                  (fleet.yaml); split over two cards they may fit whole
#   layout  g0, g1   one card each
#           layer    --split-mode layer, llama.cpp's pipeline split, weighted
#                    by free memory (its default --tensor-split)
#           row      --split-mode row; b10644's CUDA backend refuses it ("does
#                    not support split buffers"), and the refusal is filed
#           tensor   --split-mode tensor, llama.cpp's tensor-parallel split
#                    (EXPERIMENTAL in b10644)
#           dp2      two single-card replicas
#   p2p     built: llama.cpp takes no runtime switch this campaign trusts, so
#           peer access is whatever the build and driver give (link.tsv says
#           which)
#   levels  1, 4, 8, 16 (32B: 1, 4, so its q8_0 cache fits beside 19 GiB)
#   ctx     2048 a slot; -c = slots x 2048
#
# The image is hosts.json[srv1].llamacpp_image (CUDA archs 61 and 80: the
# Turing card runs without tensor-core emulation, an Ampere card runs the 80
# kernels), resolved to its digest once.
#
# A single card running a MoE with --n-cpu-moe is NOT a cell here: the fit
# check counts whole weights, and those placements are already on file under
# the live fleet's own records.
#
# Estimated wall time: ~20 launches x 2-4 min, about 1 h.
#
# RUN_ARTIFACTS: lcp.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/4-lcp.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "4-lcp.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/4-lcp.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

DRIVER="tools/runs/drivers/mgpu_sweep.py"
WORKLOAD="tools/runs/workload.py"
CTX=2048
MODELS=(
    "7b=/models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf=1,4,8,16"
    "14b=/models/dense/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf=1,4,8,16"
    "32b=/models/dense/Qwen2.5-Coder-32B-Instruct-Q4_K_M.gguf=1,4"
    "a3b=/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf=1,4,8,16"
    "c30=/models/moe/Qwen3-Coder-30B-A3B-Instruct-UD-IQ3_XXS.gguf=1,4,8,16"
)
LAYOUTS=(g0 g1 layer row tensor dp2)

mgpu_preamble lcp.tsv
IMG=$(_py -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]["llamacpp_image"])' \
    "$RUN_ROOT/tools/runs/hosts.json" "$RUN_HOST") || { _fail "hosts.json names no llamacpp_image for $RUN_HOST" || true; exit 2; }
DIGEST=$(image_digest "$IMG") || { _fail "$IMG resolves to no digest on $RUN_HOST" || true; exit 1; }
export LCP_IMG="$DIGEST"
trap '"$DOCKER" rm -f "$RUN_ID-mgpu-a" "$RUN_ID-mgpu-b" >/dev/null 2>&1 || true' EXIT

open_tsv workload_stamp "$WORKLOAD"
emit stamp NOTE "image=$IMG"

for entry in "${MODELS[@]}"; do
    IFS='=' read -r size model levels <<<"$entry"
    cells=()
    for layout in "${LAYOUTS[@]}"; do
        cells+=("l$size-$layout:$model:$layout:built:$CTX:$levels")
    done
    say "$model: ${#cells[@]} cells"
    emit rig_stamp
    emit _py "$DRIVER" lcp "${cells[@]}"
done

close_tsv
say "wrote $OUT"
