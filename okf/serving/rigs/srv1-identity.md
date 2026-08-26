---
type: Finding
title: "srv1 hardware identity"
id: claim-H1
description: "Claim H1 of the 2026-08-25 serving report: verified."
aliases: ["claim H1", "H1"]
tags: ["serving", "verdict:verified", "rig:srv1"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-23-cross-rig/"
---

# H1 — srv1 hardware identity

**Claim as written.** srv1 is a GTX 1660 SUPER, 6144 MiB, compute capability 7.5, driver 580.173.02, 48 GB RAM.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

Verified exactly. RAM total reads 49,351,319,552 B = 45.96 GiB = 49.35 GB, i.e. the "48 GB" nameplate (2x24 or 3x16); GPU/cc/driver match to the digit.

```bash
ssh srv1 'nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv; free -b | head -2; nproc'
```

```
name, memory.total [MiB], compute_cap, driver_version
NVIDIA GeForce GTX 1660 SUPER, 6144 MiB, 7.5, 580.173.02
               total        used        free      shared  buff/cache   available
Mem:     49351319552  2745159680   694124544    46557429760 ...
6
```

Bears on: `records/evidence/2026-08-23-cross-rig/` (host table)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
