---
title: "Config sweep — session report"
subtitle: "srv1 / srv2, 140 cells, 20 axes"
date: "2026-08-24"
geometry: margin=2cm
fontsize: 10pt
colorlinks: true
---

# 1. Results

Aggregate tokens/s, measured. 475 output tokens per request with `ignore_eos`,
temperature 0, one fixed prompt. **Baseline** = the configuration every prior run
in this tree used: `--max-model-len 8192 --gpu-memory-utilization 0.85
--max-num-seqs 16 --enforce-eager`.

```
RIG   MODEL              CELLS RAN  BASELINE      BEST   GAIN  WINNING CONFIG
srv1  Qwen2.5-Cdr-1.5B     58   41     164.3     294.7  1.79x  no-eager, len 512,  seqs 256          (n=256)
srv2  Qwen2.5-Cdr-1.5B     66   51     530.1    6445.1 12.16x  no-eager, len 1024, seqs 256, kv-fp8  (n=256)
srv2  Qwen3-4B              6    6     370.0    2349.4  6.35x  no-eager, len 1024, seqs 256, kv-fp8  (n=128)
srv2  Qwen2.5-Cdr-7B        6    6     507.2    1674.3  3.30x  no-eager, len 1024, seqs 256, kv-fp8  (n=256)
srv1  Qwen2.5-Cdr-7B        4    0         -         -      -  ALL REFUSED - CUDA OOM loading weights
TOTAL                      140  104
```

## Per-axis best, 1.5B, stage 1

Twenty axes, one factor at a time from the baseline.

```
AXIS                     srv1     srv2      NOTE
concurrency             293.4   4006.1      the only axis that moves srv1
graphs (drop eager)     165.7   2601.7      5.02x on srv2, 0.1% on srv1
optimization-level      168.1   2354.8      rides on graphs being enabled
performance-mode        168.0   2012.7      "throughput" LOST to plain no-eager
kv-cache-dtype          167.2    592.3      inert at n=16, decisive at n=256
attention-backend       165.2    565.1
memory (util)           167.9    564.4
prefix-cache            167.3    561.9
scheduler (async)       168.0    553.8
watermark               167.8    550.9
cascade-attn            165.4    550.2
dtype                   167.2    550.1
batched-tokens          167.9    548.5
stream-interval         167.0    537.4
BASELINE                164.3    530.1
chunked-prefill         167.8    523.5
linear-backend          167.9    516.4
block-size              167.9    508.9
speculative (fixed)     201.7   2738.8      loses everywhere; -63% on srv1 at ngram-5
```

## Decode-step cost — the mechanism

Latency divided by 475, milliseconds per decode step.

```
batch      srv1 1.5B    srv2 1.5B    srv2 7B (untied lm_head)
    1          22.96        27.64        17.17
    2          72.75        28.27          -
    8          74.80        28.08        15.99   <- cheaper than batch 1
   32              -            -        24.25
   64              -            -        41.96
  128          95.99        28.65        81.81
```

srv1 steps 3.17x between batch 1 and 2, then is flat. srv2 is flat throughout.
The 7B, whose lm_head is quantized because it does not tie embeddings, has no
step at all and is *cheaper* per step at batch 8 than at batch 1.

## Isolated lm_head GEMM

`[151936 x hidden]`, no model loaded, same container on both rigs. Milliseconds.

```
            srv1 fp16   srv1 fp32   srv2 fp16
M=1              1.77        2.95        1.39
M=2             50.83        2.98        1.39
M=32            50.85       11.63        1.46
```

Excess on srv1 at M>=2: **49.06 ms**. Excess observed in the live vLLM run:
**49.79 ms**. Agreement to 1.5%.

# 2.1 Knobs used

**Turned** — 20 axes, drawn from the engine's own 274-flag surface
(`vllm serve --help=all`, 250 with printed defaults):

`max-num-seqs` · `max-model-len` · `enforce-eager` · `performance-mode` ·
`optimization-level` · `async-scheduling` · `dtype` · `kv-cache-dtype` ·
`gpu-memory-utilization` · `max-num-batched-tokens` · `block-size` ·
`enable-prefix-caching` · `enable-chunked-prefill` · `disable-cascade-attn` ·
`stream-interval` · `watermark` · `ubatch-size` · `attention-backend` ·
`linear-backend` · `speculative-config`

**Refused by srv1** (compute-capability gates): `dtype bfloat16` ·
`kv-cache-dtype fp8 / fp8_e5m2 / fp8_e4m3` · `attention-backend FLASH_ATTN /
FLASHINFER` · `seqs 512` · `kv-fp8 + seqs 256`

**Refused by both:** `linear-backend exllama / torch / machete / cutlass` ·
`ubatch-size 2` · `spec-method suffix` · `seqs 512`

**Refused by srv2:** `kv-fp8` above seqs 256

