#!/usr/bin/env bash
# tools/runs/campaigns/srv1-kernel-arms/6-moe-slots.sh — campaign step 6, behaviour 10.
#
# Emits, into records/evidence/2026-09-02-srv1-kernel-arms/:
#   srv1-moe-slots.tsv    (APPENDED to; see "one file, two steps" below)
#   placement-null.json   read by
#                         tests/test_placement_is_not_declared_output_neutral_without_a_measurement.py
#                         with a bare Path.read_text -- there is no friendly RED
#                         message for a missing or misshapen file, so the shape
#                         written here is exactly the one that test reads
#                         (ARTIFACT-CONTRACT.md section 4.1).
#
# WHAT THIS TESTS. tools/bench/serving/fingerprint.py declares by fiat that
# n_cpu_moe is placement, not semantics -- "WHERE a tensor is computed, not WHAT
# is emitted ... None of them alters the token distribution". The whole ncmoe
# floor programme (step 9, behaviour 9) rests on that fiat, and nothing has ever
# tested it. So this runs ONE checkpoint at ncmoe=0 and at ncmoe=99 through
# tools/breadth/measure.py, pairs the two through tools/bench/null.py, and
# writes down whether any cell CHANGED VERDICT. flips == 0 is demonstrated here,
# not asserted: the number in the JSON is null.py's own count over the two runs.
#
# AND THE BOUND IT IS JUDGED AGAINST. Guideline 9: each arm is a new
# serving_build, so no committed bound in tools/bench/reproducibility.json
# covers it, and 1.47pp measured elsewhere may not be borrowed. The run
# therefore prices its own null FIRST -- two identical passes at ncmoe=0 in one
# server session -- and "bound" in the JSON is that measurement, keyed to this
# build and to this run's own cell count.
#
# ORDER, AND WHY. ncmoe=0 is the cheap, fully-resident cell and it is also where
# the bound comes from, so it runs first and both its passes complete before the
# offloaded cell is launched at all. ncmoe=99 moves the bottleneck to host RAM,
# which is the load srv1 hard-locks under, so it is last: a lock there still
# leaves the CONFIG row, both a-passes and the priced bound on disk. Every
# marker and row is appended the moment it is produced -- one open/append/close
# per line, nothing buffered -- and measure.py appends its own rows as it goes.
#
# ONE FILE, TWO STEPS -- AND THIS SCRIPT OWNS IT. srv1-moe-slots.tsv is also the
# crash study's file (step 7, behaviour 8: the L2 boundary sweep and L3's 60
# trials). That work is the KERNEL question and is not this script's:
# PLAN.md's "Not worth rig time" list puts ncmoe cells for the
# kernel question out of scope, and this script's grid is exactly two placement
# cells of one model at one width.
#
# ARTIFACT-CONTRACT.md section 4 names `run tools/runs/campaigns/srv1-kernel-arms/6-moe-slots.sh` as the
# one behaviour that produces this file, so THIS SCRIPT IS THE OWNER-CREATOR: it
# creates the file, truncating any previous copy, and it must run FIRST.
# tools/runs/campaigns/srv1-kernel-arms/4-kernel-arms.sh --step crash is the APPENDER: it refuses to run
# until the step-6 block is on disk. The order is step 6 then step 7, it is
# enforced at both ends, and out of order both ends fail loudly rather than
# leaving half a file. See RUN-ORDER.md.
#
# Within this script every marker and row is appended the moment it is produced,
# so a hard lock keeps what was measured. The ### INSTRUMENT marker names which
# tool produced the rows that follow it. The ### WORKLOAD stamp the file owes
# (section 2.1) is emitted here because the file owes it; the digest is computed
# by tools/runs/rows.py itself, never asserted.
#
# NOTE the rows below are CONFIG / MEASURED / SELFNULL / PLACEMENT. None of them
# is a level row and none is a CRASH row, so this script adds nothing to the
# cell set test_a_crash_not_reproduced_is_not_a_crash_fixed.py counts -- it
# cannot make that test's "two MoE checkpoints" read as satisfied by one.
#
# Usage:
#   tools/runs/campaigns/srv1-kernel-arms/6-moe-slots.sh --model /path/to/ling.gguf [options]
#
#   --model PATH        the MoE checkpoint. Required, no default. Ling-3.0-tiny
#                       is the subject: it fits the 6 GB card at ncmoe=0 and
#                       survived a 60-minute soak at ncmoe=99.
#   --arm ARM           default L3 (must match [ABL][0-9]).
#   --img IMG           default llamacpp:b10644-L3. ONE image for both cells:
#                       two builds and two placements is two variables.
#   --served-name NAME  model name as the endpoint reports it (default: derived
#                       from the filename); passed to llama-server --alias.
#   --tier TIER         measure.py tier (default bench-py).
#   --tasks IDS         comma-separated task subset (default: the whole tier).
#   --draws N           sampled draws per task (default 1; the null reads the
#                       greedy arm only, so this is the cheapest legal value).
#   --cell NAME         label cell (default: derived from the filename).
#   --np N              --parallel (default 1: measure.py dispatches serially).
#   --ctx-slot N        per-slot context (default 4096).
#   --port N            host port for the container (default 8094).
#   --run-prefix NAME   run-directory prefix under records/measurements.
#   --dry-run           print every cell's exact command line, run nothing.
#
# An existing srv1-moe-slots.tsv is an error, and the door's gate 5 refuses it
# before this script starts: this script creates that artifact, and a second
# step-6 pass appended under a first one would file two placement nulls as one.
#
# Through the door only (tools/runs/run.sh): RUN_ID names the run in ### START,
# ### ROUND records the product round gate 1 checked, both files land in
# $RUN_OUT_DIR, and --img is resolved to a digest ONCE (image_digest, gate 3)
# before a container is started from it.
# RUN_ARTIFACTS: srv1-moe-slots.tsv placement-null.json

