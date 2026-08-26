---
type: Finding
title: "How well srv2's best cell repeats"
id: claim-V14
description: "Claim V14 of the 2026-08-25 serving report: verified."
aliases: ["claim V14", "V14"]
tags: ["serving", "verdict:verified", "engine:vllm", "reproducibility", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md"
---

# V14 — How well srv2's best cell repeats

**Claim as written.** Four independent takes of srv2's best 1.5B cell agree within +/-1.8% (6,445.1 / 6,452.2 / 6,480.6 / 6,562.0).

**Standing verdict: VERIFIED.**

## Evidence — srv2 [verified]

The four recorded takes do lie within +/-1.8% of their mean (6,485.0; band
6,368-6,602). Two further independent takes today — separate container loads, cold each time —
read **6,600.6** and **6,602.5**. All **six** takes now span 6,445.1-6,602.5, i.e. within

```bash
# two separate loads of the identical cell in one run of the driver
ssh srv2 'python3 /tmp/vcells.py \
  "best-fp8|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256 --kv-cache-dtype fp8|1,16,256" \
  "best-nofp8|...|1,16,256" \
  "best-fp8-take2|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256 --kv-cache-dtype fp8|1,16,256"'
```

```
best-fp8        n=1 202.0  n=16 2808.2  n=256 6600.6
best-fp8-take2  n=1 202.4  n=16 2815.7  n=256 6602.5
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md` §5

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
