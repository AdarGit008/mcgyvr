#!/bin/bash
# records/measurements/lock-fleets/drive.sh — one rig's frozen lock-fleets order, through the door.
#
# usage: bash records/measurements/lock-fleets/drive.sh RIG USE
#
# Runs RIG's entries of <USE>/RUNS.md in their frozen order, each as the exact
# door command plan.py wrote, under the dev config in fleet-setup/
# (MCGYVR_CONFIG). It reaches no rig itself: every ssh and docker is the door's.
# Per entry it mints a read's run id just before the read and holds it to the
# door's pattern, records started/ended/exit as a log row under a flock on the
# use folder (both rigs log into one RUNS.md), and runs
# `assemble_evidence.py check`: the first non-zero is `STOP <reason>`, exit 3.
# An exit code is logged and never decided on. An entry already logged is not
# run again, and every logged entry of this rig is checked again before the
# first new one; a failed entry with its one retry (<use>/retries.json, plan.py
# retry) passes that check, logged as failed and retried, and its retry is the
# entry after it. At the end it logs finished_at and, when the other rig
# finished first, that rig's idle tail. No fill work is added (owner,
# 2026-09-15).
#
# REFUSED (exit 2) with any RUN_* or DOCKER_* already set, which the door mints
# itself, or when a compose group use.json holds to live is not byte for byte
# the file `mcgyvr emit` writes for the dev fleet.
set -u
shopt -u patsub_replacement 2>/dev/null || true

RIG=${1:-}
USE=${2:-}
if [ -z "$RIG" ] || [ -z "$USE" ]; then
    echo "usage: bash records/measurements/lock-fleets/drive.sh RIG USE" >&2
    exit 2
fi
inherited=$(env | grep -oE '^(RUN|DOCKER)_[A-Za-z0-9_]*' | sort -u | tr '\n' ' ')
if [ -n "$inherited" ]; then
    echo "drive.sh: REFUSED — ${inherited}set in the calling environment; the door mints its own" >&2
    exit 2
fi

HERE=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
USE_DIR=$HERE/$USE
RUNS=$USE_DIR/RUNS.md
if [ ! -f "$RUNS" ]; then
    echo "drive.sh: REFUSED — $RUNS does not exist; freeze the use first: plan.py freeze --use $USE" >&2
    exit 2
fi
LOGS=$USE_DIR/logs/$RIG
mkdir -p "$LOGS"
LOG=$LOGS/drive.log
WINDOW_DATE=$(date -u +%F)
COMPOSE_DIR=$(mktemp -d)
trap 'rm -rf "$COMPOSE_DIR"' EXIT
export MCGYVR_CONFIG=$REPO/fleet-setup

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s %s %s\n' "$(now)" "$RIG" "$*" | tee -a "$LOG"; }
py() { (cd "$REPO" && uv run --no-sync python "$@"); }
plan() { py "$HERE/plan.py" "$@"; }
locked() { (flock -x 9 && "$@") 9<"$USE_DIR"; }
check() { # ENTRY [READ_RUN_ID]
    py "$HERE/assemble_evidence.py" check --use "$USE" --host "$RIG" --entry "$1" ${2:+--run-id "$2"} 2>&1
}
stop() { # ENTRY WHY
    log "STOP $1: $(printf '%s' "$2" | head -n 1)"
    printf '%s\n' "$2" >>"$LOG"
    locked plan event --use "$USE" --rig "$RIG" --event stopped --at "$(now)" >>"$LOG"
    exit 3
}

log "window date $WINDOW_DATE; the dev fleet's compose files go to $COMPOSE_DIR"
if ! (cd "$REPO" && uv run --no-sync mcgyvr emit --out "$COMPOSE_DIR") >>"$LOG" 2>&1; then
    log "REFUSED — mcgyvr emit wrote no compose files for the dev fleet"
    exit 2
fi
if ! MATCHES=$(plan live-compose --use "$USE" --rig "$RIG"); then
    log "REFUSED — use.json's live compose files could not be named"
    exit 2
fi
while IFS=$'\t' read -r name live; do
    [ -n "$name" ] || continue
    if ! cmp -s "$COMPOSE_DIR/$name" "$live"; then
        log "REFUSED — $COMPOSE_DIR/$name is not $live byte for byte, and use.json holds this group to what live serves"
        exit 2
    fi
    log "compose $name is the live file $live"
done <<<"$MATCHES"

if ! ENTRIES=$(plan entries --use "$USE" --rig "$RIG") || [ -z "$ENTRIES" ]; then
    log "REFUSED — $RUNS holds no entry for $RIG"
    exit 2
fi

while IFS=$'\t' read -r E _ <&3; do
    if plan logged --use "$USE" --entry "$E"; then
        if ! WHY=$(check "$E"); then
            stop "$E (logged before this start)" "$WHY"
        fi
        log "checked again: $(printf '%s' "$WHY" | head -n 1)"
    fi
done 3<<<"$ENTRIES"

locked plan log --use "$USE" --entry window --rig "$RIG" --window-date "$WINDOW_DATE" --started "$(now)"

while IFS=$'\t' read -r E KIND <&3; do
    if plan logged --use "$USE" --entry "$E"; then
        log "$E already logged; not run again"
        continue
    fi
    ARGV=()
    mapfile -d '' ARGV < <(plan argv --use "$USE" --entry "$E")
    [ "${#ARGV[@]}" -gt 0 ] || stop "$E" "plan.py gave no door command"
    RID=
    case $KIND in
        read | load)
            RID=run-$(date -u +%Y%m%dT%H%M%S)-$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
            [[ $RID =~ ^run-[0-9]{8}T[0-9]{6}-[0-9a-f]{8}$ ]] ||
                stop "$E" "minted $RID, which is not run-YYYYMMDDTHHMMSS-xxxxxxxx"
            ;;
    esac
    for i in "${!ARGV[@]}"; do
        arg=${ARGV[$i]}
        arg=${arg//@WINDOW_DATE@/$WINDOW_DATE}
        arg=${arg//@COMPOSE_DIR@/$COMPOSE_DIR}
        arg=${arg//@READ_RUN_ID@/$RID}
        ARGV[$i]=$arg
    done
    OUT=$LOGS/$E.out
    STARTED=$(now)
    log "$E $KIND: python -m mcgyvr.serving.run ${ARGV[*]}"
    (cd "$REPO" && uv run --no-sync python -m mcgyvr.serving.run "${ARGV[@]}") >"$OUT" 2>&1 </dev/null
    RC=$?
    ENDED=$(now)
    locked plan log --use "$USE" --entry "$E" --rig "$RIG" --window-date "$WINDOW_DATE" \
        --started "$STARTED" --ended "$ENDED" --exit "$RC" --read-run-id "$RID" --output "${OUT#"$REPO"/}"
    log "$E exited $RC (logged, not decided on)"
    if ! WHY=$(check "$E" "$RID"); then
        stop "$E" "$WHY"
    fi
done 3<<<"$ENTRIES"

FINISHED=$(now)
log "finished_at $FINISHED; $(locked plan event --use "$USE" --rig "$RIG" --event finished --at "$FINISHED")"
