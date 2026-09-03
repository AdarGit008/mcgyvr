#!/usr/bin/env bash
# tools/runs/campaigns/srv1-kernel-arms/5-correctness.sh — campaign step 5, and the only producer of
# `records/evidence/2026-09-02-srv1-kernel-arms/correctness.json`.
# Behaviour 11, `tests/test_a_faster_arm_that_answers_differently_has_not_won.py`.
#
# WHY THIS EXISTS
# ---------------
# The arms deliberately run different kernels. Different reduction order gives
# different logits, and the 2026-09-01 A/B already shows the symptom: same
# prompts, `temperature: 0`, and yet `otok` 214 against 221 on one cell with
# `early_stop` 3/4 against 2/4. The arms did different amounts of work and
# nothing checked whether they did the same *work*. A faster arm that answers
# differently has not won — it has computed something else.
#
# Guideline 9: score with what exists. No diff harness is written here.
#   tools/breadth/measure.py --endpoint ... --protocol openai --tier bench-py
#     drives the 257-problem paired corpus through the production gate
#   tools/bench/null.py
#     compares two runs by `candidate_sha256`, separating SAMPLER drift
#     (different bytes) from ACCEPTANCE drift (identical bytes scoring
#     differently). Only one of those is survivable.
#   tools/bench/responsiveness.py:wilson
#     the campaign's one Wilson implementation — the bound is the 95% upper
#     limit on d/n, never `d/n` itself, because a bound of 0.00pp would claim
#     the instrument is exact and 257 cells cannot establish that.
#
# EVERY ARM PRICES ITS OWN NULL FIRST. `tools/bench/reproducibility.json`
# declares that a bound describes a run only when model, tier, gate_rungs,
# **serving_build** and cells all match it, and every arm in this campaign is a
# new `serving_build`. So no committed bound covers any of them, and this script
# measures two identical runs per arm before any arm is compared to any other.
# That is the whole reason for the second RED test: a bound borrowed across
# builds is a wrong published effect.
#
# `null.py`'s CLI walks both bench tiers at once; this reads its `compare()`
# instead, so one tier can be scored on its own exactly as guideline 9 names it.
# It is the same function, not a second implementation of it.
#
# THE VERDICTS ARE THE LADDER'S, AND ONLY THE LADDER'S. `verdicts[]` names the
# speed winner read out of `srv1-lcpp-arms.tsv` — the controlled study, one
# variable per rung, inside one engine — through `tools/runs/rows.py`, the one
# parser. `srv1-vllm-arms.tsv` is deliberately NOT read: guideline 5 makes B1 vs
# B2 a capability probe and not a ranking, and importing a "winner" from it
# would put a rank on a file that exists to say what the card can do. If the
# arm this file names as fastest was never scored here, the test fails — that
# is the behaviour working, not a bug to route around.
#
# Nothing here fabricates. An arm whose build nothing recorded is refused rather
# than given a plausible string (ADR-0024: a serving build that nothing recorded
# has already moved results twice), and a bound is never written for a
# comparison that shared no cells.
#
# THE STEP SERVES ITS OWN ARMS. Until 2026-09-02 this script took
# `--arm ARM=ENDPOINT=BUILD` and measured whatever answered at ENDPOINT, and
# nothing in the campaign started that server: run.sh is the one executable
# allowed to start a container on a rig, and only the step it starts may do so
# on its behalf. So the endpoints were nobody's job and the step could not run
# at all. Now `--arm ARM=IMAGE`: the tag is resolved to a digest ONCE before
# anything starts (gate 3), one container per arm runs as `<RUN_ID>-<ARM>` (so
# gate 7 finds a leftover), on one host port, one arm at a time — the card
# holds one — and is removed before the next arm comes up. `serving_build` in
# correctness.json is `llama.cpp@<tag>@<digest>`, the vocabulary step 6 writes,
# never a string the caller typed.
#
# Usage:
#   tools/runs/campaigns/srv1-kernel-arms/5-correctness.sh [--dry-run] \
#       --gguf /data/models/dense/Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf \
#       --model qwen2.5-coder-1.5b --reference L0 \
#       --arm L0=llamacpp:b10644-L0 --arm L2=llamacpp:b10644-L2 \
#       --arm L3=llamacpp:b10644-L3
#
#   --arm ARM=IMAGE   ARM matches [ABL][0-9], the campaign's one arm vocabulary.
#                     IMAGE is the tag the arm was built and stamped as; the
#                     step resolves it to a digest and serves that. An endpoint
#                     here is refused: a server this step did not start is one
#                     the door did not start.
#   --gguf PATH       the checkpoint every arm serves. Required, must exist:
#                     a wrong path would be measured silently.
#   --reference ARM   the arm every other arm's drift is measured from.
#   --model NAME      the served name (llama-server --alias) measure.py
#                     dispatches to. Every arm in one invocation serves the SAME
#                     checkpoint under the SAME name in the SAME engine: a drift
#                     measured across engines is guideline 5's forbidden row
#                     wearing a correctness hat.
#   --arms-tsv PATH   the serve step's srv1-lcpp-arms.tsv the verdicts are read
#                     from (default: the one beside this run's artifact). An
#                     input: the door's envelope is dated, and a step 5 run on
#                     a later day than step 4 has no such file beside it.
#   --port N          host port the one container listens on (default 8081).
#   --ctx N           llama-server -c (default 4096; bench-py prompts are
#                     ~700 tokens and the reply cap is 768).
#   --tier TIER       default bench-py (guideline 9's tier).
#   --draws N         sampled draws per task, default 1. Only the greedy arm is
#                     read here; this is the floor the instrument will run at.
#   --api-key-env NAME  passed through to measure.py. The NAME, never the key.
#   --dry-run         print every command line, in order, and exit.
#
# Environment: RUN_HOST RUN_REPO RUN_RETRY_SLEEP — see tools/runs/_common.sh
#
# Through the door only (tools/runs/run.sh): RUN_ID names the run and the
# artifact lands in $RUN_OUT_DIR beside the ladder it reads its verdict from.
# RUN_ARTIFACTS: correctness.json

