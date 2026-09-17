#!/usr/bin/env bash
# tools/runs/campaigns/lock-fleets/_move.sh — one timed switch move on one rig.
#
# lock-fleets (owner, 2026-09-15). A move is what `mcgyvr.fleet.lock` keys a
# switch's dev run by: one rig's slots in FROM_FLEET's layout, then in
# TO_FLEET's. Each side is either one llama.cpp unit, started with `docker run`
# as <RUN_ID>-<unit>, or a group of vLLM units, started together by
# `docker compose -p mcgyvr -f -` from the file `mcgyvr emit` writes for it,
# which comes on stdin (COMPOSE).
#
# Every rig timed the same way, srv1's 2026-09-13 way
# (records/measurements/fleet-setup-2026-09-13/srv1/measure_move.py:72-102):
# the source is brought up healthy untimed; then ONE ssh runs the stopwatch on
# the rig, stamped by the rig's own `date +%s.%N`: t0 as the source's stop is
# issued, the page cache dropped (its return code filed), the target started —
# t1 after `docker run -d` returns, or t1 just before `docker compose up -d`
# and t_compose after it, since compose waits on each dependency's health —
# and each target unit polled at 127.0.0.1 every 1 s, 5 s a try, up to 900 s,
# to t2. The docker verbs are in the ssh argv as words, so the shim's spend
# check and the lease still see them. Stamps are teed to
# ~/mcgyvr-relock/<RUN_ID>.move and read back by a second ssh, because a lock
# takes the ssh pipe with it (okf/must-read/touching-rigs.md). The artifact
# carries downtime_s = max(t2) - t0 and wake_s[u] = t2_u - t1; it judges none.
#
# REFUSED (exit 2, the artifact written with its `failure`) before the rig is
# started on, when the rig is not the door's; the move is not a listed switch
# on it; a side is neither one llama.cpp unit nor a vLLM group; the door's
# --model is no llama.cpp unit of the move, or its --parallel/--ctx-per-slot/
# --ubatch are not that unit's; a unit's launch is not its digests' fields; an
# image resolves to another digest; or, for a compose side, COMPOSE is missing,
# is not byte-identical to mcgyvr.emit.emit_locked's file, or names other
# containers than fleet.yaml.
#
# A FAILED START KEEPS ITS WHOLE LOG (owner ruling, 2026-09-15). When the source
# does not come up healthy, or the timed ssh ends before every target said
# healthy, each container of that side has its whole `docker logs` (stdout and
# stderr, every line, through the door's shim) filed in the envelope as
# <artifact stem>.<unit>.docker.log before anything removes it, and `failure`
# names those files. The wrapper does not declare them: gate 8 holds each
# declared name to exist, and these exist only when a start failed
# (lockfleets.keep_log writes each once, never through a link).
#
# Usage: a use's numbered wrapper declares the artifact and runs
#   exec bash ../_move.sh <artifact>.json RIG FROM_FLEET TO_FLEET "$@"
# with the compose file, when a side needs one, as the door's `-- COMPOSE`.
# shellcheck disable=SC2016

[ -n "${RUN_ID:-}" ] || { echo "_move.sh: RUN_ID is unset — start a lock-fleets wrapper through the door: python -m mcgyvr.serving.run --host <rig> --campaign lock-fleets --step <wrapper> --model <a llama.cpp unit's --model> --parallel <its -np> --ctx-per-slot <its -c/-np> [-- COMPOSE]" >&2; exit 2; }

set -euo pipefail

ARTIFACT=${1:-}
RIG=${2:-}
FROM_FLEET=${3:-}
TO_FLEET=${4:-}
COMPOSE=${5:-}

# shellcheck source=../../_common.sh disable=SC1091
. "$RUN_ROOT/tools/runs/_common.sh"
door_required

if [ -z "$ARTIFACT" ] || [ -z "$RIG" ] || [ -z "$FROM_FLEET" ] || [ -z "$TO_FLEET" ]; then
    _fail "usage: _move.sh ARTIFACT RIG FROM_FLEET TO_FLEET [COMPOSE] — a use's wrapper names the first four" || exit 2
fi

HERE=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LF=$HERE/lockfleets.py
DOCKER=$(_door_shim docker) || exit 2
SSH=$(_door_shim ssh) || exit 2
OUT=$RUN_OUT_DIR/$ARTIFACT
STATE=$(mktemp -d)
MOVE_ALL_NAMES=
STARTED=
date -u +%Y-%m-%dT%H:%M:%SZ >"$STATE/started_at"

