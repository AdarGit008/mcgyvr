#!/usr/bin/env bash
# RUN_ARTIFACTS: sizing.tsv
#
# The door's default step: walk the derived --n-cpu-moe floor down onto the
# rig and let the rig judge it. Model-agnostic on purpose: the owner's rule is
# that the protocol is the default whatever the checkpoint, so nothing here
# reads a model name, only the placement the door derived for it.
#
# WHAT IT DOES. Launch at the predicted floor and measure the card after one
# real completion; then, when the floor is above zero, launch one block below
# it and expect a refusal. The refusal is the measurement
# (okf/must-read/touching-rigs.md): a load one below the floor says the floor
# was loose, a refusal AT the floor says it was greedy, and both are rows, not
# errors. A launch near the memory edge is a 1-in-3 coin flip, so every
# REFUSED is retried RETRY times before it is believed; an OK needs no retry.
#
# WHAT REFUSES (exit 2, one line naming the rule, before any container):
#   - a RUN_* fact is missing: this step was started outside the door
#   - the placement was not derived (the door refused it before this ran)
#   - hosts.json[HOST] declares no llamacpp_image or cpu_expert_offload
#   - the daemon does not hold the declared image, so no digest can be stamped
#   - the host forbids CPU expert offload and the placement needs it: srv1
#     hard-locks under it. A REFUSED row is written first, so the file says why
# WHAT FAILS (exit 1): REFUSED at the floor after RETRY tries. The step
# measured that this placement does not run; gates 7 and 8 still run.
#
# EVERY LINE IS TEED TO THE RIG under ~/mcgyvr-runs/<RUN_ID>/sizing.tsv. A hard
# lock takes the ssh pipe with it and the local file stops mid-run; the rig's
# copy is what survives the reboot. PL1/PL2 are stamped at START from the scan
# and re-read at END, because a lock has wiped srv1's BIOS profile before.
#
# The ssh and docker this step runs are the door's shims (gate-scripts/bin),
# resolved BY PATH from RUN_BIN and never from $PATH: ssh refuses any host
# but RUN_HOST, docker lands on the rig's daemon, and a PATH reordered
# mid-step finds neither real binary. Before that, the door itself is proved
# — an ancestor's command line, read by gatelib.under_door — because every
# RUN_* below can be typed into a shell. Bind-mount paths are the RIG's, so
# $HOME is asked of the rig and never expanded here.
# shellcheck disable=SC2029
set -euo pipefail

ME=default-step
PORT=8080
RETRY=3
HEALTH_POLLS=120
HEALTH_INTERVAL=3
THREAD_CAP=10
TEARDOWN_WAIT=30
DOOR='python -m mcgyvr.serving.run --host H --campaign C --step PATH --model M'

refuse() { printf '%s: REFUSED — %s\n' "$ME" "$*" >&2; exit 2; }
warn() { printf '%s: %s\n' "$ME" "$*" >&2; }
oneline() { tr '\t\r\n' '   ' | tr -s ' ' | cut -c1-300; }

# The proof, first. A non-zero exit for ANY reason — no python3 on PATH, no
# mcgyvr on it, a /proc that cannot be read — is a refusal: the door is proved
# or it is not, and "could not check" is not. What the proof said is quoted.
proof=$(python3 -c 'from mcgyvr.serving.gatelib import under_door; raise SystemExit(0 if under_door() else 2)' 2>&1 >/dev/null) \
    || refuse "this step was not started by the door — no ancestor is mcgyvr.serving.run${proof:+; the proof said: $(printf '%s' "$proof" | tail -n 1 | oneline)} — and RUN_* set by hand does not stand in for one. Start the run as \`$DOOR\` (okf/must-read/touching-rigs.md)"

