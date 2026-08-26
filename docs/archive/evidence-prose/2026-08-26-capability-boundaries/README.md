# The capability boundaries of this system, as measured

**2026-08-26, both rigs.** Fifteen cells run to find the walls rather than the winners:
where each rig stops being able to serve a model, and what the engine says when it stops.
Every refusal below is a recorded result with the engine's own sentence, not an omission.

Engines: `ghcr.io/ggml-org/llama.cpp:server-cuda-b10481` and `vllm/vllm-openai:v0.26.0` —
the digests pinned in `docs/archive/evidence-prose/2026-08-24-engine-sweep/README.md`,
unchanged and re-verified by the 2026-08-26 claim verification.

**Noise bar.** Every cell here is an across-reload comparison, so the applicable bars are
the ones that pass measured on 2026-08-26: **2.6% on srv1** and **5.2% for llama.cpp on
srv2** (`records/evidence/2026-08-26-claim-verification/`). Steady-state repeatability is
0.77%, which is *not* the bar for anything below. Differences under those bars are ties.
Protocol: 475 tokens, `ignore_eos`, temperature 0, one fixed prompt, `-c = np x ctx_slot`
(llama.cpp divides `-c` across slots). Drivers in `records/evidence/2026-08-26-capability-boundaries/drivers/`. Single pass per cell.

**This record measures emission, not capability.** Every rate is tokens produced. Nothing
here scores a model on any task. The pool reads that do measure capability (3B 0%,
7B ~19%, 14B 33.8%) are ADR-0017's and were taken on dense models; no MoE has ever been
scored on the pool.

## The four walls

1. **VRAM decides how fast, not whether.** A 35B model serves from 3,402 MiB on srv1.
   Card size sets the offload fraction and the offload fraction sets the rate.
2. **Host RAM decides whether mmap thrashes — but the asymmetry is smaller than recorded.**
   srv1 (48 GB) is 12-18% slower with `--no-mmap`; that half is exact and verified. The
   srv2 half is not: claim L6 was **falsified** on 2026-08-26 (`okf/serving/llamacpp/
   no-mmap-host-asymmetry.md`), which reads the flag at **2-5% on srv2**, not +63%. srv2's
   cells here still carry `--no-mmap` because the 2026-08-25 winners did; on the corrected
   figure that choice is close to free rather than decisive.
3. **Compute capability is a feature gate, not a speed gate.** cc 7.5 costs srv1 fp8 KV,
   bfloat16, FLASH_ATTN and FLASHINFER, which is why srv1's vLLM ceiling is ~3B dense
   while srv2's is 14B.
4. **The engine build is its own boundary.** `gpt-oss-20b` refuses on both rigs at b10481:
   `unknown model architecture: 'gptoss'`. Not VRAM, not flags.

## The boundary that decides the system's shape

**Both rigs top out at the same model class — 35B — by opposite routes.** srv1 reaches it
with 40 of 48 expert layers in system RAM (4,582 MiB of card); srv2 with 4 (11,882 MiB).
Same byte-identical GGUF, same build, each within ~400 MiB of its ceiling.

The capability envelope of this system is therefore **one model class wide, not two**. The
larger card buys rate (254.5 against 128.1 tok/s at 32 slots) and dense headroom (14B
against 3B under vLLM). It does not buy a larger model.

## srv1 — GTX 1660 SUPER, 6,144 MiB, cc 7.5

45 GB usable DDR4-3200, **dual channel but asymmetric** (16 GB rank-1 + 32 GB rank-2, one
per channel), i5-9600K, 6 cores no SMT. **Usable VRAM ceiling ~5,650 MiB** — the largest
working cell observed is 5,652 MiB.

| boundary | value | proof |
|---|---|---|
| largest model servable | **35B** (`Qwen3.6-35B-A3B` IQ3_XXS, 13.2 GB) | loads in 3,402 MiB at ncmoe 35 |
| smallest footprint, 30B MoE | **1,472 MiB** at ncmoe 48 | an 18.56 GB model on 1.5 GB of card |
| offload wall, 30B | ncmoe 37 last to load | ncmoe 36 -> model loading error |
| *(the edge is monotone)* | 37 is 1.7% **above** 38 | claim L11 falsified, `okf/serving/llamacpp/n-cpu-moe-non-monotone-edge.md` |
| offload wall, 35B | ncmoe 28 last to load | ncmoe 27 / 24 / 18 -> OOM |
| concurrency ceiling, 35B | **32 slots, only at ncmoe >= 40** | ncmoe 35 + `-np 32` -> OOM; ncmoe 40 + `-np 32` -> 4,582 MiB, ok |
| slots-vs-experts trade | ncmoe 28 buys **zero** slots | ncmoe 28 + `-np 8` and `-np 16` -> both OOM |
| concurrency ceiling, 30B | `-np 8` at ncmoe 38 | ncmoe 38 + `-np 16` -> OOM |
| dense KV budget | `np x ctx_slot ~ 16K` tokens | 7B: 32x1024, 8x4096 -> OOM; 8x8192 -> load error |
| vLLM model ceiling | **~3B dense** | 7B-AWQ -> `torch.OutOfMemoryError` at util 0.85 / 0.90 / 0.95 |
| vLLM feature floor | no fp8 KV, bf16, FLASH_ATTN, FLASHINFER | four cc 7.5 gates, `../2026-08-24-knob-surface/` |
| vLLM MoE offload | **untested** | probe died at config parse, see below |

