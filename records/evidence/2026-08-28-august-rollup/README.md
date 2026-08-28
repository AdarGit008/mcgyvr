# August rollup — every serving measurement, one score, one ladder (2026-08-28)

**Question.** Across *all* of August's evidence — not one directory — which
(model x machine x engine x concurrency) setups top the ladder on
`tok/s x model_size_B x n`, for one user and for many?

**Answer.** Four tables below, plus a correction to the key itself, speculative decoding
accounted for, and TTFT. Every cell names the run it came from.

Artifact (same content, rendered): `rig-ladder.html`.

## Scope

15 directories dated 2026-08-02 -> 2026-08-28 were read end to end. **2,308 measured rows**
and **196 refusals** were normalised into `rows-merged.jsonl`; **1,301 rows**
were eligible to rank.

Two directories that look substantial contribute nothing: `2026-08-23-phase0-footprint`
(2.6 MB `survey.json`) and `2026-08-23-phase0-refit` set `collect.concurrency=false` by
design — they record VRAM residency and weight digests, never a timing. 4.4 MB, zero cells.

## Protocol

The ranking admits only the 475-token protocol: 475-token replies, `ignore_eos`,
temperature 0, one fixed prompt, `-c = np x 1024`. Everything else is in the dataset and
excluded from the ladder — see *What was dropped*.

---

## The key counts n twice

`agg_tok_s` is the **aggregate across all n streams**, not a per-stream rate. Verified
against `n x 475 / wall`: median relative error **0.13%** over 295 levels; the per-stream
hypothesis is rejected at **87%**. So

```
score = agg_tok_s x size x n  =  (per_stream x n) x size x n  =  per_stream x size x n^2
```

Written as `tok/s x size x n` with **tok/s meaning one stream's rate**, the key is exactly
right — model-mass delivered per second across the fleet. Fed the aggregate, it becomes
quadratic in width and ranks how many slots a setup accepts rather than what it delivers.

Both readings collapse to the same thing: `per_stream x size x n` == `agg_tok_s x size`.
That is the **score /n** column in tables 3 and 4, and the re-ranked tables that follow them.
Both are reported: the quadratic form is the key as written and as `2026-08-28-setup-selection`
applies it.

---

## Table 1 — srv1, one request one user (n=1)

| # | model | type | quant | engine | total B | tok/s | score | run |
|---|---|---|---|---|---|---|---|---|
| 1 | Qwen3-Coder-Next-80B-A3B | MoE | `Q3_K_XL` | llamacpp | 80.0 | 19.0 | **1,520** | `2026-08-28-setup-selection/rows.jsonl` line:82 |
| 2 | Qwen3.6-35B-A3B | MoE | `IQ3_XXS` | llamacpp | 35.0 | 29.3 | **1,026** | `2026-08-25-moe-expert-offload/width-sweep/srv1-35B-IQ3XXS-ncmoe35.txt` line:7 |
| 3 | Qwen3-Coder-30B-A3B | MoE | `Q4_K_M` | llamacpp | 30.5 | 25.9 | **790** | `2026-08-26-capability-boundaries/srv1-llamacpp.txt` line:10 |
| 4 | North-Mini-Code-1.0 | MoE | `Q4_K_M` | llamacpp | 30.0 | 23.7 | **711** | `2026-08-28-north-mini-code/results-srv1.txt` line:3 |
| 5 | GPT-OSS-4B | dense | `Q4_K_M` | llamacpp | 4.2 | 99.0 | **416** | `2026-08-28-setup-selection/rows.jsonl` line:298 |
| 6 | Qwen2.5-Coder-7B | dense | `IQ4_XS` | llamacpp | 7.61 | 54.5 | **415** | `2026-08-25-moe-expert-offload/width-sweep/srv1-7B-IQ4XS.txt` line:3 |
| 7 | Nemotron-7B | dense | `Q4_K_M` | llamacpp | 7.6 | 49.6 | **377** | `2026-08-28-setup-selection/rows.jsonl` line:52 |
| 8 | DeepSeek-Coder-V2-Lite-16B | MoE | `Q4_0` | llamacpp | 15.7 | 20.3 | **319** | `2026-08-28-setup-selection/rows.jsonl` line:93 |
| 9 | Qwen3-4B | dense | `Q4_K_M` | llamacpp | 4.02 | 76.7 | **308** | `2026-08-28-setup-selection/rows.jsonl` line:355 |
| 10 | Qwen2.5-Coder-3B | dense | `Q4_K_M` | llamacpp | 3.09 | 96.8 | **299** | `2026-08-28-setup-selection/rows.jsonl` line:29 |

