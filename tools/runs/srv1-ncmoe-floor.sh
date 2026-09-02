#!/usr/bin/env bash
# tools/runs/srv1-ncmoe-floor.sh — campaign step 9, behaviour 9.
#
# Emits records/evidence/2026-09-02-srv1-kernel-arms/srv1-ncmoe-floor.tsv, read
# by tests/test_an_ncmoe_floor_is_derived_and_not_copied.py through
# tests/sweeprows.py. The shapes below are ARTIFACT-CONTRACT.md sections 2.8
# and 5.7.
#
# WHAT THIS MEASURES. --n-cpu-moe is the number of layers whose expert tensors
# stay in host RAM. The floor -- the smallest value that still loads -- is
# VRAM-bound, and every arm in this campaign carries a different VRAM overhead
# (a Vulkan allocator is not a CUDA one; a PTX-only context is not a SASS one).
# So each arm DERIVES its own floor from its own six readings, and a floor
# copied from a sibling arm is not a floor. The derivation is:
#
#     budget    = usable_mib - cuda_ctx_mib - nonexpert_mib - kv_mib
#     resident  = budget / expert_total_mib
#     predicted = (1 - resident) * n_layers
#
# Every one of the six inputs is read off THIS arm's own probe launch. The
# arithmetic is the test's own (test_an_ncmoe_floor_...:44-56), recomputed here
# from the same strings the stamp carries, so the two cannot drift.
#
# WHAT ESTABLISHES IT. "predicted" is arithmetic. "measured" is a launch, and
# what makes it a floor is the REFUSED row one step BELOW it: descent until
# refusal (guideline 8 -- a refusal is a result). A refusal is believed only
# after three attempts, through retry3, because a launch near the memory edge is
# a 1-in-3 coin flip, and two REFUSED rows on 2026-09-01 turned out to be a
# dangling HF-blob symlink read as a capability limit.
#
# SCOPE -- this is step 9, not the kernel grid. lcp-vllm-3-arm-run.md's "Not
# worth rig time" list rules out ncmoe cells for the *kernel* question, because
# the bottleneck moves to host RAM and srv1 hard-locks under that load. So:
#   * no serving sweep, no width ladder, no replicates. Every cell here is one
#     model LOAD (--no-warmup, health, read the log, kill). Nothing is driven
#     under load, which is the state that locks the host.
#   * the probe runs at maximum offload -- the smallest VRAM footprint the arm
#     has, so it cannot itself be refused for want of VRAM -- and it alone
#     yields all six inputs. Every arm is probed BEFORE any descent, so a lock
#     during a descent still leaves every arm's derivation on disk (### PREDICT).
#   * the descent is capped at --max-steps (default 4) launches per arm.
# Worst case per arm: 1 probe + 1 start + 4 steps = 6 launches.
#
# SURVIVABILITY. Every marker and every row is appended the moment it is
# produced -- one open/append/close per line, nothing buffered -- so a hard lock
# mid-run loses only the cell it was in. A hard lock also wipes the BIOS power
# profile (srv1 read PL1 95 W at 05:23 and 4095 W at 05:57 on one boot), so
# rig_assert_unchanged failing at the end is a REAL FINDING about the machine
# rather than a script fault. It is reported as one, marked in the file, and
# exits 3.
#
# Usage:
#   tools/runs/srv1-ncmoe-floor.sh --model /path/to/moe.gguf [options]
#
#   --model PATH        GGUF to derive the floor for. Required, no default.
#   --arm ARM=IMG       repeatable; default L3=llamacpp:b10644-L3 and
#                       A3=llamacpp:b10644-A3. ARM must match [ABL][0-9].
#   --cell NAME         label cell (default: derived from the model filename).
#   --start-ncmoe K     begin the descent at K instead of ceil(predicted).
#   --max-steps N       cap on descent launches per arm (default 4).
#   --np N              --parallel (default 1: this loads, it does not serve).
#   --ctx-slot N        per-slot context (default 4096).
#   --port N            host port for the container (default 8094).
#   --out-dir DIR       artifact directory (default: the run's evidence dir).
#   --dry-run           print every cell's exact command line, run nothing.

set -euo pipefail

