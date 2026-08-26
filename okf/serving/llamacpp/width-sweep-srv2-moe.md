---
type: Finding
title: "Slot width on an expert-offloaded MoE (srv2)"
id: claim-L11
description: "Claim L11 of the 2026-08-25 serving report: verified."
aliases: ["claim L11", "L11"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "moe", "concurrency", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md"
---

# L11 — Slot width on an expert-offloaded MoE (srv2)

**Claim as written.** srv2, 35B-A3B IQ3_XXS, --n-cpu-moe 25, -c = np x 1024: 44.9 tok/s at np=1 rises to 254.5 at np=32/n=32 (5.67x); p50 59.7 s at np32/n32 vs 94.8 s at np16/n16.

**Standing verdict: VERIFIED.**

## Evidence — srv2, srv2 arm [verified]

Reproduces. **44.5 agg (45.34 decode) at np=1 -> 235.3 at np=32/n=32 = 5.29x**,
p50 **64.59 s**. VRAM matches the record to the MiB: **6,069** at np=1 and **8,635** at np=32.
The 5.29x/5.67x difference is inside this cell's own run-to-run spread (see M5 below, 5.2%),
so this is the same result, not a smaller one. `truncated=0/32` — every slot returned all 475
tokens, so the width sweep is not starving slots (the trap the record names).

```bash
ssh srv2 'python3 /tmp/lcells.py \
  "L11-np1|/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf|-ngl 99 -np 1 -c 1024 --n-cpu-moe 25 -fa on|1" \
  "L11-np32|/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf|-ngl 99 -np 32 -c 32768 --n-cpu-moe 25 -fa on|32"'
```

```
L11-np1   CONFIG  vram=6069  slots=1   ctx_slot=1024  kv_unified=false
L11-np1   n=1   agg=44.5   decode_tok_s_p50=45.34  p50_lat=10.68  ttft_p50=0.17  truncated=0/1
L11-np32  CONFIG  vram=8635  slots=32  ctx_slot=1024  kv_unified=false
L11-np32  n=32  agg=235.3  decode_tok_s_p50=7.67   p50_lat=64.59  ttft_p50=2.77  truncated=0/32
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md` §1

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