## Table 2 — srv2, one request one user (n=1)

| # | model | type | quant | engine | total B | tok/s | score | run |
|---|---|---|---|---|---|---|---|---|
| 1 | North-Mini-Code-1.0 | MoE | `IQ2_M` | llamacpp | 30.0 | 90.3 | **2,709** | `2026-08-28-north-mini-code/results-srv2.txt` line:3 |
| 2 | GPT-OSS-20B | MoE | `MXFP4` | llamacpp | 20.5 | 97.0 | **1,988** | `2026-08-28-setup-selection/rows.jsonl` line:330 |
| 3 | Qwen3.6-35B-A3B | MoE | `IQ3_XXS` | llamacpp | 35.0 | 44.9 | **1,572** | `2026-08-25-moe-expert-offload/width-sweep/srv2-35B-IQ3XXS-ncmoe25.txt` line:15 |
| 4 | DeepSeek-Coder-V2-Lite-16B | MoE | `Q4_0` | ollama | 15.7 | 94.4 | **1,482** | `calibration-2026-08-19/d7-survey.json` $.hosts.srv2.measured['deepseek-coder-v2-16b'].concurrency.levels[0] (n=1) |
| 5 | Nemotron-3-Nano-30B-A3B | MoE | `IQ2_XXS` | llamacpp | 30.0 | 44.3 | **1,329** | `2026-08-28-setup-selection/rows.jsonl` line:237 |
| 6 | Qwen3-Coder-30B-A3B | MoE | `IQ3_XXS` | llamacpp | 30.5 | 37.8 | **1,153** | `2026-08-28-setup-selection/rows.jsonl` line:274 |
| 7 | Qwen3-Coder-30B-A3B | MoE | `Q4_K_M` | ollama | 30.5 | 22.7 | **692** | `calibration-2026-08-19/d7-survey.json` $.hosts.srv2.measured['qwen3-coder-30b'].concurrency.levels[0] (n=1) |
| 8 | GPT-OSS-20B | MoE | `MXFP4` | ollama | 20.5 | 32.4 | **664** | `calibration-2026-08-19/d7-survey.json` $.hosts.srv2.measured['gpt-oss-20b'].concurrency.levels[0] (n=1) |
| 9 | Qwen3-Coder-Next-80B-A3B | MoE | `Q3_K_XL` | llamacpp | 80.0 | 7.5 | **600** | `2026-08-28-setup-selection/rows.jsonl` line:249 |
| 10 | GPT-OSS-4B | dense | `Q4_K_M` | llamacpp | 4.2 | 130.5 | **548** | `2026-08-28-setup-selection/rows.jsonl` line:267 |

> **New this week.** `North-Mini-Code-1.0` (Cohere, `cohere2moe`, 30B total / 3B active,
> Apache 2.0) takes srv2's Key 1 at 90.3 tok/s x 30B = **2,709**, beating `gpt-oss-20b`'s
> 1,988 by 36%. Whole model on the card at IQ2_M, 11,067 MiB. On srv1 it lands 4th.

## Table 3 — srv1, many requests (n = argmax)

