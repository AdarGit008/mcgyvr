# Width × context × concurrency — the run that corrects §5

Measured 2026-08-25, both rigs, `ghcr.io/ggml-org/llama.cpp:server-cuda-b10481`
(the digest already pinned in `../../2026-08-24-engine-sweep/`). 475-token replies,
`ignore_eos`, temperature 0, one fixed short prompt.

Two models, both pulled once and rsync'd rig-to-rig so each rig serves a
byte-identical file:

- `Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf` — 13,211,155,424 B, MoE, `unsloth/Qwen3.6-35B-A3B-GGUF`
- `Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf` — 4,218,473,248 B, dense, `bartowski/Qwen2.5-Coder-7B-Instruct-GGUF`

## 0. `-c` is divided across slots — the design constraint

`np-semantics-probe.txt`, launch-only cells on srv1's 7B, reading the server's own
`n_ctx_slot`:

| `-np` | `-c` | resulting `n_ctx_slot` |
|---|---|---|
| 1 | 4,096 | 4,096 |
| 4 | 4,096 | **1,024** |
| 16 | 4,096 | **256** |
| 32 | 4,096 | **256** |
| 4 | 16,384 | **4,096** |

**llama.cpp reserves per slot; vLLM does not.** `--max-model-len` in vLLM is a
ceiling that allocates per token used (this record §5, and the 2026-08-25 context
sweep). `-c` here is a *total* that gets divided.

Consequence for any width sweep: at `-np 32 -c 4096` each slot holds 256 tokens and
a 475-token reply cannot fit. **Every cell below therefore sets `-c = np × ctx_slot`**,
and every level records `truncated=n/N` so a starved slot would be visible rather
than silently shortening the reply.

## 1. Width — the knob this campaign never varied

### srv2, 35B-A3B, `--n-cpu-moe 25`, 1,024 tokens/slot

| `-np` | `-c` | VRAM | n=1 | n=4 | n=8 | n=16 | n=32 |
|---|---|---|---|---|---|---|---|
| 1 | 1,024 | 6,069 | 44.7 | | | | |
| 4 | 4,096 | 6,317 | 44.4 | 62.6 | | | |
| 8 | 8,192 | 6,649 | 40.0 | | 70.5 | | |
| 16 | 16,384 | 7,311 | 44.8 | | 70.1 | 80.2 | |
| 32 | 32,768 | 8,635 | 44.9 | | 70.2 | | **254.5** |

**44.9 → 254.5 is 5.67×**, against the 2.06× this record reports at the default
4 slots. p50 falls with it: **59.7 s** at `np=32, n=32` against **94.8 s** at
`np=16, n=16` — wider was faster per request, not merely higher in aggregate.

Width costs VRAM as the probe predicts: **6,069 → 8,635 MiB** from 1 to 32 slots.

### srv1, 7B IQ4_XS — width turns over

| `-np` | `-c` | VRAM | n=1 | n=4 | n=8 | n=16 |
|---|---|---|---|---|---|---|
| 1 | 1,024 | 4,012 | 54.5 | | | |
| 4 | 4,096 | 4,180 | 54.3 | 107.5 | | |
| 8 | 8,192 | 4,404 | 54.2 | | **128.4** | |
| 16 | 16,384 | 4,852 | 54.1 | | 128.7 | **106.3** |
| 32 | 32,768 | — | **refused — CUDA OOM** | | | |

**Peak at 8 slots.** Sixteen is slower than eight.

### srv1, 35B-A3B, `--n-cpu-moe 35`

| `-np` | VRAM | n=1 | n=4 | n=8 | n=16 |
|---|---|---|---|---|---|
| 1 | 3,402 | 29.1 | | | |
| 4 | 3,650 | 28.4 | **24.3** | | |
| 8 | 3,982 | 29.3 | | 31.8 | |
| 16 | 4,644 | 29.3 | | 31.8 | 42.7 |

A 35B model serving from **3,402 MiB on a 6 GB card**. Batching is weak here and
`n=4` is *worse than n=1* — srv1 has neither the VRAM to widen far nor the memory
bandwidth to feed the experts.

## 2. srv1's hard KV budget: `np × ctx_slot ≈ 16K tokens`

Three cells refused on srv1's 7B, and they name the same wall from two directions:

- `np 32 × 1,024` = 32,768 — CUDA OOM
- `np 8 × 4,096` = 32,768 — CUDA OOM
- `np 8 × 8,192` = 65,536 — model loading error

`np 16 × 1,024` = 16,384 loads at 4,852 MiB. **The budget is the product, not
either factor**: 16 slots of 1K, 4 of 4K and 2 of 8K are the same purchase.

## 3. Context buys nothing and still costs

srv2's 35B at fixed `-np 8`, varying tokens per slot:

| tokens/slot | `-c` | VRAM | n=8 |
|---|---|---|---|
| 1,024 | 8,192 | 6,649 | 70.5 |
| 4,096 | 32,768 | 7,131 | 70.4 |
| 8,192 | 65,536 | 7,775 | 70.1 |

**8× the context, 1,126 MiB more VRAM, 0.6% less throughput.** Since width and
context draw on one budget, **spend it on width** beyond what prompts actually need.

## 4. Two models srv1 could not run before

- **7B IQ4_XS loads in 4,012 MiB.** The AWQ build of the same model refuses on this
  card (5.20 GB of weights against a 5,102 MiB budget — see `../README.md` §5's
  dense table). The hole in srv1's dense coverage is closed by the quantisation.
- **A 35B serves from 3,402 MiB.**

## Bounds

One pass per cell. The 5.67×-against-2.06× comparison is **not a controlled pair** —
different model, quantisation and `--n-cpu-moe`. What is controlled is that the
2.06× row's slot count was never chosen; raising it on comparable hardware
multiplies the result by 2.75. A same-model width sweep on `qwen3-coder:30b` would
settle the magnitude and is not in this record.

**A harness defect caught in flight, and what it cost.** The first launch of both
sweeps omitted `ignore_eos`, so replies stopped at EOS and their length varied by
cell — the confound `../../2026-08-24-config-sweep/` names explicitly. The
`truncated=` counter surfaced it after four cells; both sweeps were killed, the
driver fixed, and every cell above re-run. All report `truncated=0/N`.

## Files

`np-semantics-probe.txt` · `srv1-7B-IQ4XS.txt` · `srv1-35B-IQ3XXS-ncmoe35.txt` ·
`srv2-35B-IQ3XXS-ncmoe25.txt` · drivers `lcpsweep.py`, `probe_np.sh`.
