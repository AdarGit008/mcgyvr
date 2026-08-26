---
type: Finding
title: "srv2 llama-server throughput at 128 slots"
id: claim-L16
description: "Claim L16 of the 2026-08-25 serving report: verified."
aliases: ["claim L16", "L16"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "throughput", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-engine-sweep/README.md:116"
---

# L16 — srv2 llama-server throughput at 128 slots

**Claim as written.** srv2, 1.5B Q4_K_M, -np 128 -c 131072 -no-kvu -b 2048 -ub 2048 -fa on: 1,396.4 agg tok/s at n=128.

**Standing verdict: VERIFIED.**

## Evidence — srv2 [verified]

**1,667.1** at n=128 today, **+19.4%** over the recorded 1,396.4. Direction and
configuration verified; the recorded number is low by more than any repeat spread found here,
so the cell is worth re-recording. VRAM 4,899 MiB; `truncated=0/128`.

```bash
ssh srv2 'python3 /tmp/lcells.py "L16-15b-q4km|/blobs/sha256-29d8c98fa6b098e200069bfb88b9508dc3e85586d20cba59f8dda9a808165104|-ngl 99 -np 128 -c 131072 --no-kv-unified -b 2048 -ub 2048 -fa on|128"'
```

```
L16-15b-q4km CONFIG load_s=2.3 vram=4899 slots=128 ctx_slot=1024 kv_unified=false
L16-15b-q4km n=128 agg=1667.1 decode_tok_s_p50=13.09 p50_lat=36.42 ttft_p50=0.11 truncated=0/128 wall=36.5
```

Bears on: `records/evidence/2026-08-24-engine-sweep/README.md:116` (cell B2-1)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