| # | model | type | quant | engine | total B | tok/s | /stream | n | score ×n | score ÷n | run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Qwen3.6-35B-A3B | MoE | `IQ3_XXS` | llamacpp | 35.0 | 128.1 | 4.0 | 32 | **143,472** | 4,484 | `2026-08-26-capability-boundaries/srv1-llamacpp.txt` line:7 |
| 2 | Qwen2.5-Coder-1.5B | dense | `AWQ` | vllm | 1.54 | 294.7 | 1.2 | 256 | **116,183** | 454 | `2026-08-24-config-sweep/srv1-1.5B-stage2.jsonl` line:4 $.levels[5] |
| 3 | Qwen2.5-Coder-1.5B | dense | `Q4_K_M` | llamacpp | 1.54 | 467.5 | 3.7 | 128 | **92,154** | 720 | `2026-08-28-setup-selection/rows.jsonl` line:27 |
| 4 | Qwen2.5-Coder-3B | dense | `Q4_K_M` | llamacpp | 3.09 | 268.7 | 4.2 | 64 | **53,138** | 830 | `2026-08-28-setup-selection/rows.jsonl` line:42 |
| 5 | Qwen3-Coder-30B-A3B | MoE | `Q4_K_M` | llamacpp | 30.5 | 49.6 | 1.6 | 32 | **48,410** | 1,513 | `2026-08-26-capability-boundaries/srv1-llamacpp.txt` line:15 |
| 6 | Qwen3-Coder-Next-80B-A3B | MoE | `Q3_K_XL` | llamacpp | 80.0 | 29.0 | 1.8 | 16 | **37,120** | 2,320 | `2026-08-28-setup-selection/rows.jsonl` line:91 |
| 7 | North-Mini-Code-1.0 | MoE | `Q4_K_M` | llamacpp | 30.0 | 66.2 | 4.1 | 16 | **31,776** | 1,986 | `2026-08-28-north-mini-code/results-srv1.txt` line:12 |
| 8 | Qwen2.5-Coder-3B | dense | `AWQ` | vllm | 3.09 | 155.3 | 2.4 | 64 | **30,712** | 480 | `2026-08-28-setup-selection/rows.jsonl` line:125 |
| 9 | GPT-OSS-4B | dense | `Q4_K_M` | llamacpp | 4.2 | 215.3 | 6.7 | 32 | **28,936** | 904 | `2026-08-28-setup-selection/rows.jsonl` line:303 |
| 10 | Qwen3-4B | dense | `AWQ` | vllm | 4.02 | 87.9 | 1.4 | 64 | **22,615** | 353 | `2026-08-28-setup-selection/rows.jsonl` line:133 |

## Table 4 — srv2, many requests (n = argmax)

| # | model | type | quant | engine | total B | tok/s | /stream | n | score ×n | score ÷n | run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Qwen2.5-Coder-1.5B | dense | `AWQ` | vllm | 1.54 | 6,038.7 | 15.7 | 384 | **3,571,046** | 9,300 | `2026-08-24-config-sweep/srv2-1.5B-ceiling.jsonl` line:4 $.levels[6] |
| 2 | Qwen2.5-Coder-7B | dense | `AWQ` | vllm | 7.61 | 1,674.3 | 6.5 | 256 | **3,261,804** | 12,741 | `2026-08-24-config-sweep/srv2-7B.jsonl` line:6 $.levels[5] |
| 3 | Qwen2.5-Coder-3B | dense | `AWQ` | vllm | 3.09 | 3,497.3 | 13.7 | 256 | **2,766,504** | 10,807 | `2026-08-26-capability-boundaries/srv2-vllm-3b.txt` line:6 |
| 4 | Qwen3-4B | dense | `AWQ` | vllm | 4.02 | 2,325.0 | 9.1 | 256 | **2,392,704** | 9,346 | `2026-08-24-config-sweep/srv2-q3-4B.jsonl` line:6 $.levels[5] |
| 5 | Qwen2.5-Coder-14B | dense | `AWQ` | vllm | 14.7 | 313.5 | 1.2 | 256 | **1,179,763** | 4,608 | `2026-08-26-capability-boundaries/srv2-vllm-14b.txt` line:7 |
| 6 | Qwen2.5-Coder-7B | dense | `IQ4_XS` | llamacpp | 7.61 | 1,107.6 | 8.7 | 128 | **1,078,891** | 8,429 | `2026-08-28-setup-selection/rows.jsonl` line:207 |
| 7 | Qwen2.5-Coder-1.5B | dense | `Q4_K_M` | llamacpp | 1.54 | 1,684.5 | 6.6 | 256 | **664,097** | 2,594 | `2026-08-28-setup-selection/rows.jsonl` line:157 |
| 8 | Qwen2.5-Coder-3B | dense | `Q4_K_M` | llamacpp | 3.09 | 1,361.5 | 10.6 | 128 | **538,500** | 4,207 | `2026-08-28-setup-selection/rows.jsonl` line:174 |
| 9 | Qwen3.6-35B-A3B | MoE | `IQ3_XXS` | llamacpp | 35.0 | 258.9 | 8.1 | 32 | **289,968** | 9,062 | `2026-08-28-setup-selection/rows.jsonl` line:235 |
| 10 | Qwen3-4B | dense | `Q4_K_M` | llamacpp | 4.02 | 1,010.8 | 15.8 | 64 | **260,059** | 4,063 | `2026-08-28-setup-selection/rows.jsonl` line:182 |

