# Speculative Decoding — BYOB Due Diligence (2026-08-27)

**Question.** Verify/falsify the kickoff claim *"srv2 (12 GB) is the only real SD machine"* and smoke-test `Qwen2.5-Coder-1.5B → 7B` on srv2. Method is **BYOB**: measure our own non-SD baseline on the same rig (not published numbers), then compare SD against it.

**Harness.** `bench_sd.py` — self-contained vLLM 0.26.0 offline benchmark (docker `vllm/vllm-openai:v0.26.0`, `llm.chat`), modeled on the official
`examples/features/speculative_decoding/spec_decode_offline.py`. Accept metrics from `llm.get_metrics()`: `vllm:spec_decode_num_drafts/_num_draft_tokens/_num_accepted_tokens/_num_accepted_tokens_per_pos`. Greedy (temp=0), decode-dominated prompts, 30×256 tokens (7680 tok/run). Unless noted: `gpu-mem 0.90, max-model-len 4096, num-spec 4`.

**Models on disk** (HF AWQ): `Qwen/Qwen2.5-Coder-{1.5B,3B,7B}-Instruct-AWQ` on both boxes; srv2 also has `14B`.

---

## 0. Vocabulary finding (the blocker the brief missed)

Qwen2.5-Coder splits vocab by size group:

| Size | vocab_size |
|------|-----------|
| 0.5B / 1.5B / 3B | **151936** |
| 7B / 14B / 32B | **152064** |

vLLM therefore refuses `1.5B(151936) → 7B(152064)`:
`Target and draft model should have the same vocabulary size ... vocab_size=152064 ... 151936`.

The 128-token delta is **embedding padding only** — the tokenizer content is byte-identical across all sizes (Qwen pads embedding rows to /128 for small, /256 for large for distributed-training alignment; IDs above ~151646 are padding). So there is **no config-level same-vocab small draft for the 7B target** in the family. The Qwen requirement: `use_heterogeneous_vocab: true` (Token-Level Intersection, **greedy-only**; merged in v0.26.0). `llama.cpp` instead tolerates the delta naturally (`SPEC_VOCAB_MAX_SIZE_DIFFERENCE=128` + byte-identical tokenizer).

---

## 1. srv1 (GTX 1660 SUPER, 6 GB, compute-cap **7.5**) — verify/falsify

| config | tok/s | mean AL | vs baseline |
|---|---|---|---|
| 3B baseline (eager) | 64.87 | — | 1.00× |
| 3B baseline (CUDA graphs) | 64.85 | — | 1.00× |
| 3B + 1.5B SD (eager) | 43.37 | 4.227 | **0.67×** |
| 3B + 1.5B SD (CUDA graphs) | 37.97 | 4.199 | **0.59×** |
| 7B baseline (any) | **FAILS to load** | — | — |

- **SD runs on srv1** with **high acceptance** (per-pos α ≈ 0.90/0.83/0.77/0.72; mean ~4.2 tokens/draft) — so *"srv1 can't run SD at all" is false.*
- **But it is NET-NEGATIVE**: 0.59–0.67× baseline. The 1.5B draft's compute + verify overhead isn't amortized on the weak Turing card.
- **CUDA graphs give zero benefit on srv1** (baseline eager = baseline graphs = ~64.85). Turing CC 7.5 has no FA2/FlashInfer (`FA2 only supported on compute capability >= 8`); vLLM falls back to TRITON, so graphs are not the unlock.
- **7B cannot even be loaded on srv1**: `FA2 is only supported on devices with compute capability >= 8` (CC 7.5), independent of memory. srv1's ~3.5 GiB usable KV also can't hold 7B target + 1.5B draft.

**Verdict (srv1):** srv1 can *mechanically* run SD but it regresses throughput, cannot host the 7B-class target, and CUDA-graph fixes don't help. It is not a "real SD machine" for meaningful targets.

---

## 2. srv2 (RTX 3060, 12 GB, compute-cap **8.6**) — smoke test 1.5B → 7B (cross-vocab)

