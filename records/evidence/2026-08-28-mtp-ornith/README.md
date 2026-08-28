# MTP at concurrency, the ncmoe floor, and Ornith-1.0-35B — a new Key 1 (2026-08-28)

**Question.** Push the open MTP levers from `2026-08-28-kat-coder`: (1) is native MTP's
+13%/+22% single-slot only, or does it hold at concurrency and long context? (2) does
`Ornith-1.0-35B` (the offmonreal sibling with higher draft acceptance) beat KAT's MTP?

**Answer.** Three findings, one of which flips Key 1:

1. **The prior `ncmoe=28` was over-offloading by ~3.5×.** The Q2_K-AllGPU MTP file needs
   only **8** of 40 expert layers on CPU to fit the 12 GB card (MTP head included). At
   `ncmoe=8` the single-slot number is **~91 tok/s**, not 57.5 — the 2026-08-28 report
   undersold its own model by 1.6×.
2. **MTP is NOT single-slot only on the fast card** — it holds and even widens at
   concurrency (srv2), but it **regresses at concurrency on the offload-bound card**
   (srv1), exactly offmonreal's own warning. Acceptance stays high at long context on
   srv2 (0.73–0.80 @ 8.5K-token prompt), not the "51%" the card fears for KAT.
3. **Ornith-1.0-35B + MTP @ ncmoe=8 is the new Key 1: 91.2 tok/s × 35 = 3,192**, beating
   North-Mini-Code (90.3 × 30 = 2,709) by **+17.8%** — and it needs the graft: without
   MTP, Ornith's 72.1 tok/s loses to North.

## Protocol

Same as the 2026-08-28 sweeps: llama.cpp `server-cuda` **b10644** (stock image, no fork),
475-token replies, `ignore_eos`, temperature 0, short prompt
("Write a Python function that merges two sorted lists."), `-c = n × 1024`.
Driver `mtpsweep2.py` extends `mtpsweep.py` with a concurrency ladder (baseline `nmax=0`
vs `--spec-type draft-mtp --spec-draft-n-max 2`) and a long-context mode. Draft acceptance
is read from the completion response `timings.draft_n_accepted / draft_n`.

- srv2 (RTX 3060, 12 GB): `Q2_K-AllGPU` MTP files (~14.0 GB), `ncmoe` swept 4→28.
- srv1 (GTX 1660 SUPER, 6 GB / 45 GB): `Q3_K_M` MTP files (~18.1 GB), `ncmoe=40`.

## 1. The ncmoe floor — why last week's 57.5 was 1.6× too low (srv2)

`Ornith-1.0-35B_Q2_K-AllGPU` single-slot, MTP `nmax=2`:

| ncmoe | baseline tok/s | MTP tok/s | acceptance |
|---|---|---|---|
| 4 | 77.8 | REFUSED | — |
| **8** | 68.6 | **92.2** | 0.902 |
| 12 | 62.1 | 85.0 | 0.913 |
| 16 | 61.3 | 80.4 | 0.972 |
| 20 | 58.2 | 72.3 | 0.925 |
| 24 | 45.9 | 69.2 | 0.972 |
| 28 | 51.1 | 62.3 | 0.913 |

- `ncmoe=4` baseline loads but **MTP REFUSED** (`cudaMalloc failed`): the grafted head is
  ~1 GB, so the floor for *MTP* is `ncmoe=8`.
- Every extra offloaded layer costs ~2–3 tok/s. The 2026-08-28 kat-coder run used `ncmoe=28`
  and reported 50.8→57.5; the **same file at ncmoe=8 is 68.6→92.2**. The earlier report's
  headline was an offload artifact, not a property of the model.

## 2. Concurrency — MTP holds on the fast card, regresses on the offload-bound card

### srv2 · Q2_K-AllGPU @ ncmoe=8 (baseline → MTP nmax=2)

