#!/usr/bin/env bash
# A rig's account of itself, as whitespace-free `key=value` lines.
#
# SHIPPED TO THE RIG ON STDIN and never installed there: the door pipes this
# file to `bash -s`, so nothing lands on the rig's disk and gate 7 has nothing
# extra to clean up. The same reason ggufscan.py goes over as `python3 -`.
#
# EVERY READING REFUSES RATHER THAN GUESSING. A missing value is not an empty
# field, it is exit 1 — because a placeholder in a rig stamp is a fabricated
# row, and the whole point of gate 2 is that this file's output can be compared
# with a declaration and disagree.
#
# Ported from tools/runs/_common.sh's _rig_* readers. Two of them carry a rule
# that is not obvious and is marked at the line it applies to.
set -u

fail() { printf 'rig-snapshot: %s\n' "$*" >&2; exit 1; }

# One whitespace-free token: a snapshot line has to be legal inside a stamp
# exactly as it is printed, so spaces collapse to underscores rather than
# getting quoted somewhere downstream.
tok() { printf '%s' "$*" | tr -s ' \t\n' '_' | sed -e 's/^_//' -e 's/_$//'; }

uptime_since() {
    local btime out=
    btime=$(awk '/^btime /{print $2; exit}' /proc/stat 2>/dev/null) || btime=
    [ -n "$btime" ] && out=$(date -u -d "@$btime" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
    [ -n "${out:-}" ] || out=$(uptime -s 2>/dev/null | tr ' ' 'T')
    out=$(tok "${out:-}")
    [ -n "$out" ] || fail "cannot read the boot time (/proc/stat btime, uptime -s)"
    printf '%s' "$out"
}

cpu_max_mhz() {
    local khz out=
    if [ -r /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq ]; then
        khz=$(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq)
        case $khz in *[!0-9]*|'') khz= ;; esac
        [ -n "$khz" ] && out=$((khz / 1000))
    fi
    [ -n "${out:-}" ] || out=$(LC_ALL=C lscpu 2>/dev/null | sed -n 's/^CPU max MHz:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n 1)
    out=$(tok "${out:-}")
    # srv1's max clock moved 4800 -> 4600 unattended; a row that cannot name it
    # is not comparable with one taken before the move.
    [ -n "$out" ] || fail "cannot read cpu_max_mhz (cpufreq/cpuinfo_max_freq, lscpu)"
    printf '%s' "$out"
}

cpu_model() {
    local out
    out=$(sed -n 's/^model name[[:space:]]*:[[:space:]]*//p' /proc/cpuinfo 2>/dev/null | head -n 1) || out=
    [ -n "$out" ] || out=$(LC_ALL=C lscpu 2>/dev/null | sed -n 's/^Model name:[[:space:]]*//p' | head -n 1)
    out=$(tok "${out:-}")
    [ -n "$out" ] || fail "cannot read the CPU model (/proc/cpuinfo, lscpu)"
    printf '%s' "$out"
}

ram_mt_s() {
    local raw= speeds count out
    if command -v dmidecode >/dev/null 2>&1; then
        raw=$(dmidecode -t memory 2>/dev/null) || raw=
        [ -n "$raw" ] || raw=$(sudo -n dmidecode -t memory 2>/dev/null) || raw=
    fi
    # RAM has moved between these rigs twice in six days. Never guessed.
    [ -n "$raw" ] || fail "cannot read the DDR speed: dmidecode -t memory produced nothing (needs root, or sudo -n)"
    speeds=$(printf '%s\n' "$raw" | sed -n 's/^[[:space:]]*Configured Memory Speed:[[:space:]]*\([0-9][0-9]*\)[[:space:]]*MT\/s.*/\1/p' | sort -u)
    [ -n "$speeds" ] || fail "dmidecode reported no 'Configured Memory Speed' line; the DDR speed is unread"
    count=$(printf '%s\n' "$speeds" | wc -l)
    [ "$count" -eq 1 ] || fail "dmidecode reports $count different configured memory speeds ($(printf '%s' "$speeds" | tr '\n' ' ')); one token cannot name them honestly"
    out=$(tok "$speeds")
    printf '%s' "$out"
}

rapl_dir() {
    local d
    for d in /sys/class/powercap/intel-rapl:0 /sys/class/powercap/intel-rapl/intel-rapl:0; do
        [ -d "$d" ] && { printf '%s' "$d"; return 0; }
    done
    fail "no intel-rapl package directory under /sys/class/powercap; the power limits are unread"
}

power_limit() {
    local which=$1 d idx want got out
    d=$(rapl_dir) || exit 1
    case $which in
        pl1) idx=0; want=long_term ;;
        pl2) idx=1; want=short_term ;;
    esac
    # constraint_N_power_limit_uw, never constraint_N_max_power_uw: the latter is
    # the CPU's rated TDP and reads 95000000 whatever the live limit is, which
    # looks exactly like the cap being in force when it is not.
    [ -r "$d/constraint_${idx}_power_limit_uw" ] || fail "$d/constraint_${idx}_power_limit_uw is unreadable; $which is unread"
    got=$(cat "$d/constraint_${idx}_name" 2>/dev/null) || got=
    [ -z "$got" ] || [ "$got" = "$want" ] || fail "$d/constraint_${idx}_name reads '$got', not '$want'; the constraint indices are not what $which assumes"
    out=$(tok "$(cat "$d/constraint_${idx}_power_limit_uw")")
    case $out in ''|*[!0-9]*) fail "$which read '$out', which is not a number of microwatts" ;; esac
    printf '%s' "$out"
}

