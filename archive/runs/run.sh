#!/usr/bin/env bash
# tools/runs/run.sh — the one door to the rigs.
#
# THE CONTRACT, IN TEN LINES.
#   1. This is the only executable that starts a container on, or opens an ssh
#      to, srv1/srv2. Every driver and every step refuses without the RUN_ID
#      this file mints, so a bare invocation of either files nothing.
#   2. `run.sh <campaign> <step> --host srv1|srv2 [-- STEP ARGS...]`. A
#      campaign is a directory under tools/runs/campaigns/; a step is a
#      `<n>-<name>.sh` in it, addressed by `<n>` or by `<name>`.
#   3. Eight gates, in order. Each refuses loudly, names the rule, exits
#      non-zero — and gates 1-5 refuse having written nothing under records/
#      and having reached no rig.
#   4. gate 1  the tree is on the open product round (require_pinned)  exit 2
#   5. gate 2  the live rig equals its declaration in hosts.json       exit 2
#      gate 2b a serving campaign's harness markers are all present    exit 2
#   6. gate 3  the daemon a tag is resolved through answers now, and
#      resolution is ONCE (image_digest); gate 4 the workload module
#      digests to the pin                                              exit 2
#   7. gate 5  the envelope records/evidence/<RUN_DATE>-<campaign>/ is
#      made, the declared artifacts are write-once (or superseded by the
#      one step that wrote them, under a new id), a file this step
#      appends to exists and was door-produced, RUN_ID is minted       exit 2
#   8. gate 6  the step runs, with RUN_ID RUN_OUT_DIR RUN_HOST RUN_ROUND
#      RUN_PRODUCT_SHA256 RUN_STEP RUN_REPO exported; its stdout/stderr
#      pass through
#   9. gate 7  after the step, whatever its exit — a signal included: no
#      container named for the run is left (named, not killed), and the
#      rig reads as it did before                                      exit 1
#  10. gate 8  every declared artifact exists and parses (tools.runs.rows.read
#      for a TSV, json for a .json), an appended file kept its prefix and
#      grew; a step that exited non-zero propagates its status after 7
#      and 8; an interrupted run exits 130 after 7 and 8               exit 1
#
# WHY ONE DOOR. On 2026-09-02 four live entry points reached srv1 and srv2 —
# the eight srv1-*.sh over _common.sh, the three root drivers run bare,
# tools/bench/serving/launch.py and serving/sweep.py — and only the first
# stamped rig state, workload digest and build identity. The drivers printed
# byte-compatible rows with no stamps; only tools/breadth/measure.py checked
# the product round; the rig was compared with itself (start==end) and never
# with a declaration, which is how RAM swapped between the rigs twice in six
# days with every artifact internally consistent; and the parser ran only in
# CI, post-hoc, over one directory, so a run that wrote a file the parser
# rejects exited green on the rig and turned red a commit later. Each gate
# below is one of those holes, closed where the rig time is spent.
#
# A step declares what it writes on one comment line the door reads with grep
# and never executes:
#   # RUN_ARTIFACTS: a.tsv [b.tsv ...]     created by this step; write-once
#   # RUN_REWRITES:  b.tsv [...]           created by this step, which may run
#                                          again over it (a two-pass step): an
#                                          existing file is admitted only if its
#                                          ### START run_id= names THIS step,
#                                          and is moved to
#                                          <name>.superseded-<run_id>.<ext>
#                                          first — nothing recorded is lost;
#                                          another step's file, or one with no
#                                          run id, is refused
#   # RUN_APPENDS:   c.tsv [...]           appended to by this step (another
#                                          step created it): it must exist and
#                                          its ### START must carry a run_id a
#                                          step of this campaign minted; after
#                                          the step, the bytes that were there
#                                          must still be its prefix and must
#                                          have been added to
# Each directive appears at most once; a second line is refused, not dropped.
#
# Seams (BRIEF "Seams for tests"): a test may not touch a rig, so every read of
# the machine or the daemon is behind one variable, and nothing else is.
#   RUN_REPO              the checkout (default: this file's ../..)
#   RUN_DATE              YYYY-MM-DD in the envelope name (default: today, UTC)
#   RUN_PRODUCT_CHECK     a command replacing the require_pinned call; prints
#                         `round=<id> product_sha256=<hex>` or exits non-zero
#   RUN_RIG_SNAPSHOT_CMD  a command whose stdout replaces rig_snapshot's
#   RUN_DOCKER            invoked in place of docker (here, _common.sh, drivers)
#   RUN_SSH               invoked in place of ssh by steps that open one
# Optional: `--suffix S` appends `-S` to RUN_ID; S matches [A-Za-z0-9_.-]+ and
# may not make `<step>-S` spell another step of the campaign (a run id names
# exactly one step). A RUN_REWRITES re-run on the same day NEEDS one: two door
# invocations never share a run id.
#
# The door owns the envelope: a step's own `--out`, `--out-dir` or `--force`
# after `--` is refused before gate 1, because a file written anywhere but
# $RUN_OUT_DIR/<declared> is one no gate can see, and one written by force is
# evidence overwritten.

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# ARCHIVED 2026-09-05, round r3: this file moved to archive/runs/ when
# src/mcgyvr/serving/run.py became the one access point to the rigs.
# `_common.sh` did NOT move with it — the campaign steps source it as an
# emitter library and go on working — so the library is reached at the home it
# kept, and this file is no longer beside it. Kept runnable rather than
# deleted: the one-door tests drive it as the SPEC the Python door must meet.
# shellcheck source=../../tools/runs/_common.sh
# shellcheck disable=SC1091  # sourced at runtime
. "$HERE/_common.sh" 2>/dev/null || . "$HERE/../../tools/runs/_common.sh"