[ -n "${RUN_ID:-}" ] || { echo "5-correctness.sh: RUN_ID is unset — start me through tools/runs/run.sh" >&2; exit 2; }

set -euo pipefail

_here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=./_common.sh disable=SC1091
. "$_here/../../_common.sh"
door_required

ARTIFACT="correctness.json"
MEASURE="tools/breadth/measure.py"

TIER="bench-py"
DRAWS="1"
MODEL=""
GGUF=""
ARMS_TSV=""
REFERENCE=""
API_KEY_ENV=""
PORT=8081
CTX=4096
HEALTH_TRIES=90
DRY_RUN=0
STAMP=""
DOCKER=${RUN_DOCKER:-docker}

ARMS=()
IMAGES=()
DIGESTS=()
ENDPOINTS=()
BUILDS=()
MEASURED=()

# --------------------------------------------------------------------------
# the scorer
#
# Reads the run directories measure.py just filled, prices each arm's own null
# through null.compare(), and writes correctness.json. Printed in full by
# --dry-run. It refuses rather than rounds: no shared cells, no bound.
# --------------------------------------------------------------------------

SCORE_PY=$(
cat <<'PY'
import json
import pathlib
import sys

spec = json.loads(sys.stdin.read())
root = pathlib.Path(spec["root"])
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "tools" / "bench"))

# The campaign's own instruments. null.py fixes up sys.path for mode/product/
# mde/responsiveness itself when it is imported.
import null as nullmod  # noqa: E402
from responsiveness import wilson  # noqa: E402

from tools.runs.rows import read as read_sweep  # noqa: E402

tier = spec["tier"]
measurements = root / "records" / "measurements"


def manifest(run):
    path = measurements / run / tier / "run.json"
    if not path.is_file():
        sys.exit(f"{path} does not exist; the run it describes was never completed.")
    return json.loads(path.read_text(encoding="utf-8"))


# null.py's own doctrine, applied here because compare() is being called
# directly: two runs scored by different bars disagree about the scorer, and a
# null read across that boundary reports the grader as instrument noise.
bars = {}
for arm in spec["arms"]:
    for run in (arm["run_a"], arm["run_b"]):
        bars[run] = tuple(manifest(run).get("gate_rungs") or ())
if len(set(bars.values())) != 1:
    sys.exit(
        "these runs were scored by different bars, so their disagreement is the "
        "scorer and not the model's drift: "
        + json.dumps({k: list(v) for k, v in bars.items()}, sort_keys=True)
    )
