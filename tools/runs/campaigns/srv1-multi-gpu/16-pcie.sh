#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/16-pcie.sh — step 16: the same cells with
# the PCIe links held to gen3, gen2 and gen1, to split the two-card cost into
# the part the wire's speed sets and the part it does not.
#
# How: each card's root port (00:01.0, 00:01.1 on srv1, read live) has a
# Target Link Speed in Link Control 2 (PCIe cap + 0x30, bits 3:0; 3 = 8 GT/s,
# 2 = 5 GT/s, 1 = 2.5 GT/s). The step writes it with setpci and retrains the
# link (Link Control + 0x10, bit 5); the card then trains no faster. Width
# stays x8. The owner approved this on 2026-09-27 (root on a live host,
# undone by writing 3 back or a reboot; the risk is a card dropping off the
# bus during retrain, which ends the step). On ANY exit the trap writes gen3
# back and retrains; on a clean exit the last PCIE rows say what the ports
# read after restore.
#
# Per speed: PCIE (each port's target and status), the all-reduce ladder
# (mgpu_link.py, NCCL's own choice), vLLM 7B AWQ g0 and tp2, llama.cpp 14B
# g0, layer and tensor, all @knob, and each cell's PREFILL. The cards' link
# under load is in every level row (link0=/link1=, from the sidecar), which is
# the proof the cap held.
#
# Prediction (the interconnect model of 2026-09-27): decode at n=1 barely
# moves (the per-all-reduce cost is ~95% fixed latency), prefill and n=16
# slow roughly with the wire, and the one-card cells only in their PREFILL.
#
# RUN_ARTIFACTS: pcie.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/16-pcie.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "16-pcie.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/16-pcie.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

DRIVER=tools/runs/drivers/mgpu_sweep.py
V="Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
M14="/models/dense/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf"
GENS=(3 2 1)

mgpu_preamble pcie.tsv
VDIG=$(image_digest "vllm/vllm-openai:v0.26.0") || { _fail "vllm image resolves to no digest" || true; exit 1; }
LIMG=$(_py -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]["llamacpp_image"])' \
    "$RUN_ROOT/tools/runs/hosts.json" "$RUN_HOST") || { _fail "hosts.json names no llamacpp_image" || true; exit 2; }
LDIG=$(image_digest "$LIMG") || { _fail "$LIMG resolves to no digest" || true; exit 1; }
export VLLM_IMG="$VDIG" LCP_IMG="$LDIG"
NAME="$RUN_ID-pcie"

rig_line() { "$SSH" "$RUN_HOST" "$1" </dev/null 2>/dev/null; }

# The root port above each card, read from sysfs, never assumed.
PORTS=$(rig_line 'for g in $(nvidia-smi --query-gpu=pci.bus_id --format=csv,noheader); do
    d=$(echo "$g" | tr A-Z a-z | sed "s/^00000000/0000/"); basename "$(dirname "$(readlink -f /sys/bus/pci/devices/$d)")"; done' | paste -sd' ' -)
[ "$(wc -w <<<"$PORTS")" = 2 ] || { _fail "REFUSED — the two cards' root ports did not read: '$PORTS'" || true; exit 2; }

set_speed() {
    local gen=$1 p
    for p in $PORTS; do
        rig_line "sudo setpci -s $p CAP_EXP+0x30.w=000$gen:000f && sudo setpci -s $p CAP_EXP+0x10.w=0020:0020" || return 1
    done
    sleep 2
}

port_rows() {
    local when=$1 p ctl sta
    for p in $PORTS; do
        ctl=$(rig_line "sudo setpci -s $p CAP_EXP+0x30.w")
        sta=$(rig_line "sudo lspci -s $p -vv | sed -n 's/.*LnkSta:[[:space:]]*Speed \([^,]*\), Width \([^ ,]*\).*/\1x\2/p'")
        row "port-$p" PCIE "when=$when" "port=$p" "lnkctl2=$(_tok "${ctl:-unread}")" "target=$((16#${ctl:-0} & 15))" "lnksta=$(_tok "${sta:-unread}")"
    done
}

RESTORED=""
restore() {
    [ -n "$RESTORED" ] || set_speed 3 || true
    "$DOCKER" rm -f "$RUN_ID-mgpu-a" "$RUN_ID-mgpu-b" "$NAME" >/dev/null 2>&1 || true
}
trap restore EXIT

open_tsv workload_stamp tools/runs/workload.py
emit stamp NOTE "vllm=$VDIG" "llamacpp=$LIMG" "ports=$(echo $PORTS | tr " " ,)"

for gen in "${GENS[@]}"; do
    say "PCIe gen$gen"
    set_speed "$gen" || { emit row pcie REFUSED "gen=$gen" -- "setpci did not take on $PORTS"; break; }
    emit port_rows "gen$gen"
    emit rig_stamp
    log=$(mktemp)
    "$DOCKER" run --rm -i --name "$NAME" --runtime=nvidia --gpus all --ipc=host \
        -e CUDA_DEVICE_ORDER=PCI_BUS_ID --entrypoint bash "$VDIG" \
        -c 'cat > /tmp/l.py && python3 /tmp/l.py' <"$HERE/mgpu_link.py" >"$log" 2>/dev/null || true
    _py - "$log" "$gen" <<'PY' >>"$OUT"
import json
import os
import sys

log, gen = sys.argv[1:3]
for line in open(log, encoding="utf-8", errors="replace"):
    if line.startswith("MGPU\t"):
        doc = json.loads(line.split("\t", 1)[1])
        kind = doc.pop("kind")
        label = f"pcie-gen{gen}" + (f" gpu={doc['gpu']}" if "gpu" in doc else "")
        label += f" bytes={doc['bytes']}" if "bytes" in doc else ""
        fields = [f"gen={gen}"] + [f"{k}={str(v).replace(' ', '_')}" for k, v in doc.items()]
        print("\t".join([os.environ["RUN_HOST"], label, kind, *fields]))
PY
    rm -f "$log"
    emit _py "$DRIVER" vllm \
        "g$gen-v7-g0:$V:g0:on:2048:1,16:@knob" \
        "g$gen-v7-tp2:$V:tp2:on:2048:1,16:@knob"
    emit _py "$DRIVER" lcp \
        "g$gen-l14-g0:$M14:g0:built:2048:1,4:@knob" \
        "g$gen-l14-layer:$M14:layer:built:2048:1,4:@knob" \
        "g$gen-l14-tensor:$M14:tensor:built:2048:1,4:@knob"
done

set_speed 3
RESTORED=1
emit port_rows restored
close_tsv
say "wrote $OUT"
