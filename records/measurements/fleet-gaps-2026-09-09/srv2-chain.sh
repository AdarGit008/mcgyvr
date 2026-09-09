#!/bin/bash
# The rest of srv2's campaign, chained so the rig is never idle between phases.
# Order is by value: the sleep-mode price and the sleep matrix first (M5, M6,
# M7 -- the precondition for the whole sleep/wake design), then the wake-rate
# blobs that turn r(srv2) from n=1 into a line (M4), then co-residency (M2),
# then the 80B loading-mode probe (M1), then production is restored.
set -x
cd /home/adaramir/claude/mcgyvr/records/measurements/fleet-gaps-2026-09-09
uv run --no-sync python vllm_arms.py arms-vllm-2.json
# arms-vllm-2 ends on the sleep-mode pair, which is what the matrix needs up.
uv run --no-sync python sleep_matrix.py
MCG_OUT=results-arms-srv2-rate.json uv run --no-sync python wake_rate.py arms-srv2-rate.json
uv run --no-sync python coresidency.py
MCG_OUT=results-arms-srv2-m1-80b.json uv run --no-sync python wake_rate.py arms-srv2-m1-80b.json
echo "CHAIN DONE"
# Production, as it must be left: the declared compose, sleep mode off again.
MCG_RESTORE=1 uv run --no-sync python - <<'PY'
import rig, time
rig.door_or_die("down", "srv2", rig.last_up("srv2"), f"restore-down-{int(time.time())%10**6}")
rig.door_or_die("up", "srv2", "/home/adaramir/.mcgyvr/config/compose.srv2.yml",
                f"restore-up-{int(time.time())%10**6}")
rig.note_up("srv2", "/home/adaramir/.mcgyvr/config/compose.srv2.yml")
print("srv2 restored:", rig.gpu("srv2"), rig.meminfo("srv2")["MemAvailable"])
PY
echo "SRV2 CHAIN DONE"
