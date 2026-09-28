#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/17-arch.sh — step 17: architectures the
# ladder does not cover, and llama.cpp's speculative decoding.
#
#   nemo      Nemotron-3-Nano-30B-A3B (hybrid Mamba): layer / tensor, against
#             vLLM tp2+EP on the AWQ checkpoint (step 6). Tensor may refuse
#   goss      gpt-oss-20b MXFP4 (attention sinks, 128-token sliding window, 32
#             wide experts): one card, layer, tensor; and the unsloth Q3_K_M
#             one card; the legacy `gptoss` file one card (expected REFUSED)
#   gem       gemma-4-26B-A4B IQ3_XXS (1024 sliding window): g0, layer, tensor
#   north     North-Mini-Code (cohere2moe, 4096 sliding window): layer, tensor
#   ornith    Ornith-1.0-35B: its header will not read in gguf-py; one probe
#   spec      KAT-Coder-V2.5 Q3_K_M with its MTP head (--spec-type draft-mtp),
#             against the same cell without; gpt-oss-20b with the 4B gpt-oss
#             draft (-md), layer and tensor; n=1 and 4 on the real workload
#
# RUN_ARTIFACTS: arch.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/17-arch.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "17-arch.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/17-arch.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

X=/models/moe
L="built:2048:1,4,16"
GQ3=/hf/hub/models--unsloth--gpt-oss-20b-GGUF/snapshots/d449b42d93e1c2c7bda5312f5c25c8fb91dfa9b4/gpt-oss-20b-Q3_K_M.gguf
KAT=$X/KAT-Coder-V2.5-Dev_Q3_K_M_imatrix_MTP.gguf
GOSS=$X/gpt-oss-20b-MXFP4.gguf
cells=(
    "nemo-layer:$X/nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf:layer:$L"
    "nemo-tensor:$X/nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf:tensor:$L"
    "goss-g0:$GOSS:g0:$L:@headroom=384"
    "goss-layer:$GOSS:layer:$L"
    "goss-tensor:$GOSS:tensor:$L"
    "goss3-g0:$GQ3:g0:$L:@headroom=384"
    "gossold-g0:$X/gpt-oss-20b.gguf:g0:$L"
    "gem-g0:$X/gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf:g0:$L:@headroom=512"
    "gem-layer:$X/gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf:layer:$L"
    "gem-tensor:$X/gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf:tensor:$L"
    "north-layer:$X/North-Mini-Code-1.0-Q4_K_M.gguf:layer:$L"
    "north-tensor:$X/North-Mini-Code-1.0-Q4_K_M.gguf:tensor:$L"
    "ornith-layer:$X/Ornith-1.0-35B_Q3_K_M.gguf:layer:$L"
    "katmtp-layer-off:$KAT:layer:built:2048:1,4"
    "katmtp-layer-on:$KAT:layer:built:2048:1,4:--spec-type+draft-mtp"
    "gossd-layer-off:$GOSS:layer:built:2048:1,4"
    "gossd-layer-on:$GOSS:layer:built:2048:1,4:-md+$X/4b-Q4_K_M.gguf+-ngld+99"
    "gossd-tensor-on:$GOSS:tensor:built:2048:1,4:-md+$X/4b-Q4_K_M.gguf+-ngld+99"
)
mgpu_serve arch.tsv lcp "${cells[@]}"
