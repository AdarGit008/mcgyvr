#!/bin/bash
# srv2 gap runs: wait for fix run, then Qwen3-8B, 14B-kvu llama.cpp, vLLM-latest cells
set -u
cd ~/sweep-2026-08-28/drivers
R=~/sweep-2026-08-28/results-srv2-gap.txt
echo "== srv2 gap start $(date) ==" >> "$R"
while ! grep -q "srv2 fix done" "$R" 2>/dev/null; do
  grep -q "srv2 fix done" ~/sweep-2026-08-28/results-srv2-fix.txt 2>/dev/null && break
  sleep 60
done
sleep 30
python3 lcpsweep28.py Qwen3-8B-Q4_K_M.gguf /home/adaramir/models/dense q3-8b-Q4 "32:1024:0:1,2,4,8,16,32" "64:1024:0:1,2,4,8,16,32,64" >> "$R" 2>&1
python3 lcpsweep28k.py Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf /home/adaramir/models/dense 14b-Q4-kvu "32:1024:0:1,2,4,8,16,32" >> "$R" 2>&1
# vLLM latest image (driver 595.84): re-run cells that v0.26.0 refused
python3 vllmsweep28L.py vllmL-15b Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ "0.9:1024:256:fp8:1,2,4,8,16,32,64,128,256" >> "$R" 2>&1
python3 vllmsweep28L.py vllmL-3b Qwen/Qwen2.5-Coder-3B-Instruct-AWQ "0.9:1024:256:fp8:1,2,4,8,16,32,64,128,256" >> "$R" 2>&1
python3 vllmsweep28L.py vllmL-14b Qwen/Qwen2.5-Coder-14B-Instruct-AWQ "0.9:1024:64:fp8:1,2,4,8,16,32,64" >> "$R" 2>&1
# nem30b full-log probe on latest image
docker rm -f vsweep >/dev/null 2>&1
docker run -d --name vsweep --runtime=nvidia --gpus all -v $HOME/.cache/huggingface:/root/.cache/huggingface -v $HOME/models:/models:ro -p 8095:8000 --ipc=host vllm/vllm-openai:latest /models/moe/nemotron-30b-awq --port 8000 --gpu-memory-utilization 0.9 --max-model-len 1024 --max-num-seqs 64 --enforce-eager >/dev/null 2>&1
sleep 120
docker logs vsweep 2>&1 | grep -iE "error|memory|out of" | tail -4 >> "$R"
docker rm -f vsweep >/dev/null 2>&1
echo "== srv2 gap done $(date) ==" >> "$R"
