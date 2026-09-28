#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/1-link.sh — step 1: what the wire between
# the two cards is, before anything is served across it.
#
# Every tensor-parallel number in steps 3-5 is decided here: TP pays two
# all-reduces a layer per decode step, so its speedup is set by the latency of
# a ~10 KiB all-reduce, and that latency is set by whether the driver gives
# these two GeForce cards peer access or bounces every collective through host
# RAM. Measured, not assumed.
#
# Rows (link.tsv):
#   GPU    one per card (_mgpu.sh)
#   TOPO   nvidia-smi topo -m, the GPU0<->GPU1 cell (PIX/PXB/PHB/NODE/SYS/NV#)
#   P2P    nvidia-smi topo -p2p r and w, GPU0->GPU1 (OK / NS / CNS / ...)
#   BAR1   each card's BAR1 total: ~the card's VRAM means Resizable BAR is on,
#          which the patched-driver P2P route needs; 256 MiB means it is off
#   IOMMU  the iommu words on the kernel command line, or none
#   PEER / H2D / LINK / AR   mgpu_link.py, twice: p2p=on (NCCL's choice) and
#          p2p=off (NCCL_P2P_DISABLE=1), each with the transport NCCL logged
#
# RUN_ARTIFACTS: link.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/1-link.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "1-link.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/1-link.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

IMG="vllm/vllm-openai:v0.26.0"
NAME="$RUN_ID-link"

mgpu_preamble "${LINK_ARTIFACT:-link.tsv}"
DIGEST=$(image_digest "$IMG") || { _fail "$IMG resolves to no digest on $RUN_HOST" || true; exit 1; }
trap '"$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

open_tsv microbench_stamp
emit stamp TOOL name=mgpu_link "img=$DIGEST"

rig_line() { "$SSH" "$RUN_HOST" "$1" </dev/null; }

# GPU0's row of the topology matrix; its second column is the GPU1 relation.
rel=$(rig_line 'nvidia-smi topo -m' | awk '$1 ~ /^GPU0/ { print $3; exit }')
emit row pair TOPO "gpu0_gpu1=$(_tok "${rel:-unread}")"
for mode in r w; do
    cell=$(rig_line "nvidia-smi topo -p2p $mode" | awk '$1 == "GPU0" { print $3; exit }')
    emit row pair P2P "mode=$mode" "gpu0_gpu1=$(_tok "${cell:-unread}")"
done
rig_line "nvidia-smi -q | awk '/BAR1 Memory Usage/ { getline; print \$3 }'" |
    awk '{ print NR - 1, $1 }' | while read -r idx mib; do
        emit row "gpu$idx" BAR1 "index=$idx" "total_mib=$(_tok "$mib")"
    done
iommu=$(rig_line 'tr " " "\n" </proc/cmdline | grep -i iommu | paste -sd, -' || true)
emit row host IOMMU "cmdline=$(_tok "${iommu:-none}")"

# The probe, once per arm. A row is filed per MGPU line; the NCCL transport is
# read from the same output.
probe_once() {
    local log=$1 p2p=$2 env=()
    [ "$p2p" = off ] && env=(-e NCCL_P2P_DISABLE=1)
    "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
    "$DOCKER" run --rm -i --name "$NAME" --runtime=nvidia --gpus all --ipc=host \
        -e CUDA_DEVICE_ORDER=PCI_BUS_ID -e NCCL_DEBUG=INFO "${env[@]}" \
        --entrypoint bash "$DIGEST" -c 'cat > /tmp/mgpu_link.py && python3 /tmp/mgpu_link.py' \
        <"$HERE/mgpu_link.py" >"$log" 2>&1
}

probe() {
    local p2p=$1 log via
    log=$(mktemp)
    if ! retry3 probe_once "$log" "$p2p"; then
        emit refused "link-p2p-$p2p" "p2p=$p2p" checkpoint_quant=none "tries=$RUN_TRIES" \
            -- "the link probe exited non-zero on every try; its last words: $(grep -vE 'NCCL INFO' "$log" | tail -3 | tr '\n\t' '  ' | cut -c1-300)"
    fi
    via=$(grep -oE 'NCCL INFO Channel [0-9]+(/[0-9]+)? : .* via [A-Za-z0-9/_]+' "$log" | awk '{ print $NF }' | sort -u | paste -sd, - || true)
    _py - "$log" "$p2p" "${via:-unread}" <<'PY' >>"$OUT"
import json
import os
import sys

log, p2p, via = sys.argv[1:4]
host = os.environ["RUN_HOST"]
for line in open(log, encoding="utf-8", errors="replace"):
    if not line.startswith("MGPU\t"):
        continue
    doc = json.loads(line.split("\t", 1)[1])
    kind = doc.pop("kind")
    label = f"link-p2p-{p2p}" + (f" gpu={doc['gpu']}" if "gpu" in doc else "")
    label += f" bytes={doc['bytes']}" if "bytes" in doc else ""
    fields = [f"p2p={p2p}", f"nccl_via={via}"]
    fields += [f"{k}={str(v).replace(' ', '_')}" for k, v in doc.items()]
    print("\t".join([host, label, kind, *fields]))
PY
    rm -f "$log"
}

say "link probe, NCCL's own choice"
probe on
say "link probe, NCCL_P2P_DISABLE=1"
probe off

close_tsv
say "wrote $OUT"