### Re-ranked without the second n

Each setup taken at its own new argmax (which for `agg x size` is simply max aggregate).

**srv1**

| # | model | type | quant | engine | total B | tok/s | n | score ÷n | was |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Qwen3.6-35B-A3B | MoE | `IQ3_XXS` | llamacpp | 35.0 | 128.1 | 32 | **4,484** | #1 = |
| 2 | Qwen3-Coder-Next-80B-A3B | MoE | `Q3_K_XL` | llamacpp | 80.0 | 29.0 | 16 | **2,320** | #6 ↑4 |
| 3 | Qwen3-Coder-30B-A3B | MoE | `Q4_K_M` | llamacpp | 30.5 | 67.8 | 8 | **2,068** | #5 ↑2 |
| 4 | North-Mini-Code-1.0 | MoE | `Q4_K_M` | llamacpp | 30.0 | 66.2 | 16 | **1,986** | #7 ↑3 |
| 5 | Qwen2.5-Coder-7B | dense | `IQ4_XS` | llamacpp | 7.61 | 128.7 | 8 | **979** | #12 ↑7 |
| 6 | GPT-OSS-4B | dense | `Q4_K_M` | llamacpp | 4.2 | 215.3 | 32 | **904** | #9 ↑3 |
| 7 | Nemotron-7B | dense | `Q4_K_M` | llamacpp | 7.6 | 115.6 | 16 | **879** | #11 ↑4 |
| 8 | Qwen2.5-Coder-3B | dense | `Q4_K_M` | llamacpp | 3.09 | 268.7 | 64 | **830** | #4 ↓4 |
| 9 | Qwen2.5-Coder-1.5B | dense | `Q4_K_M` | llamacpp | 1.54 | 467.5 | 128 | **720** | #3 ↓6 |
| 10 | Qwen3-4B | dense | `Q4_K_M` | llamacpp | 4.02 | 174.4 | 16 | **701** | #13 ↑3 |

**srv2**

