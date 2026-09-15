#!/usr/bin/env bash
# What holds a rig right now, as whitespace-free `key=value` lines.
#
# SHIPPED TO THE RIG ON STDIN behind rig-snapshot.sh, as one reading, by the
# door's `read` (gate-scripts/read-02-rig.py). Nothing lands on the rig's disk,
# nothing is started, stopped or leased. Its arguments are the units the fleet
# places on this rig, `ENGINE:PORT:CONTAINER` each (`ENGINE:PORT` for a unit
# the lock names no container for).
#
#   container=NAME,ID,PROJECT,RESTARTS   every running container. PROJECT is its
#                                         compose project or `-`; RESTARTS is
#                                         docker's RestartCount or `unread`,
#                                         never a 0 nobody read
#   gpu_app=PID,MIB,CONTAINER,PROCESS    every compute process on the card, and
#                                         the container its /proc/PID/cgroup
#                                         names: a 64-hex id, `none` (in no
#                                         container) or `unread`
#   sleeping=PORT,true|false|unknown     a vLLM unit's own /is_sleeping
#   status=PORT,BASE64                   the unit's in-flight page, as served:
#                                         /metrics for vLLM, /slots otherwise
#   backend=PORT,BACKEND|none            the attention backend a vLLM unit's
#                                         start-up log line names, or `none`
#                                         when no line names one (owner,
#                                         2026-09-15, B4: never guessed)
#
# Two single readings, for the load `read --load` runs on the rig (the harness
# ships this same text back to bash): `--card-holders` prints only the gpu_app
# rows, and `--restarts ID` only that container's restart count.
set -u

fail() { printf 'rig-units: %s\n' "$*" >&2; exit 1; }

# One whitespace-free, comma-free token: a row's fields are split on commas.
tok() { printf '%s' "$*" | tr -s ' \t\n,' '_' | sed -e 's/^_//' -e 's/_$//'; }

restarts_of() {
    local restarts
    restarts=$(docker inspect --format '{{.RestartCount}}' "$1" 2>/dev/null) || restarts=
    restarts=$(tok "$restarts")
    case $restarts in ''|*[!0-9]*) restarts=unread ;; esac
    printf '%s\n' "$restarts"
}

containers_up() {
    local listed id name project
    listed=$(docker ps --no-trunc --format '{{.ID}}|{{.Names}}|{{.Label "com.docker.compose.project"}}' 2>/dev/null) ||
        fail "cannot list containers (docker ps)"
    printf '%s\n' "$listed" | while IFS='|' read -r id name project; do
        [ -n "$id" ] || continue
        project=$(tok "${project:-}")
        printf 'container=%s,%s,%s,%s\n' "$(tok "$name")" "$(tok "$id")" "${project:--}" "$(restarts_of "$id")"
    done
}

card_holders() {
    local out pid mib name cid
    out=$(nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader,nounits 2>/dev/null) ||
        fail "cannot list the card's compute processes (nvidia-smi --query-compute-apps)"
    printf '%s\n' "$out" | while IFS=, read -r pid mib name; do
        pid=$(tok "${pid:-}"); mib=$(tok "${mib:-}"); name=$(tok "${name:-}")
        case $pid in ''|*[!0-9]*) continue ;; esac
        case $mib in ''|*[!0-9]*) mib=unread ;; esac
        if [ -r "/proc/$pid/cgroup" ]; then
            cid=$(grep -oE '[0-9a-f]{64}' "/proc/$pid/cgroup" 2>/dev/null | head -n 1)
            cid=${cid:-none}
        else
            cid=unread
        fi
        printf 'gpu_app=%s,%s,%s,%s\n' "$pid" "$mib" "$cid" "${name:-unnamed}"
    done
}

# The backend the start-up line names, from that line alone: the 09-13 method's
# tokens (records/measurements/fleet-setup-2026-09-13/srv2/measure_vllm.py), but
# never a token met elsewhere in the log, which is a list of what is available.
backend_of() {
    local line found
    line=$(docker logs "$1" 2>&1 | grep -i -m 1 -E 'attention[ _]backend')
    found=$(printf '%s' "$line" | grep -oE 'FLASH_ATTENTION|FLASH_ATTN|FLASHINFER|TRITON_ATTN' | head -n 1)
    printf '%s' "${found:-none}"
}

unit_pages() {
    local arg engine rest port container said state path page
    for arg in "$@"; do
        engine=${arg%%:*}
        rest=${arg#*:}
        port=${rest%%:*}
        container=
        case $rest in *:*) container=${rest#*:} ;; esac
        case $port in ''|*[!0-9]*) fail "not ENGINE:PORT[:CONTAINER]: $arg" ;; esac
        path=/slots
        if [ "$engine" = vllm ]; then
            path=/metrics
            said=$(curl -s -m 5 "http://127.0.0.1:$port/is_sleeping" 2>/dev/null) || said=
            said=$(printf '%s' "$said" | tr -d ' \t\n')
            case $said in
                *'"is_sleeping":true'*) state=true ;;
                *'"is_sleeping":false'*) state=false ;;
                *) state=unknown ;;
            esac
            printf 'sleeping=%s,%s\n' "$port" "$state"
            if [ -n "$container" ]; then
                printf 'backend=%s,%s\n' "$port" "$(backend_of "$container")"
            fi
        fi
        if page=$(curl -s -f -m 10 "http://127.0.0.1:$port$path" 2>/dev/null); then
            printf 'status=%s,%s\n' "$port" "$(printf '%s' "$page" | base64 -w0)"
        fi
    done
}

case "${1:-}" in
    --card-holders) card_holders; exit 0 ;;
    --restarts) restarts_of "${2:-}"; exit 0 ;;
esac
containers_up
card_holders
unit_pages "$@"
