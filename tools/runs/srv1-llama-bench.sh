#!/usr/bin/env bash
#
# tools/runs/srv1-llama-bench.sh
#   -> records/evidence/2026-09-02-srv1-kernel-arms/srv1-llama-bench.tsv
#
# Campaign step 3 (`lcp-vllm-3-arm-run.md:117-118`):
#
#   3  bench  llama-bench -p 512,2048 -n 128 -r 9 -fa 0,1  x {L0,L1,L2,L3,L4,A3}
#
# This file is the INSTRUMENT RECORD. Guideline 3: `prefill=` from the sweep
# drivers is `pin/wall` over the same wall as `agg = gen/wall`, so `prefill/agg`
# is `ptok/otok` identically and says nothing about prompt processing. The only
# prefill verdict this campaign may quote comes from here, and from nothing
# else. `srv1-build-ladder.tsv` re-files one row per rung out of this file
# (ARTIFACT-CONTRACT.md §6.4); it is a projection, never a second measurement.
#
# Two properties are asserted here and nowhere else
# (test_a_prefill_verdict_needs_an_instrument_that_measures_prefill.py:52-71):
#
#   reps / stddev  the same build read 55.7 t/s at -r 3 and 86.4 t/s at -r 9.
#                  `reps` is COUNTED from the sample array llama-bench reports,
#                  not copied off the -r flag: a flag records what was asked
#                  for, and this column has to record what was done.
#   fa=0 and fa=1  the arch change moves ggml_cuda_get_best_fattn_kernel on the
#                  same turing_mma_available test that moves MMQ. One number
#                  for both attributes the gain to whichever kernel the reader
#                  already believed in.
#
# What lands in the artifact (ARTIFACT-CONTRACT.md §5.4):
#   ### TOOL name=llama-bench                                       (§2.10)
#   ### WORKLOAD digest=none comparable_with=microbenchmark-only    (§2.1, §6.4)
#   ### START / ### RIG / ### END                                   (guideline 7)
#   BENCH rows: arm= fa= pp= tg= reps= stddev= ...
#   REFUSED rows where a tool or a launch was missing                (guideline 8)
#
# NO `n=<int>` rows are emitted, so `sweep.levels()` is empty and
# `sweep.levels() or of_kind("BENCH")` resolves to the BENCH rows (§5.4).
#
# It runs ON the rig, because ### START / ### RIG / ### END describe the machine
# this process is reading and a stamp taken over ssh would name the wrong box.
#
#   RUN_ARMS         arms to bench.        default "L0 L1 L2 L3 L4 A3"
#   RUN_TAG_PREFIX   image tag prefix.     default llamacpp:b10644-
#   RUN_MODELS_DIR   mounted at /models.   default $HOME/models
#   RUN_MODEL        model, relative to RUN_MODELS_DIR
#   RUN_PP / RUN_TG / RUN_REPS / RUN_FA / RUN_NGL   the step-3 command line
#   RUN_HOST / RUN_REPO / RUN_RETRY_SLEEP           read by tools/runs/_common.sh
#
# Flags:
#   --dry-run     print the exact command line for every cell, execute nothing,
#                 read nothing off the rig, write no file.
#   --out PATH    write somewhere other than the contract path (for rehearsal).

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./_common.sh
# shellcheck disable=SC1091  # sourced at runtime from the script's own directory
. "$HERE/_common.sh"

ARTIFACT=srv1-llama-bench.tsv
RUN_REL=records/evidence/2026-09-02-srv1-kernel-arms

TAG_PREFIX=${RUN_TAG_PREFIX:-llamacpp:b10644-}
MODELS_DIR=${RUN_MODELS_DIR:-$HOME/models}
MODEL=${RUN_MODEL:-dense/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf}
PP=${RUN_PP:-512,2048}
TG=${RUN_TG:-128}
REPS=${RUN_REPS:-9}
FA=${RUN_FA:-0,1}
NGL=${RUN_NGL:-99}

DRY_RUN=0
OUT=