[ -n "${RUN_ID:-}" ] || { echo "6-moe-slots.sh: RUN_ID is unset — start me through tools/runs/run.sh" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(cd -- "$HERE/../../../.." && pwd)
# shellcheck source=tools/runs/_common.sh disable=SC1091
. "$HERE/../../_common.sh"
door_required

# The envelope: the door's $RUN_OUT_DIR (door_required refused without it).
OUT_DIR=$RUN_OUT_DIR
OUT_NAME=srv1-moe-slots.tsv
JSON_NAME=placement-null.json
WORKLOAD=tools/runs/workload.py
MODEL=
ARM=L3
IMG=llamacpp:b10644-L3
SERVED_NAME=
TIER=bench-py
TASKS=
DRAWS=1
CELL=
NP=1
CTX_SLOT=4096
PORT=8094
RUN_PREFIX=
DRY_RUN=0
# Named for the run, so gate 7 of the door finds it if this script does not.
CONTAINER="$RUN_ID-moe-slots"
IMG_DIGEST=
HEALTH_TRIES=90
NCMOE_A=0
NCMOE_B=99

die() {
    printf 'srv1-moe-slots: %s\n' "$*" >&2
    exit 2
}

say() {
    printf '# %s\n' "$*" >&2
}

while [ "$#" -gt 0 ]; do
    case $1 in
        --model) MODEL=${2:?--model needs a path}; shift 2 ;;
        --arm) ARM=${2:?--arm needs an arm}; shift 2 ;;
        --img) IMG=${2:?--img needs an image}; shift 2 ;;
        --served-name) SERVED_NAME=${2:?--served-name needs a name}; shift 2 ;;
        --tier) TIER=${2:?--tier needs a tier}; shift 2 ;;
        --tasks) TASKS=${2:?--tasks needs a list}; shift 2 ;;
        --draws) DRAWS=${2:?--draws needs an integer}; shift 2 ;;
        --cell) CELL=${2:?--cell needs a name}; shift 2 ;;
        --np) NP=${2:?--np needs an integer}; shift 2 ;;
        --ctx-slot) CTX_SLOT=${2:?--ctx-slot needs an integer}; shift 2 ;;
        --port) PORT=${2:?--port needs an integer}; shift 2 ;;
        --run-prefix) RUN_PREFIX=${2:?--run-prefix needs a name}; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h | --help) sed -n '63,83p' "$0"; exit 0 ;;
        *) die "unknown argument '$1'" ;;
    esac
