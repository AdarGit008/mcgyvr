#!/usr/bin/env bash
# A machine's short account of itself: its id, its host name, and every card
# with its name, its memory and the processes holding it.
#
# SHIPPED ON STDIN like the door's other readers (`bash -s`): nothing lands on
# the machine's disk and nothing on it is changed. It asks for no raised
# rights: every source below is one an ordinary user may read, and a source
# that cannot be read is named, never asked again with more rights.
#
# It never fails over a field. A field it cannot read is left empty and named
# on its own line with the reason, and the script goes on. Everything a tool
# prints is taken as untrusted: a value that is not what it should be is named
# unread, never passed on.
#
# Output, one `key=value` per line. The free-text field of a row comes last, so
# a comma inside it is kept; an empty field was not read.
#
#   machine_id=HEX16             the first 16 hex of the sha256 of the first
#                                machine-id file that is there and not empty,
#                                else of `host:NAME`, as `mcgyvr scan` derives
#                                its machine id
#   machine_id_from=PATH|hostname  which of the two the id was taken from
#   host=NAME                    the machine's host name
#   cards=SOURCE[,SOURCE]|none   the card sources that gave a card
#   card=VENDOR,INDEX,TOTAL,USED,FREE,NAME   one per card, sizes in MiB
#   holder=VENDOR,INDEX,PID,MIB,NAME         one per process on a card
#   container=NAME,ID,PROJECT,RESTARTS       every running container, spelled
#                                            as rig-units.sh spells it
#   unread=FIELD,WHY             a field that could not be read, and why
#
# Card sources, in order: the first vendor's tool (nvidia-smi), then the
# second vendor's tool (rocm-smi); each one that is installed is asked. sysfs
# is read only when neither gave a card. A card is known by its vendor and its
# index as its source numbers it, so two vendors may both have a card 0.
# Nothing here sums the cards or picks one of them.
#
# Programs it uses besides the card tools and docker: sha256sum, and python3
# only to read the second vendor's tool's JSON (that tool is itself a Python
# program, so where it runs python3 is there).
#
# MCGYVR_TEST_MACHINE_ROOT is for the product's tests only: every file this
# script reads is read under that folder when it is set, so a test can give it
# an invented machine. It changes no command.
set -u
export LC_ALL=C

ROOT=${MCGYVR_TEST_MACHINE_ROOT:-}

# The longest card or process name passed on; a longer one is named unread.
NAME_MAX=256
# The longest run of digits taken as a size: more would overflow the shell's
# arithmetic, so a longer one is named unread rather than wrapped.
DIGITS_MAX=18
MIB_BYTES=1048576

# Rows, printed at the end so a card can still be marked after it was read.
C_VENDOR=() C_INDEX=() C_TOTAL=() C_USED=() C_FREE=() C_NAME=() C_DROP=()
H_VENDOR=() H_INDEX=() H_PID=() H_MIB=() H_NAME=()
U_FIELD=() U_WHY=()
SOURCES=()

unread() { U_FIELD+=("$1"); U_WHY+=("$2"); }

