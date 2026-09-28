#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/7-nccl.sh — step 7: the collective alone,
# under each NCCL setting the serving steps try, with no engine in the way.
#
# Step 1 measured NCCL's own choice. Here each arm re-runs mgpu_link.py's
# all-reduce ladder (4 KiB .. 64 MiB) with one setting changed, so the
# latency at decode sizes (4-64 KiB) and the bandwidth at prefill sizes
# (8 MiB+) of every arm in 8-vknobs.sh is measured without vLLM around it.
# The socket arm (NCCL_SHM_DISABLE=1) is the slow control: a second
# (latency, tok/s) point for the fitted per-all-reduce cost.
#
# Also: HOSTMEM, a pinned host-to-host copy (the RAM side of every host-staged
# collective); H2D2, both cards loading from host memory at once (does the
# pair get twice one card's 6 GiB/s, or share one root complex?).
#
# Every tensor-parallel number in steps 3-5 is decided here: TP pays two
# all-reduces a layer per decode step, so its speedup is set by the latency of
# a ~10 KiB all-reduce, and that latency is set by whether the driver gives
# these two GeForce cards peer access or bounces every collective through host
# RAM. Measured, not assumed.
#
# RUN_ARTIFACTS: nccl.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/7-nccl.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "7-nccl.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/7-nccl.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

IMG="vllm/vllm-openai:v0.26.0"
NAME="$RUN_ID-nccl"

mgpu_preamble nccl.tsv
DIGEST=$(image_digest "$IMG") || { _fail "$IMG resolves to no digest on $RUN_HOST" || true; exit 1; }
trap '"$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

# arm -> the env words it adds (empty: NCCL's own choice).
declare -A ARM_ENV=(
    [base]=""
    [LL]="NCCL_PROTO=LL"
    [LL128]="NCCL_PROTO=LL128"
    [simple]="NCCL_PROTO=Simple"
    [ch1]="NCCL_MIN_NCHANNELS=1 NCCL_MAX_NCHANNELS=1"
    [ch4]="NCCL_MIN_NCHANNELS=4"
    [shmcpy]="NCCL_SHM_USE_CUDA_MEMCPY=1"
    [buf1m]="NCCL_BUFFSIZE=1048576"
    [buf8m]="NCCL_BUFFSIZE=8388608"
    [socket]="NCCL_SHM_DISABLE=1"
)
ARMS=(base LL LL128 simple ch1 ch4 shmcpy buf1m buf8m socket)

open_tsv microbench_stamp
emit stamp TOOL name=mgpu_link "img=$DIGEST"

rig_line() { "$SSH" "$RUN_HOST" "$1" </dev/null; }

# The probe, once per arm. A row is filed per MGPU line; the NCCL transport is
# read from the same output.
probe_once() {
    local log=$1 p2p=$2 env=() w
    for w in ${ARM_ENV[$p2p]}; do env+=(-e "$w"); done
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
    label = f"nccl-{p2p}" + (f" gpu={doc['gpu']}" if "gpu" in doc else "")
    label += f" bytes={doc['bytes']}" if "bytes" in doc else ""
    fields = [f"arm={p2p}", f"nccl_via={via}"]
    fields += [f"{k}={str(v).replace(' ', '_')}" for k, v in doc.items()]
    print("\t".join([host, label, kind, *fields]))
PY
    rm -f "$log"
}

for arm in "${ARMS[@]}"; do
    say "link probe, arm $arm: ${ARM_ENV[$arm]:-NCCL default}"
    probe "$arm"
done

# The RAM and root-complex side, in the same image (mgpu_hostmem.py).
"$DOCKER" run --rm -i --name "$NAME-host" --runtime=nvidia --gpus all --ipc=host \
    --entrypoint bash "$DIGEST" -c 'cat > /tmp/h.py && python3 /tmp/h.py' \
    <"$HERE/mgpu_hostmem.py" 2>/dev/null | while IFS=$'\t' read -r kind rest; do
        # shellcheck disable=SC2086  # the k=v words are split on purpose
        emit row host "$kind" ${rest//$'\t'/ }
    done

close_tsv
say "wrote $OUT"
