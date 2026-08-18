# Calibrating the constants — measured, 2026-08-19

Every threshold and timeout in `tools/bench/serving/` was chosen from one or two
observations, several from a single model on a single host. `BATCHING_SPEEDUP`
carried a docstring admitting it was a judgement calibrated on four
measurements; the others did not, and two (`0.95` for the throughput plateau,
`0.10` for the latency plateau) were function defaults invisible to review.

This is the campaign that measures them. `samples.jsonl` holds every observation
as it was taken, including every level of every ramp, so a threshold can be
re-derived later without re-running the rig.

**Nothing here changed a constant on its own.** The numbers are below; each
decision is recorded beside them.

## Phase 1 — `fast` (320 samples, 158 s, no model loaded)

| metric | n | min | p50 | p95 | max |
|---|---|---|---|---|---|
| `ssh_step_seconds` | 60 | 0.884 | 0.956 | 1.40 | 2.22 |
| `discovery_seconds` | 51 | 0.135 | 0.141 | 0.153 | 1.44 |
| `capture_show_seconds` | 17 | 0.719 | 1.181 | 1.51 | 2.16 |

### Finding C1 — `MAX_INLINE_ITEMS = 512` splits one field inconsistently

Array lengths across all 17 models, by key:

| key | n | min | max |
|---|---|---|---|
| `tokenizer.ggml.merges` | 16 | 99,757 | **446,189** |
| `tokenizer.ggml.tokens` | 17 | 64,000 | 201,088 |
| `tokenizer.ggml.token_type` | 17 | 64,000 | 201,088 |
| `tokenizer.ggml.scores` | 4 | 64,000 | 201,088 |
| **`tensors`** | 17 | **255** | **843** |
| everything structural | 61 | 1 | **52** |

`observed.py` documents 512 as "keeps every structural list inline — the 1.5B's
`tensors` is 338 rows — and elides only the three tokenizer arrays". That is
false across the corpus: `tensors` runs 255–843, so at 512 some models keep it
inline and others have it elided. The same field behaves differently per model,
which is exactly what a reader of two captures would not expect.

The measured gap between structural metadata and everything larger is
**52 → 255**. Any threshold inside it elides `tensors` for every model; any
threshold ≥ 1024 keeps it for every model. 512 is the one range that is
inconsistent.

**Decision owed.** Consistency matters more than which side: either elide
`tensors` everywhere (threshold in 52–255) and rely on the digest, or keep it
everywhere (≥ 1024) at ~60 KB per capture for the largest model.

### Finding C2 — the idle-card metric measured a loaded card

`idle_gpu_mib` was sampled 30 times per host with nothing to guarantee the card
was idle. srv1 returned **4958 MiB in all 30 samples** — vLLM was serving
throughout. Only srv2's 30 samples (**1 MiB**, every one) describe an idle card.

So the useful reading is the separation: idle is **1 MiB**, a loaded card is
**4958 MiB**, and `IDLE_GPU_MIB = 500` sits inside a gap three orders of
magnitude wide. The threshold is safe; the *measurement* was not what its name
claimed, and the harness has been left as-is so the contamination stays visible
in `samples.jsonl` rather than being quietly re-run.

### Timeouts against their measured distributions

| constant | value | measured max | ratio |
|---|---|---|---|
| `STEP_TIMEOUT_S` | 180 | 2.22 s | 81× |
| `DISCOVERY_TIMEOUT_S` | 5.0 | 1.44 s | 3.5× |
| `CAPTURE_TIMEOUT_S` | 30.0 | 2.16 s | 14× |

`STEP_TIMEOUT_S` looks absurd against a 2.2 s worst case, and is not: it was
raised from 30 s after a step timed out on a host thrashing with a 36 GB model
in page cache. The distribution above is the quiet case. What the ratio shows is
that the constant is a tail-guard, not a typical-case budget — which is worth
stating, because a reader comparing 180 to 0.96 would otherwise cut it.
