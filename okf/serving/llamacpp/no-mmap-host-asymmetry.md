---
type: Finding
title: "--no-mmap is host-dependent, and by how much"
id: claim-L6
description: "Claim L6 of the 2026-08-25 serving report: falsified."
aliases: ["claim L6", "L6"]
tags: ["serving", "verdict:falsified", "engine:llamacpp", "memory", "rig:srv1", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:110-112"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:20,33,47"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md"
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md"
---

# L6 — --no-mmap is host-dependent, and by how much

**Claim as written.** --no-mmap is +63% on srv2 (16 GB host) and -12..-18% on srv1 (48 GB host) — same flag, opposite sign.

**Standing verdict: FALSIFIED.**

## Evidence — srv1, srv1 arm [verified]

Three matched pairs on srv1, same model (`qwen3-coder-30b`), same everything but the flag: **22.19 vs 25.21 (-12.0%)** at ncmoe 40, **20.47 vs 24.66 (-17.0%)** at 44, **18.89 vs 23.08 (-18.2%)** at 48. The range "-12..-18%" is exact, and all three gaps exceed srv1's measured quiet-box repeatability of 0.77% (M5) by more than an order of magnitude, so they are real rather than noise — a point the record could not make under its own 10% tie rule.

```bash
sed -n '47,48p' records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
```

```
## srv1 --no-mmap is consistently WORSE (keep mmap there)
  n-cpu-moe 40: 22.19 vs 25.21 mmap | 44: 20.47 vs 24.66 | 48: 18.89 vs 23.08
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:110-112`

## Evidence — srv1, srv1 arm [verified]

**Verified, and it is −17.0%, i.e. the bottom of the claimed range rather than
the −12% the raw log's own srv1 row reports.** Five reloads at the record's own cell
(`qwen3-coder-30b` Q4_K_M, `--n-cpu-moe 40`, `-t 5`, `-c 4096`, `-fa on`):

| arm | decode tok/s (per reload) | mean | vs mmap |
|---|---|---|---|
| mmap | 25.83 / 25.50 / 25.45 / 25.16 | **25.49** | — |
| `--no-mmap` | 21.41 / 20.92 | **21.17** | **−17.0%** |

The two `--no-mmap` takes were run *between* mmap takes 3 and 4, so the drift noted in M5
works against the mmap arm, not for it — the true gap is if anything slightly larger.

```bash
ssh srv1 'python3 /tmp/vc.py \
 "L6-nommap-take1|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 40 -t 5 -c 4096 -fa on --no-mmap|1" \
 "L6-nommap-take2|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 40 -t 5 -c 4096 -fa on --no-mmap|1"'
```

```
L6-nommap-take1 READY load_s=10.6 vram=4446   dec_p50=21.41  agg=21.11  ttft=0.357
L6-nommap-take2 READY load_s=7.4  vram=4446   dec_p50=20.92  agg=20.65  ttft=0.348
(mmap control, same driver run: 25.45 and 25.16)
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:20,33,47`
and `README.md` §3 (`18.89 / 20.47 / 22.19 against 23.08 / 24.66 / 25.21 at --n-cpu-moe 48/44/40`);
and claim M2, which prices this flag.

## Evidence — srv2, srv2 arm [falsified]

**Not reproduced, and not by a small margin.** At the record's own cell
(`qwen3-coder-30b` Q4_K_M, `--n-cpu-moe 20`, `-t 10`, `-c 4096`, `-fa on`), `--no-mmap` is worth

```bash
# warm pair, back to back in one driver run
ssh srv2 'python3 /tmp/lcells.py \
  "L6-nommap|/blobs/sha256-1194192cf2a187eb...|-ngl 99 -np 1 -c 4096 --n-cpu-moe 20 -t 10 -fa on --no-mmap|1" \
  "L6-mmap|/blobs/sha256-1194192cf2a187eb...|-ngl 99 -np 1 -c 4096 --n-cpu-moe 20 -t 10 -fa on|1"'
# then the decisive cold-cache arm
ssh srv2 'sync; sudo sh -c "echo 3 > /proc/sys/vm/drop_caches"; free -g; \
  python3 /tmp/lcells.py "L6-mmap-coldcache|/blobs/sha256-1194192cf2a187eb...|-ngl 99 -np 1 -c 4096 --n-cpu-moe 20 -t 10 -fa on|1"'
```

```
L6-nommap          CONFIG load_s=23.6 vram=11297
L6-nommap          n=1 agg=44.4 decode_tok_s_p50=44.82 ttft_p50=0.10 truncated=0/1
L6-mmap            CONFIG load_s=18.8 vram=11283
L6-mmap            n=1 agg=41.7 decode_tok_s_p50=42.68 ttft_p50=0.22 truncated=0/1

              total  used  free  shared  buff/cache  available
Mem:             15     0    14       0           0          14      <- cache dropped
L6-mmap-coldcache  CONFIG load_s=21.1 vram=11283
L6-mmap-coldcache  n=1 agg=43.2 decode_tok_s_p50=43.91 ttft_p50=0.12 truncated=0/1
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md` §3 and
`raw-postswap-squeeze-concurrency.txt:32`; and the CORRECTION §3 in
`records/measurements/serving-sweep-2026-08-25/README.md`, which rests on this figure.

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
