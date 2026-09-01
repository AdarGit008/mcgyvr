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

## Compute capability 7.5 (srv1)

AWQ works. Marlin MoE kernels are selected. bfloat16 falls back to float16
automatically. FlashAttention 2 is unavailable → TRITON_ATTN. FlashInfer
sampler unavailable → falls back. **None of these blocked a load; only capacity
did.** FP8 needs a newer card.
