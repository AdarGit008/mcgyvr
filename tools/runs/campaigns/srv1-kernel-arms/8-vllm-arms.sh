#!/usr/bin/env bash
# tools/runs/campaigns/srv1-kernel-arms/8-vllm-arms.sh — campaign step 8, and the only producer of
# `records/evidence/2026-09-02-srv1-kernel-arms/srv1-vllm-arms.tsv`
# (`tools/runs/rows.py`). Behaviour 12,
# `tests/test_two_backends_on_one_checkpoint_is_the_only_pair.py`.
#
# WHAT THIS ASKS, AND WHAT IT MUST NEVER BE READ AS
# -------------------------------------------------
# A CAPABILITY probe, inside vLLM only: srv1's TU116 die reports compute
# capability 7.5 with the tensor cores removed, Marlin's sm75 path is `mma.sync`
# PTX that this silicon microcodes, so — does vLLM offer this card a path that
# is not that, and what does it cost? Guideline 5: no number in this file may be
# compared with a llama.cpp row. The two engines differ in scheduler, batching,
# KV management and quantisation format; a tok/s ratio across them measures two
# stacks. **B1 vs B2 is the only pair this file contains**, which is why the
# artifact carries no llama.cpp arm, no cross-engine field and no ratio.
#
# THE PAIR (B2-CHECKPOINT.md, verified 2026-09-01 — supersedes the run doc)
#   B1  --linear-backend marlin    -> MarlinLinearKernel   (mma.sync on sm75)
#   B2  --linear-backend exllama   -> ExllamaLinearKernel  (__hfma2, no mma.sync)
# One flag, one variable, one checkpoint. The run doc's `--quantization gptq`
# vs `gptq_marlin` fallback is INVALID in v0.26.0 — both strings map to
# `AutoGPTQConfig` (quantization/__init__.py:152-154), so that contrast would
# print two flags and run one kernel. It is not implemented here.
#
# `kernel_observed=` is read from the engine's own line,
# `Using {Marlin,Exllama}LinearKernel for AutoGPTQLinearMethod`
# (auto_gptq.py:354-358) — never from the flag. A flag that parses is not a
# kernel that ran: `--cpu-offload-params experts` was accepted, hashed into the
# compile cache key and silently ignored under the V2 runner.
#
# THE CHECKPOINT. srv1 holds exactly one GPTQ checkpoint and it is the wrong
# shape: `Qwen/Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4`, 7.9 G in three shards, verified
# present on 2026-09-02 (the 2026-08-31 inventory does not list it, and an
# earlier note in B2-CHECKPOINT.md that said srv1 held "no GPTQ checkpoint of any
# shape" was WRONG — see that file's section (A)). It is MoE, so
# `--linear-backend` would bind only its attention and dense projections while
# the experts route through `--moe-backend`, and 7.9 G does not fit a 6144 MiB
# card. So B2 still sits behind a fetch of a DENSE one — the conclusion is
# unchanged, the reason for it was not what this header used to claim.
# `Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4`:
# 1.071 GiB of weights on a 6144 MiB card, dense Qwen2ForCausalLM. Its
# quantisation parameters live in `config.json` under `quantization_config` —
# these repos ship NO `quantize_config.json` (HTTP 404), so a script that checks
# that filename reports "missing config" for exactly the right checkpoints. The
# requirement chain, all of it a hard gate before either launch:
#   bits=4 sym=true  -> auto_gptq.py:100-104 TYPE_MAP gives uint4b8, the type
#                       ExllamaLinearKernel accepts; anything else is not it
#   group_size=128   -> divides 1536 and 8960, exllama's can_implement
#   desc_act=false   -> keeps has_g_idx False and the weight permute out of the
#                       arm (not a hard gate at TP=1; still held)
#   torch_dtype fp16 -> "Exllama only supports float16 activations"
# A mismatch is a REFUSED row, not a warning: a checkpoint's name is not
# evidence of its format (`nemotron-30b-awq/` resolves as compressed-tensors).
# The verifier also reads every weight byte, which is what makes a dangling HF
# blob symlink — mistaken for a capability limit in two REFUSED rows on
# 2026-09-01 — fail here, loudly, instead of at launch.
#
# THE POOL IS PINNED, NOT LEFT TO FLOAT. Under `--gpu-memory-utilization` the KV
# cache is whatever survives the weights, so if the two kernels' scratch buffers
# differ the pools differ, the driver's width gate drops different rungs, and
# the file compares two schedulers rather than two kernels. Both arms therefore
# pass `--kv-cache-memory-bytes` (the knob ADR-0039 already uses for this exact
# architecture: 1,879,048,192 B / 28,672 B per token = 65,536 tokens), and the
# engine's own `GPU KV cache size:` line is compared across the arms afterwards.
# An unequal pool does not silently become a verdict — it forces `unresolved`.
#
# GUIDELINE 8. A refusal is a result: every launch goes through `retry3`, and a
# B2 that never came up is written as a REFUSED row carrying `checkpoint_quant`,
# `tries>=3` and the engine's own words — resolved conflict §6.3. Known risk,
# unexecuted (B2-CHECKPOINT.md): `AutoGPTQLinearMethod.__init__` calls
# `verify_marlin_supported()` unconditionally, before the kernel chooser runs,
# so B2 may die with a Marlin-worded message. That is a finding and a REFUSED
# row, not a setup error, and this script says so on stderr when it sees one.
#
# Nothing here fabricates. Every field is read from the engine log, the driver's
# stdout, the checkpoint's own config.json or the live rig; a value that could
# not be read stops the run with a message instead of acquiring a placeholder.
#
# Usage:
#   tools/runs/campaigns/srv1-kernel-arms/8-vllm-arms.sh [--dry-run]
#
# Environment (all optional, none required, none fabricated from):
#   RUN_HOST RUN_REPO RUN_RETRY_SLEEP   — see tools/runs/_common.sh
#   HF_TOKEN                            — passed through to the fetch if set
#
# Through the door only (python -m mcgyvr.serving.run): RUN_ID names the run in ### START,
# ### ROUND records the product round gate 1 checked, the file lands in
# $RUN_OUT_DIR, and IMG is resolved to a digest ONCE (image_digest, gate 3)
# before the driver sees it — the driver refuses a tag.
# RUN_ARTIFACTS: srv1-vllm-arms.tsv

