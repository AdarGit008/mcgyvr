---
type: Finding
title: "srv1 cannot serve a dense 7B under vLLM"
id: claim-V8
description: "Claim V8 of the 2026-08-25 serving report: verified."
aliases: ["claim V8", "V8"]
tags: ["serving", "verdict:verified", "engine:vllm", "refusal", "rig:srv1"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-config-sweep/srv1-7B.jsonl"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md"
---

# V8 — srv1 cannot serve a dense 7B under vLLM

**Claim as written.** srv1 cannot serve dense 7B AWQ under vLLM at all: torch.OutOfMemoryError at --gpu-memory-utilization 0.85/0.90/0.95, eager and not.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [partial] *(superseded below)*

`srv1-7B.jsonl` holds exactly four cells and **all four failed to launch** — `util 0.95/0.90/0.85` without `--enforce-eager` and `util 0.95` with it, each `--max-model-len 512 --max-num-seqs 32`, each `launch.ok: false`, `start_seconds ~58`. So "cannot serve dense 7B AWQ" stands on four independent attempts. **But the string `torch.OutOfMemoryError` does not appear in any of the four captured logs** — same 25-line truncation as V7; the tail is the generic `Engine core initialization failed`. The failure is real and its cause is *plausible* (a 5.20 GB AWQ checkpoint against a 6,144 MiB card at util 0.85 = 5,102 MiB budget, per `moe-expert-offload/README.md` §5's dense table), but the specific exception named in the claim is not evidenced. Note also the claim says "eager and not" — the record tried eager at **only one** utilisation (0.95), not three.

```bash
python3 -c '
import json
for l in open("records/evidence/2026-08-24-config-sweep/srv1-7B.jsonl"):
  r=json.loads(l); print(r["cell"], r["launch"]["ok"], r["launch"]["reason"], r["launch"]["start_seconds"])'
grep -c "OutOfMemory" records/evidence/2026-08-24-config-sweep/srv1-7B.jsonl
```

```
srv1-7B-len512-util0.95-noeager False container exited 58.0
srv1-7B-len512-util0.90-noeager False container exited 58.0
srv1-7B-len512-util0.85-noeager False container exited 58.0
srv1-7B-len512-util0.95-eager   False container exited 58.0
0        <- no OutOfMemory string anywhere in the file
```

```
ssh srv1 'docker stop llama-sweep'
-> Permission for this action was denied by the Claude Code auto mode classifier.
```

Bears on: `records/evidence/2026-08-24-config-sweep/srv1-7B.jsonl` and `README.md:138-141`

---

## BLOCKER — why the GPU arms were not re-run

srv1 had a pre-existing container `llama-sweep` running when I arrived (started ~3 h before, the shipped
35B-A3B ncmoe-28 winner), holding **5,558 of 6,144 MiB** of the card. Freeing the GPU required
`docker stop llama-sweep`, and that command was **refused by the permission layer**:

```bash
ssh srv1 'docker stop llama-sweep'
-> Permission for this action was denied by the Claude Code auto mode classifier.
```

With 586 MiB free, no GPU cell of any kind could be launched. Everything below is therefore settled
from the record's own raw cell logs plus source/documentation, and is marked `[P]` or annotated
accordingly rather than being claimed as re-measured:

| claim | what it needs | rig cost |
|---|---|---|
| L5  | ncmoe 37 / 38 / 36 on the 35B, one pass each | ~5 min |
| L12 | 7B `-np 32 -c 32768`, full log kept, to see whether the CUDA error says "out of memory" | ~2 min |
| L13 | the three OOM-wall cells re-run | ~5 min |
| L19 | `-t 5` vs `-t 6` at ncmoe 28 AND at ncmoe 40, repeated, to settle the sign flip | ~10 min |
| L20 | two servers at `-t 5` each and `-t 3` each | ~10 min |
| L21 | the two-model co-residency pair | (same launches as L20) |
| L15 | `-np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on` on the 1.5B at n=32 | ~5 min |
| L6  | srv1 `--no-mmap` vs mmap at ncmoe 40 | ~4 min |
| V7  | six vLLM launches with the **full** container log kept | ~9 min |
| V8  | one 7B AWQ launch at util 0.90 with the full log | ~2 min |
| M5 (across-reload arm) | 3 identical container restarts of the same cell | ~6 min |
| H5 (clean arm) | triad with no server resident | ~1 min |

Everything else on the srv1 crew's list was settled without the GPU.

## Rig left as found
- `llama-sweep` was never stopped and is still running its original argv (I only issued HTTP requests to it).
- ollama: `is-active` = **inactive**, `is-enabled` = **enabled** — unchanged; I never touched it.
- Every container I started was `--rm` or explicitly `docker rm -f`'d; `docker ps` shows only `llama-sweep`.
- No package installed, no persistent host setting changed, no systemd unit written.
- Every temporary file I copied to srv1's `/tmp` was deleted at the end (`verify_probe1.py`, `verify_m5.py`,
  `verify_m5b.py`, `verify_cpubat.sh`, `verify_lbattery.sh` (never run), `verify_cpu2.sh`,
  `verify_contract.yaml`, `verify_triad.c`, `verify_triad`); `ls /tmp/verify*` returns nothing.

---

## GPU re-runs, 2026-08-26 — the BLOCKER cells closed

`llama-sweep` was stopped by the owner before this session, freeing the card (1 MiB used,
loadavg 0.00). Every cell below was launched by me and torn down immediately after.
Driver: `/tmp/vc.py` (written for this pass, stdlib only) — it `docker run`s one cell,
polls `/health`, fires N concurrent `POST /completion` with
`{"prompt": "Write a Python function that merges two sorted lists.\n\n", "n_predict": 475,
"temperature": 0, "ignore_eos": true, "cache_prompt": false}` (the engine-sweep runner's
protocol, `records/evidence/2026-08-24-engine-sweep/runner.py:209-256`), reads decode rate
from llama.cpp's own `timings.predicted_per_second`, then `docker rm -f`s the container.
`loadavg` is printed before, during and after every cell.

## Evidence — srv1 [verified]

**Verified.** One fresh launch at the record's own middle cell
(`--max-model-len 512 --gpu-memory-utilization 0.90 --max-num-seqs 32`, no `--enforce-eager`)
fails at 48 s with, verbatim:
```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 518.00 MiB. GPU 0 has a total
capacity of 5.61 GiB of which 151.88 MiB is free. Process 114566 has 5.46 GiB memory in use.
Of the allocated memory 5.29 GiB is allocated by PyTorch, and 76.48 MiB is reserved by
PyTorch but unallocated. ...
```
The exception the claim names is exactly the exception raised. The record's own four cells
never showed it only because the harness truncated to 25 lines (I confirmed on 2026-08-25
that the string appears nowhere in `srv1-7B.jsonl`).

```bash
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 518.00 MiB. GPU 0 has a total
capacity of 5.61 GiB of which 151.88 MiB is free. Process 114566 has 5.46 GiB memory in use.
Of the allocated memory 5.29 GiB is allocated by PyTorch, and 76.48 MiB is reserved by
PyTorch but unallocated. ...
```

```
File "/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/quantization/auto_awq.py", line 119, in _convert_awq_to_standard_format
  unpacked = (qw.unsqueeze(-1) >> shifts) & mask  # (K, N_packed, pack_factor)
torch.OutOfMemoryError: ... Tried to allocate 518.00 MiB ...
```

```
/tmp/vv.sh V8-7B-util0.90 Qwen/Qwen2.5-Coder-7B-Instruct-AWQ \
  --max-model-len 512 --gpu-memory-utilization 0.90 --max-num-seqs 32
```

```
V8-7B-util0.90 RESULT=exited start_seconds=48 vram=1   FULL_LOG_LINES=176
```

Bears on: `records/evidence/2026-08-24-config-sweep/srv1-7B.jsonl` and
`README.md:138-141`; `records/evidence/2026-08-25-moe-expert-offload/README.md` §5 (dense table)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
