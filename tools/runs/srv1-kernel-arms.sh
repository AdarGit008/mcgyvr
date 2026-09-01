#!/usr/bin/env bash
# tools/runs/srv1-kernel-arms.sh — steps 4 (serve) and 7 (crash) of the srv1
# kernel-arms run (`lcp-vllm-3-arm-run.md:111-128`), written against
# `records/evidence/2026-09-02-srv1-kernel-arms/ARTIFACT-CONTRACT.md`.
#
# It drives `lcp_sweep_31-08-2026.py` — the workload the whole campaign shares —
# and prints the contract's rows around it. It never invents a number: every
# field it adds is either read from the rig, read from the engine log, or
# replayed from the driver's own prompt generator.
#
# TWO ARTIFACTS, and the reason:
#
#   srv1-lcpp-arms.tsv   step 4. The llama.cpp arms at n=1,4,8 on resident
#                        models, five replicates, INTERLEAVED at cell
#                        granularity (guideline 1). ONE CELL PER PROCESS
#                        INVOCATION (guideline 2).
#   srv1-moe-slots.tsv   step 7. L2's crash boundary over n=1..12, then L3 for
#                        60 trials at every width L2 actually died on.
#
#   ONE FILE, TWO STEPS. `srv1-moe-slots.tsv` is shared with
#   `tools/runs/srv1-moe-slots.sh`, which writes step 6's placement rows into it
#   and reserves the crash study — step 7, behaviour 8, the L2 boundary and L3's
#   60 trials — for this script, because that is the kernel question and not a
#   placement one. So `--step crash` APPENDS and never truncates, exactly as
#   that script does, and the two run in either order. Each writer emits its own
#   `### WORKLOAD`, `### START` and `### END`; `Sweep.stamp()` takes the last of
#   each and `stamped_before()` the nearest preceding, so both blocks resolve.
#   `### INSTRUMENT` names which tool produced the rows that follow it.
#
# GUIDELINE 1 — interleaving. The 2026-09-01 A/B ran all of one arm then all of
# the other, confounding arm with elapsed time and card temperature. Here the
# arm is the INNERMOST loop: replicate, then cell, then arm, and the arm order
# rotates by replicate so no arm keeps a fixed position in the sequence. The arm
# changes every three level rows.
#
# GUIDELINE 2 — one cell per process invocation. The prompt draw comes from a
# per-process `itertools.count()`, so a process that ran levels `1,2,4,8` drew
# different work than one that ran `1,4,8` — measured at 6.2%, larger than most
# effects this run is looking for. Every invocation below passes the driver
# EXACTLY ONE cell argument, and every arm gets the identical level list for a
# given (cell, replicate), so `(ptok, otok_req)` pairs across arms.
#
# `otok_req` is the requested output budget and is NOT `otok` (resolved conflict
# §6.2). The driver prints neither, so `otok_req` is recovered by replaying the
# driver's own `mkprompt()` — the same source region `sweeprows.workload_digest`
# execs — over the same call order the driver uses (one warm-up, then n per
# level). It is a plan, computed from the driver, not a measurement copied from
# somewhere else.
#
# GUIDELINE 8 — a refusal is a result. Every launch goes through `retry3`; only
# a third failure is believed, and it is recorded as a REFUSED row with the
# engine's own words. No row is ever fabricated: if L2 does not re-crash, no
# CRASH row and no `### BOUNDARY` are emitted and step 7 stays honestly red.
#
# Usage:
#   srv1-kernel-arms.sh [--dry-run] [--step serve|crash|all] [--out-dir DIR]
#                       [--arms "L0 L1 ..."] [--cells "d3b mling"]
#                       [--crash-cells "mling moss4b"] [--reps N] [--trials N]
#                       [--models DIR] [--force]
#
# --dry-run prints the exact command line for every cell and touches nothing.

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./_common.sh disable=SC1091
. "$HERE/_common.sh"

REPO=$(cd -- "$HERE/../.." && pwd)
DRIVER=lcp_sweep_31-08-2026.py
RUN_DIR=$REPO/records/evidence/2026-09-02-srv1-kernel-arms
ARMS_TSV=srv1-lcpp-arms.tsv
SLOTS_TSV=srv1-moe-slots.tsv

