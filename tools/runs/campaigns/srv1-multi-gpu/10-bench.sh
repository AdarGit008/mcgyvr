#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/10-bench.sh — step 10: llama-bench,
# prefill and decode measured apart, across the settings the serving steps
# cannot hold still: physical batch, KV type, and depth into the context.
#
#   model   Qwen2.5-Coder-7B IQ4_XS, 14B Q4_K_M
#   split   none on card 0 (`--gpus device=0`), layer, tensor (both cards).
#           row is gone: b10644 refuses it for every model (step 4)
#   sets    q8   -ub 128,512,2048 -ctk q8_0 -ctv q8_0
#           f16  -ub 512 -ctk f16 -ctv f16
#   bench   -p 512 -n 128 -d 0,8192 -r 3 -fa 1 -ngl 99 -o jsonl
#
# -d 8192 is the same pp512/tg128 run 8k tokens into a filled context: what a
# long conversation costs each split, apart from the prompt that filled it.
#
# BENCH rows carry what llama-bench REPORTS having run: `reps` is counted from
# its sample array, `backends` and `split_mode` are its own fields. A config
# that does not fit exits non-zero; three tries, then a REFUSED row.
#
# RUN_ARTIFACTS: bench.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/10-bench.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "10-bench.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/10-bench.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../../_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required
# shellcheck source=./_mgpu.sh disable=SC1091
. "$HERE/_mgpu.sh"

NAME="$RUN_ID-bench"
MODELS=(
    "7b=/models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf"
    "14b=/models/dense/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf"
)
# name  --gpus  llama-bench split flags
SPLITS=(
    "g0|device=0|-sm none -mg 0"
    "layer|all|-sm layer"
    "tensor|all|-sm tensor"
)
BENCH_ARGS=(-p 512 -n 128 -d 0,8192 -r 3 -fa 1 -ngl 99 -o jsonl)
# set name  its llama-bench words
SETS=(
    "q8|-ub 128,512,2048 -ctk q8_0 -ctv q8_0"
    "f16|-ub 512 -ctk f16 -ctv f16"
)

mgpu_preamble bench.tsv
IMG=$(_py -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]["llamacpp_image"])' \
    "$RUN_ROOT/tools/runs/hosts.json" "$RUN_HOST") || { _fail "hosts.json names no llamacpp_image for $RUN_HOST" || true; exit 2; }
DIGEST=$(image_digest "$IMG") || { _fail "$IMG resolves to no digest on $RUN_HOST" || true; exit 1; }
trap '"$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

# The entry point: /app/llama-bench, or the /app/llama dispatcher's `bench`
# (srv1-kernel-arms/3-llama-bench.sh found images shipping only the latter).
ENTRY=()
if "$DOCKER" run --rm --entrypoint test "$DIGEST" -x /app/llama-bench; then
    ENTRY=(--entrypoint /app/llama-bench "$DIGEST")
elif "$DOCKER" run --rm --entrypoint /app/llama "$DIGEST" help all 2>/dev/null | grep -qE '^[[:space:]]+bench[[:space:]]'; then
    ENTRY=(--entrypoint /app/llama "$DIGEST" bench)
fi

open_tsv microbench_stamp
emit stamp TOOL name=llama-bench "img=$IMG"

if [ "${#ENTRY[@]}" -eq 0 ]; then
    emit refused "bench" checkpoint_quant=none tries=3 \
        -- "$IMG ships neither /app/llama-bench nor an /app/llama dispatcher that lists bench, so nothing was benched"
    close_tsv
    exit 1
fi

bench_once() {
    local out=$1 gpus=$2 model=$3
    shift 3
    "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
    "$DOCKER" run --rm --name "$NAME" --gpus "$gpus" -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
        -v "$HOME/models:/models:ro" "${ENTRY[@]}" -m "$model" "$@" "${BENCH_ARGS[@]}" >"$out" 2>"$out.err"
}

for entry in "${MODELS[@]}"; do
    size=${entry%%=*}
    model=${entry#*=}
    emit rig_stamp
    for spec in "${SPLITS[@]}"; do
      for set in "${SETS[@]}"; do
        IFS='|' read -r split gpus flags <<<"$spec"
        kv=${set%%|*}
        flags="$flags ${set#*|}"
        label="b$size-$split-$kv"
        out=$(mktemp)
        say "$label"
        # shellcheck disable=SC2086  # $flags is split into llama-bench words
        if retry3 bench_once "$out" "$gpus" "$model" $flags; then
            _py - "$out" "$label" "$split" "$model" <<'PY' >>"$OUT"
import json
import os
import sys

path, label, split, model = sys.argv[1:5]
host = os.environ["RUN_HOST"]
for line in open(path, encoding="utf-8"):
    line = line.strip()
    if not line.startswith("{"):
        continue
    d = json.loads(line)
    test = f"pp{d['n_prompt']}" if d["n_prompt"] else f"tg{d['n_gen']}"
    test += f"@d{d.get('n_depth', 0)}+ub{d.get('n_ubatch', 'unread')}"
    fields = [
        f"split={split}",
        f"model={model.rsplit('/', 1)[-1]}",
        f"test={test}",
        f"ts={d['avg_ts']:.2f}",
        f"stddev={d['stddev_ts']:.2f}",
        f"reps={len(d.get('samples_ts') or [])}",
        f"backends={d.get('backends', 'unread')}",
        f"split_mode={d.get('split_mode', 'unread')}",
        f"main_gpu={d.get('main_gpu', 'unread')}",
        f"type_k={d.get('type_k', 'unread')}",
        f"n_ubatch={d.get('n_ubatch', 'unread')}",
        f"n_depth={d.get('n_depth', 'unread')}",
        f"tensor_split={str(d.get('tensor_split', 'unread')).replace(' ', '')}",
        f"gpu_info={str(d.get('gpu_info', 'unread')).replace(' ', '_')}",
    ]
    print("\t".join([host, f"{label} {test}", "BENCH", *fields]))
PY
        else
            emit refused "$label" "split=$split" "model=$(basename "$model")" checkpoint_quant=unread "tries=$RUN_TRIES" \
                -- "llama-bench exited non-zero on every try, and a GGUF's quant is read from its header only when it loads: $(tail -3 "$out.err" | tr '\n\t' '  ' | cut -c1-300)"
        fi
        rm -f "$out" "$out.err"
      done
    done
done

close_tsv
say "wrote $OUT"
