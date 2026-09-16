#!/usr/bin/env bash
# srv1-cpu-saturation arm A2: Qwen3.6-35B-A3B UD-IQ3_XXS on srv1 at --n-cpu-moe 36, --parallel 8, 4096 a slot; the body is _arm.sh.
# RUN_ARTIFACTS: A2-ncmoe36.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_arm.sh" A2-ncmoe36.json A2 36 "$@"