HERE=$(cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(cd -- "$HERE/../.." && pwd)
# shellcheck source=tools/runs/_common.sh disable=SC1091
. "$HERE/_common.sh"

OUT_DIR="$ROOT/records/evidence/2026-09-02-srv1-kernel-arms"
OUT_NAME=srv1-ncmoe-floor.tsv
MODEL=
CELL=
START_NCMOE=
MAX_STEPS=4
NP=1
CTX_SLOT=4096
PORT=8094
DRY_RUN=0
CONTAINER=lcp-ncmoe-floor
HEALTH_TRIES=90
OFFLOAD_ALL=99
ARMS=()

die() {
    printf 'srv1-ncmoe-floor: %s\n' "$*" >&2
    exit 2
}

say() {
    printf '# %s\n' "$*" >&2
}

while [ "$#" -gt 0 ]; do
    case $1 in
        --model) MODEL=${2:?--model needs a path}; shift 2 ;;
        --arm) ARMS+=("${2:?--arm needs ARM=IMG}"); shift 2 ;;
        --cell) CELL=${2:?--cell needs a name}; shift 2 ;;
        --start-ncmoe) START_NCMOE=${2:?--start-ncmoe needs an integer}; shift 2 ;;
        --max-steps) MAX_STEPS=${2:?--max-steps needs an integer}; shift 2 ;;
        --np) NP=${2:?--np needs an integer}; shift 2 ;;
        --ctx-slot) CTX_SLOT=${2:?--ctx-slot needs an integer}; shift 2 ;;
        --port) PORT=${2:?--port needs an integer}; shift 2 ;;
        --out-dir) OUT_DIR=${2:?--out-dir needs a path}; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h | --help) sed -n '52,65p' "$0"; exit 0 ;;
        *) die "unknown argument '$1'" ;;
    esac
done

[ -n "$MODEL" ] || die "no --model. This derives a floor for a real checkpoint; there is no default, because a wrong path would be measured silently."
if [ "${#ARMS[@]}" -eq 0 ]; then
    ARMS=("L3=llamacpp:b10644-L3" "A3=llamacpp:b10644-A3")
fi
for _n in "MAX_STEPS=$MAX_STEPS" "NP=$NP" "CTX_SLOT=$CTX_SLOT" "PORT=$PORT" "START_NCMOE=${START_NCMOE:-0}"; do
    case ${_n#*=} in
        '' | *[!0-9]*) die "--${_n%%=*} is '${_n#*=}', which is not an integer" ;;
    esac
done

MODEL_DIR=$(cd -- "$(dirname -- "$MODEL")" 2>/dev/null && pwd) || MODEL_DIR=$(dirname -- "$MODEL")
MODEL_BASE=$(basename -- "$MODEL")
CONTAINER_MODEL="/models/$MODEL_BASE"
if [ -z "$CELL" ]; then
    CELL=$(printf '%s' "${MODEL_BASE%.gguf}" | tr '[:upper:]' '[:lower:]' |
        tr -c 'a-z0-9' '-' | sed -e 's/-\{1,\}/-/g' -e 's/^-//' -e 's/-$//')
fi
[ -n "$CELL" ] || die "the cell name derived from '$MODEL_BASE' is empty; pass --cell"

CTX_TOTAL=$((CTX_SLOT * NP))
OUT="$OUT_DIR/$OUT_NAME"

# --------------------------------------------------------------------------
# emission -- one append per line, so a hard lock keeps what was measured
# --------------------------------------------------------------------------

# stamp/row/refused validate everything before their single printf, so a
# rejected line appends nothing. The callee runs in THIS shell (a redirection
# forks nothing), which is what keeps start_stamp's reading available to
# rig_assert_unchanged at the end.
emit() {
    "$@" >>"$OUT"
}

label_for() {
    local arm=$1 ncmoe=$2 base
    base=$(arm_label "$arm" "$CELL") || return 1
    printf '%s np=%s ctx_slot=%s c=%s ncmoe=%s' "$base" "$NP" "$CTX_SLOT" "$CTX_TOTAL" "$ncmoe"
}

# --------------------------------------------------------------------------
# the launch -- one model load, health, log, kill. It never serves a request.
#
# `-lv 5` IS PART OF THE INSTRUMENT, not a debugging convenience. Every one of
# the six derivation inputs below is read out of this launch's own log:
# `print_info: n_layer`, `load_tensors: CUDA0 model buffer size`,
# `load_tensors: CPU_Mapped model buffer size`, `llama_kv_cache: CUDA0 KV
# buffer size` and `print_info: file type`. b10644's llama-server prints NONE
# of them at its default verbosity -- measured on srv1 2026-09-02, where the
# whole default-verbosity log is fourteen lines and carries no model metadata
# at all -- so without this flag the script correctly refuses every arm with
# "n_layers could not be read". Raising the verbosity makes the values
# READABLE; it does not supply them, and nothing here is substituted when a
# line is still absent.
# --------------------------------------------------------------------------

