# Setup Selection — the rigs' serving matrix, freshly measured (2026-08-28)

**Question.** Which (model × machine × engine × concurrency) setups should run the mcgyvr
worker ladder? One score: `tok/s × model_size × n`, three keys:

1. `tok/s × size × 1` — fast **and** smart, one request, one end user.
2. `tok/s × size × n*` — max throughput and smarts (n* = measured argmax).
3. `tok/s × size × n*` — runner-up.

**Size = total params** (owner's lean; active params shown alongside — see §Verification).
Every cell below is a fresh run from 2026-08-27/28, not a borrowed number. Empty cells
(= no data after all attempts) are marked and are the run list for the next pass.

## Protocol (same as the 2026-08-24/25/26 sweeps)

475-token replies, `ignore_eos`, temperature 0, one fixed short prompt
("Write a Python function that merges two sorted lists."), `-c = np × 1024`.
Concurrency ladder {1,2,4,8,16,32,64,128,256}, capped by what launches; a refusal is a
recorded cell with the engine's own sentence, not an omission.
Drivers: `lcpsweep*.py` (llama.cpp), `vllmsweep*.py` (vLLM).

- **llama.cpp**: `ghcr.io/ggml-org/llama.cpp:server-cuda` = **b10644** (pulled fresh;
  b10481 control cells run first — delta ≈ ±1.5%, within the 2.6%/5.2% noise bars, so the
  table bridges to all prior weeks' numbers).
- **vLLM**: `vllm/vllm-openai:v0.26.0` (pinned). srv2 driver moved 580.173.02 → **595.84**:
  v0.26.0 init fails on seqs=256 cells there; `vllm:latest` re-runs match v0.26.0 where both
  load (14B: 605.4 vs 610.1 @64 — tie). 15b/3b/Qwen3-4b vLLM cells on srv2 were re-run at
  seqs=128 (256 = driver-broken; see walls).

## DoD table — columns: (srv1 | srv2)

`n=1` = tok/s single request. `max×N` = max over measured n of (tok/s × n), with the argmax n.
REF = refused with cause (see walls); "—" = empty cell → a run.

| model | type | active params (GB) | srv1: lc n=1 | srv1: vLLM n=1 | srv1: lc max×N | srv1: vLLM max×N | srv2: lc n=1 | srv2: vLLM n=1 | srv2: lc max×N | srv2: vLLM max×N |
|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder-1.5b | dense | 3.1 | 158.5 | 44.8 | 467.5 @128 | 284.0 @64 | 193.9 | 201.8 | 1684.5 @256 | 5949.7 @128 |
| qwen2.5-coder-3b | dense | 6.2 | 96.8 | 22.6 | 268.7 @64 | 155.3 @64 | 126.9 | 122.3 | 1361.5 @128 | 3236.0 @128 |
| qwen3-4b | dense | 8.0 | 76.7 | 17.2 | 174.4 @16 | 87.9 @64 | 96.8 | 99.4 | 1010.8 @64 | 2378.6 @128 |
| qwen3-8b | dense | 16.5 | REF | — | REF | — | 61.1 | — | 664.2 @32 | — |
| qwen2.5-coder-7b | dense | 15.2 | 54.1 | REF | 105.6 @16 | REF | 72.0 | 67.1 | 1107.6 @128 | **1608.0 @128** |
| nemotron-7b | dense | 15.2 | 49.6 | — | 115.6 @16 | — | 66.3 | — | 778.0 @32 | — |
| qwen2.5-coder-14b | dense | 29.4 | REF | REF | REF | REF | REF | 26.7 | REF | 605.4 @64 |
| qwen2.5-coder-32b | dense | 65.0 | REF | — | REF | — | — | — | — | — |
| gpt-oss-4b | dense | 8.4 | 99.0 | — | 215.3 @32 | — | 130.5 | — | 846.5 @32 | — |
| nemotron-4b (fp8) | dense | 8.0 | — | REF | — | REF | — | REF | — | REF |
| qwen3-coder-30b-a3b | MoE | 6.6 | 23.2 | — | 67.8 @8 | — | 37.8 | — | **264.7 @32** | — |
| qwen3.6-35b-a3b | MoE | 6.0 | 26.9 | — | 127.4 @32 | — | 44.8 | — | 258.9 @32 | — |
| nemotron-3-nano-30b-a3b | MoE | 6.0 | REF | — | REF | — | 44.3 | — | 170.1 @32 | — |
| qwen3-coder-next-80b-a3b | MoE | 6.6 | 19.0 | — | 29.0 @16 | — | 7.5 | — | 23.1 @8 | — |
| deepseek-coder-v2-lite | MoE | 4.8 | 20.3 | — | 20.9 @8 | — | 22.7 | — | 29.7 @32 | — |
| gpt-oss-20b (MXFP4) | MoE | 7.2 | REF | — | REF | — | **97.0** | — | 277.9 @8 | — |
| gpt-oss-20b (Q3_K_M) | MoE | 7.2 | REF | — | REF | — | REF | — | REF | — |
| nemotron-30b-a3b (AWQ) | MoE | 6.0 | — | — | — | — | — | REF | — | REF |

*Per-model best quant per rig shown: 30b-A3B is Q4_K_M on srv1 (IQ3_XXS there needs ncmoe48
and then only 17.8/41.5 — deeper offload loses more than the quant saves) and UD-IQ3_XXS on
srv2. gpt-oss-20b: only the official MXFP4 conversion loads (arch `gpt-oss`); the unsloth
Q3_K_M carries arch `gptoss`, which llama.cpp b10644 does not know.*

## The three keys

**Key 1 — one request, one end user (tok/s × total × 1):**
1. 🏆 **srv2 · llama.cpp · gpt-oss-20b MXFP4** — 97.0 tok/s × 20.5B = **1,988** (whole model on the card, 11,511 MiB)
2. srv2 · llama.cpp · Qwen3.6-35B-A3B — 44.8 × 35 = 1,568
3. srv1 · llama.cpp · Qwen3-Coder-Next-80B-A3B — 19.0 × 80 = 1,520

**Key 2 — max throughput and smarts (tok/s × total × n\*):**
1. 🏆 **srv2 · vLLM · Qwen2.5-Coder-7B AWQ** — 1,608 tok/s @ n=128 = **1,566,321** (fp8 KV, seqs=128)
2. srv2 · vLLM · Qwen2.5-Coder-3B AWQ — 3,236.0 @ 128 = 1,279,903
3. srv2 · vLLM · Qwen3-4B AWQ — 2,378.6 @ 128 = 1,223,932

**Key 3 — runner-up:** srv2 · vLLM · Qwen2.5-Coder-3B AWQ @ 128 (3,236 tok/s).

The top-5 is all-vLLM-on-srv2: 7B, 3B, Qwen3-4B, 1.5B (5,949.7 @128 = 1,172,804),
then llama.cpp 7B IQ4_XS (1,107.6 @128 = 1,078,891). Caveat: the seqs=256 cells are
driver-broken on srv2 (595.84); at 256 the small models would score higher (last week's
1.5B: 6,480 tok/s @ 256 on the old driver), but at n=128 — today's measurable ceiling —
the 7B wins.

**The contrasts the note asked for:**
- vLLM vs llama.cpp: same 7B on srv2 — 1,608 vs 1,107.6 @128 (1.45× engine delta);
  reversed at n=1 (67.1 vs 72.0).
- single vs concurrent: 7B srv2 — 67–72 tok/s at n=1 → 1,608 at n=128 (vLLM, ~24×).
- srv1 vs srv2: same 35B file — srv1 26.9/127.4, srv2 44.8/258.9 (~2× on both ends).
- model_X vs model_Y: 30B-A3B IQ3_XXS (264.7@32) now beats 35B-A3B (258.9@32) on srv2.

## Verification — total vs active params

With **active** params in the key, the podium changes: gpt-oss-4b (130.5 × 4.2 = 548) beats
gpt-oss-20b (97 × 3.6 = 349). The owner's lean (total) stands on quality grounds: a 3B-active
MoE is far above a 3B dense on coding/agentic benchmarks (gpt-oss-20b: OpenAI-reported
agentic/tool-call evals ~GPT-4o-mini class; Qwen3-Coder-30B-A3B: LiveCodeBench ≈ 57+ vs
Qwen3-4B ≈ 38; 3B dense coder ≈ 30–34). Total params are the better smarts proxy for this
hardware class. Both columns are in the table; recompute on active if you prefer.

## Walls (refusal = recorded result)

| wall | rig | engine | cause (engine's own words) |
|---|---|---|---|
| gpt-oss-20b Q3_K_M | both | llama.cpp | `unknown model architecture: 'gptoss'` (unsloth tag; official MXFP4 tag is `gpt-oss` and loads) |
| gpt-oss-20b MXFP4 | srv1 | llama.cpp | cudaMalloc OOM (12.1 GB file, 6 GB card) |
| 14B dense (any flags, incl. -kvu) | both | llama.cpp | OOM: 8.9 GB weights + KV > card/RAM budget at every np that fits |
| 32B dense (incl. -kvu) | srv1 | llama.cpp | OOM on 6 GB card; srv2 not attempted (15 GB RAM < 19.9 GB file) |
| 30B UD-IQ3_XXS @ ncmoe28/35 | srv1 | llama.cpp | `cudaMalloc failed: allocating 5747.92 MiB` — UD quant's GPU buffer > Q4's 5,490 MiB; loads only at ncmoe48+kvu, and slower |
| qwen3-8b | srv1 | llama.cpp | OOM (5.0 GB weights + KV) |
| Nemotron-30B IQ2_XXS | srv1 | llama.cpp | OOM |
| 7B AWQ | srv1 | vLLM | OOM at util 0.85–0.95 (cc 7.5, no FA2 — the 2026-08-26 wall, re-verified) |
| nemotron-4b-fp8 | both | vLLM | `quantization method modelopt ... Minimum capability: 89. Current capability: 75/86` |
| nemotron-30b-awq | srv2 | vLLM | `torch.OutOfMemoryError` (17 GB > 12 GB) |
| vLLM seqs=256 cells | srv2 | vLLM | `Engine core initialization failed` — driver 595.84 × v0.26.0; re-ran at seqs=128, `vllm:latest` same wall |
| gpt-oss-20b on vLLM | both | vLLM | no AWQ/GGUF-vLLM path fits (13.8 GB > both cards) |

## Files

- `README.md` — this report
- `rows.jsonl` — every measured level/config/refusal row
- `baseline-2026-08-23..27.jsonl` — last week's evidence, mined for cross-check (reference only)
- Rig-side logs: `srv1:~/sweep-2026-08-28/results-srv1*.txt`, `srv2:~/sweep-2026-08-28/results-srv2*.txt`

## Still empty → next run list

srv2 vLLM @ seqs=256 (needs driver fix or vLLM rebuild; measured at seqs=128 instead);
qwen3-8b AWQ (not fetched); 32B on srv2 (15 GB RAM < 19.9 GB file); everything marked
"—" above.
