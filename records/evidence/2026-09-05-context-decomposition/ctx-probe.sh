#!/usr/bin/env bash
# Does the compute buffer move with -c, and is any of it repeatable?
#
# The 2026-09-04 probes were all `-c 8192`, so `C`'s context term was measured
# once and never varied. Everything downstream of "one probe fixes C for every
# placement" rests on the untested claim that the ONLY term that moves with
# context is the KV cache.
#
# Three departures from buffer-probe.sh, each because that script lost data:
#
#  1. NOTHING IS PARSED HERE. The full container log is kept per cell and the
#     arithmetic is done off-rig. `grep ... | tail -1` silently kept one of the
#     TWO `CUDA0 KV buffer size` lines an SWA model prints, which put gpt-oss's
#     KV 192.00 MiB low and its "CUDA context" 192.00 MiB high. A parse that
#     runs on the rig cannot be corrected without spending the rig again.
#  2. EVERY cell runs three times. A figure that is not identical across three
#     loads of the same config is not a measurement.
#  3. The idle baseline is read BEFORE each launch, after the previous
#     container tears down -- not once at the top. It is the number every
#     reading is net of.
set -u
IMG=${IMG:?set IMG}; MODEL=${MODEL:?set MODEL}
NCMOE=${NCMOE:?}; NP=${NP:-8}; UB=${UB:-256}; REPS=${REPS:-3}
CTXS=${CTXS:-"2048 4096 8192 16384"}
TAG=$(basename "$MODEL" .gguf)
DIR=$HOME/ctxprobe/$TAG; mkdir -p "$DIR"
OUT=$DIR/readings.tsv
NAME=mcgyvr-ctxprobe

say() { printf '%s\n' "$*" | tee -a "$OUT"; }
: > "$OUT"
say "### HOST $(hostname) $(date -Is) uptime_since=$(uptime -s)"
say "### GPU $(nvidia-smi --query-gpu=name,memory.total,memory.reserved,driver_version --format=csv,noheader)"
say "### IMG $IMG"
say "### DIGEST $(docker image inspect "$IMG" -f '{{index .RepoDigests 0}}{{.Id}}' 2>/dev/null)"
say "### MODEL $MODEL bytes=$(stat -c %s "${MODEL/\/models/$HOME/models}" 2>/dev/null) ncmoe=$NCMOE np=$NP ub=$UB"
say "### PL1 $(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw 2>/dev/null || echo n/a)"
say $'ctx\trep\tidle_used\tvram_min\tvram_max\tfree_before\tstatus\tlogfile'

for CTX in $CTXS; do
for REP in $(seq 1 "$REPS"); do
  docker rm -f $NAME >/dev/null 2>&1; sleep 4
  # after teardown: the only moment that shows what the next launch gets
  idle=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  freeb=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
  LOG=$DIR/c${CTX}-r${REP}.log
  docker run -d --name $NAME --runtime=nvidia --gpus all \
    -v "$HOME/models":/models -p 8080:8080 "$IMG" \
    -m "$MODEL" --host 0.0.0.0 --port 8080 \
    --parallel "$NP" -c "$CTX" -b "$UB" -ub "$UB" -ngl 99 --n-cpu-moe "$NCMOE" -t 6 \
    --verbose >/dev/null 2>&1
  ok=0
  for _ in $(seq 1 100); do
    curl -sf localhost:8080/health >/dev/null 2>&1 && { ok=1; break; }
    docker ps --format '{{.Names}}' | grep -qx $NAME || break
    sleep 3
  done
  if [ "$ok" != 1 ]; then
    docker logs $NAME > "$LOG" 2>&1
    say "$CTX	$REP	$idle	-	-	$freeb	REFUSED	$(basename "$LOG")"
    docker rm -f $NAME >/dev/null 2>&1; continue
  fi
  # deterministic settle: one completion, then five samples 200 ms apart.
  # min != max means the card was still moving and the row is not a reading.
  curl -s localhost:8080/completion -d '{"prompt":"hi","n_predict":1,"seed":1}' >/dev/null 2>&1
  sleep 3
  lo=999999; hi=0
  for _ in 1 2 3 4 5; do
    u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    [ "$u" -lt "$lo" ] && lo=$u; [ "$u" -gt "$hi" ] && hi=$u
    sleep 0.2
  done
  docker logs $NAME > "$LOG" 2>&1
  say "$CTX	$REP	$idle	$lo	$hi	$freeb	OK	$(basename "$LOG")"
  docker rm -f $NAME >/dev/null 2>&1
done
done
docker rm -f $NAME >/dev/null 2>&1
say "### END $(date -Is) uptime_since=$(uptime -s) PL1 $(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw 2>/dev/null || echo n/a)"
