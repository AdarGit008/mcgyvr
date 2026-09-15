#!/usr/bin/env bash
# tools/runs/campaigns/quick-check-2026-09-15/_check.sh — the body every numbered step runs.
#
# A quick elimination check of one staged checkpoint (owner, 2026-09-15). The
# step starts llama-server as <RUN_ID>-server from hosts.json's image for this
# rig, resolved to a digest, then drives tools/breadth/measure.py over
# bench-py and bench-ts on the same 20 ids: 10 function_implementation and 10
# bug_fix, drawn by random.Random(20260915).sample over pinned_bench_ids() per
# task type. Greedy only (--draws 0), reply cap 2048. A server that never
# answers /health is the result, and the artifact says why.
#
# Thinking is off (owner, 2026-09-15, after LFM2.5 ran into the cap on 16 of 40
# replies): --reasoning-budget 0 and enable_thinking=false, a no-op on templates
# without a thinking mode. Rows go under <tag>-nothink/, so they never resume
# into the thinking-on rows measured before the switch.
#
# Usage: a numbered step declares its artifact and runs
#   exec bash _check.sh <artifact>.json <blob file name> "$@"
# and the door passes --model, the blob as the rig sees it.

[ -n "${RUN_ID:-}" ] || { echo "_check.sh: RUN_ID is unset — start a numbered step through the door: python -m mcgyvr.serving.run --host <srv1|srv2> --campaign quick-check-2026-09-15 --step <numbered step> --model <blob> --parallel 1 --ctx-per-slot 8192" >&2; exit 2; }

set -euo pipefail

ARTIFACT=$1
EXPECTED=$2

# shellcheck source=../../_common.sh disable=SC1091
. "$RUN_ROOT/tools/runs/_common.sh"
door_required

if [ "$(basename -- "$RUN_MODEL")" != "$EXPECTED" ]; then
    _fail "--model $RUN_MODEL is not $EXPECTED, the blob this step is named for" || exit 2
fi

IDS=b007-cent-split,b030-date-span,b094-relay-chain,b258-lap-best,b345-hour-rate,b379-hide-values,b417-mark-list,b423-scan-tally,b488-root-digit,b496-span-letters,b033-till-session,b046-rest-harvest,b073-bump-release,b080-brace-fill,b112-net-tally,b200-fleet-hops,b266-span-merge,b281-tier-cost,b351-vat-back,b443-fold-ends
PORT=8090
CTX=8192
CAP=2048
HEALTH_TRIES=180
THINKING=off
TAG=${ARTIFACT%.json}
OUT_REL="records/measurements/quick-check-2026-09-15/$TAG-nothink"
NAME="$RUN_ID-server"

DOCKER=$(_door_shim docker) || exit 2
IMG=$(_py -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]]["llamacpp_image"])' \
    "$RUN_ROOT/tools/runs/hosts.json" "$RUN_HOST")
DIGEST=$(image_digest "$IMG") || exit 2
MODEL_DIR=$(dirname -- "$RUN_MODEL")

