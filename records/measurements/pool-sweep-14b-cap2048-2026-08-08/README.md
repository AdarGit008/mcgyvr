# Pool sweep at cap 2048, 2026-08-08 — the reply-length distribution, uncensored

**What this is.** `pool-sweep-14b-2026-08-07` re-run at a cap that does not
bind: same model (`qwen2.5-coder:14b` on srv2), same 269 problems, same prompt
bundle, same temperatures, same draw count, **cap raised 768 → 2048**. 807
rows, **0 truncated, 0 replies the parser refused, 0 draws lost**.

It exists because #212 found that all 47 of the earlier run's "parse refusals"
were the 768-token cap, and because #216 needs an uncensored length
distribution to fit a sizing formula against. Every figure on this page was
unobtainable from the capped run: a truncated reply's true length is censored,
and no analysis recovers it.

```
uv run --no-sync python tools/breadth/measure.py \
    --endpoint http://srv2:11434 --protocol openai --model qwen2.5-coder:14b \
    --tier pool-ts --draws 2 --sampled-temperature 0.7 --max-output-tokens 2048 \
    --tasks "$(<the 269 ids>)" \
    --out records/measurements/pool-sweep-14b-cap2048-2026-08-08
```

## The cap does not bind

| | median | p90 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| all 807 rows | 397 | 708 | — | 1114 | **1370** |

678 tokens of headroom left unused. **52 rows (6.4%) ran past the old 768**,
and those are the draws the earlier run destroyed.

## Raising the cap recovered almost nothing

| | passed | truncated | refused |
|---|---:|---:|---:|
| old, cap 768 | 262/807 (32.5%) | 47 | 47 |
| new, cap 2048 | 273/807 (33.8%) | 0 | 0 |

Of the **47 cells that were truncated under 768, exactly 4 now pass** and 43
still fail. The replies were not correct answers cut short; they were wrong
answers that also ran long. This is the direct measurement of what #212 could
only infer by discarding truncated rows, and it agrees: **the cap was costing
about half a percentage point, not the difficulty gap.**

## The churn is larger than the effect, and that is the finding to carry

The net +11 is the residue of **49 cells newly passing and 38 newly failing** —
and only **4 of the 49** were previously truncated. The other 45 flips, and all
38 reversals, are run-to-run variation between two runs of the same experiment.

Greedy is supposed to be the reproducible arm. It is not, quite:

- **227 of 269 greedy replies are byte-identical across the two runs (84%).**
- 14 of the 42 that differ were truncated under 768 and legitimately continue.
- That leaves **~28 greedy cells — 11% of the untruncated ones — differing with
  temperature 0, the same weights, the same prompt and the same host.**

**But differing text is not a differing verdict, and the two must not be
conflated.** Collapsing to one outcome per problem, and removing the flips the
cap change can explain, the same two runs give:

| unit | discordant | net drift | a real effect must net |
|---|---:|---:|---:|
| greedy, problem verdict | **1 / 269** | +0.4% | > 2 problems (**+0.7%**) |
| any-of-3-draws (2 sampled at T=0.7) | 24 / 269 | +3.7% | > 10 problems (+3.6%) |

So **11% of greedy replies differ and only ~1% of greedy verdicts do** — most
text divergence lands on a problem the model was going to fail either way.
Greedy is a far quieter instrument than the byte-identity rate suggests, and the
noise lives in the sampled arm.

Ranked, the three sources anyone differencing two sweeps has to clear:

1. **greedy re-run, same backend: ±0.7pp** — small, and the reason greedy is
   worth paying for;
2. **sampled / any-of-k: ±3.6pp** — this is sampling working as designed, not a
   defect, but it must be replicated or it swamps a small effect;
3. **backend change: 2.6pp** — the fine-tune pilot's own 2×2 read +1.9pp on CUDA
   and −0.7pp on CPU from identical weights
   (`records/measurements/finetune-pilot-2026-08-07/`). Changing backend between
   two arms measures the backend.

The consequence for the fine-tune question is #219: a +3pp bar tested on
HumanEval+ at n=164 has a minimum detectable effect of ~+4.8pp, so #189's
+1.9pp cannot separate "no effect" from "an effect that would have passed".

## #212's verdict survives with the cap removed