DRY_RUN=0
STEP=all
FORCE=0
MODELS=${LCP_MODELS:-/home/adaramir/models}
SERVE_ARMS="L0 L1 L2 L3 L4 A1"
SERVE_CELLS="d3b mling"
SERVE_LEVELS="1,4,8"
REPS=5
# The unpatched arm and its patch. `lcp-vllm-3-arm-run.md:43-44`.
CRASH_ARM=L2
FIX_ARM=L3
CRASH_CELLS="mling moss4b"
CRASH_MAX_N=12
TRIALS=60

WORK=
LOGTAIL_PID=
LOGTAIL_FLAG=

usage() {
    sed -n '2,60p' "$0" >&2
    exit "${1:-2}"
}

while [ "$#" -gt 0 ]; do
    case $1 in
        --dry-run) DRY_RUN=1 ;;
        --force) FORCE=1 ;;
        --step) STEP=$2; shift ;;
        --out-dir) RUN_DIR=$2; shift ;;
        --models) MODELS=$2; shift ;;
        --arms) SERVE_ARMS=$2; shift ;;
        --cells) SERVE_CELLS=$2; shift ;;
        --crash-cells) CRASH_CELLS=$2; shift ;;
        --reps) REPS=$2; shift ;;
        --trials) TRIALS=$2; shift ;;
        -h | --help) usage 0 ;;
        *) _fail "unknown argument '$1'"; usage ;;
    esac
    shift
done

case $STEP in
    serve | crash | all) : ;;
    *) _fail "--step must be serve, crash or all (got '$STEP')"; exit 2 ;;
esac

# --------------------------------------------------------------------------
# the arms and the cells
# --------------------------------------------------------------------------

# Every locally built arm is tagged `llamacpp:b10644-<ARM>`, which is what
# `test_a_row_that_does_not_name_its_arm_...:29` accepts and what the `### BUILD`
# stamps below resolve. `A1` is the stock image, pinned by tag and never
# floating (`:26`).
arm_img() {
    case $1 in
        A1) printf '%s' 'ghcr.io/ggml-org/llama.cpp:server-cuda-b10644' ;;
        [ABL][0-9]) printf 'llamacpp:b10644-%s' "$1" ;;
        *) _fail "arm_img: '$1' is not an arm this campaign names"; return 1 ;;
    esac
}

# A cell is `<subdir>|<gguf>|<np>|<ctx_slot>|<ncmoe>`. Resident models only
# (step 4): every one of these loads whole onto the 6144 MiB card at ncmoe=0,
# as the 2026-09-01 A/B's `vram=` readings show. `ctx_slot` is 2048 because the
# driver SKIPs anything under its worst sampled prompt+reply, 1347.
cell_def() {
    case $1 in
        # dense 3B — the 2026-09-01 A/B's own cell, carried forward
        d3b) printf '%s' 'dense|Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf|8|2048|0' ;;
        # MoE, bailingmoe3, 128 experts / 8 used, 23 expert layers
        mling) printf '%s' 'moe|Ling-3.0-tiny-Q4_K_M.gguf|8|2048|0' ;;
        # MoE, gpt-oss, 4 experts / 2 used, 24 expert layers — a different
        # expert geometry, which is what test_a_crash_...:96-101 is asking for
        moss4b) printf '%s' 'moe|4b-Q4_K_M.gguf|8|2048|0' ;;
        *) _fail "cell_def: no such cell '$1'"; return 1 ;;
    esac
}

_cell_field() {
    local def
    def=$(cell_def "$1") || return 1
    printf '%s' "$def" | cut -d'|' -f"$2"
}

cell_label() { # ARM CELL -> `<ARM>-<cell> np=.. ctx_slot=.. c=.. ncmoe=..`
    local arm=$1 cell=$2 np cs ncm
    np=$(_cell_field "$cell" 3) || return 1
    cs=$(_cell_field "$cell" 4) || return 1
    ncm=$(_cell_field "$cell" 5) || return 1
    printf '%s np=%s ctx_slot=%s c=%s ncmoe=%s' \
        "$(arm_label "$arm" "$cell")" "$np" "$cs" "$((np * cs))" "$ncm"
}

