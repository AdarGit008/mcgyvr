#!/bin/bash
# Quick elimination check, 2026-09-15. usage: bash drive.sh srv1|srv2
# 10 function_implementation + 10 bug_fix per arm (bench-py, bench-ts), greedy only (--draws 0),
# cap 2048. Ids: random.Random(20260915).sample over pinned_bench_ids() per task type; same ids both arms.
# Owner approved stopping the live units on both rigs for the window; they are restarted on exit.
set -u
HOST=$1
REPO=/home/adaramir/claude/mcgyvr
OUT=$REPO/records/measurements/quick-check-2026-09-15
LOG=$OUT/$HOST.drive.log
NAME=mcgyvr-quickcheck
PORT=8090
VLLM_IMG=vllm/vllm-openai:v0.26.0
IDS=b007-cent-split,b030-date-span,b094-relay-chain,b258-lap-best,b345-hour-rate,b379-hide-values,b417-mark-list,b423-scan-tally,b488-root-digit,b496-span-letters,b033-till-session,b046-rest-harvest,b073-bump-release,b080-brace-fill,b112-net-tally,b200-fleet-hops,b266-span-merge,b281-tier-cost,b351-vat-back,b443-fold-ends

# kind|source|file|ngl rungs (walked down until the server is healthy)
SMALL=(
  "lcpp|Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF|qwen2.5-coder-0.5b-instruct-q4_k_m.gguf|99"
  "lcpp|Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF|qwen2.5-coder-1.5b-instruct-q4_k_m.gguf|99"
  "lcpp|Schnuckade/LFM-2.5-Coder-2.6B|LFM2.5-2.6B.Q4_K_M.gguf|99"
  "lcpp|bunnycore/MiniCPM5-2B-Code-lora|MiniCPM5-2B.Q8_0.gguf|99"
  "lcpp|janhq/Jan-code-4b-gguf|Jan-code-4b-Q4_K_M.gguf|99"
  "lcpp|jica98/qwen3.5-4B-super-coder|qwen3.5-4B-super-coder.Q4_0.gguf|99"
  "lcpp|h3rb3rn/moe-expert-coder-4b|moe-expert-coder-4b-Q4_K_M.gguf|99"
)
case $HOST in
  srv1)
    IMG=llamacpp:b10644-L3
    THREADS=6
    STOP="docker stop mcgyvr-srv1-deepseek"
    START="docker start mcgyvr-srv1-deepseek"
    LIVE_URLS="http://srv1:8080/health"
    MODELS=("${SMALL[@]}")
    ;;
  srv2)
    IMG=ghcr.io/ggml-org/llama.cpp:server-cuda-b10644
    THREADS=10
    STOP="docker compose -f ~/measurements-srv2/compose-pair.yml -p mcgyvr stop"
    START="docker compose -f ~/measurements-srv2/compose-pair.yml -p mcgyvr up -d"
    LIVE_URLS="http://srv2:8001/v1/models http://srv2:8002/v1/models"
    MODELS=(
      "lcpp|apto-as/Qwen2.5-Coder-7B-Instruct-Q5_K_M-GGUF|qwen2.5-coder-7b-instruct-q5_k_m.gguf|99"
      "lcpp|yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF|gemma4-coding-Q4_K_M.gguf|99"
      "lcpp|projectj/Instinct-Python-Coder-Gemma4-12B-GLM5.2|Instinct-Python-Coder-Gemma4-12B-GLM5.2-Q8_0.gguf|99 44 40 36 32"
      "vllm|Qwen/CodeQwen1.5-7B-AWQ|-|-"
      "vllm|TheBloke/CodeLlama-7B-Instruct-GPTQ|-|-"
      "${SMALL[@]}"
    )
    ;;
  *) echo "usage: bash drive.sh srv1|srv2" >&2; exit 2 ;;
esac

