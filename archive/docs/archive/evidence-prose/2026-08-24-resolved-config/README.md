# Two rigs, one argument list, two instruments (#358)

**What is here.** The complete startup log and the whole `/server_info` payload
from one vLLM launch on each rig, taken 2026-08-24. Four files, no derived
numbers — `tests/test_bench_resolved_config.py` recomputes everything it asserts
from these.

**The launch.** Identical on both hosts, and the container image is pinned by
digest, not by tag:

```
docker run -d --runtime=nvidia --gpus all --ipc=host \
  -e VLLM_SERVER_DEV_MODE=1 -e FLASHINFER_DISABLE_VERSION_CHECK=1 \
  vllm/vllm-openai:v0.26.0 Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ \
  --port 8000 --max-model-len 8192 --gpu-memory-utilization 0.85 \
  --max-num-seqs 16 --enforce-eager
```

`/server_info?config_format=json` is the JSON form; the bare endpoint answers the
same configuration as a Python repr and both are parsed by the same reader.

## What the two servers resolved

| field | srv1 (GTX 1660 SUPER, sm_75) | srv2 (RTX 3060, sm_86) |
| --- | --- | --- |
| attention backend | `TRITON_ATTN` | `FLASH_ATTN` |
| sampler path | `torch` (fallback) | `flashinfer` |
| linear kernel | `MarlinLinearKernel` | `MarlinLinearKernel` |
| dtype | `torch.float16` | `torch.float16` |
| kv_cache_dtype | `auto` | `auto` |
| compilation mode | `0` | `0` |
| cudagraph mode | `0` | `0` |
| **`serving_resolved_sha256`** | `5ac25112…` | `75fd5838…` |
| `serving_build` | `vllm 0.26.0` | `vllm 0.26.0` |

The engine states the sampler on both hosts, and on srv1 it states the reason:

```
FlashInfer top-p/top-k sampling unavailable: unsupported compute capability 7.5;
falling back. Set VLLM_USE_FLASHINFER_SAMPLER=0 to silence.
```

## Why the existing pin could not have caught it

`serving_semantic_sha256` is taken over `/server_info`. Across these two hosts
that payload differs on exactly five keys, and not one of them is a kernel:

| key | srv1 | srv2 | what it is |
| --- | --- | --- | --- |
| `cache_config.kv_cache_size_tokens` | 131,088 | 322,304 | card size |
| `cache_config.num_gpu_blocks` | 8,193 | 20,144 | card size |
| `cache_config.kv_cache_max_concurrency` | 16.002 | 39.344 | card size |
| `instance_id` | `1787560477…` | `1787562266…` | a per-launch nonce |
| `quant_config` | 59 layer names | the same 59 | **set iteration order only** |

`vllm_env` adds a sixth difference of the same kind — a per-launch shared-memory
buffer name. So a digest over this surface moves for three reasons that are not
the instrument and stays still for the one that is. The kernels are not there to
be found: `kernel_config.linear_backend` and `kernel_config.moe_backend` both
read `auto` on both hosts — the policy that was asked for — and the payload
carries no attention or sampler key at all.

That is why #358 added a second digest rather than widening the first.

## Corrections to #358's body

1. **The dtype claim does not hold for this pair.** The issue states the
   divergence as srv1 `float16` against srv2 `bfloat16`. Both rigs resolve
   `torch.float16` on the 1.5B AWQ. The divergence is the attention backend and
   the sampler; the dtype reading came from a different cell.
2. **`/server_info` is not simply unread.** The issue says "nothing calls it".
   `vllm.serving_config` has called it since #326 — the gap was that what it
   returns does not contain the resolved kernels, and that only one field of what
   it does return reached a row.

## A defect this measurement found

The 2026-08-24 config sweep scraped resolved lines with a grep for
`FlashInfer for top`. That matches srv2's success sentence and misses srv1's
fallback sentence entirely, so every srv1 cell in that sweep looks as though the
engine said nothing about its sampler. It said the opposite of nothing. Fixed in
`sweep.py`; the sweep's own records are left as written, per the amendment
convention.
