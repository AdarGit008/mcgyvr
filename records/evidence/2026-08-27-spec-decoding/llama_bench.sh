#!/usr/bin/env bash
# usage: llama_bench.sh MODEL_GGUF [DRAFT_GGUF] [N_PREDICT] [PREFIX] [PORT]
# Runs llama.cpp server (server-cuda-b10481) with optional --model-draft speculative
# decoding, does a warmup + N measured /completion requests, then prints per-request
# tokens/sec parsed from the server's own "print_timing" log lines.
# NOTE: a single request must complete within TMO seconds (serve stdout not needed).
MODEL="$1"; DRAFT="$2"; N="${3:-150}"; N_RUNS="${4:-3}"; PREFIX="${5:-base}"; PORT="${6:-8081}"; TMO="${7:-300}"; NMAX="${8:-3}"; NCMOE="${9:-0}"
CONTAINER="llama_${PREFIX}"
docker rm -f "$CONTAINER" >/dev/null 2>&1

ARGS=( -m "/models/$(basename "$MODEL")" -ngl 99 -c 4096 -np 1 --host 0.0.0.0 --port "$PORT" )
if [ "$NCMOE" -gt 0 ]; then ARGS+=( --n-cpu-moe "$NCMOE" ); fi
if [ -n "$DRAFT" ]; then
  ARGS+=( -md "/draft/$(basename "$DRAFT")" --spec-draft-n-max "$NMAX" --spec-type draft-simple )
fi

docker run -d --gpus all -p "${PORT}:${PORT}" --name "$CONTAINER" \
  -v /home/adaramir/ggufs:/models \
  -v /home/adaramir/specdecode/llama_sd:/draft \
  ghcr.io/ggml-org/llama.cpp:server-cuda-b10481 "${ARGS[@]}" >/dev/null 2>&1

ok=""
for i in $(seq 1 120); do
  if docker logs "$CONTAINER" 2>&1 | grep -q "listening on"; then ok=1; break; fi
  sleep 1
done
if [ -z "$ok" ]; then
  echo "RESULT={\"ok\":false,\"why\":\"no-listening\"}"
else
  BODY="{\"prompt\":\"Write a Python function to compute the nth Fibonacci number. Steps:\", \"n_predict\": $((N)), \"temperature\": 0}"
  # warmup
  curl -s -4 --max-time "${TMO}" -X POST "http://127.0.0.1:${PORT}/completion" \
    -H "Content-Type: application/json" -d "$BODY" >/dev/null 2>&1
  for r in $(seq 1 "$N_RUNS"); do
    curl -s -4 --max-time "${TMO}" -X POST "http://127.0.0.1:${PORT}/completion" \
      -H "Content-Type: application/json" -d "$BODY" >/dev/null 2>&1
  done
  log=$(docker logs "$CONTAINER" 2>&1)
  echo "$log" | grep -oE "print_timing:[^|]*\|[^|]*eval time[^|]*\|[^|]*tokens per second\)" | tail -n "$N_RUNS"
  echo "$log" | grep -oE "tokens per second\)" | wc -l | awk '{print "RESULT_TIMING_LINES=" $1}'
  echo "$log" | grep -oE "eval time =[^|]*(tokens per second)" | tail -n "$N_RUNS"
fi
docker stop "$CONTAINER" >/dev/null 2>&1
docker rm -f "$CONTAINER" >/dev/null 2>&1
