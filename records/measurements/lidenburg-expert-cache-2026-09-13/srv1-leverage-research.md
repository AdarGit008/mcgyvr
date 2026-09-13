# srv1 leverage — prior-art research (researcher subagent, 2026-09-13)

Goal: find testable leverage for srv1 (GTX 1660 SUPER 6 GB sm_75, 16 GB RAM, i5-9600K)
running Qwen3.6-35B-A3B (13.2 GB IQ3_XXS, 3B active) on llama.cpp MoE CPU-offload.

## Key facts (verified)

- **sm_75 (Turing) still in llama.cpp/ggml 0.15.x** default CUDA arch list. Pin
  `-DCMAKE_CUDA_ARCHITECTURES=75` (CUDA 13 auto-detect can emit broken PTX).
- **GTX 1660 SUPER (TU116) has NO tensor cores** — INT8 `dp4a` path only; kernel choice matters.
- **Turing Qwen3.5/3.6 SSM/Gated-DeltaNet regression** (fixed `0b14b87d7`); `--draft-mtp`
  does **not** activate on sm_75 for Qwen3.6 (issue #24670).
- **Dominant cost = 13.2 GB expert weights, not KV** — the model is KV-light (only 10/40
  layers use per-token attention KV; 30 use Gated DeltaNet linear attention, O(1) state).
- **No per-expert hot/cold cache is merged in mainline.** 4 closed PRs, 1 open.

## Ranked candidates (highest leverage first)

1. **Lidenburg 3-tier expert cache (GPU+RAM tiers only)** — +60–66% reported on this exact
   model; but single-request-only, Linux/NVIDIA, tested only on RTX 5080 (Blackwell), never
   sm_75/6 GB. https://github.com/Lidenburg/llama.cpp
2. **Mainline fit tuning — do first.** `--n-cpu-moe N` sweep + `-ctk q8_0 -ctv q8_0 -fa on`,
   sm_75 build. Zero-fork baseline. https://github.com/ggml-org/llama.cpp/pull/15077
3. **2-tier GPU+RAM cache from closed mainline PRs** — the right-fit design for srv1 (model
   fits RAM; PCIe is the bottleneck; no disk tier). #24524 (adaptive VRAM cache), #26563
   (`-ehs N`, closed "with plans to re-open"), #26824 (heatmap + mmap pinning). Cherry-pick cost.
4. **SM75-tuned quant forks** — nisten/prism-ml-biturbo (GTX 1660 Ti 6 GB: dp4a + 4-bit KV,
   closest hardware match), atomicmilkshake/llama-cpp-turboquant (TurboQuant + TriAttention),
   LL4nc33/llama-tq. Alpha/buggy.
5. **KV cache quantization** — symmetric `q8_0/q8_0` (default build); asymmetric `q8_0/q5_1`
   needs `-DGGML_CUDA_FA_ALL_QUANTS=ON` or flash-attention silently falls back to CPU.
   discussions/23470.
6. **KV offload/dynamic** — `--no-kv-offload` (long-standing); `--kv-dynamic` (open PR #21757).
7. **KV eviction forks** (TriAttention / H2O / SnapKV / StreamingLLM) — low value here (KV-light
   model). mit-han-lab/streaming-llm; peva3/turboquant-h2o-streamingllm.
8. **Model/quant swap** — smaller active MoE or IQ2_XXS. Config change, not code.

## Recommended first test

Mainline llama.cpp pinned sm_75; sweep `llama-server -ngl 99 --n-cpu-moe <N> -fa on
-ctk q8_0 -ctv q8_0 -c 16384` over N, logging the `llama_memory_breakdown` table. Reveals
whether expert caching (candidates 1/3) or plain fit tuning (candidate 2) is the higher
leverage before touching any fork.

## Caveats

- **No independent expert-cache measurement exists for a 6 GB sm_75 + 16 GB RAM box** —
  Lidenburg's nearest config was Blackwell 12 GB. Treat all magnitudes as unverified for srv1.
- Lidenburg is **single-request-only** (breaks with `users > 1`); srv1 serves `--parallel 2`.
- Contradiction: operator "q8_0 KV = 5.2 GB @ 256k" vs researcher head-count math (suggests
  smaller, implying DeltaNet state or buffer accounting) — resolve by on-rig measurement.

Full report: subagent artifact `e86aaf37` (`research.md`, 18.3 KB) in the session dir.
