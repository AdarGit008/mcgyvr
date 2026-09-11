#!/usr/bin/env bash
# measuring-gaps orchestration: 30 arms + offline reports + final teardown.
# Run from this directory. Writes to stdout; launch under nohup/setsid and tail.
set -u
cd "$(dirname "$0")"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
fail=0

log "=== preflight: verify rigs empty ==="
for h in srv1 srv2; do
  up=$(ssh -o BatchMode=yes "$h" "docker ps --format '{{.Names}}' | wc -l" 2>/dev/null)
  up=${up//[[:space:]]/}
  if [ -z "$up" ] || [ "$up" != "0" ]; then
    log "ABORT: $h has '$up' running containers (expected 0)"; exit 1
  fi
  log "$h empty ($up running containers)"
done

run() {
  local name="$1"; shift
  log "=== $name ==="
  uv run --no-sync python "$@"
  local rc=$?
  log "$name exit rc=$rc"
  [ "$rc" -ne 0 ] && fail=1
}

# srv1 block first, then srv2 (Q3 spans both: Ling+gemma on srv1, 80B on srv2).
run "Q1 kv_q8_ab (srv1)"        kv_q8_ab.py        arms-q1-kv-q8.json
run "Q5 mla_absorbed_v (srv1)"  mla_absorbed_v.py  arms-q5-mla.json
run "Q3 scratch_curve (both)"   scratch_curve.py   arms-q3-scratch.json
run "Q2 vllm_fp8_kv (srv2)"     vllm_fp8_kv.py     arms-q2-vllm-fp8.json
run "Q4 c_drift_deepseek (srv2)" c_drift_deepseek.py arms-q4-c-drift.json

log "=== offline reports ==="
run "Q4 c_drift_report" c_drift_report.py
run "Q3 scratch_report" scratch_report.py

log "=== final teardown (both rigs empty again) ==="
uv run --no-sync python final_teardown.py
[ $? -ne 0 ] && fail=1

log "=== summary ==="
for f in results-arms-q1-kv-q8.json results-arms-q5-mla.json results-arms-q3-scratch.json \
         results-q2-vllm-fp8.json results-arms-q4-c-drift.json; do
  if [ -e "$f" ]; then
    python3 - "$f" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
failed = [r for r in d if r.get("failed")]
print(f"{sys.argv[1]}: {len(d)} rows, {len(failed)} failed")
for r in failed:
    print("   FAILED", r.get("label"), "->", r.get("failed"))
PY
  else
    echo "$f: MISSING"
  fi
done
log "=== DONE (fail=$fail) ==="
exit "$fail"
