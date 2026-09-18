#!/usr/bin/env bash
# tools/runs/campaigns/srv1-kernel-arms/7-crash.sh — campaign step 7, the crash
# study (behaviour 8), as a door step of its own.
#
# WHY A FILE OF ITS OWN. The crash study's code lives in 4-kernel-arms.sh
# (`--step crash`): the L2 boundary sweep and L3's 60 trials are the kernel
# question, so that script owns it. But the door guards what a step file
# DECLARES, and 4-kernel-arms.sh declares `srv1-lcpp-arms.tsv` write-once for
# step 4 (`--step serve`). Run as that one file, the crash study is refused at
# gate 5 once step 4 has written its artifact. So step 7 is this file: it
# declares the one thing the crash
# study writes, an APPEND to step 6's file, and hands off. The door exports
# RUN_STEP=crash, and 4-kernel-arms.sh holds its --step to that.
#
# Through the door only:
#   python -m mcgyvr.serving.run --host srv1 --campaign srv1-kernel-arms --step tools/runs/campaigns/srv1-kernel-arms/7-crash.sh --model <blob> [-- --dry-run ...]
# Everything after -- reaches 4-kernel-arms.sh (--crash-cells, --trials, ...).
# RUN_APPENDS: srv1-moe-slots.tsv

[ -n "${RUN_ID:-}" ] || { echo "7-crash.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-kernel-arms --step tools/runs/campaigns/srv1-kernel-arms/7-crash.sh --model <blob as the rig sees it>" >&2; exit 2; }

set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "$HERE/4-kernel-arms.sh" --step crash "$@"
