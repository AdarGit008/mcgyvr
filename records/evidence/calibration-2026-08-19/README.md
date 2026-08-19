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