cleanup() { "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

ARGV=(-m "$RUN_MODEL" --alias "$TAG" --host 0.0.0.0 --port "$PORT" --parallel 1 -c "$CTX" -ngl 99 -fa on
    --reasoning-budget 0 --chat-template-kwargs '{"enable_thinking":false}')
echo "quick-check: $DIGEST ${ARGV[*]}"
"$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
"$DOCKER" run -d --name "$NAME" --runtime=nvidia --gpus all \
    -v "$MODEL_DIR:$MODEL_DIR:ro" -p "$PORT:$PORT" "$DIGEST" "${ARGV[@]}" >/dev/null

healthy=false
reason=""
for _ in $(seq 1 "$HEALTH_TRIES"); do
    code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://$RUN_HOST:$PORT/health" || true)
    if [ "$code" = 200 ]; then
        healthy=true
        break
    fi
    if ! "$DOCKER" inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null | grep -q true; then
        reason="container exited: $("$DOCKER" logs --tail 8 "$NAME" 2>&1 | tr '\n\t' '  ' | cut -c1-600)"
        break
    fi
    sleep 5
done
if [ "$healthy" != true ] && [ -z "$reason" ]; then
    reason="no /health in $((HEALTH_TRIES * 5))s: $("$DOCKER" logs --tail 8 "$NAME" 2>&1 | tr '\n\t' '  ' | cut -c1-600)"
fi

rc_py=NA
rc_ts=NA
if [ "$healthy" = true ]; then
    set +e
    _py tools/breadth/measure.py --endpoint "http://$RUN_HOST:$PORT" --protocol openai \
        --model "$TAG" --tier bench-py --tasks "$IDS" --draws 0 --max-output-tokens "$CAP" \
        --out "$OUT_REL/bench-py"
    rc_py=$?
    _py tools/breadth/measure.py --endpoint "http://$RUN_HOST:$PORT" --protocol openai \
        --model "$TAG" --tier bench-ts --tasks "$IDS" --draws 0 --max-output-tokens "$CAP" \
        --out "$OUT_REL/bench-ts"
    rc_ts=$?
    set -e
fi

_py - "$RUN_OUT_DIR/$ARTIFACT" "$RUN_ROOT/$OUT_REL" "$RUN_ID" "$RUN_HOST" "$RUN_MODEL" \
    "$IMG" "$DIGEST" "$healthy" "$reason" "$rc_py" "$rc_ts" "$RUN_ROUND" "$RUN_PRODUCT_SHA256" \
    "$IDS" "$CAP" "${ARGV[*]}" "$THINKING" <<'PY'
import json
import sys
from pathlib import Path

(artifact, out, run_id, host, model, image, digest, healthy, reason, rc_py, rc_ts,
 round_id, product, ids, cap, argv, thinking) = sys.argv[1:18]

tiers = {}
for tier, rc in (("bench-py", rc_py), ("bench-ts", rc_ts)):
    rows_path = Path(out) / tier / "results.jsonl"
    rows = [
        json.loads(line)
        for line in (rows_path.read_text().splitlines() if rows_path.is_file() else [])
        if line.strip()
    ]
    rows = [row for row in rows if not row.get("dispatch_error")]
    by_type = {}
    for row in rows:
        kind = by_type.setdefault(row.get("type", "?"), [0, 0])
        kind[0] += bool(row.get("passed"))
        kind[1] += 1
    tokens = [r["completion_tokens"] for r in rows if r.get("completion_tokens") is not None]
    latency = [r["latency_s"] for r in rows if r.get("latency_s") is not None]
    tiers[tier] = {
        "measure_rc": rc,
        "out": str(Path(out) / tier),
        "rows": len(rows),
        "passed": sum(bool(r.get("passed")) for r in rows),
        "by_type": {k: f"{p}/{n}" for k, (p, n) in sorted(by_type.items())},
        "parse_refused": sum(r.get("parse_error") is not None for r in rows),
        "truncated": sum(r.get("stop_reason") == "truncated" for r in rows),
        "overran_cap": sum(bool(r.get("overran_cap")) for r in rows),
        "mean_completion_tokens": round(sum(tokens) / len(tokens), 1) if tokens else None,
        "mean_latency_s": round(sum(latency) / len(latency), 2) if latency else None,
    }

Path(artifact).write_text(
    json.dumps(
        {
            "run_id": run_id,
            "host": host,
            "model": model,
            "image": image,
            "digest": digest,
            "argv": argv,
            "thinking": thinking,
            "healthy": healthy == "true",
            "reason": reason,
            "round": round_id,
            "product_sha256": product,
            "ids": ids.split(","),
            "draws": 0,
            "max_output_tokens": int(cap),
            "tiers": tiers,
        },
        indent=1,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

[ "$healthy" = true ] && [ "$rc_py" = 0 ] && [ "$rc_ts" = 0 ]