usage() {
    sed -n '2,52p' "${BASH_SOURCE[0]}" | sed 's/^#\{1,2\} \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
    case $1 in
        --dry-run) DRY_RUN=1 ;;
        --out)
            [ "$#" -ge 2 ] || { _fail "--out needs a path"; exit 2; }
            OUT=$2
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            _fail "unknown argument '$1'. See --help"
            exit 2
            ;;
    esac
    shift
done

ROOT=$(_repo_root)
[ -n "$OUT" ] || OUT="$ROOT/$RUN_REL/$ARTIFACT"

read -r -a ARM_LIST <<<"${RUN_ARMS:-L0 L1 L2 L3 L4 A3}"

TMP=
cleanup() {
    if [ -n "$TMP" ] && [ -d "$TMP" ]; then rm -rf "$TMP"; fi
    return 0
}
trap cleanup EXIT

# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------

say() { printf '# %s\n' "$*" >&2; }

plan() {
    local q
    q=$(printf '%q ' "$@")
    printf '+ %s\n' "${q% }"
}

dry() { [ "$DRY_RUN" -eq 1 ]; }

# Every artifact line goes through here. Under --dry-run nothing is written and
# nothing is read off the rig: the numbers do not exist yet, and a placeholder
# where a measurement belongs is the one unacceptable output.
emit() {
    if dry; then return 0; fi
    "$@" >>"$OUT"
}

tag_of() { printf '%s%s' "$TAG_PREFIX" "$1"; }

# A3 is the Vulkan arm; it reaches the card through the driver's ICD rather than
# through CUDA, so it needs the driver's display capability inside the container.
docker_args() {
    local arm=$1
    printf '%s\n' --rm --gpus all
    if [ "$arm" = A3 ]; then
        printf '%s\n' -e NVIDIA_DRIVER_CAPABILITIES=all
    fi
    printf '%s\n' -v "$MODELS_DIR:/models:ro"
}

# The step-3 command line, verbatim from lcp-vllm-3-arm-run.md:117-118.
bench_cmd() {
    local arm=$1 tag
    tag=$(tag_of "$arm")
    local args=()
    mapfile -t args < <(docker_args "$arm")
    printf '%s\n' docker run "${args[@]}" --entrypoint /app/llama-bench "$tag" \
        -m "/models/$MODEL" -p "$PP" -n "$TG" -r "$REPS" -fa "$FA" -ngl "$NGL" -o json
}

# --------------------------------------------------------------------------
# reading llama-bench's own report
# --------------------------------------------------------------------------
#
# `-o json` and not `-o csv`, for one reason: the JSON carries `samples_ts`, so
# the repetition count on every row is COUNTED rather than copied off the `-r`
# flag. Everything the parser cannot read honestly it refuses to print, and the
# caller turns that into a REFUSED row.

