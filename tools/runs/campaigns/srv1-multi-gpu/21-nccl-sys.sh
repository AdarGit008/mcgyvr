#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/21-nccl-sys.sh — step 21: the all-reduce
# with NCCL told to take the peer path across the CPU's host bridge.
#
# Step 19 granted peer access (topo -p2p OK, a verified cuda:0 -> cuda:1 copy
# at 6.11 GiB/s), yet NCCL still chose SHM: the cards meet at the CPU (PHB)
# and NCCL's default P2P level stops short of that path. NCCL_P2P_LEVEL=SYS
# lifts the limit. The question is the small sizes decode pays (4 KiB is
# ~0.06 ms over SHM, fixed), and whether the peer path returns right data:
# vLLM's own peer test failed on this rig, so every AR row carries
# `verified`, an all-reduce of known values checked on both ranks.
#
# Arms, on the same boot, each the full mgpu_link.py probe:
#   default   NCCL's own choice (expected SHM, as step 19)
#   sys       NCCL_P2P_LEVEL=SYS
# The transport NCCL chose is read from its own Channel lines (nccl_via).
# Refuses, writing no row, unless peer access is live.
#
# RUN_ARTIFACTS: nccl-sys.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/21-nccl-sys.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "21-nccl-sys.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/21-nccl-sys.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

mgpu_preamble nccl-sys.tsv
VDIG=$(image_digest "vllm/vllm-openai:v0.26.0") || { _fail "vllm image resolves to no digest" || true; exit 1; }
NAME="$RUN_ID-ncclsys"
trap '"$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

rig_line() { "$SSH" "$RUN_HOST" "$1" </dev/null 2>/dev/null; }

P2P_W=$(rig_line 'nvidia-smi topo -p2p w' | awk '$1 == "GPU0" { print $3; exit }' || true)
if [ "${P2P_W:-}" != OK ]; then
    _fail "REFUSED — peer access is not live on $RUN_HOST (topo -p2p w=${P2P_W:-unread}), so NCCL_P2P_LEVEL=SYS has no peer path to take and no row is written" || true
    exit 2
fi

open_tsv workload_stamp tools/runs/workload.py
emit stamp NOTE "vllm=$VDIG"
rel=$(rig_line 'nvidia-smi topo -m' | awk '$1 ~ /^GPU0/ { print $3; exit }' || true)
emit row pair TOPO "gpu0_gpu1=$(_tok "${rel:-unread}")"
emit row pair P2P mode=w "gpu0_gpu1=$(_tok "$P2P_W")"

probe_once() {
    local log=$1 arm=$2 env=()
    [ "$arm" = sys ] && env=(-e NCCL_P2P_LEVEL=SYS)
    "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
    "$DOCKER" run --rm -i --name "$NAME" --runtime=nvidia --gpus all --ipc=host \
        -e CUDA_DEVICE_ORDER=PCI_BUS_ID -e NCCL_DEBUG=INFO "${env[@]}" \
        --entrypoint bash "$VDIG" -c 'cat > /tmp/mgpu_link.py && python3 /tmp/mgpu_link.py' \
        <"$HERE/mgpu_link.py" >"$log" 2>&1
}

probe() {
    local arm=$1 log via
    log=$(mktemp)
    if ! retry3 probe_once "$log" "$arm"; then
        emit refused "nccl-$arm" "arm=$arm" checkpoint_quant=none "tries=$RUN_TRIES" \
            -- "the link probe exited non-zero on every try; its last words: $(grep -vE 'NCCL INFO' "$log" | tail -3 | tr '\n\t' '  ' | cut -c1-300)"
    fi
    via=$(grep -oE 'NCCL INFO Channel [0-9]+(/[0-9]+)? : .* via [A-Za-z0-9/_]+' "$log" | awk '{ print $NF }' | sort -u | paste -sd, - || true)
    _py - "$log" "$arm" "${via:-unread}" <<'PY' >>"$OUT"
import json
import os
import sys

log, arm, via = sys.argv[1:4]
host = os.environ["RUN_HOST"]
for line in open(log, encoding="utf-8", errors="replace"):
    if not line.startswith("MGPU\t"):
        continue
    doc = json.loads(line.split("\t", 1)[1])
    kind = doc.pop("kind")
    label = f"nccl-{arm}" + (f" gpu={doc['gpu']}" if "gpu" in doc else "")
    label += f" bytes={doc['bytes']}" if "bytes" in doc else ""
    fields = [f"arm={arm}", f"nccl_via={via}"]
    fields += [f"{k}={str(v).replace(' ', '_')}" for k, v in doc.items()]
    print("\t".join([host, label, kind, *fields]))
PY
    rm -f "$log"
}

emit rig_stamp
say "link probe, NCCL's own choice"
probe default
say "link probe, NCCL_P2P_LEVEL=SYS"
probe sys
emit rig_stamp
close_tsv
say "wrote $OUT"
