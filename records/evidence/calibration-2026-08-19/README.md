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

### Finding C6 — the vLLM matrix: the plateau recovers the flag, and both gates are wrong

15 ramps, 5 configured widths x 3 token counts, srv1, `Qwen2.5-Coder-1.5B-AWQ`,
11432 s. Every launch clean; the 15 error rows in `samples.jsonl` are the earlier
runs that had no `env`.

| configured `--max-num-seqs` | 32 tok | 128 tok | 512 tok | throughput plateau (all three) |
|---|---|---|---|---|
| 1 | none | none | none | 4 / 2 / 1 |
| 2 | none | none | none | 1 / 1 / 1 |
| **4** | none | none | none | **4 / 4 / 4** |
| **8** | **16** | 8 | 8 | 16 / 8 / 8 |
| **16** | 16 | 16 | 16 | 16 / 16 / 16 |

**The throughput plateau recovers the configured width exactly at 4, 8 and 16**,
and 128 agrees with 512 at every one of the five widths. Three distinct configured
values recovered on one engine is a stronger result than the two this lane had.

#### `BATCHING_SPEEDUP` does not survive, and no value of it would

At width 4 the plateau is **4 at all three token counts** — three independent
measurements, each correct — and the gate discards all three because the speedup
is 1.23-1.49. The curve is unambiguous: at 512 tokens throughput is 44.0 tok/s at
n=1, rises to 54.0 at n=4, and is 54.2 at every level from 8 to 24.

The threshold cannot be lowered to fix it:

| curve | max speedup | plateau | truth |
|---|---|---|---|
| vLLM `--max-num-seqs 4` @512 | **1.23** | 4 | 4 |
| ollama `-np 2` @512 | **1.45 / 1.48** | 2 (run 1), 4 (run 2) | 2 |

Any gate low enough to admit the first admits the second, whose plateau is
unstable across replications and unrelated to its slot count. So the failure is
not a mis-set number — **speedup magnitude cannot separate these two curves at
any threshold**, because it measures how much compute headroom the card had, not
whether the engine batches. `BATCHING_SPEEDUP` is a concept to withdraw, not a
constant to recalibrate.

#### The single wrong cell is the unnamed 0.95, not the token count

Width 8 at 32 tokens is the only cell in the matrix that reports a wrong width. It
is not a token-count effect in the way C4's ollama result was:

```
n= 8   95.3 tok/s      95.3 / 101.5 = 0.939   <- just under the 0.95 cutoff
n=16  100.7 tok/s
n=24  101.5 tok/s      peak
```

`_throughput_plateau` takes the first level reaching **0.95 x peak**. At 32 tokens
n=8 lands at 0.939 of peak — short by 1.1 tok/s — so the rule walks on to n=16. At
512 tokens the same width gives 106.7 against a peak of 107.1 (0.996) and reads 8.

So the two thresholds that were function defaults, invisible to the review that
scrutinised `BATCHING_SPEEDUP`, are between them responsible for every wrong
answer in this matrix: `0.95` produces the one false width, and `BATCHING_SPEEDUP`
suppresses three correct ones.

#### Partial batches cost a full batch-time, at every width

The dips reproduce across all five widths and all three token counts, which makes
them scheduler behaviour rather than noise:

- **n=2 is slower than n=1 at every single width** (0.62x - 0.74x). Two requests
  cost more than one and deliver less throughput than one.
- **n=12 against width 8**: 1.84x versus 2.43x at n=8 and n=16 — one full batch of
  eight plus a two-thirds-empty batch of four pays two batch-times for one and a
  half batches of work.
- **n=6 against width 4**: 0.93x versus 1.23x at n=4 and n=8 — the same arithmetic
  one width down.

Latency shows it directly: at width 8 and 512 tokens, mean latency is 37.25-38.36 s
flat across n=2 to n=8 (one batch, finishing together), then steps to 50.86 s at
n=12.

#### A prediction that was tested and did not bite

srv1's `kv_cache_max_concurrency` measured **16.004** at `max_model_len 8192`, so
the matrix's top width sat exactly at the KV-cache ceiling and a knee below 16 was
expected as capacity binding rather than method failure. It read **16 at all three
token counts**. The ceiling was reached, not exceeded.

#### Widths 1 and 2 have no signal to recover

Width 2 reads a speedup of exactly **1.00** at all three token counts, with a
plateau of 1. This is not a gate suppressing an answer — vLLM at two sequences
batches no better than at one on this model and card. A method that reported 2
here would be reading noise.

#### Decisions owed

1. **Withdraw `BATCHING_SPEEDUP`.** Shown above to be unfixable by recalibration.
   The replacement question is whether the ramp needs an engine gate at all:
   ollama's width is *readable* (`total_slots` from `llama-server`'s `/props`,
   confirmed four ways), and only vLLM's `max_num_seqs` is unaskable. Making the
   ramp a vLLM instrument removes the gate from the path entirely — at the cost of
   the independent cross-check that first caught the `-np`-versus-`/props`
   agreement.
2. **Name and set the plateau cutoff.** `0.95` is a function default at
   `contract.py:429`. It produced the matrix's only false width at a margin of
   1.1 tok/s. Whatever it becomes, it must be a named constant beside the others.
3. **`RAMP_TOKENS`**: 128 and 512 agree at every width, so anything >= 128 is
   stable for vLLM. Against the served workload (median 194, p90 475 - see above),
   the defensible choices are 194 or 475, not 128.

## Owner decisions, 2026-08-19

Taken in session, one at a time, against the findings above. Each block records the
decision, the evidence that decided it, and what it costs. These are decisions on
this lane's constants; they are not amendments to any ADR.

### D1 — `BATCHING_SPEEDUP` is set to 1.0, renamed, and confined to the inferred path

**Decided: record both widths.** The constant survives as a number and does not
survive as a concept.

What the review above got wrong: "no threshold fixes it" was a claim about
separating vLLM@4 (1.23) from ollama@2 (1.45), and that claim is true. But
separating them is not the job. Recomputed from `samples.jsonl`, a `> 1.0` gate at
512 tokens is exact on vLLM:

| configured | max speedup | plateau | `> 1.0` reports | truth |
|---|---|---|---|---|
| 1 | 1.02 | 1 | 1 | 1 |
| 2 | 1.00 | 1 | *declined* | 2 |
| 4 | 1.23 | 4 | 4 | 4 |
| 8 | 2.43 | 8 | 8 | 8 |
| 16 | 3.78 | 16 | 16 | 16 |

Four correct, one declined, **no wrong answer**. At 2.0 the same matrix gives two
correct and three correct answers suppressed. The gate at 1.0 says only *concurrency
raised throughput at all, so a plateau is claimable* — it asserts nothing about
batching, and it is renamed accordingly.

**The result is coupled to `RAMP_TOKENS` (D3).** At 128 tokens the same rule reads
2 for a 1-sequence server (speedup 1.06, plateau 2); at 32 it reads 4 for that
server and 16 for an 8-sequence one. The clean column is 512.

**`batches` is retired with the concept.** C5 showed it reads `true` for srv2's
**one-slot** ollama at 2.27 — 58% of a 32-token request there is CPU-side fixed
cost overlapping across requests. The field asserted batching on a server that
provably cannot batch.

**One field, one meaning, both engines.** The width now carries its provenance:

| field | vLLM | ollama | meaning |
|---|---|---|---|
| `width` | inferred | declared | the server's concurrent-sequence limit |
| `width_source` | `inferred_plateau` | `declared_props` | how it is known |
| `max_speedup_vs_n1` | as measured | as measured | peak throughput over the single-request rate — a raw statistic carrying no verdict |

`llama-server`'s `/props` answers `total_slots` directly (confirmed four ways);
only vLLM's `max_num_seqs` is unaskable. Inference on ollama is measurably unfit
for the `width` field: at 512 tokens srv2 `-np 1` reads 2, and srv1 `-np 2` reads
2 on one run and 4 on an identical rerun.

**ollama keeps ramping.** The declared width goes in `width`; the inferred plateau
is recorded beside it in `readings`. Every ollama run is then a live test of the
inference method against ground truth on the same host — a stronger cross-check
than the one being replaced, which had nothing to compare against. The cost is the
ramp's rig time on an engine whose width could be read in one HTTP call.

### D1, amended the same day — a plateau is not a slot limit

The decision above put a declared value and an inferred one in one `width` field.
That reintroduced, one level down, the defect it had just fixed: the two sources do
not measure the same quantity.

- **Declared slots** are a *scheduler* limit. `--max-num-seqs`, `-np`. The server
  will not run more sequences than this, ever.
- **The throughput plateau** is a *workload* measurement: the offered concurrency
  past which this model, on this card, at this generation length, stops delivering
  more tokens per second.

They coincide only when the scheduler limit binds before the hardware does, and
nothing guarantees that. **This lane already measured a divergence**: ollama on
srv2 with `-np 1` reads a plateau of **2** at 512 tokens. One slot, and the curve
still rose from n=1 to n=2, because per-request CPU-side fixed cost overlaps across
requests — C5's mechanism. The plateau exceeded the limit.

The opposite direction — a model saturating the card at n=4 while configured for 16,
so the plateau *under*-reads the limit — is **untested, not excluded**. Every vLLM
width up to 16 was recovered on a 1.5B AWQ model with headroom to spare on srv1's
card. A 7B, or srv2's 12 GB card, is where it would appear.

So C6's result is restated: **at 4, 8 and 16 the flag bound before the card did, so
the plateau recovered it there.** Not "the plateau measures the concurrency limit".

**The fields split.** No `width`, no `width_source`.

| field | source | what it is |
|---|---|---|
| `declared_slots` | ollama `/props total_slots`; `null` on vLLM (unaskable) | the scheduler's hard limit — a read, not a derivation, and immune to every threshold below |
| `saturation_n` | the throughput curve | the concurrency past which throughput stops rising, for this model, card and token count |
| `max_speedup_vs_n1` | the curve | peak over the single-request rate; a raw statistic carrying no verdict |

Where both exist their agreement is a reported finding, not a hidden assumption:
srv2's `declared_slots: 1` beside `saturation_n: 2` is now an interpretable row
instead of a wrong answer.

### D2 — `PLATEAU_FRACTION = 0.92`

The cutoff is not a side question: it **is** the definition of `saturation_n`.

    saturation_n = first n whose tokens_per_s >= PLATEAU_FRACTION * max(tokens_per_s)

Before D1's split this constant was tuned to make the plateau match `--max-num-seqs`,
which was circular — tuning a measurement until it reproduces a number it does not
measure. After the split the two roles are separate. The **definition** claims only
that throughput reached 92% of its own peak. The **calibration** uses the nine vLLM
cells where the flag is known and binds as the only available ground truth for what
counts as flat.

