#!/usr/bin/env bash
# tools/runs/campaigns/srv1-cpu-saturation/_arm.sh — one cold start of
# Qwen3.6-35B-A3B UD-IQ3_XXS on srv1 at one --n-cpu-moe, all eight slots driven.
#
# Owner, 2026-09-16: the footprint-versus-stream test okf/must-read/touching-rigs.md
# names as outstanding, approved with its hard-lock risk. Three arms differ in
# --n-cpu-moe only: A1 = 30 (the live b-big placement's depth), A2 = 36, A3 = 40
# (every expert block in host RAM, 69% of srv1's 15 GB at only ~331 MB per
# token). Everything else is the srv1 launch shape fleet.yaml locks:
# --parallel 8, -c 32768 (4096 a slot), -b 512 -ub 512 -fa on -ctk q8_0 -ctv
# q8_0 -ngl 99 -t 6, under hosts.json's srv1 image resolved to its digest.
#
# What one arm does, in order, each part filed in the artifact whether or not
# the next ran: the START marker (uptime_since, pl1_uw from
# constraint_0_power_limit_uw, pl2_uw, ram_mt_s) teed on the rig under
# ~/mcgyvr-relock/<RUN_ID>.cpusat, because a lock takes the ssh pipe with it;
# /proc/vmstat pswpout and pgmajfault; the container started as
# <RUN_ID>-qwen36 and its wake to /health ok timed; the lock's own harness
# (mcgyvr/fleet/harness.py) on the rig — the measure (warm decode and prefill
# at n=1, every sample), then the load: 8 requests each filling a 4096-token
# slot, 30 s, the card sampled until the unit reads idle — with per-core CPU
# sampled on the rig once a second (mpstat -P ALL when sysstat is there,
# /proc/stat deltas otherwise) from before the load starts until the
# aggregate pass ends; the aggregate pass, 8 concurrent 256-token decodes
# read from the server's own timings, twice; restarts; the END marker; the
# samples and markers read back. The step judges nothing: the peak and mean
# all-core utilisation per phase, the aggregate tok/s, the swap delta and
# whether the markers moved are filed for the report.
#
# REFUSED (exit 2) before the rig is touched when the door's --model is not the
# Qwen3.6-35B blob, --parallel is not 8, --ctx-per-slot is not 4096 or --ubatch
# is not 512: data-30 sized this run from them, and the arm is that shape.
#
# Usage: a numbered step declares its artifact and runs
#   exec bash _arm.sh <artifact>.json <ARM> <n-cpu-moe> "$@"

[ -n "${RUN_ID:-}" ] || { echo "_arm.sh: RUN_ID is unset — start a numbered step through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-cpu-saturation --step <numbered step> --model /home/adaramir/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf --parallel 8 --ctx-per-slot 4096 --ubatch 512" >&2; exit 2; }

set -euo pipefail

ARTIFACT=${1:-}
ARM=${2:-}
NCMOE=${3:-}

# shellcheck source=../../_common.sh disable=SC1091
. "$RUN_ROOT/tools/runs/_common.sh"
door_required

if [ -z "$ARTIFACT" ] || [ -z "$ARM" ] || [ -z "$NCMOE" ]; then
    _fail "usage: _arm.sh ARTIFACT ARM N_CPU_MOE — a numbered step names all three" || exit 2
fi

HERE=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CS=$HERE/cpusat.py
DOCKER=$(_door_shim docker) || exit 2
SSH=$(_door_shim ssh) || exit 2
UNITS_READER=${RUN_BIN%/}/../rig-units.sh
NAME=$RUN_ID-qwen36
OUT=$RUN_OUT_DIR/$ARTIFACT
PORT=8080
WIDTH=8
WINDOW=4096
BLOB=Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf
STATE=$(mktemp -d)
STARTED=
SAMPLER_PID=
# A hard lock takes an established ssh with it and nothing times that out by
# default; these end a long call within three minutes of the rig going silent,
# so the step files what it has instead of hanging (touching-rigs.md).
KEEPALIVE=(-o ServerAliveInterval=15 -o ServerAliveCountMax=12)
date -u +%Y-%m-%dT%H:%M:%SZ >"$STATE/started_at"
RIG_FILE=$(_py "$CS" remote-file "$RUN_ID" cpusat)
CPU_FILE=$(_py "$CS" remote-file "$RUN_ID" cpu)
STOP_FILE=$(_py "$CS" remote-file "$RUN_ID" cpu.stop)

finish() {
    local rc=$?
    trap - EXIT
    if [ -n "$SAMPLER_PID" ]; then
        "$SSH" "$RUN_HOST" "touch $STOP_FILE" </dev/null >/dev/null 2>&1 || true
        stop_sampler
    fi
    if [ ! -f "$OUT" ]; then
        [ -s "$STATE/failure" ] || printf 'the step exited %s before it wrote its artifact\n' "$rc" >"$STATE/failure"
    fi
    if [ -n "$STARTED" ]; then
        if [ "$rc" -ne 0 ] && [ ! -e "$STATE/exit-state" ]; then
            "$DOCKER" inspect --format '{{json .State}}' "$NAME" >"$STATE/exit-state" 2>/dev/null || true
        fi
        "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
    fi
    if [ ! -f "$OUT" ]; then
        _py "$CS" write "$STATE" "$OUT" || true
    fi
    rm -rf "$STATE"
    exit "$rc"
}
trap finish EXIT

