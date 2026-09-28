#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/19-p2p.sh — step 19: the two cards WITH
# peer access, re-measured on the cells steps 1, 7, 8 and 9 measured without it.
#
# Before this step the owner changes srv1 by hand, following
# records/evidence/2026-09-27-srv1-multi-gpu/p2p-rebar-runbook.md: Above 4G
# Decoding on in the BIOS, BAR1 resized from Linux through resource1_resize
# (the BIOS has no Re-Size BAR option), the IOMMU in passthrough, and the
# P2P-patched open kernel module (the p2p patch forward-ported onto NVIDIA's
# open-gpu-kernel-modules at the userspace driver's exact version) in place of
# the proprietary DKMS module. The driver version does not move, so the rows
# here stand beside the earlier artifacts cell for cell.
#
# THE REFUSAL. Nothing is written unless peer access is live, so this step can
# never file a no-op as a "with P2P" measurement. Before the TSV is opened it
# reads, and exits 2 with no rows unless all hold:
#   nvidia-smi topo -p2p w, GPU0->GPU1, is OK (the write path NCCL and vLLM's
#          custom all-reduce use; `r` is filed, not required: some Intel root
#          complexes forward peer writes and not peer reads)
#   torch.cuda.can_device_access_peer is True both ways, inside the vLLM image,
#          and a 4 MiB copy cuda:0 -> cuda:1 -> cuda:0 comes back identical
#   each card's BAR1 total is at least its VRAM (BAR1 is resized; the
#          patch maps peer memory through BAR1)
#
# Rows (p2p.tsv):
#   GPU / TOPO / P2P / BAR1 / IOMMU   as 1-link.sh, plus the IOMMU domain type
#            of card 0's group (identity = passthrough; DMA / DMA-FQ =
#            translated, which the patch's peer writes do not survive)
#   MODULE   the loaded nvidia module's license, version and path (Dual
#            MIT/GPL = open; NVIDIA = proprietary)
#   PEERGATE what the refusal read
#   ENV / PEER / H2D / LINK / AR      mgpu_link.py, twice: p2p=on (NCCL's
#            choice; the transport should now read P2P/...) and p2p=off
#            (NCCL_P2P_DISABLE=1: the host-memory path on the same boot)
#   CONFIG / PREFILL / n=K            mgpu_sweep.py @knob cells:
#     vLLM 7B AWQ, 2048:1,16 (as 8-vknobs.sh k7-*)
#       p7-g0          one card
#       p7-tp2-check   tp2 under VLLM_SKIP_P2P_CHECK=0: vLLM runs its own peer
#                      test before it enables the custom all-reduce, and a
#                      failing test turns it off (p2p_check=tested). First, so
#                      a peer path that corrupts is caught before the cell
#                      that trusts the driver
#       p7-tp2         tp2 as vLLM ships: custom all-reduce on when the driver
#                      grants peer access (custom_ar=on, ar_backend=CUSTOM,...)
#       p7-tp2-nocar   tp2 with --disable-custom-all-reduce: NCCL over P2P alone
#       p7-tp2-p2poff  tp2 with p2p=off: host memory, this boot's control
#       p7-dp2         two replicas
#     llama.cpp 14B Q4_K_M, built:2048:1,4,8 (as 9-lknobs.sh kl14-*)
#       pl14-g0 / -layer / -tensor
#       pl14-tensor-ar-nccl / -ar-internal   GGML_CUDA_ALLREDUCE
#       pl14-layer-p2p / pl14-tensor-p2p     GGML_CUDA_P2P=1: llama.cpp enables
#                      peer access only under that variable (or an NCCL build)
#     llama.cpp 7B IQ4_XS tensor, built:2048:1,4 (as kl7-tensor)
#
# Files under the same envelope as steps 1-18 with --date 2026-09-27 (the door
# defaults to today, UTC). If the module swap moves gpu_reserve_mib, gate 2
# refuses until hosts.json[srv1].rig is redeclared: the owner's call.
#
# RUN_ARTIFACTS: p2p.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/19-p2p.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "19-p2p.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/19-p2p.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

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
M7="/models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf"
VL="2048:1,16"
LL="built:2048:1,4,8"
RUNBOOK=records/evidence/2026-09-27-srv1-multi-gpu/p2p-rebar-runbook.md