| config | tok/s | mean AL | vs baseline |
|---|---|---|---|
| 7B baseline (eager) | 320.99 | — | 1.00× |
| 7B baseline (CUDA graphs) | 475.37 | — | 1.00× |
| 7B + 1.5B SD (eager, cv) | 240.23 | 4.204 | **0.75×** |
| 7B + 1.5B SD (graphs, cv) | 418.39 | 4.207 | **0.88×** |
| 7B + 1.5B SD (graphs, cv, FLASH_ATTN) | 411.51 | 4.207 | **0.87×** |
| 7B baseline (graphs, batch 1) | 68.23 | — | 1.00× |
| 7B + 1.5B SD (graphs, cv, batch 1) | 69.33 | 4.271 | **1.02×** |

- The **exact requested pair runs** (cross-vocab TLI, greedy), with **high acceptance** (α ≈ 0.90/0.83/0.77/0.71; mean ~4.2 tokens/draft).
- **But no net speedup**: 0.75–0.88× at batch 8; ~1.02× at batch 1 (within noise). The TLI overhead + draft compute on the 3060 is not amortized.
- **CUDA graphs help the baseline** (321→475, 1.48×) but do **not** rescue SD (still 0.88×).
- **Forcing FLASH_ATTN** (researcher's #1 lever for the #49547 FlashInfer→PIECEWISE downgrade) did **not** flip it (411.5, still 0.87×).
- Consistency: the prior `2026-08-24-config-sweep` already found **ngram SD net-negative on both boxes** (srv1 0.62–0.74×, srv2 0.37–0.90×). draft_model agrees.

---

## 3. Verdict

**"srv2 (12 GB) is the only real SD machine" → VERIFIED in practice.** srv1 can't host a meaningful target (7B won't load on CC 7.5; ~3.5 GiB KV), and its SD is net-negative. srv2 is the only viable SD rig.

**The deeper, more important finding → the brief's implied "2–4× speedup" does NOT materialize for `Qwen2.5-Coder` via vLLM `draft_model` on these consumer GPUs.** Acceptance is high (α ≈ 0.9 initial, ~4.2 tokens/draft), yet wall-clock **regresses** at batch 8 (0.75–0.88×) and is a wash at batch 1 (~1.02×), across eager/CUDA-graph and default/FLASH_ATTN backends. High α ≠ speedup here.

**BUT llama.cpp `--model-draft` DOES win (~+10–11%)** — the opposite sign from vLLM, and it needs no cross-vocab surgery (see §4). This is the one path that beats target-alone for this pair on srv2.

## 4. llama.cpp `--model-draft` (the win path) — srv2

Image `ghcr.io/ggml-org/llama.cpp:server-cuda-b10481`, `llama-server`, `-ngl 99`, single-slot, `temperature 0`, 150-token completion. Draft `qwen2.5-coder-1.5b-instruct-q6_k.gguf` (1.5B / vocab 151936), target `Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf` (vocab 152064) — **diff 128, which llama.cpp's `SPEC_VOCAB_MAX_SIZE_DIFFERENCE` (=128) tolerates natively** (byte-identical tokenizer), so `--spec-type draft-simple` just works, no TLI.

| config | tok/s | vs baseline |
|---|---|---|
| 7B alone | 72.7 | 1.00× |
| +1.5B draft, `--spec-draft-n-max 2` | 76.0 | 1.05× |
| +1.5B draft, `--spec-draft-n-max 3` | 80.2 | 1.10× |
| +1.5B draft, `--spec-draft-n-max 4` | **80.9** | **1.11×** |
| +1.5B draft, `--spec-draft-n-max 5` | 79.7 | 1.10× |

- **llama.cpp is the one runtime that beats target-alone here** (+10–11%, plateau at NMAX 3–5). It tolerates the 128-token vocab diff natively, so the 1.5B draft runs as a plain small GGUF with **no TLI intersection cost** — exactly the overhead that sank vLLM `draft_model`.
- **Not EAGLE3**: `--spec-type draft-eagle3` needs a dedicated EAGLE head checkpoint; we only have a plain 1.5B draft GGUF (→ `draft-simple`). No published Qwen2.5-Coder EAGLE head exists, so `--model-draft` (draft-simple) is the available path.
- **Scale caveat**: +10% is far from the brief's "2–4×". This is single-slot (batch-1) latency; the absolute ceiling on this hardware is ~81 tok/s for the heavily-quantized IQ4_XS target.