DOCKER_ARGV=()
launch_argv() {
    local img=$1 ncmoe=$2
    DOCKER_ARGV=(
        docker run -d --name "$CONTAINER" --runtime=nvidia --gpus all
        -v "$MODEL_DIR:/models" -p "$PORT:$PORT" "$img"
        -m "$CONTAINER_MODEL" --host 0.0.0.0 --port "$PORT"
        --parallel "$NP" -c "$CTX_TOTAL" -ngl 99 --n-cpu-moe "$ncmoe" --no-warmup
        -lv 5
    )
}

launch_cmd() {
    launch_argv "$1" "$2"
    printf '%q ' "${DOCKER_ARGV[@]}"
    printf '\n'
}

LAUNCH_LOG=
launch_once() {
    local img=$1 ncmoe=$2 i code
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    [ -z "$LAUNCH_LOG" ] || rm -f "$LAUNCH_LOG"
    LAUNCH_LOG=$(mktemp)
    launch_argv "$img" "$ncmoe"
    if ! "${DOCKER_ARGV[@]}" >/dev/null 2>>"$LAUNCH_LOG"; then
        docker logs "$CONTAINER" >>"$LAUNCH_LOG" 2>&1 || true
        return 1
    fi
    i=0
    while [ "$i" -lt "$HEALTH_TRIES" ]; do
        i=$((i + 1))
        code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" || true)
        if [ "$code" = "200" ]; then
            docker logs "$CONTAINER" >>"$LAUNCH_LOG" 2>&1 || true
            return 0
        fi
        if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
            break
        fi
        sleep 2
    done
    docker logs "$CONTAINER" >>"$LAUNCH_LOG" 2>&1 || true
    return 1
}

teardown() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

# --------------------------------------------------------------------------
# reading the launch. Every value is parsed or the run stops: this file never
# substitutes a placeholder for a number it could not read.
# --------------------------------------------------------------------------

log_last_line() {
    grep -v '^[[:space:]]*$' "$LAUNCH_LOG" 2>/dev/null | tail -n 1 | tr '\t' ' ' | cut -c1-200
}

sum_mib() {
    # Sums the `... = <MiB>` figure on every line holding both markers.
    awk -v a="$2" -v b="$3" '
        index($0, a) && index($0, b) {
            for (i = 1; i <= NF; i++) if ($i == "=") { s += $(i + 1) + 0; break }
        }
        END { if (s > 0) printf "%.2f", s }
    ' "$1"
}

gpu_process_mib() {
    nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits 2>/dev/null |
        awk '{ s += $1 + 0 } END { if (s > 0) printf "%d", s }'
}

# --------------------------------------------------------------------------
# dry run -- every cell's exact command line, nothing executed
# --------------------------------------------------------------------------

if [ "$DRY_RUN" -eq 1 ]; then
    printf '# srv1-ncmoe-floor.sh --dry-run\n'
    printf '# artifact, appended one line at a time: %s\n' "$OUT"
    printf '# model %s / cell %s / np=%s ctx_slot=%s c=%s / max-steps %s\n' \
        "$MODEL" "$CELL" "$NP" "$CTX_SLOT" "$CTX_TOTAL" "$MAX_STEPS"
    for spec in "${ARMS[@]}"; do
        arm=${spec%%=*}
        img=${spec#*=}
        printf '\n## arm %s (%s)\n' "$arm" "$img"
        printf '# probe: maximum offload, the arm smallest VRAM footprint, and the\n'
        printf '#   one launch that yields all six derivation inputs.\n'
        launch_cmd "$img" "$OFFLOAD_ALL"
        printf 'nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits\n'
        printf 'docker logs %s\n' "$CONTAINER"
        printf 'docker rm -f %s\n' "$CONTAINER"
        if [ -n "$START_NCMOE" ]; then
            k=$START_NCMOE
            step=0
            while [ "$step" -le "$MAX_STEPS" ] && [ "$k" -ge 0 ]; do
                printf '# descent step %s (--start-ncmoe %s was given, so this is exact)\n' \
                    "$step" "$START_NCMOE"
                launch_cmd "$img" "$k"
                k=$((k - 1))
                step=$((step + 1))
            done
        else
            printf '# descent: the same command line with --n-cpu-moe K, for K =\n'
            printf '#   ceil(predicted), K-1, ... until a REFUSED launch or %s steps,\n' "$MAX_STEPS"
            printf '#   whichever comes first. K is DERIVED from the probe above and so\n'
            printf '#   is not printable off-rig; pass --start-ncmoe K to enumerate it.\n'
            printf '#   Each failing launch is attempted 3x (retry3) before it is believed.\n'
            launch_cmd "$img" 'K'
        fi
    done
    exit 0
fi

# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

mkdir -p "$OUT_DIR"
trap teardown EXIT

say "artifact: $OUT"
emit start_stamp
emit rig_stamp

SNAP=$(rig_snapshot)
GPU_TOTAL=$(printf '%s\n' "$SNAP" | sed -n 's/^gpu_vram_mib=//p' | head -n 1)
GPU_RESERVE=$(printf '%s\n' "$SNAP" | sed -n 's/^gpu_reserve_mib=//p' | head -n 1)
case ${GPU_TOTAL:-} in '' | *[!0-9]*) die "gpu_vram_mib read as '${GPU_TOTAL:-}'" ;; esac
case ${GPU_RESERVE:-} in '' | *[!0-9]*) die "gpu_reserve_mib read as '${GPU_RESERVE:-}'" ;; esac
USABLE=$((GPU_TOTAL - GPU_RESERVE))
[ "$USABLE" -gt 0 ] || die "usable_mib computed as $USABLE from total=$GPU_TOTAL reserve=$GPU_RESERVE"

