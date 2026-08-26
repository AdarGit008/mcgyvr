---
type: Finding
title: "gpt-oss-20b will not load in b10481"
id: claim-L8
description: "Claim L8 of the 2026-08-25 serving report: verified."
aliases: ["claim L8", "L8"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "refusal"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md:80-83"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:253-254"
---

# L8 — gpt-oss-20b will not load in b10481

**Claim as written.** ollama's gpt-oss-20b blob will not load in b10481: "unknown model architecture: 'gptoss'".

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

Verified verbatim on srv1, today, against the same 13,793,422,144-byte blob. It is a GGUF-parse-time refusal — it fires before any device memory is touched, which is why it reproduces CPU-only.

```bash
ssh srv1 'docker run --rm -v /home/adaramir/ggufs:/models:ro ghcr.io/ggml-org/llama.cpp:server-cuda-b10481 \
  -m /models/gpt-oss-20b.gguf -c 512 -ngl 0 --no-warmup 2>&1 | grep -iE "architec|error"'
```

```
E llama_model_load: error loading model: unknown model architecture: 'gptoss'
E common_fit_params: encountered an error while trying to fit params to free device memory: failed to load model
E srv  llama_server: exiting due to model loading error
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:80-83` and `records/evidence/2026-08-25-moe-expert-offload/README.md:253-254`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
