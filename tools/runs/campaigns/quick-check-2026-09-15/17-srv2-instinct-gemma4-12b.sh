#!/usr/bin/env bash
# Quick check of Instinct-Python-Coder-Gemma4-12B-GLM5.2-Q8_0.gguf on srv2; the body is _check.sh.
# RUN_REWRITES: srv2-instinct-gemma4-12b.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv2-instinct-gemma4-12b.json Instinct-Python-Coder-Gemma4-12B-GLM5.2-Q8_0.gguf "$@"
