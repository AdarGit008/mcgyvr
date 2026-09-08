#!/bin/bash
# srv1 A/B, take 2. The first attempt measured nothing: gate 5 refuses to
# overwrite an envelope, every `serve` call after the first pair was REFUSED,
# and the script both ignored the exit status and grepped the message away, so
# all three "arms" measured one process that never restarted.
# This one checks every exit status, moves each envelope aside deliberately
# before the door writes a new one, and asserts the container's StartedAt moved.
set -uo pipefail
CFG=$HOME/.mcgyvr/config
SCR=/tmp/claude-1000/-home-adaramir-claude-mcgyvr/b915e087-afc2-4bf5-b964-b6ce4ed97fa9/scratchpad
EV=/home/adaramir/claude/mcgyvr/records/evidence/2026-09-08-live-srv1
UNMAPPED=$SCR/emit/compose.srv1.yml
MAPPED=$CFG/compose.srv1.yml.bak-20260908-185213
CONTAINER=mcgyvr-srv1-Qwen3.6-35B-A3B-UD-IQ3_XXS-8080
cd /home/adaramir/claude/mcgyvr || exit 1

started () { ssh -o BatchMode=yes srv1 "docker inspect $CONTAINER --format '{{.State.StartedAt}}'" 2>/dev/null; }

door () {  # up|down label
  local dir=$1 label=$2
  [ -f "$EV/serve-$dir.json" ] && mv "$EV/serve-$dir.json" "$EV/serve-$dir-$label.json"
  uv run --no-sync python -m mcgyvr.serving.run serve "$dir" --host srv1 \
    --compose $CFG/compose.srv1.yml --suffix "$label" > "$SCR/door-$dir-$label.log" 2>&1
  local rc=$?
  if [ $rc -ne 0 ]; then
    echo "DOOR FAILED ($dir/$label, rc=$rc):"; tail -3 "$SCR/door-$dir-$label.log"; exit 1
  fi
  grep -E "up after|serve-down:" "$SCR/door-$dir-$label.log"
}

arm () {  # composefile label
  local file=$1 label=$2 before after i
  before=$(started)
  door down "$label-down"
  cp "$file" $CFG/compose.srv1.yml
  door up "$label-up"
  after=$(started)
  if [ "$before" = "$after" ]; then echo "NOT RESTARTED ($label): StartedAt still $before"; exit 1; fi
  echo "$label: restarted, StartedAt $before -> $after"
  ssh -o BatchMode=yes srv1 "docker inspect $CONTAINER --format '{{json .Config.Cmd}}'" | grep -o '"--load-mode","[a-z]*"' || echo "$label: no --load-mode in argv (mapped)"
  for i in 0 1 2 3; do
    curl -s -m 600 http://srv1:8080/completion -H 'Content-Type: application/json' \
      -d '{"prompt":"Write a Python function that merges two sorted lists.","n_predict":160,"temperature":0,"cache_prompt":false}' \
    | python3 -c "
import sys,json
d=json.load(sys.stdin); t=d['timings']
print('%-8s %-20s decode %6.2f tok/s' % ('$label', 'warm-up (discarded)' if '$i'=='0' else 'sample $i', t['predicted_per_second']))"
  done
  ssh -o BatchMode=yes srv1 'free -m | awk "/Mem:/{printf \"'"$label"': RAM used %d MiB, avail %d MiB, cache %d MiB\n\", \$3, \$7, \$6}"'
}

arm "$MAPPED"   "mmap"
arm "$UNMAPPED" "none"
arm "$MAPPED"   "mmap2"
arm "$UNMAPPED" "none2"
echo "A/B COMPLETE; srv1 left serving unmapped"
