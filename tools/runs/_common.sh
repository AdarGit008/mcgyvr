# shellcheck shell=bash
# tools/runs/_common.sh — the one emitter the six srv1 kernel-arms run scripts
# source. Written against
# `records/evidence/2026-09-02-srv1-kernel-arms/ARTIFACT-CONTRACT.md` (the
# authority) and the parser it cites, `tests/sweeprows.py`. Section numbers below
# are that contract's.
#
#   _fail / _tok / _kv_ok        internal; a loud stderr message and a non-zero
#                                return. Nothing here ever substitutes a
#                                placeholder for a value it could not read: a
#                                fabricated row is the one unacceptable outcome.
#   stamp NAME [k=v ...]         §1.6 — a `### NAME k=v ...` marker. Enforces
#                                both rules the parser now RAISES on: the name
#                                is a token that is not itself k=v
#                                (`_stamp_name`, §6.6), and no value may contain
#                                whitespace (`_stamp_fields`, §6.7).
#   row LABEL KIND [k=v ...] [-- free text ...]
#                                §1.1-§1.4 — `host<TAB>label<TAB>kind<TAB>k=v...`.
#                                Fields are TAB-separated; a field value carrying
#                                whitespace is refused. Anything after `--` is
#                                emitted as the single free-text `tail` field
#                                (§1.3), which may hold spaces.
#   arm_label ARM CELL           §1.5, §3.2, resolved conflict §6.1 — the one
#                                labelling convention, `<ARM>-<cell>`, with ARM
#                                matching ARM_PREFIX `[ABL][0-9]`
#                                (`sweeprows.py:49`).
#   rig_snapshot                 §2.2/§2.3 — reads the live rig, one `k=v` per
#                                line. GPU name/VRAM/compute-cap/driver/reserve
#                                from nvidia-smi; CPU model and cpu_max from
#                                /sys (else lscpu); DDR speed from dmidecode;
#                                PL1/PL2 from `constraint_0/1_power_limit_uw`.
#   rig_stamp                    §2.2 — `### RIG` carrying all six RIG_FIELDS
#                                (`sweeprows.py:260-267`) plus the card and CPU
#                                identity. Emit once before the first row and
#                                re-stamp per arm (`test_a_row_without_...:9-11`).
#   start_stamp / end_stamp      §2.3 — `### START` (with
#                                `pl1_source=constraint_0_power_limit_uw`) and
#                                `### END`. start_stamp also records the reading
#                                that rig_assert_unchanged compares against.
#   rig_assert_unchanged         §2.3 and guideline 7's "start equals end" — a
#                                fresh read, compared field by field with the
#                                one start_stamp took. Loud on any difference.
#   workload_stamp DRIVER        §2.1 — `### WORKLOAD digest=... driver=...`.
#                                The digest is computed by
#                                `tests/sweeprows.py:workload_digest()` itself,
#                                through `uv run python`; a second implementation
#                                would be a second thing to drift.
#   microbench_stamp             §2.1/§6.4 — `### WORKLOAD digest=none
#                                comparable_with=microbenchmark-only`, owed by
#                                BOTH microbenchmark files.
#   refused LABEL [k=v ...] -- REASON
#                                §3 and resolved conflict §6.3 — a REFUSED row
#                                carrying `checkpoint_quant`, `tries>=3` and a
#                                reason over 40 characters. Guideline 8: a
#                                refusal is a result.
#   retry3 CMD [ARG ...]         guideline 8 — three attempts before a refusal is
#                                believed; sets RUN_TRIES to the attempt count
#                                for `refused` to record.
#
# Sourcing this file executes nothing and sets nothing. Every function is safe
# under `set -euo pipefail`.
#
# Environment read (never required, never fabricated from):
#   RUN_HOST          host column; default `hostname`.
#   RUN_REPO          repo root; default `git rev-parse --show-toplevel`.
#   RUN_RETRY_SLEEP   seconds between retry3 attempts; default 5.

# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------

_fail() {
    printf '%s: %s\n' "${0##*/}" "$*" >&2
    return 1
}