refuse() {
    printf '%s\n' "$*" >"$STATE/failure"
    _fail "REFUSED — $*" || true
    exit 2
}

fail() {
    printf '%s\n' "$*" >"$STATE/failure"
    _fail "$*" || true
    exit 1
}

keep_log() {
    "$DOCKER" logs "$NAME" >"$STATE/docker.log" 2>&1 || true
    _py "$CS" keep-log "$STATE/docker.log" "$RUN_OUT_DIR" "${ARTIFACT%.json}.docker.log" >"$STATE/docker-log-kept" ||
        printf 'none kept\n' >"$STATE/docker-log-kept"
    "$DOCKER" inspect --format '{{json .State}}' "$NAME" >"$STATE/exit-state" 2>/dev/null || true
}

rig_epoch() { "$SSH" "$RUN_HOST" 'date +%s.%N' </dev/null; }

# The sampler's ssh ends by itself once the stop file is on the rig; one that
# has not within 60 s (the rig gone silent) is ended here, never waited on.
stop_sampler() {
    local i=0
    while [ "$i" -lt 60 ] && kill -0 "$SAMPLER_PID" 2>/dev/null; do
        sleep 1
        i=$((i + 1))
    done
    kill "$SAMPLER_PID" 2>/dev/null || true
    wait "$SAMPLER_PID" 2>/dev/null || true
    SAMPLER_PID=
}

# --- the refusals, before the rig is touched --------------------------------
[ "$RUN_HOST" = srv1 ] || refuse "this campaign is srv1's, and the run is on $RUN_HOST"
[ "$(basename -- "$RUN_MODEL")" = "$BLOB" ] || refuse "--model $RUN_MODEL is not $BLOB, the blob every arm runs"
[ "${RUN_PARALLEL:-}" = "$WIDTH" ] || refuse "--parallel ${RUN_PARALLEL:-} is not $WIDTH: every arm drives all eight slots"
[ "${RUN_CTX_PER_SLOT:-}" = "$WINDOW" ] || refuse "--ctx-per-slot ${RUN_CTX_PER_SLOT:-} is not $WINDOW"
[ "${RUN_UBATCH:-}" = 512 ] || refuse "--ubatch ${RUN_UBATCH:-} is not 512"
case $NCMOE in '' | *[!0-9]*) refuse "N_CPU_MOE '$NCMOE' is not an integer" ;; esac
IMG=$(_py -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]["llamacpp_image"])' \
    "$RUN_ROOT/tools/runs/hosts.json" "$RUN_HOST") || refuse "hosts.json names no llamacpp_image for $RUN_HOST"
DIGEST=$(image_digest "$IMG") || refuse "image $IMG resolves to no digest on $RUN_HOST"
CTX=$((WIDTH * WINDOW))
ARGV=(--model "$RUN_MODEL" --n-cpu-moe "$NCMOE" --parallel "$WIDTH" --port "$PORT"
    -b 512 -ub 512 -c "$CTX" -fa on -ctk q8_0 -ctv q8_0 -ngl 99 -t 6)
_py - "$STATE/arm.json" "$ARM" "$NCMOE" "$IMG" "$DIGEST" "$CPU_FILE" "${ARGV[@]}" <<'PY'
import json
import sys

out, arm, ncmoe, image, digest, cpu_file, *argv = sys.argv[1:]
json.dump(
    {
        "arm": arm,
        "n_cpu_moe": int(ncmoe),
        "image": image,
        "digest": digest,
        "cpu_file": cpu_file,
        "argv": argv,
        "env": {"LLAMA_ARG_HOST": "0.0.0.0"},
    },
    open(out, "w", encoding="utf-8"),
)
PY

# --- 1. START marker and vmstat, teed on the rig ------------------------------
start_stamp >"$STATE/marker-start" || fail "$RUN_HOST could not be read for the START marker"
printf '%s\n' "$RUN_RIG_START" >"$STATE/snap-start"
"$SSH" "$RUN_HOST" "mkdir -p \"\$HOME\"/mcgyvr-relock && cat >> $RIG_FILE" <"$STATE/marker-start" ||
    fail "the START marker could not be teed on $RUN_HOST"
"$SSH" "$RUN_HOST" "grep -E '^(pswpout|pgmajfault) ' /proc/vmstat" >"$STATE/vmstat-start" </dev/null ||
    fail "/proc/vmstat could not be read on $RUN_HOST at START"

