# shellcheck shell=bash
# tools/runs/_common.sh — the one emitter every campaign step under
# `tools/runs/campaigns/` sources. The door is `python -m mcgyvr.serving.run`
# (src/mcgyvr/serving/run.py): it runs the gates around a step and exports the
# run to it, and a step reaches the rig only through the door's `ssh` and
# `docker` shims (gate-scripts/bin), which land on --host: rig_snapshot and
# image_digest prove the door first (gatelib.under_door, read from /proc) and
# resolve the shim by path from RUN_BIN, never from $PATH. Written against
# `archive/docs/2026-09-02-srv1-kernel-arms-ARTIFACT-CONTRACT.md` (the
# authority) and the parser it cites, `tools/runs/rows.py` (once
# `tests/sweeprows.py`, moved beside the door on 2026-09-02 so the parser the
# door trusts and the parser the tests trust are one module). Section numbers
# below are that contract's; "gate N" is an entry of run.py's SEQUENCE — the
# script under src/mcgyvr/serving/gate-scripts/ that owns the rule.
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
#                                (`rows.py:ARM_PREFIX`).
#   rig_snapshot                 §2.2/§2.3 — reads the live rig, one `k=v` per
#                                line, over `ssh "$RUN_HOST"`: gate 2's own
#                                reader (src/mcgyvr/serving/gate-scripts/
#                                rig-snapshot.sh) is shipped on stdin, so the
#                                step and the door read one machine one way.
#                                Never the machine this step runs on.
#   rig_stamp                    §2.2 — `### RIG` carrying all six RIG_FIELDS
#                                (`rows.py:RIG_FIELDS`) plus the card and CPU
#                                identity. Emit once before the first row and
#                                re-stamp per arm (`test_a_row_without_...:9-11`).
#   start_stamp / end_stamp      §2.3 — `### START` (with
#                                `pl1_source=constraint_0_power_limit_uw`) and
#                                `### END`, both carrying `run_id=$RUN_ID`: gate
#                                8 holds a run's START, ROUND and END to the id
#                                and round the door exported, so a file whose
#                                stamps name another run — or none — is not
#                                green. start_stamp also records the reading
#                                that rig_assert_unchanged compares against.
#   rig_assert_unchanged         §2.3 and guideline 7's "start equals end" — a
#                                fresh read, compared field by field with the
#                                one start_stamp took. Loud on any difference.
#   rig_assert_declared HOST [SNAPSHOT]
#                                gate 2 — the rig compared with its DECLARATION
#                                (`tools/runs/hosts.json[HOST].rig`, ten keys,
#                                read live on 2026-09-02), not only with itself.
#                                start==end never caught a rig that moved
#                                BEFORE a run: RAM swapped between srv1 and
#                                srv2 twice in six days and srv1's max clock
#                                went 4800 -> 4600, every artifact in between
#                                internally consistent. Loud, naming the key
#                                and both values.
#   round_stamp                  gate 1's receipt — `### ROUND id=
#                                product_sha256=` from RUN_ROUND and
#                                RUN_PRODUCT_SHA256, which gate 1 exports after
#                                `tools/bench/product.require_pinned()` passed.
#                                Fails when either is unset: a round nobody
#                                checked is not stamped from a guess.
#   image_digest TAG             gate 3 — ONE `docker image inspect`, and the
#                                tag becomes a digest (RepoDigests for a
#                                registry image, Id for a local build). A tag
#                                is a pointer: the same `img=` on two rows can
#                                name two images a week apart, which is the
#                                floating `:server-cuda` mistake the pin only
#                                half ended. Drivers refuse anything else.
#   workload_stamp MODULE        §2.1 — `### WORKLOAD digest=... driver=...`.
#                                MODULE is `tools/runs/workload.py`, the one
#                                file every driver imports its prompts from.
#                                The digest is computed by
#                                `tools/runs/rows.py:workload_digest()` itself,
#                                through `uv run --no-sync python`; a second
#                                implementation would be a second thing to drift.
#   microbench_stamp             §2.1/§6.4 — `### WORKLOAD digest=none
#                                comparable_with=microbenchmark-only`, owed by
#                                BOTH microbenchmark files.
#   refused LABEL [k=v ...] -- REASON
#                                §3 and resolved conflict §6.3 — a REFUSED row
#                                carrying `checkpoint_quant`, `tries>=3` and a
#                                reason over 40 characters. Guideline 8: a
#                                refusal is a result. `checkpoint_quant` is
#                                either a value read off the checkpoint or one
#                                of exactly two sentinels — `none` (no
#                                checkpoint was involved) or `unread` (one was,
#                                and its quantisation was never read). A
#                                home-made third spelling is rejected.
#   retry3 CMD [ARG ...]         guideline 8 — three attempts before a refusal is
#                                believed; sets RUN_TRIES to the attempt count
#                                for `refused` to record.
#
# Sourcing this file executes nothing and sets nothing. Every function is safe
# under `set -euo pipefail`.
#
# Environment read (never required, never fabricated from):
#   RUN_HOST          host column, and the rig rig_snapshot reads over ssh;
#                     exported by the door (gate 5). Defaults to `hostname`
#                     for the column only — a snapshot refuses without it.
#   RUN_REPO          repo root; default `git rev-parse --show-toplevel`.
#   RUN_RETRY_SLEEP   seconds between retry3 attempts; default 5.
#   RUN_ID            minted by the door (gate 5, 05-envelope.py); start_stamp
#                     writes it as `run_id=` and refuses without it.
#   RUN_ROUND / RUN_PRODUCT_SHA256
#                     exported by the door (gate 1, 01-round.py); round_stamp
#                     writes them.
#
# There is no seam. A test that needs a rig or a daemon answered puts an `ssh`
# or `docker` of its own first on PATH — the shim, having admitted the host,
# execs the next binary of that name — and runs under the door or a stand-in
# whose path ends in mcgyvr/serving/run.py, because nothing here reaches a
# rig without proving the door; nothing here reads a variable that names a
# substitute, because a variable that replaces a reading is a variable that
# skips one.

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

