---
type: Finding
title: "srv2 llama-server 7B throughput at 32 slots"
id: claim-L17
description: "Claim L17 of the 2026-08-25 serving report: verified."
aliases: ["claim L17", "L17"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "throughput", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-engine-sweep/README.md:120"
---

# L17 — srv2 llama-server 7B throughput at 32 slots

**Claim as written.** srv2, 7B Q4_K_M, -np 32 -c 32768 -b 1024 -ub 1024 -fa on: 726.2 agg tok/s at n=32.

**Standing verdict: VERIFIED.**

## Evidence — srv2 [verified]

**784.6** at n=32 today, +8.0% over the recorded 726.2. The claim holds as a floor.
VRAM 6,357 MiB; `truncated=0/32`.

```bash
ssh srv2 'python3 /tmp/lcells.py "L17-7b-q4km|/blobs/sha256-60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463|-ngl 99 -np 32 -c 32768 -b 1024 -ub 1024 -fa on|32"'
```

```
L17-7b-q4km CONFIG vram=6357 slots=32 ctx_slot=1024 kv_unified=false
L17-7b-q4km n=32 agg=784.6 decode_tok_s_p50=24.75 p50_lat=19.36 ttft_p50=0.14 truncated=0/32 wall=19.4
```

Bears on: `records/evidence/2026-08-24-engine-sweep/README.md:120` (cell B2-5)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