[ -n "${RUN_ID:-}" ] || { echo "8-vllm-arms.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-kernel-arms --step tools/runs/campaigns/srv1-kernel-arms/8-vllm-arms.sh --model <blob as the rig sees it>" >&2; exit 2; }

set -euo pipefail

_here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./_common.sh disable=SC1091
. "$_here/../../_common.sh"
door_required

# --------------------------------------------------------------------------
# what this run is
# --------------------------------------------------------------------------

ARTIFACT="srv1-vllm-arms.tsv"
DRIVER="tools/runs/drivers/vllm_sweep.py"
# The prompts the driver draws come from this module, not from the driver:
# the WORKLOAD stamp names it, and the digest is re-derived from it.
WORKLOAD="tools/runs/workload.py"

IMG="vllm/vllm-openai:v0.26.0"
# What the driver actually runs: IMG resolved once by image_digest (gate 3).
IMG_DIGEST=""
MODEL="Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4"
CELL_CELL="gptq"

# The cell, in the driver's own `util:maxlen:seqs:kvdtype:levels[:extra]` form.
# util 0.85 is B2-CHECKPOINT.md's budget; len 2048 clears the driver's
# MAXLEN_NEED (887+460=1347) so no SKIP is emitted; levels are step 4's.
CELL_UTIL="0.85"
CELL_LEN="2048"
CELL_SEQS="8"
CELL_KV="auto"
CELL_LEVELS="1,4,8"

# 1,879,048,192 B = 65,536 tokens at this architecture's measured 28,672 B/token
# (28 layers x 2 KV heads x 128 head_dim x 2 x 2 B). 65,536 / len 2048 = 32
# concurrent requests, four times the widest rung, so the driver's WIDTH gate
# drops nothing and both arms run the same ladder.
KV_CACHE_BYTES="1879048192"

# The container the driver names — `<RUN_ID>-vsweep`, so gate 7 of the door
# finds it. Its engine log is the only place the kernel that actually ran is
# written down.
CONTAINER="$RUN_ID-vsweep"

DRY_RUN=0

# --------------------------------------------------------------------------
# the checkpoint verifier
#
# Printed in full by --dry-run, run once before either launch. It prints
# `checkpoint_quant=` and `weights_sha256=` on stdout BEFORE it decides, so a
# refusal can still record the quant format it was offered, and exits non-zero
# with the whole requirement chain's verdict when the checkpoint is wrong.
# --------------------------------------------------------------------------