# TRIM: $1 without leading and trailing white space.
trim() {
    local s=$1
    s=${s#"${s%%[![:space:]]*}"}
    s=${s%"${s##*[![:space:]]}"}
    TRIM=$s
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
        unread "$2" "$3 printed a name longer than $NAME_MAX characters"
    else
        TEXT=$v
    fi
}

# ADDED: the position of the card with this vendor and index, new or not.
add_card() { # VENDOR INDEX TOTAL USED FREE NAME
    local k
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

# --- the first vendor's tool ----------------------------------------------
# Format assumption (from the tool's documentation, `--help-query-gpu`): with
# `--format=csv,noheader,nounits` it prints one line per card, the queried
# fields in order separated by ", ", sizes in MiB, and `[N/A]` for a value it
# cannot give. The name is asked last, so a comma in it stays in the name.
FIRST_QUERY=index,memory.total,memory.used,memory.free,name
# Format assumption (same documentation, `--help-query-compute-apps`): `-i N`
# limits the listing to card N; one line per process, `pid, used MiB, name`,
# and nothing at all for a card no process holds.
FIRST_APPS=pid,used_memory,process_name

first_tool() {
    local out rc line idx total used free rest k="" start
    command -v nvidia-smi >/dev/null 2>&1 || return 0
    out=$(nvidia-smi --query-gpu=$FIRST_QUERY --format=csv,noheader,nounits 2>/dev/null)
    rc=$?
    if [ $rc -ne 0 ]; then
        unread cards.nvidia-smi "nvidia-smi --query-gpu exited $rc; its cards are unread"
        return 0
    fi
    start=${#C_INDEX[@]}
    while IFS= read -r line; do
        [ -n "${line//[[:space:]]/}" ] || continue
        IFS=, read -r idx total used free rest <<<"$line"
        trim "$idx"; idx=$TRIM
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
        number "${total:-}" "card.nvidia.$idx.total" nvidia-smi; total=$NUM
        number "${used:-}" "card.nvidia.$idx.used" nvidia-smi; used=$NUM
        number "${free:-}" "card.nvidia.$idx.free" nvidia-smi; free=$NUM
        name "${rest:-}" "card.nvidia.$idx.name" nvidia-smi
        add_card nvidia "$idx" "$total" "$used" "$free" "$TEXT"
        k=$ADDED
    done <<<"$out"
    [ ${#C_INDEX[@]} -gt "$start" ] && SOURCES+=(nvidia-smi)
    for k in "${!C_INDEX[@]}"; do
        [ "$k" -ge "$start" ] && [ -z "${C_DROP[$k]}" ] && first_tool_holders "${C_INDEX[$k]}"
    done
    return 0
}

first_tool_holders() { # INDEX
    local out rc line pid mib pname key=card.nvidia.$1
    local -a pids=() mibs=() names=()
    out=$(nvidia-smi -i "$1" --query-compute-apps=$FIRST_APPS --format=csv,noheader,nounits 2>/dev/null)
    rc=$?
    if [ $rc -ne 0 ]; then
        unread "$key.holders" "nvidia-smi --query-compute-apps exited $rc; the processes on this card are unread"
        return 0
    fi
    while IFS= read -r line; do
        [ -n "${line//[[:space:]]/}" ] || continue
        # Format assumption: an idle card may be reported by this sentence.
        [ "$line" = "No running processes found" ] && continue
        IFS=, read -r pid mib pname <<<"$line"
        trim "$pid"; pid=$TRIM
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
        number "${mib:-}" "$key.holder.$pid.mib" nvidia-smi
        name "${pname:-}" "$key.holder.$pid.name" nvidia-smi
        pids+=("$pid") mibs+=("$NUM") names+=("$TEXT")
    done <<<"$out"
    local i
    for i in "${!pids[@]}"; do
        H_VENDOR+=(nvidia) H_INDEX+=("$1") H_PID+=("${pids[$i]}")
        H_MIB+=("${mibs[$i]}") H_NAME+=("${names[$i]}")
    done
    return 0
}

# --- the second vendor's tool ---------------------------------------------
# Format assumption (from the tool's documentation and its source, not tried
# on a machine here): `--showproductname --showmeminfo vram --json` prints one
# JSON object with a member per card named `cardN`, each an object of strings;
# the card's name is under `Card series` (else `Card model`), its memory in
# bytes under `VRAM Total Memory (B)` and `VRAM Total Used Memory (B)`. Key
# case differs between versions, so keys are matched without case. It names
# no card for a process, so the processes on its cards are named unread.
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

second_tool() {
    local out rc parsed tag idx total used cname free start
    command -v rocm-smi >/dev/null 2>&1 || return 0
    out=$(rocm-smi --showproductname --showmeminfo vram --json 2>/dev/null)
    rc=$?
    if [ $rc -ne 0 ]; then
        unread cards.rocm-smi "rocm-smi --json exited $rc; its cards are unread"
        return 0
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        unread cards.rocm-smi "python3 is not on PATH to read the JSON rocm-smi prints; its cards are unread"
        return 0
    fi
    parsed=$(printf '%s' "$out" | python3 -c "$SECOND_READER" 2>/dev/null)
    rc=$?
    if [ $rc -ne 0 ]; then
        unread cards.rocm-smi "reading the JSON rocm-smi printed failed (exit $rc); its cards are unread"
        return 0
    fi
    start=${#C_INDEX[@]}
    while IFS=$'\x1f' read -r tag idx total used cname; do
        case $tag in
            card) ;;
            error) unread cards.rocm-smi "rocm-smi: $idx"; continue ;;
            *) continue ;;
        esac
        case $idx in ''|*[!0-9]*) continue ;; esac
        [ ${#idx} -le 9 ] || continue
        idx=$((10#$idx))
        number "$total" "card.amd.$idx.total" rocm-smi bytes; total=$NUM
        number "$used" "card.amd.$idx.used" rocm-smi bytes; used=$NUM
        free=
        if [ -n "$total" ] && [ -n "$used" ] && [ "$used" -le "$total" ]; then
            free=$((total - used))
        elif [ -n "$total" ] && [ -n "$used" ]; then
            unread "card.amd.$idx.free" "rocm-smi printed more memory used than the card's total"
        else
            unread "card.amd.$idx.free" "free memory is the total less the used, and one of them is unread"
        fi
        name "$cname" "card.amd.$idx.name" rocm-smi
        add_card amd "$idx" "$total" "$used" "$free" "$TEXT"
        unread "card.amd.$idx.holders" "rocm-smi does not say which card a process holds"
    done <<<"$parsed"
    [ ${#C_INDEX[@]} -gt "$start" ] && SOURCES+=(rocm-smi)
    return 0
}

# --- sysfs ------------------------------------------------------------------
# Format assumption (from the kernel's documentation, not tried on a machine
# here): each card is /sys/class/drm/cardN (connectors are cardN-NAME), its
# PCI ids in device/vendor and device/device as `0xHHHH`. Some drivers publish
# device/product_name and the memory in bytes as device/mem_info_vram_total
# and device/mem_info_vram_used; others publish neither, and then the card is
# named by its PCI ids and its memory is named unread. No process is listed.
pci_vendor() {
    case $1 in
        0x10de) VENDOR=nvidia ;;
        0x1002) VENDOR=amd ;;
        0x8086) VENDOR=intel ;;
        *) VENDOR=pci-$1 ;;
    esac
}

read_file() { # PATH -> FILE (first line, trimmed), status 1 when unreadable
    FILE=
    [ -r "$1" ] || return 1
    local line=
    IFS= read -r line <"$1" || [ -n "$line" ] || return 1
    trim "$line"; FILE=$TRIM
    return 0
}

sysfs() {
    local dir n dev vid did pname total used free key start
    start=${#C_INDEX[@]}
    for dir in "$ROOT"/sys/class/drm/card*; do
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
        total= used= free=
        if read_file "$dev/mem_info_vram_total"; then
            number "$FILE" "$key.total" sysfs bytes; total=$NUM
        else
            unread "$key.total" "sysfs publishes no memory size for this card; its driver does not give one there"
        fi
        if read_file "$dev/mem_info_vram_used"; then
            number "$FILE" "$key.used" sysfs bytes; used=$NUM
        else
            unread "$key.used" "sysfs publishes no used memory for this card; its driver does not give one there"
        fi
        if [ -n "$total" ] && [ -n "$used" ] && [ "$used" -le "$total" ]; then
            free=$((total - used))
        else
            unread "$key.free" "free memory is the total less the used, and one of them is unread"
        fi
        add_card "$VENDOR" "$n" "$total" "$used" "$free" "$pname"
        unread "$key.holders" "sysfs does not list the processes on a card"
    done
    [ ${#C_INDEX[@]} -gt "$start" ] && SOURCES+=(sysfs)
    return 0
}

# --- containers, as rig-units.sh lists them -------------------------------
# One whitespace-free, comma-free token, as rig-units.sh's `tok` makes it:
# every run of blanks, line breaks and commas becomes one `_`, and one `_` is
# taken off each end.
tok() {
    local s=$1
    s=${s//[$' \t\n,']/_}
    while [[ $s == *__* ]]; do s=${s//__/_}; done
    s=${s#_}; s=${s%_}
    TOK=$s
}

containers() {
    local listed id cname project restarts
    if ! command -v docker >/dev/null 2>&1; then
        unread containers "docker is not on PATH"
        return 0
    fi
    listed=$(docker ps --no-trunc --format '{{.ID}}|{{.Names}}|{{.Label "com.docker.compose.project"}}' 2>/dev/null) || {
        unread containers "docker ps failed; this user may not be allowed to reach the docker daemon"
        return 0
    }
    while IFS='|' read -r id cname project; do
        [ -n "$id" ] || continue
        tok "${project:-}"; project=$TOK
        tok "$cname"; cname=$TOK
        tok "$id"; id=$TOK
        restarts=$(docker inspect --format '{{.RestartCount}}' "$id" 2>/dev/null) || restarts=
        tok "$restarts"; restarts=$TOK
        case $restarts in ''|*[!0-9]*)
            restarts=unread
            unread "container.$id.restarts" "docker inspect gave no restart count"
            ;;
        esac
        printf 'container=%s,%s,%s,%s\n' "$cname" "$id" "${project:--}" "$restarts"
    done <<<"$listed"
    return 0
}

# --- the machine ------------------------------------------------------------
host_name() {
    HOST=
    local got=
    if read_file "$ROOT/proc/sys/kernel/hostname"; then
        got=$FILE
    elif [ -z "$ROOT" ] && command -v hostname >/dev/null 2>&1; then
        got=$(hostname 2>/dev/null) || got=
    fi
    case $got in
        '') unread host "the host name is unread (/proc/sys/kernel/hostname, hostname)" ;;
        *[!A-Za-z0-9._-]*) unread host "the host name holds characters a host name does not" ;;
        *)
            if [ ${#got} -gt 253 ]; then
                unread host "the host name is longer than a host name may be"
            else
                HOST=$got
            fi
            ;;
    esac
}

machine_id() {
    local f seed= from=
    MID= MID_FROM=
    for f in /etc/machine-id /var/lib/dbus/machine-id; do
        read_file "$ROOT$f" || continue
        if [ -n "$FILE" ]; then seed=$FILE; from=$f; break; fi
    done
    if [ -z "$seed" ] && [ -n "$HOST" ]; then
        seed="host:$HOST"; from=hostname
    fi
    if [ -z "$seed" ]; then
        unread machine_id "no machine-id file (/etc/machine-id, /var/lib/dbus/machine-id) and no host name to derive it from"
        return 0
    fi
    if ! command -v sha256sum >/dev/null 2>&1; then
        unread machine_id "sha256sum is not on PATH"
        return 0
    fi
    local sum
    sum=$(printf '%s' "$seed" | sha256sum 2>/dev/null) || sum=
    sum=${sum:0:16}
    case $sum in
        ????????????????) ;;
        *) sum=x ;;
    esac
    case $sum in
        *[!0-9a-f]*) unread machine_id "sha256sum gave no digest" ;;
        *) MID=$sum MID_FROM=$from ;;
    esac
}

host_name
machine_id
first_tool
second_tool
[ ${#C_INDEX[@]} -eq 0 ] && sysfs

printf 'machine_id=%s\n' "$MID"
printf 'machine_id_from=%s\n' "$MID_FROM"
printf 'host=%s\n' "$HOST"
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
