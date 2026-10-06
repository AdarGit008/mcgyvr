#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/18-offload.sh — step 18: MoE experts held
# in host RAM (--n-cpu-moe N: the experts of the first N layers stay on the CPU),
# so decode reads them over srv1's DDR4-3600 dual channel and prefill streams
# them over PCIe. The one step here where RAM speed and capacity, and the CPU,
# are the measured thing.
#
#   c30q4     Qwen3-Coder-30B-A3B Q4_K_M (17.3 GiB, 48 layers): one card with
#             the first 16 / 24 / 32 layers' experts on the CPU (~6 / 9 / 12 GiB
#             in host RAM), -t 6 and -t 3 at 24 (does decode follow the cores or
#             the memory?), and layer split with 8 layers' experts on the CPU.
#             Predicted: ~+1.2 ms a token per offloaded layer (~23 MB of experts
#             per layer per token against ~40 GB/s), prefill PCIe-bound
#   a3b       Qwen3.6-35B-A3B IQ3_XXS on one card with 10 layers' experts out:
#             one card plus RAM against step 4's two-card split
#   next      Qwen3-Coder-Next UD-Q3_K_XL (33.8 GiB), layer split, 24 layers'
#             experts out (~13.8 GiB mapped against ~14.3 GiB available). The
#             owner approved it on 2026-09-27 knowing srv1 hard-locked under
#             --n-cpu-moe on 09-01 (hosts.json):
#             one level, last in the step, never --no-mmap or --mlock
#
# Offload cells are not fit-predicted (mgpu_sweep.py): the engine decides.
# Each level row carries swap_kib and free_min_mib from the sidecar.
#
# RUN_ARTIFACTS: offload.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/18-offload.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "18-offload.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/18-offload.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

X=/models/moe
C30=$X/qwen3-coder-30b.gguf
A3B=$X/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf
NEXT=$X/Qwen3-Coder-Next-UD-Q3_K_XL.gguf
L="built:2048:1,4"
cells=(
    "o30-g0-cm16:$C30:g0:$L:--n-cpu-moe+16"
    "o30-g0-cm24:$C30:g0:$L:--n-cpu-moe+24"
    "o30-g0-cm24-t3:$C30:g0:$L:--n-cpu-moe+24+-t+3"
    "o30-g0-cm32:$C30:g0:$L:--n-cpu-moe+32"
    "o30-layer-cm8:$C30:layer:$L:--n-cpu-moe+8"
    "oa3b-g0-cm10:$A3B:g0:$L:--n-cpu-moe+10"
    "onext-layer-cm24:$NEXT:layer:built:2048:1:--n-cpu-moe+24"
)
mgpu_serve offload.tsv lcp "${cells[@]}"
