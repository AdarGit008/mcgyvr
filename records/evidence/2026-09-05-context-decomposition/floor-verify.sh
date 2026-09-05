#!/usr/bin/env bash
# Walk `--n-cpu-moe` down at a context that was never probed, and see whether
# the predicted floor is where the engine actually refuses.
#
# The prediction under test came from ONE launch at `-c 8192` plus the header's
# KV law -- nothing at this context, and nothing at any placement below 24. If
# the floor lands where predicted, context is accounted for by arithmetic and a
# context change no longer costs a probe.
#
# The refusal is the measurement (okf/must-read/touching-rigs.md): a launch near
# the memory edge is a 1-in-3 coin flip, so every REFUSED cell is retried three
# times before it is believed.
set -u
IMG=${IMG:?}; MODEL=${MODEL:?}; CTX=${CTX:?}; NP=${NP:-8}; UB=${UB:-256}
NS=${NS:?"space-separated --n-cpu-moe values, high to low"}
RETRY=${RETRY:-3}
TAG=$(basename "$MODEL" .gguf)
DIR=$HOME/floorverify/$TAG-c$CTX; mkdir -p "$DIR"
OUT=$DIR/readings.tsv; NAME=mcgyvr-floorverify
say() { printf '%s\n' "$*" | tee -a "$OUT"; }
: > "$OUT"
say "### HOST $(hostname) $(date -Is) uptime_since=$(uptime -s)"
say "### GPU $(nvidia-smi --query-gpu=name,memory.total,memory.reserved,driver_version --format=csv,noheader)"
say "### IMG $IMG  MODEL $MODEL  c=$CTX np=$NP ub=$UB"
say $'ncmoe\ttry\tidle\tfree_before\tvram\tstatus\tlogfile'
for N in $NS; do
  for T in $(seq 1 "$RETRY"); do
    docker rm -f $NAME >/dev/null 2>&1; sleep 4
    idle=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    freeb=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
    LOG=$DIR/n${N}-t${T}.log
    docker run -d --name $NAME --runtime=nvidia --gpus all \
      -v "$HOME/models":/models -p 8080:8080 "$IMG" \
      -m "$MODEL" --host 0.0.0.0 --port 8080 \
      --parallel "$NP" -c "$CTX" -b "$UB" -ub "$UB" -ngl 99 --n-cpu-moe "$N" -t 6 \
      --verbose >/dev/null 2>&1
    ok=0
    for _ in $(seq 1 120); do
      curl -sf localhost:8080/health >/dev/null 2>&1 && { ok=1; break; }
      docker ps --format '{{.Names}}' | grep -qx $NAME || break
      sleep 3
    done
    if [ "$ok" != 1 ]; then
      docker logs $NAME > "$LOG" 2>&1
      say "$N	$T	$idle	$freeb	-	REFUSED	$(basename "$LOG")"
      docker rm -f $NAME >/dev/null 2>&1; continue
    fi
    curl -s localhost:8080/completion -d '{"prompt":"hi","n_predict":1,"seed":1}' >/dev/null 2>&1
    sleep 3
    v=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    docker logs $NAME > "$LOG" 2>&1
    say "$N	$T	$idle	$freeb	$v	OK	$(basename "$LOG")"
    docker rm -f $NAME >/dev/null 2>&1
    break   # an OK needs no retry; the coin flip is only on the refusal side
  done
done
docker rm -f $NAME >/dev/null 2>&1
say "### END $(date -Is) uptime_since=$(uptime -s)"
