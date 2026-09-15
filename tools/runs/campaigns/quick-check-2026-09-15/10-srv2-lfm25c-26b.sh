#!/usr/bin/env bash
# Quick check of LFM2.5-2.6B.Q4_K_M.gguf on srv2; the body is _check.sh.
# RUN_REWRITES: srv2-lfm25c-26b.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv2-lfm25c-26b.json LFM2.5-2.6B.Q4_K_M.gguf "$@"
