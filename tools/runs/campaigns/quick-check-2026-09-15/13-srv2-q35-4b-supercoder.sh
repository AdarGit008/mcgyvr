#!/usr/bin/env bash
# Quick check of qwen3.5-4B-super-coder.Q4_0.gguf on srv2; the body is _check.sh.
# RUN_REWRITES: srv2-q35-4b-supercoder.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv2-q35-4b-supercoder.json qwen3.5-4B-super-coder.Q4_0.gguf "$@"