# Collapse whitespace runs to `_` and trim. A stamp value may not contain a
# space (§1.6) and a row field value is refused if it does, so every value that
# reaches a marker or a field passes through here first.
_tok() {
    printf '%s' "$*" | tr -s ' \t\n' '_' | sed -e 's/^_//' -e 's/_$//'
}

# The parser's own field test, `_KV` at sweeprows.py:33.
_kv_ok() {
    case $1 in
        [A-Za-z_]*)
            case ${1%%=*} in
                *[!A-Za-z0-9_]*) return 1 ;;
            esac
            case $1 in
                *=*) return 0 ;;
                *) return 1 ;;
            esac
            ;;
        *) return 1 ;;
    esac
}

_has_space() {
    case $1 in
        *[[:space:]]*) return 0 ;;
        *) return 1 ;;
    esac
}

_has_tab() {
    case $1 in
        *"$(printf '\t')"*) return 0 ;;
        *) return 1 ;;
    esac
}

_host() {
    local h
    h=$(_tok "${RUN_HOST:-$(hostname)}")
    [ -n "$h" ] || { _fail "no host: set RUN_HOST, or fix hostname"; return 1; }
    printf '%s' "$h"
}

_repo_root() {
    local root
    if [ -n "${RUN_REPO:-}" ]; then
        root=$RUN_REPO
    else
        root=$(git rev-parse --show-toplevel 2>/dev/null) || root=
    fi
    if [ -z "$root" ] || [ ! -f "$root/tests/sweeprows.py" ]; then
        _fail "cannot locate the repo (no tests/sweeprows.py under '${root:-?}'). Set RUN_REPO."
        return 1
    fi
    printf '%s' "$root"
}

# --------------------------------------------------------------------------
# §1.6  marker lines
# --------------------------------------------------------------------------

stamp() {
    local name arg out
    [ "$#" -ge 1 ] || { _fail "stamp: usage: stamp NAME [k=v ...]"; return 1; }
    name=$1
    shift
    if [ -z "$name" ] || _has_space "$name"; then
        _fail "stamp: name '$name' is empty or holds whitespace; the name is the first token after ###"
        return 1
    fi
    if _kv_ok "$name"; then
        _fail "stamp: '$name' is a k=v field where the stamp's name belongs — sweeprows._stamp_name raises on this (§6.6)"
        return 1
    fi
    case $name in
        [A-Za-z]*) : ;;
        *)
            _fail "stamp: '$name' does not open with a letter. A stamp names itself; emit a free-text marker with printf, not through stamp"
            return 1
            ;;
    esac
    out="### $name"
    for arg in "$@"; do
        if ! _kv_ok "$arg"; then
            _fail "stamp $name: '$arg' is not key=value — sweeprows._stamp_fields raises on a loose token (§6.7)"
            return 1
        fi
        if _has_space "$arg"; then
            _fail "stamp $name: '$arg' holds whitespace; a stamp is split on whitespace and the tail would be dropped silently (§6.7). Join it: 2026-09-01T08:11:08"
            return 1
        fi
        out="$out $arg"
    done
    printf '%s\n' "$out"
}

# --------------------------------------------------------------------------
# §1.1-§1.4  rows
# --------------------------------------------------------------------------

