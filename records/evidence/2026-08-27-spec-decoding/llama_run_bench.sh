#!/usr/bin/env bash
# usage: run_bench.sh MODEL_GGUF [DRAFT_GGUF] [N_PREDICT] [PREFIX] [PORT]
# Runs llama.cpp (server-cuda-b10481) with optional speculative decoding (-md),
# warms up, then takes 3 timed /completion measurements. Prints RESULT=... lines.
MODEL="$1"; DRAFT="$2"; N="${3:-150}"; PREFIX="${4:-base}"; PORT="${5:-8081}"
CONTAINER="llama_${PREFIX}"
docker rm -f "$CONTAINER" >/dev/null 2>&1

ARGS=( -m "/models/$(basename "$MODEL")" -ngl 99 -c 4096 -np 1 --host 0.0.0.0 --port "$PORT" )
if [ -n "$DRAFT" ]; then
  ARGS+=( -md "/draft/$(basename "$DRAFT")" --spec-draft-n-max 3 --spec-type draft-simple )
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
  curl -s -4 --max-time 120 -X POST "http://127.0.0.1:${PORT}/completion" \
    -H "Content-Type: application/json" -d "$BODY" >/dev/null 2>&1
  for r in 1 2 3; do
    RESP=$(curl -s -4 --max-time 200 -X POST "http://127.0.0.1:${PORT}/completion" \
      -H "Content-Type: application/json" -d "$BODY")
    python3 - "$r" <<PYEOF
import json,sys
r=sys.argv[1]
try:
    d=json.loads(sys.stdin.read()); t=d.get("timings") or {}
    print("RESULT={\"ok\":true,\"run\":%s,\"predicted_n\":%d,\"predicted_ms\":%.1f,\"tokens_per_sec\":%.2f}" % (r, t.get("predicted_n",0), t.get("predicted_ms",0), t.get("predicted_per_second",0)))
except Exception as e:
    print("RESULT={\"ok\":false,\"why\":\"parse\",\"err\":%r}" % str(e)[:80])
PYEOF
  done
fi

docker stop "$CONTAINER" >/dev/null 2>&1
docker rm -f "$CONTAINER" >/dev/null 2>&1
