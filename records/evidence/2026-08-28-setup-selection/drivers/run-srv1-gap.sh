#!/bin/bash
# srv1 gap: wait for fix run, then 14B/32B kvu cells + 30B-IQ3XXS ncmoe48 probe
set -u
cd ~/sweep-2026-08-28/drivers
R=~/sweep-2026-08-28/results-srv1-gap.txt
echo "== srv1 gap start $(date) ==" >> "$R"
while ! grep -q "srv1 fix done" ~/sweep-2026-08-28/results-srv1-fix.txt 2>/dev/null; do sleep 60; done
sleep 30
# 30B UD-IQ3_XXS: one more probe, deeper offload (was: cudaMalloc 5747MiB OOM)
docker rm -f lcps >/dev/null 2>&1
docker run -d --name lcps --gpus all -v /home/adaramir/models/moe:/models:ro -p 8094:8080 ghcr.io/ggml-org/llama.cpp:server-cuda -m /models/Qwen3-Coder-30B-A3B-Instruct-UD-IQ3_XXS.gguf -ngl 99 -np 32 -c 32768 --n-cpu-moe 48 -fa on -kvu --no-warmup --host 0.0.0.0 --port 8080 >/dev/null 2>&1
sleep 75
docker logs lcps 2>&1 | grep -iE "error|memory|alloc|buffer" | tail -4 >> "$R"
if docker ps --format '{{.Names}}' | grep -q lcps; then
  python3 lcpsweep28k.py Qwen3-Coder-30B-A3B-Instruct-UD-IQ3_XXS.gguf /home/adaramir/models/moe 30b-IQ3XXS-kvu "32:1024:48:1,2,4,8,16,32" >> "$R" 2>&1
fi
docker rm -f lcps >/dev/null 2>&1
python3 lcpsweep28k.py Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf /home/adaramir/models/dense 14b-Q4-kvu "8:1024:0:1,2,4,8" >> "$R" 2>&1
python3 lcpsweep28k.py Qwen2.5-Coder-32B-Instruct-Q4_K_M.gguf /home/adaramir/models/dense 32b-Q4-kvu "8:1024:0:1,2,4,8" "16:1024:0:1,2,4,8,16" >> "$R" 2>&1
echo "== srv1 gap done $(date) ==" >> "$R"