gate_rungs = list(next(iter(bars.values())))

# ADR-0024. Where the endpoint answers, the recorded build decides; a
# declaration that contradicts it is not quietly preferred.
for arm in spec["arms"]:
    for run in (arm["run_a"], arm["run_b"]):
        recorded = manifest(run).get("serving_build")
        if recorded and recorded != arm["serving_build"]:
            sys.exit(
                f"{arm['arm']}: {run}/{tier}/run.json recorded serving_build "
                f"{recorded!r} and this invocation declared "
                f"{arm['serving_build']!r}. One of them describes a different "
                "machine than the rows do."
            )


def paired(run_a, run_b, what):
    cmp = nullmod.compare(tier, run_a, run_b)
    n = len(cmp["shared"])
    if n == 0:
        sys.exit(
            f"{what}: {run_a} and {run_b} share no cell, so there is no "
            "denominator and no bound. A rate over nothing is not a rate."
        )
    return cmp, n


reference = next(a for a in spec["arms"] if a["arm"] == spec["reference"])
ref_cmp, ref_n = paired(
    reference["run_a"], reference["run_b"], f"{reference['arm']} self-null"
)

out_arms = []
for arm in spec["arms"]:
    is_ref = arm["arm"] == spec["reference"]
    self_cmp, self_n = paired(
        arm["run_a"], arm["run_b"], f"{arm['arm']} self-null"
    )
    self_flips = len(self_cmp["flips"])
    self_null = {
        "serving_build": arm["serving_build"],
        "cells": self_n,
        "bound_pp": round(wilson(self_flips, self_n)[1] * 100, 2),
        "flips": self_flips,
        "acceptance_drift": len(self_cmp["acceptance_flips"]),
        "runs": [f"{arm['run_a']}/{tier}", f"{arm['run_b']}/{tier}"],
        "_bound": (
            "95% Wilson upper limit on flips/cells, measured on THIS arm's own "
            "build. reproducibility.json keys a bound on serving_build and "
            "every arm here is a new one, so no committed bound covers it."
        ),
    }
    if is_ref:
        # Drift is measured FROM this arm, so the honest number in its own row
        # is the drift it shows against itself — the same two runs the bound
        # came from, not a zero asserted by construction.
        drift_flips = self_flips
        drift_n = self_n
        acceptance = len(self_cmp["acceptance_flips"])
        against = self_null["runs"]
    else:
        cmp, drift_n = paired(
            reference["run_a"], arm["run_a"], f"{arm['arm']} vs the reference"
        )
        drift_flips = len(cmp["flips"])
        acceptance = len(cmp["acceptance_flips"])
        against = [f"{reference['run_a']}/{tier}", f"{arm['run_a']}/{tier}"]
    entry = {
        "arm": arm["arm"],
        "image": arm.get("image"),
        "measured_backend": arm.get("measured_backend"),
        "endpoint": arm["endpoint"],
        "serving_build": arm["serving_build"],
        "cells": drift_n,
        "drift_pp": round(drift_flips / drift_n * 100, 2),
        "flips": drift_flips,
        "acceptance_drift": acceptance,
        "is_reference": is_ref,
        "self_null": self_null,
        "compared_runs": against,
    }
    out_arms.append(entry)

# The speed verdict, read out of the controlled study only. srv1-vllm-arms.tsv
# is not read: B1 vs B2 is a capability probe, not a ranking (guideline 5).
verdicts = []
lcpp = root / spec["lcpp_arms"]
if lcpp.is_file():
    sweep = read_sweep(lcpp)
    agg = {}
    for row in sweep.levels():
        name = row.fields.get("arm")
        if not name or "agg" not in row.fields:
            continue
        agg.setdefault((name, row.n), []).append(float(row.fields["agg"]))
    seen = sorted({a for a, _ in agg})
    widths = sorted({n for _, n in agg})
    common = [w for w in widths if all((a, w) in agg for a in seen)]
    if seen and common:
        means = {
            a: sum(sum(agg[(a, w)]) / len(agg[(a, w)]) for w in common) / len(common)
            for a in seen
        }
        winner = max(means, key=lambda a: means[a])
        verdicts.append(
            {
                "question": "which llama.cpp build should srv1 serve on",
                "winner": winner,
                "basis": (
                    "highest mean aggregate throughput over the widths every arm "
                    f"ran (n={','.join(str(w) for w in common)}) in "
                    f"{spec['lcpp_arms']}"
                ),
                "mean_agg_tok_s": {a: round(means[a], 2) for a in seen},
            }
        )
    else:
        print(
            f"note: {spec['lcpp_arms']} holds no width every arm ran, so no "
            "winner is named from it.",
            file=sys.stderr,
        )
