# The unified measurement campaign — KV dtype + reserve + scratch — measured 2026-09-11/12

The umbrella plan is `records/plans/kv-dtype-measurement-requirements-2026-09-11.md`
(tracked by PR #443). It scopes ONE combined rig run covering the KV-dtype arms
(R1–R5), the qwen35moe scratch at `-ub 512` (S1), and the two-boot
`gpu_reserve_mib` readings #438 and #439 wait on.

**Owner's frame (concrete dtype, NO "auto").** "auto" follows the model weights, so
it is spelled concretely. For the srv2 vLLM AWQ units the native dtype is `float16`,
so the comparison is **`fp8` vs `float16`** (distinct units). For the srv1 llama.cpp
unit it is **`q8_0` vs `f16`** (`-ctk`/`-ctv`). The live srv1 unit's as-run compose
carries `--verbose`, which the engine needs to print its `llama_kv_cache` line.

**All arms ran through the door** (gate 2 verified open, round `r28-11-09-2026`,
image `vllm/vllm-openai@sha256:ffb2d59b…` / `llamacpp:b10644-L3`). Instruments:
the 257-cell bench-py bundle (greedy, T=0) for answers; the `vllmsweep28.py`
concurrency ladder (475 tokens, ignore_eos) for speed; the engine's own KV line for
the llama.cpp sizes.

## R1 — vLLM fp8 vs float16 answers, the other srv2 AWQ units — DONE

Shape util 0.72 / len 4096 / seqs 8 (M5's shape). One cold start per
(model, dtype, a/b). `results-vllm-kv-answers.json`.

| unit | float16 pass (a/b) | fp8 pass (a/b) | float16 KV tokens | fp8 KV tokens |
|---|---|---|---|---|
| Qwen2.5-Coder-1.5B-AWQ | 25 / 24 | 9 / 8 | 253744 | 507504 (2.0×) |
| Qwen2.5-Coder-3B-AWQ | 27 / 27 | 20 / 22 | 168192 | 336400 (2.0×) |
| thewimo/Qwen3-4B-AWQ | **crashes** | 5 / 5 | — | 73920 |

- **fp8 halves the KV bytes/token, so the pool doubles (2.0× tokens) on every unit.**
- **fp8 also collapses answer quality**: 1.5B 24.5→8.5 (−65%), 3B 27→21 (−22%).
- **Qwen3-4B-AWQ + `float16` KV crashes deterministically** — vLLM v0.26.0
  FLASH_ATTN raises `RuntimeError: query and key must have the same dtype` during
  the forward pass. fp8 (FLASHINFER) is the only viable dtype for that unit.
- Backends: float16 → FLASH_ATTN, fp8 → FLASHINFER (both arms, all units).

## R2 — the 7B at the serving shape — DONE (shape adjusted)

Shape util 0.9 / len 4096 / seqs 8. **Deviation from the plan**: the specified
08-28 window (len 1024) rejects every bench-py cell — vLLM answers HTTP 400 when
`prompt + 768 output > 1024`, which the bench records as a transport error and
aborts. Length is raised to 4096 (M5's length) so the prompts fit; util 0.9 kept.

| unit | float16 pass (a/b) | fp8 pass (a/b) | float16 KV tokens | fp8 KV tokens |
|---|---|---|---|---|
| Qwen2.5-Coder-7B-AWQ | 68 / 68 | 6 / 6 | 76448 | 152912 (2.0×) |

- **The 7B's fp8 answer collapse is the worst of the set**: 68 → 6 (−91%). The M5
  difference holds at the serving utilization.

## R3 — speed ladder, fp8 vs float16 at the 08-28 shape — DONE

Shape util 0.9 / len 1024 / seqs 128, the `vllmsweep28.py` ladder n = 1…128, 475
tokens, ignore_eos, 2 cold starts per (model, dtype). `results-vllm-kv-ladder.json`
(14/16 arms; the two Qwen3-4B float16 cold starts crash as in R1).

n=128 aggregate tok/s (c1 / c2):

| unit | float16 | fp8 |
|---|---|---|
| 1.5B | 5537 / 5542 | 5736 / 5705 |
| 3B | 3074 / 3070 | 3182 / 3188 |
| Qwen3-4B | — | 2350 / 2349 |
| 7B | 1551 / 1558 | 1596 / 1600 |

- **fp8 is ~3% faster at n=128 on every unit that runs both** (less KV memory
  traffic); cold-start pairs agree within 0.1–1%.

## R4 — llama.cpp q8_0 vs f16 on the live srv1 unit — DONE

The live Qwen3.6-35B-A3B placement (`--n-cpu-moe 30 --parallel 2 -c 16384 -ub 512`,
`llamacpp:b10644-L3`, `--verbose`) held fixed; only `-ctk`/`-ctv` move.
`results-lcpp-kv-answers.json`.

| cache | engine line | K | V | size | bench-py pass (a/b) |
|---|---|---|---|---|---|
| f16 | `K (f16): 160.00 MiB, V (f16): 160.00 MiB` | 160 | 160 | **320 MiB** | 69 / 69 |
| q8_0 | `K (q8_0): 85.00 MiB, V (q8_0): 85.00 MiB` | 85 | 85 | **170 MiB** | 67 / 67 |

- **q8_0 is 17/32 of f16 (170/320) — the factor the plan predicted — and costs
  only −2/257 passes (69 → 67)**, unlike vLLM fp8 which collapses answers.

## R5 — reserve readings — folded, not re-measured

`results-reserve.json` (fleet-identity-2026-09-11, folded into #438): srv1 401 →
399 MiB (2 MiB move across the reboot), srv2 377/377. Pins #439's bound width and
answers #438's plan §12 open item.

## S1 — qwen35moe scratch+context at `-ub 512` — MEASURED (earlier this session)

qwen35moe scratch+context @ 512 = **316.57 MiB** (compute 221.00 + residue 95.57;
`-ub 256` control 304.57 reproduces the pinned 302.7 to 0.6%). The #446 GREEN folds
`MEASURED_SCRATCH_MIB["qwen35moe"][512] = 316.57`.

## Headline

- **vLLM `fp8` KV cache doubles the token pool but destroys bench-py answers**
  (7B 68→6, 1.5B 24.5→8.5, 3B 27→21); Qwen3-4B cannot even start on `float16`.
- **llama.cpp `q8_0` KV cache is the cheap one**: half the MiB (320→170), ~same
  answers (69→67).

## Rigs as left

Both rigs: no `mcgyvr-*` container up, swap on, card idle (used 1 MiB). Nothing
declared in `hosts.json` moved beyond the #439 stopgap.
