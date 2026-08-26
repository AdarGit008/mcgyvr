---
type: Finding
title: "srv2 hardware identity"
id: claim-H2
description: "Claim H2 of the 2026-08-25 serving report: verified."
aliases: ["claim H2", "H2"]
tags: ["serving", "verdict:verified", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/srv2-sysinfo.txt"
---

# H2 — srv2 hardware identity

**Claim as written.** srv2 is an RTX 3060, 12288 MiB, cc 8.6, driver 595.84, 16 GB RAM dual-channel (post-swap).

**Standing verdict: VERIFIED.**

## Evidence — srv2 [verified]

Exact on every field. 2 x 8 GB DDR4-2667 in ChannelA-DIMM0 and ChannelB-DIMM0 = dual channel, 16 GB.

```bash
ssh srv2 'nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv; free -g; sudo dmidecode -t memory | grep -E "Size|Locator|Configured Memory Speed"'
```

```
NVIDIA GeForce RTX 3060, 12288 MiB, 8.6, 595.84
Mem: total 15 (GiB, i.e. 16 GB)
Size: 8 GB   Locator: ChannelA-DIMM0   Configured Memory Speed: 2667 MT/s
Size: No Module Installed  Locator: ChannelA-DIMM1
Size: 8 GB   Locator: ChannelB-DIMM0   Configured Memory Speed: 2667 MT/s
Size: No Module Installed  Locator: ChannelB-DIMM1
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/srv2-sysinfo.txt`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