### srv1 cells, 2026-08-26 (`srv1-llamacpp.txt`)

| model | ncmoe | -np | VRAM | n=1 | n=8 | n=16 | n=32 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 35B-A3B IQ3_XXS | 35 | 32 | — | REFUSED (cudaMalloc) | | | |
| 35B-A3B IQ3_XXS | 28 | 16 | — | REFUSED | | | |
| 35B-A3B IQ3_XXS | 28 | 8 | — | REFUSED | | | |
| **35B-A3B IQ3_XXS** | **40** | **32** | **4,582** | 26.8 | 28.0 | | **128.1** |
| qwen3-coder-30b Q4_K_M | 38 | 16 | — | REFUSED | | | |
| qwen3-coder-30b Q4_K_M | 38 | 8 | 5,490 | 25.9 | **60.6** | | |
| qwen3-coder-30b Q4_K_M | 44 | 32 | 5,652 | 24.0 | 55.6 | | 49.6 |
| deepseek-coder-v2-16b | 27 | 1 | **1,158** | 19.0 | | | |
| deepseek-coder-v2-16b | 27 | 16 | 5,208 | 19.3 | 21.4 | 21.5 | |
| deepseek-coder-v2-16b | 20 | 16 | — | REFUSED | | | |

**128.1 tok/s at n=32 is srv1's best MoE figure by 3x** (prior best 42.7 at ncmoe 35,
`-np 16`). Scaling is **4.78x**, against the 1.47x the 2026-08-25 width sweep measured —
that sweep stopped at 16 slots and never reached the width where expert reuse begins.

**The 30B turns over.** ncmoe 44 at `-np 32` reads 55.6 at n=8 and **49.6** at n=32: more
slots than the memory bus can feed.

**DeepSeek-Coder-V2-16B does not batch.** 19.3 -> 21.5 is **1.11x** across 16 slots, the
flattest curve measured on either rig, and p50 goes 24.7 s -> 353.4 s to buy it.

### The vLLM GGUF probe did not test what it was for

`records/evidence/2026-08-26-capability-boundaries/srv1-vllm-gguf-probe.txt`. Both probes died in argument handling:
`OSError: It looks like the config file at '/ggufs/qwen3-coder-30b.gguf' is not a valid
JSON file`, raised from `maybe_override_with_speculators` before any offload code ran.
**vLLM expert offload on srv1 is untested, not refused.** Loading a GGUF under vLLM needs
a separate `--tokenizer` and an HF config directory; that was not supplied.

