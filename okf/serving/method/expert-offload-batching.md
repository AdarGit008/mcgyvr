---
type: Finding
title: "'Expert offload does not batch' is about -np 4"
id: claim-M3
description: "Claim M3 of the 2026-08-25 serving report: verified."
aliases: ["claim M3", "M3"]
tags: ["serving", "verdict:verified", "method", "moe", "concurrency"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md"
---

# M3 — 'Expert offload does not batch' is about -np 4

**Claim as written.** "Expert offload does not batch" is a statement about -np 4, not about expert offload: at 32 slots a comparable MoE reaches 5.67x rather than 2.06x.

**Standing verdict: VERIFIED.**

## Evidence — srv2 [verified]

Verified by the L11 pair above — the same model and `--n-cpu-moe` at 32 slots
batches **5.29x** (44.5 -> 235.3). The correction the record issued to its own §5 stands: the
2.06x figure is a property of llama.cpp's default slot count, not of expert offload. Latency
moves with it rather than being traded away (p50 64.6 s at np32/n32 for 32 replies, against
10.7 s for one reply at np=1 — 32x the work for 6x the wall).

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md` ("CORRECTION — the offload
rows measured a default, not a property")

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
