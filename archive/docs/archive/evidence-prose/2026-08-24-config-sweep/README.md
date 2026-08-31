# The config sweep: what each rig actually does when it is configured for throughput

**2026-08-24.** 106 cells and counting, both rigs, one model
(`Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ`), one image
(`vllm/vllm-openai:v0.26.0`, identical digest), 20 configuration axes.
Coverage rather than targeting: one factor at a time from a baseline, then the
winners crossed, then the caps pushed until the engine refused.

Every cell records what the engine **resolved** — `/server_info` plus the
startup lines naming the attention backend, the linear kernel, the sampler path
and the KV cache size — not what it was asked for. Until this run, this tree had
never captured any of that on a launch that succeeded (`vllm.py:1423` reads the
engine log only on the failure path).

## The headline

| | srv1 | srv2 |
|---|---|---|
| as every prior run in this tree configured it | 164.3 | 518.2 |
| **best configuration found** | **293.6** | **6,445.1** |
| gain | **1.79x** | **12.4x** |
| the config that wins | `--max-num-seqs 128` | `no --enforce-eager`, `--max-num-seqs 256`, `--max-model-len 1024`, `--kv-cache-dtype fp8` |

**The gap between the rigs is 22x, not the 3.2x the 2026-08-19 campaign
recorded.** That campaign measured two servers that were both misconfigured, and
one of them far more than the other.

## What moves each rig, by axis

The best cell on each axis, 1.5B, stage 1 (aggregate tok/s):

| axis | srv1 | srv2 |
|---|---|---|
| **concurrency** | **293.4** | **4,006.1** |
| graphs (drop `--enforce-eager`) | 165.7 | **2,601.7** |
| optimization level | 168.1 | 2,354.8 |
| performance mode | 168.0 | 2,012.7 |
| kv-cache dtype | 167.2 | 592.3 |
| attention backend | 165.2 | 565.1 |
| every other axis (12 of them) | 164–168 | 508–564 |
| baseline | 164.3 | 530.1 |

**srv1 responds to exactly one axis of twenty.** Twenty-five cells across
compile, graphs, performance mode, scheduler, dtype, KV dtype, block size,
prefix caching, chunked prefill, cascade attention, stream interval, watermark,
attention backend and linear backend all land inside a 2.8% band. Concurrency
alone takes it from 164 to 293, and it saturates there: 16→32 is +36%, 32→64 is
+24%, 64→128 is +3.6%, and four different context lengths (4096, 2048, 1024,
512) return 293.3–293.4 — agreement to four significant figures. **293 is srv1's
ceiling and it is not context-bound.**

**srv2 responds to two, and they multiply.** `--enforce-eager` alone is worth
5.0x; concurrency on top of it takes the total to 12.4x.

## `--enforce-eager` cost srv2 5x, and it was never required