for v in RUN_ROOT RUN_BIN RUN_HOST RUN_MODEL RUN_PARALLEL RUN_CTX_PER_SLOT RUN_UBATCH \
    RUN_ROUND RUN_PRODUCT_SHA256 RUN_PROFILE RUN_CONFIG_DIGEST RUN_ID RUN_OUT_DIR \
    RUN_SCAN_JSON RUN_GEOMETRY_JSON RUN_PLACEMENT_JSON; do
    [ -n "${!v:-}" ] || refuse "$v is not set. This step reads the run from the environment the door exports; an empty one means it was started outside mcgyvr.serving.run, where no gate has run and nothing is guarded"
done

# The shims, by path. RUN_BIN is the door's export of its own shim directory
# (RUN_ROOT is the run root, which need not hold any code); with the door
# proved above, taking it from the environment is fine — the shim refuses by
# itself when it is not under the door.
SHIMS=$RUN_BIN
for bin in ssh docker; do
    [ -x "$SHIMS/$bin" ] || refuse "$SHIMS/$bin is missing or not executable; the door's shims are the only ssh and docker this step runs, and RUN_BIN=$RUN_BIN holds none"
done
SSH=$SHIMS/ssh
DOCKER=$SHIMS/docker

# ---------------------------------------------------------------------------
# the facts: placement, scan, geometry, hosts.json — read once, refused if short
# ---------------------------------------------------------------------------
HOSTS_JSON=$RUN_ROOT/tools/runs/hosts.json
[ -f "$HOSTS_JSON" ] || refuse "$HOSTS_JSON is missing; the image and the offload rule for $RUN_HOST are declared there and nowhere else"

facts=$(python3 - "$RUN_PLACEMENT_JSON" "$RUN_SCAN_JSON" "$RUN_GEOMETRY_JSON" \
    "$HOSTS_JSON" "$RUN_HOST" "$THREAD_CAP" <<'PY'
import json
import shlex
import sys

placement, scan, geometry, hosts_path, host, thread_cap = sys.argv[1:7]


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def out(key, value):
    print(f"{key}={shlex.quote(str(value))}")


def missing(why):
    out("FACTS_MISSING", why)
    sys.exit(0)


p, s, g, hosts = load(placement), load(scan), load(geometry), load(hosts_path)

h = hosts.get(host)
if not isinstance(h, dict):
    missing(f"hosts.json declares no {host!r}")
for key in ("llamacpp_image", "cpu_expert_offload"):
    if key not in h:
        missing(
            f"hosts.json[{host!r}] declares no {key!r}; the image a row is "
            "valid against and whether the host survives CPU expert offload "
            "are declarations, not guesses"
        )
if not isinstance(h["llamacpp_image"], str) or not h["llamacpp_image"].strip():
    missing(f"hosts.json[{host!r}].llamacpp_image is empty")
if not isinstance(h["cpu_expert_offload"], bool):
    missing(f"hosts.json[{host!r}].cpu_expert_offload is not true/false")
out("H_IMG", h["llamacpp_image"].strip())
out("H_OFFLOAD", "true" if h["cpu_expert_offload"] else "false")

out("P_DERIVED", "true" if p.get("derived") is True else "false")
out("P_WHY", p.get("why") or "")
floor = p.get("floor_n_cpu_moe")
if not isinstance(floor, int) or isinstance(floor, bool) or floor < 0:
    missing(f"placement.json carries floor_n_cpu_moe={floor!r}, not a block index")
out("P_FLOOR", floor)
predicted = p.get("predicted_card_mib")
out("P_PREDICTED", predicted if predicted is not None else "NA")
below = "NA"
if predicted is not None and floor > 0:
    # At --n-cpu-moe N the blocks with index < N leave the card, so one step
    # below the floor puts block N-1 back on it (vramfit.experts_on_card).
    extra = (g.get("expert_bytes_by_block") or {}).get(str(floor - 1), 0)
    below = round(float(predicted) + int(extra) / 1024**2, 1)
out("P_PREDICTED_BELOW", below)

for key in ("pl1_uw", "pl2_uw", "uptime_since", "nproc"):
    value = s.get(key)
    if value is None or not str(value).strip() or any(c.isspace() for c in str(value)):
        missing(f"scan.json carries {key}={value!r}, which cannot be stamped")
out("S_PL1", s["pl1_uw"])
out("S_PL2", s["pl2_uw"])
out("S_UPTIME", s["uptime_since"])
free = (s.get("gpu") or {}).get("free_mib")
if not isinstance(free, int):
    missing(f"scan.json carries gpu.free_mib={free!r}, not a number of MiB")
out("S_FREE", free)
nproc = str(s["nproc"])
if not nproc.isdigit() or int(nproc) < 1:
    missing(f"scan.json carries nproc={nproc!r}; the thread count is read, never assumed")
out("S_THREADS", min(int(nproc), int(thread_cap)))
out("FACTS_OK", 1)
PY
) || refuse "reading the envelope failed: placement, scan, geometry or hosts.json did not parse"
eval "$facts"
[ -z "${FACTS_MISSING:-}" ] || refuse "$FACTS_MISSING"
[ "${FACTS_OK:-}" = 1 ] || refuse "the envelope reader produced nothing; the placement is not read"