# Whatever happened, what this run started is removed and the artifact exists. A
# run refused before its bring-up removes no container.
finish() {
    local rc=$?
    trap - EXIT
    if [ -n "$STARTED" ] && [ -n "$MOVE_ALL_NAMES" ]; then
        # shellcheck disable=SC2086
        "$DOCKER" rm -f $MOVE_ALL_NAMES >/dev/null 2>&1 || true
    fi
    if [ ! -f "$OUT" ]; then
        [ -s "$STATE/failure" ] || printf 'the step exited %s before it wrote its artifact\n' "$rc" >"$STATE/failure"
        _py "$LF" write-move "$STATE" "$OUT" || true
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

# keep_logs "CONTAINER=UNIT ..." — each container's whole `docker logs`, filed
# in the envelope while it still exists; prints the files' names.
keep_logs() {
    local pair kept=
    for pair in $1; do
        "$DOCKER" logs "${pair%%=*}" >"$STATE/docker.log" 2>&1 || true
        kept="$kept $(_py "$LF" keep-log "$STATE/docker.log" "$RUN_OUT_DIR" "$ARTIFACT" "${pair#*=}" ||
            printf 'none kept for %s' "${pair#*=}")"
    done
    printf '%s\n' "${kept# }"
}

# --- the refusals, before the rig is started on ------------------------------
FACTS=$(_py "$LF" move-facts "$RUN_ROOT" "$STATE" "$RIG" "$FROM_FLEET" "$TO_FLEET" "$COMPOSE") ||
    refuse "the move $FROM_FLEET -> $TO_FLEET on $RIG could not be read from fleet-setup/"
eval "$FACTS"
[ -z "$MOVE_REFUSED" ] || refuse "$MOVE_REFUSED"
DIGESTS=
for tag in $MOVE_IMAGES; do
    digest=$(image_digest "$tag") || refuse "image $tag resolves to no digest on $RUN_HOST"
    DIGESTS="$DIGESTS$tag=$digest"$'\n'
done
VALUES=$(_py "$LF" move-values "$RUN_ROOT" "$STATE" "$DIGESTS") || refuse "the move's launch could not be built"
eval "$VALUES"
[ -z "$MOVE_REFUSED" ] || refuse "$MOVE_REFUSED"
COMPOSE_IN=/dev/null
if [ "$MOVE_SOURCE_KIND" = compose ] || [ "$MOVE_TARGET_KIND" = compose ]; then
    COMPOSE_IN=$COMPOSE
fi

# --- the shell the rig runs: single-quoted, values put in by `render` --------
# Each @NAME@ is replaced with a value quoted here, on this side; every `$` is
# the rig's own.
PRELUDE='set -u
mkdir -p @RIG_DIR@
f=@RIG_FILE@
st() { printf "%s %s\n" "$1" "$(date +%s.%N)" | tee -a "$f"; }
rc() { printf "rc_%s %s\n" "$1" "$2" | tee -a "$f"; }
up() {
    end=$(( $(date +%s) + 900 ))
    while [ "$(date +%s)" -lt "$end" ]; do
        case $2 in
            vllm)
                if curl -sf -m 5 -o /dev/null "http://127.0.0.1:$3/v1/models" </dev/null; then st "t2 $1"; return 0; fi ;;
            *)
                body=$(curl -s -m 5 "http://127.0.0.1:$3/health" </dev/null) || body=
                case $body in ok|OK|*\"status\":\"ok\"*) st "t2 $1"; return 0 ;; esac ;;
        esac
        sleep 1
    done
    printf "timeout %s\n" "$1" | tee -a "$f"
    return 1
}
poll() { (IFS=:; set -- $1; up "$1" "$2" "$3"); }
'
SOURCE_RUN='docker rm -f @ALL_NAMES@ </dev/null >/dev/null 2>&1
docker run -d @SOURCE_RUN_ARGS@ </dev/null >/dev/null || exit 1
for p in @SOURCE_POLLS@; do poll "$p" </dev/null || exit 1; done
'
SOURCE_COMPOSE='docker rm -f @ALL_NAMES@ </dev/null >/dev/null 2>&1
docker compose -p @PROJECT@ -f - up -d >/dev/null || exit 1
for p in @SOURCE_POLLS@; do poll "$p" </dev/null || exit 1; done
'
TIMED_RUN='st t0
docker rm -f @SOURCE_NAMES@ </dev/null >/dev/null 2>&1; rc stop $?
sudo -n sh -c "echo 3 > /proc/sys/vm/drop_caches" </dev/null; rc drop $?
docker run -d @TARGET_RUN_ARGS@ </dev/null >/dev/null; rc run $?
st t1
ok=0
for p in @TARGET_POLLS@; do poll "$p" </dev/null || ok=1; done
exit $ok
'
TIMED_COMPOSE='st t0
docker rm -f @SOURCE_NAMES@ </dev/null >/dev/null 2>&1; rc stop $?
sudo -n sh -c "echo 3 > /proc/sys/vm/drop_caches" </dev/null; rc drop $?
st t1
pids=
for p in @TARGET_POLLS@; do poll "$p" </dev/null & pids="$pids $!"; done
docker compose -p @PROJECT@ -f - up -d >/dev/null; rc compose $?
st t_compose
ok=0
for pid in $pids; do wait "$pid" || ok=1; done
exit $ok
'
TEARDOWN_RUN='docker rm -f @ALL_NAMES@ </dev/null >/dev/null 2>&1
exit 0
'
TEARDOWN_COMPOSE='docker rm -f @ALL_NAMES@ </dev/null >/dev/null 2>&1
docker compose -p @PROJECT@ -f - down >/dev/null 2>&1
exit 0
'

