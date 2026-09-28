#!/usr/bin/env bash
# tools/runs/campaigns/srv1-multi-gpu/20-rebar.sh — step 1's link probe, filed
# as its own artifact after BAR1 was resized (Above 4G Decoding on, CSM off,
# BAR1 resized to 16 GiB from Linux through resource1_resize; the BIOS has no
# Re-Size BAR option). The stock driver still reports P2P as CNS, so this
# isolates what a card-sized BAR1 alone does to the link; link.tsv is the
# 256 MiB baseline of the same boot image and driver.
#
# RUN_ARTIFACTS: rebar.tsv
#
# python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu \
#   --step tools/runs/campaigns/srv1-multi-gpu/20-rebar.sh \
#   --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048

[ -n "${RUN_ID:-}" ] || { echo "20-rebar.sh: RUN_ID is unset — start me through the door: python -m mcgyvr.serving.run --host srv1 --campaign srv1-multi-gpu --step tools/runs/campaigns/srv1-multi-gpu/20-rebar.sh --model /models/dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf --ctx-per-slot 2048" >&2; exit 2; }

LINK_ARTIFACT=rebar.tsv
export LINK_ARTIFACT
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/1-link.sh" "$@"
