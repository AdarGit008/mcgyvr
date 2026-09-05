#!/usr/bin/env bash
# Walk --n-cpu-moe down from the derived floor until the launch refuses.
# The refusal is the measurement: it names the true edge, which the derivation
# only predicts. Runs ON the rig and tees as it goes, because a hard lock takes
# the ssh pipe with it and an untee'd row is a row that never happened.
set -u
MODEL=/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf
IMG=llamacpp:b10644-L3
NAME=mcgyvr-floor
OUT=$HOME/srv1-ncmoe-floor.tsv
PROMPT='Write a detailed explanation of how a mixture-of-experts transformer routes tokens.'
NPRED=475

say() { printf '%s\n' "$*" | tee -a "$OUT"; }
: > "$OUT"
say "### START $(date -Is)"
say "### RIG $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | xargs) mem=$(free -g | awk '/^Mem:/{print $2}')G PL1=$(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw)"
say "### GPU $(nvidia-smi --query-gpu=name,memory.total,memory.reserved,driver_version --format=csv,noheader)"
say "### IMG $IMG  uptime_since=$(uptime -s)"

for N in "$@"; do
  docker rm -f $NAME >/dev/null 2>&1
  sleep 3
  docker run -d --name $NAME --runtime=nvidia --gpus all \
    -v "$HOME/models":/models -p 8080:8080 "$IMG" \
    -m "$MODEL" --host 0.0.0.0 --port 8080 \
    --parallel 8 -c 8192 -ngl 99 --n-cpu-moe "$N" -t 6 >/dev/null 2>&1

  ok=0
  for _ in $(seq 1 100); do
    curl -sf localhost:8080/health >/dev/null 2>&1 && { ok=1; break; }
    docker ps --format '{{.Names}}' | grep -qx $NAME || break
    sleep 3
  done

  if [ "$ok" != 1 ]; then
    tail=$(docker logs $NAME 2>&1 | grep -E ' E |error|OOM|out of memory' | tail -2 | tr '\n' '|')
    say "srv1	ncmoe=$N	REFUSED	$tail"
    docker rm -f $NAME >/dev/null 2>&1
    continue
  fi

  vram=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  rss=$(docker stats --no-stream --format '{{.MemUsage}}' $NAME | cut -d/ -f1 | xargs)
  # warm the model, then time one request and eight concurrent ones
  curl -s localhost:8080/completion -d "{\"prompt\":\"$PROMPT\",\"n_predict\":32}" >/dev/null

  s1=$(curl -s localhost:8080/completion \
       -d "{\"prompt\":\"$PROMPT\",\"n_predict\":$NPRED}" \
       | python3 -c 'import json,sys; print(round(json.load(sys.stdin)["timings"]["predicted_per_second"],2))' 2>/dev/null)

  t0=$(date +%s.%N)
  for _ in $(seq 1 8); do
    curl -s localhost:8080/completion \
      -d "{\"prompt\":\"$PROMPT\",\"n_predict\":$NPRED}" >/dev/null &
  done
  wait
  t1=$(date +%s.%N)
  s8=$(python3 -c "print(round(8*$NPRED/($t1-$t0),2))")

  say "srv1	ncmoe=$N	OK	vram=$vram	rss=$rss	n1=$s1	n8_agg=$s8	up=$(uptime -s)"
  docker rm -f $NAME >/dev/null 2>&1
  sleep 3
done

say "### END $(date -Is) uptime_since=$(uptime -s) PL1=$(cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw)"