write_parser() {
    cat >"$TMP/parse.py" <<'PY'
"""One llama-bench JSON report -> one line per (fa, prompt length) row.

Prints `<cell> k=v k=v ...`, whitespace-free, ready for tools/runs/_common.sh's
`row`. Exits non-zero with a message rather than printing a value it could not
read: a fabricated measurement is the single unacceptable output.
"""

import json
import sys


def die(msg):
    sys.exit(f"llama-bench report {path}: {msg}")


def tok(v):
    return "_".join(str(v).split())


def num(entry, key):
    if key not in entry:
        die(f"an entry has no {key!r}: {sorted(entry)[:12]}")
    try:
        return float(entry[key])
    except (TypeError, ValueError):
        die(f"{key}={entry[key]!r} is not a number")


def as_int(entry, key):
    return int(num(entry, key))


def fa_of(entry):
    for key in ("flash_attn", "fa"):
        if key in entry:
            v = entry[key]
            break
    else:
        die("an entry names no flash_attn; -fa 0,1 coverage cannot be read")
    if isinstance(v, bool):
        return "1" if v else "0"
    s = str(v).strip().lower()
    if s in ("1", "true", "on", "enabled", "yes"):
        return "1"
    if s in ("0", "false", "off", "disabled", "no"):
        return "0"
    die(f"flash_attn={v!r} is neither on nor off; the row cannot name its kernel")


def reps_of(entry):
    for key in ("samples_ts", "samples_ns"):
        v = entry.get(key)
        if isinstance(v, list) and v:
            return len(v)
    die(
        "an entry reports no samples_ts/samples_ns array. reps= must be the "
        "number of repetitions performed, never the number requested on -r"
    )


path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    report = json.load(fh)
if isinstance(report, dict):
    report = report.get("results", report.get("entries"))
if not isinstance(report, list) or not report:
    die("holds no list of results")

prompts, gens = {}, {}
for entry in report:
    fa = fa_of(entry)
    n_prompt, n_gen = as_int(entry, "n_prompt"), as_int(entry, "n_gen")
    if n_prompt and not n_gen:
        prompts.setdefault(fa, {})[n_prompt] = entry
    elif n_gen and not n_prompt:
        gens.setdefault(fa, {})[n_gen] = entry

if not prompts:
    die("holds no prompt-processing entry, which is the whole point of step 3")

for fa in sorted(prompts):
    if fa not in gens:
        die(f"-fa {fa} produced no token-generation entry; every row owes a tg=")
    n_gen, tg = sorted(gens[fa].items())[0]
    for n_prompt, pp in sorted(prompts[fa].items()):
        fields = [
            f"p{n_prompt}",
            f"fa={fa}",
            f"pp={num(pp, 'avg_ts')}",
            f"tg={num(tg, 'avg_ts')}",
            f"reps={reps_of(pp)}",
            f"stddev={num(pp, 'stddev_ts')}",
            f"tg_reps={reps_of(tg)}",
            f"tg_stddev={num(tg, 'stddev_ts')}",
            f"pp_tokens={n_prompt}",
            f"n_tokens={n_gen}",
        ]
        for key, name in (
            ("model_filename", "model"),
            ("model_type", "model_type"),
            ("build_commit", "build_commit"),
            ("n_gpu_layers", "ngl"),
        ):
            value = pp.get(key)
            if value in (None, ""):
                continue
            if key == "model_filename":
                value = str(value).replace("\\", "/").rsplit("/", 1)[-1]
            fields.append(f"{name}={tok(value)}")
        line = " ".join(fields)
        if len(line.split()) != len(fields):
            die(f"a value carried whitespace: {line!r}")
        print(line)
PY
}

# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

# A reason for the tail channel: no TAB, and a first word the parser will not
# eat as a `key=value` field (§1.3).
clean_reason() {
    printf '%s' "$*" | tr '\t\n' '  ' | tr -s ' ' | cut -c1-400
}

bench_arm() {
    local arm=$1 tag json cell line reason
    tag=$(tag_of "$arm")
    local cmd=()
    mapfile -t cmd < <(bench_cmd "$arm")

    say "$arm: llama-bench on $tag"
    plan "${cmd[@]}"
    if dry; then
        say "$arm: would file $(printf '%s' "$PP" | tr ',' ' ' | wc -w) prompt lengths x $(printf '%s' "$FA" | tr ',' ' ' | wc -w) -fa values as BENCH rows"
        return 0
    fi

    # The blocker the run doc flags: `server-cuda-b10644` may ship no
    # llama-bench, and a locally built image can miss the target too. Checked
    # before the model is loaded, retried because guideline 8 asks for three.
    if ! retry3 docker run --rm --entrypoint test "$tag" -x /app/llama-bench; then
        emit refused "$(arm_label "$arm" "p${PP%%,*}")" \
            "arm=$arm" "img=$tag" "checkpoint_quant=unread" \
            -- "the image $tag holds no executable /app/llama-bench, so this arm has no prefill instrument and no prefill number may be quoted for it"
        say "$arm: no llama-bench in the image. Refused, not synthesised."
        return 0
    fi

    json=$TMP/$arm.json
    if ! retry3 run_bench "$arm" "$json"; then
        reason=$(clean_reason "$(tail -n 3 "$TMP/$arm.err" 2>/dev/null || true)")
        emit refused "$(arm_label "$arm" "p${PP%%,*}")" \
            "arm=$arm" "img=$tag" "checkpoint_quant=unread" \
            -- "llama-bench on $arm failed ${RUN_TRIES:-3} times and measured nothing; its last words were: ${reason:-(it printed nothing at all)}"
        say "$arm: llama-bench refused. Recorded as a result (guideline 8)."
        return 0
    fi

    # An unreadable report is not a refusal: llama-bench ran, and retrying a
    # deterministic parse three times would only make `tries=3` a lie. It is a
    # cell with nothing filed, which is what SKIP means (§1.4) — and SKIP is the
    # one kind exempt from the per-row rules, so it claims nothing either.
    if ! "${PY[@]}" "$TMP/parse.py" "$json" >"$TMP/$arm.rows" 2>"$TMP/$arm.perr"; then
        reason=$(clean_reason "$(cat "$TMP/$arm.perr")")
        emit row "$(arm_label "$arm" "p${PP%%,*}")" SKIP \
            -- "the $arm report could not be read honestly and no row was written from it: ${reason:-(the parser said nothing)}"
        say "$arm: unreadable report. Skipped rather than half-parsed."
        return 1
    fi

    while read -r cell line; do
        [ -n "$cell" ] || continue
        # Every token is whitespace-free by construction (the parser checks),
        # so this split is the intent.
        # shellcheck disable=SC2086
        emit row "$(arm_label "$arm" "$cell")" BENCH "arm=$arm" "img=$tag" $line
    done <"$TMP/$arm.rows"
    say "$arm: $(wc -l <"$TMP/$arm.rows") BENCH rows"
}

