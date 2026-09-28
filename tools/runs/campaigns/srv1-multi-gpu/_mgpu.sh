# shellcheck shell=bash
# tools/runs/campaigns/srv1-multi-gpu/_mgpu.sh — what every step of this
# campaign shares, sourced after tools/runs/_common.sh. Executes nothing.
#
#   mgpu_preamble ARTIFACT   the refusals every step makes before it writes:
#                            the host is srv1, and srv1 shows exactly two cards.
#                            Sets OUT, DOCKER, SSH.
#   emit CMD...              CMD's stdout appended to OUT
#   say TEXT...              progress on stderr, never in the artifact
#   open_tsv WORKLOAD_FN     the stamps a door-produced TSV opens with, and one
#                            GPU row per card
#   close_tsv                ### END, then the start==end comparison
#
# THE CARDS ARE READ, NOT DECLARED. hosts.json[srv1].rig describes one card
# (gate 2 reads nvidia-smi's first line only), and which two cards are in the
# box is the owner's call. Every step files both cards' identity as GPU rows,
# so a row is never read against a pair it was not measured on.

OUT=""
DOCKER=""
SSH=""

say() { printf 'srv1-multi-gpu: %s\n' "$*" >&2; }

emit() { "$@" >>"$OUT"; }

mgpu_preamble() {
    local artifact=$1 count
    DOCKER=$(_door_shim docker) || exit 2
    SSH=$(_door_shim ssh) || exit 2
    OUT="$RUN_OUT_DIR/$artifact"
    [ "$RUN_HOST" = srv1 ] || { _fail "REFUSED — this campaign is srv1's, and the run is on $RUN_HOST" || true; exit 2; }
    count=$("$SSH" "$RUN_HOST" 'nvidia-smi --query-gpu=index --format=csv,noheader | wc -l' </dev/null) ||
        { _fail "REFUSED — $RUN_HOST's cards could not be counted" || true; exit 2; }
    [ "$count" = 2 ] || { _fail "REFUSED — $RUN_HOST shows $count cards; this campaign measures two" || true; exit 2; }
}

# One GPU row per card: what the pair IS for every row below it.
gpu_rows() {
    "$SSH" "$RUN_HOST" 'nvidia-smi --query-gpu=index,name,pci.bus_id,memory.total,compute_cap,power.limit,pcie.link.gen.max,pcie.link.width.max,driver_version --format=csv,noheader,nounits' </dev/null |
        while IFS=, read -r idx name bus total cc plimit gmax wmax drv; do
            row "gpu$(_tok "$idx")" GPU \
                "index=$(_tok "$idx")" "name=$(_tok "$name")" "bus=$(_tok "$bus")" \
                "vram_mib=$(_tok "$total")" "cc=$(_tok "$cc")" "power_limit_w=$(_tok "$plimit")" \
                "pcie_gen_max=$(_tok "$gmax")" "pcie_width_max=$(_tok "$wmax")" "driver=$(_tok "$drv")"
        done
}

# The two compute capabilities, space-separated, in index order.
card_ccs() {
    "$SSH" "$RUN_HOST" 'nvidia-smi --query-gpu=compute_cap --format=csv,noheader' </dev/null | tr -d ' ' | paste -sd' ' -
}

open_tsv() {
    : >"$OUT"
    emit "$@"
    emit start_stamp
    emit round_stamp
    emit rig_stamp
    emit gpu_rows
}

close_tsv() {
    emit end_stamp
    rig_assert_unchanged
}

# mgpu_serve ARTIFACT ENGINE CELL...   one serving step end to end: the image
# (vllm: vllm/vllm-openai:v0.26.0; lcp: hosts.json's llamacpp_image) resolved
# once to a digest, the driver's containers removed on any exit, the TSV
# opened and closed around one driver run. Cells are mgpu_sweep.py's format.
mgpu_serve() {
    local artifact=$1 engine=$2 img digest
    shift 2
    mgpu_preamble "$artifact"
    if [ "$engine" = vllm ]; then
        img="vllm/vllm-openai:v0.26.0"
    else
        img=$(_py -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]["llamacpp_image"])' \
            "$RUN_ROOT/tools/runs/hosts.json" "$RUN_HOST") || { _fail "hosts.json names no llamacpp_image for $RUN_HOST" || true; exit 2; }
    fi
    digest=$(image_digest "$img") || { _fail "$img resolves to no digest on $RUN_HOST" || true; exit 1; }
    if [ "$engine" = vllm ]; then export VLLM_IMG="$digest"; else export LCP_IMG="$digest"; fi
    trap '"$DOCKER" rm -f "$RUN_ID-mgpu-a" "$RUN_ID-mgpu-b" >/dev/null 2>&1 || true' EXIT
    open_tsv workload_stamp tools/runs/workload.py
    emit stamp NOTE "image=$img"
    say "$engine: $# cells"
    emit rig_stamp
    emit _py tools/runs/drivers/mgpu_sweep.py "$engine" "$@"
    close_tsv
    say "wrote $OUT"
}
