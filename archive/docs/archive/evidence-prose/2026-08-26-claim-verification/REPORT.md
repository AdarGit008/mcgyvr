# What survived the check — the 2026-08-25 serving report, verified

Two crews, one per rig, 2026-08-25. 51 claims. Documentation and engine source first,
then live probes, then throughput. Full evidence with commands: `srv1-findings.md`,
`srv2-findings.md`. Claim register: `CLAIMS.md`.

**Score: 26 verified · 7 falsified · 12 partial · 4 untested (51 claims).**

> **Revised 2026-08-26** after the 12 blocked GPU cells were closed on srv1. Six verdicts
> were superseded and two of the crews' own findings reversed. The sections below carry the
> final numbers; `srv1-findings.md` keeps both passes so the changes are legible.

All 45 verdict-carrying claims are OKF concepts under `okf/`, one per claim, each with its
command, its output and its source paths. Review queue: `REVIEW-QUEUE.md`.

---

## In one paragraph

The **facts** hold: the cards, drivers, image digests and model files are exactly what the
report says, and the headline speeds are real — several are even conservative. What does not
hold is a set of **explanations** the report built on top of those facts. Three of them were
used to retire earlier work, and all three are weaker than stated. Worst of all, the model of
"how noisy is this rig" is wrong on both machines and in opposite directions, which means a
lot of past results were filed as "too close to call" when they weren't, and vice versa.

---

## 1. The speeds are real, and some were understated

| what | recorded | re-measured today |
|---|---:|---:|
| srv2 vLLM best cell (1.5B, fp8 KV, 256 seqs) | 6,445 tok/s | **6,600** (+2.4%) |
| srv2 llama-server 1.5B at 128 slots | 1,396 tok/s | **1,667** (+19.4%) |
| srv2 llama-server 7B at 32 slots | 726 tok/s | **785** (+8.0%) |
| srv2 35B-A3B vs 30B, smaller quant wins | 1.49x | **1.51x** |
| the -np width correction (4 slots -> 32) | 5.67x | **5.29x** |

Six independent takes of srv2's best vLLM cell now sit within ±1.21%. **Nothing in the
report was found to be inflated.** Where it is wrong, it is wrong low.

Hardware checks out on every field: both cards, both drivers, both RAM configurations,
both pinned image digests to the character, and all three model files byte-identical
across rigs.

## 2. Three explanations do not survive

**`--no-mmap` is not worth 63% on srv2. It is worth 2-5%.**
Re-run with the page cache dropped: 43.91 tok/s with mmap against 44.82 without. The record's
mechanism — 207 MB free, 821 MB/s of disk reads during decode — describes a *different
configuration* than the one it was applied to. At `--n-cpu-moe 20` only ~7 GB stays in host
RAM, which fits 15.4 GB comfortably and never thrashes.
**Why it matters:** this figure is the reason the 2026-08-25 sweep's two cross-host
comparisons were retired as "confounded". The confound is real but small — a 2-5% flag cannot
explain a 1.95x gap. Those two comparisons deserve a re-read, not a retirement.

**`--enforce-eager` costs about 4x on srv2, not 5.02x** — and the three numbers cited for it
are the wrong cells. `518.2` is the interactivity cell, not the baseline (530.1). `181.7` is
the fp8 cell's single-stream, not the no-eager baseline's (197.1). `36.2` does not appear at
n=1 in any srv2 1.5B cell. The direction and the order of magnitude are right; the arithmetic
behind the headline is not.

**srv1 responds to three axes, not one.** The claim "exactly one of twenty" misses
`async-sched-off` (153.5), `FLEX_ATTENTION` (**116.3**) and `linear-triton` (**124.4**) — all
well outside the 2.8% band it says everything lands in. 22 cells in band, not 25.

## 3. The noise model is wrong on both rigs, in opposite directions

This is the finding with the widest reach.

| | the report says | measured |
|---|---|---|
| srv1 | varies 5-10% run to run | **12 repeats agree within 0.77%** |
| srv2, vLLM | repeats within 0.2% | **0.03%** — tighter than claimed |
| srv2, llama.cpp | repeats within 0.2% | **5.2%** between two cold loads of identical argv |

