#!/usr/bin/env bash
# Quick check of Jan-code-4b-Q4_K_M.gguf on srv1; the body is _check.sh.
# RUN_REWRITES: srv1-jancode-4b.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv1-jancode-4b.json Jan-code-4b-Q4_K_M.gguf "$@"
