---
type: Finding
title: "What --n-cpu-moe actually does"
id: claim-L3
description: "Claim L3 of the 2026-08-25 serving report: verified."
aliases: ["claim L3", "L3"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "moe", "placement"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:38-40"
---

# L3 — What --n-cpu-moe actually does

**Claim as written.** --n-cpu-moe N keeps attention, KV cache and embeddings on the card and puts the expert FFN weights of N layers in system RAM.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

Verified. `-ncmoe N` builds one tensor-buffer override per layer `i = 0..N-1` matching `blk.<i>\.ffn_(up|down|gate|gate_up)_(ch|)exps` and points it at the CPU buffer type. **Two corrections:** (a) it is the **first N layers**, not "N layers" anywhere; (b) it is strictly *subtractive* — it removes only expert-FFN tensors from wherever `-ngl` put them. Attention, KV and embeddings stay on the card because `-ngl` put them there, not because `-ncmoe` keeps them there. Shared-expert and dense FFN tensors (`ffn_*_shexp`, `ffn_up/down/gate` without `_exps`) do **not** match and stay on the GPU. KV is untouched by construction: overrides apply only in the model loader, while KV picks its buffer from `model.dev_layer(il)` (`src/llama-kv-cache.cpp:212-216`), which `-ncmoe` does not change.

```bash
ssh srv1 'docker run --rm --entrypoint bash ghcr.io/ggml-org/llama.cpp:server-cuda-b10481 -c "/app/llama-server --help | grep -A2 n-cpu-moe"'
```

```
-ncmoe, --n-cpu-moe N   keep the Mixture of Experts (MoE) weights of the first N layers in the CPU
                        (env: LLAMA_ARG_N_CPU_MOE)
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:38-40`
Upstream: https://github.com/ggml-org/llama.cpp/blob/25ae3a9b331fffea50ff8d07a5cad34c33f1276f/common/arg.cpp#L2727-L2741

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