## Root causes (measured + sourced)

- **Draft overhead isn't amortized on compute/bandwidth-bound consumer cards** (RTX 2070 ref: cost_ratio 1.18×; target already cheap → draft is pure overhead). This dominates on both the 3060 and 1660 SUPER.
- **vLLM #47460** (draft ran fully eager; merged in v0.26.0) — was the historic net-negative cause; fixed, but graphs still don't rescue it here.
- **Cross-vocab TLI** adds intersection/constraint cost and is greedy-only.
- **srv1 CC 7.5**: no FA2/FlashInfer (TRITON fallback), no CUDA-graph benefit, 7B unloadable.

## Options ranked (for actually getting a win)

1. **Same-vocab pairing** (best α, no TLI cost) — but Qwen2.5-Coder has **no** same-vocab small draft for the 7B target (only 151936 family is small: 0.5/1.5/3B). For a *3B target* the 1.5B draft is same-vocab and ran clean (but regressed on srv1 anyway).
2. **Force `VLLM_ATTENTION_BACKEND=FLASH_ATTN` + CUDA graphs** (tested: no win here). Consider `--kv-cache-memory` to claw back KV and raise concurrency where SD *can* win on datacenter-class loads — but on 12 GB the headroom is small.
3. **llama.cpp `--model-draft`** — **MEASURED (srv2): +10–11% (80.9 vs 72.7 tok/s)**, the only path that beats target-alone. Accepts the 128-token delta natively, no TLI. (Matches the Reddit 32B+1.5B RTX 3090 report.)
4. **Skip draft-model SD** — expected. For throughput on these cards the target alone (with CUDA graphs) is the better engine; SD only makes sense at very low concurrency where the gain is ~1.02% here. N-gram/suffix SD was already shown net-negative.

## Untested levers (recommended if pursued)

- `VLLM_ATTENTION_BACKEND=FLASH_ATTN` doesn't help (**confirmed**); try **PIECEWISE/`FLASH_ATTN` with explicit `--kv-cache-memory`** and a **smaller draft (0.5B)** to cut draft cost.
- **SGLang EAGLE3** (best Qwen3-SpecForge support, published draft checkpoints) — different stack, would need install; the realistic path to a real Qwen SD speedup but out of scope for a vLLM smoke.

## Sources

- vLLM draft_model docs / PR #38174 (TLI semantics, greedy-only, ~99.8% overlap → ~61% acceptance, `unk_token_id` req) — https://github.com/vllm-project/vllm/blob/main/docs/features/speculative_decoding/draft_model.md
- vLLM PR #13849 (vocab diff = embedding padding /128 vs /256, byte-identical tokenizer; RTX 4090 0.5B→7B 1.72× batch-1; **CLOSED not merged**) + issue #5203 / #10913 (Qwen padding statement)
- vLLM PR #47460 (draft_model ran eager → net-negative; fixed in 0.26.0)
- vLLM issues #49547 / #49986 / #49548 (FlashInfer→PIECEWISE downgrade −16%; dynamic-SD baseline tax)
- llama.cpp `common/speculative.cpp` (`SPEC_VOCAB_MAX_SIZE_DIFFERENCE=128`, vocab-type/bos-eos/content checks) + PR #3812 + `docs/speculative.md`
- Qwen HF config.json per size (0.5B/1.5B/3B/7B/14B/32B) — canonical vocab_size
- unsloth spec-decode docs (llama.cpp only, same-tokenizer required)
- r/LocalLLaMA (32B+1.5B llama.cpp cross-vocab on RTX 3090)
- NVIDIA TensorRT-LLM lookahead (datacenter 3.6×/1.6× — not consumer vLLM)
