#!/bin/bash
# b-small through the door, 2026-09-15 (owner go). srv2: door down, door up. srv1: hand rm of the
# hand-started container, door up. A rig whose door run does not end healthy is restored to its hand launch.
set -u
W=/home/adaramir/claude/mcgyvr-emit-f4
C=/home/adaramir/.local/state/mcgyvr/compose/b-small
LOG=/tmp/claude-1000/-home-adaramir-claude-mcgyvr/3dcb25d3-9a98-4204-8da0-88dab9557425/scratchpad/bring-up-b-small.log
log() { echo "$(date -Is) $*" | tee -a "$LOG"; }
door() { (cd "$W" && env -u MCGYVR_CONFIG uv run --no-sync python -m mcgyvr.serving.run serve "$@") >> "$LOG" 2>&1; }
healthy() { for i in $(seq 1 60); do ok=1; for u in "$@"; do curl -s -m 5 -o /dev/null -w '%{http_code}' "$u" | grep -q 200 || ok=0; done; [ $ok = 1 ] && return 0; sleep 10; done; return 1; }
SRV2_3B=mcgyvr-srv2-Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001
SRV2_7B=mcgyvr-srv2-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002
restore_srv2() { log "RESTORE srv2 by hand (compose-pair)"; ssh srv2 "docker rm -f $SRV2_3B $SRV2_7B >/dev/null 2>&1; docker compose -f ~/measurements-srv2/compose-pair.yml -p mcgyvr up -d" >> "$LOG" 2>&1; }
restore_srv1() { log "RESTORE srv1 by hand (docker run, dev-run argv)"; ssh srv1 'docker rm -f mcgyvr-srv1-deepseek >/dev/null 2>&1; docker run -d --name mcgyvr-srv1-deepseek --restart unless-stopped --gpus all --network host -v /home/adaramir/models:/models:ro -v /home/adaramir/models:/home/adaramir/models:ro llamacpp:b10644-L3 --model /home/adaramir/models/moe/deepseek-coder-v2-16b.gguf --n-cpu-moe 19 --parallel 2 --port 8080 -b 512 -ub 512 -c 8192 -fa on -ngl 99 -t 6' >> "$LOG" 2>&1; }

log "== srv2: door serve down"
door down --host srv2 --compose "$C/compose.srv2.b-small.yml"; rc=$?; log "srv2 serve down rc=$rc"
if [ $rc -ne 0 ]; then
  if ssh srv2 "docker ps --format '{{.Names}}'" | grep -qx "$SRV2_7B"; then log "srv2 unchanged (pair still up); skipping srv2 up"; else restore_srv2; fi
else
  log "== srv2: door serve up"
  door up --host srv2 --compose "$C/compose.srv2.b-small.yml"; rc=$?; log "srv2 serve up rc=$rc"
  if healthy http://srv2:8001/v1/models http://srv2:8002/v1/models; then log "srv2 HEALTHY after door up"; else log "srv2 NOT healthy after door up"; restore_srv2; fi
fi

log "== srv1: hand rm of hand-started deepseek, then door serve up"
ssh srv1 'docker rm -f mcgyvr-srv1-deepseek' >> "$LOG" 2>&1; log "srv1 hand rm rc=$?"
door up --host srv1 --compose "$C/compose.srv1.b-small.yml"; rc=$?; log "srv1 serve up rc=$rc"
if healthy http://srv1:8080/health; then log "srv1 HEALTHY after door up"; else log "srv1 NOT healthy after door up"; restore_srv1; healthy http://srv1:8080/health && log "srv1 healthy after restore"; fi

log "== final"
for u in http://srv1:8080/health http://srv2:8001/v1/models http://srv2:8002/v1/models; do log "$u $(curl -s -m 5 -o /dev/null -w '%{http_code}' $u)"; done
for h in srv1 srv2; do ssh $h "docker ps --format '{{.Names}} {{.Status}} compose={{.Label \"com.docker.compose.project\"}}'; for c in \$(docker ps -q); do docker inspect -f '{{.Name}} restarts={{.RestartCount}}' \$c; done" 2>&1 | sed "s/^/$h: /" | tee -a "$LOG"; done
log ALLDONE
