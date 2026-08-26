---
type: Finding
title: "Thread count scales with layers on the CPU"
id: claim-L19
description: "Claim L19 of the 2026-08-25 serving report: verified."
aliases: ["claim L19", "L19"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "threads", "moe"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md:67-70"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:83-86"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:73"
---

# L19 — Thread count scales with layers on the CPU

**Claim as written.** Threads matter in proportion to layers on the CPU: srv2 (4 CPU layers) flat from -t 10 to -t 20; srv1 (28 CPU layers) gains 3.9% from -t 5 to -t 6. Under ncmoe 48 srv2 is flat past 4 threads (16 of 20 contribute nothing).

**Standing verdict: VERIFIED.**

## Evidence — srv1, srv1 arm [falsified] *(superseded below)*

The repo carries **three srv1 `-t 5` vs `-t 6` readings and they do not agree in sign**:
- `serving-sweep README.md:69` — 35B-A3B at ncmoe 28: `-t 5`->`-t 6` is **+3.9%** (the claim)
- `raw-postswap-squeeze-concurrency.txt:73` — 30B at ncmoe 40: `t=5 -> 25.82 (PEAK, shipped) | t=6 -> 25.01` = **-3.1%**
- `moe README.md:86` and `:266` — 30B at ncmoe 48: 23.49 (`t 5`) / 23.93 (`t 6`) = **+1.9%**, which that record itself then calls a tie
Since M5 now puts a quiet srv1's repeatability at **0.77%**, all three of these are outside noise and therefore *all three are real* — which means the effect is **configuration-dependent (it flips sign with `--n-cpu-moe`)**, not a general "threads matter in proportion to layers on the CPU". The claim generalises one cell. srv1 has 6 cores and no SMT, so `-t 6` leaves nothing for the server's own I/O threads; that is a plausible mechanism for the sign flip, and it is untested.

```bash
sed -n '69p' records/measurements/serving-sweep-2026-08-25/README.md
sed -n '73p' records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
```

```
srv1 (28 layers on CPU): `-t 5`->`-t 6` is +3.9%, and composed with ncmoe 28 gives 33.28
srv1 thread tune at n-cpu-moe 40 (mmap): t=4 -> 23.96 | t=5 -> 25.82 (PEAK, shipped) | t=6 -> 25.01
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:67-70` and `records/evidence/2026-08-25-moe-expert-offload/README.md:83-86`

## Evidence — srv1, srv1 arm [verified]

**Verified in direction and understated in size: +8.1%, not +3.9%. And the
opposing −3.1% reading in the repo does not reproduce — at that cell the two thread counts
are a dead tie.** Nine reloads, the two thread counts interleaved at both `--n-cpu-moe`
settings the repo disagrees about:

| cell | `-t 5` (each reload) | `-t 6` (each reload) | t6 vs t5 | record |
|---|---|---|---|---|
| **35B-A3B IQ3_XXS, ncmoe 28**, `-c 4096 -fa on` | 30.80 / 31.00 → **30.90** | 33.31 / 33.48 → **33.40** | **+8.1%** | +3.9% |
| **qwen3-coder-30b Q4_K_M, ncmoe 40**, `-c 4096 -fa on` | 25.83/25.50/25.45/25.16/25.49 → **25.49** | 25.53 / 25.57 → **25.55** | **+0.24%** | **−3.1%** |

+8.1% is 3.1x the 2.6% reload bar (M5) — solidly real. +0.24% is a tenth of the bar — a tie
by any reading. **There is no negative reading anywhere in nine reloads.** The repo's
`t=6 -> 25.01` at ncmoe 40 (`raw-postswap-squeeze-concurrency.txt:73`) sits 2.1% below my
five `-t 5` takes and 2.2% below my two `-t 6` takes; it is a single sample, and re-measured
twice the same cell comes back level.

```bash
ssh srv1 'python3 /tmp/vc.py \
 "L19-35B-nm28-t5-a|/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf|-ngl 99 --n-cpu-moe 28 -t 5 -c 4096 -fa on|1" \
 "L19-35B-nm28-t6-a|...-t 6...|1" "L19-35B-nm28-t5-b|...-t 5...|1" "L19-35B-nm28-t6-b|...-t 6...|1" \
 "L19-30b-nm40-t6-a|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 40 -t 6 -c 4096 -fa on|1" \
 "L19-30b-nm40-t5-e|...-t 5...|1" "L19-30b-nm40-t6-b|...-t 6...|1"'
```

```
L19-35B-nm28-t5-a  vram=5500  dec_p50=30.80  pp=37.7  ttft=0.292
L19-35B-nm28-t6-a  vram=5502  dec_p50=33.31  pp=41.6  ttft=0.264
L19-35B-nm28-t5-b  vram=5502  dec_p50=31.00  pp=37.5  ttft=0.293
L19-35B-nm28-t6-b  vram=5502  dec_p50=33.48  pp=41.4  ttft=0.266
L19-30b-nm40-t6-a  vram=4420  dec_p50=25.53  pp=35.8
L19-30b-nm40-t5-e  vram=4420  dec_p50=25.49  pp=34.2
L19-30b-nm40-t6-b  vram=4420  dec_p50=25.57  pp=35.9
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:67-70`;
`records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:73`
(the `t=6 -> 25.01` row, which does not reproduce); `moe README.md:83-86`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