[ "$P_DERIVED" = true ] || refuse "placement.json says derived=false${P_WHY:+ ($P_WHY)}. The door refuses an underived placement before the step; nothing is launched from one"

# ---------------------------------------------------------------------------
# the image, as a digest: a row on srv1 is only valid against a stated image
# ---------------------------------------------------------------------------
IMG=$H_IMG
img=$("$DOCKER" image inspect \
    --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}{{.Id}}{{end}}' \
    "$IMG" 2>/dev/null | head -n 1 | tr -d '[:space:]') || img=
[ -n "$img" ] || refuse "the daemon does not hold $IMG (hosts.json[$RUN_HOST].llamacpp_image): it inspects with neither a RepoDigests entry nor an Id, so no image can be stamped on a row and no container is started from it (gate 3)"

# ---------------------------------------------------------------------------
# the rig's own paths and the rig-side copy of the artifact
# ---------------------------------------------------------------------------
# shellcheck disable=SC2016  # $HOME must expand on the rig, not here
RIG_HOME=$("$SSH" "$RUN_HOST" 'echo $HOME' | tr -d '[:space:]') || RIG_HOME=
[ -n "$RIG_HOME" ] || refuse "$RUN_HOST did not answer 'echo \$HOME'; the bind mount is the rig's path and is never expanded on this machine"
"$SSH" "$RUN_HOST" "mkdir -p ~/mcgyvr-runs/$RUN_ID" \
    || refuse "$RUN_HOST could not create ~/mcgyvr-runs/$RUN_ID; without the rig-side copy a hard lock would leave no record of what was running"

OUT=$RUN_OUT_DIR/sizing.tsv
[ ! -e "$OUT" ] || refuse "$OUT already exists; an artifact is written once (gate 5)"

MODEL=$(basename "$RUN_MODEL" .gguf)
N_CTX=$((RUN_CTX_PER_SLOT * RUN_PARALLEL))

say() {
    printf '%s\n' "$1" >>"$OUT"
    printf '%s\n' "$1"
    if ! printf '%s\n' "$1" | "$SSH" "$RUN_HOST" "cat >> ~/mcgyvr-runs/$RUN_ID/sizing.tsv" 2>/dev/null; then
        warn "could not tee a line to $RUN_HOST:~/mcgyvr-runs/$RUN_ID/sizing.tsv; the local file has it"
    fi
}