**Not turned:** ollama's entire surface. `OLLAMA_NUM_PARALLEL=0`,
`MAX_LOADED_MODELS=0`, `KEEP_ALIVE=-1`; `OLLAMA_FLASH_ATTENTION` and
`OLLAMA_KV_CACHE_TYPE` unset on both rigs.

# 2.2 What we learned

1. **`--enforce-eager` cost srv2 5.02x and was never required.** Justified twice
   in this tree as "MANDATORY on compute capability 7.5" and never once as a
   measurement. Worth 0.1% on the card it was claimed for; 5x at a single stream
   on the other (181.7 vs 36.2 tok/s at n=1), so not a batching effect.
2. **The 2026-08-19 campaign compared two misconfigured servers.** The real gap
   between the rigs is **21.9x**, not the 3.2x it recorded.
3. **The N=2 cliff is the unquantized lm_head.** `tie_word_embeddings: true`
   means lm_head is fp16 through cuBLAS, and TU116 carries no tensor cores.
   Microbenchmark excess 49.06 ms against 49.79 ms in vivo. Controls pass in
   both directions: srv1 fp32 does not cliff, srv2 fp16 does not cliff.
4. **srv1 responds to one axis of twenty.** Twenty-five cells land inside a 2.8%
   band; only concurrency moves it, to **~295 tok/s**, where five configurations
   agree within 0.4% and four context lengths agree to four significant figures.
5. **srv1's one lever is gated shut.** fp8 KV produced srv2's best cell - it
   doubles the sequences that fit rather than speeding a kernel up - and srv1
   refuses all three fp8 variants by compute capability.
6. **fp8 KV is regime-dependent.** Inert at n=16 (558, indistinguishable from
   baseline), decisive at n=256 (6,445 against 6,088).
7. **Speculative decoding loses at every concurrency**, on both rigs, worse on
   the weaker one (-63% at ngram-5 on srv1).
8. **`--performance-mode throughput` lost** to plain no-eager, 2,012 vs 2,601.
9. **AWQ-Marlin is not sm_80-gated.** The floor is 75 and both rigs resolve
   `MarlinLinearKernel`. The common claim traces to vLLM #1282 from 2023.
10. **srv1 cannot hold the 7B.** CUDA OOM allocating 518 MiB with 151.88 MiB
    free of 5.61 GiB, in `auto_awq.py:533` during weight loading - before KV is
    considered. srv1 caches no untied-lm_head model it can run.
11. **The gain shrinks as the model grows** on srv2: 12.16x, 6.35x, 3.30x for
    1.5B, 4B, 7B.

# 2.3 Still unknown / unverified

## Measurement

- **The decisive mechanism test was not run.** It required an untied-lm_head
  model on srv1; the 7B OOMs and no other untied model is cached there. The
  mechanism rests on the isolated GEMM plus srv2's contrast, not on srv1 running
  an untied model.
- **ollama's real ceiling.** "Saturates at n=4" is a default, not a limit.
  Changing it needs a daemon env change and restart, and the current values are
  pinned by `tests/test_declared_host_state.py`.
- **3B and Qwen3-4B on srv1**, and **14B on srv2** - never swept.
- **One workload shape only**: short prompt, 475 output tokens. Nothing here
  speaks to prefill-heavy traffic.
- **Interactions beyond pairs.** One-factor-at-a-time plus a handful of crosses;
  the space is not factorially covered.
- **srv1's second step at b>8** - attributed to Marlin's narrow-M kernel
  (`prob_m_split <= 8`) by reading the source, not by measurement.

## Instrument

- The `contract.py` constants (**#356**) - all derived under the 5x
  misconfiguration. `START_TIMEOUT_S` is directionally wrong, and `RAMP_LEVELS`
  tops out at 24 while both rigs' maxima sit at n=128-256.
- The knob surface as data (**#357**) and the resolved config entering
  `identity.KEY` (**#358**) - filed, not built.
- The sweep harness keeps only 25 log lines, which lost the 7B root cause until
  it was re-run by hand.

## Errors made this session, all corrected in the record

- Concurrency arithmetic `b x max_model_len <= KV tokens` - wrong. KV is
  allocated per token actually used; srv1 ran 64 concurrent on a server printing
  `Maximum concurrency: 16.00x`.
- A shell-quoting defect produced **six false refusals** across two rigs;
  speculative decoding was recorded as refused when it was untested.
- Two process-management bugs (a `pgrep -f` self-match deadlock and a `pkill`
  self-match). Cost time, touched no data.

# Landed

Evidence README and 8 result files under
`records/evidence/2026-08-24-config-sweep/`. Three dated record corrections:
`calibration-2026-08-19/README.md` (twice), `step0-gaps.md` gap 10, and
`calibrate.py:597` in place because code is operative. Issues **#356**, **#357**,
**#358** filed. Both rigs idle at 1 MiB.
