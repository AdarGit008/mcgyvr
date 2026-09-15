#!/usr/bin/env bash
# tools/runs/campaigns/lock-fleets/_unit.sh — one cold start of one llama.cpp unit.
#
# lock-fleets (owner, 2026-09-15) measures everything the fleet lock needs. This
# body starts the unit exactly as fleet.yaml states its launch, as
# <RUN_ID>-<unit>, times its wake to /health ok, runs the lock's own harness on
# the rig (mcgyvr/fleet/harness.py: the measure with every sample, then a load
# of W requests filling the unit's N-token window for at most 30 s), reads the
# container's restarts, and files one artifact whole. It judges nothing:
# records/measurements/lock-fleets/assemble_evidence.py does, from the artifact.
#
# REFUSED (exit 2, the artifact written with its `failure`) before a container
# starts, when the unit is not in fleet.yaml, is placed on another rig or is not
# llama.cpp; when its launch.argv or launch.env are not the fields its
# digests-<rig>.json hashed; when the door's --model, --parallel, --ctx-per-slot
# or --ubatch are not the unit's own (data-20 and data-30 sized the run from
# them); or when its image resolves to another digest than the digests file
# recorded (image_id in one file, image in the other).
#
# The START and END markers (uptime_since, pl1_uw, pl2_uw, ram_mt_s) and the
# rig's /proc/vmstat pswpout and pgmajfault are read at both ends. The markers
# are teed on the rig to ~/mcgyvr-relock/<RUN_ID>.unit and read back, because a
# lock takes the ssh pipe with it (okf/must-read/touching-rigs.md).
#
# Usage: a use's numbered wrapper declares the artifact and runs
#   exec bash ../_unit.sh <artifact>.json <unit> "$@"
# and the door passes the unit's own --model, --parallel and --ctx-per-slot.

[ -n "${RUN_ID:-}" ] || { echo "_unit.sh: RUN_ID is unset — start a lock-fleets wrapper through the door: python -m mcgyvr.serving.run --host <rig> --campaign lock-fleets --step <wrapper> --model <the unit's --model> --parallel <its -np> --ctx-per-slot <its -c/-np>" >&2; exit 2; }

set -euo pipefail

ARTIFACT=${1:-}
UNIT=${2:-}

# shellcheck source=../../_common.sh disable=SC1091
. "$RUN_ROOT/tools/runs/_common.sh"
door_required

if [ -z "$ARTIFACT" ] || [ -z "$UNIT" ]; then
    _fail "usage: _unit.sh ARTIFACT UNIT — a use's wrapper names both" || exit 2
fi

HERE=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LF=$HERE/lockfleets.py
DOCKER=$(_door_shim docker) || exit 2
SSH=$(_door_shim ssh) || exit 2
UNITS_READER=${RUN_BIN%/}/../rig-units.sh
NAME=$RUN_ID-$UNIT
OUT=$RUN_OUT_DIR/$ARTIFACT
STATE=$(mktemp -d)
STARTED=
date -u +%Y-%m-%dT%H:%M:%SZ >"$STATE/started_at"

