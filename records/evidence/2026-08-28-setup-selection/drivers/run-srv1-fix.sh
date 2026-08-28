#!/bin/bash
# srv1 fix runs: re-run contaminated 30B-IQ3XXS + gptoss-4b, then gpt-oss-20b MXFP4
set -u
cd ~/sweep-2026-08-28/drivers
R=~/sweep-2026-08-28/results-srv1-fix.txt
echo "== srv1 fix start $(date) ==" >> "$R"
sleep 30
# probe 30B-IQ3XXS with full logs (was refused during stray-container contamination)
docker rm -f lcps >/dev/null 2>&1
docker run -d --name lcps --gpus all -v /home/adaramir/models/moe:/models:ro -p 8094:8080 ghcr.io/ggml-org/llama.cpp:server-cuda -m /models/Qwen3-Coder-30B-A3B-Instruct-UD-IQ3_XXS.gguf -ngl 99 -np 8 -c 8192 --n-cpu-moe 28 -fa on --no-warmup --host 0.0.0.0 --port 8080 >/dev/null 2>&1
sleep 75
docker logs lcps 2>&1 | grep -iE "error|memory|arch|tensor" | tail -5 >> "$R"
docker rm -f lcps >/dev/null 2>&1
sleep 5
python3 lcpsweep28.py Qwen3-Coder-30B-A3B-Instruct-UD-IQ3_XXS.gguf /home/adaramir/models/moe 30b-IQ3XXS "8:1024:28:1,2,4,8" "32:1024:35:1,2,4,8,16,32" >> "$R" 2>&1
python3 lcpsweep28.py 4b-Q4_K_M.gguf /home/adaramir/models/moe gptoss-4b "32:1024:0:1,2,4,8,16,32" >> "$R" 2>&1
# Qwen3-8B (missed in main runner)
python3 lcpsweep28.py Qwen3-8B-Q4_K_M.gguf /home/adaramir/models/dense q3-8b-Q4 "16:1024:0:1,2,4,8,16" "32:1024:0:1,2,4,8,16,32" >> "$R" 2>&1
# gpt-oss-20b MXFP4: copy official conversion from HF cache to the store
cp ~/.cache/huggingface/hub/models--ggml-org--gpt-oss-20b-GGUF/snapshots/*/gpt-oss-20b-MXFP4.gguf ~/models/moe/ 2>/dev/null || true
python3 lcpsweep28.py gpt-oss-20b-MXFP4.gguf /home/adaramir/models/moe mxfp4-20b "8:1024:0:1,2,4,8" "32:1024:0:1,2,4,8,16,32" >> "$R" 2>&1
echo "== srv1 fix done $(date) ==" >> "$R"