# The parser's own field test, `_KV` in tools/runs/rows.py.
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

# The run root, where the parser and the declarations live: RUN_REPO when a
# caller named one, else RUN_ROOT (the door's export — the tree a run is
# filed under and measured against, which need not be the checkout this
# shell is in), else the enclosing git checkout.
_repo_root() {
    local root
    if [ -n "${RUN_REPO:-}" ]; then
        root=$RUN_REPO
    elif [ -n "${RUN_ROOT:-}" ]; then
        root=$RUN_ROOT
    else
        root=$(git rev-parse --show-toplevel 2>/dev/null) || root=
    fi
    # The parser is what makes a tree this repo: `tools/runs/rows.py` at its
    # home beside the door, or the `tests/sweeprows.py` shim that re-exports it.
    if [ -z "$root" ] || { [ ! -f "$root/tools/runs/rows.py" ] && [ ! -f "$root/tests/sweeprows.py" ]; }; then
        _fail "cannot locate the repo (no tools/runs/rows.py under '${root:-?}'). Set RUN_REPO."
        return 1
    fi
    printf '%s' "$root"
}

# _py ARGS... — the repo's interpreter, run from the repo root so `tools.runs`
# resolves as a namespace package. `--no-sync`, always: a plain `uv run` tries
# to build the project and fails inside a throw-away checkout, which is exactly
# where the door's tests run it.
_py() {
    local root
    root=$(_repo_root) || return 1
    (cd "$root" && uv run --no-sync --quiet python "$@")
}

# _door_proof — 0 iff an ancestor of this shell is the door, read from /proc by
# gatelib.under_door. Non-zero for ANY reason (no python3 on PATH, no mcgyvr
# on it, /proc unreadable) is a refusal: the door is proved or it is not, and
# "could not check" is not. What the proof said comes back on stdout so a
# refusal can quote it.
_door_proof() {
    python3 -c 'from mcgyvr.serving.gatelib import under_door; raise SystemExit(0 if under_door() else 2)' 2>&1 >/dev/null
}

