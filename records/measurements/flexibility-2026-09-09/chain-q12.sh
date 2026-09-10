#!/bin/bash
cd /home/adaramir/claude/mcgyvr/records/measurements/flexibility-2026-09-09
while true; do
  n=$(python3 -c "import json;print(len(json.load(open('m2-coresidency.json'))))" 2>/dev/null || echo 0)
  [ "$n" -ge 3 ] && break
  sleep 45
done
uv run --no-sync --project /home/adaramir/claude/mcgyvr python - <<'PY' > logs/chain-q12.log 2>&1
import sys, time, json
sys.path.insert(0, ".")
import rig
C = "mcgyvr-srv2-Qwen3-Next-80B-A3B-Instruct-Q3_K_M-8003"
COMPOSE = "/home/adaramir/claude/mcgyvr/records/measurements/flexibility-2026-09-09/compose.srv2-80b-ncmoe36-w4.yml"
running = rig.rig("srv2", "docker ps --format '{{.Names}}' | grep '^mcgyvr-' || true")
if running.strip():
    last = rig.last_up("srv2")
    if last: rig.door_or_die("down", "srv2", last, f"q12td-{int(time.time())%10**6}")
rig.drop_caches("srv2")
rig.door_or_die("up", "srv2", COMPOSE, f"q12-80b-w4-{int(time.time())%10**6}")
rig.note_up("srv2", COMPOSE)
print("80B up at width 4", flush=True)
PY
uv run --no-sync --project /home/adaramir/claude/mcgyvr python /home/adaramir/claude/mcgyvr/tools/serving/concurrency_sweep.py \
  --url http://srv2:8003 --model Qwen3-Next-80B-A3B-Instruct-Q3_K_M --widths 1,2,4 \
  --label q12-80b-lambda --out results-q12-lambda.json >> logs/chain-q12.log 2>&1
echo "CHAIN-Q12-DONE"
