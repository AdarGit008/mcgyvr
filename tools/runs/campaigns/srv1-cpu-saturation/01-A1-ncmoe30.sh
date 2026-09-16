#!/usr/bin/env bash
# srv1-cpu-saturation arm A1: Qwen3.6-35B-A3B UD-IQ3_XXS on srv1 at --n-cpu-moe 30, --parallel 8, 4096 a slot; the body is _arm.sh.
# RUN_ARTIFACTS: A1-ncmoe30.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_arm.sh" A1-ncmoe30.json A1 30 "$@"
