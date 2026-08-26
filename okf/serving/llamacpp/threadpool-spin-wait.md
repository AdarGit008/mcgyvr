---
type: Finding
title: "The threadpool spin-waits, so oversubscription collapses throughput"
id: claim-L20
description: "Claim L20 of the 2026-08-25 serving report: verified."
aliases: ["claim L20", "L20"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "threads", "contention"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:229-243"
---

# L20 — The threadpool spin-waits, so oversubscription collapses throughput

**Claim as written.** llama.cpp's threadpool spin-waits, so oversubscribing cores collapses throughput far past the oversubscription ratio (srv1: two models at -t 5 each on 6 cores = 14x slower than solo).

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified] *(superseded below)*

The raw log gives the numbers exactly: at `-t 5` each (10 threads on 6 cores, a **1.67x** oversubscription) throughput falls from 23.02/23.73 solo to **1.63/1.64** concurrent — **14x**, i.e. the collapse is ~8.4x worse than the oversubscription ratio. At `-t 3` each (6 on 6, no oversubscription) it is 1.44x slower and the combined aggregate is 28.25, which beats the best single-model cell. **I corroborated the spin-wait mechanism independently today**: with zero requests in flight, the resident llama-server holds srv1 at **16.1-16.5% of 6 cores**, i.e. it burns about one core doing nothing. That is the same behaviour that makes oversubscription catastrophic rather than merely proportional. It is also, by M5, why any co-tenant on srv1 destroys a measurement.

```bash
sed -n '158,164p' records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
ssh srv1 'top -bn2 -d2 | grep "%Cpu"'
```

```
THREAD SIZING IS EVERYTHING (i5-9600K, 6 cores, no HT):
  -t 5 each (10 threads on 6 cores):  solo 23.02 / 23.73 -> CONC 1.63 / 1.64  = 14x SLOWER
  -t 3 each (6 threads on 6 cores):   solo 20.53 / 20.18 -> CONC 14.14 / 14.11 = 1.44x slower
%Cpu(s): 16.1 us,  0.0 sy,  0.0 ni, 83.9 id      <- idle server, no requests in flight
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:229-243`

## Evidence — srv1 [verified]

**Verified by direct measurement, and the collapse is 15–18x, not 14x.** Two
different expert-offloaded MoE models, both live, both generating 475 tokens at once:

| `-t` each | threads on 6 cores | A solo (30b, ncmoe 48) | B solo (dsc-v2-16b, ncmoe 27) | A conc | B conc | collapse |
|---|---|---|---|---|---|---|
| **5** | 10 (1.67x oversubscribed) | **22.58** | **19.43** | **1.291** | **1.290** | **A 17.5x / B 15.1x** |
| **3** | 6 (exactly saturated) | **20.19** | **17.44** | **13.10** | **12.50** | **A 1.54x / B 1.40x** |

At `-t 5` a **1.67x** oversubscription costs **16.3x** aggregate (41.99 → 2.58 combined
tok/s) — the collapse is **9.8x worse than the oversubscription ratio**, which is the claim's
whole point and is if anything understated by the record's 14x. The single concurrent request
pair took **368.6 s of wall clock**; the same pair at `-t 3` took **38.5 s**.
At `-t 3` the combined aggregate is **25.60 tok/s**, which beats either model alone — so the
record's "co-residency is worth having, but only at `-t 3`" holds. (The record's combined
figure is 28.25; mine is 9% lower, and my solo figures are 2–5 tok/s below the record's too,
so the whole cell reads slightly slow today rather than the ratio being different.)

```bash
ssh srv1 'python3 /tmp/vco.py 5; python3 /tmp/vco.py 3'
# each: docker run two llama.cpp b10481 servers on ports 8091/8092 —
#   A: -m /models/qwen3-coder-30b.gguf        -ngl 99 --n-cpu-moe 48 -t <T> -c 4096 -fa on
#   B: -m /models/deepseek-coder-v2-16b.gguf  -ngl 99 --n-cpu-moe 27 -t <T> -c 4096 -fa on
# then one 475-token request to A alone, one to B alone, then both at once in two threads.
```

```
## L20/L21  -t 5 each
A(qwen3-coder-30b ncmoe48) ready=True load_s=39.6 vram=1484
B(deepseek-coder-v2-16b ncmoe27) ready=True load_s=30.5
BOTH_RESIDENT vram=3466 MiB
SOLO_B t=5 dec=19.4288  (A idle-resident)
SOLO_A t=5 dec=22.5761  (B idle-resident)
CONC  t=5 A_dec=1.29061  B_dec=1.28957  wall=368.6  loadavg=['9.99','7.85','4.52']
## L20/L21  -t 3 each
SOLO_B t=3 dec=17.4442   SOLO_A t=3 dec=20.1894
CONC  t=3 A_dec=13.0972  B_dec=12.4991  wall=38.5   loadavg=['4.25','5.34','4.14']
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:229-243` and
`raw-postswap-squeeze-concurrency.txt:158-164`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
