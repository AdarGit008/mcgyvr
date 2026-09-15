#!/usr/bin/env bash
# Quick check of qwen2.5-coder-0.5b-instruct-q4_k_m.gguf on srv1; the body is _check.sh.
# RUN_REWRITES: srv1-q25c-05b.json
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/_check.sh" srv1-q25c-05b.json qwen2.5-coder-0.5b-instruct-q4_k_m.gguf "$@"
