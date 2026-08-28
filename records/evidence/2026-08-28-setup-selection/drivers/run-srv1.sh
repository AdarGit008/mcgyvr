#!/bin/bash
# srv1 sweep runner (2026-08-28 setup selection). Sequential, logged.
set -u
cd ~/sweep-2026-08-28/drivers
R=~/sweep-2026-08-28/results-srv1.txt
D=/home/adaramir/models/dense
M=/home/adaramir/models/moe
echo "== srv1 sweep start $(date) ==" >> "$R"

# 0. control on b10481 (bridge to last-week numbers)
python3 lcpsweep.py Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf "$M" ctrl-35B-ncmoe40-b10481 "32:1024:40:1,32" >> "$R" 2>&1

# 1. llama.cpp b10644 — dense
python3 lcpsweep28.py Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf "$D" 15b-Q4 "32:1024:0:1,2,4,8,16,32" "64:1024:0:1,2,4,8,16,32,64" "128:1024:0:1,2,4,8,16,32,64,128" >> "$R" 2>&1
python3 lcpsweep28.py Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf "$D" 3b-Q4 "32:1024:0:1,2,4,8,16,32" "64:1024:0:1,2,4,8,16,32,64" >> "$R" 2>&1
python3 lcpsweep28.py Qwen3-4B-Q4_K_M.gguf "$D" q3-4b-Q4 "32:1024:0:1,2,4,8,16,32" "64:1024:0:1,2,4,8,16,32,64" >> "$R" 2>&1
python3 lcpsweep28.py Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf "$D" 7b-IQ4XS "16:1024:0:1,2,4,8,16" >> "$R" 2>&1
python3 lcpsweep28.py nvidia_OpenCodeReasoning-Nemotron-7B-Q4_K_M.gguf "$D" nemotron7b-Q4 "16:1024:0:1,2,4,8,16" >> "$R" 2>&1
python3 lcpsweep28.py Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf "$D" 14b-Q4 "8:1024:0:1,2,4,8" "16:1024:0:1,2,4,8,16" >> "$R" 2>&1

# 2. llama.cpp b10644 — MoE
python3 lcpsweep28.py qwen3-coder-30b.gguf "$M" 30b-Q4 "8:1024:38:1,2,4,8" "32:1024:44:1,2,4,8,16,32" >> "$R" 2>&1
python3 lcpsweep28.py Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf "$M" 35B-IQ3XXS "32:1024:40:1,2,4,8,16,32" "64:1024:48:1,2,4,8,16,32,64" >> "$R" 2>&1
python3 lcpsweep28.py nvidia_Nemotron-3-Nano-30B-A3B-IQ2_XXS.gguf "$M" nem30b-IQ2XXS "8:1024:38:1,2,4,8" "32:1024:44:1,2,4,8,16,32" >> "$R" 2>&1
python3 lcpsweep28.py Qwen3-Coder-Next-UD-Q3_K_XL.gguf "$M" nextud-80B-Q3XL "8:1024:50:1,2,4,8" "16:1024:60:1,2,4,8,16" >> "$R" 2>&1
python3 lcpsweep28.py deepseek-coder-v2-16b.gguf "$M" dscv2-16b "8:1024:30:1,2,4,8" "32:1024:40:1,2,4,8,16,32" >> "$R" 2>&1
python3 lcpsweep28.py gpt-oss-20b.gguf "$M" gptoss-20b "8:1024:0:1,2,4,8" >> "$R" 2>&1
python3 lcpsweep28.py 4b-Q4_K_M.gguf "$M" gptoss-4b "32:1024:0:1,2,4,8,16,32" >> "$R" 2>&1

python3 lcpsweep28.py Qwen2.5-Coder-32B-Instruct-Q4_K_M.gguf "$D" 32b-Q4 "8:1024:0:1,2,4,8" "16:1024:0:1,2,4,8,16" >> "$R" 2>&1
python3 lcpsweep28.py Qwen3-Coder-30B-A3B-Instruct-UD-IQ3_XXS.gguf "$M" 30b-IQ3XXS "8:1024:28:1,2,4,8" "32:1024:35:1,2,4,8,16,32" >> "$R" 2>&1
# 3. vLLM v0.26.0 — AWQ / local safetensors (cc7.5: no fp8 KV)
python3 vllmsweep28.py vllm-15b Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ "0.85:1024:64:auto:1,2,4,8,16,32,64" >> "$R" 2>&1
python3 vllmsweep28.py vllm-3b Qwen/Qwen2.5-Coder-3B-Instruct-AWQ "0.85:1024:64:auto:1,2,4,8,16,32,64" >> "$R" 2>&1
python3 vllmsweep28.py vllm-q3-4b thewimo/Qwen3-4B-AWQ "0.85:1024:64:auto:1,2,4,8,16,32,64" >> "$R" 2>&1
python3 vllmsweep28.py vllm-7b Qwen/Qwen2.5-Coder-7B-Instruct-AWQ "0.9:1024:64:auto:1,8" >> "$R" 2>&1
python3 vllmsweep28.py vllm-nem4b-fp8 /models/dense/nemotron-4b-fp8 "0.8:1024:32:auto:1,2,4,8,16,32" >> "$R" 2>&1

echo "== srv1 sweep done $(date) ==" >> "$R"
