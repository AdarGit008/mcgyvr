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

## Phase 2 — `load` (34 loads, 2279 s, one model at a time, cleared between)

| metric | n | min | p50 | p95 | max |
|---|---|---|---|---|---|
| `load_seconds`, succeeded | 24 | 29 | 32 | 37 | 38 |
| `load_seconds`, refused | 10 | 91 | 99 | — | 145 |

`LOAD_TIMEOUT_S = 2400` against a 38 s worst case is **63×**. Harmless, and the
refusals took 91–145 s only because each is two full clear-load attempts.

### Finding C3 — `MIN_VRAM_FRACTION = 0.8` makes five real models unmeasurable

The distribution is clean and the threshold sits in the gap:

| | n | vram_fraction |
|---|---|---|
| model fits on the card | 24 | **0.908 – 1.000** |
| model does not fit | 5 | 0.297, 0.330, 0.581, 0.581, **0.794** |

So as a *detector* it works. As a *policy* it is wrong. Every one of the five is
a model larger than srv2's 12 GB card — `gpt-oss:20b` (13.8 GB) reached **0.794**,
six thousandths under the line — and a model larger than the card **cannot** be
fully resident. Refusing them means the instrument cannot measure five of the
twelve models that host actually holds, permanently.

The refusal message this lane wrote says *"a model far larger than the card is
the known case — it never reaches 80% VRAM, and this refusal is the correct
answer about it rather than a bug to route around."* That is the sentence to
withdraw. The check was written to catch **placement contamination** — a model
pushed onto the CPU because another engine held the card, measured at 0.07 — and
it cannot tell that apart from a model that simply does not fit.

`claim` already checks `card_idle_before_load` separately, and that is the check
that catches contamination. When the card was verified idle and the model still
lands partly on the CPU, that is the honest placement for that model on that
host.

**Decision owed.** Record `placement: full | partial` with the fraction and stop
refusing on it when the card was idle beforehand — which makes all 17 models
measurable — or keep refusing and accept that srv2's five largest are outside
the instrument.

## Phase 3 — `ramp` (the concurrency matrix, 11127 s)

### Finding C4 — `RAMP_TOKENS` decides whether the rule is right at all

Ollama, both hosts, three token counts, nothing else varied:

| host | configured | tokens | knee reported | max speedup | throughput plateau |
|---|---|---|---|---|---|
| srv1 | `-np 2` | **32** | **12** | **2.52** | 12 |
| srv1 | `-np 2` | 128 | none | 1.70 | 4 |
| srv1 | `-np 2` | 512 | none | 1.48 | 2 |
| srv2 | `-np 1` | **32** | **12** | **2.27** | 12 |
| srv2 | `-np 1` | 128 | none | 1.35 | 6 |
| srv2 | `-np 1` | 512 | none | 1.09 | 2 |

At 32 tokens both hosts clear the `BATCHING_SPEEDUP = 2.0` gate and report a
knee of **12** — wrong for both, and *identical* on two hosts configured one slot
apart. The rule declines correctly only at 128 and 512.

This is the measurement that was owed. `RAMP_TOKENS = 128` was chosen by
reasoning and never varied, and the earlier record said only that the plateau
"could move with it". It does more than move: at 32 tokens the rule produces a
confident wrong answer, and at 128 it produces the right refusal. Short
generations are prefill-dominated, and prefill batches well on an engine whose
decode does not — so the speedup gate measures the wrong phase of the work.

The throughput plateau alone is also unstable across token counts (12 / 4 / 2 on
srv1, 12 / 6 / 2 on srv2), so the "plateau of 6 on both ollama hosts" recorded
earlier was a fact about 128-token generations, not about the engine.

**Decisions owed.**
1. `RAMP_TOKENS` is not a tuning knob — it is part of the measurement's
   definition, and any reported width must carry the token count it was measured
   at. 512 gives the cleanest ollama refusal (1.48 / 1.09).
2. `BATCHING_SPEEDUP = 2.0` does not survive as a token-count-independent gate.
   Either the gate moves with the token count, or the measurement is defined at
   one token count and the constant is calibrated there and only there.

### Harness defect — ten vLLM ramps produced nothing

All ten vLLM launches in the first matrix failed with `served=[], gpu=1 MiB`.
`calibrate.py` passed no `env`, so a pip-installed vLLM started without
`CUDA_HOME` and never came up, and `claim` correctly refused an empty card. The
harness also picked the first AWQ model alphabetically, which put a 14B on a
12 GB card. Both fixed; the vLLM half of the matrix is being re-run.

The refusal working exactly as designed is the reason this cost only rig time
rather than ten rows of plausible nonsense.

## Addendum, 2026-08-19 — the ollama matrix replicated

The first attempt to re-run the vLLM half re-ran ollama instead: the harness patch
had died on an assertion and written nothing, so the unchanged harness ran the full
matrix again and spent 1.5 h of rig time. As evidence that is not wasted — it is an
independent replication of Finding C4 on the same hardware:

