---
type: Finding
title: "What fp8 KV cache actually buys"
id: claim-V6
description: "Claim V6 of the 2026-08-25 serving report: partial."
aliases: ["claim V6", "V6"]
tags: ["serving", "verdict:partial", "engine:vllm", "kv-cache", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:78-84"
---

# V6 — What fp8 KV cache actually buys

**Claim as written.** fp8 KV does nothing at n=16 (558, indistinguishable from baseline) and wins at n=256 (6,445 vs 6,088): it halves bytes per token rather than speeding a kernel up.

**Standing verdict: PARTIAL.**

## Evidence — srv2 [partial]

The **n=256 half is verified**: fp8 6,600.6 against no-fp8 6,261.7 in an otherwise
identical cell, **+5.4%** — the record's +5.9% (6,445.1/6,087.7). The **n=16 half is not**. In a
properly controlled pair (same `--max-model-len 1024 --max-num-seqs 256`, fp8 the only
difference) fp8 reads **2,808.2 against 2,698.8 at n=16 — +4.1%**, which is 20x srv2's 0.2%
repeat spread and so is not "indistinguishable".

The record's own "558 at n=16" is not a controlled comparison either: 558.0 is the

```bash
ssh srv2 'python3 /tmp/vcells.py \
  "best-fp8|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256 --kv-cache-dtype fp8|1,16,256" \
  "best-nofp8|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256|1,16,256"'
```

```
best-fp8    n=1 202.0  n=16 2808.2  n=256 6600.6   (vram 11805)
best-nofp8  n=1 217.9  n=16 2698.8  n=256 6261.7   (vram 11085)
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:78-84`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
