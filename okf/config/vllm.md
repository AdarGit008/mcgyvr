# config — vLLM

What each knob does, and what it does not do. Engine: `vllm/vllm-openai:v0.26.0`.

## `--cpu-offload-gb`

**Moves weights to host RAM — but only on the V1 model runner.** The V2 runner
accepts the flag, hashes it into the compile-cache key, and ignores it.
`set_offloader()` exists only in `vllm/v1/worker/gpu_model_runner.py`. Path
selection is architecture-dependent (`VllmConfig.use_v2_model_runner`).

Measured, same model and host, only the path changed:
```
no offload  (V2)   weights 1.95 GiB   KV  87,584 tok   Shmem     14,660 kB
offload 1   (V2)   weights 1.95 GiB   KV  87,584 tok   Shmem     14,688 kB
offload 1   (V1)   weights 0.93 GiB   KV 117,152 tok   Shmem  1,573,244 kB
offload 2   (V1)   weights 0.59 GiB   KV 127,056 tok   Shmem  2,091,416 kB
```
Qwen2/AWQ takes V2 on both rigs → inert. NemotronH takes V1 → works.
Force with `VLLM_USE_V2_MODEL_RUNNER=0`. Verify with `Total CPU offloaded
parameters:` in the log, never with RAM figures.
→ `records/evidence/2026-08-31-inventory/board3-srv1-*.log`, D1

**The declaration gate does not subtract it.** `_CPU_OFFLOAD_IS_NOT_A_DISCOUNT`
is a constant nothing reads; the `cpu_offload_mib()` the configs cite does not
exist. A cell is weighed at full weight and refused if it does not fit.

## `kv_offloading_size` / `kv_offloading_backend`

Ship in 0.26.0 for moving the KV cache to host RAM. Recorded as available and
unset in this repo's own 2026-08-24 config capture
(`kv_offloading_backend: native`, `kv_offloading_size: None`). **Untested here.**

## `--max-num-seqs`

**The batch width. On no HTTP endpoint** — not in `/server_info`, not in the 122
metrics series, not on the model card. But the harness reads it off the running
process argv / container `Config.Cmd` over ssh (`launched_width()`), records
`provenance: "observed"`, and refuses on mismatch with `"contradicted"`.
→ `vllm.py:1665-1783`

**Nothing asserts `max_num_seqs >= max(concurrency.levels)`** — `grep -n levels
backends/vllm.py` returns nothing. Set it to the top of the ladder yourself, or
the ramp queues at the scheduler and prints a plateau indistinguishable from
saturation.

## `--gpu-memory-utilization`

Raises the card budget — and **backfills freed weight space with KV cache**,
which is why `nvidia-smi memory.used` stays flat whether or not weights were
offloaded. Do not use card occupancy to judge placement.

**Under util-sizing, `--max-num-seqs` is a cap the pool need not honour.** The
pool is sized from whatever VRAM survives the weights, so a cell can declare 128
and hold 6. The engine states what it got — `GPU KV cache size: N tokens` and
`Maximum concurrency for N tokens per request: Xx` — and that line is the only
width readback vLLM offers. Measured 2026-09-01 at `len=2048`:

```
srv1 q15    129,584 tok    63.3x     srv2 q15  664,320 tok   324.4x
srv1 q3      71,616 tok    35.0x     srv2 q3   458,368 tok   223.8x
srv1 q34b    12,816 tok     6.3x     srv2 q34b 104,400 tok    51.0x
srv2 q36-fp8 --cpu-offload-gb 26     10,240 tok    5.0x
```

**srv1's q34b holds 6.3 concurrent requests**, so n=8 and up queue — one rung
earlier than the 2026-08-31 plan's arithmetic predicted, and that plan already
accounted for the GSP reserve. Both cells that came in under the ladder were
offload or large-model cells, where weights crowd the pool.
→ `records/evidence/2026-09-01-prompt-realism/`

## `--max-model-len` + `max_num_seqs` + `bytes_per_token`

KV requirement is their product. The gate reads the pre-computed
`serve.kv_cache_memory_bytes` and returns early if absent; the product appears
only as an inverse in `_ways_out` and as a config-time assertion.
→ `vllm.py:1292`

