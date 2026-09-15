#!/usr/bin/env bash
# Quick check of moe-expert-coder-4b-Q4_K_M.gguf on srv1; the body is _check.sh.
# RUN_REWRITES: srv1-expertcoder-4b.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv1-expertcoder-4b.json moe-expert-coder-4b-Q4_K_M.gguf "$@"