Swept over every ramp on disk, scored against the configured width (vLLM only;
cfg 2 excluded, its speedup is exactly 1.00 and D1's gate declines it):

| cutoff | 32 tok | 128 tok | 512 tok | cells right |
|---|---|---|---|---|
| 0.90 | cfg 1 wrong | all | all | 8 / 9 |
| **0.92** | cfg 1 wrong | all | all | **8 / 9** |
| 0.93 | cfg 1 wrong | all | all | 8 / 9 |
| 0.94 | cfg 1, cfg 8 wrong | all | all | 7 / 9 |
| 0.95 (was) | cfg 1, cfg 8 wrong | cfg 1 wrong | all | 6 / 9 |
| 0.97 | 3 wrong | cfg 1 wrong | all | 5 / 9 |
| 0.99 | 3 wrong | 2 wrong | cfg 1 wrong | 3 / 9 |

At 512 tokens the cutoff barely matters — everything from 0.90 to 0.97 reads all
five widths. It is load-bearing only at shorter generations. The band that holds
across **all three** token counts is 0.90–0.93; above 0.93 the C6 false width
returns, cfg 8 at 32 tokens landing at 0.939 of peak and short by 1.1 tok/s.

**0.92 is the centre of that band.** The reason to prefer it over 0.95 is not
accuracy at the shipping setting — both are exact at 512 — but that 0.95's
correctness *depends on `RAMP_TOKENS` staying at 512*. That is the coupling C4
found and this campaign exists to break: a constant chosen by reasoning, never
varied, silently deciding whether another rule works.

**Two consequences built in.** `saturation_n` is meaningless without its parameters
and is reported with both the token count and the cutoff that produced it — two runs
at different values are not comparable numbers. `declared_slots` needs neither.

**The `0.10` latency tolerance** at `contract.py:433` is named alongside and
documented as informational: it feeds `latency_plateau_n`, which decides nothing.
It has no measurement behind it, and it is kept because throughput and latency
disagree by design on a genuinely wide server — that disagreement is how a reader
tells a real 16-slot curve from a broken measurement.

### D3 — `RAMP_TOKENS = 475`

**What the number is for, which the earlier framing had wrong.** `saturation_n`
(`knee` in code) is consumed at `run.py:235` as a drift tripwire: the survey config
declares `concurrency.expect`, the ramp measures, and a mismatch is recorded and
printed. It exists to catch a server restarted with a different `--max-num-seqs`
that nobody noticed — which is #286's own subject. It is not a capacity plan for
the bench's dispatch, so "which workload should it describe" is the wrong question.
The right one is **at which generation length is the drift check most sensitive.**

**Why the answer moves with token count.** Short generations are prefill-dominated
— the prompt is processed once and few tokens are emitted — and prefill batches
well, so throughput climbs past the slot count and saturation over-reads. Long
generations are decode-dominated, and decode is memory-bandwidth-bound, so the
curve flattens where the slots actually run out. That is the mechanism behind C4's
ollama readings of 12 / 4 / 2 at 32 / 128 / 512.

**Sensitivity, measured** — how much cutoff slack each column has before a vLLM
cell flips, at `PLATEAU_FRACTION = 0.92`:

| tokens | cutoffs that read every cell correctly | slack above 0.92 |
|---|---|---|
| 32 | none — cfg 1 is wrong at every cutoff | — |
| 128 | 0.90 – 0.94 | 0.02 |
| 512 | 0.90 – 0.97 | **0.05** |

**Cost, measured** (9 levels x 2 repeats, srv1, `Qwen2.5-Coder-1.5B-AWQ`):

| tokens | vLLM ramp | ollama ramp | percentile of 33,358 real completions |
|---|---|---|---|
| 32 | 1.7 min | 0.7 min | below p10 |
| 128 | 6.5 min | 2.2 min | p28 |
| 194 | ~9.8 min | ~3.3 min | p50 |
| **475** | **~24 min** | **~8.1 min** | **p90** |
| 512 | 26 min | 8.2 min | p92 |

**475 takes the sensitivity without the round number.** It sits within 7% of the
512 column, keeping almost all of its 0.05 slack, and it is a figure the served
workload justifies rather than one chosen by reasoning — which matters now that
every `saturation_n` reports the token count that produced it. It is an
interpolation inside a bracket whose endpoints agree at all five vLLM widths, not
an extrapolation.

**The counter-pressure is recorded and untested.** Longer generations are exactly
the decode-bound regime in which the *card* binds before the *flag* — the
D1-amendment failure mode where `saturation_n` under-reads `declared_slots`. It did
not appear on a 1.5B AWQ with headroom on srv1's card. A 7B, or srv2's 12 GB card,
is where it would appear first. Raising the token count buys sensitivity now and
carries that risk forward; the split fields make it visible when it happens rather
than silently wrong.

### D4 — `MIN_VRAM_FRACTION` is withdrawn as a gate and replaced by a declaration

**What it measures.** `backends/ollama.py:455`: `vram_fraction = size_vram / size`
from `/api/ps` — the fraction of *this model's own bytes* resident on the GPU. It
is ollama-only; vLLM has no equivalent check.

**Three facts the number does not carry, each of which changes its meaning.** The
owner supplied all three; none is in the 34 loads the constant was calibrated on,
which were every one of them dense, single-model and awake.

1. **MoE is in scope.** `size` is the full weight footprint, and a MoE serves fine
   with much of it on CPU because only a fraction of the parameters are active per
   token. **0.794 on a MoE is a working configuration; 0.794 on a dense model is
   20% of the layers on CPU and a large slowdown.** `gpt-oss:20b` — the refusal
   this finding was built around, 13.8 GB on a 12 GB card, six thousandths under
   the line — *is* a MoE. The headline case was never a failure.
2. **Two models may be resident at once** (1.5B + 3B). The fraction is per-model,
   but a neighbour holding VRAM pushes one of them partial. A reading of 0.6 then
   means either "another engine took the card" or "exactly the layout I
   configured", and the fraction cannot distinguish them.
3. **Sleep is in scope** — offload-to-RAM for fast reload. Placement becomes
   time-varying, so a sample taken in a sleep window reads a healthy model as a
   broken load, and a single sample stops being a property of the configuration.

**So no single number survives**, not 0.8 and not any other: the fraction's meaning
depends on the architecture, the intended co-residency and the sampling moment, and
it carries none of them. This is the same shape as `BATCHING_SPEEDUP` — a threshold
over a statistic that does not contain the thing being judged.

**Decided: the `concurrency.expect` pattern.** The survey declares `placement.expect`
per model; the run measures; a mismatch is recorded and reported. A declaration can
carry architecture and intended co-residency; a constant cannot. With nothing
declared the run records and never refuses, which makes all 17 models measurable.
Contamination stays caught where it always was, by `card_idle_before_load`.

To make the recorded number readable, capture alongside it: `resident_names`
(already captured), and the architecture and expert count, which `/api/show`
carries and nothing reads today.

**Owner caveat — a validation run is owed.** Once the decisions here are locked and
the harness is fixed, the servers are run again with these settings deliberately
exercised: MoE, two co-resident models, and sleep. The purpose is to see what the
endpoints actually return under each and to harden the mechanism against it. The
`placement.expect` design above is provisional until that run reports; it is the
shape the evidence supports, not a shape any measurement has yet exercised.

### D5 — elide by name, with a 4096-item backstop

`MAX_INLINE_ITEMS = 512` is a size-based guess at an intent about identity, and the
guess broke as models grew. Its own docstring states the intent — *"keeps every
structural list inline … and elides only the three tokenizer arrays"* — and that
sentence was true when the reference model had 338 tensors. Measured across the
corpus, `tensors` runs **255–843**, so 512 splits one field down the middle of the
model ladder: inline on the small models, elided on the large ones. A reader
comparing two captures sees differently-shaped files and cannot tell a real
difference from the rule flipping.

**Nothing is lost either way.** `observed.py:433` replaces an elided list with
`{elided, count, sha256}` on the same digest convention `run.json` uses, so drift
detection is untouched. Only legibility is at stake.

**Which lists are worth reading decides it.** A tensor row carries a name, a shape
and a dtype: when two captures differ, an inline `tensors` shows that
`blk.0.attn_q.weight` went from one quantization to another, which separates a
re-quantization from an architecture swap without re-running anything. A diff in
201,088 vocabulary entries is unreadable at any threshold.

**Decided: state the intent instead of approximating it.** The three tokenizer
arrays are elided by key. Everything else stays inline, `tensors` included, at
~60 KB per capture for the largest model. A **4096-item backstop** stays as a
safety valve for an array no measurement has seen — the named set expresses the
policy, the cap prevents a future model from committing 400,000 rows to git. The
rule cannot drift as models grow, because it no longer depends on how big anything
is. The cost is two mechanisms where there was one: a reader must know both to
predict a capture's shape.

### D6 — the four unmeasured constants are instrumented on the D4 validation run

| constant | value | what exists today | what is missing |
|---|---|---|---|
| `START_TIMEOUT_S` | 900 s | 15 clean vLLM launches in C6 | none was timed — the metric is not recorded |
| `DIGEST_TIMEOUT_S` | 1800 s | one point: 5.57 GB in 34 s (srv2, docker) | no distribution, no scaling against size |
| `LOAD_ATTEMPTS` | 2 | refusals cost 91–145 s, being two full clear-load cycles | whether a second attempt ever rescues a first |
| `RAMP_REPEATS` | 2 | — | the discarded repeat is never written down |
| `DIGEST_TIMEOUT_S` *(appended 2026-08-21, #326)* | 1800 s | every launch row now carries `digest_bytes` beside `digest_seconds`, and a timed-out digest is a recorded point with `digest_error` naming the constant | the distribution accrues from the next run; check: `tests/test_sink_conformance.py::test_the_digest_duration_arrives_with_the_bytes_it_hashed` |
| `LOAD_ATTEMPTS` *(appended 2026-08-21, #326)* | 2 | every attempt carries `ok` and `seconds`; the load row carries `attempts`, `attempt_outcomes`, `rescued_by_retry`; a refusal keeps its whole trail in both sinks | whether a second attempt ever rescues a first is now countable; check: `tests/test_serving.py::test_a_load_that_fails_once_and_succeeds_once_records_both_attempts` |

**`RAMP_REPEATS` is not like the other three — it is coupled to D2.**
`contract.py:325` runs each level twice and keeps the better:

    max((_level(base, model, n) for _ in range(RAMP_REPEATS)), key=tokens_per_s)

Max-of-2 is biased upward, and what it biases is the **peak** — the denominator of
`saturation_n = first n reaching PLATEAU_FRACTION x peak`. An inflated peak makes
the cutoff harder to reach, which biases `saturation_n` toward **over-reading**:
precisely the C6 failure mode this campaign found. The size of that bias is
unmeasured because the losing repeat is discarded and never recorded — and
recording it costs **no rig time at all**, since the work is already done twice.

**`LOAD_ATTEMPTS` has a directly testable question**: if a second attempt never
rescues a first, the constant doubles the cost of every refusal (91–145 s) for
nothing.

**Decided: instrument all four on the D4 validation run** and set them from that
data afterwards. The run records what is presently thrown away — vLLM start
durations, digest durations against model size, per-attempt load outcomes, and
*both* ramp repeats rather than only the winner — and the max-of-2 bias is then
quantified against `PLATEAU_FRACTION` rather than assumed away. No extra rig time
beyond the run already owed under D4.

### D7 — the comprehensive srv2 campaign, with no time or token limit

**Decided by the owner: the most comprehensive run**, the full 5-width srv2 matrix
plus the D4 additions, with no time or token budget imposed.

**Why srv2's ramp is not cleanup.** srv2's measured `kv_cache_max_concurrency` is
**5.314**. vLLM launched there with `--max-num-seqs 16` should read `saturation_n`
of about **5, not 16** — the card binding before the flag. That is exactly the
divergence the D1 amendment records as *untested, not excluded*, and srv1 could not
test it: a 1.5B AWQ had headroom at every width up to 16, so the flag always bound
first. srv2 is the only place the caveat is falsifiable.

Running declared 8 **and** declared 16 discriminates where one cell cannot:

- both read ~5 → the card binds; the D1 caveat is a measured phenomenon
- 8 reads 8 and 16 reads ~5 → the crossover is located between them
- both read their flag → the prediction is refuted and `kv_cache_max_concurrency`
  does not govern saturation

**Costs, scaled from measured srv1 times.** srv2 runs **1.30x** slower — consistent
across all three ollama token counts (0.8/0.6, 2.6/2.0, 9.7/7.4) and matching its
single-channel 13.3 GB/s against srv1's 21.8.

| item | estimate |
|---|---|
| srv2 vLLM ramp, one width at 475 tokens | ~31 min |
| srv2 full 5-width matrix | ~2.7 h |
| srv2 full survey via the docker launcher (12 models) | ~1–1.5 h |
| srv1 5-width matrix re-run at 475 tokens | ~2 h |

**The campaign, as one session:**

1. **srv2 full survey via the docker launcher** — all 12 models, load, digest,
   describe, with placement *recorded* per D4 rather than refused, so the five
   large models appear for the first time.
2. **srv2 vLLM 5-width matrix at 475 tokens** (1, 2, 4, 8, 16) — the cross-host
   replication of C6 and the `kv_cache_max_concurrency` prediction in one.
3. **MoE against dense** — a MoE and a dense model of comparable footprint, each
   captured for placement and ramped, so D4's claim that the same
   `vram_fraction` means different things is measured rather than argued.
4. **Intended co-residency** — 1.5B and 3B loaded together; placement captured for
   each, and a ramp run with the neighbour resident.
5. **Sleep state** — placement and the endpoint's answers captured during and after
   a sleep/offload window, to see what a sampled sleep actually looks like.
6. **srv1 at 475 tokens** — the new `RAMP_TOKENS` is an interpolation between two
   measured columns; this confirms it on the host whose matrix is already known.
7. **D6 instrumentation throughout** — start durations, digest durations against
   model size, per-attempt load outcomes, and **both** ramp repeats.

Rough total 8–9 h of rig time. The owner set no limit; completeness is the
constraint that binds, not the clock.

### D8 — explicit outcomes and a durable output, before the D7 campaign launches

The rewrite is forced by D1–D6 regardless: the fields split, two constants move, a
gate becomes a declaration, elision changes, and what is discarded starts being
recorded. D8 decides what else goes in while it is open.

**The three recorded defects share one root cause** — the row schema encodes
outcomes by *which fields happen to be missing*:

1. the same quantity is `configured_width` on a success row and `width` on a
   failure row, and a failed *launch* is distinguishable from a failed *ramp* only
   by the absence of `tokens`
2. ollama rows carry `configured_width: null` and no other field naming `-np`, so
   they cannot be scored without hand-joining to a separate document
3. a refused `vram_fraction` is recoverable only by regex over the prose in `why`

**Decided.** Every row carries an explicit `outcome` — `ok` / `launch_failed` /
`ramp_failed` / `refused` — and a structured `refusal` with a reason code beside the
prose, so nothing is inferred from absence and nothing is recoverable only from a
sentence. `declared_slots` is populated for both engines (`-np` and
`--max-num-seqs`) and is never null when it is known. Every derived number ships
with the parameters that produced it: `ramp_tokens`, `plateau_fraction`,
`ramp_repeats`.

**And the output is durable.** Rows append to a committed path as they complete.
The last two campaigns lost work twice — the end-to-end orchestrator survey was
written to a transient path and is gone, and 1.5 h of rig time was spent because a
patch silently never reached the file and the unchanged harness ran. An 8–9 h
campaign with no time limit is the wrong place to repeat either, and the process
rule already adopted on this lane applies to the launch: assert the marker in the
file after writing *and* after the formatter, and make verify-then-launch one step.

### Correction, 2026-08-19 — D7 is BOTH rigs, not srv2 alone

The D7 block above is headed "the comprehensive srv2 campaign". That is wrong and
the owner corrected it: **each rig gets the fullest run it can support.** srv1 runs
the full survey, the 5-width matrix at 475 tokens and the D6 instrumentation;
**srv2 runs all of that plus everything only srv2 can do** — MoE against dense,
intended co-residency, sleep state, the five previously-refused placements, and the
`kv_cache_max_concurrency = 5.314` prediction against a declared 16. srv2 is a
superset of srv1's campaign, not a different one.

### The D7 model roster, settled 2026-08-19

The corpus the calibration measured is **17 ollama models: 5 on srv1, 12 on srv2**
(the AWQ model is vLLM and ramp-only, and is not part of it). The D7 roster is
drawn from it by the owner:

**srv1 — 5**, the whole srv1 corpus: `qwen2.5-coder:1.5b`, `qwen2.5-coder:3b`,
`qwen2.5-coder:7b`, `nemotron-3-nano:4b`, `llama3.2:3b`.

**srv2 — 10**: the srv1 five plus `qwen2.5-coder:14b`, `deepseek-coder-v2:16b`,
`yi-coder:9b`, `gpt-oss:20b`, and `qwen3-coder:30b`.

Three points settled with it:

1. **`llama3.2:3b` is not on srv2.** The survey never saw it there. It is to be
   **downloaded, or copied from srv1**, and then verified exactly as every other
   model on the roster — no model enters the campaign unverified.
2. **`qwen3-coder:30b` is the intended tag** (Qwen3-Coder-30B-A3B), confirmed by the
   owner against the two near-miss tags srv2 also carries, `qwen3:30b-a3b` and
   `nemotron-3-nano:30b-a3b-iq2`.
3. **`yi-coder:9b` is added back** to the srv2 roster.

Out of scope, from srv2's twelve: `qwen3:30b-a3b`,
`nemotron-3-nano:30b-a3b-iq2`, `qwen3-coder-next-ud:q3_K_XL`.

**Two of the five `MIN_VRAM_FRACTION` refusals are in the roster** — `gpt-oss:20b`
and `qwen3-coder:30b` — so D4's withdrawal is exercised on models that the
instrument has never been able to measure.

**On D4's MoE-against-dense contrast**, the roster's architectures matter:
`gpt-oss:20b`, `qwen3-coder:30b` and `deepseek-coder-v2:16b` (DeepSeek-V2-Lite,
~16B total against ~2.4B active) are **all MoE**. The dense comparators of
comparable footprint are `qwen2.5-coder:14b` and `yi-coder:9b`. The sharpest single
pair is **`qwen2.5-coder:14b` (dense) against `gpt-oss:20b` (MoE)**: similar bytes,
very different active parameters — the cleanest available test of D4's claim that
the same `vram_fraction` means different things.

### Step 0 and step 1.1, added by the owner 2026-08-19

**Step 0 — recon and readiness, before anything touches the rigs for D7.**

*0.1 — a scouting crew with a verifier.* A great deal of running was done on srv1
and srv2 out of the `local-ai` repo, and none of it is in this tree. Scouts gather
the run configs and recorded gotchas (from `local-ai`, and separately from what our
own harness assumes about the rigs); a verifier then runs **read-only** commands on
both hosts to test which of those claims hold today. The output is one **gaps and
gotchas** list, which is read and resolved before the D7 run. `local-ai` is read for
context only — its host findings inform our run configuration and do not enter this
repo's record as this repo's content.

*0.2 — two readiness subagents, one per rig.*

- **0.2.1** Backend readiness as a **verifiable definition of done, not prose**:
  every line a command and an expected value, pass or fail. SSH, driver and free
  VRAM, disk for the digest path, vLLM present (binary or docker) with `CUDA_HOME`
  resolved, a smallest-model launch reaching health inside `START_TIMEOUT_S`,
  `/server_info` parsing at depth 0, whether a sleep endpoint exists, a clean
  shutdown returning the card to idle; ollama's version, `/props total_slots`, its
  `-np`, and `/api/tags`.
- **0.2.2** Every roster model **exists and responds on load** — present in
  `/api/tags`, loads, answers one trivial completion, placement recorded, unloaded.
  A missing model is provisioned (downloaded or copied between the machines) and
  then verified identically.
- **0.2.3** Both machines are left **idle with GPU and RAM free**, proven by a
  closing reading in the report.
- **0.2.4** Return a report with the gaps and gotchas.

**Step 1.1 — baseline check, then adversarial review, then fixes.** After the
harness rewrite the baseline gate must be green, an adversarial review runs against
the rewrite, and its findings are fixed **before** the launch step. The rewrite is
the largest single change this lane makes and it is what an 8–9 h campaign on two
rigs depends on.

### E1–E15, locked by the owner 2026-08-19

Fifteen decisions taken during steps 0 through 2 and reviewed by the owner one at
a time. **All fifteen are approved and locked**, on the same footing as D1–D8: a
change to any of them is a new decision with its own reason, not an edit.

Three were changed by the owner's review rather than merely confirmed, and those
are marked. The right-hand column names where each one lives — a decision that
exists only in prose is one nobody's code remembers.

| | Decision | Where it lives |
|---|---|---|
| **E1** | The leftover vLLM server stays up through step 0.1 and is torn down in 0.2 — it made every vLLM endpoint testable at depth 0 without paying a cold start | executed; srv1 idle at 1 MiB |
| **E2** | `qwen2.5-coder:7b` stays on the srv1 roster despite local-ai's `never_7b_on_srv1` rule. That rule is a serving-tier decision; a model that spills is the placement data point D4 asked for, and it is the only one srv1 offers | `configs/d7-campaign.json` |
| **E3** | The sleep step asserts a measured VRAM drop, never the endpoint's status | `calibrate.py` `sleep_state` |
| **E4** | The campaign driver runs detached with a log — ssh sessions on these rigs drop under load | `launch.py` |
| **E5** | `declared_slots` carries a **provenance**. ollama's is observed from the child's `/props`. **Revised by the owner:** vLLM's is *also* observed — from the server's own argv (`ps`) or the container's `Config.Cmd`, both verified on the rigs — with `dispatched` only as the fallback when the host read fails. Concluding "no observed source" from the HTTP surface alone stopped one step early. A disagreement between the two is reported as `contradicted` and refuses both numbers, because it means the server being measured is not the one this run launched | `backends/vllm.py` `launched_width`, `backends/ollama.py` `declared_slots` |
| **E6** | Config entries gain a `hosts` list, and an entry naming a host outside the run is refused rather than skipped | `run.py` |
| **E7** | srv2's HF cache is pre-warmed before the campaign, so no launch takes a cold download inside its start budget | executed; 1.6 GB present |
| **E8** | The docker filter is pinned to `CONTAINER_IMAGE`, not the bare repo name — it matched only because two tags shared an image id | `backends/vllm.py` |
| **E9** | The ollama kill runs under `sudo -n` and its effect is read back. ollama runs as another user, so the kill was getting EPERM silently while the log recorded a cleanup that could not have worked | `backends/ollama.py` |
| **E10** | `CUDA_HOME` is **dropped**, not repaired. `$HOME` never expanded — read off the live process — so it never took effect, and the record crediting it with fixing ten launches is false. **CUDA itself is untouched**: torch ships its own runtime, and the server it was set on was serving from the card at 4,916 MiB | `calibrate.py` |
| **E11** | Residency is cross-checked against the card. `/api/ps` keeps listing a killed model at full `size_vram` for the whole keep-alive window, so a residency list can report 100% resident on an empty card — including, without this, the co-residency claim D7 item 4 rests on | `backends/ollama.py` |
| **E12** | `--tokens` / `--widths` rather than editing `TOKEN_COUNTS`, which *is* the historical matrix and would make this record's own columns unreproducible | `calibrate.py` |
| **E13** | The ladder stops at 12 for the two deep-spill models. srv2 reports one slot for every model, so levels 16 and 24 are pure queueing far past the saturation point at 6–9 min each | `configs/d7-campaign.json` |
| **E14** | The two rigs are measured **one at a time**. Splitting by host would halve the wall-clock and the machines share nothing — but the ramp computes throughput from client-side wall-clock, and 12–21% aggregate degradation would land inside the curve rather than beside it. **A second driver is refused**, because a decision not to do something is not enforced by intending not to | `launch.py` `already_running` |
| **E15** | Phase order — sleep, then survey, then the width matrices — is declared in code. Sleep is twenty minutes that exercises the whole vLLM path the eleven hours behind it depend on. Phases chain with `;`: one that refuses must not cancel the two behind it | `launch.py` `CAMPAIGN` |

**Two guards refused a correct launch before they worked**, and both are recorded
because the failure mode is the same one: a check that fires on the wrong thing is
a check somebody switches off.

- The marker list's absence test was a plain substring match, and refused this tree
  because the docstring explaining what D1 *replaced* `BATCHING_SPEEDUP = 2.0` with
  contains the string. Absence is now matched against code lines only — otherwise
  the check would push every author toward deleting the explanation.
- E14's guard was `pgrep -af serving/(run|calibrate).py` and matched the shell that
  was editing the file, because the script's name was inside its argv. It now
  matches the process *shape*: a python whose arguments include the script.

**Revised campaign estimate: ~11–12 h, not D7's 8–9 h.** The review measured the
config at 17 host×entry cells each with a full ramp; at measured solo rates the
ollama ramps alone compute to ~5.5 h, on top of ~4.7 h of width matrices and
~1–1.5 h of survey overhead. The owner set completeness rather than the clock as
the binding constraint and accepted the revised figure.

## Addendum, 2026-08-20 — the campaign ran, and the four owed blocks are closed

Appended, not edited: the four **Decision owed** blocks above (lines 48, 115, 150
and 363 as this file stood on 2026-08-19) are history and stay as written. This
section names what closed each one, and what the run that followed says about it.

### The campaign

Launched 2026-08-19 19:31, finished 2026-08-20 04:43 — **9 h 12 m against an
11.5 h estimate**, three phases, **33 cells, zero failures**. Both rigs left idle
at 1 MiB. Clean exit: no `.campaign-stop` remained, so the trailing `cleanup` ran
rather than the interrupt path.

| phase | cells | wall clock |
|---|---|---|
| 1 — sleep | 4/4 | 1141 s (19 m) |
| 2 — survey | 17/17, zero refusals | 4 h 53 m |
| 3 — ramp | 12/12, zero errors | 14404 s (4 h 00 m) |

Evidence beside this file: `d7-sleep.jsonl`, `d7-survey.json` +
`d7-survey.json.jsonl`, `d7-ramp.jsonl`, `samples.jsonl`.

### The four blocks, and what closed each

| block | question it left open | closed by | what the run adds |
|---|---|---|---|
| **line 48** — C1, `MAX_INLINE_ITEMS = 512` split `tensors` down the middle of the model ladder | elide `tensors` everywhere, or keep it everywhere? | **D5** — elide *by name*, with a 4096-item backstop | **Nothing.** D5 governs `observed.py`'s capture shape; this campaign is a serving survey and writes no `observed.json`. Landed in code at `tools/bench/observed.py:363` (`ELIDE_BY_NAME`) and `:376` (`MAX_INLINE_ITEMS = 4096`), proven by test, not by this run. |
| **line 115** — C3, `MIN_VRAM_FRACTION = 0.8` made five srv2 models unmeasurable | record placement, or keep refusing on it? | **D4** — the gate is withdrawn; `placement` is declared and recorded, never refused | **All 17 models measured, none refused.** See below. |
| **line 150** — C4, `RAMP_TOKENS` decides whether the rule is right at all | fix the token count, or move the gate with it? | **D3** (`RAMP_TOKENS = 475`) and **D1** (`BATCHING_SPEEDUP` → 1.0, renamed, confined to the inferred path) | All 12 ramp cells ran at `ramp_tokens: 475`, **zero levels dropped**. |
| **line 363** — the vLLM matrix's three owed items | withdraw `BATCHING_SPEEDUP`; name the plateau cutoff; set `RAMP_TOKENS` | **D1**, **D2** (`PLATEAU_FRACTION = 0.92`), **D3** | All 12 cells carry `plateau_fraction: 0.92`; `saturation_n` tracked the configured width exactly on every cell that was not refused. |

### D4 on live data — placement recorded, never gated

The three entries that spilled are the three the step-0.2 arithmetic predicted, to
four decimals:

| entry | predicted 2026-08-19 | measured 2026-08-20 |
|---|---|---|
| srv1 / `qwen2.5-coder:7b` | 0.908 | **0.9080** |
| srv2 / `gpt-oss:20b` | 0.7945 | **0.7945** |
| srv2 / `qwen3-coder:30b` | 0.5806 | **0.5806** |

The other 14 cells read exactly **1.0**. `gpt-oss:20b` — the MoE the withdrawn 0.8
gate refused, and the case D4 was argued around — measured without incident.

**A number the next pricing session should have:** every entry that *did* declare a
floor read exactly 1.0, against floors of 0.85 and 0.9. Not one came within ten
points of firing. `min_vram_fraction` is today a field that has never gated
anything on any entry. Whether it should fire somewhere, or is ceremony, is a
separate question and is not decided here.

#### Correction — `placement_meets_expectation` is null on six rows, not three

The session record of 2026-08-19/20 and the commit message of `7d5ec4d8` both say
the field "came back null on exactly those three entries and true on every other."
Read off `d7-survey.json`, it is null on **six of seventeen**:

| row | `vram_fraction` | `placement_meets_expectation` |
|---|---|---|
| srv1 / `qwen2.5-coder-7b` | 0.9080 | null |
| srv1 / `coresident-3b-beside-1.5b` | 1.0 | null |
| srv2 / `qwen2.5-coder-7b` | **1.0** | null |
| srv2 / `gpt-oss-20b` | 0.7945 | null |
| srv2 / `qwen3-coder-30b` | 0.5806 | null |
| srv2 / `coresident-3b-beside-1.5b` | 1.0 | null |

The rule is not "null where it spilled" but **"null where the entry declares no
floor"** — which after DE-G is the 7B on *both* hosts and both co-residency cells,
regardless of what they measured. srv2's 7B is the row that separates the two
readings: it did not spill (1.0) and is still null. The other eleven rows are
`true`, and all eleven read exactly 1.0.

This does not change DE-G — it strengthens the reason for it. The field tracks the
*declaration*, which is exactly what D4 said it should do.

### D1/D2/D3 on live data — the width matrices

All twelve cells at `ramp_tokens: 475`, `plateau_fraction: 0.92`, zero levels
dropped, and all ten vLLM rows carrying `declared_slots.provenance: "observed"`
read from the server's own `--max-num-seqs` with `dispatched` matching `value`
every time (E5-revised).

| configured width | srv1 speedup | srv1 `sat_n` | srv2 speedup | srv2 `sat_n` |
|---|---|---|---|---|
| 1 | 1.00 | *refused* | 1.02 | 1 |
| 2 | 1.00 | *refused* | 1.97 | 2 |
| 4 | 1.23 | 4 | 3.94 | 4 |
| 8 | 2.41 | 8 | 7.84 | 8 |
| 16 | **3.76** | 16 | **15.42** | 16 |

Both rigs saturate at exactly their configured width — `--max-num-seqs` binds on
both, never the card. The **efficiency** differs: srv2 returns 96% of linear at
width 16 (15.42/16), srv1 returns 23% (3.76/16). Both ran `--enforce-eager`
(mandatory on srv1's compute capability 7.5, kept on srv2 deliberately), so the gap
is hardware, not configuration. ollama arms: srv1 1.45x at `sat_n` 2, srv2 1.10x at
`sat_n` 2.

srv1 also shows throughput and latency parting company at the top: at width 16 its
`saturation_n` is 16 but `latency_plateau_n` is **8**. srv2's two agree at 16.

**The boundary case worth keeping.** srv1 width 1 read exactly **1.00** and DE-1
refused it; srv2 width 1 read **1.02** and was recorded.
`INFERRED_SATURATION_MIN_SPEEDUP` uses `<=`, so **0.02 separates** "excluded as a
curve that never rises" from "a valid measurement". Both are correct under the rule
as written; its sensitivity at its own boundary is now demonstrated rather than
theoretical.

### D6's four constants are still unmeasured

`START_TIMEOUT_S`, `DIGEST_TIMEOUT_S`, `LOAD_ATTEMPTS` and `RAMP_REPEATS` were to be
instrumented on this run and were not. They are seed content for #322's first run
headers, and remain owed.

### A confound this sweep exposed

**Quantization is not controlled across the roster:** Q4_K_M on 9 of 11 srv2 cells,
Q4_0 on `yi-coder-9b` and `deepseek-coder-v2-16b`, MXFP4 on `gpt-oss-20b`. Context
is uniform at 4096 and every digest matched its pin. That is fine for placement,
which is what the survey is for — and **a real confound for any throughput rate read
across models.**

## Addendum, 2026-08-21 — the journals carry no clock, and two figures above were derived on record from nothing (#325)

Appended, not edited. Two figures in the 2026-08-20 addendum above are correct
and could not be checked from the files beside this README, because no row in
`d7-ramp.jsonl`, `d7-sleep.jsonl` or `d7-survey.json.jsonl` carries an instant:
every duration the harness wrote was a `time.monotonic()` delta.

**8,185.3 s of the ramp phase belongs to no row.** Method: the phase's
`ramp finished in 14404s` (`d7-campaign.log:89`) minus the sum of the twelve
ramp rows' 108 `levels[].wall_s`, which is 6,218.7 s. The 56.8% remainder is
losing repeats (`contract.ramp` keeps the better of two), ten vLLM launches,
two weights digests, the releases between cells and the slot reads — in a
split no file holds. **4 h 53 m for the survey** (table above) agrees with
the residual of the clock readings at the top of that addendum
(33,120 − 1,141 − 14,404 = 17,575 s) and with the `d7-sleep.jsonl` →
`d7-survey.json` mtime gap (19:50 → 00:42); session 5's record does not say
which it was derived from, and no journal holds either.

**What #325 changed, so the next run does not repeat this.** Every row now
carries `started_at`/`ended_at` (UTC ISO-8601, one seam: `contract.now`), the
launch row's span is the claim's, every `ollama.claim` attempt and the
`vllm.claim` checks are spanned, and each phase writes one
`{"metric": "phase", "started_at", "ended_at", "seconds"}` row — a `--resume`d
journal holds one per invocation, and `completed()` never counts it as a cell.
Every row is also stamped with `commit`, `tree_dirty`, `harness_sha256`
(`product.digest`'s shape over `tools/bench/serving/`), `config_sha256` (the
bytes the survey read — a `_`-key hand-edit moves it), `argv` and
`run_started_at`; the survey document carries the same under `result["run"]`.

**Its check.** `tests/test_sink_conformance.py::test_the_ramp_phase_remainder_is_a_sum_of_named_terms`
drives `calibrate.ramp` with a fake clock that advances only inside the stubbed
seams and asserts that `phase span − Σ(launch + ramp row spans)` equals exactly
the clock spent inside `release`, `ollama.slots_now`, `vllm.declared_slots` and
the ramp phase's `ollama.claim` — the seams that write no row. One of those is
a finding of its own: the ramp phase's ollama load writes no row at all (the
load phase's does), so its minutes are attributable only as a remainder; #326
and #327 own whether that becomes a row. The 8,185.3 s above stays as
derived, from the log; the next campaign's equivalent will be a sum of rows.

## Addendum, 2026-08-21 — the width-16 gap was attributed to hardware by rows that could not see the card (#327)

Appended, not edited. The D1/D2/D3 matrix above reads srv2 at 96% of linear
and srv1 at 23% at width 16 and says "the gap is hardware, not configuration".
The rows it rests on carry ten keys per level and none of them is the state of
the card or of either machine: every `nvidia-smi` the harness ran asked for
`memory.used`, the load average was read once per host by the survey and
discarded by the `fast` step, and the order was fixed ascending on both axes —
width 16 at n=24 was the last cell of every host's block, with the most load
behind it. A card throttling by its fifth width and a slower card read the
same on those rows. The attribution stands as written; what it rests on is
now stated.

**What #327 changed, so the next run can separate the two.** Every recorded
level row carries `card` (`temperature_c`, `power_w`, `sm_clock_mhz`, the
driver's `throttle_reasons` mask) read at the level's end, and `ambient`
(`host_loadavg` from the rig's `/proc/loadavg`, `client_loadavg` from the
driver whose clock `wall_s` comes from — E14 in `launch.py` puts client-side
contention at 12–21%, the 2026-08-18 record at 1%, and no row carried either
load). Both travel in one ssh per recorded level (18 per ramp at the default
matrix, each one `ssh_step_seconds`: p50 0.956 s above); the discarded warm-up
reads nothing; a read the host did not answer is `null` with the command
beside it. `contract.ramp` sorts by `n` before any reader — offered descending,
the same curve used to read `saturation_n` 24 instead of 4 — and the ramp row
carries `levels_run`, `level_order` and `level_seed` so the order becomes a
condition on the record rather than a term in the reading. The vLLM launch
row carries the card at the claim, beside `gpu_used_mib`.

**Its checks.** `tests/test_sink_conformance.py::test_every_level_row_carries_the_card_state_it_ran_under`,
`::test_every_level_row_carries_the_load_of_both_machines`,
`::test_one_ssh_per_recorded_level_carries_card_and_load_together`,
`::test_the_level_sink_declares_a_disposition_for_every_field_a_level_produces`
(the level rows are values inside a sink, so the #324 census never reaches
them; `LEVEL_ROW_DISPOSITION` in `calibrate.py` is their only guard) and
`tests/test_serving.py::test_the_curve_reads_the_same_in_any_order_it_was_run`.
No rig time: the first values are the re-run's to write and to read.

## Conflicts recorded 2026-08-21 — six, re-derived at `d4d6b8c1` (#328)

Appended, not edited. Session 6 counted six contradictions in this campaign's
record (`records/sessions/lane/286/2026-08-20-131600-claude.md:151`) and left
every one of them in prose. All six were re-derived from the files beside this
README at `d4d6b8c1`: **four survive and two dissolve.** They are labelled
**K1–K6** because C1–C6 above are this README's own findings and are not these.

**Nothing read any of them until now.** `grep -rl xfail tests` found nothing,
and the only guards over these journals were the disposition tables beside the
sinks (#324), which account for the *fields* of a row and say nothing about the
*values* inside one — which is why the session record says of K3 that it "would
not be caught today".

Each K is now a check in `tests/test_calibration_conflicts.py`, under ADR-0037:
a finding is a test with an expected state; a finding the owner has not ruled on
keeps its check as a dated `xfail(strict=True)`; the record names the check.
Four are `owed` and carry the question the investigation must answer. Two are
green, and their job is to keep a re-derived non-finding from being re-filed.

**The checks read the newest campaign, not this one.** Every one resolves its
evidence to the newest `records/evidence/calibration-*` directory. The files
beside this README are frozen history and can never turn green, so a check
pinned to them would be an `xfail` that outlives its own finding and can never
XPASS. Pointed at the newest campaign, each `owed` reason is a question put to
the **next** run, and the run that answers it flips the marker.

**Two checks read wider than #328 filed them,** and are noted below: K5 covers
both engines rather than ollama alone (227 pairs, not 27), and K6 covers every
figure-bearing ramp row in this directory's journals (36) rather than the twelve
of `d7-ramp.jsonl`. Both verdicts are unchanged by the widening.

**Shown to reject.** 25 mutations were applied to a copy of this evidence and
the six checks run against it. Each of the four survivors turns green when its
defect is repaired in the copy — which is what `strict` is for — and stays red
under a partial repair: one sampler field left disagreeing, `n_ctx_total`
present but carrying the per-slot window, `holder` present and `null`, a version
on one host's rows only. Each green check goes red under four independent
breakages, and refuses a population it would pass vacuously. Two mutations prove
the campaign resolution in both directions: a newer campaign with the four
defects repaired turns all six green while these files stay as they are, and
repairing *these* files while a defective newer campaign sits beside them
changes nothing. 25 of 25.

### K1 — the sampler pin is not the layer any request ran under

`d7-survey.json`, `hosts[].measured[].description.serving_config.semantic`
against `…server.instances[].slots[].params`. `serving_config` digests
`/props`'s `default_generation_settings`, which is llama-server's own default
set, while every request this project dispatches goes through ollama's
per-request parameters (where a `Modelfile`'s `parameters` enter). The two
layers disagree on **17 of 17 served slots**: `top_p`, `min_p` and
`repeat_penalty` on all 17, `temperature` on 4, `top_k` on 1 — under a digest
quoted as the pin that makes the cells comparable.

- check: `tests/test_calibration_conflicts.py::test_the_sampler_pin_is_the_layer_the_request_ran_under` — red, 17/17
- decision: owed — which layer is `serving_semantic_sha256` a pin of: llama-server's defaults, or the params a request ran under?

### K2 — the launched context total is recoverable by arithmetic and unnamed

`d7-survey.json`, `…server.instances[].command_line` against the same semantic
block. `-c` is the total window and `-np` splits it into slots; `serving_config`
parses both and then overwrites `n_ctx` with the per-slot window off `/props`,
so the total survives only as a product. It holds on **19 of 19** children, and
**6 of 19** were launched at 8192 rather than 4096 — `OLLAMA_NUM_PARALLEL=2` in
srv1's unit (`d7-survey.json:342`), nothing in srv2's (`:21963`). That is a
host-configuration difference sitting under a figure this README reads as
hardware, and the text above still calls context "uniform at 4096".

- check: `tests/test_calibration_conflicts.py::test_the_launched_context_total_has_a_name_in_the_semantic_block` — red, 19/19 carry no `n_ctx_total`
- decision: owed — is the width split inherited or intended, and does a cross-host figure refuse it, carry it, or equalise the hosts first? (feeds #329)

### K3 — a yield finds the card held, and does not say by whom

`d7-survey.json`, `hosts[].measured[].yielded.vllm`. `release()` stops this
engine's own processes and then reads the whole card, deliberately keeping "I
released mine" apart from "the card is empty". The vLLM yield runs before ollama
evicts its previous model, so **15 of 17** cells recorded `card_idle: false`
against a residue matching the previous cell's post-load reading to within 14
MiB, and `card_used_mib_before_load` is 1 on 17 of 17. The reading is correct
and unattributable: nothing in the row says whose memory it is, though the same
`release()` call could name it from `/api/ps` or
`nvidia-smi --query-compute-apps`. Moving the read to after eviction is
instrument placement and is not this record's.

- check: `tests/test_calibration_conflicts.py::test_a_yield_row_that_finds_the_card_held_names_the_holder` — red, 15/15
- decision: owed — does the yield row name what holds the card?

### K4 — `endpoint_props: false` is the write flag. Dissolves

`d7-survey.json`, `…instances[].props`. Filed as a payload fetched *from*
`/props` that says the props endpoint is off, on 19 of 19 instances. It is
llama.cpp's **write** flag: its server README (`tools/server/README.md`, fetched
2026-08-21) documents `--props` as "enable changing global properties via POST
/props (default: disabled)" and says of `GET /props` that "By default, it is
read-only". The harness only ever issues that GET, and a search of
`tools/bench/serving` for a POST or a `curl -d` to `/props` on 2026-08-21 found
none — so the flag describes writes nobody makes, and `fingerprint` classing it
operational is correct. The check holds the property that dissolves it: wherever
the flag is false, the payload beside it is nonetheless complete.

- check: `tests/test_calibration_conflicts.py::test_a_false_endpoint_props_beside_a_captured_props_payload_is_the_write_flag` — green, 19/19
- decision: dissolved 2026-08-21 — not a contradiction; the check keeps it from being re-filed and goes red if a capture ever does come back empty.

### K5 — 2.52× and 1.45× are the same server at different token counts. Dissolves

`samples.jsonl` and `d7-ramp.jsonl`, `phase: ramp`. Filed as a knee of 12 at
2.52× against a `saturation_n` of 2 at 1.45× for srv1/ollama/1.5B. They were
measured at 32 and at 475 completion tokens; the same file reads 1.48 and 1.45
at 512, D3 retired the 32-token ramp, and the section above already explains why
a 32-token ramp reads a knee on a one-slot server. The check is the general form
of that lesson rather than the instance, and it is **read wider than filed**:
over both engines, because the vLLM matrix quotes 1.0 against 3.76 for one model
at one token count and what separates them is `configured_width`. Every pair of
figures for one host, engine and model that disagrees by more than 10% differs
in a declared condition — 227 pairs, 187 of them disagreeing, 0 unattributable.

- check: `tests/test_calibration_conflicts.py::test_two_ramp_rows_that_disagree_differ_in_a_declared_condition` — green, 187 disagreeing pairs all attributable
- decision: dissolved 2026-08-21 — the 32-token rows are superseded, not contradictory; a figure that cannot be told from its neighbour is what the check now refuses.

### K6 — the two hosts ran different ollama builds and no figure says so

`d7-survey.json:346` and `:21967` against every ramp row in `samples.jsonl` and
`d7-ramp.jsonl`. srv1 ran ollama 0.32.4 and srv2 ran 0.32.5. The survey read
both, the split was known before launch
(`records/sessions/lane/286/2026-08-18-220000-claude.md:13`), and this README
quotes the two ollama arms side by side — while **0 of 36** figure-bearing ramp
rows carry a version. The version is recoverable only by joining a figure to the
survey document that happens to sit beside it, and not at all once the figure is
quoted elsewhere.

- check: `tests/test_calibration_conflicts.py::test_a_cross_host_figure_carries_the_engine_version_on_each_host` — red, 36/36
- decision: owed — what moved between 0.32.4 and 0.32.5 in scheduling or placement, and does a cross-host row carry the version or refuse the split? (feeds #329)

**No rig time.** Nothing here opened an ssh connection or ran `launch.py`; the
checks read the committed files, and the mutation sweep ran over copies of them.
Implementing any fix the owner selects is its own commit, referenced from the
K-line it closes, and removes one `xfail`.

## Addendum, 2026-08-21 — the cross-rig claim is now a predicate that refuses (#329)

Appended, not edited; the sentence it is about is left exactly as written at
`:983-987`. "The gap is hardware, not configuration" was read off
`d7-ramp.jsonl`, and **that file names neither.** Twelve rows of seventeen keys:
no card, no driver, no launcher, no engine build, no weights digest, no engine
config, and not one launch row. `grep -c -E "1660|3060|driver_version|launcher|v0\.26\.0|enforce-eager|engine_version|weights_sha256" d7-ramp.jsonl` prints `0`.
The two cards do differ — a GTX 1660 SUPER (6144 MiB, driver 580.173.02) and an
RTX 3060 (12288 MiB, 595.84), both read by the survey — and so do the two
deployments: srv1 runs a pip `vllm serve` on torch 2.11.0+cu130, srv2 runs the
`vllm/vllm-openai:v0.26.0` container (`step0-gaps.md:21`). Hardware may be the
answer. Nothing in the journal the sentence rests on can tell it from the
container image, and under ADR-0026 lens 3 that makes the claim worse than dead
weight rather than wrong.

**What #329 changed.** The cross-rig claim is now `cross_host_contrast(journal,
model, width)`, a pure reader that returns the two hosts' speedups *only* when both
launch rows carry the same `weights_sha256` and the same `identity.serving_build`
and each names its card, and otherwise returns the field that refused it. Run
against this directory's journal it returns `{"refused": "no launch row"}`.
Two things it deliberately does not require: equal cards, because the cards
differing is the hypothesis under test, and any decision about what the gap is.

**Its checks.**
`tests/test_cross_rig_claim.py::test_the_two_launchers_hand_the_engine_the_same_arguments`
builds both launch command lines through `vllm._start` with the launcher forced
and ssh stubbed, and holds them to the same engine arguments and the same
environment once `PATH` is set aside — the flags on the two hosts really are
identical, and that was an assumption about two strings nobody had compared
until now.
`::test_a_cross_host_contrast_refuses_when_identity_differs_or_is_missing` holds
the refusals, and the accepting case beside them.
`::test_the_2026_08_20_cross_rig_claim_holds_only_on_a_journal_with_identity_rows`
reads the claim off this directory's journal and is
`xfail(strict=True, reason="2026-08-21: owed — …")`: it is red because the
journal carries no identity, not because 3.76 and 15.42 are in doubt. The rig
arm of #329 writes one width-16 ramp and one launch row per host — about 19
minutes, the only rig time any #286 child asks for — points the module's
`CROSS_RIG_JOURNAL` at it, and takes the marker off in the same commit. A strict
xfail that passes fails the suite, so the flip is a predicate rather than a
promise.

**No rig time was spent here**, and none of the three arms above can spend any.

**The rig arm ran on 2026-08-23, and the marker is off.**
`records/evidence/2026-08-23-cross-rig/` holds one width-16 vLLM ramp and one
launch row per host, **both launched through the `v0.26.0` container** — srv1
included, which had only ever been launched from its pip install. The contrast
is returned rather than refused: the two launch rows carry the same weights
digest (`047d5b14…`), the same `serving_build` (`vllm 0.26.0`) and each names
its card.

| | 2026-08-19, launcher detected | 2026-08-23, launcher declared docker |
|---|---|---|
| srv1 speedup at width 16 | 3.76 (pip) | **3.82** (container) |
| srv2 speedup at width 16 | 15.42 (container) | **15.41** (container) |
| srv1 `saturation_n` / `latency_plateau_n` | 16 / 8 | 16 / 8 |
| srv2 `saturation_n` / `latency_plateau_n` | 16 / 16 | 16 / 16 |

**The launcher is out of the contrast, and it was not the answer.** srv1 moved
by 0.06 on a gap of about 11.6, and every level of its curve reproduced within
noise (10.708 → 10.908 s at n=1, 45.466 → 45.593 s at n=16). The sentence at
`:983-987` survives the one alternative explanation that could be removed
without buying hardware.

**What is still not separated, and the record should not be read as if it were.**
The two rigs differ in card *and* driver together — a GTX 1660 SUPER on
580.173.02 against an RTX 3060 on 595.84 — and the container does not pin the
driver: inside srv2's container `nvidia-smi` reports the host's 595.84. So
"hardware" is now a claim the record can support as *not configuration*, and it
remains one no run in this tree can decompose further.

## Correction appended 2026-08-24 — "Partial batches cost a full batch-time" is srv1-only

The section at `:332-345` concludes from the dips that they are "scheduler
behaviour rather than noise". **The observation is real; the attribution is
not.** Every row of the matrix it is derived from (`samples.jsonl`, 15 rows) is
**srv1**. srv2's own five-width matrix in `d7-ramp.jsonl` reads 1.95-1.97x at
n=2 with no dip at any width, and the 2026-08-24 sweep confirms srv2's decode
step is flat from batch 1 to batch 16 (27.6 to 28.7 ms, +3.7%).

So "n=2 is slower than n=1 at every single width" is a property of **srv1**, not
of vLLM's scheduler. Its cause is named in the block below: the unquantized
lm_head GEMM, which costs 1.77 ms at batch 1 and 50.8 ms at every batch from 2
to 32 on srv1 and is flat on srv2. A fixed per-step cost that appears only when
the batch is not 1 produces exactly the dips this section describes, on one card
and not the other.

The n=12-against-width-8 and n=6-against-width-4 observations are a second,
smaller step of the same kind, and are also srv1-only.

## Correction appended 2026-08-24 — the contrast compared two misconfigured servers

The sentence at `:983-987` and the addendum above both survive as far as they
go: the deployment is not the explanation, and the launcher was worth 0.06 of a
gap of 11.6. **What neither of them can survive is that both servers were
configured to a fraction of what they can do.**

A 106-cell configuration sweep over 20 axes on both rigs
(`records/evidence/2026-08-24-config-sweep/`) reads:

| | srv1 | srv2 |
|---|---|---|
| this campaign's configuration | 164.3 tok/s | 518.2 tok/s |
| best configuration measured | **293.6** | **6,445.1** |
| | 1.79x | **12.4x** |

**The gap is 22x, not 3.2x**, and the campaign's own numbers were a reading of
two misconfigurations rather than of two machines.

**`--enforce-eager` is the largest term and it was never required.** This
directory's justification for it — "mandatory on srv1's compute capability 7.5",
repeated at `calibrate.py:597` and `step0-gaps.md:197` — is an assertion no run
in this tree ever tested. vLLM's `docs/features/README.md:66` lists CUDA graph
as supported on Turing and no capability gate on graph capture exists in the
0.26.0 source. Measured: the flag is worth **0.1% on srv1**, the card the claim
was about, and **5.02x on srv2**, where nobody claimed it was needed — including
at a single stream (181.7 tok/s at n=1 against 36.2), so it is not a batching
effect. The belief was attached to the wrong rig and taxed the other one for the
life of the campaign.

**What still stands, and is now better supported.** srv1 responds to exactly one
axis of twenty; twenty-five cells across compile, graphs, performance mode,
scheduler, dtype, KV dtype, kernels and scheduling all land inside a 2.8% band,
and only concurrency moves it — to 293, where four context lengths agree to four
significant figures. srv1 is also *refused* `bfloat16` and all three fp8 KV
dtypes by compute capability, and fp8 KV is what produced srv2's best cell. So
srv1 is genuinely the weaker rig. **The size of the difference this campaign
reported, however, is a property of how both were run.**

**The mechanism behind srv1's N=2 cliff, which this campaign left open.**
`Qwen2.5-Coder` ties its word embeddings, so lm_head is unquantized fp16 and
runs through cuBLAS every decode step. A microbenchmark of that one GEMM on both
cards (`2026-08-24-config-sweep/README.md`, and the lm_head figures in the
2026-08-23 lane record) steps 28.7x between M=1 and M=2 on srv1 and is flat on
srv2 — an excess of 49.06 ms against the 49.79 ms the live run shows. The card's
TU116 die carries no tensor cores. That is hardware; which model, and therefore
whether its lm_head is tied, is configuration.

**Two figures the arm produced on the way.** srv1's first container launch:
**83.5 s**, against the 33 s its pip launch measured — a 2.5x start-time cost
for the same engine on the same card, and the first `START_TIMEOUT_S` point
srv1 has ever contributed on the container arm (srv2's was 93.1 s here, 109 s
in D7). And the weights digest ran inside the image on both hosts for the first
time: 7.5 s on srv1, 10.4 s on srv2.

## Conflicts recorded 2026-08-22 — three, from a live verification

Appended, append-only, beside `## Conflicts recorded 2026-08-21`. That block's
K1–K6 are unchanged and its count of six is a count of itself; the file now
names nine checks across two dated blocks.

On 2026-08-22 the two rigs were read live and `OLLAMA_NUM_PARALLEL` was
declared as `1` on both (srv1 had `2` in a drop-in; srv2 had it unset and the
engine had chosen `1`). With that pinned, srv1 (ollama **0.32.4**) and srv2
(ollama **0.32.5**) launched `qwen2.5-coder:1.5b` at an identical `-c 4096
-np 1` and reported a byte-identical `size_vram` of `1166236712`. The engines
agree at that point. K7–K9 are the three ways that agreement could still be
wrong, each as a check rather than a caveat.

**K7 — the same model, two hosts, two windows.**
`tests/test_calibration_conflicts.py::test_a_model_served_on_both_hosts_was_launched_with_the_same_geometry`
Evidence: `d7-survey.json`. Of the 6 models served on both hosts on
2026-08-19, **5 ran at `8192x2` on srv1 and `4096x1` on srv2** — the geometry
K2 names as a total the semantic block never carries, here as a condition two
hosts' numbers were compared under as if it were absent.
- decision: owed — is a cross-host figure allowed to rest on children the two
  hosts launched differently?

**K8 — an equal footprint is not an equal throughput.**
`tests/test_calibration_conflicts.py::test_a_cross_host_agreement_rests_on_more_than_one_model_per_engine`
Evidence: all `*.jsonl`. Of 36 figure-bearing ramp rows, **exactly one model
per engine carries a figure on both hosts** — `qwen2.5-coder:1.5b` for ollama
and `Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ` for vLLM, which is the model the
`23% vs 96%` claim quotes. One shared model cannot separate "the engines
agree" from "these two runs agreed"; `MIN_CROSS_HOST_MODELS = 2` is the
smallest population in which the first can fail.
- decision: owed — how many models must agree across hosts before an engine is
  called equivalent?

**K9 — residency declared on one host, inherited on the other.**
`tests/test_calibration_conflicts.py::test_both_hosts_declare_the_settings_that_decide_residency`
Evidence: `d7-survey.json`, `hosts.<host>.present.ollama.readings.service_environment`.
srv1 declared all three of `OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`,
`OLLAMA_KEEP_ALIVE`; **srv2 declared none**. The last two decide whether a
model stays on the card and whether a second may join it — what the
co-residency cells measure. An inherited value is picked by an engine, the two
hosts do not run the same engine version (K6), and the picked value appears
nowhere in the evidence.
- decision: owed — must every host declare the settings that decide residency,
  or may one inherit the engine's default?

Each check reads the **newest** `calibration-*` directory, so all three are
questions put to the re-run rather than verdicts on frozen files. Each was
shown to reject: K7 and K9 turn green on a repaired copy of the evidence, K8
turns green once a second model per engine carries a figure on both hosts.

## Conflict recorded 2026-08-22 (second) — a constant this project did not choose

**K10 — `gpu_memory_utilization = 0.85`.**
`tests/test_calibration_conflicts.py::test_a_serving_constant_this_project_did_not_choose_names_its_source`

Traced 2026-08-22 after the value was noticed to carry no comment at any of its
five sites (`configs/srv-full.json:34`, `:60`; `calibrate.py:596`, `:833`;
`backends/vllm.py:599`) while the line beside one of them carries a full
justification for `--enforce-eager`.

**It was copied, not decided.** The value was read off a *running* srv1 on
2026-08-18 — `tests/test_bench_observed.py:172` is a fixture captured from a
server this repo did not start — roughly seven hours before it entered any
config here, and it existed in the local-ai repo by 2026-08-10. The three
commits that wrote it (`d07d45c5`, `ccae4424`, `e8ea2648`) never mention it;
the first has a ~1,500-word message about everything else.
`backends/vllm.py:10` records it as an observation: "allocates a fraction of
VRAM at startup — 0.85 or 0.90 on these rigs — and holds it".

**The reason exists, in the other repo.** local-ai `AGENTS.md:126-127`:
"reduced from doc values to avoid CUDA OOM", the original values being
`--max-model-len 16384 --gpu-memory-utilization 0.90 --max-num-seqs 16`, which
"caused CUDA OOM on the RTX 3060 12GB". Two things follow, and both are why
this is a conflict rather than a closed question:

1. The reduction bundled **three** changes, so the OOM is not attributed to
   this knob alone.
2. It was an OOM fix for **srv2's 12 GB card**. srv1 has a **6 GB** card and
   carries the same value, unexamined.

vLLM 0.26.0's own default is **0.92** on both builds (`vllm serve --help=all`,
read 2026-08-22, byte-identical across the pip and container installs), so
0.85 is a deliberate 7-point reduction no document here defends.

An earlier reading of this session proposed that 0.85 was chosen in response to
Finding 2c (`serving-surface-2026-08-18/README.md:124`), to leave co-residency
headroom. **That is refuted by chronology**: 0.85 predates Finding 2c, and the
value Finding 2c observed was 0.90. Recorded here because the inference was
plausible and someone will make it again.

The `min_vram_fraction: 0.85` that was removed from the 7B entry is a different
quantity — a floor on the fraction of an *ollama model's own bytes* resident,
against a cap on the *card's VRAM vLLM preallocates*. Opposite direction, and
the global constant it replaced was 0.8. No document connects them.

- decision: owed — is 0.85 this project's choice or local-ai's, and does an OOM
  fix taken on a 12 GB card apply unchanged to a 6 GB one?

## Rulings recorded 2026-08-22 — eight, from the owner in one pass

Appended, append-only, beside `## Conflicts recorded 2026-08-21` (K1–K6),
`## Conflicts recorded 2026-08-22` (K7–K9) and `## Conflict recorded
2026-08-22 (second)` (K10, which has its own heading). **None of those blocks
is edited.** Their `- decision: owed —` lines are the state at the time they were
written and stay that way; this block is where the answers live, and each
ruling names the check it moves. `grep -c ': owed — '` on
`tests/test_calibration_conflicts.py` printed 8 before this block and prints 0
after it, which is #328's last definition-of-done box.

Zero rig time was spent here. Nothing in this block is a measurement.

**Two checks were rewritten by their own ruling and one was repointed.** A
ruling that makes a check unpassable is not honoured by leaving the check
standing — K7 asserted geometry *equality* and the ruling permits difference;
K8 asserted a floor of two models per engine and the ruling abolishes the
quantity. Both were rewritten in the ruling's commit, and both are still red,
for the reason the ruling creates rather than the one it removed. K6 was
repointed from a field name nothing writes. See ADR-0037's 2026-08-22
amendment, which also adds the third reason grammar the last item below uses.

---

**K1 — the pin is the sampler the request ran under.**
`tests/test_calibration_conflicts.py::test_the_sampler_pin_is_the_layer_the_request_ran_under`
- decision: 2026-08-22, owner — the pin is the layer the request ran under.
  llama-server's `/props` defaults are **recorded beside it and not digested**.
  The digest's **sampler half** is one constant set — `temperature 0.8, top_k
  40, top_p 0.95, min_p 0.05, repeat_penalty 1.0` — across all 17 served slots
  (11 distinct models over 19 served children), while the slots those cells ran
  disagree with it on `top_p`, `min_p` and `repeat_penalty` 17 of 17, on
  `temperature` on 4 and on `top_k` on 1. A sampler pin that cannot tell those
  apart cannot decide whether two cells are comparable, which is
  `serving_semantic_sha256`'s only job. (Re-derived 2026-08-22 by running the
  check's own helpers over `d7-survey.json`. The whole digest is not identical
  across cells — only this half is, which is the half the ruling moves.)
- code owed: #336 (`backends/ollama.py:741-742`; the pin must also name which
  request layer it took — the ramp sends `temperature: 0.0`, the describe probe
  sends no sampler at all)

**K2 — record, never equalise.**
`tests/test_calibration_conflicts.py::test_the_launched_context_total_has_a_name_in_the_semantic_block`
- decision: 2026-08-22, owner — the launched total gets its own name, and a
  cross-host contrast **carries** the difference rather than the hosts being
  pinned to match. Equalising was rejected: it fights the no-caps rule (the
  hardware is the limit) and would still leave the total unnamed.
- code owed: #336 (`CONTEXT_TOTAL_KEY` is already declared in the check;
  `fingerprint.SEMANTIC` is not)

**K3 — a yield that finds the card held names the holder.**
`tests/test_calibration_conflicts.py::test_a_yield_row_that_finds_the_card_held_names_the_holder`
- decision: 2026-08-22, owner — yes. `release()` names the holder from
  `/api/ps` and the card's process list. vLLM's want of a residents equivalent
  is a **stated refusal**, not a null.
- code owed: #336. Note the run contract already depends on this: its
  co-residency pre-state is a card that "already holds a **named** neighbour"
  (`docs/run-contract-2026-08-22.md:78`), which cannot be asserted while no row
  says whose memory it is.

**K6 — the row carries the build; repointed to the name the tree writes.**
`tests/test_calibration_conflicts.py::test_a_cross_host_figure_carries_the_engine_version_on_each_host`
- decision: 2026-08-22, owner — a cross-host row **carries** the build and does
  not refuse the split. The "what moved between 0.32.4 and 0.32.5" half is dead
  — both rigs are one build since 2026-08-22 — and the recording half is live.
- repointed: the check asked every row for `engine_version`, which appears
  nowhere in `tools/` or `src/` and never did. `calibrate.py:115,129` builds an
  `identity` block carrying **`serving_build`** with a sibling `refusals` entry.
  The check now reads `identity.serving_build` and the test's *name* is kept,
  because #328's definition of done quotes it. A check a correct run cannot
  satisfy is a typo with a marker on it, not a finding — which is why this
  needed the owner rather than a session's judgement.
- **owed: a run, not code.** `calibrate.emit()` merges the identity block into
  every row that carries a `host` (`calibrate.py:172`) and has since #326
  landed on 2026-08-21 — so the ramp sink already emits `serving_build`. The
  reason `grep -ro serving_build *.jsonl` in this directory is empty is that
  these journals were written on 2026-08-19 and **predate the sink**. This
  entry first said "the ramp sink does not emit it", which was wrong; corrected
  before this block was committed, and #336's K6 box restated to match, so
  nobody ticks a box that is already satisfied. What K6 needs is a post-#326
  campaign on disk.

**K7 — a cross-host figure may rest on children launched differently.**
`tests/test_calibration_conflicts.py::test_a_model_served_on_both_hosts_was_launched_with_the_same_geometry`
- decision: 2026-08-22, owner — yes, **provided the difference is recorded and
  declared on the contrast that reads the two rows**. Same ruling as K2, asked
  of the population that actually bears a cross-host claim.
- rewritten: the check asserted equality, which the ruling permits to fail
  forever. It now asserts that both hosts' launched total is on the record for
  every model a cross-host figure could rest on. It fails independently of K2:
  a campaign naming the total for single-host children and omitting it for the
  shared ones passes K2 by a wide margin and fails here.
- the second clause is elsewhere: the ignore list is ADR-0038 D4's contrast
  record, checked in `tests/test_run_contract.py`, because an ignore is a
  property of the claim and the claim is built at reading time.
- code owed: #336 for the recording; #335 for the contrast

**K8 — two hosts are two one-armed cells, not one contrast.**
`tests/test_calibration_conflicts.py::test_a_cross_host_agreement_rests_on_more_than_one_model_per_engine`
- decision: 2026-08-22, owner — **there is no such number.** Cross-host
  equivalence is never claimed; srv1 and srv2 are not one instrument at any
  population, and ollama and vLLM are never equivalent either. The owner's own
  framing, quoted verbatim from the ruling, typing and all:

  > we run a check to see how much can we 1.5B models can we put on each
  > machine = 2 one armed cells -> we can use them if we create the second arm
  > -> the second arm is runnig the same amount of 1.5B models with one config
  > different, e.g. context.arm1!=context.arm2. that way we can use data we get
  > from testing capability to measure.

  So a **capability** cell's comparison is built by adding a second arm against
  it — typically on the same machine, differing in exactly one declared
  parameter. This is ADR-0038 D5's one-armed cell made concrete, and it is why
  a capability measurement is reusable as a contrast nobody planned.
- **scope, stated because the first draft of this entry over-read it:** the
  ruling denies cross-host *equivalence*, not cross-machine *comparison*.
  ADR-0038 **D1** withdrew the rigs' roles and **D2** says a cross-machine
  question authorises its own run — *"which machine serves the 1.5B faster"* is
  D2's own example — and both were Accepted the same day as this ruling. A
  cross-machine contrast therefore stays available and carries what it ignored
  on D4's record, which is K7's ruling above. What is denied is treating the
  two hosts as interchangeable instruments, which is what a models-per-engine
  floor was quietly building toward.
- rewritten: `MIN_CROSS_HOST_MODELS` is retired — a floor presumes a count at
  which two hosts become one instrument, and the ruling says there is none. The
  check now asks that every model this campaign read on more than one host is
  stored as a standalone cell per host, in the shape D5 defines. Red today
  because the campaign holds journals, not cells.
- deliberately not asserted: per-model cell naming. #335 has not defined the
  convention and this check does not own it.
- code owed: #335

**K9 — every host declares the settings that decide residency.**
`tests/test_calibration_conflicts.py::test_both_hosts_declare_the_settings_that_decide_residency`
- decision: 2026-08-22, owner — every host declares them. An engine default
  inherited in silence is **not** a declaration.
- state: both rigs were declared live on 2026-08-22, so the check goes green on
  the next campaign's survey without further code. **This is not the same as
  closed.** The rig state is asserted in prose only: `0.32.15` and the three
  settings on srv2 appear nowhere in this tree except a session record and
  ADR-0038's Context, no capture shows them, and nothing in the repository sets
  or asserts them. It
  can regress between campaigns and nothing here would notice — an unfiled gap,
  named on purpose so it is not re-derived.

**K10 — 0.85 is local-ai's, and it is not kept on a citation.**
`tests/test_calibration_conflicts.py::test_a_serving_constant_this_project_did_not_choose_names_its_source`
- decision: 2026-08-22, owner — the value is **measured on both rigs**, and the
  entry then names that measurement as its origin. Keeping 0.85 with a source
  note was offered and declined.
- measurement owed: #337. It carries the two sites this check reads
  (`configs/srv-full.json:34,:60`) and the three it cannot see —
  `calibrate.py:596`, `calibrate.py:833`, and `backends/vllm.py:599`, the
  fallback default that runs whenever a config omits the key. It also carries
  the consequence: `gpu_memory_utilization` is in `fingerprint.SEMANTIC`
  (`fingerprint.py:182`), so the measured value **re-baselines the serving
  pin** — which is why it is ordered before the campaign re-run, not after.

---

**The ninth marker is not the owner's.**
`tests/test_cross_rig_claim.py::test_the_2026_08_20_cross_rig_claim_holds_only_on_a_journal_with_identity_rows`
asks whether the width-16 gap is hardware or configuration. No ruling settles
that: the journal names no card, no engine build and no weights on any row, so
the answer is not in the tree. Reworded from `owed —` to **`measurement owed —`**
under ADR-0037's 2026-08-22 amendment, which added the third grammar for
exactly this: a reason now says *who* owes a finding — the owner, the keyboard,
or the rigs — and `grep ': owed — '` answers one question only.

The three markers in `tests/test_run_contract.py` were reworded the other way,
to `decided —`. Their own text said *"ADR-0038 D3/D4/D5 **is decided** and
unimplemented"*: the owner had ruled, ADR-0038 was Accepted the same day, and
what was owed was #335's harness code. A finding whose decision lives in
another record is `decided`, and the reason names the record.

**One correction to the 2026-08-22 session record.** It states that
`max_speedup_vs_n1` is null on every survey cell, and rejected a peer agent's
srv2 range of 1.02–1.10 on that basis. That is true of the **top-level** key
only — it is null on 17 of 17. The nested
`concurrency.saturation.max_speedup_vs_n1` is populated on all 17, and **srv2's
eleven cells run 1.02–1.10 exactly**, which is the rejected range. The peer was
reading a real population.

Every figure below names its population, because the paragraph's own point is
that a quoted number does not. All re-derived 2026-08-22 from `d7-survey.json`
and this directory's `*.jsonl`:

| population | n | range |
|---|---|---|
| survey nested, srv2 | 11 | 1.02–1.10 |
| survey nested, srv1 | 6 | 1.03–1.59 |
| survey nested, all | 17 | 1.02–1.59 |
| ramp journals, srv1 | 27 | 1.00–4.16 |
| ramp journals, srv2 | 9 | 1.02–15.42 |
| ramp journals, all | 36 | 1.00–15.42 |

Two live speedup populations exist in this campaign, they do not mean the same
thing, and **nothing on a quoted figure says which one it came from.** Recorded
here rather than fixed: it is a defect in what a figure carries, and it belongs
to whichever check claims it, not to this block. (The first draft of this
paragraph quoted "ramp journals 1.09–2.27, survey 1.02–1.10" — both srv2-only
subsets presented as whole populations, which is the very defect the paragraph
names. Corrected before this block was committed.)

## Correction — 2026-08-22 (#328), appended: K9's gap is closed, not merely named

The `## Rulings recorded 2026-08-22` block above records K9 as ruled and then
names an **unfiled gap**: *"nothing in the repository sets or asserts them. It
can regress between campaigns and nothing here would notice."* The owner's
answer to that, the same day, was to close it now.

It is closed as data plus a check, which is ADR-0037 rule 1 applied to the gap
itself rather than to a campaign finding:

- **`tools/bench/serving/configs/hosts.json`** — the declared host state. The
  three residency settings with the value each must hold (`OLLAMA_NUM_PARALLEL=0`,
  `OLLAMA_MAX_LOADED_MODELS=0`, `OLLAMA_KEEP_ALIVE=-1`) and the reason for each,
  the declared ollama build (`0.32.15`), the unit-file content a host must
  carry, and — named rather than left silent — the two things it deliberately
  does **not** declare: the vLLM image digest, which the session record elided
  to `sha256:ffb2d59b…` so the full value exists only on the hosts, and
  `gpu_memory_utilization`, which #337 is measuring rather than inheriting.
- **`tests/test_declared_host_state.py`** — four green checks over the
  declaration (it covers every residency setting, every setting states a value
  *and* why, the omissions are named, plus a canary that shows the reason check
  rejecting) and two strict xfails that hold the newest campaign's survey to it.

**The half K9 could not see.** K9 asks whether a setting's *name* appears in the
unit. The new check asks whether it appears **set to the declared value** — so a
rig that quietly restored `OLLAMA_KEEP_ALIVE=5m` would satisfy K9 and put a
clock back over the co-residency cells. Demonstrated before landing: red on the
2026-08-19 survey (6 of 6 pairs wrong, both hosts on the wrong build), green on
a survey matching the declaration, and red again when a single host reverts one
setting or drifts one build.

**Two consequences, stated rather than discovered later.**

1. `hosts.json` sits under `contract.HARNESS_SURFACE`, so it **moves the serving
   pin**. That is where it belongs — a declaration of required host state
   outside the pinned harness is the drift it exists to stop — and it lands
   before the campaign re-run, alongside #337's measured
   `gpu_memory_utilization`, so the re-run banks one pin rather than three.
2. Applying the state is still a host action. The repository states the unit
   content and checks the result; it does not write to a rig's unit files, and a
   setter that could silently disagree with this file would be the same drift
   wearing a different hat.

**A defect found in the closing work, recorded because it is the failure mode
this project keeps meeting.** The new module's `campaign()` was first written
as `def campaign(evidence: Path = EVIDENCE)`. A default argument is evaluated at
import, so pointing the module at a mutated copy of the evidence did nothing and
the sweep meant to demonstrate the two checks green could not move them — they
were red against the real directory the whole time and looked correct. It is the
exact seam `tests/test_calibration_conflicts.campaign` documents keeping open,
and it was caught only because the demonstration was actually run rather than
assumed. Fixed to resolve at call time before either check landed.

## Correction appended 2026-08-24 (second) — which of this campaign's constants survive (#356)

The block above voids the throughput columns. This one is about the residue: the
constants read off those curves and wired into `contract.py`, pinned by markers in
`launch.py`, and inherited by any rebuild. Each was either re-derived against a
measurement taken with the configuration declared, or is recorded as invariant with
the reason. "Still looks right" was not an admissible outcome (ADR-0026 lens 3).
The provenance now travels with the constants: `contract.PROVENANCE` names the run
behind every numeric constant in that module, and
`tests/test_serving.py::test_every_serving_constant_names_the_run_behind_it`
refuses one without an entry, an entry naming no evidence directory on disk, and an
entry naming no constant.

**The instrument.** `records/evidence/2026-08-24-config-sweep/` — 140 cells, 104
launched, 68 with `--enforce-eager` and 36 with CUDA graphs on, ladder to 384 —
read through this directory's own readers (`_throughput_plateau`, `_max_speedup`,
`_latency_plateau`) at the shipped constants and their neighbours. Plus one run
filed for this review, `records/evidence/2026-08-24-ramp-tokens/`, for the one
constant the sweep could not vary.

| constant | value | outcome | what the graphs-on data says |
|---|---|---|---|
| `RAMP_LEVELS` | (1…24) | **survives as the survey default; superseded as the width-matrix ladder** | both rigs' maxima sit at 128 (srv1) / 256 (srv2) with `--max-num-seqs 256`; 384 read below 256. `contract.ladder(width)` now continues the knee ladder to one level past 1.5× the configured width (`RAMP_LADDER_EXTENSION`, to 384); `calibrate.py --phase ramp` uses it. Width ≤ 16 — every D7 row — gets the old ladder, so those cells remain re-takeable. Cost stated in the docstring: ~1 h per two-repeat ramp at width 256 on srv1, ~10 min on srv2. |
| `RAMP_REPEATS` | 2 | **invariant, unmeasured with graphs** | reads no rate. The only `repeat_spread` on record is 2026-08-23's cross-rig ramp (eager): second attempt won 4 of 9 levels on each rig, max/min ≤ 1.015 srv1 / 1.072 srv2. This journal holds no losing repeat — the field landed after it ran. |
| `RAMP_TOKENS` | 475 | **survives** | re-measured at 128/256/475/1024 tokens on both rigs with graphs on (`2026-08-24-ramp-tokens/`). At n=1, 475 reads 97% (srv1) / 95% (srv2) of the 1024 rate; 128 reads 81% / 77%. The per-request overhead scaled with the rig (0.79 s → 0.22 s), so its share at 475 is 6.9% / 8.3% on both — the D3 argument was about a share, and the share survived the rate being corrected. Past the knee 1024 reads 6-10% below 475: longer is a different regime, not a better reading. |
| `PLATEAU_FRACTION` | 0.92 | **survives** | 0.92 and 0.95 agree on all 104 launched cells; 0.90 differs on two srv2 graph cells. Caveat: the sweep's ladder is powers of two, so this is agreement at that resolution. |
| `INFERRED_SATURATION_MIN_SPEEDUP` | 1.0 | **survives** | lowest max-speedup with graphs on is 3.61 (srv1), 7.5 (srv2). The 0.02 boundary case at `:996-1000` is a width-1 property; nothing in the new regime is within 3× of the floor. |
| `LATENCY_TOLERANCE` | 0.10 | invariant | informational; nothing downstream reads it. |
| `RAMP_FLOOR_TOKENS_PER_S` / `RAMP_TIMEOUT_BASE_S` | 4.0 / 90 | **survive** | slowest request across 104 cells used 14.9% of its budget (srv1, n=2). At n=256 on srv1 a stream ran 0.79 tok/s — below the floor per stream — and the floor is aggregate: budget 30,490 s against a 413 s level. A 5× faster rig loosens it. |
| `STEP_TIMEOUT_S` / `IDLE_GPU_MIB` | 180 / 500 | invariant | ssh steps outside the engine; every released card read 1 MiB after all 140 cells. |
| `START_TIMEOUT_S` (`vllm.py`) | 900 | **survives, and every prior point was an underestimate** | eager skips graph capture. Graphs-on container launches: median 122 s both rigs, max 153 s (srv1) / 145 s (srv2), against eager medians of 81–84 s — capture is ~40 s here. 900 is 5.9× the slowest measured; a cold cache and the 14B are not in the set. The D6 points at `:1002` (33 s pip srv1, 109 s srv2) stand as eager launches. |
| `DIGEST_TIMEOUT_S` (`vllm.py`) | 1800 | invariant, confirmed | #356 listed it as the other engine's; it is vLLM's, and the digest is a separate process no serve flag reaches. Points: 7.3 s host torch; 7.5 / 10.4 s in-image (2026-08-23). |
| `LOAD_ATTEMPTS` (`ollama.py`) | 2 | invariant, confirmed | not that engine's flag; all 17 `claim.attempts` trails in `d7-survey.json` loaded on attempt 1 with the card idle, so the second attempt has never been exercised — its cost is measured at zero, its rescue rate is not measured. |

**Markers.** No constant's value moved, so no existing marker string changed.
Three markers were added: `def ladder(`, `PROVENANCE: dict[str, dict[str, str]]`,
and `contract.ladder(width)` in `calibrate.py`.

**What this does not do.** It does not re-run the campaign, decide the knob surface
(#357) or put the resolved configuration into the identity key (#358). The
`calibrate.py` serve dict at `:594-602` still carries `--enforce-eager`; removing it
is the rebuild's decision, and the rebuild now inherits constants with their runs
named rather than constants with a marker.