# _door_shim NAME — the path of the door's ssh or docker shim, the door proved
# first. By path from RUN_BIN (the door's export of its own shim directory;
# RUN_ROOT is the run root and need not hold any code) and never from $PATH: a
# PATH reordered mid-step would find the real binary. The shim refuses by
# itself outside the door, so RUN_BIN being the environment's word is fine.
# Returns 2 on refusal.
_door_shim() {
    local said shim
    said=$(_door_proof) || {
        _fail "$1 refused: this process was not started by the door — no ancestor is mcgyvr.serving.run${said:+; the proof said: $(printf '%s' "$said" | tail -n 1)} — and RUN_* set by hand does not stand in for one. Start the run as: python -m mcgyvr.serving.run --host <srv1|srv2> --campaign <campaign> --step <step> --model <blob as the rig sees it>"
        return 2
    }
    if [ -z "${RUN_BIN:-}" ]; then
        _fail "$1 refused: RUN_BIN is unset; the door exports its shim directory there, and the $1 this file runs is the door's shim under it (gate-scripts/bin/$1), never the one on PATH"
        return 2
    fi
    shim=$RUN_BIN/$1
    if [ ! -x "$shim" ]; then
        _fail "$1 refused: $shim is missing or not executable; the door's shim is the only $1 this file runs"
        return 2
    fi
    printf '%s\n' "$shim"
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
        _fail "stamp: '$name' is a k=v field where the stamp's name belongs — rows._stamp_name raises on this (§6.6)"
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
            _fail "stamp $name: '$arg' is not key=value — rows._stamp_fields raises on a loose token (§6.7)"
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
            _fail "arm_label: '$arm' does not match ARM_PREFIX [ABL][0-9] (tools/runs/rows.py), so Row.cell would not strip it and the arms would not align (§6.1)"
            return 1
            ;;
    esac
    if [ -z "$cell" ] || _has_space "$cell"; then
        _fail "arm_label: cell '$cell' is empty or holds whitespace; the label's first word is the tag (rows.Row.tag)"
        return 1
    fi
    printf '%s-%s' "$arm" "$cell"
}

# --------------------------------------------------------------------------
# §2.2/§2.3  the live rig
# --------------------------------------------------------------------------

# Gate 2's reader, beside the door's shims (RUN_BIN is `gate-scripts/bin`, and
# the reader is `gate-scripts/rig-snapshot.sh`): the CODE's copy, the same
# file gate 2 shipped to the rig, and never one found under the run root —
# a run root that is another tree would read the machine with another
# reader, and gate 7 could not diff the two readings. One reader for the
# door and the step: the `_rig_*` functions that once lived here were its
# source, and were a second copy the moment it existed.
_rig_reader() {
    if [ -z "${RUN_BIN:-}" ]; then
        _fail "rig_snapshot: RUN_BIN is unset; the reader is the door's own (gate-scripts/rig-snapshot.sh, beside the shims RUN_BIN names), and a step reads the machine with it or not at all"
        return 1
    fi
    printf '%s' "${RUN_BIN%/}/../rig-snapshot.sh"
}

# One reading of the machine, `k=v` per line, taken ON THE RIG over
# `ssh "$RUN_HOST"`. The step runs on the operator's machine and the container
# on the rig, so a local /sys or nvidia-smi describes the wrong box; the reader
# goes over on stdin to `bash -s` and is never installed there, so gate 7 has
# nothing extra to find. Every value is one whitespace-free token, so each line
# is legal in a marker as-is (§1.6). A rig that cannot be read is unread —
# nothing below fills a line in.
rig_snapshot() {
    local root out line ssh_bin
    if [ -z "${RUN_HOST:-}" ]; then
        _fail "rig_snapshot: RUN_HOST is unset. The rig is read over ssh to the host the door was given (gate 5 exports it); nothing here reads the machine a step happens to run on"
        return 1
    fi
    ssh_bin=$(_door_shim ssh) || return 2
    root=$(_rig_reader) || return 1
    if [ ! -f "$root" ]; then
        _fail "rig_snapshot: $root is missing; that file is the one reader of a rig (gate 2's), and a step reads the machine with it or not at all"
        return 1
    fi
    out=$("$ssh_bin" "$RUN_HOST" bash -s <"$root") || {
        _fail "rig_snapshot: reading $RUN_HOST over ssh failed; the rig is unread and no stamp is written from a guess"
        return 1
    }
    [ -n "$out" ] || { _fail "rig_snapshot: $RUN_HOST answered nothing; the rig is unread"; return 1; }
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        if ! _kv_ok "$line" || _has_space "$line"; then
            _fail "rig_snapshot: $RUN_HOST printed '$line', which is not one whitespace-free key=value; a snapshot line must be legal in a stamp as-is (§1.6)"
            return 1
        fi
    done <<EOF
$out
EOF
    printf '%s\n' "$out"
}

