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
# them); when it states a launch.seccomp profile that is not a file beside
# fleet.yaml; or when its image resolves to another digest than the digests file
# recorded (image_id in one file, image in the other).
#
# THE SECCOMP A UNIT STATES (owner ruling, 2026-09-16: "Fix PR: allow
# io_uring"). A unit's launch may state `seccomp:`, a profile file named
# relative to fleet-setup/. It is passed as `--security-opt seccomp=<file>`,
# absolute: the docker CLI reads the profile itself and sends its JSON to the
# daemon, and under the door that CLI runs HERE, against the rig's daemon over
# `-H ssh://<rig>`, so nothing is installed on the rig. A unit that states none
# is launched exactly as before, under docker's default profile.
#
# A FAILED START KEEPS ITS WHOLE LOG (owner ruling, 2026-09-15). When the
# container exits, or does not say ok on /health in 900 s, its whole `docker
# logs` (stdout and stderr, every line, through the door's shim) is filed in the
# envelope as <artifact stem>.<unit>.docker.log before anything removes it, and
# `failure` names that file. The wrapper does not declare it: gate 8 holds each
# declared name to exist, and this one exists only when a start failed
# (lockfleets.keep_log writes it once, never through a link).
#
# A FAILED START FILES ITS EXIT CAUSE (owner ruling, 2026-09-15: "Fix PR, then
# one diagnostic start"). Whenever the step fails after `docker run` — the
# container exited before /health said ok, said no ok in 900 s, or anything later
# failed while it exists — the container's whole State (`docker inspect`, through
# the door's docker shim: ExitCode, OOMKilled, Error, StartedAt, FinishedAt,
# Status and the rest) and the rig's kernel log from the START marker to now
# (`journalctl -k`, through the door's ssh shim) are filed in the artifact's
# `exit` before anything removes the container, and `failure` names the exit
# code and OOMKilled. A read that fails is filed as what it said; it is never a
# stop. The cause is data: assemble_evidence.py check fails the entry for
# exiting, and does not judge why.
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
    if [ ! -f "$OUT" ]; then
        [ -s "$STATE/failure" ] || printf 'the step exited %s before it wrote its artifact\n' "$rc" >"$STATE/failure"
    fi
    if [ -n "$STARTED" ]; then
        # A failure after `docker run` that has not filed the exit cause yet.
        if [ "$rc" -ne 0 ] && [ ! -f "$OUT" ] && [ ! -e "$STATE/exit-said" ]; then
            file_exit
            printf '%s; %s\n' "$(cat "$STATE/failure")" "$(cat "$STATE/exit-said")" >"$STATE/failure.said" &&
                mv -f "$STATE/failure.said" "$STATE/failure" || true
        fi
        "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
    fi
    if [ ! -f "$OUT" ]; then
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

# The container's whole `docker logs`, filed in the envelope while it still
# exists; prints the file's name, or that none was kept.
keep_log() {
    "$DOCKER" logs "$NAME" >"$STATE/docker.log" 2>&1 || true
    _py "$LF" keep-log "$STATE/docker.log" "$RUN_OUT_DIR" "$ARTIFACT" "$UNIT" ||
        printf 'none kept (the step output says why)\n'
}

# The container's exit cause, filed while it still exists: its State through the
# door's docker shim, and the rig's kernel log from the START marker to now
# through the door's ssh shim. Neither read is a stop: one that fails is filed as
# its exit code and what it said. Leaves the failure line's words — the exit
# code and OOMKilled — in $STATE/exit-said.
file_exit() {
    local rc
    if "$DOCKER" inspect --format '{{json .State}}' "$NAME" >"$STATE/exit-state" 2>"$STATE/exit-state-err"; then rc=0; else rc=$?; fi
    printf '%s\n' "$rc" >"$STATE/exit-state-rc"
    printf 'journalctl -k --utc --no-pager -o short-iso-precise --since @%s --until now\n' \
        "$(cat "$STATE/start_epoch" 2>/dev/null)" >"$STATE/kernel-log-command"
    if "$SSH" "$RUN_HOST" "$(cat "$STATE/kernel-log-command")" >"$STATE/kernel-log" 2>"$STATE/kernel-log-err" </dev/null; then rc=0; else rc=$?; fi
    printf '%s\n' "$rc" >"$STATE/kernel-log-rc"
    _py "$LF" exit-said "$STATE" >"$STATE/exit-said" ||
        printf 'the exit cause could not be put in words; what was read is in the artifact\n' >"$STATE/exit-said"
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
# The START marker's time: a failed start's kernel log is read from it.
date -u +%s >"$STATE/start_epoch"
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
    if [ "$(date +%s)" -ge "$DEADLINE" ]; then
        kept=$(keep_log)
        file_exit
        fail "$NAME did not say ok on /health in 900 s; its whole docker logs: $kept; $(cat "$STATE/exit-said")"
    fi
    polls=$((polls + 1))
    if [ $((polls % 10)) -eq 0 ]; then
        running=$("$DOCKER" inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null || true)
        if [ "$running" != true ]; then
            kept=$(keep_log)
            file_exit
            fail "$NAME exited before /health said ok: $("$DOCKER" logs --tail 8 "$NAME" 2>&1 | tr '\n\t' '  ' | cut -c1-600); its whole docker logs: $kept; $(cat "$STATE/exit-said")"
        fi
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
