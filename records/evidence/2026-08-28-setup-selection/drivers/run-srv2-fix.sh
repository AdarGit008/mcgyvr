#!/bin/bash
# srv2 fix runs: vLLM eager re-runs + gpt-oss-20b MXFP4 (llama.cpp b10644)
set -u
cd ~/sweep-2026-08-28/drivers
R=~/sweep-2026-08-28/results-srv2-fix.txt
echo "== srv2 fix start $(date) ==" >> "$R"
sleep 30
python3 vllmsweep28e.py vllm-15b Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ "0.9:1024:256:fp8:1,2,4,8,16,32,64,128,256" >> "$R" 2>&1
python3 vllmsweep28e.py vllm-3b Qwen/Qwen2.5-Coder-3B-Instruct-AWQ "0.9:1024:256:fp8:1,2,4,8,16,32,64,128,256" >> "$R" 2>&1
python3 vllmsweep28e.py vllm-q3-4b thewimo/Qwen3-4B-AWQ "0.9:1024:256:fp8:1,2,4,8,16,32,64,128,256" >> "$R" 2>&1
python3 vllmsweep28e.py vllm-14b Qwen/Qwen2.5-Coder-14B-Instruct-AWQ "0.9:1024:64:fp8:1,2,4,8,16,32,64" >> "$R" 2>&1
# nem30b: probe with full log capture for the real OOM line
docker rm -f vsweep >/dev/null 2>&1
docker run -d --name vsweep --runtime=nvidia --gpus all -v $HOME/.cache/huggingface:/root/.cache/huggingface -v $HOME/models:/models:ro -p 8095:8000 --ipc=host vllm/vllm-openai:v0.26.0 /models/moe/nemotron-30b-awq --port 8000 --gpu-memory-utilization 0.9 --max-model-len 1024 --max-num-seqs 64 --enforce-eager >/dev/null 2>&1
sleep 90
docker logs vsweep 2>&1 | grep -iE "error|memory|out of" | tail -4 >> "$R"
docker rm -f vsweep >/dev/null 2>&1
# gpt-oss-20b MXFP4 on llama.cpp (wait for download)
for i in $(seq 1 60); do [ -f ~/models/moe/gpt-oss-20b-MXFP4.gguf ] && break; sleep 30; done
python3 lcpsweep28.py gpt-oss-20b-MXFP4.gguf /home/adaramir/models/moe mxfp4-20b "8:1024:0:1,2,4,8" "32:1024:0:1,2,4,8,16,32" >> "$R" 2>&1
echo "== srv2 fix done $(date) ==" >> "$R"