| n | KAT baseline | KAT MTP | KAT acc | Ornith baseline | Ornith MTP | Ornith acc |
|---|---|---|---|---|---|---|
| 1 | 70.3 | 88.9 (+26.5%) | 0.851 | 72.1 | **91.2 (+26.5%)** | 0.902 |
| 2 | 100.7 | 115.7 (+14.9%) | 0.783 | 104.2 | **127.1 (+22.0%)** | 0.905 |
| 4 | 126.2 | REFUSED | — | 127.9 | REFUSED | — |
| 8 | 162.2 | REFUSED | — | 164.2 | REFUSED | — |
| 16 | 215.9 | REFUSED | — | 219.3 | REFUSED | — |

- **MTP is not single-slot only** — it wins at n=1 *and* n=2 on srv2 (+15–26%).
- The **wall moves to the KV cache**: at `ncmoe=8` the MTP head's extra ~1 GB pushes the
  c=n×1024 KV cache over the 12 GB card at n≥4 (`cudaMalloc failed`). For concurrency ≥4 you
  must raise `ncmoe`, which is slower — MTP's win and high concurrency trade off on a 12 GB
  card. Baseline (no MTP) still scales to 215.9/219.3 @ n=16 at ncmoe=8.

For reference, at `ncmoe=28` (deep offload) MTP held at n=4 and n=8 too (110.4 @4, 128.0 @8
for KAT) — but from a much lower baseline, so the absolute throughput is still below the
ncmoe=8 n=2 peak.

### srv1 · Q3_K_M @ ncmoe=40 (baseline → MTP nmax=2)

| n | KAT baseline | KAT MTP | KAT acc | Ornith baseline | Ornith MTP | Ornith acc |
|---|---|---|---|---|---|---|
| 1 | 32.8 | 37.1 (+13.1%) | 0.831 | 32.7 | **39.4 (+20.5%)** | 0.919 |
| 2 | 27.7 | 23.6 (−14.8%) | 0.836 | 27.1 | 24.4 (−10.0%) | 0.945 |
| 4 | 40.6 | 29.9 (−26.4%) | 0.849 | 40.2 | 30.2 (−24.9%) | 0.835 |
| 8 | 48.1 | 39.5 (−17.9%) | 0.829 | 47.2 | 41.4 (−12.3%) | 0.905 |

- **On the offload-bound card MTP wins only at n=1 and regresses at n≥2** — even Ornith's
  0.91–0.95 acceptance can't save it. The 6 GB card is CPU-expert-bandwidth-bound, so the
  draft head's extra GPU compute contends with offload instead of saving forwards. This is
  offmonreal's own "~50% slowdown on heavy-CPU-offload" warning, reproduced.

## 3. Long context — acceptance holds, MTP win holds (srv2, ctx=16384, ~8.5K-token prompt)

| model | baseline tok/s | MTP tok/s | acceptance |
|---|---|---|---|
| KAT @ ncmoe=8 | 68.0–68.2 | 80.4 (+18.2%) | 0.725–0.732 |
| Ornith @ ncmoe=8 | 69.7–70.2 | **84.4–85.0 (+21%)** | 0.797 |

- Acceptance at 8.5K context is 0.73–0.80, essentially the short-context level — **not** the
  "KAT 51% @ 10K" the model card predicts. Our benchmark's 475-token deterministic code
  continuation is easy; acceptance tracks the *generated* tokens, which are unchanged by a
  longer prefix.
- On srv1 (ctx=8192, offload) the long-context MTP gain collapses to ~+2% (Ornith, noisy)
  / +13.7% (KAT) — same offload-bound signature as §2.

## 4. Key 1 recomputed — Ornith+MTP is the new #1

`tok/s × total × 1` (total-params convention, per the 2026-08-28 DoD table):