# The checkout is where this file lives unless a caller says otherwise; the
# cwd is not evidence of anything.
: "${RUN_REPO:=$(cd -- "$HERE/../.." && pwd)}"
export RUN_REPO

# --------------------------------------------------------------------------
# refusals
# --------------------------------------------------------------------------

# refuse STATUS MESSAGE... — one loud line on stderr, then out. `_fail` returns
# 1 and `set -e` would take the script down with THAT status, so the exit
# status a gate owes is passed explicitly and never inherited.
refuse() {
    local status=$1
    shift
    printf 'run.sh: %s\n' "$*" >&2
    exit "$status"
}

usage_campaigns() {
    local d found=0
    {
        printf 'usage: tools/runs/run.sh <campaign> <step> --host srv1|srv2 [--suffix S] [-- STEP ARGS...]\n'
        printf '\n'
        printf 'The one door to the rigs. A campaign is a directory under\n'
        printf 'tools/runs/campaigns/; a step is a <n>-<name>.sh in it, addressed by\n'
        printf 'number or by name. Campaigns in this checkout:\n'
        for d in "$ROOT"/tools/runs/campaigns/*/; do
            [ -d "$d" ] || continue
            found=1
            printf '  %s\n' "$(basename -- "$d")"
        done
        [ "$found" -eq 1 ] || printf '  (none under %s/tools/runs/campaigns/)\n' "$ROOT"
        printf '\n'
        printf 'Name a campaign alone to see its steps. --host is required: it is the\n'
        printf 'key of tools/runs/hosts.json whose declared rig the machine is held to.\n'
    } >&2
    exit 2
}

usage_steps() {
    local campaign=$1 f found=0
    {
        printf 'usage: tools/runs/run.sh %s <step> --host srv1|srv2 [-- STEP ARGS...]\n' "$campaign"
        printf '\n'
        printf 'Steps of %s (by number or by name):\n' "$campaign"
        for f in "$ROOT/tools/runs/campaigns/$campaign"/[0-9]*-*.sh; do
            [ -f "$f" ] || continue
            found=1
            printf '  %s\n' "$(basename -- "$f" .sh)"
        done
        [ "$found" -eq 1 ] || printf '  (no <n>-<name>.sh in it)\n'
    } >&2
    exit 2
}

# --------------------------------------------------------------------------
# argv
# --------------------------------------------------------------------------

ROOT=$(_repo_root) || exit 2

CAMPAIGN=
STEP=
HOST=
SUFFIX=
STEP_ARGS=()

parse_argv() {
    while [ "$#" -gt 0 ]; do
        case $1 in
            -h | --help) usage_campaigns ;;
            --host)
                [ "$#" -ge 2 ] || refuse 2 "--host needs a host name (srv1|srv2)"
                HOST=$2
                shift
                ;;
            --host=*) HOST=${1#--host=} ;;
            --suffix)
                [ "$#" -ge 2 ] || refuse 2 "--suffix needs a value matching [A-Za-z0-9_.-]+"
                SUFFIX=$2
                shift
                ;;
            --suffix=*) SUFFIX=${1#--suffix=} ;;
            --)
                shift
                STEP_ARGS=("$@")
                check_step_args
                break
                ;;
            -*) refuse 2 "unknown option '$1'. The door takes <campaign> <step> --host HOST [--suffix S]; a step's own arguments go after --" ;;
            *)
                if [ -z "$CAMPAIGN" ]; then
                    CAMPAIGN=$1
                elif [ -z "$STEP" ]; then
                    STEP=$1
                else
                    refuse 2 "unexpected argument '$1'; a step's own arguments go after --"
                fi
                ;;
        esac
        shift
    done
}

# check_step_args — the door owns the envelope. Six steps kept an output
# override from their bare-run days and three a --force; through the door,
# `-- --out <recorded file>` overwrote committed evidence under a green line
# and `-- --out-dir <anywhere>` filed a run where gates 5, 7 and 8 could not
# see it. Refused here, before gate 1: nothing checked, nothing made.
check_step_args() {
    local t
    for t in ${STEP_ARGS[@]+"${STEP_ARGS[@]}"}; do
        case $t in
            --out | --out=* | --out-dir | --out-dir=* | --force)
                refuse 2 "step argument '$t' is refused: the door owns the envelope (records/evidence/<RUN_DATE>-<campaign>/) and every declared artifact is written there, once. A re-run is --suffix S over a RUN_REWRITES declaration; nothing is written elsewhere, or by force"
                ;;
        esac
    done
}

# resolve_step CAMPAIGN STEP — the one `<n>-<name>.sh` STEP names, by its
# number or its name, into STEP_FILE and STEP_NAME. Nothing is executed. An
# address that fits two files (`1-2.sh` and `2-two.sh` both answer to `2`), or
# a campaign that numbers two steps alike, is refused naming them: a door that
# guesses which step was meant is not a door.
STEP_FILE=
STEP_NAME=
resolve_step() {
    local campaign=$1 want=$2 f base name num
    local -a hits=()
    local -A numbered=()
    for f in "$ROOT/tools/runs/campaigns/$campaign"/[0-9]*-*.sh; do
        [ -f "$f" ] || continue
        base=$(basename -- "$f" .sh)
        num=${base%%-*}
        name=${base#*-}
        [ -z "${numbered[$num]:-}" ] ||
            refuse 2 "campaign '$campaign' numbers two steps $num: ${numbered[$num]} and $base. A step is addressed by its number, so each number is one file; renumber one of them"
        numbered[$num]=$base
        if [ "$want" = "$num" ] || [ "$want" = "$name" ] || [ "$want" = "$base" ]; then
            hits+=("$base")
            STEP_FILE=$f
            STEP_NAME=$name
        fi
    done
    [ "${#hits[@]}" -ne 0 ] || return 1
    [ "${#hits[@]}" -eq 1 ] ||
        refuse 2 "step '$want' fits ${#hits[@]} files in campaign '$campaign' (${hits[*]}); the door does not guess which was meant — address it by its full stem (<n>-<name>)"
    return 0
}

# step_of_run_id RUN_ID — the step of THIS campaign that minted RUN_ID, or an
# empty line. A run id is <date>-<campaign>-<step>[-<suffix>] and both the step
# name and the suffix may carry dashes, so the LONGEST step name that fits is
# the one: `probe-again` is the step probe-again if that step exists, and the
# step probe under suffix `again` only if it does not. Always returns 0.
step_of_run_id() {
    local stem=${1#[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-} f base name best=
    for f in "$ROOT/tools/runs/campaigns/$CAMPAIGN"/[0-9]*-*.sh; do
        [ -f "$f" ] || continue
        base=$(basename -- "$f" .sh)
        name=${base#*-}
        case $stem in
            "$CAMPAIGN-$name" | "$CAMPAIGN-$name"-*)
                if [ "${#name}" -gt "${#best}" ]; then best=$name; fi
                ;;
        esac
    done
    printf '%s\n' "$best"
    return 0
}

check_argv() {
    local h declared
    [ -n "$CAMPAIGN" ] || usage_campaigns
    [ -d "$ROOT/tools/runs/campaigns/$CAMPAIGN" ] ||
        refuse 2 "no campaign '$CAMPAIGN' under tools/runs/campaigns/ (run with no arguments to list them)"
    [ -n "$STEP" ] || usage_steps "$CAMPAIGN"
    resolve_step "$CAMPAIGN" "$STEP" ||
        refuse 2 "no step '$STEP' in campaign '$CAMPAIGN' (run 'tools/runs/run.sh $CAMPAIGN' to list them by number and name)"
    [ -x "$STEP_FILE" ] || refuse 2 "step '$STEP_FILE' is not executable"
    [ -n "$HOST" ] || refuse 2 "missing --host srv1|srv2: the rig is held to tools/runs/hosts.json[HOST].rig (gate 2), and the door will not guess which machine it is on"
    declared=$(_hosts_declared) || refuse 2 "tools/runs/hosts.json could not be read for its declared hosts"
    # One host name per line, none with whitespace: the split is the intent.
    # shellcheck disable=SC2086
    for h in $declared; do
        [ "$h" = "$HOST" ] && return 0
    done
    refuse 2 "host '$HOST' has no rig block in tools/runs/hosts.json (declared: $(printf '%s' "$declared" | tr '\n' ' ')); a rig nobody declared cannot be compared with its declaration (gate 2)"
}

# --------------------------------------------------------------------------
# the gates
# --------------------------------------------------------------------------

# Gate 1 refuses a checkout that has moved off the open product round. Only
# tools/breadth/measure.py checked this before; the sweeps stamped nothing about
# it, so an arm measured three commits past the pin landed in the same table as
# one measured on it (ADR-0018: every arm in a round runs against one revision).
# The default loads tools/bench/product.py by path, the way measure.py does, so
# no cwd and no PYTHONPATH decides which product module answers.
gate_1_round() {
    local out
    if [ -n "${RUN_PRODUCT_CHECK:-}" ]; then
        out=$(bash -c "$RUN_PRODUCT_CHECK") || refuse 2 "gate 1: the product check refused (see above); the tree is not on the open round and nothing is measured on it"
    else
        out=$(_py - <<'PY'
import importlib.util
import sys
from pathlib import Path

slot = "bench_product"
module = sys.modules.get(slot)
if module is None:
    path = Path("tools/bench/product.py").resolve()
    spec = importlib.util.spec_from_file_location(slot, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[slot] = module
    spec.loader.exec_module(module)
try:
    round_id, digest = module.require_pinned()
except module.ProductError as error:
    sys.exit(f"gate 1: {error}")
print(f"round={round_id} product_sha256={digest}")
PY
        ) || refuse 2 "gate 1: tools/bench/product.require_pinned() refused (see above); the tree is not on the open round and nothing is measured on it"
    fi
    RUN_ROUND=$(printf '%s\n' "$out" | sed -n 's/^round=\([^[:space:]]\{1,\}\) product_sha256=\([0-9a-f]\{1,\}\)$/\1/p' | head -n 1)
    RUN_PRODUCT_SHA256=$(printf '%s\n' "$out" | sed -n 's/^round=\([^[:space:]]\{1,\}\) product_sha256=\([0-9a-f]\{1,\}\)$/\2/p' | head -n 1)
    if [ -z "$RUN_ROUND" ] || [ -z "$RUN_PRODUCT_SHA256" ]; then
        refuse 2 "gate 1: the product check printed '$out', not 'round=<id> product_sha256=<hex>'; a round it cannot name is not a round it checked"
    fi
    export RUN_ROUND RUN_PRODUCT_SHA256
}

# Gate 2 refuses a machine that is not the one --host names. start==end (the
# steps' own check) catches a rig that moves DURING a run and says nothing
# about one that moved before it; hosts.json[HOST].rig is the declaration, read
# live on its read_on date, and every one of its ten keys must match. The
# reading is kept for gate 7. Gate 2b: a campaign whose campaign.json declares
# {"serving": true} runs on the serving harness, and D8's rule — verify the
# markers, then launch, as ONE step — is applied here, before any step.
PRE_RIG=
gate_2_rig() {
    local problems
    PRE_RIG=$(rig_snapshot) || refuse 2 "gate 2: the rig could not be read (see above); a machine that cannot be read is not compared, and nothing is measured on it"
    rig_assert_declared "$HOST" "$PRE_RIG" || refuse 2 "gate 2: refused — this machine is not the declared $HOST (see above)"
    if campaign_is_serving; then
        problems=$(_py - <<'PY'
import sys
from pathlib import Path

from tools.bench.serving.launch import verify_markers

problems = verify_markers(Path.cwd())
for line in problems:
    print(line)
sys.exit(2 if problems else 0)
PY
        ) || {
            printf '%s\n' "$problems" >&2
            refuse 2 "gate 2b: the serving harness on disk fails its own markers (above); 1.5 h of rig time once went to a run whose patch never reached the file (D8), and this campaign declares serving: true"
        }
    fi
}

# campaign.json is optional; absent means {"serving": false}.
campaign_is_serving() {
    local f=$ROOT/tools/runs/campaigns/$CAMPAIGN/campaign.json
    [ -f "$f" ] || return 1
    _py - "$f" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if doc.get("serving") is True else 1)
PY
}

# Gate 3: a tag reaches a driver as a digest, resolved ONCE, or not at all.
# The resolution itself is `image_digest` in _common.sh, called by each step
# for each tag it launches (a step knows its images; the door does not), and
# every driver refuses an image value that is not a digest. What the door owns
# is the daemon that resolution goes through: it must be reachable now, and it
# is the same one gate 7 asks about leftovers, so a step cannot resolve a tag
# against one daemon and start a container on another.
gate_3_image() {
    local docker=${RUN_DOCKER:-docker}
    command -v "$docker" >/dev/null 2>&1 ||
        refuse 2 "gate 3: '$docker' is not on PATH; a tag cannot be resolved to a digest and no container can be started, so nothing is measured"
    # A CLI with no daemon behind it passes `command -v` and fails inside the
    # step, after START/ROUND are stamped, as a REFUSED row against the arm.
    "$docker" info >/dev/null 2>&1 ||
        refuse 2 "gate 3: '$docker info' failed — the daemon a tag is resolved through does not answer, so no tag becomes a digest and no container is started; fix the daemon (or the operator's docker group) and nothing is measured until it answers"
}

# Gate 4 refuses a workload module that does not generate the pinned prompts.
# The digest is over 200 generated prompts, not the file text, so a formatter
# cannot void a comparison and a changed decile does; every driver imports this
# one module, so one check covers all of them.
gate_4_workload() {
    _py - <<'PY' || refuse 2 "gate 4: tools/runs/workload.py does not generate the pinned workload (see above); every comparison in the campaign would be void, so nothing is measured"
import sys
from pathlib import Path

from tools.runs.rows import WORKLOAD_DIGEST, workload_digest

got = workload_digest(Path("tools/runs/workload.py"))
if got != WORKLOAD_DIGEST:
    sys.exit(
        f"tools/runs/workload.py generates workload {got}, not {WORKLOAD_DIGEST}"
    )
PY
}

# Gate 5 makes the envelope, refuses to start a step whose declared artifact is
# already in it (artifacts are write-once; a second run over the same name would
# be two measurements filed as one), and mints RUN_ID. The declaration is read
# with grep and the step is not executed to learn it.
#
# One exception, declared rather than waived: a step that runs twice BY DESIGN
# (1-build-ladder.sh writes its stamps before step 3 and re-files the BENCH
# rows after it) names its file under RUN_REWRITES. An existing file is then
# admitted only if its ### START carries a run_id this same step minted — a
# step may supersede its own artifact and never another step's — and it is
# moved to <name>.superseded-<old run_id>.<ext> beside itself before the step
# starts, so the earlier pass stays on disk. A file with no run_id (the legacy
# shape) is refused: the door cannot tell who wrote a file that never said. And
# the old run_id may not be the one this run would mint: two door invocations
# never share an id, so a same-day re-run needs --suffix.
#
# A file declared under RUN_APPENDS (7-crash.sh onto step 6's) is held to the
# same rule minus the move: it must exist, and its first ### START must carry a
# run_id a step of this campaign minted. Its size and digest are kept for gate
# 8, which checks the step only added to it.
ARTIFACTS=
REWRITES=
APPENDS=
RUN_OUT_DIR=
ENVELOPE_MADE=
declare -A ASIDE_OF=()
declare -A APPEND_SIZE=()
declare -A APPEND_SHA=()
step_declaration() {
    sed -n "s/^#[[:space:]]*$1:[[:space:]]*//p" "$STEP_FILE" | head -n 1
}

# declared_files — every name the step declared, under any directive, one per
# line: what gate 7 stamps and gate 8 parses. Gate 5 guards each list by its
# own rule.
declared_files() {
    # Whitespace-separated names, validated in gate 5 to be exactly that: the
    # split is the intent.
    # shellcheck disable=SC2086
    printf '%s\n' $ARTIFACTS $REWRITES $APPENDS
}

# is_appended NAME — whether NAME was declared under RUN_APPENDS.
is_appended() {
    local a
    # shellcheck disable=SC2086
    for a in $APPENDS; do [ "$a" = "$1" ] && return 0; done
    return 1
}

# start_run_id FILE — the run_id on FILE's first ### START, or nothing.
start_run_id() {
    sed -n 's/^###[[:space:]]\{1,\}START[[:space:]].*[[:space:]]run_id=\([^[:space:]]\{1,\}\).*/\1/p' "$1" | head -n 1
}

gate_5_envelope() {
    local a d n f old writer aside other
    local -A seen=()
    for d in RUN_ARTIFACTS RUN_REWRITES RUN_APPENDS; do
        n=$(grep -c "^#[[:space:]]*$d:" "$STEP_FILE") || n=0
        [ "$n" -le 1 ] || refuse 2 "gate 5: $STEP_FILE carries $n '# $d:' lines; a step declares what it writes on one line per directive, and a file on a second line would be guarded by no gate at all"
    done
    ARTIFACTS=$(step_declaration RUN_ARTIFACTS)
    REWRITES=$(step_declaration RUN_REWRITES)
    APPENDS=$(step_declaration RUN_APPENDS)
    [ -n "$ARTIFACTS$REWRITES$APPENDS" ] || refuse 2 "gate 5: $STEP_FILE declares no '# RUN_ARTIFACTS: <name> ...' (or RUN_REWRITES / RUN_APPENDS) line, so the door cannot guard what it writes or parse it back (gate 8); a step that names nothing it produces is not run"
    for a in $(declared_files); do
        case $a in
            */* | '' | *[![:alnum:]_.-]*) refuse 2 "gate 5: declared artifact '$a' is not a plain file name ([A-Za-z0-9_.-]+, relative to the envelope)" ;;
        esac
        [ -z "${seen[$a]:-}" ] || refuse 2 "gate 5: $STEP_FILE declares '$a' twice; one file is guarded by one rule (RUN_ARTIFACTS, RUN_REWRITES or RUN_APPENDS), not by two"
        seen[$a]=1
    done
    RUN_DATE=${RUN_DATE:-$(date -u +%Y-%m-%d)}
    case $RUN_DATE in
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) : ;;
        *) refuse 2 "gate 5: RUN_DATE='$RUN_DATE' is not YYYY-MM-DD" ;;
    esac
    RUN_OUT_DIR="$ROOT/records/evidence/$RUN_DATE-$CAMPAIGN"
    # A run id parses back to its step by longest match (step_of_run_id), which
    # is exact only if no suffix makes `<step>-<suffix>` spell another step.
    if [ -n "$SUFFIX" ]; then
        for f in "$ROOT/tools/runs/campaigns/$CAMPAIGN"/[0-9]*-*.sh; do
            [ -f "$f" ] || continue
            other=$(basename -- "$f" .sh)
            other=${other#*-}
            [ "$other" != "$STEP_NAME" ] || continue
            case "$STEP_NAME-$SUFFIX" in
                "$other" | "$other"-*) refuse 2 "gate 5: --suffix '$SUFFIX' would mint run id $RUN_DATE-$CAMPAIGN-$STEP_NAME-$SUFFIX, which reads as step '$other' of this campaign; a run id names exactly one step, so give --suffix a value that does not spell another step's name" ;;
            esac
        done
    fi
    RUN_ID="$RUN_DATE-$CAMPAIGN-$STEP_NAME${SUFFIX:+-$SUFFIX}"
    case $RUN_ID in
        *[![:alnum:]_.-]* | '') refuse 2 "gate 5: RUN_ID '$RUN_ID' is not [A-Za-z0-9_.-]+; it names containers (<RUN_ID>-<role>) and must be legal as a docker name prefix" ;;
    esac
    # shellcheck disable=SC2086
    for a in $ARTIFACTS; do
        [ ! -e "$RUN_OUT_DIR/$a" ] || refuse 2 "gate 5: $a already exists under records/evidence/$RUN_DATE-$CAMPAIGN/; an artifact is written once. Move it aside deliberately if this is a re-run — the door does not overwrite evidence"
    done
    # Every RUN_REWRITES file is judged before any is moved, so a refusal on
    # the second leaves the first where it was.
    # shellcheck disable=SC2086
    for a in $REWRITES; do
        f=$RUN_OUT_DIR/$a
        [ -e "$f" ] || continue
        old=$(start_run_id "$f")
        [ -n "$old" ] || refuse 2 "gate 5: $a already exists under records/evidence/$RUN_DATE-$CAMPAIGN/ and its ### START carries no run_id=, so no step can claim it as its own; a file the door did not produce is never superseded by one it does. Move it aside deliberately if this is a re-run"
        writer=$(step_of_run_id "$old")
        [ "$writer" = "$STEP_NAME" ] || refuse 2 "gate 5: $a already exists under records/evidence/$RUN_DATE-$CAMPAIGN/ and was written by run_id=$old${writer:+ (step $writer)}, not by $CAMPAIGN/$STEP_NAME; a step may supersede its own artifact and never another step's. Move it aside deliberately if that is what is meant"
        [ "$old" != "$RUN_ID" ] || refuse 2 "gate 5: $a already exists under records/evidence/$RUN_DATE-$CAMPAIGN/ and carries run_id=$old — the id this run would mint. Two door invocations never share a run id (it names the containers, the ### START and any ### RIGMOVED of exactly one run), so give this re-run its own: --suffix S"
        case $a in
            *.*) aside="${a%.*}.superseded-$old.${a##*.}" ;;
            *) aside="$a.superseded-$old" ;;
        esac
        [ ! -e "$RUN_OUT_DIR/$aside" ] || refuse 2 "gate 5: $a was written by run_id=$old and $aside, already beside it, was too; two runs carried one run id and nothing recorded is overwritten. Move one aside deliberately, and give re-runs distinct ids with --suffix"
        ASIDE_OF[$a]=$aside
    done
    # shellcheck disable=SC2086
    for a in $APPENDS; do
        f=$RUN_OUT_DIR/$a
        [ -e "$f" ] || refuse 2 "gate 5: $a is declared under RUN_APPENDS and does not exist under records/evidence/$RUN_DATE-$CAMPAIGN/; this step appends to a file another step creates, and that step has not run through the door yet"
        old=$(start_run_id "$f")
        [ -n "$old" ] || refuse 2 "gate 5: $a exists under records/evidence/$RUN_DATE-$CAMPAIGN/ and its ### START carries no run_id=, so the door did not produce it; nothing recorded outside the door is appended to. Move it aside deliberately, or run the step that creates it through the door first"
        writer=$(step_of_run_id "$old")
        [ -n "$writer" ] || refuse 2 "gate 5: $a was written by run_id=$old, which names no step of campaign $CAMPAIGN; a step appends only to a file this campaign produced"
        APPEND_SIZE[$a]=$(stat -c %s "$f")
        APPEND_SHA[$a]=$(sha256sum <"$f" | cut -d' ' -f1)
    done
    [ -d "$RUN_OUT_DIR" ] || ENVELOPE_MADE=1
    mkdir -p "$RUN_OUT_DIR"
    for a in "${!ASIDE_OF[@]}"; do
        mv -- "$RUN_OUT_DIR/$a" "$RUN_OUT_DIR/${ASIDE_OF[$a]}"
        printf 'run.sh: gate 5: %s was written by this step; moved to %s before this run supersedes it (nothing recorded is lost)\n' "$a" "${ASIDE_OF[$a]}" >&2
    done
    RUN_HOST=$HOST
    # The step it was started as, so a file serving two campaign steps
    # (4-kernel-arms.sh: serve, and crash via 7-crash.sh) can hold its mode to it.
    RUN_STEP=$STEP_NAME
    export RUN_ID RUN_OUT_DIR RUN_HOST RUN_DATE RUN_STEP
}

# Gate 6 runs the step, from the repo root, with the step's own arguments after
# `--`. Its output is the operator's; the door adds nothing to it.
STEP_RC=0
INTERRUPTED=
gate_6_step() {
    printf 'run.sh: %s %s --host %s -> %s (RUN_ID=%s)\n' "$CAMPAIGN" "$STEP_NAME" "$HOST" "$RUN_OUT_DIR" "$RUN_ID" >&2
    (cd "$ROOT" && "$STEP_FILE" ${STEP_ARGS[@]+"${STEP_ARGS[@]}"}) || STEP_RC=$?
}

# Gate 7 runs after the step, whatever its exit: no container named for this
# run may be up, and the rig must read as it did before the step. The step's
# own start==end check lives inside the step and a step that dies before
# end_stamp compares nothing — a hard lock takes the ssh pipe with it, and the
# run whose end state is unknown is exactly the one that ended silently. So
# this runs on the interrupt path too, in the main flow and not inside the
# signal handler (where a nested $(rig_snapshot) came back with the signal's
# status and no reading). A leftover container is named, not removed: docker's
# name filter is a prefix match and `<RUN_ID>-` also covers a `--suffix` run
# of the same step, so the kill is the operator's, with the name in hand. A rig
# that moved is stamped `### RIGMOVED run_id=<this run> ...` after the step's
# own ### END into every TSV this run wrote — an appended file only if this
# run added to it — because the rows in it were produced under two machines
# and the file must say so; a non-TSV cannot carry the line and gets it in a
# <name>.RIGMOVED sidecar instead.
TEARDOWN_RC=0
gate_7_teardown() {
    local docker=${RUN_DOCKER:-docker} left post key a b moved stamp f
    left=$("$docker" ps --filter "name=^${RUN_ID}-" --format '{{.Names}}') || {
        printf 'run.sh: gate 7: %s ps failed; whether the run left a container is unknown\n' "$docker" >&2
        TEARDOWN_RC=1
        left=
    }
    if [ -n "$left" ]; then
        printf 'run.sh: gate 7: the step left containers named for this run: %s — a run that leaves a container is not green (kill what you started: %s rm -f <name>)\n' "$(printf '%s' "$left" | tr '\n' ' ')" "$docker" >&2
        TEARDOWN_RC=1
    fi
    post=$(rig_snapshot) || {
        printf 'run.sh: gate 7: the rig could not be re-read after the step; its end state is unknown and the run is not green\n' >&2
        TEARDOWN_RC=1
        return 0
    }
    moved=
    stamp="run_id=$RUN_ID"
    # shellcheck disable=SC2086  # a space-separated key list, split on purpose
    for key in uptime_since $RIG_DECLARED_KEYS; do
        a=$(_snap_get "$PRE_RIG" "$key")
        b=$(_snap_get "$post" "$key")
        [ "$a" = "$b" ] && continue
        moved="${moved:+$moved, }$key ($a -> $b)"
        stamp="$stamp $key=$b ${key}_start=$a"
    done
    if [ -n "$moved" ]; then
        printf 'run.sh: gate 7: THE RIG MOVED UNDER THIS RUN — %s. The rows were not all produced under one machine state; ### RIGMOVED is stamped after the step'"'"'s ### END and the run is not green\n' "$moved" >&2
        for a in $(declared_files); do
            f=$RUN_OUT_DIR/$a
            [ -f "$f" ] || continue
            if is_appended "$a" && [ "$(stat -c %s "$f")" -le "${APPEND_SIZE[$a]}" ]; then
                printf 'run.sh: gate 7: %s is not stamped — this run added nothing to it\n' "$a" >&2
                continue
            fi
            case $a in
                *.tsv)
                    if [ -s "$f" ] && [ "$(tail -c 1 "$f" | od -An -c | tr -d ' ')" != '\n' ]; then
                        printf '\n' >>"$f"
                    fi
                    printf '### RIGMOVED %s\n' "$stamp" >>"$f"
                    ;;
                *)
                    printf '### RIGMOVED %s\n' "$stamp" >"$f.RIGMOVED"
                    printf 'run.sh: gate 7: %s is not a TSV and cannot carry the stamp; it is written beside it as %s.RIGMOVED\n' "$a" "$a" >&2
                    ;;
            esac
        done
        TEARDOWN_RC=1
    fi
}

# Gate 8 reads back every artifact the step declared, through the parser the
# tests use, before this process returns 0. A file the parser rejects used to
# exit green on the rig and turn red a commit later. The artifact is left
# exactly as the step wrote it: it is the record of what the step did. A
# declared artifact that is not there after a step that exited 0 is not a
# note: a run that measured nothing is not green (every real step's --dry-run
# lands here, by design). A RUN_APPENDS file must still begin with the bytes
# gate 5 saw and must have grown. Then the two things the door did on the way
# in are undone where nothing followed: a superseded file whose successor was
# never written goes back under its own name, and an envelope the door made
# for a run that filed nothing is removed.
PARSE_RC=0
gate_8_parse() {
    local a f size sha
    local -a names=()
    # shellcheck disable=SC2086
    for a in $APPENDS; do
        f=$RUN_OUT_DIR/$a
        size=${APPEND_SIZE[$a]}
        if [ ! -f "$f" ]; then
            printf 'run.sh: gate 8: %s was declared under RUN_APPENDS and is gone after the step; the run is not green\n' "$a" >&2
            PARSE_RC=1
            continue
        fi
        sha=$(head -c "$size" "$f" | sha256sum | cut -d' ' -f1)
        if [ "$sha" != "${APPEND_SHA[$a]}" ]; then
            printf 'run.sh: gate 8: %s was declared under RUN_APPENDS and the step rewrote it — the %s bytes that were there before are no longer its prefix; left on disk as written, and the run is not green\n' "$a" "$size" >&2
            PARSE_RC=1
        elif [ "$(stat -c %s "$f")" -eq "$size" ] && [ "$STEP_RC" -eq 0 ]; then
            printf 'run.sh: gate 8: %s was declared under RUN_APPENDS and the step appended nothing to it; a run that measured nothing is not green\n' "$a" >&2
            PARSE_RC=1
        fi
    done
    # shellcheck disable=SC2086
    for a in $ARTIFACTS $REWRITES; do names+=("w:$a"); done
    # shellcheck disable=SC2086
    for a in $APPENDS; do names+=("a:$a"); done
    _py - "$RUN_OUT_DIR" "$STEP_RC" "${names[@]}" <<'PY' || PARSE_RC=1
import json
import sys
from pathlib import Path

from tools.runs.rows import read

out_dir = Path(sys.argv[1])
step_rc = int(sys.argv[2])
bad = 0
for token in sys.argv[3:]:
    mode, _, name = token.partition(":")
    path = out_dir / name
    if not path.is_file():
        if mode == "a":
            continue  # already named above
        if step_rc == 0:
            print(
                f"run.sh: gate 8: declared artifact {path} was not written by a step "
                "that exited 0; a run that measured nothing is not green",
                file=sys.stderr,
            )
            bad += 1
        else:
            print(
                f"run.sh: gate 8: declared artifact {path} was not written "
                f"(the step exited {step_rc})",
                file=sys.stderr,
            )
        continue
    try:
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        else:
            read(path)
    except Exception as error:  # noqa: BLE001 - the parser's own words are the verdict
        print(f"run.sh: gate 8: {path} does not parse — {error}", file=sys.stderr)
        bad += 1
if bad:
    print(
        f"run.sh: gate 8: {bad} declared artifact(s) missing or rejected; "
        "whatever was written is left on disk as written, and the run is not green",
        file=sys.stderr,
    )
    sys.exit(1)
PY
    for a in "${!ASIDE_OF[@]}"; do
        f=$RUN_OUT_DIR/$a
        [ ! -e "$f" ] || continue
        mv -- "$RUN_OUT_DIR/${ASIDE_OF[$a]}" "$f"
        printf 'run.sh: gate 8: %s was never rewritten; %s is back under its own name (nothing recorded is lost)\n' "$a" "${ASIDE_OF[$a]}" >&2
    done
    if [ -n "$ENVELOPE_MADE" ] && rmdir -- "$RUN_OUT_DIR" 2>/dev/null; then
        printf 'run.sh: gate 8: nothing was filed, so the envelope %s the door made is removed again\n' "$RUN_OUT_DIR" >&2
    fi
}

# --------------------------------------------------------------------------
# the door
# --------------------------------------------------------------------------

main() {
    parse_argv "$@"
    check_argv
    gate_1_round
    gate_2_rig
    gate_3_image
    gate_4_workload
    gate_5_envelope
    # Whatever ends the step — its own exit, or a signal that reaches this
    # shell — the rig is re-read and the containers are checked. The handler
    # only records the signal: the gates run here, in the main flow, once the
    # step has returned (bash defers the trap until then).
    trap 'INTERRUPTED=1' INT TERM
    gate_6_step
    trap - INT TERM
    gate_7_teardown
    gate_8_parse
    if [ -n "$INTERRUPTED" ]; then
        printf 'run.sh: interrupted during the step (it exited %s); gates 7 and 8 ran above, and the run is not green\n' "$STEP_RC" >&2
        exit 130
    fi
    if [ "$TEARDOWN_RC" -ne 0 ] || [ "$PARSE_RC" -ne 0 ]; then
        exit 1
    fi
    if [ "$STEP_RC" -ne 0 ]; then
        printf 'run.sh: the step exited %s\n' "$STEP_RC" >&2
        exit "$STEP_RC"
    fi
    printf 'run.sh: green — %s/%s done; declared artifacts (%s) checked under %s\n' \
        "$CAMPAIGN" "$STEP_NAME" "$(declared_files | tr '\n' ' ' | sed 's/ $//')" "$RUN_OUT_DIR" >&2
}

main "$@"