else:
    print(
        f"note: {spec['lcpp_arms']} does not exist yet, so this file names no "
        "speed winner. Re-run after step 4 to bind the verdict to the rows.",
        file=sys.stderr,
    )

result = {
    "record": "srv1-kernel-arms/correctness/1",
    "model": spec["model"],
    "tier": tier,
    "gate_rungs": gate_rungs,
    "reference": spec["reference"],
    "arms": out_arms,
    "verdicts": verdicts,
}
out = root / spec["out"]
out.write_text(json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8")
print(f"wrote {out}", file=sys.stderr)
PY
)

# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------

usage() {
    sed -n '/^# Usage:/,/^# Environment/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

say() {
    printf 'srv1-correctness: %s\n' "$*" >&2
}

show() {
    printf '+ %s\n' "$*"
}

run_dir() {
    printf 'srv1-correct-%s-%s-%s' "$STAMP" "$1" "$2"
}

# One builder, so --dry-run cannot drift from what runs.
MEASURE_ARGV=()
measure_argv() {
    local arm half endpoint out
    arm=$1
    half=$2
    endpoint=$3
    out="records/measurements/$(run_dir "$arm" "$half")/$TIER"
    MEASURE_ARGV=(
        uv run --no-sync --quiet python "$MEASURE"
        --out "$out"
        --endpoint "$endpoint"
        --protocol openai
        --model "$MODEL"
        --tier "$TIER"
        --draws "$DRAWS"
    )
    if [ -n "$API_KEY_ENV" ]; then
        MEASURE_ARGV+=(--api-key-env "$API_KEY_ENV")
    fi
}

measure_cmdline() {
    measure_argv "$@" || return 1
    printf '%s' "${MEASURE_ARGV[*]}"
}

# --------------------------------------------------------------------------
# argument handling
# --------------------------------------------------------------------------

add_arm() {
    local spec name image
    spec=$1
    name=${spec%%=*}
    image=${spec#*=}
    # An endpoint (scheme, or a bare host:port) or a third field is refused;
    # a registry with a port (`localhost:5000/img:tag`) and a digest are images.
    if [ -z "$image" ] || [[ $image == *=* || $image == *://* || $image =~ ^[^/]+:[0-9]+$ ]]; then
        _fail "--arm wants ARM=IMAGE; got '$1'. This step starts the server it measures (run.sh is the one door, and only the step it started may start a container), so an endpoint or a build typed here names a server nobody in the campaign started"
        return 1
    fi
    [ -n "$name" ] && [ "$name" != "$spec" ] || {
        _fail "--arm wants ARM=IMAGE; got '$1'"
        return 1
    }
    # The campaign's one arm vocabulary, ARM_PREFIX [ABL][0-9] (tools/runs/rows.py)
    # — the same check the TSV labels pass, so an arm named here is an arm the
    # speed artifacts can be matched to.
    arm_label "$name" "$TIER" >/dev/null || return 1
    ARMS+=("$name")
    IMAGES+=("$image")
}

# --------------------------------------------------------------------------
# the servers — one per arm, one at a time, named for the run
# --------------------------------------------------------------------------

# Gate 3, once for every arm before any container: the tag becomes a digest,
# and the digest is what runs. An image this daemon does not hold is a refusal
# of the whole step, not of one arm — a drift table with a hole in it names a
# winner it never scored.
resolve_images() {
    local i digest
    for i in "${!ARMS[@]}"; do
        digest=$(image_digest "${IMAGES[$i]}") || return 1
        DIGESTS[$i]=$digest
        ENDPOINTS[$i]="http://127.0.0.1:$PORT"
        BUILDS[$i]="llama.cpp@${IMAGES[$i]}@$digest"
    done
}

container_of() {
    printf '%s-%s' "$RUN_ID" "$1"
}

LAUNCH_ARGV=()
launch_argv() {
    local arm=$1 digest=$2 model_dir model_base
    model_dir=$(cd -- "$(dirname -- "$GGUF")" 2>/dev/null && pwd) || model_dir=$(dirname -- "$GGUF")
    model_base=$(basename -- "$GGUF")
    LAUNCH_ARGV=(
        docker run -d --name "$(container_of "$arm")" --runtime=nvidia --gpus all
        -v "$model_dir:/models:ro" -p "127.0.0.1:$PORT:$PORT" "$digest"
        -m "/models/$model_base" --alias "$MODEL" --host 0.0.0.0 --port "$PORT"
        -c "$CTX" -ngl 99 --parallel 1
    )
}

teardown_arm() {
    "$DOCKER" rm -f "$(container_of "$1")" >/dev/null 2>&1 || true
}

teardown_all() {
    local arm
    for arm in "${ARMS[@]}"; do
        teardown_arm "$arm"
    done
}

# The backend the served container can actually reach, against the image's
# declared one. A3 on 2026-09-02 declared vulkan and ran the CPU; a drift
# measured on the wrong device and filed under the image's name is the same
# defect here. llama-server prints no `load_backend:` line at its default
# verbosity (the first run of this check, 2026-09-03, read nothing from a
# healthy L0 and refused it), so the probe is `llama-server --list-devices`
# exec'd in the running container: `CUDA0: ...` / `Vulkan0: ...`, or nothing.
LOADED_BACKENDS=
served_backend_ok() {
    local name=$1 digest=$2 declared
    LOADED_BACKENDS=$("$DOCKER" exec "$name" /app/llama-server --list-devices 2>&1 |
        sed -n 's/^[[:space:]]*\([A-Za-z]*\)[0-9][0-9]*:[[:space:]].*/\1/p' | sort -u | paste -sd, -)
    declared=$("$DOCKER" image inspect --format '{{index .Config.Labels "org.mcgyvr.build.backend"}}' "$digest") || {
        _fail "the backend $digest declares (org.mcgyvr.build.backend) could not be read from the daemon; nothing checks what served, so nothing is measured"
        return 1
    }
    backend_verdict "$declared" "${LOADED_BACKENDS:-unreported}"
}

# Up, then answering /health, then serving the declared backend — or gone. The
# container's log is the reason.
launch_arm() {
    local arm=$1 digest=$2 i code name
    name=$(container_of "$arm")
    teardown_arm "$arm"
    launch_argv "$arm" "$digest"
    say "${LAUNCH_ARGV[*]}"
    if ! "$DOCKER" "${LAUNCH_ARGV[@]:1}" >/dev/null; then
        "$DOCKER" logs "$name" 2>&1 | tail -n 5 >&2 || true
        return 1
    fi
    i=0
    while [ "$i" -lt "$HEALTH_TRIES" ]; do
        i=$((i + 1))
        code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" || true)
        if [ "$code" = "200" ]; then
            served_backend_ok "$name" "$digest" || return 1
            return 0
        fi
        if ! "$DOCKER" inspect -f '{{.State.Running}}' "$name" 2>/dev/null | grep -q true; then
            break
        fi
        sleep 2
    done
    "$DOCKER" logs "$name" 2>&1 | tail -n 5 >&2 || true
    return 1
}

# --------------------------------------------------------------------------
# --dry-run
# --------------------------------------------------------------------------

plan() {
    local i arm
    cat <<EOF
# 5-correctness.sh --dry-run
# Nothing below is executed. No measurement directory is created and no
# artifact is written.
#
# artifact  : $RUN_OUT_DIR/$ARTIFACT
# model     : $MODEL
# tier      : $TIER   (guideline 9)
# reference : $REFERENCE
# arms      : ${ARMS[*]}
#
# Order matters: every arm's own null pair is measured BEFORE any arm is
# compared to any other. No committed bound in tools/bench/reproducibility.json
# covers these builds, so a borrowed one would be a wrong published effect.

EOF
    for i in "${!ARMS[@]}"; do
        arm=${ARMS[$i]}
        printf '## arm %s — %s served as %s at %s. Two identical runs: its own null.\n' \
            "$arm" "${IMAGES[$i]}" "${BUILDS[$i]}" "${ENDPOINTS[$i]}"
        launch_argv "$arm" "${DIGESTS[$i]}"
        show "${LAUNCH_ARGV[*]}"
        show "curl -m 5 http://127.0.0.1:$PORT/health   # until 200; at most $HEALTH_TRIES tries of up to 7 s, x3 through retry3"
        show "docker exec $(container_of "$arm") /app/llama-server --list-devices   # must list the backend the image declares (backend_verdict)"
        show "$(measure_cmdline "$arm" a "${ENDPOINTS[$i]}")"
        show "$(measure_cmdline "$arm" b "${ENDPOINTS[$i]}")"
        show "docker rm -f $(container_of "$arm")"
        echo
    done
    printf '## verdicts from %s\n' "$ARMS_TSV"
    cat <<EOF
## score: each arm's self-null, then every arm's drift from $REFERENCE
+ printf '<the arm table, as JSON>' | uv run --no-sync --quiet python -c "\$SCORE_PY"

##    where "\$SCORE_PY" is, verbatim:
EOF
    printf '%s\n' "$SCORE_PY" | sed 's/^/#     /'
}

# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

measure_once() {
    local arm half endpoint
    arm=$1
    half=$2
    endpoint=$3
    measure_argv "$arm" "$half" "$endpoint" || return 1
    say "${MEASURE_ARGV[*]}"
    "${MEASURE_ARGV[@]}"
}

main() {
    local root i arm spec_json out out_dir
    root=$(_repo_root) || return 1
    # The envelope: the door's $RUN_OUT_DIR (door_required refused without
    # it). Absolute, because the scorer joins it onto the root with pathlib
    # and an absolute right-hand side wins there.
    out_dir=$RUN_OUT_DIR
    [ -d "$out_dir" ] || { _fail "$out_dir is not a directory"; return 1; }

    # Guideline 9, in the order it is written: every arm prices its own null
    # first, and no arm is compared to any other until all of them have.
    trap teardown_all EXIT
    for i in "${!ARMS[@]}"; do
        arm=${ARMS[$i]}
        say "arm $arm — serving ${IMAGES[$i]} as ${DIGESTS[$i]} on :$PORT"
        if ! retry3 launch_arm "$arm" "${DIGESTS[$i]}"; then
            teardown_arm "$arm"
            _fail "arm $arm: ${IMAGES[$i]} did not come up healthy on :$PORT in ${RUN_TRIES:-0} attempts (its last lines are above). An arm that never served is an arm with no null, and this run writes nothing"
            return 1
        fi
        MEASURED[$i]=${LOADED_BACKENDS:-unreported}
        say "arm $arm — serving on ${MEASURED[$i]}"
        say "arm $arm — run a of its own null pair"
        if ! retry3 measure_once "$arm" a "${ENDPOINTS[$i]}"; then
            teardown_arm "$arm"
            _fail "arm $arm: measure.py did not complete run a in ${RUN_TRIES:-0} attempts. An arm with no null is an arm with no bound, and this run writes neither"
            return 1
        fi
        say "arm $arm — run b of its own null pair"
        if ! retry3 measure_once "$arm" b "${ENDPOINTS[$i]}"; then
            teardown_arm "$arm"
            _fail "arm $arm: measure.py did not complete run b in ${RUN_TRIES:-0} attempts. One run is not a null"
            return 1
        fi
        teardown_arm "$arm"
        say "arm $arm — container $(container_of "$arm") removed"
    done

    spec_json=$(
        {
            printf '{"root": "%s", "tier": "%s", "model": "%s", "reference": "%s",' \
                "$root" "$TIER" "$MODEL" "$REFERENCE"
            printf ' "out": "%s/%s", "lcpp_arms": "%s", "arms": [' \
                "$out_dir" "$ARTIFACT" "$ARMS_TSV"
            for i in "${!ARMS[@]}"; do
                [ "$i" -eq 0 ] || printf ','
                printf '{"arm": "%s", "image": "%s", "measured_backend": "%s", "endpoint": "%s", "serving_build": "%s", "run_a": "%s", "run_b": "%s"}' \
                    "${ARMS[$i]}" "${IMAGES[$i]}" "${MEASURED[$i]:-unreported}" "${ENDPOINTS[$i]}" "${BUILDS[$i]}" \
                    "$(run_dir "${ARMS[$i]}" a)" "$(run_dir "${ARMS[$i]}" b)"
            done
            printf ']}'
        }
    )
    out="$out_dir/$ARTIFACT"
    say "scoring: $out"
    printf '%s' "$spec_json" | (cd "$root" && uv run --no-sync --quiet python -c "$SCORE_PY")
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    while [ "$#" -gt 0 ]; do
        case $1 in
            --dry-run) DRY_RUN=1 ;;
            --arm)
                shift
                [ "$#" -ge 1 ] || { _fail "--arm wants ARM=IMAGE"; exit 2; }
                add_arm "$1" || exit 2
                ;;
            --arm=*) add_arm "${1#--arm=}" || exit 2 ;;
            --gguf)
                shift
                GGUF=${1:-}
                ;;
            --gguf=*) GGUF=${1#--gguf=} ;;
            --arms-tsv)
                shift
                ARMS_TSV=${1:-}
                ;;
            --arms-tsv=*) ARMS_TSV=${1#--arms-tsv=} ;;
            --port)
                shift
                PORT=${1:-}
                ;;
            --port=*) PORT=${1#--port=} ;;
            --ctx)
                shift
                CTX=${1:-}
                ;;
            --ctx=*) CTX=${1#--ctx=} ;;
            --model)
                shift
                MODEL=${1:-}
                ;;
            --model=*) MODEL=${1#--model=} ;;
            --reference)
                shift
                REFERENCE=${1:-}
                ;;
            --reference=*) REFERENCE=${1#--reference=} ;;
            --tier)
                shift
                TIER=${1:-}
                ;;
            --tier=*) TIER=${1#--tier=} ;;
            --draws)
                shift
                DRAWS=${1:-}
                ;;
            --draws=*) DRAWS=${1#--draws=} ;;
            --api-key-env)
                shift
                API_KEY_ENV=${1:-}
                ;;
            --api-key-env=*) API_KEY_ENV=${1#--api-key-env=} ;;
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

    STAMP=$(date -u +%Y-%m-%d)

    [ "${#ARMS[@]}" -gt 0 ] || {
        usage >&2
        _fail "no --arm was given. This script measures arms; it does not know which ones exist" || exit 2
    }
    [ -n "$MODEL" ] || {
        _fail "--model is required. measure.py dispatches to a named model, and a run that cannot name it is not comparable to any other" || exit 2
    }
    [ -n "$GGUF" ] || {
        _fail "--gguf is required: this step serves the checkpoint it measures, and it will not guess which one" || exit 2
    }
    [ -f "$GGUF" ] || {
        _fail "--gguf $GGUF is not a file on this host; a wrong path would be served as nothing and measured silently" || exit 2
    }
    [ -n "$ARMS_TSV" ] || ARMS_TSV="$RUN_OUT_DIR/srv1-lcpp-arms.tsv"
    [ -f "$ARMS_TSV" ] || {
        _fail "--arms-tsv $ARMS_TSV is not a file. The verdicts are the ladder's (srv1-lcpp-arms.tsv, written by step 4); a run whose verdict source does not exist would score every arm and name no winner. Name the serve step's file, wherever its envelope is" || exit 2
    }
    for _n in "PORT=$PORT" "CTX=$CTX"; do
        case ${_n#*=} in
            '' | *[!0-9]*) _fail "--$(printf '%s' "${_n%%=*}" | tr '[:upper:]' '[:lower:]') is '${_n#*=}', which is not an integer" || exit 2 ;;
        esac
    done
    [ -n "$REFERENCE" ] || {
        _fail "--reference is required: drift is measured FROM one arm, and exactly one entry may be the reference" || exit 2
    }
    _found=0
    for _a in "${ARMS[@]}"; do
        if [ "$_a" = "$REFERENCE" ]; then
            _found=1
        fi
    done
    [ "$_found" -eq 1 ] || {
        _fail "--reference $REFERENCE is not among the arms (${ARMS[*]}). The reference must be scored like every other arm" || exit 2
    }

    command -v curl >/dev/null 2>&1 || {
        _fail "curl is not on PATH, and /health is how a served arm is told from a dead one; without it every launch would time out and be called unhealthy" || exit 2
    }

    # Gate 3 before the plan and before the run alike: a tag nobody can
    # resolve is refused here, with no container started and nothing written.
    resolve_images || exit 2

    if [ "$DRY_RUN" -eq 1 ]; then
        plan
        exit 0
    fi

    main
fi
