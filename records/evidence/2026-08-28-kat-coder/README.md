# KAT-Coder-V2.5-Dev — same speed as the base, and native MTP unblocks the 35B (2026-08-28)

**Question.** Get `KAT-Coder-V2.5` (the user's "kat-coder 2.5"), run it on both rigs, and
report the numbers: (1) plain throughput vs the models we already have, and (2) whether the
grafted-MTP build finally cracks last week's *"35B not draftable"* wall.

**Model.** [`Kwaipilot/KAT-Coder-V2.5-Dev`](https://huggingface.co/Kwaipilot/KAT-Coder-V2.5-Dev)
— Apache 2.0, **35B total / 3B active MoE**, a post-trained **Qwen3.6-35B-A3B** (SFT on 127K
examples + RL). SOTA agentic coding: SWE-bench Verified **69.4** vs the base's 64.4, Qwen3-Coder-30B's 31.8.
Arch `qwen35moe`, vocab 248,320 — identical to the 35B already in our store, so the pinned
llama.cpp `server-cuda` b10644 image loads it with **zero changes**.

## 1. Plain throughput — same speed, better model

Protocol identical to `2026-08-28-setup-selection` (lcpsweep, 475-token, `ignore_eos`, temp 0).
`mradermacher/KAT-Coder-V2.5-Dev-GGUF` quants.

**srv2 · Q2_K (12.9 GB, ncmoe=25):**

| n | KAT tok/s | Qwen3.6-35B IQ3_XXS (existing) |
|---|---|---|
| 1 | **44.1** | 44.8 |
| 8 | 123.4 | — |
| 32 | **244.7** | 258.9 |

→ Throughput is a wash (±5%, within noise), exactly as expected for a fine-tune of the same
architecture. **KAT-Coder buys the SWE-bench jump (69.4 vs 64.4) at no throughput cost.**

**srv1 · Q4_K_M (21.2 GB, ncmoe=48/50, offload):** n=1 28.6, n=8 73.4, n=16 65.7 tok/s.
(Higher-quality quant than the incumbent's 13.2 GB IQ3_XXS; not a like-for-like throughput
comparison, just the "it runs on srv1's RAM" datapoint.)

## 2. Native MTP speculative decoding — the wall falls

Last week: *"35B not draftable — MTP head stripped in stock GGUF + vocab 248320 blocks a
small draft."* Fix tested here: [`offmonreal/KAT-Coder-V2.5-Dev-MaxQuality-MTP-GGUF`](https://huggingface.co/offmonreal/KAT-Coder-V2.5-Dev-MaxQuality-MTP-GGUF),
which grafts the **Qwen3.6 MTP draft head** back into the GGUF as `blk.40` (Apache 2.0, donor
head © Qwen Team). It is documented against the `llama-cpp-turboquant` fork, **but the stock
b10644 image runs it as-is** — `--spec-type draft-mtp` for `qwen35moe` is already in b10644,
so the fork was unnecessary.

Driver `mtpsweep.py` (single-slot, `-np 1 -c 2048`, 3 runs per config, 475 tokens). Baseline =
same MTP file with `--spec-type` off. `draft acceptance = 0.783 (289/369), mean len 2.56`.

**srv2 · Q2_K-AllGPU (14.1 GB, ncmoe=28):**

| config | tok/s | vs baseline |
|---|---|---|
| baseline (no MTP) | 50.8 | 1.00× |
| `--spec-draft-n-max 2` | **57.5** | **+13.1%** |
| `--spec-draft-n-max 3` | 55.3 | +8.8% |
| `--spec-draft-n-max 4` | 55.7 | +9.5% |

**srv1 · Q3_K_M (18.1 GB, ncmoe=40):**

| config | tok/s | vs baseline |
|---|---|---|
| baseline (no MTP) | 30.2 | 1.00× |
| `--spec-draft-n-max 2` | **36.9** | **+22.2%** |
| `--spec-draft-n-max 3` | 36.7 | +21.5% |
| `--spec-draft-n-max 4` | 35.7 | +18.1% |

## Verdict

1. **Plain KAT-Coder: no throughput win, big quality win.** Same tok/s as Qwen3.6-35B-A3B on
   both rigs (44.1 vs 44.8 on srv2), with SWE-bench 69.4 vs 64.4. It is a drop-in *better* 35B,
   not a *faster* one.
2. **Native MTP is the real find.** It beats the two past-week spec-decode results:
   - **srv2 +13.1%** — above the 7B `draft-simple` win (+11%, same rig, 2026-08-27) *and* on a
     35B target instead of a 7B.
   - **srv1 +22.2%** — where last week's external 1.7B-draft on a 30B MoE was +3% (offload-bound).
     Native MTP wins *because* the rig is offload-bound: it cuts the number of expensive target
     forwards rather than adding a second model. External-draft and native-MTP point in
     **opposite directions** on the weak card.
3. **The "35B not draftable" wall is falsified** — you don't need the 71 GB BF16, and you don't
   need a fork: a ≤14 GB grafted-MTP GGUF on stock b10644 does it.

## Files

- `README.md` — this report
- `results-kat-srv2.txt`, `results-kat-srv1.txt` — raw sweep output
- `drivers/mtpsweep.py` — the MTP baseline-vs-draft driver

Rig-side (kept): `~/models/moe/KAT-Coder-V2.5-Dev.{Q2_K,Q4_K_M}.gguf` (plain) and
`KAT-Coder-V2.5-Dev_Q{2_K-AllGPU,3_K_M_imatrix_MTP}.gguf` (MTP) on srv2/srv1;
`~/north-bench/results-kat-*.txt`; `~/sweep-2026-08-28/drivers/mtpsweep.py`.

## Sources

- Model card: https://huggingface.co/Kwaipilot/KAT-Coder-V2.5-Dev (Apache 2.0)
- Plain GGUFs: https://huggingface.co/mradermacher/KAT-Coder-V2.5-Dev-GGUF
- MTP GGUFs: https://huggingface.co/offmonreal/KAT-Coder-V2.5-Dev-MaxQuality-MTP-GGUF
- llama.cpp `draft-mtp` (b10644) + PR #24260 / #24615; donor head © Qwen/Qwen3.6-35B-A3B