| # | model | type | quant | engine | total B | tok/s | n | score ÷n | was |
|---|---|---|---|---|---|---|---|---|---|
| 1 | North-Mini-Code-1.0 | MoE | `IQ2_M` | llamacpp | 30.0 | 518.4 | 16 | **15,552** | #12 ↑11 |
| 2 | Qwen2.5-Coder-7B | dense | `AWQ` | vllm | 7.61 | 1,674.3 | 256 | **12,741** | #2 = |
| 3 | Qwen2.5-Coder-3B | dense | `AWQ` | vllm | 3.09 | 3,497.3 | 256 | **10,807** | #3 = |
| 4 | Qwen2.5-Coder-1.5B | dense | `AWQ` | vllm | 1.54 | 6,480.6 | 256 | **9,980** | #1 ↓3 |
| 5 | Qwen3-4B | dense | `AWQ` | vllm | 4.02 | 2,378.6 | 128 | **9,562** | #4 ↓1 |
| 6 | Qwen3.6-35B-A3B | MoE | `IQ3_XXS` | llamacpp | 35.0 | 258.9 | 32 | **9,062** | #9 ↑3 |
| 7 | Qwen2.5-Coder-14B | dense | `AWQ` | vllm | 14.7 | 610.1 | 64 | **8,968** | #5 ↓2 |
| 8 | Qwen2.5-Coder-7B | dense | `IQ4_XS` | llamacpp | 7.61 | 1,107.6 | 128 | **8,429** | #6 ↓2 |
| 9 | Qwen3-Coder-30B-A3B | MoE | `IQ3_XXS` | llamacpp | 30.5 | 264.7 | 32 | **8,073** | #11 ↑2 |
| 10 | Nemotron-7B | dense | `Q4_K_M` | llamacpp | 7.6 | 778.0 | 32 | **5,913** | #13 ↑3 |

srv2's answer changes hands entirely: the 1.5B that wins the quadratic score falls to
fourth, and **North-Mini-Code-1.0 at n=16** takes it on 518.4 tok/s x 30B = 15,552. A 30B
MoE that never accepted more than 16 streams was invisible under the quadratic score and is
the rig's best fleet setup under the corrected one. On srv1 the MoE models climb three to
seven places each — they were being penalised for not accepting 128 streams, which was never
the question.

---

## Speculative decoding

Nine measured target/draft pairs, each against its own no-draft baseline from the same run
and build. **Not** on the 475-token protocol (replies were 60 / 150 / 256 tokens), so the
*ratio* transfers to the ladder, the absolute rates do not.

| engine | rig | target | draft | n | no draft | with draft | x |
|---|---|---|---|---|---|---|---|
| llama.cpp | srv2 | Qwen2.5-Coder-7B IQ4_XS | qwen2.5-coder-1.5b | 1 | 72.7 | 80.9 | **1.11** |
| llama.cpp | srv2 | Qwen2.5-Coder-7B IQ4_XS | qwen2.5-coder-1.5b | 4 | 212.6 | 226.2 | **1.06** |
| llama.cpp | srv1 | Qwen3-Coder-30B-A3B | Qwen3-1.7B | 1 | 22.8 | 23.5 | 1.03 |
| vLLM | srv2 | Qwen2.5-Coder-7B AWQ | Qwen2.5-Coder-1.5B AWQ | 1 | 68.23 | 69.33 | 1.02 |
| vLLM | srv2 | Qwen2.5-Coder-7B AWQ | Qwen2.5-Coder-1.5B AWQ | 8 cuda-graphs | 475.37 | 418.39 | 0.88 |
| vLLM | srv2 | Qwen2.5-Coder-7B AWQ | Qwen2.5-Coder-1.5B AWQ | 8 FLASH_ATTN | 475.32 | 411.51 | 0.87 |
| vLLM | srv2 | Qwen2.5-Coder-7B AWQ | Qwen2.5-Coder-1.5B AWQ | 8 eager | 320.99 | 240.23 | 0.75 |
| vLLM | srv1 | Qwen2.5-Coder-3B AWQ | Qwen2.5-Coder-0.5B AWQ | 8 eager | 64.87 | 43.37 | 0.67 |
| vLLM | srv1 | Qwen2.5-Coder-3B AWQ | Qwen2.5-Coder-0.5B AWQ | 8 cuda-graphs | 64.85 | 37.97 | **0.59** |

The split is by engine, not rig. **llama.cpp gains** (+11% at n=1, still +6% at n=4);
**vLLM loses under load** — every batched pairing measured is negative, the draft taking
compute the batch was using.

**It changes no table.** Applied where a pairing exists: srv1 Qwen3-Coder-30B-A3B
790 -> **814** (holds rank 3); srv2 Qwen2.5-Coder-7B IQ4_XS 548 -> **610** (rank 10 -> 8).
No fleet row improves. Two configurations were never tested: 35B-A3B native MTP and
external-draft on srv1 are narrative-only refusals with no measurement, and vLLM rejects the
1.5B->7B pair without `use_heterogeneous_vocab`.

