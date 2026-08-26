---
type: Finding
title: "What --max-model-len reserves"
id: claim-V11
description: "Claim V11 of the 2026-08-25 serving report: partial."
aliases: ["claim V11", "V11"]
tags: ["serving", "verdict:partial", "engine:vllm", "kv-cache"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:28-30"
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:121-126"
---

# V11 — What --max-model-len reserves

**Claim as written.** vLLM's --max-model-len is a CEILING that reserves nothing (allocates per token used) — the opposite of llama.cpp's -c.

**Standing verdict: PARTIAL.**

## Evidence — srv1 [partial]

The **direction is right and the contrast with `-c` holds**: `num_gpu_blocks` is derived from `gpu_memory_utilization` and `max_model_len` appears in none of the four block-count formulas. But "reserves nothing / allocates per token used" is not literally true, in three ways:
1. **The KV pool is pre-allocated in full at init** — `v1/worker/gpu_model_runner.py:7238-7266` `_allocate_kv_cache_tensors()` does `torch.zeros(kv_cache_tensor.size, ...)`. Blocks are *assigned* on demand out of an already-claimed pool.
2. **`max_model_len` is a hard startup floor that can refuse to launch** — `v1/core/kv_cache_utils.py:751-788` `_check_enough_kv_cache_memory()` computes KV for one full `max_model_len` sequence and raises `ValueError: To serve at least one request with the model's max seq len (...)` if it exceeds the budget. Raising it on a fixed budget can prevent startup even though it reserves no blocks.
3. **It does size some buffers** — GPU block table `(max_num_reqs x cdiv(max_model_len, block_size))` int32 (`gpu_model_runner.py:696-698`, `block_table.py:79-83`); CPU `(max_num_reqs, max_model_len)` int32 **and** bool (`gpu_input_batch.py:132-144`, with the in-tree comment *"TODO(woosuk): This buffer could be too large if max_model_len is big"*).
Also worth recording: `--max-model-len -1` inverts the relationship — `kv_cache_utils.py:1930-1986 _auto_fit_max_model_len()` *derives* it from available memory.

```bash
ssh srv1 'docker run --rm --entrypoint bash vllm/vllm-openai:v0.26.0 -c \
  "cd /usr/local/lib/python3.12/dist-packages/vllm && grep -n \"num_blocks = \" v1/core/kv_cache_utils.py"'
```

```
1005:  num_blocks = int(available_memory // page_size // num_layers)
1322:  num_blocks = available_memory // total_num_bytes_per_block
1376:  num_blocks = available_memory // kv_cache_groups[0].kv_cache_spec.page_size_bytes
1409:  num_blocks = get_num_blocks(vllm_config, group_size, available_memory, page_size)
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:28-30` and `records/evidence/2026-08-24-config-sweep/README.md:121-126`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
