#!/bin/bash
SCR="$(cd "$(dirname "$0")" && pwd)"   # this record's own directory
LIVE=$HOME/.mcgyvr/config
wake () { # host port file container label
  local host=$1 port=$2 file=$3 cname=$4 label=$5 start now
  DOCKER_HOST=ssh://$host docker compose -p mcgyvr -f "$file" up -d --force-recreate >/dev/null 2>&1
  start=$(ssh -o BatchMode=yes $host "docker inspect -f '{{.State.StartedAt}}' $cname" 2>/dev/null)
  for i in $(seq 1 300); do
    if [ "$(curl -s -m3 -o /dev/null -w %{http_code} http://$host:$port/v1/models 2>/dev/null)" = 200 ]; then
      now=$(date -u +%Y-%m-%dT%H:%M:%S)
      python3 -c "
import datetime as dt
a=dt.datetime.fromisoformat('$start'[:19]); b=dt.datetime.fromisoformat('$now')
print('$label WAKE = %.0fs' % (b-a).total_seconds())"
      return 0
    fi
    sleep 3
  done
  echo "$label WAKE >900s (gave up)"; return 1
}

echo "== leg 1: srv2 7B vLLM alone, cold (the per-unit baseline nobody ever took)"
DOCKER_HOST=ssh://srv2 docker compose -p mcgyvr -f $LIVE/compose.srv2.yml down >/dev/null 2>&1
sleep 5
wake srv2 8002 $SCR/compose.srv2-7b-only.yml mcgyvr-srv2-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002 "srv2-7B-AWQ-vllm-alone"
DOCKER_HOST=ssh://srv2 docker compose -p mcgyvr -f $SCR/compose.srv2-7b-only.yml down >/dev/null 2>&1
sleep 5

echo "== leg 2: srv2 ceiling, Qwen3-Next-80B-A3B Q3_K_M, 35.7GB, llama.cpp CPU offload"
wake srv2 8003 $SCR/compose.srv2-80b.yml mcgyvr-srv2-Qwen3-Next-80B-A3B-Instruct-Q3_K_M-8003 "srv2-Qwen3Next-80B-A3B"
DOCKER_HOST=ssh://srv2 docker compose -p mcgyvr -f $SCR/compose.srv2-80b.yml down >/dev/null 2>&1
sleep 5

echo "== restoring srv2 live pair"
DOCKER_HOST=ssh://srv2 docker compose -p mcgyvr -f $LIVE/compose.srv2.yml up -d >/dev/null 2>&1
echo "MEASUREMENT COMPLETE"