row() {
    local tab label kind arg out tail seen_sep
    tab=$(printf '\t')
    [ "$#" -ge 2 ] || { _fail "row: usage: row LABEL KIND [k=v ...] [-- free text ...]"; return 1; }
    label=$1
    kind=$2
    shift 2
    if [ -z "$label" ] || _has_tab "$label"; then
        _fail "row: label '$label' is empty or holds a TAB; a TAB would split it into two columns"
        return 1
    fi
    if [ -z "$kind" ] || _has_space "$kind"; then
        _fail "row: kind '$kind' is empty or holds whitespace; kind is column 3 verbatim (§1.4)"
        return 1
    fi
    out="$(_host)$tab$label$tab$kind" || return 1
    tail=
    seen_sep=0
    for arg in "$@"; do
        if [ "$seen_sep" -eq 0 ] && [ "$arg" = "--" ]; then
            seen_sep=1
            continue
        fi
        if [ "$seen_sep" -eq 1 ]; then
            tail="${tail:+$tail }$arg"
            continue
        fi
        if ! _kv_ok "$arg"; then
            _fail "row $kind: '$arg' is not key=value. Free text goes after -- , where it lands in the parser's tail (§1.3)"
            return 1
        fi
        if _has_space "$arg"; then
            _fail "row $kind: field '$arg' holds whitespace. Every value this run emits is one whitespace-free token"
            return 1
        fi
        out="$out$tab$arg"
    done
    if [ -n "$tail" ]; then
        if _has_tab "$tail"; then
            _fail "row $kind: the free text holds a TAB, which would split it into extra columns"
            return 1
        fi
        if _kv_ok "${tail%% *}"; then
            _fail "row $kind: the free text opens with '${tail%% *}', which the parser eats as a field and drops from tail (§1.3). Rephrase so the first word is not key=value"
            return 1
        fi
        out="$out$tab$tail"
    fi
    printf '%s\n' "$out"
}

# --------------------------------------------------------------------------
# §1.5, §3.2, §6.1  labels
# --------------------------------------------------------------------------

arm_label() {
    local arm cell
    [ "$#" -eq 2 ] || { _fail "arm_label: usage: arm_label ARM CELL"; return 1; }
    arm=$1
    cell=$2
    case $arm in
        [ABL][0-9]) : ;;
        *)
            _fail "arm_label: '$arm' does not match ARM_PREFIX [ABL][0-9] (sweeprows.py:49), so Row.cell would not strip it and the arms would not align (§6.1)"
            return 1
            ;;
    esac
    if [ -z "$cell" ] || _has_space "$cell"; then
        _fail "arm_label: cell '$cell' is empty or holds whitespace; the label's first word is the tag (sweeprows.py:119-123)"
        return 1
    fi
    printf '%s-%s' "$arm" "$cell"
}

# --------------------------------------------------------------------------
# §2.2/§2.3  the live rig
# --------------------------------------------------------------------------

_rig_uptime_since() {
    local btime out
    # /proc/stat's btime is the boot instant as an epoch second: exact, and
    # stable across the run. `uptime -s` derives now-minus-uptime and can read
    # one second apart at the two ends, which would fail the start==end check
    # for a reason that is not the rig moving.
    btime=$(awk '/^btime /{print $2; exit}' /proc/stat 2>/dev/null) || btime=
    if [ -n "$btime" ]; then
        out=$(date -u -d "@$btime" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null) || out=
    fi
    if [ -z "${out:-}" ] && command -v uptime >/dev/null 2>&1; then
        out=$(uptime -s 2>/dev/null | tr ' ' 'T') || out=
    fi
    out=$(_tok "${out:-}")
    [ -n "$out" ] || { _fail "cannot read the boot time (/proc/stat btime, uptime -s)"; return 1; }
    printf '%s' "$out"
}

_rig_cpu_max_mhz() {
    local khz out
    if [ -r /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq ]; then
        khz=$(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq)
        case $khz in
            *[!0-9]* | '') khz= ;;
        esac
        [ -n "$khz" ] && out=$((khz / 1000))
    fi
    if [ -z "${out:-}" ] && command -v lscpu >/dev/null 2>&1; then
        out=$(LC_ALL=C lscpu 2>/dev/null | sed -n 's/^CPU max MHz:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n 1)
    fi
    out=$(_tok "${out:-}")
    [ -n "$out" ] || { _fail "cannot read cpu_max_mhz (cpufreq/cpuinfo_max_freq, lscpu). srv1's max clock moved 4800 -> 4600 unattended; a row that cannot name it is not comparable"; return 1; }
    printf '%s' "$out"
}