**Nothing reads `--kv-cache-dtype`.** Every srv2 entry declares `fp8` while its
`bytes_per_token` is the fp16 figure, so the gated KV is ~2x what the engine
allocates. Conservative, but not the fp8 shape. → `vllm.py:1484`

**The 2x is exact, and it is measured.** Paired A/B on srv2, q15, same card,
same weights, same `max_model_len` — so weights and residue cancel:

```
kv=auto (fp16)   vram 11,121 MiB   KV 332,160 tok   maxconc 162.2   n=1 191.8
kv=fp8           vram 11,709 MiB   KV 664,320 tok   maxconc 324.4   n=1 181.7
```

664,320 / 332,160 = **2.000**, for 5.3% of single-stream throughput. So the gate
demands twice the pool an fp8 cell needs and **will refuse cells that fit** — the
2026-08-31 plan predicted exactly one such refusal (srv2 q34b at n=32) and the
cell ran to n=32 without trouble. Do not derive this cross-rig: the two
candidate weights+residue bases give answers 14% apart, the same trap
`always.md` records for bits-per-weight.
→ `records/evidence/2026-09-01-prompt-realism/srv2-fp8-ab-and-lcp-smoke.tsv`

## Co-residency (two vLLM servers, one card)

**`util` is a budget for weights + KV + activations. The CUDA context is on top
of it.** Measured on srv2 against a card verified empty between launches:
util 0.25/0.45/0.90 gave 3,925 / 6,333 / 11,709 MiB, each ~980 MiB above
`util x 11,911`. Budget for n servers therefore sums to
`1 - n x 980/total`, not to 0.9.

**Equal utils do not give equal pools.** q3 and q15 both at 0.40, q3 launched
first: q3 got 44,592 KV tokens (maxconc 21.8), q15 got 17,536 (maxconc 8.6) --
and q15 is the *smaller* model. Whatever share the second server gets, it is
not its util.

**How util composes across co-resident servers is UNSETTLED.** Two readings each
explain part of the data and neither explains all of it; three configurations
were guessed wrong on 2026-09-01 before the guessing stopped. Do not reason it
out -- read `maxconc` off each server's CONFIG row and tune against that. Two
engine behaviours are established:

- `ValueError: Free memory on device cuda:0 (1.12/11.63 GiB) on startup is less
  than desired GPU memory utilization (0.9, 10.47 GiB)` -- a precondition on
  FREE memory, checked before anything is allocated. It caps how high the
  second server's util can go, which is what makes the composition question
  bite.
- `AssertionError: Error in memory profiling. Initial free memory 8.43 GiB,
  current free memory 8.82 GiB` -- init reads LIVE free memory, so a neighbour
  still tearing down makes the next launch refuse. `docker rm -f` returns before
  the CUDA context is gone: **wait for `nvidia-smi --query-compute-apps` to come
  back empty**, do not sleep and hope. Two of the three pass-1 refusals were
  this, not the pair.

**A 7B does not co-reside on srv2 at len 2048.** q7 refused at util 0.55 and
again at 0.65 on a verified-clean card: 5.3 GiB of weights leaves 0.01 GiB for
KV, against the 0.05 GiB one 2048-token request needs.

**Three vLLM servers do not fit on srv2 at len 2048.** q34b/q3/q15 at
0.34/0.55/0.72 on a clean card with the teardown fix in place: q34b and q15 came
up, q3 refused with `No available memory for the cache blocks`. Pass 1 failed
the same way at 0.34/0.22/0.18. The arithmetic that makes this unsurprising is
the context overhead above -- three CUDA contexts are ~2,940 MiB, a quarter of
the card, before a single weight is loaded. The 2026-08-31 plan gave this
configuration 641 MiB of headroom on paper; that paper did not count contexts.
**So the measured srv2 ceiling is two co-resident vLLM servers, both small.**
→ `records/evidence/2026-09-01-prompt-realism/srv2-util-semantics.txt`

## Compute capability 7.5 (srv1)

AWQ works. Marlin MoE kernels are selected. bfloat16 falls back to float16
automatically. FlashAttention 2 is unavailable → TRITON_ATTN. FlashInfer
sampler unavailable → falls back. **None of these blocked a load; only capacity
did.** FP8 needs a newer card.