# row VERDICT ARM N TRY PREDICTED MEASURED FREE_BEFORE REASON -> one TSV row
row() {
    local delta=NA
    if [ "$5" != NA ] && [ "$6" != NA ]; then
        delta=$(awk -v m="$6" -v p="$5" 'BEGIN { printf "%.1f", m - p }')
    fi
    printf '%s\t%s\t%s\tarm=%s\tn_cpu_moe=%s\ttry=%s/%s\tpredicted_mib=%s\tmeasured_mib=%s\tdelta_mib=%s\tfree_before_mib=%s\timg=%s\treason=%s' \
        "$RUN_HOST" "$MODEL" "$1" "$2" "$3" "$4" "$RETRY" "$5" "$6" "$delta" "$7" "$img" "$8"
}

# rig_read memory.free|memory.used -> MiB as one number, or the script dies
rig_read() {
    local value
    value=$("$SSH" "$RUN_HOST" "nvidia-smi --query-gpu=$1 --format=csv,noheader,nounits" | head -n 1 | tr -d '[:space:]')
    case $value in
        '' | *[!0-9]*) refuse "nvidia-smi on $RUN_HOST read '$value' for $1, which is not a number of MiB; a card that cannot be read is not measured" ;;
    esac
    printf '%s' "$value"
}

# rig_pl 0|1 -> constraint_N_power_limit_uw, never constraint_N_max_power_uw:
# the latter is the rated TDP and reads 95000000 whatever the live limit is.
rig_pl() {
    local value
    value=$("$SSH" "$RUN_HOST" "for d in /sys/class/powercap/intel-rapl:0 /sys/class/powercap/intel-rapl/intel-rapl:0; do [ -r \$d/constraint_${1}_power_limit_uw ] && { cat \$d/constraint_${1}_power_limit_uw; exit 0; }; done; echo NA" | tr -d '[:space:]')
    printf '%s' "${value:-NA}"
}

logtail() { "$DOCKER" logs --tail 5 "$1" 2>&1 | oneline || true; }

