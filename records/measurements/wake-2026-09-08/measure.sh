#!/bin/bash
# N7 ceiling: time a cold start of the biggest small-active MoE each rig holds.
SCR="$(cd "$(dirname "$0")" && pwd)"   # this record's own directory
LIVE=$HOME/.mcgyvr/config

wake () {  # host port composefile label
  local host=$1 port=$2 file=$3 label=$4
  local t0 t1
  DOCKER_HOST=ssh://$host docker compose -p mcgyvr -f "$file" up -d --force-recreate >/dev/null 2>&1
  t0=$(date +%s.%N)
  for i in $(seq 1 240); do
    if [ "$(curl -s -m3 -o /dev/null -w %{http_code} http://$host:$port/v1/models 2>/dev/null)" = 200 ]; then
      t1=$(date +%s.%N); echo "$label WAKE $(echo "$t1-$t0"|bc)s"; return 0
    fi
    sleep 2
  done
  echo "$label WAKE >480s (gave up)"; return 1
}

echo "--- taking both rigs down ---"
DOCKER_HOST=ssh://srv1 docker compose -p mcgyvr -f $LIVE/compose.srv1.yml down >/dev/null 2>&1
DOCKER_HOST=ssh://srv2 docker compose -p mcgyvr -f $LIVE/compose.srv2.yml down >/dev/null 2>&1
sleep 5

echo "--- srv1 ceiling: KAT-Coder-V2.5-Dev Q3_K_M, 35.5B/A3B, 16.9GB ---"
wake srv1 8080 $SCR/compose.srv1-kat.yml "srv1-kat-q3km"
DOCKER_HOST=ssh://srv1 docker compose -p mcgyvr -f $SCR/compose.srv1-kat.yml down >/dev/null 2>&1

echo "--- srv2 ceiling: Qwen3-Next-80B-A3B Q3_K_M, 79.7B/A3B, 35.7GB ---"
wake srv2 8003 $SCR/compose.srv2-80b.yml "srv2-qwen3next-80b"
DOCKER_HOST=ssh://srv2 docker compose -p mcgyvr -f $SCR/compose.srv2-80b.yml down >/dev/null 2>&1

echo "--- baseline for contrast: srv2's 7B alone, cold ---"
export SCR
python3 - <<'PY'
import yaml,pathlib,os
live=pathlib.Path(os.environ['HOME'])/'.mcgyvr/config/compose.srv2.yml'
d=yaml.safe_load(live.read_text())
k=[n for n in d['services'] if '7B' in n][0]
s=d['services'][k]; s.pop('depends_on',None)
out=pathlib.Path(os.environ['SCR'])/'compose.srv2-7b-only.yml'
out.write_text(yaml.safe_dump({'services':{k:s}}, sort_keys=False))
PY
wake srv2 8002 $SCR/compose.srv2-7b-only.yml "srv2-7b-vllm-alone"
echo "MEASUREMENT COMPLETE"
