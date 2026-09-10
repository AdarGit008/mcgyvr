#!/bin/bash
cd /home/adaramir/claude/mcgyvr/records/measurements/flexibility-2026-09-09
# Wait for Q4/Q5/Q6's 14 arms, then the hazard block: vLLM on srv1, last and alone.
while true; do
  n=$(python3 -c "import json;print(len(json.load(open('results-q4q5q6-srv1.json'))))" 2>/dev/null || echo 0)
  [ "$n" -ge 14 ] && break
  sleep 45
done
MCG_HOST=srv1 MCG_OUT=results-q9-vllm-srv1.json uv run --no-sync --project /home/adaramir/claude/mcgyvr \
  python vllm_arms.py arms-q9-vllm-srv1.json > logs/chain-q9.log 2>&1
echo "CHAIN-SRV1B-DONE"
