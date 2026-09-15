#!/usr/bin/env bash
# Quick check of gemma4-coding-Q4_K_M.gguf on srv2; the body is _check.sh.
# RUN_REWRITES: srv2-gemma4-12b-fable5.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv2-gemma4-12b-fable5.json gemma4-coding-Q4_K_M.gguf "$@"
