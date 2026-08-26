---
type: Finding
title: "-c divides across slots only when -np is passed"
id: claim-L2
description: "Claim L2 of the 2026-08-25 serving report: partial."
aliases: ["claim L2", "L2"]
tags: ["serving", "verdict:partial", "engine:llamacpp", "kv-cache"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:14-26"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:224"
---

# L2 — -c divides across slots only when -np is passed

**Claim as written.** -c is a TOTAL divided across slots (-np 4 -c 4096 yields n_ctx_slot 1024; -np 16 -c 4096 yields 256).

**Standing verdict: PARTIAL.**

## Evidence — srv1 [partial]

**The two arithmetic examples are exactly right; the general sentence is not.** The division happens only when `kv_unified == false`, and b10481's *server* forces `kv_unified = true` whenever `-np` is absent. So bare `-c 4096` gives every one of the 4 default slots the FULL 4096 — no division. Measured all four cells on srv1 (CPU-only, `-ngl 0`; the KV geometry is computed before any GPU is touched):

| invocation | n_slots | n_ctx_slot | kv_unified |
|---|---|---|---|
| `-c 4096` (no `-np`) | 4 | **4096** | true |
| `-np 4 -c 4096` | 4 | **1024** | false |
| `-np 16 -c 4096` | 16 | **256** | false |
| `-c 4096 -no-kvu` (no `-np`) | 4 | **4096** | **true — the flag is silently overridden** |

```bash
ssh srv1 'bash /tmp/verify_cpubat.sh'   # docker run ... -ngl 0 --no-warmup, no --gpus, each container --rm'd
```

```
CELL L2a 7B  no -np,  -c 4096 :: LOADED  n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
CELL L2b 7B  -np 4    -c 4096 :: LOADED  n_slots = 4, n_ctx_slot = 1024, kv_unified = 'false'
CELL L2c 7B  -np 16   -c 4096 :: LOADED  n_slots = 16, n_ctx_slot = 256, kv_unified = 'false'
CELL L2d 7B  no -np, -no-kvu, -c 4096 :: LOADED  n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:14-26` (its table is right — every probe cell passed `-np` explicitly) and `records/evidence/2026-08-25-moe-expert-offload/README.md:224` (whose unqualified sentence is wrong)
Upstream: https://github.com/ggml-org/llama.cpp/blob/25ae3a9b331fffea50ff8d07a5cad34c33f1276f/tools/server/server.cpp#L151-L155

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
