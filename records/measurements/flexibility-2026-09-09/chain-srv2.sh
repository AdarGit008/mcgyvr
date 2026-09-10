#!/bin/bash
cd /home/adaramir/claude/mcgyvr/records/measurements/flexibility-2026-09-09
while true; do
  n=$(python3 -c "import json;print(len(json.load(open('results-q14-pair-healthy.json'))))" 2>/dev/null || echo 0)
  [ "$n" -ge 2 ] && break
  sleep 30
done
MCG_OUT=results-q15-sleepmode.json uv run --no-sync --project /home/adaramir/claude/mcgyvr \
  python vllm_arms.py arms-q15-sleepmode.json > logs/chain-srv2.log 2>&1
echo "CHAIN-SRV2-DONE"
