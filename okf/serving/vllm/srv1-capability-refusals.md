---
type: Finding
title: "srv1's compute-capability refusals"
id: claim-V7
description: "Claim V7 of the 2026-08-25 serving report: verified."
aliases: ["claim V7", "V7"]
tags: ["serving", "verdict:verified", "engine:vllm", "refusal", "rig:srv1"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:75-80"
---

# V7 — srv1's compute-capability refusals

**Claim as written.** srv1 (cc 7.5) refuses --dtype bfloat16, --kv-cache-dtype fp8/fp8_e5m2/fp8_e4m3, --attention-backend FLASH_ATTN and FLASHINFER, each with the engine's own capability message. srv2 accepts all six.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [partial] *(superseded below)*

All six srv1 cells did refuse — `launch.ok: false`, `reason: "container exited"`. But **the claim's key qualifier is unsupported by the evidence in the repo**: the captured log for every one of the six is the same generic tail, `RuntimeError: Engine core initialization failed. See root cause above. Failed core proc(s): {}`. The harness stored only the last 25 lines, and the actual root cause — the capability message the claim asserts — is **above** that cut and was never captured. So six refusals are established; *why* they refused is not, in the record.

```bash
python3 -c '
import json,re
for l in open("records/evidence/2026-08-24-config-sweep/srv1-1.5B.jsonl"):
  r=json.loads(l); lo=r.get("launch",{})
  if not lo.get("ok",True): print(r["cell"], "|", lo["log"].strip().split(chr(10))[-1][:110])'
```

```
dtype-bfloat16    | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
kv-fp8            | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
kv-fp8_e5m2       | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
kv-fp8_e4m3       | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
attn-FLASH_ATTN   | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
attn-FLASHINFER   | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
linear-exllama / linear-torch / linear-machete / linear-cutlass : same generic tail
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:75-80`

## Evidence — srv1 [verified]

**All six refuse, and every one of them prints an explicit compute-capability
message naming the GTX 1660 SUPER and cc 7.5.** The qualifier my 2026-08-25 entry could not
support — because the config sweep's harness stored only the last 25 lines and the root cause
is above that cut — is now on the record. Six fresh launches, full container logs kept
(151–245 lines each, at `srv1:/tmp/vlogs/*.log` during the run):

| flag | start_s | the engine's own message (the `ValueError` above the generic tail) |
|---|---|---|
| `--dtype bfloat16` | 49 | `Bfloat16 is only supported on GPUs with compute capability of at least 8.0. Your NVIDIA GeForce GTX 1660 SUPER GPU has compute capability 7.5. You can use float16 instead by explicitly setting the dtype flag in CLI, for example: --dtype=half.` |
| `--kv-cache-dtype fp8` | 43 | `FP8 KV cache is not supported by the Triton attention backend on NVIDIA GeForce GTX 1660 SUPER (compute capability 7.5); native FP8 (fp8e4nv) requires SM89+. Re-run with --kv-cache-dtype float16.` |
| `--kv-cache-dtype fp8_e5m2` | 43 | *identical to the above, word for word* |
| `--kv-cache-dtype fp8_e4m3` | 43 | *identical to the above, word for word* |
| `--attention-backend FLASH_ATTN` | 43 | `Selected backend AttentionBackendEnum.FLASH_ATTN is not valid for this configuration. Reason: ['compute capability not supported']` (raised at `vllm/platforms/cuda.py:417`, `get_attn_backend_cls`) |
| `--attention-backend FLASHINFER` | 42 | `Selected backend AttentionBackendEnum.FLASHINFER is not valid for this configuration. Reason: ['compute capability not supported']` (same line) |

Each then produces the generic tail the record captured,
`RuntimeError: Engine core initialization failed. See root cause above.` — which is precisely
why the sweep's 25-line window saw nothing useful.

```bash
# /tmp/vv.sh keeps the FULL log: docker logs vvcell > /tmp/vlogs/<cell>.log
B15=Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ
BASE="--max-model-len 8192 --gpu-memory-utilization 0.85 --max-num-seqs 16 --enforce-eager"
/tmp/vv.sh V7-dtype-bfloat16  $B15 $BASE --dtype bfloat16
/tmp/vv.sh V7-kv-fp8          $B15 $BASE --kv-cache-dtype fp8         # and fp8_e5m2, fp8_e4m3
/tmp/vv.sh V7-attn-FLASH_ATTN $B15 $BASE --attention-backend FLASH_ATTN   # and FLASHINFER
# launch line matches the sweep's exactly:
# docker run -d --name vvcell --runtime=nvidia --gpus all -v $HOME/.cache/huggingface:/root/.cache/huggingface \
#   -p 8000:8000 --ipc=host -e VLLM_SERVER_DEV_MODE=1 -e FLASHINFER_DISABLE_VERSION_CHECK=1 \
#   vllm/vllm-openai:v0.26.0 <model> --port 8000 <flags>
```

```
=== V7-dtype-bfloat16.log  (151 lines)
ValueError: Bfloat16 is only supported on GPUs with compute capability of at least 8.0. Your
  NVIDIA GeForce GTX 1660 SUPER GPU has compute capability 7.5. ...
=== V7-kv-fp8.log / V7-kv-fp8_e5m2.log / V7-kv-fp8_e4m3.log  (236/235/236 lines)
ValueError: FP8 KV cache is not supported by the Triton attention backend on NVIDIA GeForce
  GTX 1660 SUPER (compute capability 7.5); native FP8 (fp8e4nv) requires SM89+. ...
=== V7-attn-FLASH_ATTN.log / V7-attn-FLASHINFER.log  (245/244 lines)
ValueError: Selected backend AttentionBackendEnum.<NAME> is not valid for this configuration.
  Reason: ['compute capability not supported']
  File "/usr/local/lib/python3.12/dist-packages/vllm/platforms/cuda.py", line 417, in get_attn_backend_cls
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:75-80` and
`srv1-1.5B.jsonl` (the six cells whose stored `launch.log` is the truncated generic tail)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