mgpu_preamble p2p.tsv
VDIG=$(image_digest "vllm/vllm-openai:v0.26.0") || { _fail "vllm image resolves to no digest" || true; exit 1; }
LIMG=$(_py -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]["llamacpp_image"])' \
    "$RUN_ROOT/tools/runs/hosts.json" "$RUN_HOST") || { _fail "hosts.json names no llamacpp_image" || true; exit 2; }
LDIG=$(image_digest "$LIMG") || { _fail "$LIMG resolves to no digest" || true; exit 1; }
export VLLM_IMG="$VDIG" LCP_IMG="$LDIG"
NAME="$RUN_ID-p2p"
trap '"$DOCKER" rm -f "$RUN_ID-mgpu-a" "$RUN_ID-mgpu-b" "$NAME" "$NAME-peer" >/dev/null 2>&1 || true' EXIT

rig_line() { "$SSH" "$RUN_HOST" "$1" </dev/null 2>/dev/null; }

# --------------------------------------------------------------------------
# the refusal: read before the TSV exists
# --------------------------------------------------------------------------

P2P_R=$(rig_line 'nvidia-smi topo -p2p r' | awk '$1 == "GPU0" { print $3; exit }' || true)
P2P_W=$(rig_line 'nvidia-smi topo -p2p w' | awk '$1 == "GPU0" { print $3; exit }' || true)
BAR1=$(rig_line "nvidia-smi -q | awk '/BAR1 Memory Usage/ { getline; print \$3 }'" | paste -sd' ' - || true)
VRAM=$(rig_line 'nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits' | tr -d ' ' | paste -sd' ' - || true)

PEER_PY='
import torch
a = torch.cuda.can_device_access_peer(0, 1)
b = torch.cuda.can_device_access_peer(1, 0)
ok = False
if a and b:
    x = torch.arange(1 << 20, dtype=torch.int32, device="cuda:0")
    y = x.to("cuda:1")
    z = y.to("cuda:0")
    torch.cuda.synchronize()
    ok = bool(torch.equal(x, z)) and bool(torch.equal(x.cpu(), y.cpu()))
print(f"p2p_0_to_1={a} p2p_1_to_0={b} copy_verified={ok}")
'
PEER=$("$DOCKER" run --rm --name "$NAME-peer" --runtime=nvidia --gpus all \
    -e CUDA_DEVICE_ORDER=PCI_BUS_ID --entrypoint python3 "$VDIG" -c "$PEER_PY" 2>/dev/null |
    grep -E '^p2p_0_to_1=' | tail -1 || true)

bar_ok=1
read -r -a bars <<<"${BAR1:-}"
read -r -a vrams <<<"${VRAM:-}"
if [ "${#bars[@]}" != 2 ] || [ "${#vrams[@]}" != 2 ]; then
    bar_ok=0
else
    for i in 0 1; do
        if ! [[ "${bars[$i]}" =~ ^[0-9]+$ && "${vrams[$i]}" =~ ^[0-9]+$ ]] || [ "${bars[$i]}" -lt "${vrams[$i]}" ]; then
            bar_ok=0
        fi
    done
fi

if [ "${P2P_W:-}" != OK ] || [ "$bar_ok" != 1 ] ||
    [ "${PEER:-}" != "p2p_0_to_1=True p2p_1_to_0=True copy_verified=True" ]; then
    _fail "REFUSED — peer access is not live on $RUN_HOST, so there is nothing for this step to measure and no row is written: topo -p2p w=${P2P_W:-unread} r=${P2P_R:-unread}; BAR1 MiB=[${BAR1:-unread}] against VRAM MiB=[${VRAM:-unread}]; in-container ${PEER:-peer probe printed nothing}. Bring the rig up per $RUNBOOK first" || true
    exit 2
fi

# --------------------------------------------------------------------------
# the rows
# --------------------------------------------------------------------------

open_tsv workload_stamp tools/runs/workload.py
emit stamp NOTE "vllm=$VDIG" "llamacpp=$LIMG"

rel=$(rig_line 'nvidia-smi topo -m' | awk '$1 ~ /^GPU0/ { print $3; exit }' || true)
emit row pair TOPO "gpu0_gpu1=$(_tok "${rel:-unread}")"
emit row pair P2P mode=r "gpu0_gpu1=$(_tok "${P2P_R:-unread}")"
emit row pair P2P mode=w "gpu0_gpu1=$(_tok "$P2P_W")"
for i in 0 1; do
    emit row "gpu$i" BAR1 "index=$i" "total_mib=${bars[$i]}"