cell_spec() { # CELL LEVELS -> the driver's one cell argument
    local cell=$1 levels=$2 np cs ncm
    np=$(_cell_field "$cell" 3) || return 1
    cs=$(_cell_field "$cell" 4) || return 1
    ncm=$(_cell_field "$cell" 5) || return 1
    printf '%s:%s:%s:%s' "$np" "$cs" "$ncm" "$levels"
}

cmdline() { # ARM CELL LEVELS -> the exact command line, one cell, one process
    local arm=$1 cell=$2 levels=$3 sub gguf
    sub=$(_cell_field "$cell" 1) || return 1
    gguf=$(_cell_field "$cell" 2) || return 1
    printf 'LCP_IMG=%s python3 %s %s %s %s %s' \
        "$(arm_img "$arm")" "$REPO/$DRIVER" "$gguf" "$MODELS/$sub" \
        "$(arm_label "$arm" "$cell")" "$(cell_spec "$cell" "$levels")"
}

# --------------------------------------------------------------------------
# `### BUILD` — behaviour 3: a local tag must resolve to the source that made it
# --------------------------------------------------------------------------

# Read from the image's own labels. Nothing here has a default: an arm whose
# image does not carry its build variables cannot be stamped, and a stamp that
# guessed them would be exactly the header comment this test exists to replace.
_image_label() { # IMG KEY
    local img=$1 key=$2 out
    out=$(docker image inspect --format "{{index .Config.Labels \"$key\"}}" "$img" 2>/dev/null) || out=
    case $out in '<no value>' | 'null') out= ;; esac
    printf '%s' "$(_tok "$out")"
}

build_stamp() { # ARM — skipped for a registry image, which needs no stamp
    local arm=$1 img key val out=() missing=
    img=$(arm_img "$arm") || return 1
    case $img in
        llamacpp:b10644-*) : ;;
        *) return 0 ;;
    esac
    out=("arm=$arm")
    for key in commit image_sha256 cuda_architectures force_mmq ggml_native cpu_all_variants patched; do
        val=$(_image_label "$img" "org.mcgyvr.build.$key")
        if [ -z "$val" ]; then
            val=$(_image_label "$img" "$key")
        fi
        if [ "$key" = image_sha256 ] && [ -z "$val" ]; then
            # The one build fact docker always knows about its own image.
            val=$(docker image inspect --format '{{.Id}}' "$img" 2>/dev/null) || val=
            val=${val#sha256:}
            val=$(_tok "$val")
        fi
        if [ -z "$val" ]; then
            missing="${missing:+$missing }$key"
            continue
        fi
        out+=("$key=$val")
    done
    if [ -n "$missing" ]; then
        _fail "### BUILD for $arm cannot be written: $img carries no $missing. Label the build (org.mcgyvr.build.<key>=...) — a BUILD stamp with a guessed variable is the header comment behaviour 3 replaces"
        return 1
    fi
    stamp BUILD "${out[@]}"
}

# --------------------------------------------------------------------------
# the engine log, captured while the container is alive
# --------------------------------------------------------------------------

# The driver runs its server as `lcps` and `docker rm -f`s it before returning,
# which takes the log with it. The crash marks
# (`ggml_cuda_mul_mat_vec_q` / `invalid argument`) and the checkpoint's quant
# type are only readable from that log, so it is followed while it exists. This
# reads the driver; it does not change it.
log_tail_start() { # DEST
    local dest=$1
    LOGTAIL_FLAG=$WORK/logtail.stop
    rm -f "$LOGTAIL_FLAG"
    : >"$dest"
    (
        while [ ! -e "$LOGTAIL_FLAG" ]; do
            if docker inspect lcps >/dev/null 2>&1; then
                docker logs -f lcps >>"$dest" 2>&1 || true
            else
                sleep 1
            fi
        done
    ) &
    LOGTAIL_PID=$!
}

log_tail_stop() {
    [ -n "$LOGTAIL_PID" ] || return 0
    [ -n "$LOGTAIL_FLAG" ] && : >"$LOGTAIL_FLAG"
    kill "$LOGTAIL_PID" 2>/dev/null || true
    wait "$LOGTAIL_PID" 2>/dev/null || true
    LOGTAIL_PID=
}

