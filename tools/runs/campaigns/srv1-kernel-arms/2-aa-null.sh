#!/usr/bin/env bash
# tools/runs/campaigns/srv1-kernel-arms/2-aa-null.sh — step 2 of the srv1 kernel-arms run
# (`PLAN.md:116`), written against
# `records/evidence/2026-09-02-srv1-kernel-arms/ARTIFACT-CONTRACT.md` §5.6.
#
# Produces `records/evidence/2026-09-02-srv1-kernel-arms/srv1-aa-null.tsv`.
#
# WHAT AN A/A NULL IS FOR. Before any A/B on this rig is believed, the
# instrument has to be priced: the same arm, against itself, under the same
# procedure, so that "1.7x", "1.15x" and "1.02x" can be told apart from the
# machine. `L3` is run as two sides of a comparison that is not one — side `a`
# against side `b`, both the ship candidate, same image, same cells, same level
# list, same five replicates, interleaved exactly the way step 4 interleaves its
# real arms. Whatever spread comes out is the floor every later effect claim is
# measured against (behaviour 7, guideline 1).
#
# Because the two sides are one arm, every row is labelled `L3-<cell>` and the
# rows differ only in `side=` and `rep=`. `Row.cell` strips the `L3-` prefix, so
# grouping is by `(cell, n)` and all ten replicates of a group land together —
# which is what `### NULL spread_pct=` is computed over.
#
# `spread_pct` IS NOT CHOSEN. It is computed from the rows this run just wrote,
# through `tools/runs/rows.py` itself, by the same formula
# `test_one_observation_...:112-123` uses: per `(cell, n)` group of two or more,
# `(max - min) / median`, and the largest of those as a percentage. A script that
# picked the number would be pricing nothing.
#
# GUIDELINE 2 — one cell per process invocation. The prompt draw comes from a
# per-process counter, and a null whose two sides drew different work would
# price the desync instead of the instrument. Every invocation below passes the
# driver EXACTLY ONE cell argument with the identical level list, and
# `otok_req=` records the budget that draw asked for, replayed from the driver's
# own `mkprompt()`.
#
# GUIDELINE 8 — a refusal is a result: every launch goes through `retry3`, and
# only a third failure is believed and recorded. No row is ever fabricated.
#
# Usage:
#   2-aa-null.sh [--dry-run] [--cells "d3b mling"] [--reps N] [--arm L3]
#                   [--models DIR]
#
# --dry-run prints the exact command line for every cell and touches nothing.
#
# Through the door only (tools/runs/run.sh): RUN_ID names the run in ### START,
# ### ROUND records the product round gate 1 checked, the file lands in
# $RUN_OUT_DIR, and the arm's tag is resolved to a digest ONCE (image_digest,
# gate 3) before the driver sees it — the driver refuses a tag.
# RUN_ARTIFACTS: srv1-aa-null.tsv

[ -n "${RUN_ID:-}" ] || { echo "2-aa-null.sh: RUN_ID is unset — start me through tools/runs/run.sh" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required

REPO=$(cd -- "$HERE/../../../.." && pwd)
DRIVER=tools/runs/drivers/lcp_sweep.py
# The prompts the driver draws come from this module, not from the driver:
# the WORKLOAD stamp names it, and the digest is re-derived from it.
WORKLOAD=tools/runs/workload.py
# The envelope: the door's $RUN_OUT_DIR (door_required refused without it).
RUN_DIR=$RUN_OUT_DIR
NULL_TSV=srv1-aa-null.tsv

DRY_RUN=0
MODELS=${LCP_MODELS:-/home/adaramir/models}
ARM=L3
CELLS="d3b mling"
LEVELS="1,4,8"
REPS=5
SIDES="a b"

WORK=
LOGTAIL_PID=
LOGTAIL_FLAG=

usage() {
    sed -n '2,48p' "$0" >&2
    exit "${1:-2}"
}

while [ "$#" -gt 0 ]; do
    case $1 in
        --dry-run) DRY_RUN=1 ;;
        --models) MODELS=$2; shift ;;
        --arm) ARM=$2; shift ;;
        --cells) CELLS=$2; shift ;;
        --reps) REPS=$2; shift ;;
        -h | --help) usage 0 ;;
        *) _fail "unknown argument '$1'"; usage ;;
    esac
    shift
