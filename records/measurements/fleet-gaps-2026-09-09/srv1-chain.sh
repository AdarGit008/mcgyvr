#!/bin/bash
# srv1's remaining phases, chained. M1's matched mapped/unmapped pair with the
# 1 Hz card sampler; M3's blob-axis shortfalls at -2.0 and -3.0 GiB, which is
# where `k` either saturates or does not; then the experts axis, whose two arms
# bracket the cliff G4 leaves unlocated between +0.55 and -0.97 GiB. Each
# phase ends by restoring the production mapped unit, so an abandoned chain
# still leaves the rig serving.
set -x
cd /home/adaramir/claude/mcgyvr/records/measurements/fleet-gaps-2026-09-09
uv run --no-sync python wake_rate.py arms-srv1-m1-m3.json
uv run --no-sync python wake_rate.py arms-srv1-m3-experts.json
uv run --no-sync python - <<'PY'
import rig
rig.balloon_down("srv1")
print("srv1 left on:", rig.last_up("srv1"))
print("card:", rig.gpu("srv1"), "avail:", rig.meminfo("srv1")["MemAvailable"])
PY
echo "SRV1 CHAIN DONE"