VERIFY_PY=$(
cat <<'PY'
import hashlib
import json
import os
import sys

snap = sys.argv[1]
cfg_path = os.path.join(snap, "config.json")
if not os.path.isfile(cfg_path):
    sys.exit(
        f"no config.json under {snap}. The Qwen GPTQ-Int4 repos ship no "
        "quantize_config.json (HTTP 404); the quantisation parameters live in "
        "config.json under quantization_config, which is where vLLM reads them."
    )
with open(cfg_path, encoding="utf-8") as fh:
    cfg = json.load(fh)
q = cfg.get("quantization_config")
if not isinstance(q, dict):
    sys.exit(
        f"{cfg_path} declares no quantization_config object, so this checkpoint "
        "names no quantisation and its repo id is not evidence of one."
    )

quant = "/".join(
    [
        str(q.get("quant_method")),
        f"bits={q.get('bits')}",
        f"group_size={q.get('group_size')}",
        f"desc_act={str(q.get('desc_act')).lower()}",
        f"sym={str(q.get('sym')).lower()}",
    ]
)
print("checkpoint_quant=" + quant.replace(" ", "_"))

bad = []
for key, want in (("quant_method", "gptq"), ("bits", 4), ("group_size", 128),
                  ("desc_act", False), ("sym", True)):
    got = q.get(key)
    if got != want:
        bad.append(f"{key}={got!r}, want {want!r}")
dtype = cfg.get("torch_dtype")
if dtype != "float16":
    bad.append(
        f"torch_dtype={dtype!r}, want float16 — ExllamaLinearKernel supports "
        "float16 activations only"
    )

files = sorted(f for f in os.listdir(snap) if f.endswith(".safetensors"))
if not files:
    bad.append(f"no *.safetensors under {snap}")
digest = hashlib.sha256()
for name in files:
    real = os.path.realpath(os.path.join(snap, name))
    if not os.path.isfile(real):
        bad.append(
            f"{name} resolves to {real}, which is not a file — a dangling HF "
            "blob symlink was read as a capability limit twice on 2026-09-01"
        )
        continue
    one = hashlib.sha256()
    size = 0
    with open(real, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            size += len(chunk)
            one.update(chunk)
    if size == 0:
        bad.append(f"{name} is zero bytes")
    digest.update(name.encode("utf-8"))
    digest.update(one.digest())
if files and not bad:
    print("weights_sha256=" + digest.hexdigest())
print("weights_files=" + ",".join(files))

if bad:
    sys.exit(
        "checkpoint " + snap + " does not meet the requirement chain B2 needs "
        "(B2-CHECKPOINT.md): " + "; ".join(bad)
    )
PY
)

# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------

usage() {
    cat <<'EOF'
usage: tools/runs/campaigns/srv1-kernel-arms/8-vllm-arms.sh [--dry-run]

  --dry-run   print every command line this run would execute, in order, and
              exit. Writes no artifact, fetches nothing, launches nothing.

Writes records/evidence/2026-09-02-srv1-kernel-arms/srv1-vllm-arms.tsv.
EOF
}

say() {
    printf 'srv1-vllm-arms: %s\n' "$*" >&2
}

# One place builds a command line, so --dry-run cannot drift from what runs.
show() {
    printf '+ %s\n' "$*"
}

# The fetch. `hf` is the current CLI, `huggingface-cli` its predecessor; off-rig
# (--dry-run) neither need exist for the plan to name the one that would run.
hf_bin() {
    if command -v hf >/dev/null 2>&1; then
        printf 'hf'
    elif command -v huggingface-cli >/dev/null 2>&1; then
        printf 'huggingface-cli'
    elif [ "$DRY_RUN" -eq 1 ]; then
        printf 'hf'
    else
        _fail "neither 'hf' nor 'huggingface-cli' is on PATH, and srv1's only GPTQ checkpoint is the MoE Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4, which this arm cannot use. B2 sits behind this fetch"
        return 1
    fi
}

download_cmdline() {
    local bin
    bin=$(hf_bin) || return 1
    printf '%s download %s' "$bin" "$MODEL"
}

verify_cmdline() {
    # The literal is the point: --dry-run names the variable, and the plan
    # prints its whole body separately.
    # shellcheck disable=SC2016
    printf 'uv run --no-sync --quiet python -c "$VERIFY_PY" %s' "${1:-<snapshot-dir>}"
}

# The driver's argv for one arm, in DRIVER_ARGV. `extra` is appended VERBATIM to
# the engine's argv with `+` read as a space, so the whole cell stays one word.
DRIVER_ARGV=()
driver_argv() {
    local arm backend cell label
    arm=$1
    backend=$(arm_backend "$arm") || return 1
    label=$(arm_label "$arm" "$CELL_CELL") || return 1
    cell="$CELL_UTIL:$CELL_LEN:$CELL_SEQS:$CELL_KV:$CELL_LEVELS"
    cell="$cell:--linear-backend+$backend+--dtype+float16"
    cell="$cell+--kv-cache-memory-bytes+$KV_CACHE_BYTES"
    DRIVER_ARGV=(uv run --no-sync --quiet python "$DRIVER" "$label" "$MODEL" "$cell")
}

driver_cmdline() {
    driver_argv "$1" || return 1
    printf '%s' "${DRIVER_ARGV[*]}"
}

arm_backend() {
    case $1 in
        B1) printf 'marlin' ;;
        B2) printf 'exllama' ;;
        *)
            _fail "arm_backend: '$1' is not B1 or B2. This file holds one pair and no third arm"
            return 1
            ;;
    esac
}

logs_cmdline() {
    printf 'docker logs %s   # snapshotted once a second while the driver runs, into %s' \
        "$CONTAINER" "${1:-<arm>.enginelog}"
}

kernel_cmdline() {
    printf "grep -oE 'Using [A-Za-z]+LinearKernel for AutoGPTQLinearMethod' %s" \
        "${1:-<arm>.enginelog}"
}

# --------------------------------------------------------------------------
# --dry-run: the plan, built by the same functions that execute it
# --------------------------------------------------------------------------