srv1 is not a noisy rig. It is a 6-core rig with **zero spare capacity** — a co-tenant process
collapses a cell 4x (33.44 -> 7.58 tok/s), and the idle server alone burns 16% of six cores.
What was recorded as "spread" was contention, and it is avoidable.

**Consequences both ways.** The "under ~10% is a tie" rule was applied across the corpus; on a
0.77% rig it discarded real effects (the non-monotone `--n-cpu-moe` edge at 1.8%, the srv1
`--no-mmap` penalty at 12%). Meanwhile llama.cpp reload noise on srv2 at 5.2% turns three
results the report treats as findings into ties: the KV-q8_0 cost (2.4%), the context result
(0.6%), and the 5.29x-vs-5.67x width gap. The record's own width sweep already showed this in
its single-stream column — 44.7 / 44.4 / 40.0 / 44.8 / 44.9 — and did not read it.

## 4. Several engine quotes are not actually in the evidence

The report quotes engine error messages as though the records hold them. They do not:

- srv1's four capability refusals (bfloat16, fp8 KV, FLASH_ATTN, FLASHINFER) **happened** — but
  the capability message is nowhere in the record. The log capture keeps only a 25-line tail
  and cut it off.
- `torch.OutOfMemoryError` for the dense 7B on srv1 appears **nowhere in the file**. Four
  refusals are confirmed; the reason is an inference. "Eager and not" was tried at one
  utilization, not three.
- `CUDA OOM` for the 32-slot srv1 cell is likewise not in the captured log.
- The 8-way-against-4-slots mechanism **is** verified live (`/slots` never exceeded 4 busy
  during a burst) — but "void" is stronger than what follows from it.

None of these refusals is fictional. The gap is between what happened and what the record can
prove, and it is a logging defect, not a measurement one.

## 5. Smaller corrections worth carrying

- **`-c` divides across slots only when `-np` is passed.** With the default 4 slots the build
  runs a unified KV cache and every slot sees the full `-c`. The report's two examples are
  right; its general sentence is not. (`-no-kvu` without `-np` is silently overridden.)
- **vLLM does have an expert-offload knob**: `--cpu-offload-params`, which documents
  `mlp.experts.w2_weight` as its own example. The real distinction is that vLLM offloads
  *weights over PCIe* while llama.cpp moves *compute to the CPU*.
- **srv1's memory bandwidth is ~18.3 GB/s**, not 26.8. The repo already carried a third figure
  (21.8). The srv2 figure reproduces (24.3 vs 23.8) but depends on thread count — 20.3 at 20
  threads — so the driver needs `OMP_NUM_THREADS` pinned.
- **Engine choice on srv1 is worth 1.94x, not 1.5x.** The smaller figure came from a
  denominator taken at a different concurrency.
- **`--n-cpu-moe` offloads the FIRST N layers** and is purely subtractive — `-ngl` is what puts
  attention and KV on the card, not `--n-cpu-moe`.
- **The ollama citation is wrong**: issue #11772 is a feature request; PR #12333 is the sharper
  reference. The mechanism claim itself holds.
- **`results.jsonl` carries fields named `score_S1` / `score_S8`.** Nothing scores quality
  anywhere in this corpus — those are tok/s x parameter count. The name invites a
  misreading.

## 6. What is still owed

**srv1: 12 GPU cells, ~60 minutes.** A leftover `llama-sweep` container from the 2026-08-25
sweep is holding 5,558 of srv1's 6,144 MiB and was never torn down, so no GPU cell could
launch. Every srv1 verdict above came from documentation, source read inside the images,
CPU-only launches, HTTP against the running server, and the records' own raw logs. Stopping
that container unblocks the re-runs.

**Five claims untested:** KV-q8_0 cost (L7), the context result (L14), srv2 thread scaling
(L19), speculative decoding (V12), and the memory-bandwidth-bound argument (M4) — M4 needs
turbo and RAPL changes the crews were forbidden to make.

Both rigs were left exactly as found: containers restored with their original argv, ollama
untouched, no host setting changed, no scratch files left.
