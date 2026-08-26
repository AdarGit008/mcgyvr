---
type: Finding
title: "srv2's best vLLM configuration"
id: claim-V5
description: "Claim V5 of the 2026-08-25 serving report: verified."
aliases: ["claim V5", "V5"]
tags: ["serving", "verdict:verified", "engine:vllm", "throughput", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:19"
---

# V5 — srv2's best vLLM configuration

**Claim as written.** srv2's best vLLM cell is no-eager + --max-model-len 1024 + --max-num-seqs 256 + --kv-cache-dtype fp8 = 6,445.1 agg tok/s at n=256.

**Standing verdict: VERIFIED.**

## Evidence — srv2 [verified]

Reproduces and slightly exceeds: **6,600.6** and **6,602.5** on two independent
loads today, +2.4% over the recorded 6,445.1. The named cell is confirmed as the best cell
tested (it beats the same cell without fp8 by 5.4%).

```bash
ssh srv2 'python3 /tmp/vcells.py "best-fp8|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256 --kv-cache-dtype fp8|1,16,256"'
```

```
srv2  best-fp8  LAUNCH ok start_s=... vram=11805
best-fp8   n=1    202.0   p50=2.35   cap_frac=1.00
best-fp8   n=16   2808.2  p50=2.70   cap_frac=1.00
best-fp8   n=256  6600.6  p50=18.36  cap_frac=1.00
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:19` (headline table),
`srv2-1.5B-stage2.jsonl` cell `s2-noeager-kvfp8-len1024-seqs256`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