plan() {
    local arm
    cat <<EOF
# 8-vllm-arms.sh --dry-run
# Nothing below is executed. No artifact is written, nothing is fetched, no
# container is started.
#
# artifact : $RUN_OUT_DIR/$ARTIFACT
# workload : $WORKLOAD (digest re-computed by tools/runs/rows.py:workload_digest)
# pair     : B1 --linear-backend marlin  vs  B2 --linear-backend exllama
# held     : model weights_sha256 img util len seqs kv (+ the pinned KV pool)

## 0. the live rig, read for ### RIG / ### START (tools/runs/_common.sh)
EOF
    show "nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version,memory.reserved,memory.used,memory.free --format=csv,noheader,nounits"
    show "cat /sys/class/powercap/intel-rapl:<package-0>/constraint_{0,1}_power_limit_uw"
    show "dmidecode -t memory"
    echo
    echo "## 1. THE CHECKPOINT — fetched and verified BEFORE either launch."
    echo "##    A mismatch here is a REFUSED row for both arms, not a warning."
    echo "##    Present already? The same command with the network switched off"
    echo "##    resolves the cache and fetches nothing; only a miss downloads."
    show "HF_HUB_OFFLINE=1 $(download_cmdline)"
    show "$(download_cmdline)"
    show "$(verify_cmdline '<snapshot-dir>')"
    echo
    # shellcheck disable=SC2016
    echo '##    where "$VERIFY_PY" is, verbatim:'
    printf '%s\n' "$VERIFY_PY" | sed 's/^/#     /'
    echo
    echo "## 2. THE IMAGE — one tag, resolved to a digest ONCE (gate 3); VLLM_IMG carries the digest."
    show "VLLM_IMG=\$(image_digest $IMG)"
    echo
    for arm in B1 B2; do
        printf '## 2.%s  arm %s, --linear-backend %s. Three attempts before a refusal is believed (guideline 8).\n' \
            "$arm" "$arm" "$(arm_backend "$arm")"
        show "$(driver_cmdline "$arm")"
        show "$(logs_cmdline "$arm.enginelog")"
        show "$(kernel_cmdline "$arm.enginelog")"
        show "grep -oE 'GPU KV cache size: [0-9,]+ tokens' $arm.enginelog"
        echo
    done
    cat <<EOF
## 3. emit, in this order, into $RUN_OUT_DIR/$ARTIFACT
##      ### WORKLOAD digest=<computed> driver=$WORKLOAD
##      ### START ... pl1_source=constraint_0_power_limit_uw
##      ### RIG ...                       (re-stamped before each arm)
##      <arm rows: CONFIG or REFUSED, then the driver's level rows>
##      ### VERDICT hypothesis=tensor-core-emulation status=<...> cited_line=<n>
##      ### END ...                       (compared field by field with START)
EOF
}

# --------------------------------------------------------------------------
# reading the rig's answers
# --------------------------------------------------------------------------

# `docker logs` returns the whole log every time, so the last snapshot taken
# before the driver removes the container is the complete engine log. A
# `docker logs -f` would have to survive the container's own restarts; this
# cannot miss the kernel line for a reason that is not the line being absent.
snapshot_engine_log() {
    local logfile sentinel
    logfile=$1
    sentinel=$2
    while [ ! -e "$sentinel" ]; do
        if docker logs "$CONTAINER" >"$logfile.part" 2>&1; then
            mv -f "$logfile.part" "$logfile"
        fi
        sleep 1
    done
    if docker logs "$CONTAINER" >"$logfile.part" 2>&1; then
        mv -f "$logfile.part" "$logfile"
    fi
    rm -f "$logfile.part"
}

