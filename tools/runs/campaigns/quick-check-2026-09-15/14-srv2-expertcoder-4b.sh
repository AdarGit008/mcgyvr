#!/usr/bin/env bash
# Quick check of moe-expert-coder-4b-Q4_K_M.gguf on srv2; the body is _check.sh.
# RUN_REWRITES: srv2-expertcoder-4b.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv2-expertcoder-4b.json moe-expert-coder-4b-Q4_K_M.gguf "$@"
