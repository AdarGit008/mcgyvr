#!/usr/bin/env bash
# usage: llama_bench.sh MODEL_CTR_PATH [DRAFT_CTR_PATH] [N_PREDICT] [N_RUNS] [PREFIX] [PORT] [TMO] [NMAX] [NCMOE]
# MODEL_CTR_PATH / DRAFT_CTR_PATH are CONTAINER-absolute paths:
#   /models/<file>      -> /home/adaramir/ggufs/<file>
#   /store/<family>/<f> -> /home/adaramir/model-store/<family>/<f>
#   /draft/<file>       -> /home/adaramir/specdecode/llama_sd/<file>
# Runs llama.cpp (server-cuda-b10481) with optional --model-draft speculative decoding,
# warms up, takes N_RUNS timed /completion requests, prints per-request tokens/sec.
MODEL="$1"; DRAFT="$2"; N="${3:-150}"; N_RUNS="${4:-3}"; PREFIX="${5:-base}"; PORT="${6:-8081}"; TMO="${7:-300}"; NMAX="${8:-3}"; NCMOE="${9:-0}"
CONTAINER="llama_${PREFIX}"
docker rm -f "$CONTAINER" >/dev/null 2>&1

ARGS=( -m "$MODEL" -ngl 99 -c 4096 -np 1 --host 0.0.0.0 --port "$PORT" )
if [ "$NCMOE" -gt 0 ]; then ARGS+=( --n-cpu-moe "$NCMOE" ); fi
if [ -n "$DRAFT" ]; then
  ARGS+=( -md "$DRAFT" --spec-draft-n-max "$NMAX" --spec-type draft-simple )
fi

docker run -d --gpus all -p "${PORT}:${PORT}" --name "$CONTAINER" \
  -v /home/adaramir/ggufs:/models \
  -v /home/adaramir/model-store:/store \
  -v /home/adaramir/specdecode/llama_sd:/draft \
  ghcr.io/ggml-org/llama.cpp:server-cuda-b10481 "${ARGS[@]}" >/dev/null 2>&1

ok=""
for i in $(seq 1 150); do
  if docker logs "$CONTAINER" 2>&1 | grep -q "listening on"; then ok=1; break; fi
  sleep 1
done
if [ -z "$ok" ]; then
  echo "RESULT={\"ok\":false,\"why\":\"no-listening\"}"
else
  BODY="{\"prompt\":\"Write a Python function to compute the nth Fibonacci number. Steps:\", \"n_predict\": $((N)), \"temperature\": 0}"
  curl -s -4 --max-time "${TMO}" -X POST "http://127.0.0.1:${PORT}/completion" \
    -H "Content-Type: application/json" -d "$BODY" >/dev/null 2>&1
  for r in $(seq 1 "$N_RUNS"); do
    curl -s -4 --max-time "${TMO}" -X POST "http://127.0.0.1:${PORT}/completion" \
      -H "Content-Type: application/json" -d "$BODY" >/dev/null 2>&1
  done
  docker logs "$CONTAINER" 2>&1 | grep -oE "eval time =[^|]*(tokens per second)" | grep -E "/ +$N tokens" | tail -n "$N_RUNS"
fi
docker stop "$CONTAINER" >/dev/null 2>&1
docker rm -f "$CONTAINER" >/dev/null 2>&1