nvidia() {
    local out line name total cc drv reserved used free f
    command -v nvidia-smi >/dev/null 2>&1 || fail "nvidia-smi is not on PATH; the GPU state is unread"
    out=$(nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version,memory.reserved,memory.used,memory.free --format=csv,noheader,nounits 2>/dev/null) || out=
    if [ -z "$out" ]; then
        out=$(nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv,noheader,nounits 2>/dev/null) || out=
        [ -n "$out" ] || fail "nvidia-smi returned nothing; the GPU state is unread"
        out="$out, [N/A], [N/A], [N/A]"
    fi
    line=$(printf '%s\n' "$out" | head -n 1)
    IFS=, read -r name total cc drv reserved used free <<EOF
$line
EOF
    name=$(tok "$name"); total=$(tok "$total"); cc=$(tok "$cc"); drv=$(tok "$drv")
    reserved=$(tok "${reserved:-}"); used=$(tok "${used:-}"); free=$(tok "${free:-}")
    case $reserved in
        ''|*[!0-9]*)
            # The reserve is GSP firmware and differs per boot, so it is derived
            # from the other three rather than assumed when the driver omits it.
            case $total$used$free in
                *[!0-9]*) fail "nvidia-smi reports no memory.reserved and no usable total/used/free; gpu_reserve_mib is unread" ;;
                '') fail "nvidia-smi reports no memory figures at all" ;;
            esac
            reserved=$((total - used - free))
            ;;
    esac
    for f in "$name" "$total" "$cc" "$drv"; do
        [ -n "$f" ] || fail "nvidia-smi left one of name/memory.total/compute_cap/driver_version empty: '$line'"
    done
    # used/free are printed too: gate 2 compares only the declared keys, but a
    # placement needs `free` and reading it in the same breath as the rest is
    # what makes it the same card at the same moment.
    printf 'gpu_name=%s\ngpu_vram_mib=%s\ngpu_cc=%s\ndriver=%s\ngpu_reserve_mib=%s\ngpu_used_mib=%s\ngpu_free_mib=%s\n' \
        "$name" "$total" "$cc" "$drv" "$reserved" "${used:-NA}" "${free:-NA}"
}

docker_version() {
    local out
    out=$("${RUN_DOCKER:-docker}" version --format '{{.Server.Version}}' 2>/dev/null) || out=
    out=$(tok "${out:-}")
    # A Vulkan ICD manifest is mounted by one docker version and not by another,
    # so the daemon version is a fact of the rig and not of the tooling.
    [ -n "$out" ] || fail "cannot read the docker daemon's version"
    printf '%s' "$out"
}

mem_available_kib() {
    local out
    out=$(awk '/^MemAvailable:/{print $2; exit}' /proc/meminfo 2>/dev/null) || out=
    case ${out:-} in ''|*[!0-9]*) fail "cannot read MemAvailable from /proc/meminfo" ;; esac
    printf '%s' "$out"
}

printf 'uptime_since=%s\n' "$(uptime_since)"
printf 'cpu_max_mhz=%s\n'  "$(cpu_max_mhz)"
printf 'cpu_model=%s\n'    "$(cpu_model)"
printf 'ram_mt_s=%s\n'     "$(ram_mt_s)"
printf 'pl1_uw=%s\n'       "$(power_limit pl1)"
printf 'pl2_uw=%s\n'       "$(power_limit pl2)"
nvidia
printf 'docker=%s\n'          "$(docker_version)"
printf 'mem_available_kib=%s\n' "$(mem_available_kib)"
printf 'nproc=%s\n'           "$(nproc 2>/dev/null || echo NA)"
