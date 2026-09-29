#!/usr/bin/env bash
# A machine's short account of itself: its id, its host name, and the cards its
# sources show, each with its name, its memory and the processes holding it.
#
# SHIPPED ON STDIN like the door's other readers (`bash -s`). It changes
# nothing on the machine and writes no file there: it holds no here-string and
# no here-document (bash may back either with a temporary file), and every
# tool's output reaches it through a pipe. It asks for no raised rights: every
# source below is one an ordinary user may read, and a source that cannot be
# read is named, never asked again with more rights.
#
# It never fails over a field. A field it cannot read is left empty and named
# on its own `unread=` line with the reason, and the script goes on. What a tool
# prints is untrusted: a value that is not what its field takes (a size that is
# not a whole number, a name or container value with a control character or
# over its length bound, a line longer than LINE_MAX) is named unread and is
# not printed.
#
# Output, one `key=value` per line. The free-text field of a row comes last, so
# a comma inside it is kept; an empty field was not read. The machine id and
# host lines are printed first, before any card tool is asked, so a caller that
# gives up on a slow tool still holds them.
#
#   machine_id=HEX16             the first 16 hex of the sha256 of the first
#                                line of the first machine-id file that is
#                                there and not blank, else of `host:NAME`
#   machine_id_from=PATH|hostname  which of the two the id was taken from
#   host=NAME                    the machine's host name
#   cards=SOURCE[,SOURCE]|none   the card sources that gave a card
#   card=VENDOR,INDEX,TOTAL,USED,FREE,NAME   one per card, sizes in MiB
#   holder=VENDOR,INDEX,PID,MIB,NAME         one per process on a card
#   container=NAME,ID,PROJECT,RESTARTS       every running container, spelled
#                                            as rig-units.sh spells it
#   unread=FIELD,WHY             a field that could not be read, and why
#
# Card sources: the first vendor's tool (nvidia-smi) and the second vendor's
# tool (rocm-smi), each one that is installed; then sysfs, for the cards of
# every vendor that no answering tool covered. A card is listed once: sysfs
# gives no card of a vendor a tool answered for, and when sysfs shows more
# cards of that vendor than the tool printed, the tool's list is named unread.
# A tool that is installed and prints no card, or fails, is named unread.
# A card is known by its vendor and its index as its source numbers it, so two
# vendors may both have a card 0. Nothing here sums the cards or picks one.
#
# Programs it uses besides the card tools and docker: sha256sum; timeout, when
# it is there, to bound every tool call (without it the calls are unbounded,
# and the reading says so); python3, only to read the second vendor's tool's
# JSON (ASSUMED to be on PATH wherever that tool is, since the tool is itself a
# Python program; where it is not, that tool's cards are named unread);
# hostname, only when /proc does not give the host name and no test root is
# set.
#
# Two variables are for the product's tests only. MCGYVR_TEST_MACHINE_ROOT: every
# file this script reads is read under that folder, and the `hostname` program
# is not asked. MCGYVR_TEST_TOOL_SECONDS: the bound on each tool call.
set -u
shopt -s lastpipe
export LC_ALL=C

ROOT=${MCGYVR_TEST_MACHINE_ROOT:-}
BOUND_S=${MCGYVR_TEST_TOOL_SECONDS:-20}
case $BOUND_S in ''|*[!0-9]*) BOUND_S=20 ;; esac

# The longest card, process or container value passed on, in bytes.
NAME_MAX=256
# The longest run of digits taken as a size: more would overflow the shell's
# arithmetic, so a longer one is named unread rather than wrapped.
DIGITS_MAX=18
# The longest line taken from a tool or a file, in bytes, checked before
# anything else is done with the line; and the most lines taken from one call.
LINE_MAX=4096
LINES_MAX=4096
MIB_BYTES=1048576

# Files, relative to the root; nothing is read outside ROOT.
MACHINE_ID_FILES=(etc/machine-id var/lib/dbus/machine-id)
HOSTNAME_FILE=proc/sys/kernel/hostname
DRM=sys/class/drm

# Rows, printed at the end so a card can still be marked after it was read.
C_VENDOR=() C_INDEX=() C_TOTAL=() C_USED=() C_FREE=() C_NAME=() C_DROP=()
H_VENDOR=() H_INDEX=() H_PID=() H_MIB=() H_NAME=()
U_FIELD=() U_WHY=()
SOURCES=()
COVERED=" "
declare -A PRINTED=()