| | first 189 | the 80 | ratio |
|---|---:|---:|---:|
| old, cap 768 | 216/567 (38.1%) | 46/240 (19.2%) | 0.50 |
| **new, cap 2048** | **221/567 (39.0%)** | **52/240 (21.7%)** | **0.56** |

Both sets now carry **zero refusals**, so nothing about this comparison is a
property of the instrument. The 80 remain about half as passable. #212's
conclusion — harder problems, not problems that are harder to state — is
confirmed by direct measurement rather than by conditioning.

`≥1 pass in 3 draws` moves the same small amount: first 189 94 → 103 of 189,
the 80 20 → 24 of 80.

## What #216 asked for: the distribution, by task type

| task type | n | median | p90 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| `function_implementation` | 564 | 418 | 728 | 803 | **1151** | 1370 |
| `bug_fix` | 243 | 345 | 628 | 739 | **805** | 933 |

**The two types need different caps, and not only for the reason #216 gave.**
The issue argued the branch from *available inputs* — `target_content` exists
for `bug_fix` and is identically absent for `function_implementation`. That
holds. But the tails also differ in shape: a cap covering 99% of draws is
**1151 for `function_implementation` and 805 for `bug_fix`**, and the largest
`bug_fix` reply ever seen (933) is below `function_implementation`'s p99. A
single flat cap set for the harder type over-provisions the other by ~43%.

Note also that the old 768 sat **below `function_implementation`'s p95 (803)**.
It was cutting into the top 5% of that type's draws, which is exactly the
6.4% overrun observed.

### Censoring barely biased the earlier estimates

#216's correlations were computed on complete replies only, from the capped
run, and the concern was that dropping the long tail biased them. Refit here on
uncensored data, they barely move:

| signal | `function_implementation` | `bug_fix` |
|---|---|---|
| `target_content` chars | n/a — absent for all | **+0.634** (was +0.632) |
| `task` prose chars | **+0.714** (was +0.688) | +0.737 (was +0.749) |
| `interface` chars | +0.243 (was +0.237) | +0.109 (was +0.083) |
| reference-solution chars | +0.865 (was +0.847) | +0.907 (was +0.931) |

So #216's premise was sound and this run confirms rather than overturns it. The
value of the run is the **absolute** numbers — the percentiles a cap must clear
— which no amount of re-reading the capped run could produce.

### Candidate ratios for a formula

| | `function_implementation` | `bug_fix` |
|---|---:|---:|
| tokens per reference-solution char | 0.292 | 0.275 |
| tokens per `target_content` char | n/a | **0.530** |
| tokens per `task`-prose char | 0.432 | 0.321 |

Tokens per reference char is stable across types (0.292 / 0.275) — the
conversion from *answer size* to *tokens* looks type-independent, and the
per-type work is in predicting answer size from what a dispatcher can see.

## Caveats

- **One model, one host, one arm, three draws.** These percentiles describe
  `qwen2.5-coder:14b` on TypeScript. #216's out-of-scope line says the cap is a
  contract property and must not need to know the worker; whether these
  percentiles transfer to the 7B or to Python is **unmeasured**, and a formula
  fitted only on this run would be fitting one worker.
- **A cap of 2048 bounds the observation at 2048.** Nothing hit it, so the
  distribution is complete *for this run* — but "no draw exceeded 1370" is a
  statement about 807 draws, not a guarantee.
- **The run had a backend outage and was resumed.** srv2 became unreachable for
  51 consecutive tasks (`p164-truncated-product` … `p214-debounce-levels`),
  losing 152 draws to identical 120s transport timeouts; it answered normally
  0.14s later. Those rows are kept verbatim in
  `dispatch-errors-invocation-1.jsonl` and were removed from `results.jsonl` so
  the resume could refill their cells — `done_keys` counts any row as a filled
  cell, so without pruning they would have been skipped forever. That defect is
  **#217**. `run.json` records both invocations. The refilled cells were drawn
  ~40 minutes after the rest; given the greedy non-reproducibility measured
  above, that is a within-noise difference and not a separate condition, but it
  is a difference and it is stated.
- Same prompt bundle (`001c23ec…`), tier, temperatures, draw count and task
  digests as `pool-sweep-14b-2026-08-07`; only the cap differs. Checked, not
  assumed.