done

# --------------------------------------------------------------------------
# the arm and the cells — identical to step 4's, because a null that priced a
# different instrument would price nothing
# --------------------------------------------------------------------------

arm_img() {
    case $1 in
        A1) printf '%s' 'ghcr.io/ggml-org/llama.cpp:server-cuda-b10644' ;;
        [ABL][0-9]) printf 'llamacpp:b10644-%s' "$1" ;;
        *) _fail "arm_img: '$1' is not an arm this campaign names"; return 1 ;;
    esac
}

# The digest the driver runs — gate 3 of the door: a tag is resolved ONCE per
# arm through `image_digest` (tools/runs/_common.sh), cached here, and the
# driver refuses anything that is not a digest. The row keeps `img=<tag>` —
# the arm's name, and what `test_a_row_that_does_not_name_its_arm` accepts —
# and carries the driver's `img_digest=` beside it, so a reader has both what
# the arm was called and which bytes answered.
declare -A ARM_DIGEST=()
arm_digest() {
    local tag
    if [ -z "${ARM_DIGEST[$1]:-}" ]; then
        tag=$(arm_img "$1") || return 1
        ARM_DIGEST[$1]=$(image_digest "$tag") || return 1
    fi
    printf '%s' "${ARM_DIGEST[$1]}"
}

cell_def() {
    case $1 in
        d3b) printf '%s' 'dense|Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf|8|2048|0' ;;
        mling) printf '%s' 'moe|Ling-3.0-tiny-Q4_K_M.gguf|8|2048|0' ;;
        moss4b) printf '%s' 'moe|4b-Q4_K_M.gguf|8|2048|0' ;;
        *) _fail "cell_def: no such cell '$1'"; return 1 ;;
    esac
}

_cell_field() {
    local def
    def=$(cell_def "$1") || return 1
    printf '%s' "$def" | cut -d'|' -f"$2"
}

cell_label() {
    local arm=$1 cell=$2 np cs ncm
    np=$(_cell_field "$cell" 3) || return 1
    cs=$(_cell_field "$cell" 4) || return 1
    ncm=$(_cell_field "$cell" 5) || return 1
    printf '%s np=%s ctx_slot=%s c=%s ncmoe=%s' \
        "$(arm_label "$arm" "$cell")" "$np" "$cs" "$((np * cs))" "$ncm"
}

cell_spec() {
    local cell=$1 levels=$2 np cs ncm
    np=$(_cell_field "$cell" 3) || return 1
    cs=$(_cell_field "$cell" 4) || return 1
    ncm=$(_cell_field "$cell" 5) || return 1
    printf '%s:%s:%s:%s' "$np" "$cs" "$ncm" "$levels"
}

cmdline() {
    local arm=$1 cell=$2 levels=$3 sub gguf
    sub=$(_cell_field "$cell" 1) || return 1
    gguf=$(_cell_field "$cell" 2) || return 1
    printf 'LCP_IMG="$(image_digest %s)" python3 %s %s %s %s %s' \
        "$(arm_img "$arm")" "$REPO/$DRIVER" "$gguf" "$MODELS/$sub" \
        "$(arm_label "$arm" "$cell")" "$(cell_spec "$cell" "$levels")"
}

# --------------------------------------------------------------------------
# the engine log, captured while the container is alive
# --------------------------------------------------------------------------

