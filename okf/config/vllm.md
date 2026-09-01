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

## `--max-model-len` + `max_num_seqs` + `bytes_per_token`

KV requirement is their product. The gate reads the pre-computed
`serve.kv_cache_memory_bytes` and returns early if absent; the product appears
only as an inverse in `_ways_out` and as a config-time assertion.
→ `vllm.py:1292`

**Nothing reads `--kv-cache-dtype`.** Every srv2 entry declares `fp8` while its
`bytes_per_token` is the fp16 figure, so the gated KV is ~2x what the engine
allocates. Conservative, but not the fp8 shape. → `vllm.py:1484`

## Compute capability 7.5 (srv1)

AWQ works. Marlin MoE kernels are selected. bfloat16 falls back to float16
automatically. FlashAttention 2 is unavailable → TRITON_ATTN. FlashInfer
sampler unavailable → falls back. **None of these blocked a load; only capacity
did.** FP8 needs a newer card.
