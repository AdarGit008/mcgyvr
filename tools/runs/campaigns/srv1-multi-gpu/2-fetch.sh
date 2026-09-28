#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/2-fetch.sh — step 2: the vLLM checkpoints
# step 3 serves, put in srv1's HF cache BEFORE the sweep, so no cell spends its
# launch downloading (the driver runs with HF_HUB_OFFLINE=1 and refuses a
# checkpoint that is not already there).
#
# 1.5B and 7B AWQ are already on srv1 (records/evidence/2026-08-31-inventory/
# srv1-scan.txt); 14B (~10 GiB) and 32B (~19 GiB) are the two that make the
# size axis, and the 32B is the one that needs both cards. `hf download` is
# idempotent, so a checkpoint already whole costs a manifest check.
#
# Refused before any download when the cache's filesystem has less than
# NEED_GIB free.
#
# RUN_ARTIFACTS: fetch.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/2-fetch.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "2-fetch.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/2-fetch.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

IMG="vllm/vllm-openai:v0.26.0"
NAME="$RUN_ID-fetch"
NEED_GIB=40
REPOS=(
    Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ
    Qwen/Qwen2.5-Coder-7B-Instruct-AWQ
    Qwen/Qwen2.5-Coder-14B-Instruct-AWQ
    Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
)

mgpu_preamble fetch.tsv
DIGEST=$(image_digest "$IMG") || { _fail "$IMG resolves to no digest on $RUN_HOST" || true; exit 1; }
trap '"$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

open_tsv microbench_stamp

free_b=$("$SSH" "$RUN_HOST" 'mkdir -p "$HOME/.cache/huggingface" && df -B1 --output=avail "$HOME/.cache/huggingface" | tail -1' </dev/null | tr -d ' ')
emit row host DISK "hf_cache_free_gib=$((free_b / 2**30))"
if [ "$free_b" -lt $((NEED_GIB * 2**30)) ]; then
    for repo in "${REPOS[@]}"; do
        emit refused "fetch $repo" "repo=$repo" checkpoint_quant=unread tries=3 \
            -- "the HF cache filesystem on $RUN_HOST has $((free_b / 2**30)) GiB free and the fetch needs $NEED_GIB GiB; nothing was downloaded, so the checkpoint's quantization_config was never read"
    done
    close_tsv
    exit 1
fi

fetch_once() {
    "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
    "$DOCKER" run --rm --name "$NAME" \
        -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
        ${HF_TOKEN:+-e HF_TOKEN} \
        --entrypoint bash "$DIGEST" -c \
        'command -v hf >/dev/null && exec hf download "$1" --include "*.json" "*.safetensors" "*.txt" "*.model"; exec huggingface-cli download "$1" --include "*.json" "*.safetensors" "*.txt" "*.model"' \
        fetch "$1" >/dev/null
}

for repo in "${REPOS[@]}"; do
    say "fetching $repo"
    if retry3 fetch_once "$repo"; then
        dir="models--${repo//\//--}"
        bytes=$("$SSH" "$RUN_HOST" "du -sLb \"\$HOME/.cache/huggingface/hub/$dir/snapshots\" | cut -f1" </dev/null)
        quant=$("$SSH" "$RUN_HOST" "cat \"\$HOME\"/.cache/huggingface/hub/$dir/snapshots/*/config.json" </dev/null |
            _py -c 'import json, sys; print(json.load(sys.stdin).get("quantization_config", {}).get("quant_method", "none"))' || echo unread)
        emit row "fetch $repo" FETCH "repo=$repo" "bytes=$bytes" "quant_method=$(_tok "$quant")" "tries=$RUN_TRIES"
    else
        emit refused "fetch $repo" "repo=$repo" checkpoint_quant=unread "tries=$RUN_TRIES" \
            -- "hf download of $repo into $RUN_HOST's HF cache failed on every try; the checkpoint's quantization_config was never read"
    fi
done

close_tsv
say "wrote $OUT"
