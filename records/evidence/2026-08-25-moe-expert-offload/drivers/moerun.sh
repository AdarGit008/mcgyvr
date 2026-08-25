#!/bin/bash
# usage: moerun.sh <model_path> <mount_dir> <label> <cells...>   cell = ncpumoe:threads
MODEL="$1"; MDIR="$2"; TAG="$3"; shift 3
H=$(hostname)
IMG=ghcr.io/ggml-org/llama.cpp:server-cuda-b10481
PORT=8099
for cell in "$@"; do
  NM="${cell%%:*}"; TH="${cell##*:}"
  docker rm -f llmoe >/dev/null 2>&1
  docker run -d --name llmoe --gpus all -v "$MDIR":/models:ro -p $PORT:8080 "$IMG" \
    -m "/models/$(basename "$MODEL")" -ngl 99 --n-cpu-moe "$NM" -t "$TH" \
    -c 4096 -fa on --no-warmup --host 0.0.0.0 --port 8080 >/dev/null 2>&1
  ok=0
  for i in $(seq 1 150); do
    if curl -sf -m 3 http://localhost:$PORT/health >/dev/null 2>&1; then ok=1; break; fi
    if ! docker ps --format '{{.Names}}' | grep -q '^llmoe$'; then break; fi
    sleep 2
  done
  if [ "$ok" != 1 ]; then
    echo -e "$H\t$TAG\tncpumoe=$NM\tthreads=$TH\tFAILED\t$(docker logs llmoe 2>&1 | grep -iE 'error|out of memory|failed' | tail -1 | cut -c1-110)"
    docker rm -f llmoe >/dev/null 2>&1; continue
  fi
  VRAM=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  # one untimed warm request, then the measured one
  curl -s -m 600 http://localhost:$PORT/completion -d '{"prompt":"Write a Python function that merges two sorted lists.","n_predict":32,"temperature":0}' >/dev/null 2>&1
  R=$(curl -s -m 900 http://localhost:$PORT/completion -d '{"prompt":"Write a Python function that merges two sorted lists.","n_predict":128,"temperature":0,"cache_prompt":false}')
  echo "$R" | python3 -c "
import sys,json
try: d=json.load(sys.stdin)
except Exception: print('$H\t$TAG\tncpumoe=$NM\tthreads=$TH\tPARSE_FAIL'); sys.exit()
t=d.get('timings',{})
print(f\"$H\t$TAG\tncpumoe=$NM\tthreads=$TH\tdecode_tok_s={t.get('predicted_per_second',0):.2f}\tprefill_tok_s={t.get('prompt_per_second',0):.1f}\tvram_mib=$VRAM\")
"
  docker rm -f llmoe >/dev/null 2>&1
  sleep 3
done