log_tail_start() {
    local dest=$1
    LOGTAIL_FLAG=$WORK/logtail.stop
    rm -f "$LOGTAIL_FLAG"
    : >"$dest"
    (
        while [ ! -e "$LOGTAIL_FLAG" ]; do
            if docker inspect "$RUN_ID-lcps" >/dev/null 2>&1; then
                docker logs -f "$RUN_ID-lcps" >>"$dest" 2>&1 || true
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

# Read, never inferred from the path: `a checkpoint's name is not evidence of
# its format` (PLAN.md:143).
log_file_type() {
    local out
    out=$(sed -n 's/.*file type *= *//p' "$1" 2>/dev/null | head -n 1) || out=
    out=$(_tok "$out")
    if [ -z "$out" ]; then
        # The one word for this, `_common.sh` `refused` and §6.3: a
        # checkpoint WAS involved and its type was never read. Which flavour of
        # unread goes in the reason, not in the field.
        out=unread
    fi
    printf '%s' "$out"
}

# --------------------------------------------------------------------------
# `otok_req` — the driver's own draw, replayed in its own call order
# --------------------------------------------------------------------------

otok_req_list() {
    python3 - "$REPO/$WORKLOAD" "$1" <<'PY'
import itertools
import random
import sys
import threading
from pathlib import Path

driver = Path(sys.argv[1])
levels = [int(x) for x in sys.argv[2].split(",")]
source = driver.read_text(encoding="utf-8")
block = source[source.index("PROMPT_DECILES") :]  # the module is the block
namespace = {"itertools": itertools, "threading": threading, "random": random}
exec(compile(block, str(driver), "exec"), namespace)
make = namespace["mkprompt"]

make()  # the warm-up request lcp_sweep posts before the first level
for n in levels:
    print(sum(make()[1] for _ in range(n)) // n)
PY
}

# --------------------------------------------------------------------------
# re-emitting the driver's rows
# --------------------------------------------------------------------------

reemit() {
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
            # The driver echoes the image it RAN, which is the digest gate 3
            # handed it; the tag this run named goes on as `img=` below.
            case $tok in
                img=*) tok="img_digest=${tok#img=}" ;;
            esac
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
        # §1.3: free text opening with `word=` is eaten as a field and vanishes
        # from `tail`. A leading `|` is a separator, not a measurement.
        if _kv_ok "${free[0]}"; then
            free=("|" "${free[@]}")
        fi
        row "$label" "$kind" "${args[@]}" -- "${free[@]}"
    else
        row "$label" "$kind" "${args[@]}"
    fi
}

emit_raw() { # RAW OREQ REP SIDE
    local raw=$1 oreq=$2 rep=$3 side=$4
    local img line kind idx=0 req
    local -a extra=()
    img=$(arm_img "$ARM") || return 1
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
                extra=("rep=$rep" "side=$side")
                req=$(sed -n "${idx}p" "$oreq" 2>/dev/null) || req=
                if [ -n "$req" ]; then
                    extra+=("otok_req=$req")
                fi
                reemit "$ARM" "$img" "$line" "${extra[@]}"
                ;;
            *)
                reemit "$ARM" "$img" "$line" "side=$side"
                ;;
        esac
    done <"$raw"
}

# --------------------------------------------------------------------------
# one invocation
# --------------------------------------------------------------------------

RAW=
LOG=

drive_once() {
    local cell=$1 levels=$2 sub gguf digest
    sub=$(_cell_field "$cell" 1) || return 1
    gguf=$(_cell_field "$cell" 2) || return 1
    digest=$(arm_digest "$ARM") || return 1
    : >"$RAW"
    log_tail_start "$LOG"
    LCP_IMG=$digest python3 "$REPO/$DRIVER" "$gguf" "$MODELS/$sub" \
        "$(arm_label "$ARM" "$cell")" "$(cell_spec "$cell" "$levels")" >"$RAW" 2>&1 || true
    log_tail_stop
    if grep -q -e "$(printf '\tCONFIG\t')" -e "$(printf '\tSKIP\t')" -e "$(printf '\tDEGENERATE\t')" "$RAW"; then
        return 0
    fi
    return 1
}

run_cell() { # CELL REP SIDE
    local cell=$1 rep=$2 side=$3
    local oreq=$WORK/oreq.txt img reason quant
    img=$(arm_img "$ARM") || return 1
    otok_req_list "$LEVELS" >"$oreq"
    if retry3 drive_once "$cell" "$LEVELS"; then
        emit_raw "$RAW" "$oreq" "$rep" "$side"
        return 0
    fi
    reason=$(awk -F'\t' '$3 == "REFUSED" { print $4 }' "$RAW" | tail -n 1 | tr '\t' ' ')
    if [ -z "$reason" ]; then
        reason=$(tr '\t' ' ' <"$LOG" | tail -n 3 | tr '\n' ' ')
    fi
    if [ "${#reason}" -le 40 ]; then
        reason="$reason | the driver printed no usable reason and the engine log for $(arm_label "$ARM" "$cell") held nothing longer"
    fi
    quant=$(log_file_type "$LOG")
    refused "$(cell_label "$ARM" "$cell")" \
        "arm=$ARM" "img=$img" "side=$side" "checkpoint_quant=$quant" "tries=${RUN_TRIES:-3}" \
        -- "|" "$reason"
    return 1
}

# --------------------------------------------------------------------------
# the schedule — the same interleave step 4 uses, with both sides being L3
# --------------------------------------------------------------------------

rotate() {
    local k=$1
    shift
    local -a a=("$@")
    local n=${#a[@]} i
    [ "$n" -gt 0 ] || return 0
    for ((i = 0; i < n; i++)); do
        printf '%s\n' "${a[$(((i + k) % n))]}"
    done
}

null_plan() { # prints `SIDE CELL REP` per line, in emission order
    local rep cell side
    local -a sides=()
    read -r -a sides <<<"$SIDES"
    for ((rep = 1; rep <= REPS; rep++)); do
        for cell in $CELLS; do
            while read -r side; do
                [ -n "$side" ] || continue
                printf '%s %s %s\n' "$side" "$cell" "$rep"
            done < <(rotate "$((rep - 1))" "${sides[@]}")
        done
    done
}

null_body() {
    local side cell rep
    workload_stamp "$WORKLOAD"
    start_stamp
    round_stamp
    while read -r side cell rep; do
        # Per-arm re-stamp rather than once per file, exactly as step 4 does:
        # the null prices the instrument only if it ran the same procedure.
        rig_stamp
        run_cell "$cell" "$rep" "$side" || true
    done < <(null_plan)
}

# The number this file exists to produce, computed from this file's own rows
# through `tools/runs/rows.py` — the same parser and the same formula the test
# applies, so the declared value cannot drift from the measured one.
null_spread() { # BODY_TSV
    (cd "$REPO" && uv run --no-sync --quiet python -c '
import statistics
import sys
from pathlib import Path

from tools.runs.rows import read

sweep = read(Path(sys.argv[1]))
by: dict[tuple[str, int], list[float]] = {}
for r in sweep.levels():
    if "agg" not in r.fields:
        continue
    by.setdefault((r.cell, r.n), []).append(r.num("agg"))
spreads = [
    (max(v) - min(v)) / statistics.median(v) for v in by.values() if len(v) >= 2
]
if not spreads:
    sys.exit(
        "no (cell, n) group was measured twice, so no spread was priced and "
        "the A/A null has nothing to declare"
    )
print(f"{max(spreads) * 100:.4f}")
' "$1")
}

null_dry() {
    local side cell rep
    printf '# step 2 (A/A null) -> %s\n' "$RUN_DIR/$NULL_TSV"
    printf '# arm %s against itself: %s sides x %s cells x %s replicates, one process per cell, levels %s\n' \
        "$ARM" "$(printf '%s' "$SIDES" | wc -w)" "$(printf '%s' "$CELLS" | wc -w)" \
        "$REPS" "$LEVELS"
    printf '# the two sides run the identical command; only side= and rep= on the rows tell them apart\n'
    while read -r side cell rep; do
        printf '# rep=%s side=%s cell=%s\n' "$rep" "$side" "$cell"
        cmdline "$ARM" "$cell" "$LEVELS"
        printf '\n'
    done < <(null_plan)
}

# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

if [ "$DRY_RUN" -eq 1 ]; then
    null_dry
    exit 0
fi

WORK=$(mktemp -d)
RAW=$WORK/raw.tsv
LOG=$WORK/engine.log
BODY=$WORK/body.tsv
: >"$RAW"
: >"$LOG"
trap 'log_tail_stop; rm -rf "$WORK"' EXIT

mkdir -p "$RUN_DIR"
OUT=$RUN_DIR/$NULL_TSV
if [ -e "$OUT" ]; then
    _fail "$OUT exists. A measurement file is written once (the door's gate 5 refuses this before the step starts); move it aside deliberately"
    exit 1
fi

null_body >"$BODY"
SPREAD=$(null_spread "$BODY")
{
    cat "$BODY"
    stamp NULL "spread_pct=$SPREAD"
    end_stamp
} >"$OUT"
rig_assert_unchanged
