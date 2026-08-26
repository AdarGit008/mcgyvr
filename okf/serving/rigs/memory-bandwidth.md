---
type: Finding
title: "Measured memory bandwidth per rig"
id: claim-H5
description: "Claim H5 of the 2026-08-25 serving report: falsified."
aliases: ["claim H5", "H5"]
tags: ["serving", "verdict:falsified", "rig:srv1", "rig:srv2", "bandwidth"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:16:17Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:9"
  - resource: "records/headers/2026-08-22-cpu-offload.json:30"
  - resource: "records/evidence/2026-08-23-cross-rig/"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:10"
---

# H5 — Measured memory bandwidth per rig

**Claim as written.** STREAM triad bandwidth: srv1 26.8 GB/s, srv2 23.8 GB/s post-swap (was 13.3 pre-swap).

**Standing verdict: FALSIFIED.**

## Evidence — srv1 [falsified] *(superseded below)*

I re-ran the record's **own unmodified driver** (`drivers/triad.c`, checksum-verified so the loop is not elided) on srv1 today and got **18.3 and 18.1 GB/s** — **32% below the recorded 26.8**. Two takes, `best`-of-5 internally, 6 threads.

```bash
scp records/evidence/2026-08-25-moe-expert-offload/drivers/triad.c srv1:/tmp/verify_triad.c
ssh srv1 'gcc -O2 -fopenmp -o /tmp/verify_triad /tmp/verify_triad.c && /tmp/verify_triad 3.0 && /tmp/verify_triad 3.0'
```

```
STREAM triad: 18.3 GB/s  (threads=6, best=0.0327 s, checksum=3.500)
STREAM triad: 18.1 GB/s  (threads=6, best=0.0331 s, checksum=3.500)
```

```
ssh srv1 'top -bn2 -d2 | grep "%Cpu"'    # with only the idle llama-server resident
%Cpu(s): 16.1 us,  0.0 sy,  0.0 ni, 83.9 id
%Cpu(s): 16.5 us,  0.2 sy,  0.0 ni, 83.2 id
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:9` and `README.md:94` · `records/headers/2026-08-22-cpu-offload.json:30`

## Evidence — srv1, srv1 clean arm [falsified]

**Not reproduced at any thread count, with the card idle and no server resident.**
Best-of over `OMP_NUM_THREADS` 1/2/3/4/5/6 is **20.6 GB/s** (t=2); the box's full 6 threads
give **18.5–18.7**. The recorded 26.8 is **30% above the best reading the campaign's own
driver produces on a quiet srv1**. The third figure in the repo, 21.8 GB/s
(`records/headers/2026-08-22-cpu-offload.json:30`), is the closest of the three and is still
6% above best-of. The previous crew's 18.3/18.1 — taken *with* `llama-sweep` resident — is
now explained: it is the 5–6-thread reading, and a co-tenant was not the cause.

```bash
scp records/evidence/2026-08-25-moe-expert-offload/drivers/triad.c srv1:/tmp/vtriad.c
ssh srv1 'gcc -O2 -fopenmp -o /tmp/vtriad /tmp/vtriad.c
          for t in 1 2 3 4 5 6; do OMP_NUM_THREADS=$t /tmp/vtriad 3.0; done'
```

```
STREAM triad: 19.2 GB/s  (threads=1, best=0.0312 s, checksum=3.500)
STREAM triad: 20.6 GB/s  (threads=2, best=0.0291 s, checksum=3.500)   <- best-of   (19.7, 19.3 on repeats)
STREAM triad: 19.4 GB/s  (threads=3, best=0.0309 s, checksum=3.500)   (18.9 on repeat)
STREAM triad: 19.3 GB/s  (threads=4, best=0.0311 s, checksum=3.500)
STREAM triad: 18.7 GB/s  (threads=5, best=0.0321 s, checksum=3.500)
STREAM triad: 18.5 GB/s  (threads=6, best=0.0324 s, checksum=3.500)
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:9`
(`srv1: 26.8 GB/s (was 26.8)`), `records/evidence/2026-08-23-cross-rig/`,
`records/headers/2026-08-22-cpu-offload.json:30`

## Evidence — srv2, srv2 arm [verified] *(superseded below)*

24.3 GB/s best-of at 4 threads — within 2% of the recorded 23.8. But the
figure is **thread-count dependent** and the record does not state the thread count:
24.3 (t=4) / 23.0 (t=8) / 22.2 (t=10) / 20.3-21.1 (t=20). Reading it at the host's full
20 threads gives 20.3, which is 15% below the recorded number. The claim is verified
against the best-of reading; the record should pin `OMP_NUM_THREADS`.

```bash
scp records/evidence/2026-08-25-moe-expert-offload/drivers/triad.c srv2:/tmp/
ssh srv2 'gcc -O2 -fopenmp -o /tmp/triad /tmp/triad.c && for t in 4 8 10 20; do OMP_NUM_THREADS=$t /tmp/triad 3.0; done'
```

```
STREAM triad: 24.3 GB/s  (threads=4,  best=0.0247 s, checksum=3.500)
STREAM triad: 23.0 GB/s  (threads=8,  best=0.0261 s, checksum=3.500)
STREAM triad: 22.2 GB/s  (threads=10, best=0.0271 s, checksum=3.500)
STREAM triad: 20.3 GB/s  (threads=20, best=0.0295 s, checksum=3.500)
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:10`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
