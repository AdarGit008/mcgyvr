#!/usr/bin/env bash
# Identify the two terms of the VRAM model that the GGUF header cannot supply:
# the compute buffer's dependence on n_ubatch, and the CUDA context.
#
# Neither is fitted. The compute buffer is READ from the engine's own allocator
# printout at three ubatch sizes, so its shape is observed rather than assumed;
# the CUDA context is the RESIDUE once every buffer the engine reports is
# subtracted from what the driver says the card holds, which is the only way to
# see memory no allocator of llama.cpp's ever names.
#
# Everything except -ub is held fixed, so a difference between rows belongs to
# -ub alone, and a difference between rigs belongs to the driver and card.
set -u
MODEL=${MODEL:-/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf}
IMG=${IMG:?set IMG}
NAME=mcgyvr-bufprobe
OUT=${OUT:-$HOME/buffer-probe.tsv}
NCMOE=${NCMOE:-34}
CTX=${CTX:-8192}
NP=${NP:-8}

say() { printf '%s\n' "$*" | tee -a "$OUT"; }
: > "$OUT"
say "### HOST $(hostname)  $(date -Is)"
say "### GPU $(nvidia-smi --query-gpu=name,memory.total,memory.reserved,driver_version --format=csv,noheader)"
say "### IMG $IMG  MODEL $MODEL  ncmoe=$NCMOE c=$CTX np=$NP"
say $'ub\tvram_used\tmodel\tkv\trs\tcompute\tsum_reported\tcuda_ctx'

for UB in 256 512 1024; do
  docker rm -f $NAME >/dev/null 2>&1; sleep 2
  docker run -d --name $NAME --runtime=nvidia --gpus all \
    -v "$HOME/models":/models -p 8080:8080 "$IMG" \
    -m "$MODEL" --host 0.0.0.0 --port 8080 \
    --parallel "$NP" -c "$CTX" -b "$UB" -ub "$UB" -ngl 99 --n-cpu-moe "$NCMOE" -t 6 \
    --verbose >/dev/null 2>&1
  # --verbose is REQUIRED, not cosmetic: llama.cpp prints its allocator summary
  # (`CUDA0 model/KV/RS/compute buffer size`) only at that level, and without it
  # every buffer column reads 0 and the residue swallows the whole card.
  ok=0
  for _ in $(seq 1 90); do
    curl -sf localhost:8080/health >/dev/null 2>&1 && { ok=1; break; }
    docker ps --format '{{.Names}}' | grep -qx $NAME || break
    sleep 3
  done
  if [ "$ok" != 1 ]; then say "$UB	-	-	-	-	-	-	REFUSED"; docker rm -f $NAME >/dev/null 2>&1; continue; fi
  curl -s localhost:8080/completion -d '{"prompt":"hi","n_predict":1}' >/dev/null 2>&1
  sleep 2
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  L=$(docker logs $NAME 2>&1)
  # tail -1: the loader runs twice, a fit pass then the real one; the real one is last
  g() { printf '%s' "$L" | grep -E "$1" | tail -1 | grep -oE '[0-9]+\.[0-9]+' | tail -1; }
  m=$(g 'CUDA0 model buffer size'); k=$(g 'CUDA0 KV buffer size')
  r=$(g 'CUDA0 RS buffer size');    c=$(g 'CUDA0 compute buffer size')
  say "$UB	$used	${m:-0}	${k:-0}	${r:-0}	${c:-0}	$(python3 -c "print(round(${m:-0}+${k:-0}+${r:-0}+${c:-0},2))")	$(python3 -c "print(round($used-(${m:-0}+${k:-0}+${r:-0}+${c:-0}),2))")"
  docker rm -f $NAME >/dev/null 2>&1; sleep 2
done
say "### END $(date -Is) uptime_since=$(uptime -s)"