_rig_cpu_model() {
    local out
    out=$(sed -n 's/^model name[[:space:]]*:[[:space:]]*//p' /proc/cpuinfo 2>/dev/null | head -n 1) || out=
    if [ -z "$out" ] && command -v lscpu >/dev/null 2>&1; then
        out=$(LC_ALL=C lscpu 2>/dev/null | sed -n 's/^Model name:[[:space:]]*//p' | head -n 1)
    fi
    out=$(_tok "${out:-}")
    [ -n "$out" ] || { _fail "cannot read the CPU model (/proc/cpuinfo, lscpu)"; return 1; }
    printf '%s' "$out"
}

_rig_ram_mt_s() {
    local raw speeds count out
    raw=
    if command -v dmidecode >/dev/null 2>&1; then
        raw=$(dmidecode -t memory 2>/dev/null) || raw=
        if [ -z "$raw" ] && command -v sudo >/dev/null 2>&1; then
            raw=$(sudo -n dmidecode -t memory 2>/dev/null) || raw=
        fi
    fi
    [ -n "$raw" ] || { _fail "cannot read the DDR speed: dmidecode -t memory produced nothing (needs root, or sudo -n). RAM has moved between these rigs twice in six days; do not guess it"; return 1; }
    speeds=$(printf '%s\n' "$raw" | sed -n 's/^[[:space:]]*Configured Memory Speed:[[:space:]]*\([0-9][0-9]*\)[[:space:]]*MT\/s.*/\1/p' | sort -u)
    [ -n "$speeds" ] || { _fail "dmidecode reported no 'Configured Memory Speed' line; the DDR speed is unread"; return 1; }
    count=$(printf '%s\n' "$speeds" | wc -l)
    if [ "$count" -ne 1 ]; then
        _fail "dmidecode reports $count different configured memory speeds ($(printf '%s' "$speeds" | tr '\n' ' ')); one token cannot name them honestly"
        return 1
    fi
    out=$(_tok "$speeds")
    printf '%s' "$out"
}

# The package RAPL domain. PL1 is constraint_0 (long_term), PL2 is constraint_1
# (short_term). Guideline 7: never `constraint_0_max_power_uw`, which is the
# rated TDP and reads 95000000 whether or not the cap is in force — it looks
# exactly like the BIOS profile a hard lock has already wiped.
_rig_rapl_dir() {
    local d name
    for d in /sys/class/powercap/intel-rapl:*; do
        [ -r "$d/name" ] || continue
        name=$(cat "$d/name" 2>/dev/null) || continue
        [ "$name" = "package-0" ] || continue
        printf '%s' "$d"
        return 0
    done
    _fail "no RAPL package-0 domain under /sys/class/powercap; PL1/PL2 cannot be read"
    return 1
}

_rig_power_limit() {
    local which d idx want got out
    which=$1
    d=$(_rig_rapl_dir) || return 1
    case $which in
        pl1) idx=0; want=long_term ;;
        pl2) idx=1; want=short_term ;;
        *) _fail "_rig_power_limit: pl1 or pl2"; return 1 ;;
    esac
    if [ ! -r "$d/constraint_${idx}_power_limit_uw" ]; then
        _fail "$d/constraint_${idx}_power_limit_uw is unreadable; $which is unread. Do not fall back to constraint_${idx}_max_power_uw (guideline 7)"
        return 1
    fi
    got=$(cat "$d/constraint_${idx}_name" 2>/dev/null) || got=
    if [ -n "$got" ] && [ "$got" != "$want" ]; then
        _fail "$d/constraint_${idx}_name reads '$got', not '$want'; the constraint indices are not what $which assumes"
        return 1
    fi
    out=$(_tok "$(cat "$d/constraint_${idx}_power_limit_uw")")
    case $out in
        '' | *[!0-9]*)
            _fail "$which read '$out', which is not a number of microwatts"
            return 1
            ;;
    esac
    printf '%s' "$out"
}