_snap_get() {
    printf '%s\n' "$1" | sed -n "s/^$2=//p" | head -n 1
}

# §2.2. All six RIG_FIELDS (rows.RIG_FIELDS) plus the card and CPU this run
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

# §2.3. Also records the reading rig_assert_unchanged will compare against, and
# names the run: `run_id=` is what ties the file to the door invocation that
# produced it, and the parser (rows.read) holds a file that carries one to the
# stamp rules eagerly and demands its `### ROUND`. There is no default: a step
# started bare has no run id, and a START that invented one would claim the
# gates ran when they did not.
start_stamp() {
    local snap
    if [ -z "${RUN_ID:-}" ]; then
        _fail "start_stamp: RUN_ID is unset. A ### START names the run that produced it, and only the door mints one (gate 5, 05-envelope.py) — start this step through it: python -m mcgyvr.serving.run"
        return 1
    fi
    snap=$(rig_snapshot) || return 1
    RUN_RIG_START=$snap
    stamp START \
        "uptime_since=$(_snap_get "$snap" uptime_since)" \
        "pl1_uw=$(_snap_get "$snap" pl1_uw)" \
        "pl2_uw=$(_snap_get "$snap" pl2_uw)" \
        "pl1_source=constraint_0_power_limit_uw" \
        "cpu_max_mhz=$(_snap_get "$snap" cpu_max_mhz)" \
        "ram_mt_s=$(_snap_get "$snap" ram_mt_s)" \
        "run_id=$RUN_ID"
}

# Gate 1's receipt in the file. The door's gate 1 (01-round.py) runs
# `tools/bench/product.require_pinned()`
# before anything else and exports what it returned; a step writes it straight
# after START so a reader knows which product revision the rows were measured
# under (ADR-0018: every arm in a round runs against one revision). Both values
# come from the door or the stamp is refused — a round is checked, never guessed.
round_stamp() {
    [ "$#" -eq 0 ] || { _fail "round_stamp: takes no arguments; it writes RUN_ROUND and RUN_PRODUCT_SHA256"; return 1; }
    if [ -z "${RUN_ROUND:-}" ] || [ -z "${RUN_PRODUCT_SHA256:-}" ]; then
        _fail "round_stamp: RUN_ROUND='${RUN_ROUND:-}' RUN_PRODUCT_SHA256='${RUN_PRODUCT_SHA256:-}'. Gate 1 of the door (01-round.py) exports both after require_pinned() passes; a ### ROUND is never written from anything else"
        return 1
    fi
    stamp ROUND "id=$RUN_ROUND" "product_sha256=$RUN_PRODUCT_SHA256"
}

