#!/bin/bash
cd /home/adaramir/claude/mcgyvr/records/measurements/flexibility-2026-09-09
uv run --no-sync --project /home/adaramir/claude/mcgyvr python three_way.py > logs/chain-q16.log 2>&1
echo "Q16-DONE"
uv run --no-sync --project /home/adaramir/claude/mcgyvr python coresidency.py > logs/chain-q17.log 2>&1
echo "CHAIN-SRV2C-DONE"