run_bench() {
    local arm=$1 json=$2
    local cmd=()
    mapfile -t cmd < <(bench_cmd "$arm")
    "${cmd[@]}" >"$json" 2>"$TMP/$arm.err"
}

preflight() {
    local missing=0
    if [ ! -f "$MODELS_DIR/$MODEL" ]; then
        say "BLOCKER: no model at $MODELS_DIR/$MODEL (set RUN_MODELS_DIR/RUN_MODEL)"
        missing=1
    fi
    if ! command -v docker >/dev/null 2>&1; then
        say "BLOCKER: docker is not on PATH; the arms are images"
        missing=1
    fi
    if [ "$missing" -eq 0 ]; then return 0; fi
    if dry; then
        say "a real run stops here rather than benching something it cannot name."
        return 0
    fi
    _fail "step 3 cannot run: see the BLOCKER lines above. Nothing was written"
    return 1
}

# python for the report parser. The system interpreter if there is one, else
# the repo's, which tools/runs/_common.sh already depends on.
choose_python() {
    if command -v python3 >/dev/null 2>&1; then
        PY=(python3)
    elif command -v uv >/dev/null 2>&1; then
        PY=(uv run --quiet python)
    else
        _fail "no python3 and no uv: llama-bench's JSON report cannot be read, and a hand-parsed throughput number is a guess"
        return 1
    fi
}

main() {
    local arm

    say "artifact: $OUT"
    say "arms: ${ARM_LIST[*]}   model: $MODELS_DIR/$MODEL"
    say "cells: -p $PP -n $TG -r $REPS -fa $FA -ngl $NGL"
    if dry; then say "--dry-run: printing the plan, reading no rig, writing no file"; fi

    preflight || return 1

    if ! dry; then
        choose_python || return 1
        TMP=$(mktemp -d)
        write_parser
        mkdir -p "$(dirname "$OUT")"
        : >"$OUT"
    fi

    # §2.10 — the stamp that says a prefill verdict came from an instrument that
    # times prefill, and not from the sweep driver's ptok/otok ratio.
    emit stamp TOOL "name=llama-bench"
    # §2.1 / §6.4 — llama-bench shares no prompt, template or sampler with the
    # serving drivers. Neither microbenchmark file may claim the workload.
    emit microbench_stamp
    emit start_stamp
    emit rig_stamp

    for arm in "${ARM_LIST[@]}"; do
        bench_arm "$arm"
    done

    if dry; then
        say "then ### END + the start==end re-read (guideline 7)"
        return 0
    fi

    emit end_stamp
    rig_assert_unchanged
    say "done: $OUT"
    say "srv1-build-ladder.sh projects one row per rung out of this file; it"
    say "copies these numbers and never re-measures them (§6.4)."
}

main