# The engine names the kernel that ran (auto_gptq.py:354-358). Empty output
# means the line is absent, which is never turned into a value here.
kernel_from_log() {
    local logfile line
    logfile=$1
    [ -f "$logfile" ] || return 0
    line=$(grep -oE 'Using [A-Za-z]+LinearKernel for AutoGPTQLinearMethod' "$logfile" | head -n 1) || line=
    [ -n "$line" ] || return 0
    line=${line#Using }
    printf '%s' "${line%% for *}"
}

pool_from_log() {
    local logfile line
    logfile=$1
    [ -f "$logfile" ] || return 0
    line=$(grep -oE 'GPU KV cache size: [0-9,]+ tokens' "$logfile" | tail -n 1) || line=
    [ -n "$line" ] || return 0
    line=${line#GPU KV cache size: }
    line=${line% tokens}
    printf '%s' "${line//,/}"
}

# --------------------------------------------------------------------------
# one attempt at one arm
# --------------------------------------------------------------------------

ARM_ATTEMPT=0
ARM_ROWS=""
ARM_LOG=""

run_arm_once() {
    local arm out log sentinel watcher rc
    arm=$1
    ARM_ATTEMPT=$((ARM_ATTEMPT + 1))
    out="$WORK/$arm.attempt$ARM_ATTEMPT.rows"
    log="$WORK/$arm.attempt$ARM_ATTEMPT.enginelog"
    sentinel="$WORK/$arm.attempt$ARM_ATTEMPT.done"
    ARM_ROWS=$out
    ARM_LOG=$log
    rm -f "$sentinel"
    : >"$log"
    driver_argv "$arm" || return 1
    say "attempt $ARM_ATTEMPT: ${DRIVER_ARGV[*]}"
    snapshot_engine_log "$log" "$sentinel" &
    watcher=$!
    rc=0
    "${DRIVER_ARGV[@]}" >"$out" 2>"$out.stderr" || rc=$?
    : >"$sentinel"
    wait "$watcher" || true
    if [ "$rc" -ne 0 ]; then
        say "the driver exited $rc on attempt $ARM_ATTEMPT (stderr in $out.stderr)"
        return 1
    fi
    # A launch is believed only when the driver printed the row it prints after
    # a successful launch AND a warm-up request.
    awk -F'\t' '$3 == "CONFIG" { found = 1 } END { exit found ? 0 : 1 }' "$out"
}

# The driver's own words for why an arm did not come up. Its REFUSED line
# already carries the last ERROR lines from the container (it drops the
# levelled INFO banner first, after a startup banner was recorded as a reason
# on 2026-09-01). The engine log is the fallback, and "nothing at all" is said
# as that rather than filled in.
refusal_reason() {
    local arm rows log why
    arm=$1
    rows=$2
    log=$3
    why=
    if [ -f "$rows" ]; then
        why=$(awk -F'\t' '$3 == "REFUSED" || $3 == "DEGENERATE" { $1=""; $2=""; $3=""; print }' "$rows" | tail -n 1)
    fi
    if [ -z "$why" ] && [ -f "$log" ]; then
        why=$(grep -iE 'error|traceback|not supported|cannot implement|out of memory|capability|assert' "$log" | tail -n 2 | tr '\n' ' ') || why=
    fi
    why=$(printf '%s' "$why" | tr '\t\n' '  ' | tr -s ' ' | sed -e 's/^ *//' -e 's/ *$//')
    if [ -n "$why" ]; then
        printf 'arm %s (--linear-backend %s) produced no CONFIG row in %s attempts; the engine said: %s' \
            "$arm" "$(arm_backend "$arm")" "${RUN_TRIES:-0}" "$why"
    else
        printf 'arm %s (--linear-backend %s) produced no CONFIG row in %s attempts and the container left no error line in its log, so the cause is unread rather than known' \
            "$arm" "$(arm_backend "$arm")" "${RUN_TRIES:-0}"
    fi
}

# --------------------------------------------------------------------------
# emitting
# --------------------------------------------------------------------------

OUT=""
LAST_LINE=0

emit() {
    "$@" >>"$OUT"
    LAST_LINE=$(wc -l <"$OUT")
    LAST_LINE=$((LAST_LINE))
}

# The verdict rule, as a stamp. It used to be a free-text `### verdict-rule:`
# line (§1.6 allowed one as long as its first token was not key=value), but a
# file the door produced is held to the stamp rules eagerly when it is read
# back (rows.read, gate 8): every token after the name must be key=value, so
# the sentence rides as one whitespace-free token instead. Same one line, same
# line count, and the VERDICT's cited_line still points where it did.
note() {
    stamp NOTE "verdict_rule=$(_tok "$*")" >>"$OUT"
    LAST_LINE=$(wc -l <"$OUT")
    LAST_LINE=$((LAST_LINE))
}

# Re-emit one of the driver's rows with the fields the contract adds: `arm=` and
# `img=` on every non-SKIP row (§3). Tab-separated tokens that are key=value
# become fields; everything else is the parser's free-text tail (§1.3).
#
# NOTE ON `otok_req`. The contract's §3 table scopes `otok_req` to
# `srv1-lcpp-arms.tsv`, and nothing reads it here. This driver prints the
# per-request output budget nowhere — `want` never leaves `post()` — so the
# field is omitted rather than reconstructed from the driver's seeded counter,
# which would be a second implementation of the workload and a value this run
# did not measure.
relay_row() {
    local arm line label kind tok tail
    arm=$1
    line=$2
    local -a parts=()
    local -a args=()
    mapfile -t parts < <(printf '%s' "$line" | tr '\t' '\n')
    [ "${#parts[@]}" -ge 3 ] || return 0
    label=${parts[1]}
    kind=${parts[2]}
    args=("arm=$arm" "img=$IMG")
    tail=
    for tok in "${parts[@]:3}"; do
        [ -n "$tok" ] || continue
        if _kv_ok "$tok" && ! _has_space "$tok"; then
            case $tok in
                img=*)
                    # Pinned above and asserted at the CONFIG row; the driver's
                    # copy would only ever restate or contradict it.
                    continue
                    ;;
            esac
            args+=("$tok")
        else
            tail="${tail:+$tail }$tok"
        fi
    done
    if [ -n "$tail" ]; then
        # §1.3: free text whose first word looks like key=value is eaten as a
        # field and vanishes from the tail. Name the source rather than edit
        # the engine's words.
        if _kv_ok "${tail%% *}"; then
            tail="engine: $tail"
        fi
        args+=(-- "$tail")
    fi
    emit row "$label" "$kind" "${args[@]}"
}

# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

WORK=""
CHECKPOINT_QUANT=""
WEIGHTS_SHA256=""
SNAPSHOT=""

cleanup() {
    local status=$?
    if [ -n "$WORK" ] && [ -d "$WORK" ]; then
        rm -rf "$WORK"
    fi
    return "$status"
}

# hf_snapshot_path FILE — the snapshot directory, out of `hf download`'s stdout.
#
# THE PARSE THAT FABRICATED TWO REFUSALS. srv1 runs huggingface_hub 1.24.0, whose
# `hf download` prints a TWO-LINE summary:
#     ✓ Downloaded
#       path: /home/adaramir/.cache/huggingface/hub/models--Qwen--...
# The old `tail -n 1` therefore returned `  path: /home/...` — a sentence, not a
# directory — the `[ -d ]` below failed, and B1 and B2 were both written REFUSED
# with `checkpoint_quant=unread` while the checkpoint sat on the rig, complete
# and conforming (gptq / bits=4 / group_size=128 / desc_act=false / sym=true).
# A refusal that did not happen is the one unacceptable outcome in this repo, and
# this one came out of a line-position assumption about a CLI's cosmetics.
#
# So the LABELLED field is read. A version that prints the bare path on one line
# still parses, through the fallback; either way the answer has to be a directory
# on this host before anything believes it.
#
# `huggingface-cli` is not a fallback for this. On 1.24.0 it writes NOTHING to
# stdout (measured on srv1: 0 bytes, exit 1 offline), so there is no path in it
# to read at all — which is also why hf_bin prefers `hf`.
hf_snapshot_path() {
    local p
    p=$(sed -n 's/^[[:space:]]*path:[[:space:]]*//p' "$1" | head -n 1)
    if [ -z "$p" ]; then
        p=$(grep -v '^[[:space:]]*$' "$1" | tail -n 1)
    fi
    p=${p#"${p%%[![:space:]]*}"}
    p=${p%"${p##*[![:space:]]}"}
    printf '%s' "$p"
}

fetch_and_verify() {
    local bin out rc
    bin=$(hf_bin) || return 1
    SNAPSHOT=""
    # Already here? Ask the same tool with the network switched off. That resolves
    # the cache through huggingface_hub's own logic rather than through this
    # script guessing at its directory layout, and a checkpoint already on the rig
    # then costs nothing: srv1 holds this one at
    # ~/.cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4/
    # snapshots/d45c7545dc428f013534f8bfd0441b3afffc0006 and re-fetching it would
    # verify the same bytes it already verified.
    if HF_HUB_OFFLINE=1 "$bin" download "$MODEL" \
        >"$WORK/fetch.out" 2>"$WORK/fetch.stderr"; then
        SNAPSHOT=$(hf_snapshot_path "$WORK/fetch.out")
        if [ -n "$SNAPSHOT" ] && [ -d "$SNAPSHOT" ]; then
            say "checkpoint already on this host, nothing fetched: $SNAPSHOT"
        else
            SNAPSHOT=""
        fi
    fi
    if [ -z "$SNAPSHOT" ]; then
        say "fetching $MODEL"
        if ! "$bin" download "$MODEL" >"$WORK/fetch.out" 2>"$WORK/fetch.stderr"; then
            say "the fetch failed: $(tail -n 3 "$WORK/fetch.stderr" | tr '\n' ' ')"
            return 1
        fi
        SNAPSHOT=$(hf_snapshot_path "$WORK/fetch.out")
    fi
    if [ -z "$SNAPSHOT" ] || [ ! -d "$SNAPSHOT" ]; then
        say "'$bin download $MODEL' named no snapshot directory. Its whole stdout was: $(tr '\n' ' ' <"$WORK/fetch.out" | tr -s ' ')"
        return 1
    fi
    say "verifying $SNAPSHOT — quantization_config, and every weight byte"
    rc=0
    out=$(uv run --no-sync --quiet python -c "$VERIFY_PY" "$SNAPSHOT" 2>"$WORK/verify.stderr") || rc=$?
    # Printed before the verdict, so a refusal can still say what it was offered.
    CHECKPOINT_QUANT=$(printf '%s\n' "$out" | sed -n 's/^checkpoint_quant=//p' | head -n 1)
    WEIGHTS_SHA256=$(printf '%s\n' "$out" | sed -n 's/^weights_sha256=//p' | head -n 1)
    if [ "$rc" -ne 0 ]; then
        VERIFY_WHY=$(tr '\t\n' '  ' <"$WORK/verify.stderr" | tr -s ' ')
        say "checkpoint REFUSED: $VERIFY_WHY"
        return 1
    fi
    [ -n "$CHECKPOINT_QUANT" ] || { say "the verifier named no checkpoint_quant"; return 1; }
    [ -n "$WEIGHTS_SHA256" ] || { say "the verifier named no weights_sha256"; return 1; }
    say "checkpoint ok: $CHECKPOINT_QUANT weights_sha256=$WEIGHTS_SHA256"
}

VERIFY_WHY=""

main() {
    local root arm label kernel pool tries
    local b1_config_line=0 b2_config_line=0 b2_refused_line=0 b2_last_level=0
    local b1_pool="" b2_pool="" status cited line why

    root=$(_repo_root) || return 1
    # The envelope: the door's $RUN_OUT_DIR (door_required refused without it).
    OUT="$RUN_OUT_DIR/$ARTIFACT"
    [ -d "$(dirname "$OUT")" ] || { _fail "$(dirname "$OUT") is not a directory"; return 1; }

    WORK=$(mktemp -d "${TMPDIR:-/tmp}/srv1-vllm-arms.XXXXXX")
    trap cleanup EXIT

    # Gate 3: the tag becomes a digest, once, before anything is written. The
    # driver reads VLLM_IMG and refuses a tag; it is handed the digest here
    # rather than inheriting whatever the shell carries, and the CONFIG row it
    # prints is asserted to agree.
    IMG_DIGEST=$(image_digest "$IMG") || { _fail "$IMG resolves to no digest on this host (docker image inspect failed); both arms hold this image fixed, and it is not here"; return 1; }
    export VLLM_IMG="$IMG_DIGEST"

    say "writing $OUT"
    : >"$OUT"
    emit workload_stamp "$WORKLOAD"
    emit start_stamp
    emit round_stamp
    emit rig_stamp

    # ---- the checkpoint, before either launch -----------------------------
    if ! retry3 fetch_and_verify; then
        tries=${RUN_TRIES:-0}
        say "the checkpoint did not verify in $tries attempts; neither arm is launched"
        for arm in B1 B2; do
            label=$(arm_label "$arm" "$CELL_CELL")
            emit refused "$label" \
                "arm=$arm" "img=$IMG" "model=$MODEL" \
                "linear_backend=$(arm_backend "$arm")" \
                "checkpoint_quant=${CHECKPOINT_QUANT:-unread}" \
                "tries=$tries" \
                -- "the checkpoint this pair holds fixed was not established and its quantization_config was never read, so neither kernel was offered a layer to implement: ${VERIFY_WHY:-the fetch produced no snapshot directory}"
            if [ "$arm" = "B2" ]; then
                b2_refused_line=$LAST_LINE
            fi
        done
        note "verdict-rule: no arm launched, so no row in this file can support or refute the hypothesis."
        emit stamp VERDICT hypothesis=tensor-core-emulation status=unresolved "cited_line=$b2_refused_line"
        emit end_stamp
        rig_assert_unchanged || true
        _fail "the checkpoint was refused; the file records both arms as REFUSED and behaviour 12 stays RED until a conforming GPTQ checkpoint is on srv1"
        return 1
    fi

    # ---- the two arms -----------------------------------------------------
    for arm in B1 B2; do
        label=$(arm_label "$arm" "$CELL_CELL")
        ARM_ATTEMPT=0
        emit rig_stamp
        if retry3 run_arm_once "$arm"; then
            kernel=$(kernel_from_log "$ARM_LOG")
            pool=$(pool_from_log "$ARM_LOG")
            if [ -z "$kernel" ]; then
                _fail "$arm launched but its engine log holds no 'Using <...>LinearKernel for AutoGPTQLinearMethod' line ($ARM_LOG). A flag that parses is not a kernel that ran, and this run will not write a kernel_observed it did not read"
                return 1
            fi
            case $(printf '%s' "$kernel" | tr '[:upper:]' '[:lower:]') in
                *"$(arm_backend "$arm")"*) : ;;
                *)
                    say "WARNING: $arm asked for --linear-backend $(arm_backend "$arm") and the engine reports $kernel. The observed value is what is written; the verdict is forced to unresolved."
                    ;;
            esac
            # The driver's CONFIG row, enriched with the seven held fields and
            # the kernel the engine named. Its own CONFIG fields (vram, kv_tok,
            # maxconc, warm_ptok) ride along.
            local -a cfg_extra=()
            local cfgline tok
            cfgline=$(awk -F'\t' '$3 == "CONFIG"' "$ARM_ROWS" | head -n 1)
            local -a cfgparts=()
            mapfile -t cfgparts < <(printf '%s' "$cfgline" | tr '\t' '\n')
            for tok in "${cfgparts[@]:3}"; do
                [ -n "$tok" ] || continue
                case $tok in
                    img=*)
                        if [ "$tok" != "img=$IMG_DIGEST" ]; then
                            _fail "$arm: the driver reports $tok while this run handed it VLLM_IMG=$IMG_DIGEST (the digest of $IMG). Two images are two experiments"
                            return 1
                        fi
                        continue
                        ;;
                esac
                if _kv_ok "$tok" && ! _has_space "$tok"; then
                    cfg_extra+=("$tok")
                fi
            done
            emit row "$label" CONFIG \
                "arm=$arm" "img=$IMG" "img_digest=$IMG_DIGEST" \
                "model=$MODEL" "weights_sha256=$WEIGHTS_SHA256" \
                "util=$CELL_UTIL" "len=$CELL_LEN" "seqs=$CELL_SEQS" "kv=$CELL_KV" \
                "kernel_observed=$kernel" \
                "linear_backend=$(arm_backend "$arm")" \
                "checkpoint_quant=$CHECKPOINT_QUANT" \
                "kv_cache_memory_bytes=$KV_CACHE_BYTES" \
                "kv_pool_tokens=${pool:-unread}" \
                "${cfg_extra[@]}"
            if [ "$arm" = "B1" ]; then
                b1_config_line=$LAST_LINE
                b1_pool=$pool
            else
                b2_config_line=$LAST_LINE
                b2_pool=$pool
            fi
            # Everything else the driver printed for this arm, in file order.
            while IFS= read -r line; do
                case $(printf '%s' "$line" | cut -f3) in
                    CONFIG) continue ;;
                    REFUSED | DEGENERATE)
                        # Unreachable with one cell per invocation (the driver
                        # continues to the next cell after either), and it is
                        # not silently dropped if it ever happens: a REFUSED row
                        # owes checkpoint_quant and tries>=3, and a launch this
                        # run believed on the first attempt cannot honestly
                        # claim three.
                        _fail "$arm printed both a CONFIG row and a $(printf '%s' "$line" | cut -f3) row in one invocation. This run has no honest shape for that and will not guess one: $line"
                        return 1
                        ;;
                esac
                relay_row "$arm" "$line"
                if [ "$arm" = "B2" ]; then
                    case $(printf '%s' "$line" | cut -f3) in
                        n=*) b2_last_level=$LAST_LINE ;;
                    esac
                fi
            done <"$ARM_ROWS"
        else
            tries=${RUN_TRIES:-0}
            say "$arm did not come up in $tries attempts — recording the refusal (guideline 8)"
            why=$(refusal_reason "$arm" "$ARM_ROWS" "$ARM_LOG")
            case $why in
                *[Mm]arlin* | *verify_marlin_supported*)
                    if [ "$arm" = "B2" ]; then
                        say "NOTE: B2 died with a Marlin-worded message. AutoGPTQLinearMethod.__init__ calls verify_marlin_supported() unconditionally, before the kernel chooser runs (B2-CHECKPOINT.md, residual risk). That is a finding recorded as a refusal, not a setup error."
                    fi
                    ;;
            esac
            emit refused "$label" \
                "arm=$arm" "img=$IMG" "model=$MODEL" \
                "weights_sha256=$WEIGHTS_SHA256" \
                "linear_backend=$(arm_backend "$arm")" \
                "checkpoint_quant=$CHECKPOINT_QUANT" \
                "tries=$tries" \
                -- "$why"
            if [ "$arm" = "B2" ]; then
                b2_refused_line=$LAST_LINE
            fi
        fi
    done

    # ---- the verdict ------------------------------------------------------
    #
    # The rule, stated so a reader can disagree with it:
    #   * B2 has no CONFIG           -> unresolved. A backend that cannot
    #     implement the layer is evidence that the alternative is unavailable
    #     here, not that emulation is the cause. (The test enforces this.)
    #   * the two pools differ       -> unresolved. Different pools means the
    #     width gate dropped different rungs and the file compares schedulers.
    #   * the observed kernel is not the one asked for -> unresolved.
    #   * otherwise, over the widths BOTH arms ran: exllama (no mma.sync) faster
    #     everywhere -> supported; marlin faster everywhere -> refuted; mixed or
    #     no matched width -> unresolved. Sign agreement across every matched
    #     width is the whole criterion — this file has no null of its own, and
    #     one unreplicated pair is not licensed to call a margin.
    status=unresolved
    cited=$b1_config_line
    if [ "$b2_refused_line" -ne 0 ]; then
        cited=$b2_refused_line
        note "verdict-rule: B2 produced no CONFIG row, so this file shows no non-mma.sync path on this card rather than a cost for the one it has."
    elif [ "$b1_config_line" -ne 0 ] && [ "$b2_config_line" -ne 0 ]; then
        if [ -n "$b1_pool" ] && [ -n "$b2_pool" ] && [ "$b1_pool" = "$b2_pool" ]; then
            status=$(verdict_from_levels)
            note "verdict-rule: both arms held one checkpoint and one KV pool of $b1_pool tokens; status is the sign of B2-minus-B1 aggregate throughput where it agrees at every width both arms ran, and unresolved otherwise."
        else
            say "WARNING: the arms report KV pools '$b1_pool' and '$b2_pool'. Different pools compare two schedulers, not two kernels."
            note "verdict-rule: the two arms' KV pools differ, so their widths are not the same experiment and no throughput sign is read from them."
        fi
        if [ "$status" != "unresolved" ] && [ "$b2_last_level" -ne 0 ]; then
            cited=$b2_last_level
        elif [ "$b2_config_line" -ne 0 ]; then
            cited=$b2_config_line
        fi
    fi
    if [ "$cited" -eq 0 ]; then
        _fail "no row exists for the verdict to cite. A claim with no artifact is not a finding"
        return 1
    fi
    emit stamp VERDICT hypothesis=tensor-core-emulation "status=$status" "cited_line=$cited"

    emit end_stamp
    rig_assert_unchanged
    say "wrote $OUT"
}