# What `quantization_config` is to a GPTQ checkpoint, `print_info: file type` is
# to a GGUF: read, not inferred from the path. `A checkpoint's name is not
# evidence of its format` (lcp-vllm-3-arm-run.md:143).
log_file_type() { # LOGFILE
    local out
    out=$(sed -n 's/.*file type *= *//p' "$1" 2>/dev/null | head -n 1) || out=
    out=$(_tok "$out")
    if [ -z "$out" ]; then
        # The launch died before the loader printed. Saying so is a reading;
        # copying the quant out of the filename would not be.
        out=unread_the_loader_never_printed_it
    fi
    printf '%s' "$out"
}

# --------------------------------------------------------------------------
# `otok_req` — the driver's own draw, replayed
# --------------------------------------------------------------------------

# One integer per level, in the driver's call order: one warm-up post, then n
# posts per level. `sum(want) // n` mirrors the driver's own `otok = gen // n`,
# so the plan and the outcome are the same shape. The source region sliced here
# is the one `tests/sweeprows.py:workload_digest` execs, so this cannot drift
# from the digest the file is stamped with.
otok_req_list() { # LEVELS -> one line per level
    python3 - "$REPO/$DRIVER" "$1" <<'PY'
import itertools
import random
import sys
import threading
from pathlib import Path

driver = Path(sys.argv[1])
levels = [int(x) for x in sys.argv[2].split(",")]
source = driver.read_text(encoding="utf-8")
block = source[source.index("PROMPT_DECILES") : source.index("def sh(")]
namespace = {"itertools": itertools, "threading": threading, "random": random}
exec(compile(block, str(driver), "exec"), namespace)
make = namespace["mkprompt"]

make()  # the warm-up request lcp_sweep posts before the first level
for n in levels:
    print(sum(make()[1] for _ in range(n)) // n)
PY
}

# --------------------------------------------------------------------------
# re-emitting the driver's rows with the identity the contract wants
# --------------------------------------------------------------------------

reemit() { # ARM IMG LINE [EXTRA k=v ...]
    local arm=$1 img=$2 line=$3
    shift 3
    local -a parts=() args=() free=()
    local label kind tok i
    IFS=$'\t' read -r -a parts <<<"$line"
    [ "${#parts[@]}" -ge 3 ] || return 0
    label=${parts[1]}
    kind=${parts[2]}
    for ((i = 3; i < ${#parts[@]}; i++)); do
        tok=${parts[i]}
        if _kv_ok "$tok" && ! _has_space "$tok"; then
            args+=("$tok")
        else
            free+=("$tok")
        fi
    done
    # The identity this run adds goes LAST: the parser takes the last duplicate
    # key (§1.2), and the image we launched is the one that ran, whatever the
    # driver echoed from its own environment.
    args+=("arm=$arm" "img=$img")
    if [ "$#" -gt 0 ]; then
        args+=("$@")
    fi
    if [ "${#free[@]}" -gt 0 ]; then
        # §1.3: free text whose first word looks like `word=` is eaten as a
        # field and vanishes from `tail`. A leading `|` is a separator, not a
        # measurement, and keeps the engine's words intact.
        if _kv_ok "${free[0]}"; then
            free=("|" "${free[@]}")
        fi
        row "$label" "$kind" "${args[@]}" -- "${free[@]}"
    else
        row "$label" "$kind" "${args[@]}"
    fi
}

emit_raw() { # ARM RAW OREQ REP TRIALS_OR_EMPTY
    local arm=$1 raw=$2 oreq=$3 rep=$4 trials=$5
    local img line kind idx=0 req
    local -a extra=()
    img=$(arm_img "$arm") || return 1
    while IFS= read -r line; do
        [ -n "${line//[[:space:]]/}" ] || continue
        case $line in
            '###'*)
                printf '%s\n' "$line"
                continue
                ;;
        esac
        kind=$(printf '%s' "$line" | cut -f3)
        case $kind in
            n=*)
                idx=$((idx + 1))
                extra=()
                if [ -n "$rep" ]; then
                    extra+=("rep=$rep")
                fi
                req=$(sed -n "${idx}p" "$oreq" 2>/dev/null) || req=
                if [ -n "$req" ]; then
                    extra+=("otok_req=$req")
                fi
                if [ -n "$trials" ]; then
                    extra+=("trials=$trials")
                fi
                reemit "$arm" "$img" "$line" ${extra[@]+"${extra[@]}"}
                ;;
            *)
                reemit "$arm" "$img" "$line"
                ;;
        esac
    done <"$raw"
}

# --------------------------------------------------------------------------
# one invocation
# --------------------------------------------------------------------------

RAW=
LOG=

drive_once() { # ARM CELL LEVELS — the retry3 body
    local arm=$1 cell=$2 levels=$3 sub gguf img
    sub=$(_cell_field "$cell" 1) || return 1
    gguf=$(_cell_field "$cell" 2) || return 1
    img=$(arm_img "$arm") || return 1
    : >"$RAW"
    log_tail_start "$LOG"
    LCP_IMG=$img python3 "$REPO/$DRIVER" "$gguf" "$MODELS/$sub" \
        "$(arm_label "$arm" "$cell")" "$(cell_spec "$cell" "$levels")" >"$RAW" 2>&1 || true
    log_tail_stop
    # A launch that produced a CONFIG measured something; a SKIP or a DEGENERATE
    # is a verdict about the cell and retrying it three times would only repeat
    # it. Only a REFUSED (or an empty run) is the memory-edge coin flip
    # guideline 8 is about.
    if grep -q -e "$(printf '\tCONFIG\t')" -e "$(printf '\tSKIP\t')" -e "$(printf '\tDEGENERATE\t')" "$RAW"; then
        return 0
    fi
    return 1
}

run_cell() { # ARM CELL LEVELS REP TRIALS_OR_EMPTY
    local arm=$1 cell=$2 levels=$3 rep=$4 trials=$5
    local oreq=$WORK/oreq.txt img reason quant
    img=$(arm_img "$arm") || return 1
    otok_req_list "$levels" >"$oreq"
    if retry3 drive_once "$arm" "$cell" "$levels"; then
        emit_raw "$arm" "$RAW" "$oreq" "$rep" "$trials"
        return 0
    fi
    # Guideline 8: three attempts, then the refusal is the result. The reason is
    # the engine's, never a summary of it.
    reason=$(awk -F'\t' '$3 == "REFUSED" { print $4 }' "$RAW" | tail -n 1 | tr '\t' ' ')
    if [ -z "$reason" ]; then
        reason=$(tr '\t' ' ' <"$LOG" | tail -n 3 | tr '\n' ' ')
    fi
    if [ "${#reason}" -le 40 ]; then
        reason="$reason | the driver printed no usable reason and the engine log for $(arm_label "$arm" "$cell") held nothing longer"
    fi
    quant=$(log_file_type "$LOG")
    refused "$(cell_label "$arm" "$cell")" \
        "arm=$arm" "img=$img" "checkpoint_quant=$quant" "tries=${RUN_TRIES:-3}" \
        -- "|" "$reason"
    return 1
}

# --------------------------------------------------------------------------
# step 4 — serve
# --------------------------------------------------------------------------

rotate() { # SHIFT ITEM... — the arm order turns by replicate, so no arm keeps
    # a fixed position in the sequence and position cannot be read as arm.
    local k=$1
    shift
    local -a a=("$@")
    local n=${#a[@]} i
    [ "$n" -gt 0 ] || return 0
    for ((i = 0; i < n; i++)); do
        printf '%s\n' "${a[$(((i + k) % n))]}"
    done
}

serve_plan() { # prints one `ARM CELL REP` triple per line, in emission order
    local rep cell arm
    local -a arms=()
    read -r -a arms <<<"$SERVE_ARMS"
    for ((rep = 1; rep <= REPS; rep++)); do
        for cell in $SERVE_CELLS; do
            while read -r arm; do
                [ -n "$arm" ] || continue
                printf '%s %s %s\n' "$arm" "$cell" "$rep"
            done < <(rotate "$((rep - 1))" "${arms[@]}")
        done
    done
}

serve_step() {
    local arm cell rep
    workload_stamp "$DRIVER"
    start_stamp
    for arm in $SERVE_ARMS; do
        build_stamp "$arm"
    done
    while read -r arm cell rep; do
        # Per-arm re-stamp, not once per file: `test_a_row_without_...:9-11`.
        rig_stamp
        run_cell "$arm" "$cell" "$SERVE_LEVELS" "$rep" "" || true
    done < <(serve_plan)
    end_stamp
    rig_assert_unchanged
}

serve_dry() {
    local arm cell rep
    printf '# step 4 (serve) -> %s\n' "$RUN_DIR/$ARMS_TSV"
    printf '# %s arms x %s cells x %s replicates, arm innermost and rotating: one process per cell, levels %s\n' \
        "$(printf '%s' "$SERVE_ARMS" | wc -w)" "$(printf '%s' "$SERVE_CELLS" | wc -w)" \
        "$REPS" "$SERVE_LEVELS"
    while read -r arm cell rep; do
        printf '# rep=%s arm=%s cell=%s\n' "$rep" "$arm" "$cell"
        cmdline "$arm" "$cell" "$SERVE_LEVELS"
        printf '\n'
    done < <(serve_plan)
}

# --------------------------------------------------------------------------
# step 7 — crash
# --------------------------------------------------------------------------

CRASH_HITS=      # `cell:width` per crash actually reproduced
CRASH_FIRST=

crash_marks() { # LOGFILE -> the two lines that name the defect, or nothing
    local log=$1 a b
    a=$(grep -m1 -F 'ggml_cuda_mul_mat_vec_q' "$log" 2>/dev/null | tr '\t' ' ') || a=
    b=$(grep -m1 -F 'invalid argument' "$log" 2>/dev/null | tr '\t' ' ') || b=
    if [ -z "$a" ] || [ -z "$b" ]; then
        return 1
    fi
    if [ "$a" = "$b" ]; then
        printf '%s' "$a"
    else
        printf '%s | %s' "$a" "$b"
    fi
}

# The boundary sweep. One process per attempt, each carrying the widths that
# have not been reached yet: the driver breaks on the first dead level and takes
# its server with it, so everything past the break needs a fresh launch.
crash_probe() { # CELL
    local cell=$1 pending levels errw marks img w rest
    img=$(arm_img "$CRASH_ARM") || return 1
    pending=$(seq 1 "$CRASH_MAX_N" | tr '\n' ',')
    pending=${pending%,}
    while [ -n "$pending" ]; do
        levels=$pending
        rig_stamp
        if ! run_cell "$CRASH_ARM" "$cell" "$levels" "" ""; then
            _fail "$CRASH_ARM refused $cell three times; widths $levels are unmeasured and the boundary is not located"
            return 0
        fi
        errw=$(awk -F'\t' '$3 ~ /^n=/ && $4 == "ERR" { sub(/^n=/, "", $3); print $3 }' "$RAW" | tail -n 1)
        [ -n "$errw" ] || return 0
        if marks=$(crash_marks "$LOG"); then
            # BEHAVIOUR 8: a CRASH row is written only when the engine log
            # actually says the kernel died. `gen == 0` on its own is a cell that
            # produced no tokens, which is not the same claim.
            #
            # http_000: the driver counts a request as failed when it came back
            # with no completion at all, and at this width every one of them did
            # — the server had already aborted, so each urlopen raised. That is
            # the numerator; the width is the denominator.
            row "$(cell_label "$CRASH_ARM" "$cell")" CRASH \
                "arm=$CRASH_ARM" "img=$img" "n=$errw" "http_000=$errw/$errw" \
                -- "|" "$marks"
            CRASH_HITS="${CRASH_HITS:+$CRASH_HITS }$cell:$errw"
            if [ -z "$CRASH_FIRST" ] || [ "$errw" -lt "$CRASH_FIRST" ]; then
                CRASH_FIRST=$errw
            fi
        fi
        rest=
        for ((w = errw + 1; w <= CRASH_MAX_N; w++)); do
            rest="${rest:+$rest,}$w"
        done
        pending=$rest
    done
}

# 0 failures in 60 trials bounds the failure rate at 5%; 30 only reaches 10%.
# One server, `TRIALS` batches at the width that killed the unpatched build —
# the denominator is batches, which is what the defect is a boundary on.
crash_soak() { # CELL WIDTH
    local cell=$1 width=$2 levels='' i
    for ((i = 0; i < TRIALS; i++)); do
        levels="${levels:+$levels,}$width"
    done
    rig_stamp
    run_cell "$FIX_ARM" "$cell" "$levels" "" 1 || true
}

crash_step() {
    local cell hit w
    workload_stamp "$DRIVER"
    # Whose rows follow, in a file two steps write to.
    stamp INSTRUMENT "step=7" "behaviour=8" "driver=$DRIVER"
    start_stamp
    build_stamp "$CRASH_ARM"
    build_stamp "$FIX_ARM"
    for cell in $CRASH_CELLS; do
        crash_probe "$cell"
        for hit in $CRASH_HITS; do
            case $hit in
                "$cell":*)
                    w=${hit#*:}
                    crash_soak "$cell" "$w"
                    ;;
            esac
        done
    done
    if [ -n "$CRASH_FIRST" ]; then
        stamp BOUNDARY "arm=$CRASH_ARM" "first_failing_n=$CRASH_FIRST"
    else
        _fail "no ### BOUNDARY: $CRASH_ARM did not re-crash on this boot, so there is no first failing width to name. Behaviour 8 wants the crash REPRODUCED before it is called fixed; a boundary stamp without one would be the fabrication this run exists to avoid" || true
    fi
    end_stamp
    rig_assert_unchanged
}

crash_dry() {
    local cell
    printf '# step 7 (crash) -> %s (appended; step 6 shares this file)\n' "$RUN_DIR/$SLOTS_TSV"
    printf '# %s boundary sweep n=1..%s, then %s x %s trials at every width that actually died\n' \
        "$CRASH_ARM" "$CRASH_MAX_N" "$FIX_ARM" "$TRIALS"
    for cell in $CRASH_CELLS; do
        printf '# arm=%s cell=%s boundary probe (widths past the break are re-launched from where it broke)\n' \
            "$CRASH_ARM" "$cell"
        cmdline "$CRASH_ARM" "$cell" "$(seq 1 "$CRASH_MAX_N" | tr '\n' ',' | sed 's/,$//')"
        printf '\n'
        printf '# arm=%s cell=%s soak, one process per killed width, %s batches:\n' \
            "$FIX_ARM" "$cell" "$TRIALS"
        printf '#   %s\n' \
            "$(cmdline "$FIX_ARM" "$cell" "<WIDTH repeated $TRIALS times>")"
        printf '#   emitted only for widths %s actually crashed at — none are planned in advance\n\n' "$CRASH_ARM"
    done
}

# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

if [ "$DRY_RUN" -eq 1 ]; then
    case $STEP in
        serve) serve_dry ;;
        crash) crash_dry ;;
        all) serve_dry; crash_dry ;;
    esac
    exit 0
fi

WORK=$(mktemp -d)
RAW=$WORK/raw.tsv
LOG=$WORK/engine.log
: >"$RAW"
: >"$LOG"
trap 'log_tail_stop; rm -rf "$WORK"' EXIT

mkdir -p "$RUN_DIR"

guard() { # FILE
    if [ -e "$1" ] && [ "$FORCE" -ne 1 ]; then
        _fail "$1 exists. A measurement file is written once; pass --force only if you mean to replace it"
        exit 1
    fi
}

case $STEP in
    serve)
        guard "$RUN_DIR/$ARMS_TSV"
        serve_step >"$RUN_DIR/$ARMS_TSV"
        ;;
    crash)
        # Appended, not truncated: step 6 writes its placement rows into the
        # same file and neither step may erase the other.
        crash_step >>"$RUN_DIR/$SLOTS_TSV"
        ;;
    all)
        guard "$RUN_DIR/$ARMS_TSV"
        serve_step >"$RUN_DIR/$ARMS_TSV"
        crash_step >>"$RUN_DIR/$SLOTS_TSV"
        ;;
esac