This matters because `docs/archive/evidence-prose/2026-08-25-moe-expert-offload/README.md`
section 5 asserts "vLLM
has no `--n-cpu-moe` equivalent, so a MoE larger than the card is not a vLLM workload at
all." The declared surface captured a day earlier
(`../2026-08-24-knob-surface/declared-vllm-ffb2d59b1c05.txt`) contains
`--cpu-offload-params`, whose own help text gives `mlp.experts.w2_weight` as the example
and `experts` as a matching segment, plus `--cpu-offload-gb`, `--offload-backend
{auto,prefetch,uva}`, `--offload-group-size` and `--offload-params`. **The claim is wrong
as written.** What is true is narrower and is not established here: the mechanism exists
in the flag surface, upstream documents it as not supporting on-demand expert offload
(discuss.vllm.ai/t/expert-offloading/1880), an upstream report of
`--cpu-offload-gb --cpu-offload-params experts` on Qwen3.5-35B-A3B was closed as not
planned after three distinct crashes (vllm-project/vllm#37883), and incremental MoE
offload is an open RFC (#38256). It remains untried on this hardware.

The same defect was found independently the same day by the claim verification, which
records it as `okf/serving/vllm/expert-offload-equivalent.md`. Two passes reaching it by
different routes is the reason it is stated twice rather than merged.

## srv2 — RTX 3060, 12,288 MiB, cc 8.6

15 GB usable DDR4-2667, **dual channel and symmetric** (8 + 8 GB, both rank-1, one per
channel, two slots free), i9-10900F, 10 cores / 20 threads. **Usable VRAM ceiling
~11,900 MiB.**

| boundary | value | proof |
|---|---|---|
| largest model servable | **35B**, near-resident at ncmoe 4 -> 11,882 MiB | ncmoe 2 -> OOM, also under q8_0 KV |
| offload wall, 30B | ncmoe 20 | ncmoe 18 / 16 -> OOM |
| concurrency ceiling, 35B | 32 slots at ncmoe 25 -> 8,635 MiB | untested above 32 |
| largest dense model | **14B-AWQ, only at util 0.95** | util 0.90 -> `Engine core initialization failed` |
| host RAM wall | 16 GB against a 13.2 GB model | 821 MB/s of NVMe reads under mmap; `--no-mmap` is +63% |

### srv2 cells, 2026-08-26 (`srv2-vllm-14b.txt`, `srv2-vllm-3b.txt`)

All: no `--enforce-eager`, `--max-model-len 1024`, `--kv-cache-dtype fp8`.

| model | util | seqs | VRAM | n=1 | n=8 | n=32 | n=64 | n=128 | n=256 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 14B-AWQ | 0.90 | 256 | — | REFUSED | | | | | |
| **14B-AWQ** | 0.95 | 256 | 11,823 | 35.9 | 171.6 | 274.5 | | 307.9 | **313.5** |
| 14B-AWQ | 0.95 | 64 | 10,897 | 35.8 | 171.8 | 278.3 | 298.9 | | |
| **3B-AWQ** | 0.85 | 256 | 11,791 | 122.2 | 929.7 | 2,514.2 | | 3,237.4 | **3,497.3** |

**The 14B is KV-starved, not compute-starved.** `--max-num-seqs 64` and `256` read the
same at every shared level, and the curve flattens after n=32 (274.5 / 307.9 / 313.5).
With 9.4 GB of weights on a 12 GB card there is no KV room left for slots to matter.

## Memory subsystem, measured (`srv1-memory.txt`, `srv2-memory.txt`)

| | srv1 | srv2 |
|---|---|---|
| slots populated | 2 of 4, one per channel | 2 of 4, one per channel |
| modules | 16 GB rank-1 + 32 GB rank-2 | 8 GB + 8 GB, both rank-1 |
| channel mode | dual, **asymmetric** | dual, **symmetric** |
| configured speed | DDR4-**3200** MT/s | DDR4-**2667** MT/s |
| CPU rated speed | DDR4-2666 (XMP is on) | DDR4-2933 (**running under spec**) |
| theoretical dual-channel peak | 51.2 GB/s | 42.7 GB/s |
| **STREAM triad, 4 reps** | **19.6 GB/s** (+/-0.1) | **20.0-20.3 GB/s** (+/-0.2) |
| efficiency against theoretical | **38%** | 47% |

**The recorded 26.8 / 23.8 GB/s is already falsified.** Claim H5
(`okf/serving/rigs/memory-bandwidth.md`, 2026-08-26) reads **srv1 20.6 and srv2 24.3**,
and states the consequence: the figures invert the rigs, so the memory-channel argument —
which assumes srv1 is the faster bus — does not stand.

The four reps above are an **independent third take** and they agree on the sign: srv1 is
not ahead. They disagree on magnitude for srv2 (20.3 against H5's 24.3). Two method
differences are enough to account for it and neither side is wrong: this run compiled
`-O3 -fopenmp -march=native` and passed no size argument, H5 compiled `-O2 -fopenmp` and
passed `3.0`. **What all three takes share is the inversion**; the absolute figure needs a
pinned compile line and array size before any of them is citable.

srv1's asymmetry is the likely source of its 38%: a 16 GB and a 32 GB module put Intel
into flex mode, so 32 GB is interleaved across both channels and the remaining 16 GB runs
single-channel. srv1 has the faster RAM and the slower measured bus.

Since decode under expert offload is memory-bandwidth-bound (that record, section 2), this
is the term the MoE path rides on, and on both rigs it is a configuration state rather
than a silicon limit.

## What this record does not establish

No model was scored. No task passed or failed. The `tok/s x B` ordering used while these
cells were being chosen ranks `Qwen2.5-Coder-3B-AWQ` second of fourteen configurations at
10,807; ADR-0017 reads that model at **0%** on the #197 pool. Parameter count is not
capability, and this record's numbers cannot be turned into a capability claim.

## Files

`records/evidence/2026-08-26-capability-boundaries/srv1-llamacpp.txt` - the ten srv1 cells as printed by the driver.
`records/evidence/2026-08-26-capability-boundaries/srv1-vllm-gguf-probe.txt` - both failed probes in full.
`records/evidence/2026-08-26-capability-boundaries/srv2-vllm-14b.txt`, `srv2-vllm-3b.txt` - the srv2 cells.
`records/evidence/2026-08-26-capability-boundaries/srv1-memory.txt`, `srv2-memory.txt` - DIMM layout, four triad reps, CPU.
`records/evidence/2026-08-26-capability-boundaries/drivers/lcpsweep.py` - copied unchanged from `../2026-08-25-moe-expert-offload/width-sweep/`.
`records/evidence/2026-08-26-capability-boundaries/drivers/vllmsweep.py` - written for this run; same protocol against `/v1/completions`.
`records/evidence/2026-08-26-capability-boundaries/drivers/triad.c` - copied unchanged.

**A defect in `lcpsweep.py` this run exposed:** the REFUSED path calls `docker rm -f` and
continues with no settle time, while the success path sleeps 2 s. Three refusals fired
back to back here, so a refusal immediately following a live container could in principle
be a VRAM release race rather than a true OOM. The first refusal ran against a card
confirmed at 1 MiB and the ncmoe-40 success directly after proves the path works, but the
srv1 refusals have not been individually re-verified against an idle card.