# --- 2. the unit, cold ----------------------------------------------------------
echo "srv1-cpu-saturation $ARM: $DIGEST ${ARGV[*]}"
STARTED=1
"$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
CID=$("$DOCKER" run -d --name "$NAME" --gpus all --network host \
    -v /home/adaramir/models:/home/adaramir/models:ro \
    -e LLAMA_ARG_HOST=0.0.0.0 "$DIGEST" "${ARGV[@]}") || fail "docker run of $ARM failed on $RUN_HOST"
printf '%s\n' "$CID" >"$STATE/container_id"

# --- 3. its wake, every 1 s up to 900 s ------------------------------------------
RAN=$(date +%s.%N)
DEADLINE=$((${RAN%.*} + 900))
polls=0
while :; do
    body=$(curl -s -m 5 "http://$RUN_HOST:$PORT/health" || true)
    case $body in
        ok | OK | *'"status":"ok"'*)
            awk -v a="$RAN" -v b="$(date +%s.%N)" 'BEGIN { printf "%.3f\n", b - a }' >"$STATE/wake_s"
            break
            ;;
    esac
    if [ "$(date +%s)" -ge "$DEADLINE" ]; then
        keep_log
        fail "$NAME did not say ok on /health in 900 s; its whole docker logs: $(cat "$STATE/docker-log-kept")"
    fi
    polls=$((polls + 1))
    if [ $((polls % 10)) -eq 0 ]; then
        running=$("$DOCKER" inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null || true)
        if [ "$running" != true ]; then
            keep_log
            fail "$NAME exited before /health said ok: $("$DOCKER" logs --tail 8 "$NAME" 2>&1 | tr '\n\t' '  ' | cut -c1-600); its whole docker logs: $(cat "$STATE/docker-log-kept")"
        fi
    fi
    sleep 1
done

# --- 4. the measure: warm decode and prefill at n=1, on the rig ------------------
HARNESS=$(_py -c 'from mcgyvr.fleet import harness; print(harness.__file__)') || fail "the harness could not be located"
PROBE="python3 - mcgyvr-harness '{\"mode\":\"probe\",\"engine\":\"llama.cpp\",\"port\":$PORT}'"
"$SSH" "${KEEPALIVE[@]}" "$RUN_HOST" "$PROBE" <"$HARNESS" >"$STATE/harness.json" || true

# --- 5. the CPU sampler, then the load with all eight slots ---------------------
_py "$CS" sampler "$RUN_ID" >"$STATE/sampler.sh"
"$SSH" "${KEEPALIVE[@]}" "$RUN_HOST" 'bash -s' <"$STATE/sampler.sh" >/dev/null 2>&1 &
SAMPLER_PID=$!
sleep 3
LOAD_SPEC=$(_py - "$PORT" "$WIDTH" "$WINDOW" "$CID" "$UNITS_READER" <<'PY'
import json
import shlex
import sys

port, width, window, cid, reader = sys.argv[1:6]
spec = {
    "mode": "load",
    "engine": "llama.cpp",
    "port": int(port),
    "width": int(width),
    "window": int(window),
    "container": cid,
    "poll": open(reader, encoding="utf-8").read(),
    "pace_path": None,
}
print(f"python3 - mcgyvr-harness {shlex.quote(json.dumps(spec))}")
PY
)
rig_epoch >"$STATE/load.t0" || true
"$SSH" "${KEEPALIVE[@]}" "$RUN_HOST" "$LOAD_SPEC" <"$HARNESS" >"$STATE/load.json" || true
rig_epoch >"$STATE/load.t1" || true

# --- 6. the aggregate pass: 8 x 256 tokens, twice, read from timings ------------
AGG="python3 - rig-agg '{\"port\":$PORT,\"width\":$WIDTH,\"n_predict\":256,\"rounds\":2}'"
rig_epoch >"$STATE/aggregate.t0" || true
"$SSH" "${KEEPALIVE[@]}" "$RUN_HOST" "$AGG" <"$CS" >"$STATE/aggregate.json" || true
rig_epoch >"$STATE/aggregate.t1" || true

# --- 7. the sampler stopped, restarts, END marker, everything read back ----------
"$SSH" "$RUN_HOST" "touch $STOP_FILE" </dev/null || true
stop_sampler
"$DOCKER" inspect --format '{{.RestartCount}}' "$CID" >"$STATE/restarts" 2>/dev/null || true
end_stamp >"$STATE/marker-end" || fail "$RUN_HOST could not be read for the END marker"
printf '%s\n' "$RUN_RIG_END" >"$STATE/snap-end"
"$SSH" "$RUN_HOST" "cat >> $RIG_FILE" <"$STATE/marker-end" || true
"$SSH" "$RUN_HOST" "grep -E '^(pswpout|pgmajfault) ' /proc/vmstat" >"$STATE/vmstat-end" </dev/null || true
"$SSH" "$RUN_HOST" "cat $RIG_FILE" >"$STATE/readback" </dev/null || true
"$SSH" "$RUN_HOST" "cat $CPU_FILE" >"$STATE/cpu.samples" </dev/null || true

# --- 8. the container removed, the artifact whole ------------------------------
"$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
STARTED=
_py "$CS" write "$STATE" "$OUT" || fail "the artifact could not be written"