# One nvidia-smi call, five fields, first GPU. `memory.reserved` is absent on
# older drivers, so it falls back to total - (used + free) — the same quantity,
# arithmetic instead of a query, and still measured.
_rig_nvidia() {
    local out line name total cc drv reserved used free f
    command -v nvidia-smi >/dev/null 2>&1 || {
        _fail "nvidia-smi is not on PATH. This library reads the rig it is running on; off-rig it emits nothing, because a placeholder rig stamp is a fabricated row"
        return 1
    }
    out=$(nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version,memory.reserved,memory.used,memory.free --format=csv,noheader,nounits 2>/dev/null) || out=
    if [ -z "$out" ]; then
        out=$(nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv,noheader,nounits 2>/dev/null) || out=
        [ -n "$out" ] || { _fail "nvidia-smi returned nothing; the GPU state is unread"; return 1; }
        out="$out, [N/A], [N/A], [N/A]"
    fi
    line=$(printf '%s\n' "$out" | head -n 1)
    IFS=, read -r name total cc drv reserved used free <<EOF
$line
EOF
    name=$(_tok "$name")
    total=$(_tok "$total")
    cc=$(_tok "$cc")
    drv=$(_tok "$drv")
    reserved=$(_tok "${reserved:-}")
    used=$(_tok "${used:-}")
    free=$(_tok "${free:-}")
    case $reserved in
        '' | *[!0-9]*)
            case $total$used$free in
                *[!0-9]*)
                    _fail "nvidia-smi reports no memory.reserved and no usable total/used/free; gpu_reserve_mib is unread (it differs per boot)"
                    return 1
                    ;;
                '')
                    _fail "nvidia-smi reports no memory figures at all"
                    return 1
                    ;;
            esac
            reserved=$((total - used - free))
            ;;
    esac
    for f in "$name" "$total" "$cc" "$drv"; do
        [ -n "$f" ] || { _fail "nvidia-smi left one of name/memory.total/compute_cap/driver_version empty: '$line'"; return 1; }
    done
    printf 'gpu_name=%s\ngpu_vram_mib=%s\ngpu_cc=%s\ndriver=%s\ngpu_reserve_mib=%s\n' \
        "$name" "$total" "$cc" "$drv" "$reserved"
}

# One reading of the machine, `k=v` per line. Every value is a single
# whitespace-free token, so each line is legal in a marker as-is (§1.6).
rig_snapshot() {
    local uptime_since cpu_max_mhz cpu_model ram_mt_s pl1 pl2 nv
    uptime_since=$(_rig_uptime_since) || return 1
    cpu_max_mhz=$(_rig_cpu_max_mhz) || return 1
    cpu_model=$(_rig_cpu_model) || return 1
    ram_mt_s=$(_rig_ram_mt_s) || return 1
    pl1=$(_rig_power_limit pl1) || return 1
    pl2=$(_rig_power_limit pl2) || return 1
    nv=$(_rig_nvidia) || return 1
    printf 'uptime_since=%s\ncpu_max_mhz=%s\ncpu_model=%s\nram_mt_s=%s\npl1_uw=%s\npl2_uw=%s\n%s\n' \
        "$uptime_since" "$cpu_max_mhz" "$cpu_model" "$ram_mt_s" "$pl1" "$pl2" "$nv"
}

_snap_get() {
    printf '%s\n' "$1" | sed -n "s/^$2=//p" | head -n 1
}

# §2.2. All six RIG_FIELDS (sweeprows.py:260-267) plus the card and CPU this run
# actually ran on.
rig_stamp() {
    local snap
    snap=$(rig_snapshot) || return 1
    stamp RIG \
        "cpu_max_mhz=$(_snap_get "$snap" cpu_max_mhz)" \
        "ram_mt_s=$(_snap_get "$snap" ram_mt_s)" \
        "pl1_uw=$(_snap_get "$snap" pl1_uw)" \
        "pl2_uw=$(_snap_get "$snap" pl2_uw)" \
        "driver=$(_snap_get "$snap" driver)" \
        "gpu_reserve_mib=$(_snap_get "$snap" gpu_reserve_mib)" \
        "gpu_name=$(_snap_get "$snap" gpu_name)" \
        "gpu_vram_mib=$(_snap_get "$snap" gpu_vram_mib)" \
        "gpu_cc=$(_snap_get "$snap" gpu_cc)" \
        "cpu_model=$(_snap_get "$snap" cpu_model)"
}

