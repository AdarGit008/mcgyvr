#!/bin/bash
# srv2 final: vLLM 15b/3b/q3-4b at seqs=128 (256 is driver-broken on 595.84)
set -u
cd ~/sweep-2026-08-28/drivers
R=~/sweep-2026-08-28/results-srv2-final.txt
echo "== srv2 final start $(date) ==" >> "$R"
sleep 20
python3 vllmsweep28.py vllm-15b-s128 Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ "0.9:1024:128:fp8:1,2,4,8,16,32,64,128" >> "$R" 2>&1
python3 vllmsweep28.py vllm-3b-s128 Qwen/Qwen2.5-Coder-3B-Instruct-AWQ "0.9:1024:128:fp8:1,2,4,8,16,32,64,128" >> "$R" 2>&1
python3 vllmsweep28.py vllm-q3-4b-s128 thewimo/Qwen3-4B-AWQ "0.9:1024:128:fp8:1,2,4,8,16,32,64,128" >> "$R" 2>&1
echo "== srv2 final done $(date) ==" >> "$R"