# Aggregate throughput per (arm, width), read back out of the file this run just
# wrote — the same bytes the test will read, not a parallel tally.
verdict_from_levels() {
    awk -F'\t' '
        $3 ~ /^n=[0-9]+$/ {
            arm = ""; agg = ""; got = 0
            for (i = 4; i <= NF; i++) {
                if ($i ~ /^arm=/) arm = substr($i, 5)
                if ($i ~ /^agg=/) { agg = substr($i, 5) + 0; got = 1 }
            }
            if (arm != "" && got) { a[arm "|" substr($3, 3)] = agg; widths[substr($3, 3)] = 1 }
        }
        END {
            both = 0; up = 0; down = 0
            for (n in widths) {
                if (("B1|" n) in a && ("B2|" n) in a) {
                    both++
                    if (a["B2|" n] > a["B1|" n]) up++
                    else if (a["B2|" n] < a["B1|" n]) down++
                }
            }
            if (both == 0) print "unresolved"
            else if (up == both) print "supported"
            else if (down == both) print "refuted"
            else print "unresolved"
        }
    ' "$OUT"
}

# Guarded so the functions above can be sourced and exercised on their own;
# executing the file runs the campaign step.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    while [ "$#" -gt 0 ]; do
        case $1 in
            --dry-run) DRY_RUN=1 ;;
            -h | --help)
                usage
                exit 0
                ;;
            *)
                usage >&2
                printf '\nunknown argument: %s\n' "$1" >&2
                exit 2
                ;;
        esac
        shift
    done

    if [ "$DRY_RUN" -eq 1 ]; then
        plan
        exit 0
    fi

    main
fi
