---
type: Finding
title: "srv1's KV budget is the product np x ctx_slot"
id: claim-L13
description: "Claim L13 of the 2026-08-25 serving report: verified."
aliases: ["claim L13", "L13"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "kv-cache", "rig:srv1", "refusal"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:60-68"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:78-88"
---

# L13 — srv1's KV budget is the product np x ctx_slot

**Claim as written.** srv1's KV budget is the PRODUCT np x ctx_slot ~ 16K tokens: np32x1024 and np8x4096 both OOM, np16x1024 loads at 4,852 MiB.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

The raw per-cell log confirms all three, and adds a fourth cell in the same direction. Two cells with the *same product* (32,768) refuse from opposite factorings, and the 16,384 cell loads — that is the product, not either factor.

```bash
cat records/evidence/2026-08-25-moe-expert-offload/width-sweep/srv1-7B-IQ4XS.txt
```

```
srv1  7B-IQ4XS np=16 ctx_slot=1024 c=16384  CONFIG  real_ctx_slot=1024  vram=4852
srv1  7B-IQ4XS np=32 ctx_slot=1024 c=32768  REFUSED  /app/libggml-cuda.so(_Z15ggml_cuda_errorPKcS0_S0_iS0_+0xb5)
srv1  7B-IQ4XS np=8  ctx_slot=4096 c=32768  REFUSED  /app/libggml-cuda.so(_Z15ggml_cuda_errorPKcS0_S0_iS0_+0xb5)
srv1  7B-IQ4XS np=8  ctx_slot=8192 c=65536  REFUSED  E srv  llama_server: exiting due to model loading error
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:60-68`

## Evidence — srv1 [verified]

**All four cells reproduce exactly**, including the VRAM figure to the MiB.
The product rule holds: both 32K-token cells refuse, the 16K cell loads.

```bash
 "L13-np8-c32768|/models/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf|-ngl 99 -np 8 -c 32768 -fa on --no-warmup|8" \
 "L13-np8-c65536|/models/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf|-ngl 99 -np 8 -c 65536 -fa on --no-warmup|8"
```

```
L13-np8-c65536 NOT_READY after 3.1s reason=container exited
  0.01.305.716 E ggml_backend_cuda_buffer_type_alloc_buffer: allocating 3584.00 MiB on device 0: cudaMalloc failed: out of memory
  0.01.305.722 E alloc_tensor_range: failed to allocate CUDA0 buffer of size 3758096384
  0.01.306.660 E llama_init_from_model: failed to initialize the context: failed to allocate buffer for kv cache
  0.01.307.421 E srv  llama_server: exiting due to model loading error
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:78-88`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
