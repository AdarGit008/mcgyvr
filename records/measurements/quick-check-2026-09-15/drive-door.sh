#!/bin/bash
# Step 3, driver 7 (owner, 2026-09-15): thinking off for every remaining model, LFM2.5 re-run on both
# rigs. Per rig: wait for the in-flight door run driver 6 left, then run every step whose artifact is
# missing or was measured with thinking on (Qwen2.5 excepted: its template has no thinking mode),
# --suffix r4. Live stays down through the sweep; a failed canary pauses the rig with live down;
# live comes back (door, --suffix qc4) only after the rig's whole queue has run.
set -u
W=/home/adaramir/claude/mcgyvr-emit-f4
C=/home/adaramir/.local/state/mcgyvr/compose/b-small
CAMP=quick-check-2026-09-15
ENV_DIR=$W/records/evidence/2026-09-15-$CAMP
LOGD=/tmp/claude-1000/-home-adaramir-claude-mcgyvr/3dcb25d3-9a98-4204-8da0-88dab9557425/scratchpad
LIVE_SUFFIX=qc4
CHECK_SUFFIX=r4
declare -A DIR=(
  [qwen2.5-coder-0.5b-instruct-q4_k_m.gguf]=Qwen_Qwen2.5-Coder-0.5B-Instruct-GGUF
  [qwen2.5-coder-1.5b-instruct-q4_k_m.gguf]=Qwen_Qwen2.5-Coder-1.5B-Instruct-GGUF
  [LFM2.5-2.6B.Q4_K_M.gguf]=Schnuckade_LFM-2.5-Coder-2.6B
  [MiniCPM5-2B.Q8_0.gguf]=bunnycore_MiniCPM5-2B-Code-lora
  [Jan-code-4b-Q4_K_M.gguf]=janhq_Jan-code-4b-gguf
  [qwen3.5-4B-super-coder.Q4_0.gguf]=jica98_qwen3.5-4B-super-coder
  [moe-expert-coder-4b-Q4_K_M.gguf]=h3rb3rn_moe-expert-coder-4b
  [qwen2.5-coder-7b-instruct-q5_k_m.gguf]=apto-as_Qwen2.5-Coder-7B-Instruct-Q5_K_M-GGUF
  [gemma4-coding-Q4_K_M.gguf]=yuxinlu1_gemma-4-12B-coder-fable5-composer2.5-v1-GGUF
  [Instinct-Python-Coder-Gemma4-12B-GLM5.2-Q8_0.gguf]=projectj_Instinct-Python-Coder-Gemma4-12B-GLM5.2
)
live_urls() { case $1 in srv1) echo http://srv1:8080/health ;; srv2) echo "http://srv2:8001/v1/models http://srv2:8002/v1/models" ;; esac; }
live_answers() { for u in $(live_urls "$1"); do curl -s -m 5 -o /dev/null -w '%{http_code}' "$u" | grep -q 200 || return 1; done; return 0; }
any_live_answers() { for u in $(live_urls "$1"); do curl -s -m 5 -o /dev/null -w '%{http_code}' "$u" | grep -q 200 && return 0; done; return 1; }
healthy() { for _ in $(seq 1 60); do live_answers "$1" && return 0; sleep 10; done; return 1; }

# needs_run NAME -> 0 when the step has no artifact yet, or its artifact ran with thinking on
needs_run() {
  local art=$ENV_DIR/$1.json
  case $1 in *-q25c-05b|*-q25c-15b) [ -f "$art" ] && return 1 ;; esac
  [ -f "$art" ] || return 0
  python3 -c "
import json, sys
d = json.load(open('$art'))
sys.exit(0 if d.get('thinking') != 'off' else 1)"
}