---

## Time to first token

TTFT was never recorded under the 475-token protocol — neither driver logs it, and it is not
recoverable from p50 and wall. It exists in one place: **334 per-request ollama records** in
`2026-08-24-engine-sweep`, which report prefill, decode and total separately.
**TTFT here is derived as `total - decode`**, so it includes queue wait, which is what the
caller actually experiences.

| rig | model | n | reqs | TTFT p50 | prefill | queue |
|---|---|---|---|---|---|---|
| srv1 | `qwen2.5-coder:1.5b` | 1 | 3 | **42 ms** | 11 ms | 28 ms |
| srv1 | `qwen2.5-coder:1.5b` | 2 | 6 | **101 ms** | 42 ms | 33 ms |
| srv1 | `qwen2.5-coder:1.5b` | 8 | 24 | **430 ms** | 88 ms | 10 ms |
| srv1 | `qwen2.5-coder:1.5b` | 32 | 64 | **655 ms** | 518 ms | 43 ms |
| srv2 | `qwen2.5-coder:1.5b` | 1 | 3 | **21 ms** | 7 ms | 10 ms |
| srv2 | `qwen2.5-coder:1.5b` | 8 | 24 | **66 ms** | 31 ms | 9 ms |
| srv2 | `qwen2.5-coder:1.5b` | 32 | 32 | **100 ms** | 63 ms | 26 ms |
| srv2 | `qwen2.5-coder:1.5b` | 128 | 128 | **809 ms** | 284 ms | 523 ms |
| srv2 | `qwen2.5-coder:7b` | 1 | 2 | **42 ms** | 17 ms | 20 ms |
| srv2 | `qwen2.5-coder:7b` | 8 | 16 | **162 ms** | 44 ms | 34 ms |
| srv2 | `qwen2.5-coder:7b` | 32 | 32 | **488 ms** | 464 ms | 19 ms |

At n=1 srv2 answers in **20.8 ms** against srv1's **42.1 ms** — the same ~2x that separates
these rigs everywhere else. The shape inverts with width: through n=32 prefill dominates and
TTFT tracks the model; at n=128 on srv2 **queue wait is 523 ms of the 809 ms**. Past that,
TTFT stops measuring the engine and measures the backlog — the cost the fleet score charges
nothing for.

These are ollama, 1.5B and 7B only. They set the floor and the shape, not the value for any
vLLM or llama.cpp setup above. **Measuring TTFT on the ranked setups is an unrun experiment.**

---

## What was dropped, and why

2,308 measured rows extracted; 1,301 rankable. The gap is rows that
answer a different question, not noise.

| rows | reason |
|---|---|
| 427 | not-475-protocol |
| 284 | restatement |
| 184 | baseline-mine |
| 64 | co-resident |
| 22 | no-number |
| 17 | offline-harness |
| 12 | spec-decoding |
| 11 | contaminated |
| 4 | retracted |
| 4 | control-run |

- **not-475-protocol** — ollama and LMDeploy stop on EOS (replies ran 294-390 tokens); the whole
  `2026-08-25-moe-expert-offload` campaign is a 128-token, n=1 run. Only its `width-sweep/`
  subdirectory uses the protocol harness.
- **restatement** — post-swap summary tables and survey `repeats` arrays re-print earlier runs.
  `levels[i]` is the **max** of its repeats, not an independent sample.
- **baseline-mine** — `2026-08-28-setup-selection/baseline-2026-08-23..27.jsonl` is labelled
  reference-only and its implied reply length varies 302-475 tokens. Every directory it mines is
  covered by a primary read here.
- **co-resident** — measured with a second model still holding VRAM.
- **offline-harness** — `llama-batched-bench` is not a server.
- **contaminated / retracted** — srv1 `gptoss-4b` np=32 attempt 1 (the two attempts disagree 22% at
  n=16); the `docker --memory=15g` cells, whose cgroup never bound because the GGUF sat in host page
  cache.

