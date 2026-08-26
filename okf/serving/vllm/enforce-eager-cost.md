---
type: Finding
title: "What --enforce-eager costs, per rig"
id: claim-V1
description: "Claim V1 of the 2026-08-25 serving report: partial."
aliases: ["claim V1", "V1"]
tags: ["serving", "verdict:partial", "engine:vllm", "cuda-graphs", "rig:srv1", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:66-67"
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:19"
  - resource: "records/evidence/2026-08-24-config-sweep/srv2-1.5B.jsonl"
---

# V1 — What --enforce-eager costs, per rig

**Claim as written.** --enforce-eager costs srv2 5.02x (2,601.7 vs 518.2 agg; 181.7 vs 36.2 at n=1) and srv1 0.1% (293.6 vs 293.3).

**Standing verdict: PARTIAL.**

## Evidence — srv1, srv1 arm only [verified]

srv1 arm verified from the paired cells: `s2-noeager-len1024-seqs128` = **293.6** against `len1024-seqs128` (which carries `--enforce-eager`) = **293.3** — 0.10%, far inside srv1's own 5-10% run-to-run spread (M5), i.e. indistinguishable. The srv2 5.02x arm is the srv2 crew's.

```
len1024-seqs128            293.3   (--enforce-eager)
s2-noeager-len1024-seqs128 293.6   (no --enforce-eager)
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:66-67`

## Evidence — srv2, srv2 arm [partial]

Re-running both sides today: **3.83x** on the aggregate pair (2,699.9 vs 704.4 at
n=16) and **4.95x** at n=1 (213.7 vs 43.2). The **no-eager side reproduces** (2,699.9 vs the
record's 2,601.7, +3.8%); the **eager side does not** (704.4 vs 518.2, **+36%**). So the flag is
real and expensive on srv2 — but "5.02x" is not what a re-run gets, and the honest reading from
today's pass is **~4x**.

Separately, **both numbers V1 quotes are misattributed inside the record's own files**:
- `518.2` is the **`perf-interactivity`** cell (`--enforce-eager --performance-mode interactivity`),
  not the baseline. The baseline eager cell reads **530.1**. The README's headline row
  ("as every prior run in this tree configured it | 518.2") names the wrong cell, which flatters
  the ratio: 2601.7/530.1 = **4.91x**, not 5.02x.
- `181.7` is the n=1 reading of the **`s2-noeager-kvfp8-len1024-seqs256`** cell, not of the
  no-eager baseline (which reads **197.1**). `36.2` does not occur at n=1 in any srv2 1.5B cell
  (nearest are 36.3 `kv-fp8_e5m2` and 36.4 `no-prefix-caching`; the baseline is **34.2**).
  So "181.7 vs 36.2 at n=1" is not an eager/no-eager pair — it crosses three axes.
  The controlled n=1 pair from the record's own data is 197.1 / 34.2 = **5.76x**.

```bash
# both cells, same driver, same host, back to back
ssh srv2 'python3 /tmp/vcells.py \
  "eager-baseline|--max-model-len 8192 --gpu-memory-utilization 0.85 --max-num-seqs 16 --enforce-eager|1,8,16" \
  "noeager-baseline|--max-model-len 8192 --gpu-memory-utilization 0.85 --max-num-seqs 16|1,8,16"'
```

```
srv2  eager-baseline    LAUNCH ok start_s=78.0 vram=10219
eager-baseline   n=1   43.2    p50=11.00  cap_frac=1.00
eager-baseline   n=8   357.3   p50=10.63  cap_frac=1.00
eager-baseline   n=16  704.4   p50=10.79  cap_frac=1.00
srv2  noeager-baseline  LAUNCH ok start_s=94.4 vram=9959
noeager-baseline n=1   213.7   p50=2.22   cap_frac=1.00
noeager-baseline n=8   1544.1  p50=2.46   cap_frac=1.00
noeager-baseline n=16  2699.9  p50=2.81   cap_frac=1.00
```

```
ssh srv2 'docker logs verify-vllm 2>&1 | grep -i "Graph capturing"'
Capturing CUDA graphs (PIECEWISE): 100%|...| 7/7
Capturing CUDA graphs (FULL): 100%|...| 5/5
Graph capturing finished in 1 secs, took 0.07 GiB
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:19` and `:69-70`;
cell data in `records/evidence/2026-08-24-config-sweep/srv2-1.5B.jsonl`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