# Probes first, for every arm, before any descent: a lock during a descent then
# still leaves each arm's whole derivation on disk.
ARM_LIST=()
declare -A A_IMG A_NONEXPERT A_EXPERT A_KV A_CTX A_LAYERS A_QUANT A_PRED
for spec in "${ARMS[@]}"; do
    arm=${spec%%=*}
    img=${spec#*=}
    [ "$arm" != "$spec" ] || die "--arm '$spec' is not ARM=IMG"
    say "probe: arm $arm at maximum offload"
    if ! launch_once "$img" "$OFFLOAD_ALL"; then
        die "arm $arm refused the probe launch (--n-cpu-moe $OFFLOAD_ALL), the smallest VRAM footprint this arm has. Nothing below it can be derived. Last log line: $(log_last_line)"
    fi
    layers=$(sed -n 's/.*n_layer[[:space:]]*=[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$LAUNCH_LOG" | head -n 1)
    nonexpert=$(sum_mib "$LAUNCH_LOG" "CUDA0" "model buffer size")
    expert=$(sum_mib "$LAUNCH_LOG" "CPU" "model buffer size")
    kv=$(sum_mib "$LAUNCH_LOG" "KV self size" "=")
    [ -n "$kv" ] || kv=$(sum_mib "$LAUNCH_LOG" "KV buffer size" "=")
    quant=$(_tok "$(sed -n 's/.*file type[[:space:]]*=[[:space:]]*\(.*\)/\1/p' "$LAUNCH_LOG" | head -n 1)")
    used=$(gpu_process_mib)
    teardown
    for pair in "n_layers:$layers" "nonexpert_mib:$nonexpert" "expert_total_mib:$expert" \
        "kv_mib:$kv" "checkpoint_quant:$quant" "gpu_process_mib:$used"; do
        [ -n "${pair#*:}" ] || die "arm $arm: ${pair%%:*} could not be read from the probe launch's own log. A derivation with an unread input is not a derivation, and nothing is substituted for it. Log tail: $(log_last_line)"
    done
    # The arm's fixed CUDA overhead: what the process holds on the card beyond
    # the two buffers the engine itself reported -- context, compute buffers and
    # allocator slack. It is exactly the term that differs between arms.
    ctx=$(awk -v u="$used" -v m="$nonexpert" -v k="$kv" 'BEGIN { printf "%.2f", u - m - k }')
    case $ctx in
        -*) die "arm $arm: cuda_ctx_mib computed negative ($ctx MiB) from process VRAM $used, model $nonexpert, KV $kv. Those three readings do not describe one launch, so nothing is emitted rather than a number that cannot be true." ;;
    esac
    pred=$(awk -v u="$USABLE" -v c="$ctx" -v m="$nonexpert" -v k="$kv" -v e="$expert" -v n="$layers" \
        'BEGIN { printf "%.1f", (1 - ((u - c - m - k) / e)) * n }')
    ARM_LIST+=("$arm")
    A_IMG[$arm]=$img
    A_NONEXPERT[$arm]=$nonexpert
    A_EXPERT[$arm]=$expert
    A_KV[$arm]=$kv
    A_CTX[$arm]=$ctx
    A_LAYERS[$arm]=$layers
    A_QUANT[$arm]=$quant
    A_PRED[$arm]=$pred
    emit row "$(label_for "$arm" "$OFFLOAD_ALL")" CONFIG "arm=$arm" "img=$img" \
        "vram=$used" "n_layers=$layers" "nonexpert_mib=$nonexpert" \
        "expert_total_mib=$expert" "kv_mib=$kv" "cuda_ctx_mib=$ctx" \
        "usable_mib=$USABLE" "checkpoint_quant=$quant"
    # On disk before the descent spends a single launch: if srv1 locks below,
    # the derivation survives and only "measured" is missing.
    emit stamp PREDICT "arm=$arm" "usable_mib=$USABLE" "cuda_ctx_mib=$ctx" \
        "nonexpert_mib=$nonexpert" "kv_mib=$kv" "expert_total_mib=$expert" \
        "n_layers=$layers" "predicted=$pred"
done

# The descent. "predicted" is arithmetic; the floor is a launch, and what makes
# it a floor is the refusal one step below it.
for arm in "${ARM_LIST[@]}"; do
    img=${A_IMG[$arm]}
    pred=${A_PRED[$arm]}
    layers=${A_LAYERS[$arm]}
    if [ -n "$START_NCMOE" ]; then
        k=$START_NCMOE
    else
        k=$(awk -v p="$pred" 'BEGIN { k = int(p); if (p > k) k += 1; if (k < 0) k = 0; printf "%d", k }')
    fi
    [ "$k" -le "$layers" ] || k=$layers
    say "descent: arm $arm from --n-cpu-moe $k (predicted $pred, at most $MAX_STEPS further steps)"
    measured=
    climbing=0
    step=0
    while [ "$step" -le "$MAX_STEPS" ]; do
        step=$((step + 1))
        if retry3 launch_once "$img" "$k"; then
            used=$(gpu_process_mib)
            teardown
            emit row "$(label_for "$arm" "$k")" CONFIG "arm=$arm" "img=$img" \
                "vram=${used:-0}" "tries=$RUN_TRIES"
            measured=$k
            if [ "$climbing" -eq 1 ]; then
                break
            fi
            if [ "$k" -eq 0 ]; then
                say "arm $arm loads at --n-cpu-moe 0, so the floor is 0 and there is no cell below it to refuse. No REFUSED row: none was measured."
                break
            fi
            k=$((k - 1))
            continue
        fi
        reason="0 refused: arm $arm would not load at --n-cpu-moe $k after $RUN_TRIES launch attempts; last log line: $(log_last_line)"
        teardown
        emit refused "$(label_for "$arm" "$k")" "arm=$arm" "img=$img" \
            "checkpoint_quant=${A_QUANT[$arm]}" "tries=$RUN_TRIES" -- "$reason"
        if [ -n "$measured" ]; then
            break
        fi
        # The starting cell refused, so the floor is above it. Climb until one
        # loads: that first success is the floor, and this refusal is under it.
        climbing=1
        k=$((k + 1))
    done
    if [ -z "$measured" ]; then
        say "arm $arm: no launch loaded inside the step cap. No ### FLOOR is stamped for it -- a floor nothing reached is not a floor, and a stamped measured= would be the one thing this file must never carry."
        continue
    fi
    emit stamp FLOOR "arm=$arm" "usable_mib=$USABLE" "cuda_ctx_mib=${A_CTX[$arm]}" \
        "nonexpert_mib=${A_NONEXPERT[$arm]}" "kv_mib=${A_KV[$arm]}" \
        "expert_total_mib=${A_EXPERT[$arm]}" "n_layers=${A_LAYERS[$arm]}" \
        "predicted=${A_PRED[$arm]}" "measured=$measured"
done

emit end_stamp
if ! rig_assert_unchanged; then
    emit stamp RIGMOVED at=end
    printf 'srv1-ncmoe-floor: THE RIG MOVED UNDER THIS RUN. That is a FINDING, not a script fault: a hard lock wipes the BIOS power profile, and srv1 has already read PL1 95 W at 05:23 and 4095 W at 05:57 on one boot. The rows above were not all produced under one machine state. Report the START/END pair as measured; do not re-run over this file until the profile is restored.\n' >&2
    exit 3
fi
say "done: $OUT"