## Corrections to the record

Re-measurement during this rollup falsified four claims carried in earlier directories:

| claim | as recorded | re-measured |
|---|---|---|
| L6 | srv2 `--no-mmap` worth +63% | **+2.1% cold / +5.0% warm** — the mmap column was contaminated |
| L5 | srv1 ncmoe=38 is the peak | **no turnover** — 37 is 1.7% above 38, inside the noise bar |
| M5 | repeatability 0.04% / 0.2% | **2.6% (srv1) / 5.2% (srv2)** across reloads; srv1 also drifts ~2.6% down over 6 min of load |
| H5 | srv1 memory bandwidth 26.8 GB/s | **19.6 GB/s** — which inverts the srv1/srv2 bandwidth ratio |

Consequence for these tables: **any two setups within 2.6% on srv1 or 5.2% on srv2 are tied.**

Separately — the speculative-decoding cells recorded as REFUSED in `2026-08-24-config-sweep`
were never actually tested: a shell-quoting bug split the `--speculative-config` JSON before
the engine received it.

## Walls

| wall | rig | cause |
|---|---|---|
| 14B dense, llama.cpp | both | 8.9 GB weights + KV over budget at every np that fits |
| 32B dense | srv1 / srv2 | OOM on the 6 GB card; srv2's 15 GB RAM < the 19.9 GB file |
| gpt-oss-20b MXFP4 | srv1 | cudaMalloc OOM — 12.1 GB file, 6 GB card |
| gpt-oss-20b Q3_K_M | both | `unknown model architecture: 'gptoss'` (unsloth tag; official MXFP4 loads) |
| 7B AWQ on vLLM | srv1 | OOM at util 0.85-0.95, cc 7.5, no FA2 — 100% refusal over 8 attempts; **no srv1 7B vLLM number exists** |
| nemotron-4b fp8 | both | `Minimum capability: 89. Current capability: 75/86` |
| vLLM seqs=256 | srv2 | `Engine core initialization failed` on driver 595.84 — yet the 08-24 runs on driver **580** reached n=384 |
| North-Mini-Code np=32 | srv2 | KV-cache OOM on the 12 GB card |

## Rigs

| | srv1 | srv2 |
|---|---|---|
| GPU | GTX 1660 SUPER, 6 GB, sm75 | RTX 3060, 12 GB, sm86 |
| CPU | i5-9600K, 6c/6t, 4.6 GHz | i9-10900F, 10c/20t, turbo off |
| RAM | 48 GB DDR4-3200, 19.6 GB/s | 16 GB DDR4-2667, 20.3 GB/s |
| shape | big RAM, small card -> expert offload | big card, small RAM -> fits on GPU |

## Files

- `rows-merged.jsonl` — every measured level and refusal, 2,504 records, each with
  `src_file` + `src_locator` into the original evidence, plus `config`, `tokens_per_request` and caveats in `note`.
- `payload.json`, `scoreB.json` — the ranked top-10s (quadratic and corrected).
- `ttft.json` — the 11 aggregated TTFT cells and their per-request source count.
- `rig-ladder.html` — the rendered report.
- `drivers/sizemap.py` — canonical model -> (name, type, total_B, active_B); parameter counts follow
  `2026-08-28-setup-selection/drivers/analyze.py`.
- `drivers/final.py` — merge, exclude, rank. `python3 drivers/final.py` reproduces every table.
- `drivers/build.py` — renders `rig-ladder.html`.
- `drivers/BRIEF.md` — the extraction contract each directory was read against.

## Still open

- TTFT on any ranked vLLM or llama.cpp setup (only ollama 1.5B/7B measured).
- srv2 vLLM at seqs=256+ on driver 595.84 — the 08-24 driver-580 runs reached n=384; the
  regression is untriaged.
- North-Mini-Code-1.0 above n=16 on srv2, and on vLLM at all.
- qwen3-8b AWQ (never fetched); 32B on srv2 (15 GB RAM < 19.9 GB file).