CURRENT=
# shellcheck disable=SC2317,SC2329  # reached through the EXIT/INT/TERM trap
on_exit() {
    local status=$?
    if [ -n "$CURRENT" ]; then
        warn "exit $status with $CURRENT still started; removing it (kill what you started)"
        "$DOCKER" rm -f "$CURRENT" >/dev/null 2>&1 || true
    fi
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# teardown NAME: remove it, then wait until nothing of this run is listed, so
# the next free reading is what the next launch actually gets.
teardown() {
    local i left=
    "$DOCKER" rm -f "$1" >/dev/null 2>&1 || true
    CURRENT=
    for ((i = 0; i < TEARDOWN_WAIT; i++)); do
        left=$("$DOCKER" ps -q --filter "name=^$RUN_ID-")
        if [ -z "$left" ]; then
            return 0
        fi
        sleep 1
    done
    warn "containers named $RUN_ID-* are still listed after ${TEARDOWN_WAIT}s ($(printf '%s' "$left" | oneline)); gate 7 will name them"
}

# launch N -> L_VERDICT (OK|REFUSED) L_MEASURED L_FREE_BEFORE L_REASON; the
# container is gone when this returns, whichever way it went.
launch() {
    local n=$1 name="$RUN_ID-N$1" i healthy=0 alive err
    local -a place=()
    if [ "$n" -gt 0 ]; then
        place=(--n-cpu-moe "$n")
    fi
    L_VERDICT=REFUSED
    L_MEASURED=NA
    L_REASON=NA
    L_FREE_BEFORE=$(rig_read memory.free)
    "$DOCKER" rm -f "$name" >/dev/null 2>&1 || true
    CURRENT=$name
    if ! err=$("$DOCKER" run -d --name "$name" --runtime=nvidia --gpus all \
        -v "$RIG_HOME/models:/models" -p "$PORT:8080" "$IMG" \
        -m "$RUN_MODEL" --host 0.0.0.0 --port 8080 \
        --parallel "$RUN_PARALLEL" -c "$N_CTX" -b "$RUN_UBATCH" -ub "$RUN_UBATCH" \
        -ngl 99 -t "$S_THREADS" "${place[@]}" 2>&1 >/dev/null); then
        L_REASON="docker-run-failed: $(printf '%s' "$err" | oneline)"
        teardown "$name"
        return 0
    fi
    for ((i = 0; i < HEALTH_POLLS; i++)); do
        if "$SSH" "$RUN_HOST" "curl -sf http://localhost:$PORT/health" >/dev/null 2>&1; then
            healthy=1
            break
        fi
        alive=$("$DOCKER" ps -q --filter "name=^${name}\$")
        if [ -z "$alive" ]; then
            L_REASON="container-exited: $(logtail "$name")"
            teardown "$name"
            return 0
        fi
        sleep "$HEALTH_INTERVAL"
    done
    if [ "$healthy" != 1 ]; then
        L_REASON="health-timeout: no /health in $((HEALTH_POLLS * HEALTH_INTERVAL))s; $(logtail "$name")"
        teardown "$name"
        return 0
    fi
    if ! "$SSH" "$RUN_HOST" "curl -sf -X POST http://localhost:$PORT/completion -d '{\"prompt\":\"hi\",\"n_predict\":8}'" >/dev/null 2>&1; then
        L_REASON="warmup-failed: /health answered and /completion did not; $(logtail "$name")"
        teardown "$name"
        return 0
    fi
    sleep 2
    L_MEASURED=$(rig_read memory.used)
    L_VERDICT=OK
    teardown "$name"
}

end_stamp() {
    local free pl1 pl2
    free=$(rig_read memory.free)
    pl1=$(rig_pl 0)
    pl2=$(rig_pl 1)
    say "### END run_id=$RUN_ID free_mib=$free pl1=$pl1 pl2=$pl2"
}

# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
say "### START run_id=$RUN_ID host=$RUN_HOST pl1=$S_PL1 pl2=$S_PL2 uptime_since=$S_UPTIME"
say "### ROUND id=$RUN_ROUND product_sha256=$RUN_PRODUCT_SHA256"
say "### CONFIG profile=$RUN_PROFILE digest=$RUN_CONFIG_DIGEST"

if [ "$H_OFFLOAD" != true ] && [ "$P_FLOOR" -gt 0 ]; then
    say "$(row REFUSED at_floor "$P_FLOOR" 0 "$P_PREDICTED" NA "$S_FREE" cpu-expert-offload-disabled-on-host)"
    end_stamp
    refuse "hosts.json[$RUN_HOST].cpu_expert_offload is false and this placement needs --n-cpu-moe $P_FLOOR; $RUN_HOST hard-locks under CPU expert offload (okf/must-read/touching-rigs.md). Nothing was launched; the REFUSED row says why"
fi

at_floor_ok=0
for ((t = 1; t <= RETRY; t++)); do
    launch "$P_FLOOR"
    say "$(row "$L_VERDICT" at_floor "$P_FLOOR" "$t" "$P_PREDICTED" "$L_MEASURED" "$L_FREE_BEFORE" "$L_REASON")"
    if [ "$L_VERDICT" = OK ]; then
        at_floor_ok=1
        break
    fi
done

if [ "$at_floor_ok" = 1 ] && [ "$P_FLOOR" -gt 0 ]; then
    below=$((P_FLOOR - 1))
    for ((t = 1; t <= RETRY; t++)); do
        launch "$below"
        say "$(row "$L_VERDICT" below_floor "$below" "$t" "$P_PREDICTED_BELOW" "$L_MEASURED" "$L_FREE_BEFORE" "$L_REASON")"
        if [ "$L_VERDICT" = OK ]; then
            # It loaded below the floor: the floor was loose. That is the row,
            # not a refusal, and it needs no retry.
            break
        fi
    done
fi

end_stamp

if [ "$at_floor_ok" != 1 ]; then
    warn "REFUSED at the floor (--n-cpu-moe $P_FLOOR) $RETRY times; the placement does not run on $RUN_HOST as derived"
    exit 1
fi
exit 0
