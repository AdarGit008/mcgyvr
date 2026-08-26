---
type: Finding
title: "A cgroup memory cap does not simulate a smaller machine"
id: claim-M8
description: "Claim M8 of the 2026-08-25 serving report: verified."
aliases: ["claim M8", "M8"]
tags: ["serving", "verdict:verified", "method", "defect", "memory"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:118-126"
---

# M8 — A cgroup memory cap does not simulate a smaller machine

**Claim as written.** A cgroup --memory cap does not simulate a smaller machine when the file is already in the host page cache (the invalid docker --memory=15g cell).

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

Verified by direct demonstration. A 4,218,473,248-byte GGUF already resident in srv1's host page cache was streamed end to end inside a container capped at `--memory=1g`. It **did not OOM**, and the container's own cgroup charged **6,029,312 bytes — 0.14% of the file, 0.56% of the cap**. Page cache pages already charged outside the container are *not* re-charged on access, so the cap never binds and the cell measures nothing about a smaller machine. This is exactly the defect in the `--memory=15g` cell (31.55 capped vs 31.43 uncapped, i.e. "no penalty").

```bash
ssh srv1 '
  cat /home/adaramir/ggufs/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf > /dev/null   # warm HOST page cache
  grep -E "^(Cached|MemFree):" /proc/meminfo
  docker run --rm --memory=1g --memory-swap=1g -v /home/adaramir/ggufs:/models:ro ubuntu:24.04 \
    bash -c "cat /models/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf > /dev/null;
             echo cgroup memory.peak = \$(cat /sys/fs/cgroup/memory.peak) cap = \$(cat /sys/fs/cgroup/memory.max)"'
```

```
MemFree:         1022716 kB
Cached:         43538476 kB
cgroup memory.peak = 6029312 bytes  (cap = 1073741824)
container exit ok, no OOM kill
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:118-126`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
