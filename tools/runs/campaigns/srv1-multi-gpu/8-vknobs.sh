#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/8-vknobs.sh — step 8: vLLM's own settings
# on the 7B AWQ two-card split, each against the same cell without it.
#
# Every cell is @knob (mgpu_sweep.py): n=1 is five 256-token replies with a
# spread, n=16 is sixteen closed-loop streams for 30 s, so a setting's effect is
# larger than the run-to-run noise and the sidecar sees a sustained load.
#
#   what it isolates
#   eager       CUDA graphs off: the CPU's kernel-launch cost, per token
#   NCCL_*      the collective itself: protocol (LL / LL128 / Simple), channel
#               count, host-memory copy by the copy engine, and the socket
#               transport (NCCL_SHM_DISABLE) as a slow control
#   async       vLLM's async scheduling: CPU scheduling overlapped with the GPU
#   4cpu        the engine held to 4 of srv1's 6 cores (--cpuset-cpus): whether
#               the CPU is a two-card bottleneck; dp2 and g0 are its controls
#
# p2p is `on` throughout: on srv1 the driver refuses peer access, so vLLM turns
# its custom all-reduce off itself and yesterday's on/off cells ran one setup.
#
# RUN_ARTIFACTS: vknobs.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/8-vknobs.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "8-vknobs.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/8-vknobs.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

M="Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
L="2048:1,16"
cells=(
    "k7-g0:$M:g0:on:$L:@knob"
    "k7-g0-eager:$M:g0:on:$L:@knob+--enforce-eager"
    "k7-g0-4cpu:$M:g0:on:$L:@knob+@cpuset=0-3"
    "k7-tp2:$M:tp2:on:$L:@knob"
    "k7-tp2-eager:$M:tp2:on:$L:@knob+--enforce-eager"
    "k7-tp2-LL:$M:tp2:on:$L:@knob+@NCCL_PROTO=LL"
    "k7-tp2-LL128:$M:tp2:on:$L:@knob+@NCCL_PROTO=LL128"
    "k7-tp2-simple:$M:tp2:on:$L:@knob+@NCCL_PROTO=Simple"
    "k7-tp2-ch1:$M:tp2:on:$L:@knob+@NCCL_MIN_NCHANNELS=1+@NCCL_MAX_NCHANNELS=1"
    "k7-tp2-ch4:$M:tp2:on:$L:@knob+@NCCL_MIN_NCHANNELS=4"
    "k7-tp2-shmcpy:$M:tp2:on:$L:@knob+@NCCL_SHM_USE_CUDA_MEMCPY=1"
    "k7-tp2-socket:$M:tp2:on:$L:@knob+@NCCL_SHM_DISABLE=1"
    "k7-tp2-async:$M:tp2:on:$L:@knob+--async-scheduling"
    "k7-tp2-4cpu:$M:tp2:on:$L:@knob+@cpuset=0-3"
    "k7-dp2:$M:dp2:on:$L:@knob"
    "k7-dp2-4cpu:$M:dp2:on:$L:@knob+@cpuset=0-3"
)
mgpu_serve vknobs.tsv vllm "${cells[@]}"
