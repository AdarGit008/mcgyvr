#!/bin/bash
cd /home/adaramir/claude/mcgyvr/records/measurements/flexibility-2026-09-09
# Wait for Q1 to finish writing all 9 arms, then run Q4/Q5/Q6 without leaving srv1 idle.
while true; do
  n=$(python3 -c "import json;print(len(json.load(open('results-q1-srv1.json'))))" 2>/dev/null || echo 0)
  [ "$n" -ge 9 ] && break
  sleep 30
done
MCG_OUT=results-q4q5q6-srv1.json uv run --no-sync --project /home/adaramir/claude/mcgyvr \
  python wake_rate.py arms-q4q5q6-srv1.json > logs/chain-srv1.log 2>&1
echo "CHAIN-SRV1-DONE"
