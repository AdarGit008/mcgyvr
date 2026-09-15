#!/usr/bin/env bash
# What holds a rig right now, as whitespace-free `key=value` lines.
#
# SHIPPED TO THE RIG ON STDIN behind rig-snapshot.sh, as one reading, by the
# door's `read` (gate-scripts/read-02-rig.py). Nothing lands on the rig's disk,
# nothing is started, stopped or leased. Its arguments are the units the fleet
# places on this rig, `ENGINE:PORT` each.
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
set -u

fail() { printf 'rig-units: %s\n' "$*" >&2; exit 1; }

# One whitespace-free, comma-free token: a row's fields are split on commas.
tok() { printf '%s' "$*" | tr -s ' \t\n,' '_' | sed -e 's/^_//' -e 's/_$//'; }

containers_up() {
    local listed id name project restarts
    listed=$(docker ps --no-trunc --format '{{.ID}}|{{.Names}}|{{.Label "com.docker.compose.project"}}' 2>/dev/null) ||
        fail "cannot list containers (docker ps)"
    printf '%s\n' "$listed" | while IFS='|' read -r id name project; do
        [ -n "$id" ] || continue
        restarts=$(docker inspect --format '{{.RestartCount}}' "$id" 2>/dev/null) || restarts=
        restarts=$(tok "$restarts")
        case $restarts in ''|*[!0-9]*) restarts=unread ;; esac
        project=$(tok "${project:-}")
        printf 'container=%s,%s,%s,%s\n' "$(tok "$name")" "$(tok "$id")" "${project:--}" "$restarts"
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

unit_pages() {
    local arg engine port said state path page
    for arg in "$@"; do
        engine=${arg%%:*}
        port=${arg##*:}
        case $port in ''|*[!0-9]*) fail "not ENGINE:PORT: $arg" ;; esac
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
        fi
        if page=$(curl -s -f -m 10 "http://127.0.0.1:$port$path" 2>/dev/null); then
            printf 'status=%s,%s\n' "$port" "$(printf '%s' "$page" | base64 -w0)"
        fi
    done
}

containers_up
card_holders
unit_pages "$@"
