---
type: Finding
title: "srv1's dense 7B turns over at 8 slots"
id: claim-L12
description: "Claim L12 of the 2026-08-25 serving report: partial."
aliases: ["claim L12", "L12"]
tags: ["serving", "verdict:partial", "engine:llamacpp", "concurrency", "rig:srv1"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:52-58"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:53-62"
  - resource: "width-sweep/srv1-7B-IQ4XS.txt:13"
---

# L12 — srv1's dense 7B turns over at 8 slots

**Claim as written.** srv1, 7B IQ4_XS: width peaks at 8 slots (128.4); 16 slots is SLOWER (106.3); 32 slots refuses with CUDA OOM.

**Standing verdict: PARTIAL.**

## Evidence — srv1 [partial] *(superseded below)*

The turnover is in the raw log exactly as claimed — **128.4 at np=8/n=8, 128.7 at np=16/n=8, 106.3 at np=16/n=16**, with `truncated=0/N` on every level so it is not an EOS artefact. Note the peak is a *concurrency* peak, not a slot-count peak: at n=8 the np=16 server is marginally *faster* (128.7) than the np=8 one; what falls off is running 16 concurrent requests, not owning 16 slots. **"CUDA OOM" is not what the log captured** — the refusal line is a `ggml_cuda_error` backtrace frame, and the harness's grep truncated at 110 characters before the message itself. The refusal is real and it is on the CUDA error path; the words "out of memory" are not in the recorded evidence.

```
np=8  ... n=8  agg=128.4  p50=29.59  truncated=0/8
np=16 ... n=8  agg=128.7  p50=29.52  truncated=0/8
np=16 ... n=16 agg=106.3  p50=71.48  truncated=0/16
np=32 ... REFUSED  /app/libggml-cuda.so(_Z15ggml_cuda_errorPKcS0_S0_iS0_+0xb5)[0x7799d62230a5]
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:52-58`

## Evidence — srv1 [partial]



```bash
ssh srv1 'python3 /tmp/vc.py \
 "L12-L13-np32-c32768|/models/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf|-ngl 99 -np 32 -c 32768 -fa on --no-warmup|32" \
 "L13-np16-c16384|...-np 16 -c 16384...|16" "L12-np8-c8192|...-np 8 -c 8192...|8"'
```

```
L12-L13-np32-c32768 NOT_READY after 3.1s reason=container exited
  0.02.563.453 I cmn          init: llama threadpool init, n_threads = 6
  /app/ggml/src/ggml-cuda/ggml-cuda.cu:106: CUDA error
  0.02.574.226 E CUDA error: out of memory
  0.02.574.229 E   current device: 0, in function ggml_cuda_kernel_can_use_pdl at /app/ggml/src/ggml-cuda/common.cuh:1630
  0.02.574.229 E   cudaFuncGetAttributes(&attr, kernel)
  ... ggml_abort -> quantize_row_q8_1_cuda -> ggml_cuda_mul_mat_vec_q
      -> llama_decode -> common_context_can_seq_rm -> server_context_impl::load_model
L13-np16-c16384 READY load_s=3.0 vram=4852   n=16 agg=97.44  wall=78.0s  ok=16/16
L12-np8-c8192   READY load_s=3.0 vram=4404   n=8  agg=128.60 wall=29.6s ok=8/8   dec_p50=16.46
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:53-62`
and `width-sweep/srv1-7B-IQ4XS.txt:13`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