done

[ -n "$MODEL" ] || die "no --model. The placement null is measured on a real checkpoint; there is no default, because a wrong path would be measured silently."
for _n in "DRAWS=$DRAWS" "NP=$NP" "CTX_SLOT=$CTX_SLOT" "PORT=$PORT"; do
    case ${_n#*=} in
        '' | *[!0-9]*) die "--${_n%%=*} is '${_n#*=}', which is not an integer" ;;
    esac
done

MODEL_DIR=$(cd -- "$(dirname -- "$MODEL")" 2>/dev/null && pwd) || MODEL_DIR=$(dirname -- "$MODEL")
MODEL_BASE=$(basename -- "$MODEL")
CONTAINER_MODEL="/models/$MODEL_BASE"
SLUG=$(printf '%s' "${MODEL_BASE%.gguf}" | tr '[:upper:]' '[:lower:]' |
    tr -c 'a-z0-9' '-' | sed -e 's/-\{1,\}/-/g' -e 's/^-//' -e 's/-$//')
[ -n "$CELL" ] || CELL=$SLUG
[ -n "$SERVED_NAME" ] || SERVED_NAME=$SLUG
[ -n "$CELL" ] || die "the cell name derived from '$MODEL_BASE' is empty; pass --cell"
[ -n "$RUN_PREFIX" ] || RUN_PREFIX="placement-$SLUG-$(date -u +%Y-%m-%d)"

CTX_TOTAL=$((CTX_SLOT * NP))
OUT="$OUT_DIR/$OUT_NAME"
JSON="$OUT_DIR/$JSON_NAME"
MEASUREMENTS="records/measurements"
RUN_A1="$RUN_PREFIX-ncmoe$NCMOE_A-a"
RUN_A2="$RUN_PREFIX-ncmoe$NCMOE_A-b"
RUN_B="$RUN_PREFIX-ncmoe$NCMOE_B-a"

# --------------------------------------------------------------------------
# emission -- one append per line, so a hard lock keeps what was measured
# --------------------------------------------------------------------------

# stamp/row validate everything before their single printf, so a rejected line
# appends nothing. The callee runs in THIS shell (a redirection forks nothing),
# which is what keeps start_stamp's reading available to rig_assert_unchanged.
emit() {
    "$@" >>"$OUT"
}

label_for() {
    local ncmoe=$1 base
    base=$(arm_label "$ARM" "$CELL") || return 1
    printf '%s np=%s ctx_slot=%s c=%s ncmoe=%s' "$base" "$NP" "$CTX_SLOT" "$CTX_TOTAL" "$ncmoe"
}

# --------------------------------------------------------------------------
# the two cells
# --------------------------------------------------------------------------

DOCKER_ARGV=()
launch_argv() {
    local ncmoe=$1
    DOCKER_ARGV=(
        docker run -d --name "$CONTAINER" --runtime=nvidia --gpus all
        -v "$MODEL_DIR:/models" -p "$PORT:$PORT" "${IMG_DIGEST:-$IMG}"
        -m "$CONTAINER_MODEL" --alias "$SERVED_NAME" --host 0.0.0.0 --port "$PORT"
        --parallel "$NP" -c "$CTX_TOTAL" -ngl 99 --n-cpu-moe "$ncmoe"
    )
}

MEASURE_ARGV=()
measure_argv() {
    local run=$1
    MEASURE_ARGV=(
        uv run --no-sync python tools/breadth/measure.py
        --endpoint "http://127.0.0.1:$PORT" --protocol openai
        --model "$SERVED_NAME" --tier "$TIER" --draws "$DRAWS"
        --out "$MEASUREMENTS/$run/$TIER"
    )
    if [ -n "$TASKS" ]; then
        MEASURE_ARGV+=(--tasks "$TASKS")
    fi
}

print_argv() {
    printf '%q ' "$@"
    printf '\n'
}