| rank | setup (srv2, llama.cpp b10644) | tok/s | total (B) | score |
|---|---|---|---|---|
| 🏆 **NEW** | Ornith-1.0-35B Q2_K-AllGPU **+ MTP** @ ncmoe=8 | **91.2** | 35.0 | **3,192** |
| NEW | KAT-Coder-V2.5-Dev Q2_K-AllGPU **+ MTP** @ ncmoe=8 | 88.9 | 35.0 | 3,111 |
| (was #1) | North-Mini-Code-1.0 IQ2_M (ncmoe=0) | 90.3 | 30.0 | 2,709 |
| (was #2) | gpt-oss-20b MXFP4 | 97.0 | 20.5 | 1,988 |

→ **Ornith+MTP beats the incumbent by +17.8%** (3,192 vs 2,709), on both axes: 91.2 > 90.3
tok/s *and* 35B > 30B.

**The graft is doing the work, not the base model.** Ornith *without* MTP at ncmoe=8 is
72.1 tok/s → 2,523, which *loses* to North (2,709). North (cohere2moe) has no MTP path, so
the fair read is: the 35B-A3B family + grafted MTP head uses the 12 GB card strictly better
than any MTP-less model we have, and Ornith's higher acceptance (0.90–0.91 vs KAT's 0.78–0.85
short / 0.80 vs 0.73 long) edges it past KAT.

**Key 2 (max throughput) is unchanged.** MTP's concurrency wall (§2) means the throughput
crown stays with the 7B dense under vLLM (1.57M). The 35B+MTP's max measured aggregate is
~127 tok/s @ n=2; at n≥4 MTP OOMs and the plain baseline (219 @16) can't touch the 7B.

## Walls

| wall | rig | cause |
|---|---|---|
| MTP @ ncmoe=4 | srv2 | `cudaMalloc failed` — grafted head ~1 GB; floor is ncmoe=8 |
| MTP @ ncmoe=8, n≥4 | srv2 | KV cache (c=n×1024) + MTP head > 12 GB |
| long ctx=10240 | srv1 | prompt > context (8.5K-token prompt > 10240−475); re-ran at ctx=8192 |
| Ornith Q2_K-AllGPU @ ncmoe=0 | srv2 | needs 13,057 MiB > 12,288 MiB |

## Files

- `README.md` — this report
- `raw/results-*.txt` — every sweep row (probe, conc, long; both rigs; KAT + Ornith)
- `drivers/mtpsweep2.py` — the concurrency + long-context MTP driver

Rig-side (kept): `~/models/moe/Ornith-1.0-35B_{Q2_K-AllGPU,Q3_K_M}.gguf` on srv2/srv1
(downloaded from `offmonreal/Ornith-1.0-35B-MaxQuality-MTP-GGUF`); sweep outputs under
`~/sweep-2026-08-28/results-mtp-*.txt`. Containers torn down after each cell.

## Open levers not yet pushed

- **turboquant fork + `turbo3` KV** (`TheTom/llama-cpp-turboquant`, ~300 commits ahead;
  Linux CUDA needs a source build — only CPU/Vulkan prebuilts ship). The Ornith card's
  ~192 tok/s is on that fork @ 16 GB; turbo3's 4.6× KV compression is the likely path to
  run MTP at n≥4 on 12 GB. Untested.
- **Ornith-1.5-35B** (offmonreal, sibling repo) — newer run, not yet benchmarked.
- **plain Qwen3.6-35B-A3B + MTP** — no ready grafted GGUF in offmonreal's repos (only
  iMatrix, head stripped); would need manual graft. Blocked on artifact, not hardware.
- **North-Mini-Code on vLLM** (PR #44707) — Key 2 upside; cohere2moe has no MTP.

## Sources

- https://huggingface.co/offmonreal/Ornith-1.0-35B-MaxQuality-MTP-GGUF (MTP graft, Apache/MIT,
  donor head © Qwen; sizes/recipe/acceptance caveat from the model card)
- https://huggingface.co/offmonreal/KAT-Coder-V2.5-Dev-MaxQuality-MTP-GGUF (KAT MTP sibling)
- llama.cpp `--spec-type draft-mtp` in `ghcr.io/ggml-org/llama.cpp:server-cuda` b10644
