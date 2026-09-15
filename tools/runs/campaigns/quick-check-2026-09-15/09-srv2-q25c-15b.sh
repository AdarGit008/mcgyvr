#!/usr/bin/env bash
# Quick check of qwen2.5-coder-1.5b-instruct-q4_k_m.gguf on srv2; the body is _check.sh.
# RUN_REWRITES: srv2-q25c-15b.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv2-q25c-15b.json qwen2.5-coder-1.5b-instruct-q4_k_m.gguf "$@"
