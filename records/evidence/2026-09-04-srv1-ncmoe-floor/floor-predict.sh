#!/usr/bin/env bash
# Predict a model's --n-cpu-moe floor from ONE probe, then let the rig judge it.
#
# The claim under test: the only VRAM term that moves with --n-cpu-moe is the
# expert weight, and that term is exact from the tensor table. Everything else
# -- scratch, cache, recurrent state, the driver's own share, and whatever
# model-specific device memory no allocator reports -- is constant in the knob,
# so ONE measurement at a known placement captures the whole lump without any
# of it having to be derived, named, or guessed.
#
#   C     = vram(ncmoe = n_layer)          <- no experts on card, so C is read directly
#   floor = n_layer - floor((free - C) * n_layer / bytes_experts)
#
# Then the rig arbitrates: floor must LOAD and floor-1 must REFUSE. A floor that
# loads one step below its prediction is a floor that was too conservative; one
# that refuses AT its prediction was too greedy. Both are failures of the method
# and both are recorded as such rather than explained away.
set -u
IMG=${IMG:?set IMG}
NAME=mcgyvr-fp
OUT=${OUT:?set OUT}
CTX=${CTX:-8192}; NP=${NP:-8}; UB=${UB:-512}

say() { printf '%s\n' "$*" | tee -a "$OUT"; }
: > "$OUT"
say "### HOST $(hostname) $(date -Is)"
say "### GPU $(nvidia-smi --query-gpu=name,memory.total,memory.reserved,driver_version --format=csv,noheader)"
say "### IMG $IMG  c=$CTX np=$NP ub=$UB"
say $'model\tn_layer\texperts_gb\tfree\tC_mib\tpredicted\tat_floor\tbelow_floor\tverdict'

launch() { # ncmoe -> echoes vram, or REFUSED
  docker rm -f $NAME >/dev/null 2>&1; sleep 2
  docker run -d --name $NAME --runtime=nvidia --gpus all -v "$HOME/models":/models \
    -p 8080:8080 "$IMG" -m "$1" --host 0.0.0.0 --port 8080 \
    --parallel "$NP" -c "$CTX" -b "$UB" -ub "$UB" -ngl 99 --n-cpu-moe "$2" -t 6 >/dev/null 2>&1
  for _ in $(seq 1 100); do
    curl -sf localhost:8080/health >/dev/null 2>&1 && {
      curl -s localhost:8080/completion -d '{"prompt":"hi","n_predict":1}' >/dev/null 2>&1
      sleep 2
      nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
      docker rm -f $NAME >/dev/null 2>&1; sleep 2; return; }
    docker ps --format '{{.Names}}' | grep -qx $NAME || break
    sleep 3
  done
  echo REFUSED; docker rm -f $NAME >/dev/null 2>&1; sleep 2
}

for M in "$@"; do
  # $M is the path INSIDE the container; the scanner runs on the host, where the
  # same file lives under $HOME/models. Feeding it the container path silently
  # scans nothing, and an empty geometry launches with --n-cpu-moe "" -- which
  # fails as a refusal and reads exactly like a model that does not fit.
  HOSTM="$HOME/models${M#/models}"
  [ -f "$HOSTM" ] || { say "$(basename $M)	-	-	-	-	-	-	-	SKIP not-on-this-rig"; continue; }
  geom=$(python3 ~/ggufscan.py "$HOSTM" | python3 -c 'import json,sys; d=json.load(sys.stdin)[0]; print(d["n_layer"], d["bytes_experts"])')
  L=${geom%% *}; E=${geom##* }
  [ "$E" = "0" ] && { say "$(basename $M)	$L	0	-	-	-	-	-	SKIP dense"; continue; }
  free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
  C=$(launch "$M" "$L")
  if [ "$C" = REFUSED ]; then
    say "$(basename $M)	$L	$(python3 -c "print(round($E/1e9,2))")	$free	-	-	-	-	SKIP no-fit-at-max-offload"; continue
  fi
  P=$(python3 -c "
import math
per=$E/$L/1024**2
print(max(0,$L-int((($free-$C))//per)))")
  A=$(launch "$M" "$P")
  B=$([ "$P" -gt 0 ] && launch "$M" $((P-1)) || echo "n/a")
  v=PASS
  [ "$A" = REFUSED ] && v="FAIL floor refused"
  [ "$B" != REFUSED ] && [ "$B" != "n/a" ] && v="FAIL below-floor loaded"
  say "$(basename $M)	$L	$(python3 -c "print(round($E/1e9,2))")	$free	$C	$P	$A	$B	$v"
done
say "### END $(date -Is) uptime_since=$(uptime -s)"
