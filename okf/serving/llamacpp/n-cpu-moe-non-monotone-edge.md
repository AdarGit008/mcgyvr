---
type: Finding
title: "The --n-cpu-moe curve at the VRAM edge"
id: claim-L5
description: "Claim L5 of the 2026-08-25 serving report: falsified."
aliases: ["claim L5", "L5"]
tags: ["serving", "verdict:falsified", "engine:llamacpp", "moe", "search"]
status: stable
verified: { by: human:adar, at: 2026-08-25T21:47:56Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:128-142"
---

# L5 — The --n-cpu-moe curve at the VRAM edge

**Claim as written.** The --n-cpu-moe curve is NOT monotone at the edge: on srv1, ncmoe 37 (26.34) is slower than 38 (26.83) while still loading; 36 refuses.

**Standing verdict: FALSIFIED.**

## Evidence — srv1 [partial] *(superseded below)*

`README.md:132-138` gives 40->25.82, 39->26.00, **38->26.83**, 37->26.34, 36 refuses, so 37 is 1.8% below 38. Under the corrected repeatability figure (M5: 0.77% on a quiet box) **1.8% is outside noise**, which makes the non-monotonicity stronger than the record could claim under its own 10% tie rule. Two things keep this at [P]: (a) single pass per cell, so 1.8% rests on one sample each and the record's *other* srv1 thread scan at ncmoe 40 reads 25.82 for the identical cell — consistent, but the 37/38 pair has no repeat; (b) `raw-postswap-squeeze-concurrency.txt:75` states **"n-cpu-moe 36 refuses (6 GB card full); 38 was left untested - the sweep was stopped for time"**, i.e. one raw file says 38 was never run while the README tabulates a value for it. Those come from different passes, but the register should not cite 26.83 without saying which pass produced it. Not re-run — see BLOCKER.

```bash
sed -n '132,142p' records/evidence/2026-08-25-moe-expert-offload/README.md
sed -n '75p'      records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
```

```
| `--n-cpu-moe 38` | **26.83** | 5,108 |
| `--n-cpu-moe 37` | 26.34     | 5,444 |
| `--n-cpu-moe 36` | refuses   | —     |
n-cpu-moe 36 refuses (6 GB card full); 38 was left untested - the sweep was stopped for time.
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:128-142`

## Evidence — srv1 [falsified]

**The refusal half is verified; the non-monotone half does not reproduce — the
sign of the 37/38 difference reverses.** Six reloads on the record's own cell
(`qwen3-coder-30b` Q4_K_M, `-t 5`, `-c 4096`, `-fa on`, f16 KV), with 37 and 38 interleaved
so drift cannot produce the ordering:

| ncmoe | my decode tok/s (each reload) | mean | record | my card MiB | record MiB |
|---|---|---|---|---|---|
| 40 | 25.83 / 25.50 / 25.45 / 25.16 | 25.49 | 25.82 | 4,420 | 4,410 |
| 39 | 25.97 | 25.97 | 26.00 | 4,744 | 4,734 |
| 38 | 26.39 / 26.26 | **26.33** | **26.83** | 5,120 | 5,108 |
| 37 | 26.78 / 26.78 | **26.78** | 26.34 | 5,444 | 5,444 |
| 36 | **refuses** | — | refuses | — | — |

```bash
ssh srv1 'python3 /tmp/vc.py \
 "L5-nm38-a|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 38 -t 5 -c 4096 -fa on|1" \
 "L5-nm37-a|... --n-cpu-moe 37 ...|1"  "L5-nm38-b|...38...|1"  "L5-nm37-b|...37...|1" \
 "L5-nm39-a|...39...|1"  "L5-nm36|... --n-cpu-moe 36 ...|1"'
```

```
L5-nm38-a  READY vram=5120  dec_p50=26.39      L5-nm37-a  READY vram=5444  dec_p50=26.78
L5-nm38-b  READY vram=5120  dec_p50=26.26      L5-nm37-b  READY vram=5444  dec_p50=26.78
L5-nm39-a  READY vram=4744  dec_p50=25.97
L5-nm36    NOT_READY after 3.1s reason=container exited
  0.01.913.032 E ggml_backend_cuda_buffer_type_alloc_buffer: allocating 221.51 MiB on device 0: cudaMalloc failed: out of memory
  0.01.913.038 E ggml_gallocr_reserve_n_impl: failed to allocate CUDA0 buffer of size 232270080
  0.01.913.038 E graph_reserve: failed to allocate compute buffers
  0.01.914.748 E llama_init_from_model: failed to initialize the context: failed to allocate compute pp buffers
  0.01.915.180 E srv  llama_server: exiting due to model loading error
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:128-142` (§4 "The curve
is not monotone at the edge") and `raw-postswap-squeeze-concurrency.txt:95-102`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
