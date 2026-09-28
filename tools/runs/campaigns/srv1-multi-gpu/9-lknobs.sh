#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/9-lknobs.sh — step 9: llama.cpp's own
# settings on the 14B Q4_K_M split, each against the same cell without it.
#
# Every cell is @knob (see 8-vknobs.sh). The baseline is the driver's: -fa on,
# KV q8_0, ubatch 512, the backend's thread count, both cards.
#
#   what it isolates
#   KV f16/q4   the KV type: yesterday tensor split fell off under concurrency
#               (7B n=4 30.9 against layer 40.4); q8_0 flash-attention batched
#               kernels are one suspect
#   ar-*        tensor split's all-reduce (GGML_CUDA_ALLREDUCE): nccl (the Linux
#               default, when built with it), internal (one kernel staging
#               through pinned host memory, busy-waiting on a host flag), none
#               (the generic butterfly); and the copy-engine cut-over
#               (GGML_CUDA_AR_COPY_THRESHOLD, default 1 MiB)
#   nograph     CUDA graphs off (GGML_CUDA_DISABLE_GRAPHS): launch cost; tensor
#               split syncs more than layer split
#   ub          the physical batch: prefill and batched decode
#   t2 / 4cpu   CPU threads and cores given to the server
#   nofa        flash attention off
#   7B pair     the same KV and all-reduce question on a model where the link
#               is a bigger share of the token
#
# RUN_ARTIFACTS: lknobs.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/9-lknobs.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "9-lknobs.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/9-lknobs.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

M14="/models/dense/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf"
M7="/models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf"
L="built:2048:1,4,8"
cells=(
    "kl14-g0:$M14:g0:$L:@knob"
    "kl14-layer:$M14:layer:$L:@knob"
    "kl14-tensor:$M14:tensor:$L:@knob"
    "kl14-layer-f16:$M14:layer:$L:@knob+-ctk+f16+-ctv+f16"
    "kl14-tensor-f16:$M14:tensor:$L:@knob+-ctk+f16+-ctv+f16"
    "kl14-tensor-q4:$M14:tensor:$L:@knob+-ctk+q4_0+-ctv+q4_0"
    "kl14-tensor-ar-nccl:$M14:tensor:$L:@knob+@GGML_CUDA_ALLREDUCE=nccl"
    "kl14-tensor-ar-internal:$M14:tensor:$L:@knob+@GGML_CUDA_ALLREDUCE=internal"
    "kl14-tensor-ar-none:$M14:tensor:$L:@knob+@GGML_CUDA_ALLREDUCE=none"
    "kl14-tensor-arcopy256k:$M14:tensor:$L:@knob+@GGML_CUDA_AR_COPY_THRESHOLD=262144"
    "kl14-tensor-arcopy8m:$M14:tensor:$L:@knob+@GGML_CUDA_AR_COPY_THRESHOLD=8388608"
    "kl14-tensor-nograph:$M14:tensor:$L:@knob+@GGML_CUDA_DISABLE_GRAPHS=1"
    "kl14-layer-nograph:$M14:layer:$L:@knob+@GGML_CUDA_DISABLE_GRAPHS=1"
    "kl14-tensor-ub128:$M14:tensor:$L:@knob+-ub+128"
    "kl14-tensor-ub1024:$M14:tensor:$L:@knob+-b+2048+-ub+1024"
    "kl14-tensor-t2:$M14:tensor:$L:@knob+-t+2"
    "kl14-tensor-4cpu:$M14:tensor:$L:@knob+@cpuset=0-3"
    "kl14-tensor-nofa:$M14:tensor:$L:@knob+-fa+off"
    "kl7-tensor:$M7:tensor:built:2048:1,4:@knob"
    "kl7-tensor-f16:$M7:tensor:built:2048:1,4:@knob+-ctk+f16+-ctv+f16"
    "kl7-tensor-ar-internal:$M7:tensor:built:2048:1,4:@knob+@GGML_CUDA_ALLREDUCE=internal"
)
mgpu_serve lknobs.tsv lcp "${cells[@]}"