log() { echo "$(date -Is) $*" | tee -a "$LOG"; }
rig() { ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOST" "$@"; }
stamp() {
  log "STAMP $1 $(rig 'echo PL1=$(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw 2>/dev/null) PL2=$(cat /sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw 2>/dev/null) boot=$(uptime -s); nvidia-smi --query-gpu=memory.total,memory.reserved,memory.used,memory.free --format=csv,noheader; free -m | sed -n 2p; docker ps --format "{{.Names}}"' | tr '\n' ' ')"
}
restore() {
  rig "docker rm -f $NAME >/dev/null 2>&1; $START" >> "$LOG" 2>&1 && log "RESTART_ISSUED $START"
  for url in $LIVE_URLS; do
    healthy=""
    for i in $(seq 1 90); do
      curl -s -m 5 -o /dev/null -w '%{http_code}' "$url" | grep -q 200 && { healthy=1; break; }
      sleep 10
    done
    [ -n "$healthy" ] && log "LIVE_HEALTHY $url" || log "LIVE_NOT_HEALTHY $url after 900s"
  done
  stamp end
}
wait_healthy() {
  for i in $(seq 1 90); do
    curl -s -m 5 -o /dev/null -w '%{http_code}' "http://$HOST:$PORT/health" | grep -q 200 && return 0
    [ "$(rig "docker inspect -f '{{.State.Running}}' $NAME 2>/dev/null")" = "true" ] || return 1
    sleep 10
  done
  return 1
}

mkdir -p "$OUT/$HOST"
stamp start
rig "$STOP" >> "$LOG" 2>&1 && log "STOPPED $STOP"
trap restore EXIT
stamp after-stop

cd "$REPO"
for entry in "${MODELS[@]}"; do
  IFS='|' read -r kind src file rungs <<< "$entry"
  tag=$(echo "$src" | tr / _)
  if [ "$kind" = lcpp ]; then marker="DONE $src $file"; else marker="DONE $src"; fi
  for i in $(seq 1 180); do
    rig "grep -qxE '.* $marker' ~/models-pull-2026-09-15.log" && break
    sleep 20
  done
  rig "grep -qxE '.* $marker' ~/models-pull-2026-09-15.log" || { log "SKIP $tag download not done after 1h"; continue; }

  ok=""
  if [ "$kind" = lcpp ]; then
    path=/home/adaramir/models/.incoming/$tag/$file
    for ngl in $rungs; do
      cmd="docker rm -f $NAME >/dev/null 2>&1; docker run -d --name $NAME --runtime=nvidia --gpus all --network host -v /home/adaramir/models:/home/adaramir/models:ro $IMG -m $path --host 0.0.0.0 --port $PORT --parallel 1 -c 8192 -ngl $ngl -t $THREADS -fa on"
      log "LAUNCH $tag img=$IMG ngl=$ngl"
      echo "$cmd" > "$OUT/$HOST/$tag.launch.txt"
      rig "$cmd" >/dev/null
      if wait_healthy; then ok=1; break; fi
      log "NOT_HEALTHY $tag ngl=$ngl"
      rig "docker logs --tail 40 $NAME" > "$OUT/$HOST/$tag.ngl$ngl.launch-fail.log" 2>&1
    done
  else
    cmd="docker rm -f $NAME >/dev/null 2>&1; docker run -d --name $NAME --runtime=nvidia --gpus all --network host --ipc=host -e HF_HUB_OFFLINE=1 -v /home/adaramir/.cache/huggingface:/root/.cache/huggingface $VLLM_IMG $src --served-model-name $tag --max-model-len 8192 --max-num-seqs 1 --port $PORT --gpu-memory-utilization 0.90"
    log "LAUNCH $tag img=$VLLM_IMG"
    echo "$cmd" > "$OUT/$HOST/$tag.launch.txt"
    rig "$cmd" >/dev/null
    if wait_healthy; then ok=1; else log "NOT_HEALTHY $tag"; rig "docker logs --tail 60 $NAME" > "$OUT/$HOST/$tag.launch-fail.log" 2>&1; fi
  fi
  if [ -z "$ok" ]; then rig "docker rm -f $NAME >/dev/null 2>&1"; log "DOWN $tag never healthy"; continue; fi

  log "VRAM $tag $(rig 'nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader')"
  for tier in bench-py bench-ts; do
    log "RUN $tag $tier"
    uv run --no-sync python tools/breadth/measure.py \
      --endpoint "http://$HOST:$PORT" --protocol openai --model "$tag" \
      --tier "$tier" --tasks "$IDS" --draws 0 --max-output-tokens 2048 \
      --out "$OUT/$HOST/$tag/$tier" > "$OUT/$HOST/$tag.$tier.stdout" 2>&1
    rc=$?
    log "EXIT $tag $tier rc=$rc $(tail -3 "$OUT/$HOST/$tag.$tier.stdout" | tr '\n' ' ' | cut -c1-300)"
  done
  rig "docker logs $NAME" > "$OUT/$HOST/$tag.server.log" 2>&1
  rig "docker rm -f $NAME >/dev/null"
  log "DOWN $tag"
done
log ALLDONE