Every measurement in this tree's history carried the flag. Its justification
appears twice as an assertion — `calibrate.py:597` ("MANDATORY on srv1
(compute capability 7.5, no CUDA graphs)") and `step0-gaps.md:197` — and never
as a measured refusal. It is refuted in three independent ways:

1. **In vLLM's documentation**: `docs/features/README.md:66` lists CUDA graph as
   supported on Turing. No capability gate on graph capture exists in the 0.26.0
   source; the only forced-eager paths are ROCm encoder-decoder and 8-bit
   bitsandbytes.
2. **On srv1**, the card the belief was about: the flag is worth **0.1%**
   (293.6 without it against 293.3 with it). It was never srv1's problem.
3. **On srv2**, where nobody claimed it was needed: **5.02x** (2,601.7 against
   518.2). It is worth 5x at a single stream too — 181.7 tok/s at n=1 against
   36.2 — so this is not a batching effect.

The belief was attached to the wrong rig and cost the other one five times its
throughput for the life of the campaign.

## What srv1 is refused, and why it matters

14 of 47 stage-1 cells refused to launch on srv1. Four are the point:
`--dtype bfloat16`, `--kv-cache-dtype fp8`, `fp8_e5m2` and `fp8_e4m3`, plus
`--attention-backend FLASH_ATTN` and `FLASHINFER`. All are compute-capability
gates; srv2 accepts every one of them.

That matters because **fp8 KV is what produced srv2's best result.** It does
nothing at n=16 (558, indistinguishable from baseline) and is the winner at
n=256 (6,445 against 6,088): it does not speed a kernel up, it halves the bytes
per token and so doubles the sequences that fit. srv1 cannot have it. The one
lever that answers srv1's one responsive axis is the one its silicon refuses.

## Speculative decoding loses at every concurrency

Fixed and re-run after a harness defect (below) reported it refused when it was
untested. On srv2: ngram-3 **1,473.8** and ngram-5 **1,326.3** at n=16 against
2,601.7 without; ngram-3 at seqs 256 reads **2,738.8** against 6,087.7. The
`suffix` method refuses to launch on both rigs. Speculation buys latency at low
concurrency and costs aggregate tokens — the opposite of what this sweep is for.

## Validity

**The client is not the bottleneck.** Both rigs were driven from one host. In
srv2's best cell the ratio of maximum to mean request latency **falls** as
concurrency rises — 1.00, 1.12, 1.15, 1.07, 1.02, 1.02 at n = 1, 8, 32, 64, 128,
256. Client-side queueing would make it grow. Host load never exceeded 0.54 of
8 cores.

**Every request is the same length.** `ignore_eos=true` with `max_tokens=475`,
temperature 0, one fixed prompt, so a level's aggregate is not a function of how
early the model chose to stop.

**A refusal is a result and is recorded as one**, with the engine's own last 25
log lines beside it.

## Two defects in this sweep's own instrument

1. **A shell-quoting defect produced three false refusals per rig in stage 1.**
   `--speculative-config` takes JSON, the flags were joined with a plain space
   and passed through `ssh`, and the shell split the JSON on its spaces. The
   engine's message says so exactly: `Value {method: cannot be converted`. Fixed
   with `shlex.quote`; the affected cells were re-run in stage 2 and the results
   above are from the re-run. **The stage-1 records for those three cells are
   kept and are wrong** — they say "refused" about a config that was never
   tested.
2. **The concurrency arithmetic that designed the first matrix was wrong.** It
   assumed `max_num_seqs x max_model_len <= KV tokens`, which would cap srv1 at
   16 concurrent sequences at 8192. srv1 ran 32 and 64, on a server whose own log
   printed `Maximum concurrency: 16.00x`. KV is allocated per token actually
   used, and these requests use about 490 of the 8192 they were permitted. Every
   ceiling derived from that formula was a floor.

## Files

`srv1-1.5B.jsonl`, `srv2-1.5B.jsonl` — stage 1, 47 cells each, 20 axes.
`srv1-1.5B-stage2.jsonl`, `srv2-1.5B-stage2.jsonl` — winners crossed, caps
pushed, speculative re-run. `srv2-1.5B-ceiling.jsonl`, `srv2-7B.jsonl`,
`srv2-q3-4B.jsonl` — the gap sweep. One JSON record per cell: the flags, the
resolved config, every level, and the refusal with its log where there is one.

## What this does not settle

- **Every model but the 1.5B**, at the time of writing. The 7B is the one model
  on either rig whose `tie_word_embeddings` is false, which makes its lm_head
  quantized and puts it on Marlin rather than cuBLAS — the single cleanest test
  of the mechanism, and it is running.
- **ollama's ceiling.** `OLLAMA_NUM_PARALLEL=0` on both rigs and
  `OLLAMA_FLASH_ATTENTION` / `OLLAMA_KV_CACHE_TYPE` are unset, so the survey's
  "saturates at n=4" is a default and not a limit.
- **One workload shape.** A short prompt and 475 output tokens. Prefill-heavy
  traffic is a different question and this says nothing about it.