# §2.3. Also records the reading rig_assert_unchanged will compare against.
start_stamp() {
    local snap
    snap=$(rig_snapshot) || return 1
    RUN_RIG_START=$snap
    stamp START \
        "uptime_since=$(_snap_get "$snap" uptime_since)" \
        "pl1_uw=$(_snap_get "$snap" pl1_uw)" \
        "pl2_uw=$(_snap_get "$snap" pl2_uw)" \
        "pl1_source=constraint_0_power_limit_uw" \
        "cpu_max_mhz=$(_snap_get "$snap" cpu_max_mhz)" \
        "ram_mt_s=$(_snap_get "$snap" ram_mt_s)"
}

# §2.3. A fresh read, emitted whatever it says — if the rig moved, the file must
# say so. Call rig_assert_unchanged after this, not instead of it.
end_stamp() {
    local snap
    snap=$(rig_snapshot) || return 1
    RUN_RIG_END=$snap
    stamp END \
        "uptime_since=$(_snap_get "$snap" uptime_since)" \
        "pl1_uw=$(_snap_get "$snap" pl1_uw)" \
        "pl2_uw=$(_snap_get "$snap" pl2_uw)" \
        "cpu_max_mhz=$(_snap_get "$snap" cpu_max_mhz)" \
        "ram_mt_s=$(_snap_get "$snap" ram_mt_s)"
}

# Guideline 7's "start equals end", read on the rig rather than asserted about
# it. A hard lock wipes the BIOS profile — srv1 read PL1 95 W at 05:23 and
# 4095 W at 05:57 — so a run whose ends disagree measured two machines.
rig_assert_unchanged() {
    local now key a b bad
    if [ -z "${RUN_RIG_START:-}" ]; then
        _fail "rig_assert_unchanged: no start reading. Call start_stamp before the first row"
        return 1
    fi
    if [ -n "${RUN_RIG_END:-}" ]; then
        now=$RUN_RIG_END
    else
        now=$(rig_snapshot) || return 1
    fi
    bad=
    for key in uptime_since cpu_max_mhz cpu_model ram_mt_s pl1_uw pl2_uw driver gpu_reserve_mib gpu_name gpu_vram_mib gpu_cc; do
        a=$(_snap_get "$RUN_RIG_START" "$key")
        b=$(_snap_get "$now" "$key")
        [ "$a" = "$b" ] || bad="${bad:+$bad; }$key: start='$a' end='$b'"
    done
    if [ -n "$bad" ]; then
        _fail "THE RIG MOVED UNDER THIS RUN — $bad. The rows between the two stamps were not all produced under one machine state (guideline 7)"
        return 1
    fi
}

# --------------------------------------------------------------------------
# §2.1  the workload stamp
# --------------------------------------------------------------------------

# The digest is sweeprows.workload_digest()'s, not a copy of it: it execs the
# driver's own PROMPT_DECILES..def sh( block over 200 generated prompts, so a
# `ruff format` pass does not move it and a changed prompt does.
workload_stamp() {
    local driver root digest
    [ "$#" -eq 1 ] || { _fail "workload_stamp: usage: workload_stamp <driver.py>"; return 1; }
    driver=$1
    if _has_space "$driver"; then
        _fail "workload_stamp: driver path '$driver' holds whitespace; a stamp value may not (§1.6)"
        return 1
    fi
    root=$(_repo_root) || return 1
    if [ ! -f "$root/$driver" ]; then
        _fail "workload_stamp: '$driver' is not a file under $root. The stamp names a repo-relative path the test re-hashes (§2.1)"
        return 1
    fi
    digest=$(cd "$root" && uv run --quiet python -c '
import sys
from pathlib import Path

from tests.sweeprows import WORKLOAD_DIGEST, workload_digest

got = workload_digest(Path(sys.argv[1]))
if got != WORKLOAD_DIGEST:
    sys.exit(
        f"{sys.argv[1]} generates workload {got}, not {WORKLOAD_DIGEST}. "
        "Every comparison in this campaign is void until it does."
    )
print(got)
' "$driver") || {
        _fail "workload_stamp: could not compute the digest of '$driver' with tests/sweeprows.py:workload_digest()"
        return 1
    }
    stamp WORKLOAD "digest=$digest" "driver=$driver"
}