unread() { U_FIELD+=("$1"); U_WHY+=("$2"); }

HAVE_TIMEOUT=
if command -v timeout >/dev/null 2>&1; then
    HAVE_TIMEOUT=1
else
    unread tool_bound "timeout is not on PATH; the card tools and docker are asked without a time bound"
fi

# A tool call: standard input from /dev/null (a tool that reads it would
# otherwise read the rest of this script), standard error dropped, and at most
# BOUND_S seconds when `timeout` is there.
run_tool() {
    if [ -n "$HAVE_TIMEOUT" ]; then
        timeout -k 2 "$BOUND_S" "$@" </dev/null 2>/dev/null
    else
        "$@" </dev/null 2>/dev/null
    fi
}

# WHY: what exit status $1 of tool call $2 means.
exit_why() {
    if [ -n "$HAVE_TIMEOUT" ] && { [ "$1" -eq 124 ] || [ "$1" -eq 137 ]; }; then
        WHY="$2 did not answer within $BOUND_S s"
    else
        WHY="$2 exited $1"
    fi
}

# TRIM: $1 without leading and trailing white space. Only ever called on a
# value no longer than LINE_MAX, since the patterns below are slow on long ones.
trim() {
    local s=$1
    s=${s#"${s%%[![:space:]]*}"}
    s=${s%"${s##*[![:space:]]}"}
    TRIM=$s
}

# F: $3 split on the first $2-1 occurrences of $1; the last field keeps the
# rest, and fields past the end are empty.
split_fields() {
    local sep=$1 n=$2 rest=$3 i more=1
    F=()
    for ((i = 1; i < n; i++)); do
        if [ $more -eq 1 ] && [[ $rest == *"$sep"* ]]; then
            F+=("${rest%%"$sep"*}")
            rest=${rest#*"$sep"}
        elif [ $more -eq 1 ]; then
            F+=("$rest")
            rest=
            more=0
        else
            F+=("")
        fi
    done
    F+=("$rest")
}

# NUM: $1 as a whole number of MiB, or empty after naming $2 unread.
# $3 names the source, $4 is `bytes` when the value is in bytes.
number() {
    local v
    trim "$1"; v=$TRIM
    NUM=
    case $v in
        '') unread "$2" "$3 printed no value for it" ;;
        '[N/A]'|'N/A') unread "$2" "$3 printed [N/A] for it" ;;
        *[!0-9]*) unread "$2" "$3 printed a value for it that is not a whole number" ;;
        *)
            if [ ${#v} -gt $DIGITS_MAX ]; then
                unread "$2" "$3 printed a number for it too large to be a size"
            elif [ "${4:-}" = bytes ]; then
                NUM=$((10#$v / MIB_BYTES))
            else
                NUM=$((10#$v))
            fi
            ;;
    esac
}

# TEXT: $1 trimmed if it is a name, or empty after naming $2 unread.
name() {
    local v
    trim "$1"; v=$TRIM
    TEXT=
    if [ -z "$v" ]; then
        unread "$2" "$3 printed no name for it"
    elif [[ $v == *[[:cntrl:]]* ]]; then
        unread "$2" "$3 printed a name with control characters in it"
    elif [ ${#v} -gt $NAME_MAX ]; then
        unread "$2" "$3 printed a name longer than $NAME_MAX bytes"
    else
        TEXT=$v
    fi
}

# FREE: total less used, or empty after naming $3 unread.
free_of() { # TOTAL USED FIELD SOURCE
    FREE=
    if [ -z "$1" ] || [ -z "$2" ]; then
        unread "$3" "free memory is the total less the used, and one of them is unread"
    elif [ "$2" -gt "$1" ]; then
        unread "$3" "$4 printed more memory used than the card's total"
    else
        FREE=$(($1 - $2))
    fi
}

# ADDED: the position of the card with this vendor and index, new or not.
add_card() { # VENDOR INDEX TOTAL USED FREE NAME
    local k
    PRINTED[$1]=$((${PRINTED[$1]:-0} + 1))
    for k in "${!C_INDEX[@]}"; do
        if [ "${C_VENDOR[$k]}" = "$1" ] && [ "${C_INDEX[$k]}" = "$2" ]; then
            [ -n "${C_DROP[$k]}" ] || unread "card.$1.$2" "the card source printed index $2 twice; neither line is taken"
            C_DROP[$k]=1
            ADDED=$k
            return
        fi
    done
    C_VENDOR+=("$1") C_INDEX+=("$2") C_TOTAL+=("$3") C_USED+=("$4") C_FREE+=("$5")
    C_NAME+=("$6") C_DROP+=("")
    ADDED=$((${#C_INDEX[@]} - 1))
}

# FILE: the first line of file $1, trimmed; status 1, with WHY, when the file
# is not there, not readable, or its line is longer than LINE_MAX.
read_file() {
    FILE=
    WHY="is not there or not readable"
    [ -f "$1" ] && [ -r "$1" ] || return 1
    local line=
    IFS= read -r line <"$1" || [ -n "$line" ] || return 1
    if [ ${#line} -gt $LINE_MAX ]; then
        WHY="holds a line longer than $LINE_MAX bytes"
        return 1
    fi
    trim "$line"; FILE=$TRIM
    return 0
}

# --- the first vendor's tool ----------------------------------------------
# Format (from the tool's public documentation, `--help-query-gpu`): with
# `--format=csv,noheader,nounits` it prints one line per card, the queried
# fields in order separated by ", ", sizes in MiB, and `[N/A]` for a value it
# cannot give. The name is asked last, so a comma in it stays in the name. A
# name holding a line break is caught only when the part after the break does
# not look like a card row; otherwise it forges a row of the same kind.
FIRST_QUERY=index,memory.total,memory.used,memory.free,name
# The process listing (`--help-query-compute-apps`): one line per process,
# `pid, used MiB, name`. ASSUMED, not tried on a machine here: that `-i N`
# limits it to card N, and that an idle card may print the sentence "No
# running processes found". A process name holding a line break can forge a
# holder row on the same card. Holders are a report only; they are never part
# of the machine's identity.
FIRST_APPS=pid,used_memory,process_name

# A tool that answered and gave no card: named, unless already named.
no_card() { # FIELD TOOL
    local f
    for f in "${U_FIELD[@]}"; do [ "$f" = "$1" ] && return 0; done
    unread "$1" "$2 is installed and printed no card. If this machine has no card of its vendor, the tool is left over and can be removed"
}

first_tool() {
    local rc line idx k="" start total used free
    local -a OUT=()
    command -v nvidia-smi >/dev/null 2>&1 || return 0
    run_tool nvidia-smi --query-gpu=$FIRST_QUERY --format=csv,noheader,nounits |
        mapfile -t -n $((LINES_MAX + 1)) OUT
    rc=${PIPESTATUS[0]}
    if [ ${#OUT[@]} -gt $LINES_MAX ]; then
        unread cards.nvidia-smi "nvidia-smi printed more than $LINES_MAX lines; its cards are unread"
        return 0
    fi
    if [ "$rc" -ne 0 ]; then
        exit_why "$rc" "nvidia-smi --query-gpu"
        unread cards.nvidia-smi "$WHY; its cards are unread. Run nvidia-smi by hand to see why, or remove it if this machine has no card of its vendor"
        return 0
    fi
    start=${#C_INDEX[@]}
    for line in "${OUT[@]}"; do
        if [ ${#line} -gt $LINE_MAX ]; then
            unread cards.nvidia-smi "nvidia-smi printed a line longer than $LINE_MAX bytes"
            continue
        fi
        [ -n "${line//[[:space:]]/}" ] || continue
        split_fields , 5 "$line"
        trim "${F[0]}"; idx=$TRIM
        case $idx in
            ''|*[!0-9]*)
                if [ -n "$k" ]; then
                    # A line that is not a card after a card: its name may have
                    # run over a line break, so the name before is not trusted.
                    C_NAME[$k]=
                    unread "card.nvidia.${C_INDEX[$k]}.name" "nvidia-smi printed a line after this card that is not a card line; its name may run over a line break"
                else
                    unread cards.nvidia-smi "nvidia-smi printed a line that is not a card line"
                fi
                continue
                ;;
        esac
        if [ ${#idx} -gt 9 ]; then
            unread cards.nvidia-smi "nvidia-smi printed a card index too large to be one"
            continue
        fi
        idx=$((10#$idx))
        number "${F[1]}" "card.nvidia.$idx.total" nvidia-smi; total=$NUM
        number "${F[2]}" "card.nvidia.$idx.used" nvidia-smi; used=$NUM
        number "${F[3]}" "card.nvidia.$idx.free" nvidia-smi; free=$NUM
        name "${F[4]}" "card.nvidia.$idx.name" nvidia-smi
        add_card nvidia "$idx" "$total" "$used" "$free" "$TEXT"
        k=$ADDED
    done
    if [ ${#C_INDEX[@]} -gt "$start" ]; then
        SOURCES+=(nvidia-smi)
        COVERED+="nvidia "
    else
        no_card cards.nvidia-smi nvidia-smi
    fi
    for k in "${!C_INDEX[@]}"; do
        [ "$k" -ge "$start" ] && [ -z "${C_DROP[$k]}" ] && first_tool_holders "${C_INDEX[$k]}"
    done
    return 0
}

first_tool_holders() { # INDEX
    local rc line pid key=card.nvidia.$1 i
    local -a OUT=() pids=() mibs=() names=()
    run_tool nvidia-smi -i "$1" --query-compute-apps=$FIRST_APPS --format=csv,noheader,nounits |
        mapfile -t -n $((LINES_MAX + 1)) OUT
    rc=${PIPESTATUS[0]}
    if [ ${#OUT[@]} -gt $LINES_MAX ]; then
        unread "$key.holders" "nvidia-smi printed more than $LINES_MAX process lines"
        return 0
    fi
    if [ "$rc" -ne 0 ]; then
        exit_why "$rc" "nvidia-smi --query-compute-apps"
        unread "$key.holders" "$WHY; the processes on this card are unread"
        return 0
    fi
    for line in "${OUT[@]}"; do
        if [ ${#line} -gt $LINE_MAX ]; then
            unread "$key.holders" "nvidia-smi printed a process line longer than $LINE_MAX bytes"
            return 0
        fi
        [ -n "${line//[[:space:]]/}" ] || continue
        [ "$line" = "No running processes found" ] && continue
        split_fields , 3 "$line"
        trim "${F[0]}"; pid=$TRIM
        case $pid in
            ''|*[!0-9]*)
                unread "$key.holders" "nvidia-smi printed a process line that does not start with a process id"
                return 0
                ;;
        esac
        if [ ${#pid} -gt 9 ]; then
            unread "$key.holders" "nvidia-smi printed a process id too large to be one"
            return 0
        fi
        pid=$((10#$pid))
        number "${F[1]}" "$key.holder.$pid.mib" nvidia-smi
        name "${F[2]}" "$key.holder.$pid.name" nvidia-smi
        pids+=("$pid") mibs+=("$NUM") names+=("$TEXT")
    done
    for i in "${!pids[@]}"; do
        H_VENDOR+=(nvidia) H_INDEX+=("$1") H_PID+=("${pids[$i]}")
        H_MIB+=("${mibs[$i]}") H_NAME+=("${names[$i]}")
    done
    return 0
}

# --- the second vendor's tool ---------------------------------------------
# Format (from the tool's public documentation and source): the tool is a
# Python program; `--showproductname --showmeminfo vram --json` prints a JSON
# object with a member per card named `cardN`, each an object of strings; the
# card's name is under `Card series` (else `Card model`), its memory in bytes
# under `VRAM Total Memory (B)` and `VRAM Total Used Memory (B)`. Key case
# differs between versions, so keys are matched without case. ASSUMED, not
# tried on a machine here: that its exit status is 0 when it answers, that its
# standard output holds the JSON alone (a warning line before it reads as "not
# JSON"), and that python3 is on PATH wherever it runs. This reader asks it
# for no process listing, so the processes on its cards are named unread.
#
# The JSON is read by `python3 -I`: isolated, so no module is taken from the
# working folder or the user's site folder.
SECOND_READER='
import json, re, sys
SEP = "\x1f"
def out(*fields):
    sys.stdout.buffer.write((SEP.join(fields) + "\n").encode("utf-8", "replace"))
def text(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    return "".join(c if c.isprintable() else "\x01" for c in str(value))
try:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
except ValueError:
    out("error", "its output is not JSON")
    sys.exit(0)
if not isinstance(data, dict):
    out("error", "its output is not a JSON object")
    sys.exit(0)
rows = []
for key, entry in data.items():
    card = re.fullmatch("card([0-9]{1,9})", key)
    if not card:
        continue
    if not isinstance(entry, dict):
        out("error", "its entry for a card is not a JSON object")
        continue
    low = dict((str(k).lower(), v) for k, v in entry.items())
    name = low.get("card series", low.get("card model", ""))
    rows.append((int(card.group(1)), text(low.get("vram total memory (b)", "")),
                 text(low.get("vram total used memory (b)", "")), text(name)))
for index, total, used, name in sorted(rows):
    out("card", str(index), total, used, name)
'

run_python() {
    if [ -n "$HAVE_TIMEOUT" ]; then
        timeout -k 2 "$BOUND_S" python3 -I -c "$SECOND_READER" 2>/dev/null
    else
        python3 -I -c "$SECOND_READER" 2>/dev/null
    fi
}

second_tool() {
    local rc prc line idx total used free start
    local -a OUT=()
    command -v rocm-smi >/dev/null 2>&1 || return 0
    if ! command -v python3 >/dev/null 2>&1; then
        unread cards.rocm-smi "python3 is not on PATH to read the JSON rocm-smi prints; its cards are unread"
        return 0
    fi
    run_tool rocm-smi --showproductname --showmeminfo vram --json | run_python |
        mapfile -t -n $((LINES_MAX + 1)) OUT
    rc=${PIPESTATUS[0]} prc=${PIPESTATUS[1]}
    if [ "$rc" -ne 0 ]; then
        exit_why "$rc" "rocm-smi --json"
        unread cards.rocm-smi "$WHY; its cards are unread. Run rocm-smi by hand to see why, or remove it if this machine has no card of its vendor"
        return 0
    fi
    if [ "$prc" -ne 0 ]; then
        exit_why "$prc" "reading the JSON rocm-smi printed"
        unread cards.rocm-smi "$WHY; its cards are unread"
        return 0
    fi
    if [ ${#OUT[@]} -gt $LINES_MAX ]; then
        unread cards.rocm-smi "rocm-smi printed more than $LINES_MAX cards; its cards are unread"
        return 0
    fi
    start=${#C_INDEX[@]}
    for line in "${OUT[@]}"; do
        if [ ${#line} -gt $LINE_MAX ]; then
            unread cards.rocm-smi "rocm-smi printed a card entry longer than $LINE_MAX bytes"
            continue
        fi
        split_fields $'\x1f' 5 "$line"
        case ${F[0]} in
            card) ;;
            error) unread cards.rocm-smi "rocm-smi: ${F[1]}"; continue ;;
            *) continue ;;
        esac
        idx=${F[1]}
        case $idx in ''|*[!0-9]*) continue ;; esac
        [ ${#idx} -le 9 ] || continue
        idx=$((10#$idx))
        number "${F[2]}" "card.amd.$idx.total" rocm-smi bytes; total=$NUM
        number "${F[3]}" "card.amd.$idx.used" rocm-smi bytes; used=$NUM
        free_of "$total" "$used" "card.amd.$idx.free" rocm-smi; free=$FREE
        name "${F[4]}" "card.amd.$idx.name" rocm-smi
        add_card amd "$idx" "$total" "$used" "$free" "$TEXT"
        unread "card.amd.$idx.holders" "this reader asks rocm-smi for no process listing"
    done
    if [ ${#C_INDEX[@]} -gt "$start" ]; then
        SOURCES+=(rocm-smi)
        COVERED+="amd "
    else
        no_card cards.rocm-smi rocm-smi
    fi
    return 0
}

# --- sysfs ------------------------------------------------------------------
# Format (from the kernel's public documentation): each card is
# /sys/class/drm/cardN (connectors are cardN-NAME), its PCI ids in
# device/vendor and device/device as `0xHHHH`; the amdgpu driver publishes the
# memory in bytes as device/mem_info_vram_total and device/mem_info_vram_used.
# ASSUMED, not tried on a machine here: which drivers publish
# device/product_name, and that the cardN numbering is stable. A card with no
# name file is named by its PCI ids; a card whose driver publishes no memory
# size has its size named unread. No process is listed.
#
# Vendor names for three PCI vendor ids, as the public PCI ID list names them:
# 0x10de is the first tool's vendor and 0x1002 the second's (ASSUMED: each
# tool reads the cards of that vendor id and no other); 0x8086 is named, and
# no tool here reads its cards. Any other vendor is named by its id.
pci_vendor() {
    case $1 in
        0x10de) VENDOR=nvidia ;;
        0x1002) VENDOR=amd ;;
        0x8086) VENDOR=intel ;;
        *) VENDOR=pci-$1 ;;
    esac
}

tool_of() {
    case $1 in
        nvidia) TOOL=nvidia-smi ;;
        amd) TOOL=rocm-smi ;;
        *) TOOL=$1 ;;
    esac
}

sysfs() {
    local dir n dev vid did pname total used free key start v
    local -A SEEN=()
    start=${#C_INDEX[@]}
    for dir in "$ROOT/$DRM/card"*; do
        [ -d "$dir" ] || continue
        n=${dir##*/card}
        case $n in ''|*[!0-9]*) continue ;; esac
        [ ${#n} -le 9 ] || continue
        n=$((10#$n))
        dev=$dir/device
        vid=
        read_file "$dev/vendor" && vid=$FILE
        case $vid in
            0x[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]) vid=${vid,,} ;;
            *)
                unread "card.pci.$n" "sysfs gives no vendor id for card$n"
                continue
                ;;
        esac
        pci_vendor "$vid"
        SEEN[$VENDOR]=$((${SEEN[$VENDOR]:-0} + 1))
        # A vendor a tool answered for is that tool's; sysfs adds no card of it.
        [[ $COVERED == *" $VENDOR "* ]] && continue
        key=card.$VENDOR.$n
        did=
        read_file "$dev/device" && did=$FILE
        case $did in
            0x[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]) did=${did,,} ;;
            *) did= ;;
        esac
        pname=
        if read_file "$dev/product_name" && [ -n "$FILE" ]; then
            pname=$FILE
        elif [ -n "$did" ]; then
            pname="PCI $vid:$did"
        fi
        name "$pname" "$key.name" sysfs
        pname=$TEXT
        total= used=
        if read_file "$dev/mem_info_vram_total"; then
            number "$FILE" "$key.total" sysfs bytes; total=$NUM
        else
            unread "$key.total" "sysfs gives no memory size for this card: device/mem_info_vram_total $WHY. Its driver may not publish one; the card tool of its vendor may read it"
        fi
        if read_file "$dev/mem_info_vram_used"; then
            number "$FILE" "$key.used" sysfs bytes; used=$NUM
        else
            unread "$key.used" "sysfs gives no used memory for this card: device/mem_info_vram_used $WHY"
        fi
        free_of "$total" "$used" "$key.free" sysfs; free=$FREE
        add_card "$VENDOR" "$n" "$total" "$used" "$free" "$pname"
        unread "$key.holders" "sysfs does not list the processes on a card"
    done
    [ ${#C_INDEX[@]} -gt "$start" ] && SOURCES+=(sysfs)
    # A tool that printed fewer cards than sysfs shows of its vendor.
    for v in "${!SEEN[@]}"; do
        [[ $COVERED == *" $v "* ]] || continue
        if [ "${SEEN[$v]}" -gt "${PRINTED[$v]:-0}" ]; then
            tool_of "$v"
            unread "cards.$TOOL" "sysfs shows ${SEEN[$v]} cards of vendor $v and $TOOL printed ${PRINTED[$v]:-0}; its list of cards may be short"
        fi
    done
    return 0
}

# --- containers, as rig-units.sh lists them -------------------------------
# One whitespace-free, comma-free token, as rig-units.sh's `tok` makes it:
# every run of blanks, line breaks and commas becomes one `_`, and one `_` is
# taken off each end. Unlike rig-units.sh, a value with a control character or
# longer than NAME_MAX is not printed: the containers are named unread.
tok() {
    local s=$1
    s=${s//[$' \t\n,']/_}
    while [[ $s == *__* ]]; do s=${s//__/_}; done
    s=${s#_}; s=${s%_}
    TOK=$s
}

# Whether $1 may be printed as a container value.
fit() {
    [[ $1 != *[[:cntrl:]]* ]] && [ ${#1} -le $NAME_MAX ]
}

containers() {
    local rc line id cname project restarts
    local -a OUT=() rows=()
    if ! command -v docker >/dev/null 2>&1; then
        unread containers "docker is not on PATH"
        return 0
    fi
    run_tool docker ps --no-trunc --format '{{.ID}}|{{.Names}}|{{.Label "com.docker.compose.project"}}' |
        mapfile -t -n $((LINES_MAX + 1)) OUT
    rc=${PIPESTATUS[0]}
    if [ "$rc" -ne 0 ]; then
        exit_why "$rc" "docker ps"
        unread containers "$WHY; this user may not be allowed to reach the docker daemon"
        return 0
    fi
    if [ ${#OUT[@]} -gt $LINES_MAX ]; then
        unread containers "docker ps printed more than $LINES_MAX lines"
        return 0
    fi
    for line in "${OUT[@]}"; do
        if [ ${#line} -gt $LINE_MAX ]; then
            unread containers "docker ps printed a line longer than $LINE_MAX bytes"
            return 0
        fi
        split_fields '|' 3 "$line"
        id=${F[0]} cname=${F[1]} project=${F[2]}
        [ -n "$id" ] || continue
        if ! fit "$id" || ! fit "$cname" || ! fit "$project"; then
            unread containers "docker ps printed a container value with a control character or longer than $NAME_MAX bytes"
            return 0
        fi
        tok "$project"; project=$TOK
        tok "$cname"; cname=$TOK
        tok "$id"; id=$TOK
        restarts=$(run_tool docker inspect --format '{{.RestartCount}}' "$id") || restarts=
        fit "$restarts" || restarts=
        tok "$restarts"; restarts=$TOK
        case $restarts in ''|*[!0-9]*)
            restarts=unread
            unread "container.$id.restarts" "docker inspect gave no restart count"
            ;;
        esac
        rows+=("container=$cname,$id,${project:--},$restarts")
    done
    [ ${#rows[@]} -eq 0 ] || printf '%s\n' "${rows[@]}"
    return 0
}

# --- the machine ------------------------------------------------------------
host_name() {
    HOST=
    local got=
    if read_file "$ROOT/$HOSTNAME_FILE"; then
        got=$FILE
    elif [ -z "$ROOT" ] && command -v hostname >/dev/null 2>&1; then
        got=$(run_tool hostname) || got=
    fi
    if [ -z "$got" ]; then
        unread host "the host name is unread (/$HOSTNAME_FILE, hostname)"
    elif [ ${#got} -gt 253 ]; then
        unread host "the host name is longer than a host name may be"
    elif [[ $got == *[!A-Za-z0-9._-]* ]]; then
        unread host "the host name holds characters a host name does not"
    else
        HOST=$got
    fi
}

machine_id() {
    local f seed= from= sum
    MID= MID_FROM=
    for f in "${MACHINE_ID_FILES[@]}"; do
        read_file "$ROOT/$f" || continue
        if [ -n "$FILE" ]; then seed=$FILE; from=/$f; break; fi
    done
    if [ -z "$seed" ] && [ -n "$HOST" ]; then
        seed="host:$HOST"; from=hostname
    fi
    if [ -z "$seed" ]; then
        unread machine_id "no machine-id file (/${MACHINE_ID_FILES[0]}, /${MACHINE_ID_FILES[1]}) and no host name to derive it from"
        return 0
    fi
    if ! command -v sha256sum >/dev/null 2>&1; then
        unread machine_id "sha256sum is not on PATH"
        return 0
    fi
    sum=$(printf '%s' "$seed" | sha256sum 2>/dev/null) || sum=
    sum=${sum:0:16}
    if [[ ${#sum} -eq 16 && $sum != *[!0-9a-f]* ]]; then
        MID=$sum MID_FROM=$from
    else
        unread machine_id "sha256sum gave no digest"
    fi
}

host_name
machine_id
printf 'machine_id=%s\n' "$MID"
printf 'machine_id_from=%s\n' "$MID_FROM"
printf 'host=%s\n' "$HOST"

first_tool
second_tool
sysfs

if [ ${#SOURCES[@]} -eq 0 ]; then
    printf 'cards=none\n'
else
    (IFS=,; printf 'cards=%s\n' "${SOURCES[*]}")
fi
for k in "${!C_INDEX[@]}"; do
    [ -z "${C_DROP[$k]}" ] || continue
    printf 'card=%s,%s,%s,%s,%s,%s\n' "${C_VENDOR[$k]}" "${C_INDEX[$k]}" \
        "${C_TOTAL[$k]}" "${C_USED[$k]}" "${C_FREE[$k]}" "${C_NAME[$k]}"
done
for k in "${!H_PID[@]}"; do
    printf 'holder=%s,%s,%s,%s,%s\n' "${H_VENDOR[$k]}" "${H_INDEX[$k]}" \
        "${H_PID[$k]}" "${H_MIB[$k]}" "${H_NAME[$k]}"
done
containers
for k in "${!U_FIELD[@]}"; do
    printf 'unread=%s,%s\n' "${U_FIELD[$k]}" "${U_WHY[$k]}"
done
exit 0