checks() {
  local H=$1 LOG=$2 first=1 step name blob dir model rc art summary
  for step in "$W"/tools/runs/campaigns/$CAMP/[0-9][0-9]-$H-*.sh; do
    name=$(basename "$step" .sh); name=${name#[0-9][0-9]-}
    if ! needs_run "$name"; then
      echo "$(date -Is) $H $name: already measured under the current condition; not re-run" | tee -a "$LOG"; continue
    fi
    blob=$(grep -oE '[^ ]+\.json [^ ]+\.gguf' "$step" | awk '{print $2}')
    dir=${DIR[${blob:-none}]:-}
    if [ -z "$blob" ] || [ -z "$dir" ]; then
      echo "$(date -Is) $H $name: no blob/dir resolved from $step; skipped" | tee -a "$LOG"; continue
    fi
    model=/home/adaramir/models/.incoming/$dir/$blob
    echo "$(date -Is) == $H: check $name thinking=off ($model)" | tee -a "$LOG"
    (cd "$W" && MCGYVR_CONFIG=$W/fleet-setup uv run --no-sync python -m mcgyvr.serving.run --host "$H" --campaign "$CAMP" \
        --step "tools/runs/campaigns/$CAMP/$(basename "$step")" --model "$model" --parallel 1 --ctx-per-slot 8192 \
        --suffix "$CHECK_SUFFIX") >> "$LOG" 2>&1
    rc=$?
    art=$ENV_DIR/$name.json
    summary=$(python3 -c "
import json
d = json.load(open('$art'))
print('run_id=%s thinking=%s healthy=%s' % (d['run_id'], d.get('thinking'), d['healthy']), ' '.join('%s:%s/%s %s truncated=%s refused=%s tok=%s s=%s rc=%s' % (k, v['passed'], v['rows'], v['by_type'], v.get('truncated'), v['parse_refused'], v['mean_completion_tokens'], v['mean_latency_s'], v['measure_rc']) for k, v in d['tiers'].items()), ('reason=' + d['reason'][:200]) if d['reason'] else '')
" 2>&1 | tail -1)
    echo "$(date -Is) $H $name door rc=$rc :: $summary" | tee -a "$LOG"
    if [ $first = 1 ]; then
      first=0
      if ! python3 -c "
import json
d = json.load(open('$art'))
assert d['run_id'].endswith('-$CHECK_SUFFIX') and d.get('thinking') == 'off' and d['healthy'] and all(v['rows'] == 20 for v in d['tiers'].values())" 2>/dev/null; then
        echo "$(date -Is) $H: CANARY $name did not produce 20+20 rows with thinking off; queue stopped, live LEFT DOWN for a fix and a resume" | tee -a "$LOG"
        return 1
      fi
    fi
  done
  return 0
}

run_rig() {
  local H=$1 LOG=$LOGD/quick-check-door-$1.log rc
  log() { echo "$(date -Is) $*" | tee -a "$LOG"; }
  serve() { (cd "$W" && env -u MCGYVR_CONFIG uv run --no-sync python -m mcgyvr.serving.run serve "$1" --host "$H" --compose "$C/compose.$H.b-small.yml" --suffix "$LIVE_SUFFIX") >> "$LOG" 2>&1; }

  log "== $H (driver 7): waiting for the in-flight door run driver 6 left"
  while pgrep -f "[m]cgyvr.serving.run --host $H " >/dev/null; do sleep 10; done
  if any_live_answers "$H"; then
    log "$H: live answers; driver 7 runs no checks on a serving rig"; log "$H ALLDONE"; return
  fi

  if ! checks "$H" "$LOG"; then
    log "$H PAUSED (live down)"; return
  fi

  log "== $H: sweep finished; door serve up (live, --suffix $LIVE_SUFFIX)"
  serve up; rc=$?; log "$H serve up rc=$rc"
  if healthy "$H"; then
    log "$H live HEALTHY after door serve up"
  else
    log "$H not healthy after door serve up; hand compose up of the emitted file"
    ssh "$H" "docker compose -f - -p mcgyvr up -d" < "$C/compose.$H.b-small.yml" >> "$LOG" 2>&1
    if healthy "$H"; then log "$H live HEALTHY after hand compose up"; else log "$H STILL not healthy"; fi
  fi
  log "$H ALLDONE"
}

run_rig srv1 & run_rig srv2 & wait
