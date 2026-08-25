#!/bin/bash
# Probe llama.cpp KV allocation semantics: how does -c divide across -np slots?
# Launch only, read the allocation lines, tear down. No generation.
MODEL="$1"; MDIR="$2"; shift 2
IMG=ghcr.io/ggml-org/llama.cpp:server-cuda-b10481
PORT=8095
H=$(hostname)
for cell in "$@"; do
  NP="${cell%%:*}"; rest="${cell#*:}"; CTX="${rest%%:*}"; NCM="${rest##*:}"
  docker rm -f probe >/dev/null 2>&1
  EXTRA=""
  [ "$NCM" != "0" ] && EXTRA="--n-cpu-moe $NCM"
  docker run -d --name probe --gpus all -v "$MDIR":/models:ro -p $PORT:8080 "$IMG" \
    -m "/models/$(basename "$MODEL")" -ngl 99 -np "$NP" -c "$CTX" $EXTRA \
    -fa on --no-warmup --host 0.0.0.0 --port 8080 >/dev/null 2>&1
  ok=0
  for i in $(seq 1 200); do
    curl -sf -m 3 http://localhost:$PORT/health >/dev/null 2>&1 && { ok=1; break; }
    docker ps --format '{{.Names}}' | grep -q '^probe$' || break
    sleep 2
  done
  if [ "$ok" != 1 ]; then
    echo -e "$H\tnp=$NP\tc=$CTX\tncmoe=$NCM\tFAILED\t$(docker logs probe 2>&1 | grep -iE 'error|out of memory' | tail -1 | cut -c1-90)"
    docker rm -f probe >/dev/null 2>&1; continue
  fi
  SLOTS=$(docker logs probe 2>&1 | grep -oE "n_slots = [0-9]+" | tail -1 | grep -oE "[0-9]+")
  CTXSLOT=$(docker logs probe 2>&1 | grep -oE "n_ctx_slot = [0-9]+" | tail -1 | grep -oE "[0-9]+")
  UNIF=$(docker logs probe 2>&1 | grep -oE "kv_unified = '[a-z]+'" | tail -1)
  KVMIB=$(docker logs probe 2>&1 | grep -iE "KV cache size|kv_size" | tail -1 | cut -c1-95)
  VRAM=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  echo -e "$H\tnp=$NP\tc=$CTX\tncmoe=$NCM\tslots=$SLOTS\tctx_slot=$CTXSLOT\t$UNIF\tvram=$VRAM\t$KVMIB"
  docker rm -f probe >/dev/null 2>&1
  sleep 2
done