| host | tokens | knee, run 1 | knee, run 2 | speedup, run 1 | speedup, run 2 |
|---|---|---|---|---|---|
| srv1 | **32** | **12** | **12** | 2.52 | 2.49 |
| srv1 | 128 | none | none | 1.70 | 1.70 |
| srv1 | 512 | none | none | 1.48 | 1.45 |

The token-count dependence is reproducible, not a single bad matrix. At 32 tokens
the rule is confidently wrong twice; at 128 and 512 it declines twice.

The launch failure is worth recording beside the numbers, because it is the third
instance of one mechanism in this campaign: `str.replace` returns its input
unchanged when the pattern misses, and `ruff format` reflows the code between the
read and the patch, so an edit that did nothing reports no error. The first two
instances cost minutes; this one cost 1.5 h of rig time, because the file was never
re-read before the run was launched. Verifying the marker in the file and launching
are now one step.

### Finding C5 — ollama's slots are real, they contend, and there is no batching past them

Derived from the ramp levels already in `samples.jsonl`. No new rig time: the
question was answerable from data the matrix had already paid for.

Both hosts ramped the **same model** (`qwen2.5-coder:1.5b`), so srv1 (`-np 2`)
against srv2 (`-np 1`) is a one-variable comparison. Throughput cannot settle it —
the discriminator is **wall time against mean latency at n=2**, which separates
"the two requests ran together" from "the second one waited".

At 512 tokens, where generation dominates and per-request overhead is ~5%:

| | n=1 latency | n=2 wall | n=2 mean latency | serial predicts wall | concurrent predicts wall |
|---|---|---|---|---|---|
| srv1 `-np 2` | 4.14 s | **6.01 s** | 6.01 s | 8.28 s | 6.01 s |
| srv2 `-np 1` | 4.17 s | **7.95 s** | 6.06 s | 8.34 s | ~6 s |

srv1's wall equals its mean latency: both requests were in flight in the same
window. srv2's wall exceeds its mean by 1.9 s and lands within 5% of the serial
prediction: the second request queued. **Two slots run concurrently; one slot
serializes.**

Three consequences, each measured:

1. **The slots contend.** Two concurrent sequences on srv1 cost 1.45x the
   single-sequence time each, so throughput rises 1.45x rather than 2x. They share
   the same compute.
2. **Nothing batches past `-np`.** srv1's speedup creeps from 1.45 at n=2 to 1.47
   at n=24 — that residual is keeping both slots full, not admitting more work into
   a batch. vLLM at width 8 reached 2.52x by comparison.
3. **`-np` is a configured choice, not a property of the host.** srv2's 1 is a
   *measured* value — `-np 1` on the `llama-server` command line and
   `total_slots: 1` from `/props` — not an inference from an unset environment
   variable. Ollama also re-derives it per model: srv1 gives `nemotron-3-nano:4b`
   one slot on a host configured for two (Finding 2b of the serving record). Any
   row that reports a width must therefore carry the width that was configured
   *for that model on that host at that moment*, which is the gap named in the
   schema note below.

#### Why the 32-token rows read a knee on a one-slot server

srv2 has one slot and reads **2.27x** at 32 tokens. Model-level batching cannot
produce that. The mechanism is per-request fixed cost — HTTP, tokenize, schedule,
detokenize — which runs on the CPU and overlaps with GPU work on a *different*
request:

| generation length | time per request (srv2) | generation | fixed cost |
|---|---|---|---|
| 32 tokens | 0.64 s | ~0.27 s | **~0.37 s (58%)** |
| 512 tokens | 4.17 s | ~4.0 s | ~0.2 s (5%) |

At 32 tokens more than half of each request is overlappable overhead. The ramp
watches only total tokens per second, so it cannot distinguish "the server did
more work at once" from "the paperwork happened while the GPU was busy" — it
clears the `BATCHING_SPEEDUP` gate and reports a knee of 12 on a server with one
slot.

This is the mechanism behind C4 rather than a separate finding: C4 recorded that
the rule is confidently wrong at 32 tokens, and this states why.

#### What the ramp should have been measured at

`RAMP_TOKENS` was chosen to be "enough work to overlap" and never checked against
the workload the bench actually generates. Measured over **33,358 completions in
170 measurement files** under `records/measurements/`:

| p25 | p50 | p75 | p90 | p99 | max |
|---|---|---|---|---|---|
| 117 | **194** | 319 | 475 | 768 | 2048 |

28.5% of real replies are shorter than 128 tokens; 92.1% are shorter than 512. So
`RAMP_TOKENS = 128` sits near the 28th percentile of the served workload — most
real replies are longer than the length the batch width was measured at — and 512
sits near the 92nd. The grid brackets the workload; no point on it is *at* it.

**This sharpens C4's first decision.** A reported width must carry its token count,
and the token count that describes this bench is its own median, not a round
number: **194 for the typical case, 475 for the tail.** Measuring at 32 is
measuring a workload this project does not run.