# Whatever happened, the container this run started is removed and the artifact
# exists: a step that died says where, in `failure`. A run refused before its
# launch reaches no daemon at all.
finish() {
    local rc=$?
    trap - EXIT
    if [ -n "$STARTED" ]; then
        "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
    fi
    if [ ! -f "$OUT" ]; then
        [ -s "$STATE/failure" ] || printf 'the step exited %s before it wrote its artifact\n' "$rc" >"$STATE/failure"
        _py "$LF" write-unit "$STATE" "$OUT" || true
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

# --- the refusals, before the rig is touched --------------------------------
FACTS=$(_py "$LF" unit-facts "$RUN_ROOT" "$STATE" "$UNIT") ||
    refuse "the facts of $UNIT could not be read from fleet-setup/fleet.yaml and digests-$RUN_HOST.json"
eval "$FACTS"
[ -z "$UNIT_REFUSED" ] || refuse "$UNIT_REFUSED"
DIGEST=$(image_digest "$UNIT_IMAGE") || refuse "image $UNIT_IMAGE resolves to no digest on $RUN_HOST"
printf '%s\n' "$DIGEST" >"$STATE/digest"
[ "${DIGEST##*@}" = "$UNIT_RECORDED_IMAGE" ] ||
    refuse "image $UNIT_IMAGE resolves to $DIGEST on $RUN_HOST, and digests-$RUN_HOST.json records $UNIT_RECORDED_IMAGE"

# --- 1. START marker and vmstat ---------------------------------------------
start_stamp >"$STATE/marker-start" || fail "$RUN_HOST could not be read for the START marker"
printf '%s\n' "$RUN_RIG_START" >"$STATE/snap-start"
"$SSH" "$RUN_HOST" "mkdir -p $RIG_DIR_REMOTE && cat >> $RIG_FILE_REMOTE" <"$STATE/marker-start" ||
    fail "the START marker could not be teed on $RUN_HOST"
"$SSH" "$RUN_HOST" "grep -E '^(pswpout|pgmajfault) ' /proc/vmstat" >"$STATE/vmstat-start" ||
    fail "/proc/vmstat could not be read on $RUN_HOST at START"

# --- 2. the unit, as fleet.yaml states it -----------------------------------
mapfile -d '' LAUNCH < <(_py "$LF" run-args "$RUN_ROOT" "$UNIT" "$NAME" "$DIGEST")
[ "${#LAUNCH[@]}" -gt 0 ] || fail "no launch could be built for $UNIT from fleet.yaml"
STARTED=1
"$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
CID=$("$DOCKER" run -d "${LAUNCH[@]}") || fail "docker run of $UNIT failed on $RUN_HOST"
printf '%s\n' "$CID" >"$STATE/container_id"

# --- 3. its wake, every 1 s up to 900 s: data, not a verdict ----------------
RAN=$(date +%s.%N)
DEADLINE=$((${RAN%.*} + 900))
polls=0
while :; do
    body=$(curl -s -m 5 "http://$RUN_HOST:$UNIT_PORT/health" || true)
    case $body in
        ok | OK | *'"status":"ok"'*)
            awk -v a="$RAN" -v b="$(date +%s.%N)" 'BEGIN { printf "%.3f\n", b - a }' >"$STATE/wake_s"
            break
            ;;
    esac
    [ "$(date +%s)" -lt "$DEADLINE" ] || fail "$NAME did not say ok on /health in 900 s"
    polls=$((polls + 1))
    if [ $((polls % 10)) -eq 0 ]; then
        running=$("$DOCKER" inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null || true)
        [ "$running" = true ] ||
            fail "$NAME exited before /health said ok: $("$DOCKER" logs --tail 8 "$NAME" 2>&1 | tr '\n\t' '  ' | cut -c1-600)"
    fi
    sleep 1
done

# --- 4. the lock's harness on the rig: the measure, then the load -----------
# No timeout on either ssh: a load is held to its own 30 s and waits for the
# unit to read idle with no limit (owner rulings NB5, NBc).
HARNESS=$(_py "$LF" harness-path) || fail "the harness could not be located"
PROBE=$(_py "$LF" harness-command "$STATE" probe "$CID" "$UNITS_READER") || fail "no probe spec for $UNIT"
"$SSH" "$RUN_HOST" "$PROBE" <"$HARNESS" >"$STATE/harness.json" || true
LOAD=$(_py "$LF" harness-command "$STATE" load "$CID" "$UNITS_READER") || fail "no load spec for $UNIT"
"$SSH" "$RUN_HOST" "$LOAD" <"$HARNESS" >"$STATE/load.json" || true

# --- 5. restarts, then the END marker ---------------------------------------
"$DOCKER" inspect --format '{{.RestartCount}}' "$CID" >"$STATE/restarts" 2>/dev/null || true
end_stamp >"$STATE/marker-end" || fail "$RUN_HOST could not be read for the END marker"
printf '%s\n' "$RUN_RIG_END" >"$STATE/snap-end"
"$SSH" "$RUN_HOST" "cat >> $RIG_FILE_REMOTE" <"$STATE/marker-end" || true
"$SSH" "$RUN_HOST" "grep -E '^(pswpout|pgmajfault) ' /proc/vmstat" >"$STATE/vmstat-end" || true
"$SSH" "$RUN_HOST" "cat $RIG_FILE_REMOTE" >"$STATE/readback" || true

# --- 6. the artifact, whole --------------------------------------------------
_py "$LF" write-unit "$STATE" "$OUT" || fail "the artifact could not be written"