done
iommu=$(rig_line 'tr " " "\n" </proc/cmdline | grep -i iommu | paste -sd, -' || true)
domain=$(rig_line 'd=$(nvidia-smi --query-gpu=pci.bus_id --format=csv,noheader | head -1 | tr A-Z a-z | sed "s/^00000000/0000/"); cat /sys/bus/pci/devices/$d/iommu_group/type 2>/dev/null' || true)
emit row host IOMMU "cmdline=$(_tok "${iommu:-none}")" "gpu0_domain=$(_tok "${domain:-none}")"
lic=$(rig_line 'modinfo -F license nvidia' || true)
ver=$(rig_line 'modinfo -F version nvidia' || true)
path=$(rig_line 'modinfo -F filename nvidia' || true)
emit row host MODULE "license=$(_tok "${lic:-unread}")" "version=$(_tok "${ver:-unread}")" "path=$(_tok "${path:-unread}")"
# shellcheck disable=SC2086  # the k=v words are split on purpose
emit row pair PEERGATE $PEER

# The link probe, once per arm, as 1-link.sh: a row per MGPU line, and the
# NCCL transport read from the same output.
probe_once() {
    local log=$1 p2p=$2 env=()
    [ "$p2p" = off ] && env=(-e NCCL_P2P_DISABLE=1)
    "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
    "$DOCKER" run --rm -i --name "$NAME" --runtime=nvidia --gpus all --ipc=host \
        -e CUDA_DEVICE_ORDER=PCI_BUS_ID -e NCCL_DEBUG=INFO "${env[@]}" \
        --entrypoint bash "$VDIG" -c 'cat > /tmp/mgpu_link.py && python3 /tmp/mgpu_link.py' \
        <"$HERE/mgpu_link.py" >"$log" 2>&1
}

probe() {
    local p2p=$1 log via
    log=$(mktemp)
    if ! retry3 probe_once "$log" "$p2p"; then
        emit refused "p2p-link-$p2p" "p2p=$p2p" checkpoint_quant=none "tries=$RUN_TRIES" \
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
    label = f"p2p-link-{p2p}" + (f" gpu={doc['gpu']}" if "gpu" in doc else "")
    label += f" bytes={doc['bytes']}" if "bytes" in doc else ""
    fields = [f"p2p={p2p}", f"nccl_via={via}"]
    fields += [f"{k}={str(v).replace(' ', '_')}" for k, v in doc.items()]
    print("\t".join([host, label, kind, *fields]))
PY
    rm -f "$log"
}

emit rig_stamp
say "link probe, NCCL's own choice"
probe on
say "link probe, NCCL_P2P_DISABLE=1"
probe off

emit rig_stamp
say "vllm: 6 cells"
emit _py "$DRIVER" vllm \
    "p7-g0:$V:g0:on:$VL:@knob" \
    "p7-tp2-check:$V:tp2:on:$VL:@knob+@VLLM_SKIP_P2P_CHECK=0" \
    "p7-tp2:$V:tp2:on:$VL:@knob" \
    "p7-tp2-nocar:$V:tp2:on:$VL:@knob+--disable-custom-all-reduce" \
    "p7-tp2-p2poff:$V:tp2:off:$VL:@knob" \
    "p7-dp2:$V:dp2:on:$VL:@knob"

emit rig_stamp
say "llama.cpp: 8 cells"
emit _py "$DRIVER" lcp \
    "pl14-g0:$M14:g0:$LL:@knob" \
    "pl14-layer:$M14:layer:$LL:@knob" \
    "pl14-tensor:$M14:tensor:$LL:@knob" \
    "pl14-tensor-ar-nccl:$M14:tensor:$LL:@knob+@GGML_CUDA_ALLREDUCE=nccl" \
    "pl14-tensor-ar-internal:$M14:tensor:$LL:@knob+@GGML_CUDA_ALLREDUCE=internal" \
    "pl14-layer-p2p:$M14:layer:$LL:@knob+@GGML_CUDA_P2P=1" \
    "pl14-tensor-p2p:$M14:tensor:$LL:@knob+@GGML_CUDA_P2P=1" \
    "pl7-tensor:$M7:tensor:built:2048:1,4:@knob"

close_tsv
say "wrote $OUT"
