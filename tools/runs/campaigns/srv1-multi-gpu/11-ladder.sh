#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/11-ladder.sh — step 11: what the model's
# shape does to the two-card gain, on llama.cpp, one variable per rung.
#
#   size ladder   Coder 1.5B / 3B, Qwen3 4B / 8B, OCR-Nemotron 7B (qwen2, the
#                 7B's shape), one card against tensor split; 14B and 32B come
#                 from step 4. Qwen3-4B and -8B share 36 layers, so the link's
#                 cost is fixed and only the compute half moves. Predicted from
#                 step 4's fit (tp = g0/2 + 2L x 0.033 ms): 1.1x at 1.5B up to
#                 1.77x at 32B
#   MoE quants    one shape (qwen35moe: 40 layers, h 2048, 256 experts, top 8)
#                 at IQ2_M, IQ3_XXS (Qwen3.6-35B-A3B), Q3_K_M and Q4_K_M
#                 (KAT-Coder-V2.5), and Coder-30B at Q2_K and Q4_K_M. If MoE
#                 decode is launch/sync bound, tpot moves <=10% while the bytes
#                 read nearly double; a dense model moves with its bytes
#   dense vs MoE  at equal bytes: DeepSeek-Coder-V2 16B (MLA, 64 experts top 6)
#                 against the 14B; Ling-3.0-tiny against Qwen3-8B
#
# One-card cells of files within ~1 GiB of a card carry @headroom=512 (the
# default 1024 predicts they do not fit; the engine's refusal decides).
#
# RUN_ARTIFACTS: ladder.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/11-ladder.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "11-ladder.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/11-ladder.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

D=/models/dense
X=/models/moe
L="built:2048:1,4,16"
cells=()
for m in "s1.5=$D/Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf" \
         "s3=$D/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf" \
         "q4b=$D/Qwen3-4B-Q4_K_M.gguf" \
         "ocr7=$D/nvidia_OpenCodeReasoning-Nemotron-7B-Q4_K_M.gguf" \
         "q8b=$D/Qwen3-8B-Q4_K_M.gguf" \
         "ds16=$X/deepseek-coder-v2-16b.gguf" \
         "ling=$X/Ling-3.0-tiny-Q4_K_M.gguf"; do
    tag=${m%%=*}; path=${m#*=}
    cells+=("$tag-g0:$path:g0:$L" "$tag-tensor:$path:tensor:$L")
done
C30Q2=/hf/hub/models--unsloth--Qwen3-Coder-30B-A3B-Instruct-GGUF/snapshots/b17cb02dd882d5b6ab62fc777ad2995f19668350/Qwen3-Coder-30B-A3B-Instruct-Q2_K.gguf
cells+=(
    "a3bq2-g0:$X/Qwen3.6-35B-A3B-UD-IQ2_M.gguf:g0:$L:@headroom=512"
    "a3bq2-layer:$X/Qwen3.6-35B-A3B-UD-IQ2_M.gguf:layer:$L"
    "a3bq2-tensor:$X/Qwen3.6-35B-A3B-UD-IQ2_M.gguf:tensor:$L"
    "a3bq3-layer:$X/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf:layer:$L"
    "a3bq3-tensor:$X/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf:tensor:$L"
    "katq3-layer:$X/KAT-Coder-V2.5-Dev_Q3_K_M_imatrix_MTP.gguf:layer:$L"
    "katq3-tensor:$X/KAT-Coder-V2.5-Dev_Q3_K_M_imatrix_MTP.gguf:tensor:$L"
    "katq4-layer:$X/KAT-Coder-V2.5-Dev.Q4_K_M.gguf:layer:$L"
    "katq4-tensor:$X/KAT-Coder-V2.5-Dev.Q4_K_M.gguf:tensor:$L"
    "c30q4-layer:$X/qwen3-coder-30b.gguf:layer:$L"
    "c30q4-tensor:$X/qwen3-coder-30b.gguf:tensor:$L"
    "c30q2-g0:$C30Q2:g0:$L:@headroom=512"
    "c30q2-layer:$C30Q2:layer:$L"
    "c30q2-tensor:$C30Q2:tensor:$L"
)
mgpu_serve ladder.tsv lcp "${cells[@]}"