# §2.3. A fresh read, emitted whatever it says — if the rig moved, the file must
# say so. Call rig_assert_unchanged after this, not instead of it. Names the
# run it closes, as START names the run it opens: gate 8 reads `run_id=` off
# both and refuses a file whose END is another run's, or nobody's.
end_stamp() {
    local snap
    if [ -z "${RUN_ID:-}" ]; then
        _fail "end_stamp: RUN_ID is unset. A ### END names the run it closes, and only the door mints one (gate 5, 05-envelope.py) — start this step through it: python -m mcgyvr.serving.run"
        return 1
    fi
    snap=$(rig_snapshot) || return 1
    RUN_RIG_END=$snap
    stamp END \
        "uptime_since=$(_snap_get "$snap" uptime_since)" \
        "pl1_uw=$(_snap_get "$snap" pl1_uw)" \
        "pl2_uw=$(_snap_get "$snap" pl2_uw)" \
        "cpu_max_mhz=$(_snap_get "$snap" cpu_max_mhz)" \
        "ram_mt_s=$(_snap_get "$snap" ram_mt_s)" \
        "run_id=$RUN_ID"
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
    for key in uptime_since cpu_max_mhz cpu_model ram_mt_s pl1_uw pl2_uw driver gpu_reserve_mib gpu_name gpu_vram_mib gpu_cc docker; do
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
# gate 2  the rig against its declaration
# --------------------------------------------------------------------------

# The eleven keys `tools/runs/hosts.json[HOST].rig` declares. `uptime_since`
# is deliberately absent — it changes per boot and is compared start==end only.
# `docker` joined on 2026-09-03 (the reader's docker_version).
RIG_DECLARED_KEYS="cpu_max_mhz cpu_model ram_mt_s pl1_uw pl2_uw gpu_name gpu_vram_mib gpu_cc driver gpu_reserve_mib docker"

# _hosts_declared — every top-level host in hosts.json that carries a `rig`
# object, one per line. That set is the door's `--host` vocabulary.
_hosts_declared() {
    _py - <<'PY'
import json

doc = json.load(open("tools/runs/hosts.json", encoding="utf-8"))
for name, entry in doc.items():
    if isinstance(entry, dict) and isinstance(entry.get("rig"), dict):
        print(name)
PY
}

# _host_rig HOST — the declared rig as `k=v` lines, or a refusal naming HOST.
# The values are printed as the strings the file carries; a declaration is
# compared literally, never coerced.
_host_rig() {
    local host=$1
    _py - "$host" "$RIG_DECLARED_KEYS" <<'PY'
import json
import sys

host, keys = sys.argv[1], sys.argv[2].split()
doc = json.load(open("tools/runs/hosts.json", encoding="utf-8"))
entry = doc.get(host)
rig = entry.get("rig") if isinstance(entry, dict) else None
if not isinstance(rig, dict):
    sys.exit(
        f"host '{host}' has no rig block in tools/runs/hosts.json; the door "
        "compares a live rig with its declaration and cannot compare it with "
        "nothing"
    )
missing = [k for k in keys if not str(rig.get(k, "")).strip()]
if missing:
    sys.exit(f"tools/runs/hosts.json[{host!r}].rig declares no {missing}")
for key in keys:
    print(f"{key}={rig[key]}")
PY
}

# rig_assert_declared HOST [SNAPSHOT] — gate 2. SNAPSHOT is a rig_snapshot
# reading already taken (the door keeps its pre-step reading, RUN_PRE_RIG, for
# gate 7); without
# one the rig is read here. Every difference is named with both values, so the
# refusal says what moved and by how much rather than that something did.
rig_assert_declared() {
    local host snap declared key want got bad
    [ "$#" -ge 1 ] && [ "$#" -le 2 ] || { _fail "rig_assert_declared: usage: rig_assert_declared HOST [SNAPSHOT]"; return 1; }
    host=$1
    snap=${2:-}
    if [ -z "$snap" ]; then
        snap=$(rig_snapshot) || return 1
    fi
    declared=$(_host_rig "$host") || return 1
    bad=
    for key in $RIG_DECLARED_KEYS; do
        want=$(_snap_get "$declared" "$key")
        got=$(_snap_get "$snap" "$key")
        [ "$want" = "$got" ] || bad="${bad:+$bad; }$key: declared $want, live ${got:-<unread>}"
    done
    if [ -n "$bad" ]; then
        _fail "THIS MACHINE IS NOT THE DECLARED $host — $bad. tools/runs/hosts.json[$host].rig is what the rig was read as on its read_on date; either the wrong --host was named, or the rig moved before this run (RAM swapped between rigs twice in six days; a hard lock wipes the BIOS profile). Fix the machine or re-declare it deliberately; nothing is measured on a rig that is not the one it claims to be (gate 2)"
        return 1
    fi
}

# --------------------------------------------------------------------------
# gate 3  a tag becomes a digest, once
# --------------------------------------------------------------------------

# image_digest TAG — exactly one `docker image inspect`, and the digest the
# daemon holds for TAG on stdout: `repo@sha256:<64hex>` (RepoDigests, a
# registry image) or `sha256:<64hex>` (Id, a local build with no registry to
# appeal to). Anything else is nothing on stdout, TAG on stderr, non-zero — a
# driver refuses a non-digest, so a failed resolution cannot leak through as a
# tag. Plain JSON rather than `--format`, so one call answers both cases.
image_digest() {
    local tag json digest docker_bin
    [ "$#" -eq 1 ] || { _fail "image_digest: usage: image_digest TAG"; return 1; }
    tag=$1
    if [ -z "$tag" ] || _has_space "$tag"; then
        _fail "image_digest: tag '$tag' is empty or holds whitespace"
        return 1
    fi
    docker_bin=$(_door_shim docker) || return 2
    json=$("$docker_bin" image inspect "$tag") || {
        _fail "image_digest: 'docker image inspect $tag' failed; '$tag' is not an image this daemon holds, so it resolves to no digest and no container is started from it (gate 3)"
        return 1
    }
    # The two FIELDS, read from the parsed document — not the first
    # digest-shaped string in it. Config.Labels sits after RepoDigests and
    # 1-build-ladder.sh labels every rung `org.mcgyvr.build.toolkit=<base
    # image>`; with the toolkit pinned by digest and RepoDigests empty (every
    # rung reaches srv1 by docker save|load), a grep over the document handed
    # the driver nvidia/cuda's digest and the rung's REFUSED row was a lie.
    digest=$(_py -c '
import json
import re
import sys

DIGEST = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
ID = re.compile(r"^sha256:[0-9a-f]{64}$")
try:
    doc = json.loads(sys.argv[1])
except ValueError:
    sys.exit(1)
images = doc if isinstance(doc, list) else [doc]
if len(images) != 1 or not isinstance(images[0], dict):
    sys.exit(1)
image = images[0]
repo_digests = [
    d for d in (image.get("RepoDigests") or []) if isinstance(d, str) and DIGEST.match(d)
]
if repo_digests:
    print(repo_digests[0])
elif isinstance(image.get("Id"), str) and ID.match(image["Id"]):
    print(image["Id"])
else:
    sys.exit(1)
' "$json") || digest=
    if [ -z "$digest" ]; then
        _fail "image_digest: '$tag' inspects with neither a RepoDigests entry nor an Id; no digest can be named for it (gate 3)"
        return 1
    fi
    printf '%s\n' "$digest"
}

# --------------------------------------------------------------------------
# a step is started by the door, or not at all
# --------------------------------------------------------------------------

# door_required — the four things only the door exports: RUN_ID
# (gate 5), RUN_OUT_DIR (the envelope, gate 5), RUN_ROUND and
# RUN_PRODUCT_SHA256 (gate 1). A step once guarded itself on RUN_ID alone and
# then resolved its envelope as `${RUN_OUT_DIR:-<the committed 2026-09-02
# dir>}`; RUN_ID is any non-empty string, so a stale one in an operator's
# shell took a bare step straight to recorded evidence, where it truncated its
# file before round_stamp could refuse — twice in one session. No RUN_OUT_DIR
# is no envelope, and no envelope is nothing to write. Called by every step
# after the RUN_ID guard, before it parses an argument. Then the door itself
# is proved (_door_proof): all four variables can be typed into a shell, and
# a full hand-set RUN_* environment once took a step to a real `ssh srv1`
# with no shim on PATH to stop it.
door_required() {
    local v said missing=
    for v in RUN_ID RUN_OUT_DIR RUN_ROUND RUN_PRODUCT_SHA256; do
        [ -n "${!v:-}" ] || missing="${missing:+$missing }$v"
    done
    # `_fail || exit 2`: the caller runs under `set -e`, where _fail's own
    # return 1 would end the step with THAT status before the exit 2 it owes.
    if [ -n "$missing" ]; then
        _fail "$missing unset — only the door exports them (gates 1 and 5), so this step was not started by it; it has no envelope and writes nothing. Start me through the door: python -m mcgyvr.serving.run --host <srv1|srv2> --campaign <campaign> --step <this file> --model <blob as the rig sees it>" || exit 2
    fi
    if [ ! -d "$RUN_OUT_DIR" ]; then
        _fail "RUN_OUT_DIR='$RUN_OUT_DIR' is not a directory; the envelope the door makes (gate 5, 05-envelope.py) is the only place a step writes. Start me through the door: python -m mcgyvr.serving.run" || exit 2
    fi
    said=$(_door_proof) || {
        _fail "this step was not started by the door — no ancestor is mcgyvr.serving.run${said:+; the proof said: $(printf '%s' "$said" | tail -n 1)} — and RUN_* set by hand does not stand in for one. Start me through the door: python -m mcgyvr.serving.run --host <srv1|srv2> --campaign <campaign> --step <this file> --model <blob as the rig sees it>" || exit 2
    }
}

# --------------------------------------------------------------------------
# §2.1  the workload stamp
# --------------------------------------------------------------------------

# The digest is rows.workload_digest()'s, not a copy of it: it execs the
# module's PROMPT_DECILES..end block over 200 generated prompts, so a
# `ruff format` pass does not move it and a changed prompt does. The argument
# is the workload module (`tools/runs/workload.py`); a driver that still
# carried its own block would digest the same way, and none does.
workload_stamp() {
    local driver root digest
    [ "$#" -eq 1 ] || { _fail "workload_stamp: usage: workload_stamp <workload.py>"; return 1; }
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
    digest=$(cd "$root" && uv run --no-sync --quiet python -c '
import sys
from pathlib import Path

from tools.runs.rows import WORKLOAD_DIGEST, workload_digest

got = workload_digest(Path(sys.argv[1]))
if got != WORKLOAD_DIGEST:
    sys.exit(
        f"{sys.argv[1]} generates workload {got}, not {WORKLOAD_DIGEST}. "
        "Every comparison in this campaign is void until it does."
    )
print(got)
' "$driver") || {
        _fail "workload_stamp: could not compute the digest of '$driver' with tools/runs/rows.py:workload_digest()"
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

# backend_verdict DECLARED MEASURED -- the backend an image declares against
# the one llama-bench reports having run. On 2026-09-02 A3 (GGML_VULKAN=ON)
# filed four BENCH rows that were the six-core i5-9600K: libggml-vulkan.so
# found no device, ggml fell back to the CPU without a word, and every entry
# of llama-bench's own report said `backend: CPU`. Nothing read it. DECLARED
# is the image's `org.mcgyvr.build.backend` label (`cuda`, `vulkan`); MEASURED
# is the report's `backends` field (`CUDA`, `Vulkan`, `CPU`, or a list such as
# `CUDA,BLAS`). An empty DECLARED is an image that says nothing (the upstream
# server-cuda image, arm A1) and is not judged. Anything else must name the
# declared backend, case-insensitively, or the number is refused, not filed.
backend_verdict() {
    local declared measured
    [ "$#" -eq 2 ] || { _fail "backend_verdict: usage: backend_verdict DECLARED MEASURED"; return 1; }
    declared=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    measured=$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')
    [ -n "$declared" ] || return 0
    case "$measured" in
        *"$declared"*) return 0 ;;
    esac
    _fail "the image declares backend=$1 but llama-bench reports backend=$2: the declared backend never ran, and a number measured on whatever ran instead is not this arm's number (A3 on 2026-09-02 was the CPU under a vulkan tag)"
    return 1
}

# refused LABEL [k=v ...] -- REASON WORDS...
# Resolved conflict §6.3: a dropped arm and a refused arm leave an identical
# hole, and only one of them is a result. The price of the missing CONFIG is
# `checkpoint_quant`, `tries>=3` and a reason of more than 40 characters
# (test_two_backends_...:56-65, test_an_ncmoe_floor_...:83-86).
refused() {
    local label arg fields reason in_reason tries quant
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
    quant=${fields##* checkpoint_quant=}
    quant=${quant%% *}
    # THE SENTINEL VOCABULARY, and there are exactly two words in it.
    # `refused()` demands checkpoint_quant on every refusal, but a build that
    # never compiled and an image with no llama-bench in it have no checkpoint
    # to read. Four spellings of that hole were in circulation across the eight
    # scripts (`none`, `unread`, `unread-no-quantization_config`,
    # `unread_the_loader_never_printed_it`), which is four ways for a reader to
    # miss that they are the same fact. One vocabulary, documented in
    # ARTIFACT-CONTRACT.md §6.3:
    #
    #   none     no checkpoint was involved at all. Nothing was loaded, so there
    #            is nothing to read: a build failure, a missing binary, an image
    #            with no cuobjdump record.
    #   unread   a checkpoint WAS involved and its declared quantisation was
    #            never read — the loader died before it printed, or the repo
    #            carries no quantization_config. WHICH of those goes in the
    #            reason, where a reader will look for it; it is not a third word.
    #
    # Anything else must be a value actually read off the checkpoint. A near-miss
    # spelling is refused here rather than filed as if it were one.
    case $quant in
        none | unread) : ;;
        '')
            _fail "refused: checkpoint_quant= is empty. Use 'none' (no checkpoint was involved) or 'unread' (one was, and its quantisation was never read)"
            return 1
            ;;
        unread* | unknown* | unrecorded* | 'n/a' | 'N/A' | - | NONE | None)
            _fail "refused: checkpoint_quant='$quant' is a home-made sentinel. The vocabulary is exactly two words: 'none' (no checkpoint was involved) and 'unread' (one was, and its quantisation was never read). Which kind of unread it was belongs in the reason"
            return 1
            ;;
        *) : ;;
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