rendered() { # TEMPLATE RIG-FILE-SUFFIX
    printf '%s%s' "$PRELUDE" "$1" | _py "$LF" render "$STATE" "$2"
}

# --- START marker ------------------------------------------------------------
start_stamp >"$STATE/marker-start" || fail "$RUN_HOST could not be read for the START marker"
printf '%s\n' "$RUN_RIG_START" >"$STATE/snap-start"
"$SSH" "$RUN_HOST" "mkdir -p $RIG_DIR_REMOTE && cat >> $RIG_FILE_REMOTE" <"$STATE/marker-start" ||
    fail "the START marker could not be teed on $RUN_HOST"
"$SSH" "$RUN_HOST" "grep -E '^(pswpout|pgmajfault) ' /proc/vmstat" >"$STATE/vmstat-start" ||
    fail "/proc/vmstat could not be read on $RUN_HOST at START"

# --- the source, up and healthy: untimed ------------------------------------
if [ "$MOVE_SOURCE_KIND" = compose ]; then SOURCE=$SOURCE_COMPOSE; else SOURCE=$SOURCE_RUN; fi
SCRIPT=$(rendered "$SOURCE" source) || fail "the source's shell could not be rendered"
STARTED=1
set +e
"$SSH" "$RUN_HOST" "$SCRIPT" <"$COMPOSE_IN" >"$STATE/source.out" 2>&1
printf '%s\n' "$?" >"$STATE/source_exit"
set -e
if [ "$(cat "$STATE/source_exit")" != 0 ]; then
    kept=$(keep_logs "$MOVE_SOURCE_CONTAINERS")
    fail "the source, $FROM_FLEET on $RIG, did not come up healthy; nothing was timed; its whole docker logs: $kept"
fi

# --- the ONE timed ssh -------------------------------------------------------
if [ "$MOVE_TARGET_KIND" = compose ]; then TIMED=$TIMED_COMPOSE; else TIMED=$TIMED_RUN; fi
SCRIPT=$(rendered "$TIMED" move) || fail "the stopwatch's shell could not be rendered"
set +e
"$SSH" "$RUN_HOST" "$SCRIPT" <"$COMPOSE_IN" >"$STATE/timed.out"
printf '%s\n' "$?" >"$STATE/ssh_exit"
set -e
if [ "$(cat "$STATE/ssh_exit")" != 0 ]; then
    kept=$(keep_logs "$MOVE_TARGET_CONTAINERS")
    printf '%s\n' "the timed ssh exited $(cat "$STATE/ssh_exit") before every target of $TO_FLEET on $RIG said healthy; their whole docker logs: $kept" >"$STATE/failure"
fi

# --- teardown ------------------------------------------------------------------
if [ "$COMPOSE_IN" = /dev/null ]; then TEARDOWN=$TEARDOWN_RUN; else TEARDOWN=$TEARDOWN_COMPOSE; fi
SCRIPT=$(rendered "$TEARDOWN" teardown) || fail "the teardown's shell could not be rendered"
"$SSH" "$RUN_HOST" "$SCRIPT" <"$COMPOSE_IN" >/dev/null 2>&1 || true

# --- the stamps, read back from the rig; then END -----------------------------
"$SSH" "$RUN_HOST" "cat $RIG_FILE_REMOTE" >"$STATE/readback" || true
end_stamp >"$STATE/marker-end" || fail "$RUN_HOST could not be read for the END marker"
printf '%s\n' "$RUN_RIG_END" >"$STATE/snap-end"
"$SSH" "$RUN_HOST" "cat >> $RIG_FILE_REMOTE" <"$STATE/marker-end" || true
"$SSH" "$RUN_HOST" "grep -E '^(pswpout|pgmajfault) ' /proc/vmstat" >"$STATE/vmstat-end" || true

_py "$LF" write-move "$STATE" "$OUT" || fail "the artifact could not be written"