LAUNCH_LOG=
launch_cell() {
    local ncmoe=$1 i code
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    [ -z "$LAUNCH_LOG" ] || rm -f "$LAUNCH_LOG"
    LAUNCH_LOG=$(mktemp)
    launch_argv "$ncmoe"
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

log_last_line() {
    grep -v '^[[:space:]]*$' "$LAUNCH_LOG" 2>/dev/null | tail -n 1 | tr '\t' ' ' | cut -c1-200
}

gpu_process_mib() {
    nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits 2>/dev/null |
        awk '{ s += $1 + 0 } END { if (s > 0) printf "%d", s }'
}

# The build the rows were served by. Read from the manifest measure.py wrote if
# it recorded one (llama-server answers no /api/version, so it often will not),
# else the image identity docker reports. Both are read; neither is invented.
serving_build_for() {
    local run=$1 recorded id
    recorded=$(uv run --no-sync python -c '
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
v = json.loads(p.read_text()).get("serving_build") if p.is_file() else None
print(v if v else "")
' "$ROOT/$MEASUREMENTS/$run/$TIER/run.json" 2>/dev/null) || recorded=
    if [ -n "$recorded" ]; then
        _tok "$recorded"
        return 0
    fi
    id=$(docker image inspect -f '{{.Id}}' "$IMG" 2>/dev/null) || id=
    [ -n "$id" ] || {
        printf 'srv1-moe-slots: neither %s/run.json nor docker image inspect of %s names a serving build. The bound this null is judged against is keyed on it, so nothing is written.\n' "$run" "$IMG" >&2
        return 1
    }
    _tok "llama.cpp@$IMG@$id"
}

measure_pass() {
    local run=$1
    measure_argv "$run"
    say "measure: $run (tier $TIER, draws $DRAWS)"
    (cd "$ROOT" && "${MEASURE_ARGV[@]}")
}

# --------------------------------------------------------------------------
# the pairing. tools/bench/null.py's own compare() -- sampler drift (different
# bytes) separated from acceptance drift (same bytes, different verdict) -- and
# tools/bench/responsiveness.py's wilson upper for the bound. Neither is
# reimplemented here; a second implementation would be a second thing to drift.
# --------------------------------------------------------------------------

pair_kv() {
    local a=$1 b=$2
    (cd "$ROOT" && uv run --no-sync python - "$TIER" "$a" "$b" <<'PY'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("bench_null", "tools/bench/null.py")
null = importlib.util.module_from_spec(spec)
sys.modules["bench_null"] = null
assert spec.loader is not None
spec.loader.exec_module(null)

arm, run_a, run_b = sys.argv[1], sys.argv[2], sys.argv[3]
r = null.compare(arm, run_a, run_b)
n = len(r["shared"])
if not n:
    sys.exit(
        f"{run_a} and {run_b} share no cell under {arm}. Nothing was compared, "
        "so nothing is written: an empty pairing reports flips=0 for the same "
        "reason an unrun instrument does."
    )
print(f"cells={n}")
print(f"flips={len(r['flips'])}")
print(f"acceptance_drift={len(r['acceptance_flips'])}")
print(f"same_bytes={len(r['same_bytes'])}")
print(f"diff_bytes={len(r['diff_bytes'])}")
print(f"bound_pp={null.wilson(len(r['flips']), n)[1] * 100:.2f}")
PY
    )
}

kv_get() {
    printf '%s\n' "$1" | sed -n "s/^$2=//p" | head -n 1
}

# --------------------------------------------------------------------------
# dry run -- every cell's exact command line, nothing executed
# --------------------------------------------------------------------------

if [ "$DRY_RUN" -eq 1 ]; then
    printf '# 6-moe-slots.sh --dry-run\n'
    printf '# artifacts: %s (created here, then appended one line at a time)\n#            %s\n' "$OUT" "$JSON"
    printf '# step 6 OWNS %s: it creates it. Step 7 (tools/runs/run.sh srv1-kernel-arms crash,\n' "$OUT_NAME"
    printf '# 7-crash.sh) appends to it and refuses to run before this script has.\n'
    if [ -e "$OUT" ]; then
        printf '# NOTE: %s already exists. A real run would STOP here (the door refuses it at gate 5).\n' "$OUT"
    fi
    printf '# arm %s / img %s / cell %s / model %s\n' "$ARM" "$IMG" "$CELL" "$MODEL"
    printf '# gate 3: image_digest %s resolves the tag once; the container runs the digest\n' "$IMG"
    printf '# two placement cells of one checkpoint at one width. That is the whole grid.\n'
    printf '\n## markers\n'
    printf '%s\n' "workload_stamp $WORKLOAD   # digest computed by tools/runs/rows.py itself"
    printf '%s\n' 'start_stamp; rig_stamp   # from _common.sh, read off this rig'
    printf '\n## cell A -- ncmoe=%s, fully resident. First: cheapest, and it prices the bound.\n' "$NCMOE_A"
    launch_argv "$NCMOE_A"
    print_argv "${DOCKER_ARGV[@]}"
    measure_argv "$RUN_A1"
    print_argv "${MEASURE_ARGV[@]}"
    measure_argv "$RUN_A2"
    print_argv "${MEASURE_ARGV[@]}"
    printf '# pair A/A -> ### SELFNULL row (the bound, on disk before cell B launches)\n'
    printf 'python tools/bench/null.py:compare(%q, %q, %q)\n' "$TIER" "$RUN_A1" "$RUN_A2"
    printf 'docker rm -f %s\n' "$CONTAINER"
    printf '\n## cell B -- ncmoe=%s, experts in host RAM. Last: this is the load srv1 locks under.\n' "$NCMOE_B"
    launch_argv "$NCMOE_B"
    print_argv "${DOCKER_ARGV[@]}"
    measure_argv "$RUN_B"
    print_argv "${MEASURE_ARGV[@]}"
    printf '# pair A/B -> PLACEMENT row + %s\n' "$JSON_NAME"
    printf 'python tools/bench/null.py:compare(%q, %q, %q)\n' "$TIER" "$RUN_A1" "$RUN_B"
    printf 'docker rm -f %s\n' "$CONTAINER"
    printf '\n## close\n'
    printf '%s\n' 'end_stamp; rig_assert_unchanged'
    exit 0
fi

# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

mkdir -p "$OUT_DIR" "$ROOT/$MEASUREMENTS"

# Gate 3: the tag becomes a digest, once, before anything is written or
# started. An image the daemon does not hold stops the run here, with nothing
# on disk.
IMG_DIGEST=$(image_digest "$IMG") || die "$IMG resolves to no digest on this host (docker image inspect failed); one image for both cells is the whole design, and it is not here"

# ---- ownership, enforced --------------------------------------------------
# ARTIFACT-CONTRACT.md section 4: `srv1-moe-slots.tsv` -> `6-moe-slots.sh`.
# This script creates that file. Step 7 appends to it and checks that this block
# is already there, so the order is 6-then-7 at both ends. If the file exists
# already, either step 7 jumped the queue (its own guard should have stopped it)
# or a previous step 6 is on disk -- and appending a second placement null under
# the first would file two runs as one measurement.
if [ -e "$OUT" ]; then
    die "$OUT already exists. This script CREATES that artifact (step 6); step 7 (tools/runs/run.sh srv1-kernel-arms crash, 7-crash.sh) only appends to it. Either a previous step 6 wrote it, or step 7 ran out of order. Move the file aside deliberately -- the door's gate 5 refuses this before the step starts, and nothing here replaces evidence."
fi
: >"$OUT"

trap teardown EXIT

say "artifact: $OUT (created by this script; step 7 appends to it)"
emit workload_stamp "$WORKLOAD"
# Which instrument produced the rows that follow. The WORKLOAD stamp above is
# the file's (section 2.1) and names the serving driver; these rows are the
# placement null's and came from measure.py paired through null.py.
emit stamp INSTRUMENT step=6 behaviour=10 measure=tools/breadth/measure.py \
    pairing=tools/bench/null.py "tier=$TIER"
emit start_stamp
emit round_stamp
emit rig_stamp

# ---- cell A: ncmoe=0, and the bound ---------------------------------------
say "cell A: ncmoe=$NCMOE_A"
if ! launch_cell "$NCMOE_A"; then
    die "the ncmoe=$NCMOE_A cell would not launch, so there is no pair and no bound. Last log line: $(log_last_line)"
fi
VRAM_A=$(gpu_process_mib)
emit row "$(label_for "$NCMOE_A")" CONFIG "arm=$ARM" "img=$IMG" "img_digest=$IMG_DIGEST" \
    "ncmoe=$NCMOE_A" "vram=${VRAM_A:-0}" "served=$SERVED_NAME" "tier=$TIER"
measure_pass "$RUN_A1"
emit row "$(label_for "$NCMOE_A")" MEASURED "arm=$ARM" "img=$IMG" \
    "ncmoe=$NCMOE_A" "run=$RUN_A1" "tier=$TIER" "draws=$DRAWS"
measure_pass "$RUN_A2"
emit row "$(label_for "$NCMOE_A")" MEASURED "arm=$ARM" "img=$IMG" \
    "ncmoe=$NCMOE_A" "run=$RUN_A2" "tier=$TIER" "draws=$DRAWS"
teardown

BOUND_KV=$(pair_kv "$RUN_A1" "$RUN_A2")
BOUND_CELLS=$(kv_get "$BOUND_KV" cells)
BOUND_FLIPS=$(kv_get "$BOUND_KV" flips)
BOUND_ACC=$(kv_get "$BOUND_KV" acceptance_drift)
BOUND_PP=$(kv_get "$BOUND_KV" bound_pp)
BUILD_A=$(serving_build_for "$RUN_A1") || die "no serving build for $RUN_A1"
# The bound is on disk before cell B is launched at all: if the offloaded cell
# locks the host, this run still priced its own instrument.
emit row "$(label_for "$NCMOE_A")" SELFNULL "arm=$ARM" "img=$IMG" \
    "ncmoe=$NCMOE_A" "run_a=$RUN_A1" "run_b=$RUN_A2" "tier=$TIER" \
    "cells=$BOUND_CELLS" "flips=$BOUND_FLIPS" "acceptance_drift=$BOUND_ACC" \
    "bound_pp=$BOUND_PP" "serving_build=$BUILD_A"

# ---- cell B: ncmoe=99, the offloaded placement ----------------------------
say "cell B: ncmoe=$NCMOE_B"
if ! launch_cell "$NCMOE_B"; then
    die "the ncmoe=$NCMOE_B cell would not launch. The bound above stands; there is no placement pair, and no placement-null.json is written, because nothing was compared. Last log line: $(log_last_line)"
fi
VRAM_B=$(gpu_process_mib)
emit row "$(label_for "$NCMOE_B")" CONFIG "arm=$ARM" "img=$IMG" "img_digest=$IMG_DIGEST" \
    "ncmoe=$NCMOE_B" "vram=${VRAM_B:-0}" "served=$SERVED_NAME" "tier=$TIER"
measure_pass "$RUN_B"
emit row "$(label_for "$NCMOE_B")" MEASURED "arm=$ARM" "img=$IMG" \
    "ncmoe=$NCMOE_B" "run=$RUN_B" "tier=$TIER" "draws=$DRAWS"
teardown

PAIR_KV=$(pair_kv "$RUN_A1" "$RUN_B")
PAIR_CELLS=$(kv_get "$PAIR_KV" cells)
PAIR_FLIPS=$(kv_get "$PAIR_KV" flips)
PAIR_ACC=$(kv_get "$PAIR_KV" acceptance_drift)
PAIR_SAME=$(kv_get "$PAIR_KV" same_bytes)
PAIR_DIFF=$(kv_get "$PAIR_KV" diff_bytes)
BUILD_B=$(serving_build_for "$RUN_B") || die "no serving build for $RUN_B"
emit row "$(label_for "$NCMOE_B")" PLACEMENT "arm=$ARM" "img=$IMG" \
    "run_a=$RUN_A1" "run_b=$RUN_B" "tier=$TIER" "cells=$PAIR_CELLS" \
    "flips=$PAIR_FLIPS" "acceptance_drift=$PAIR_ACC" "same_bytes=$PAIR_SAME" \
    "diff_bytes=$PAIR_DIFF" "serving_build=$BUILD_B"

# ---- placement-null.json --------------------------------------------------
# Section 4.1's shape, read with a bare Path.read_text. Every number below is
# recomputed here by null.compare() from the same two run directories the rows
# above name -- the shell never hands it a figure to write down.
say "writing $JSON"
(cd "$ROOT" && uv run --no-sync python - \
    "$JSON" "$TIER" "$RUN_A1" "$RUN_A2" "$RUN_B" "$SERVED_NAME" \
    "$NCMOE_A" "$NCMOE_B" "$BUILD_A" "$BUILD_B" <<'PY'
import importlib.util
import json
import pathlib
import sys
from datetime import UTC, datetime

spec = importlib.util.spec_from_file_location("bench_null", "tools/bench/null.py")
null = importlib.util.module_from_spec(spec)
sys.modules["bench_null"] = null
assert spec.loader is not None
spec.loader.exec_module(null)

(out, arm, run_a1, run_a2, run_b, model, ncmoe_a, ncmoe_b, build_a, build_b) = sys.argv[1:11]

pair = null.compare(arm, run_a1, run_b)
bound = null.compare(arm, run_a1, run_a2)
cells = len(pair["shared"])
bound_cells = len(bound["shared"])
if not cells or not bound_cells:
    sys.exit("a pairing shares no cell; nothing is written")
if build_a != build_b:
    sys.exit(
        f"the two placements were served by {build_a!r} and {build_b!r}. Two "
        "builds and two placements is two variables, and this file would "
        "declare a placement result that is not one."
    )

result = {
    "model": model,
    "tier": arm,
    "cells": cells,
    "run_a": {
        "n_cpu_moe": int(ncmoe_a),
        "serving_build": build_a,
        "run": f"{run_a1}/{arm}",
    },
    "run_b": {
        "n_cpu_moe": int(ncmoe_b),
        "serving_build": build_b,
        "run": f"{run_b}/{arm}",
    },
    "flips": len(pair["flips"]),
    "acceptance_drift": len(pair["acceptance_flips"]),
    "same_bytes": len(pair["same_bytes"]),
    "diff_bytes": len(pair["diff_bytes"]),
    "bound": {
        "serving_build": build_a,
        "cells": bound_cells,
        "bound_pp": round(null.wilson(len(bound["flips"]), bound_cells)[1] * 100, 2),
        "flips": len(bound["flips"]),
        "acceptance_drift": len(bound["acceptance_flips"]),
        "runs": [f"{run_a1}/{arm}", f"{run_a2}/{arm}"],
        "measured": datetime.now(UTC).strftime("%Y-%m-%d"),
        "why": (
            "This build has no committed bound in tools/bench/reproducibility.json, "
            "so the run priced its own null first: two identical passes at "
            f"n_cpu_moe={ncmoe_a} in one server session. The bound is the 95% Wilson "
            "upper on flips/cells, never the point estimate."
        ),
    },
    "measured": datetime.now(UTC).strftime("%Y-%m-%d"),
    "instrument": {
        "measure": "tools/breadth/measure.py",
        "pairing": "tools/bench/null.py",
    },
}
pathlib.Path(out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out}: flips={result['flips']} over {cells} cells", file=sys.stderr)
PY
)

emit end_stamp
if ! rig_assert_unchanged; then
    emit stamp RIGMOVED at=end
    printf 'srv1-moe-slots: THE RIG MOVED UNDER THIS RUN. That is a FINDING, not a script fault: a hard lock wipes the BIOS power profile, and srv1 has already read PL1 95 W at 05:23 and 4095 W at 05:57 on one boot. The ncmoe=%s cell is the load that does it. The rows above were not all produced under one machine state -- report the START/END pair as measured.\n' "$NCMOE_B" >&2
    exit 3
fi
say "done: $OUT and $JSON"
