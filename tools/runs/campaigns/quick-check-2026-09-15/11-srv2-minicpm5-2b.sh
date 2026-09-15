#!/usr/bin/env bash
# Quick check of MiniCPM5-2B.Q8_0.gguf on srv2; the body is _check.sh.
# RUN_REWRITES: srv2-minicpm5-2b.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv2-minicpm5-2b.json MiniCPM5-2B.Q8_0.gguf "$@"