# §2.1/§6.4. Owed by BOTH microbenchmark files, not only the one named after the
# tool: llama-bench shares no prompt, no template and no sampler with the serving
# drivers, and a ladder rung quoted as a serving gain is the misreading
# guideline 4 blocks.
microbench_stamp() {
    [ "$#" -eq 0 ] || { _fail "microbench_stamp: takes no arguments"; return 1; }
    stamp WORKLOAD "digest=none" "comparable_with=microbenchmark-only"
}

# --------------------------------------------------------------------------
# guideline 8  refusals
# --------------------------------------------------------------------------

# retry3 CMD [ARG ...] — three attempts before a refusal is believed; a launch
# near the memory edge is a 1-in-3 coin flip. Sets RUN_TRIES to the number of
# attempts made, which `refused` records. Call it as a condition
# (`if retry3 ...; then ... else refused ...; fi`) so `set -e` does not take the
# script down on the failure this is designed to report.
retry3() {
    [ "$#" -ge 1 ] || { _fail "retry3: usage: retry3 CMD [ARG ...]"; return 1; }
    RUN_TRIES=0
    while [ "$RUN_TRIES" -lt 3 ]; do
        RUN_TRIES=$((RUN_TRIES + 1))
        if "$@"; then
            return 0
        fi
        if [ "$RUN_TRIES" -lt 3 ]; then
            sleep "${RUN_RETRY_SLEEP:-5}"
        fi
    done
    return 1
}

# refused LABEL [k=v ...] -- REASON WORDS...
# Resolved conflict §6.3: a dropped arm and a refused arm leave an identical
# hole, and only one of them is a result. The price of the missing CONFIG is
# `checkpoint_quant`, `tries>=3` and a reason of more than 40 characters
# (test_two_backends_...:56-65, test_an_ncmoe_floor_...:83-86).
refused() {
    local label arg fields reason in_reason tries
    [ "$#" -ge 2 ] || { _fail "refused: usage: refused LABEL [k=v ...] -- REASON..."; return 1; }
    label=$1
    shift
    fields=
    reason=
    in_reason=0
    for arg in "$@"; do
        if [ "$in_reason" -eq 0 ] && [ "$arg" = "--" ]; then
            in_reason=1
            continue
        fi
        if [ "$in_reason" -eq 1 ]; then
            reason="${reason:+$reason }$arg"
            continue
        fi
        if ! _kv_ok "$arg" || _has_space "$arg"; then
            _fail "refused: '$arg' is not a whitespace-free key=value field"
            return 1
        fi
        fields="${fields:+$fields }$arg"
    done
    if [ "$in_reason" -eq 0 ]; then
        _fail "refused: no -- separator, so no reason. Guideline 8: record the reason"
        return 1
    fi
    if [ "${#reason}" -le 40 ]; then
        _fail "refused: the reason is ${#reason} characters and must be more than 40 (test_an_ncmoe_floor_...:87). Say what refused, and what it said"
        return 1
    fi
    case " $fields " in
        *" checkpoint_quant="*) : ;;
        *)
            _fail "refused: no checkpoint_quant=. It carries what was read from quantization_config, not what a path implies (§6.3)"
            return 1
            ;;
    esac
    case " $fields " in
        *" tries="*)
            tries=${fields##* tries=}
            tries=${tries%% *}
            ;;
        *)
            tries=${RUN_TRIES:-0}
            fields="$fields tries=$tries"
            ;;
    esac
    case $tries in
        '' | *[!0-9]*)
            _fail "refused: tries='$tries' is not an integer"
            return 1
            ;;
    esac
    if [ "$tries" -lt 3 ]; then
        _fail "refused: tries=$tries. Retry three times before believing a refusal (guideline 8); run the launch through retry3, which sets RUN_TRIES"
        return 1
    fi
    # Fields are validated whitespace-free above, so this split is the intent.
    # shellcheck disable=SC2086
    row "$label" REFUSED $fields -- "$reason"
}
