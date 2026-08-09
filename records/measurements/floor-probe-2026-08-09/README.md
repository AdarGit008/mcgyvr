# Floor probe, 2026-08-09 — the 3B reads zero on the pool, and that is the finding

**What this is.** The evidence behind
[ADR-0017](../../../docs/decisions/0017-the-floor-is-the-product.md) and #220.
#219 planned to re-tune `qwen2.5-coder:3b` and evaluate it on the #197 problem
pool. These five probes were run *before* spending the ~6h that design costs,
and they showed the design could not answer its own question: the 3B passes
nothing in the pool, so there is no headroom for a +3pp effect to occupy.

All arms are **greedy only** (`--draws 0`), cap **2048** so nothing is censored,
dispatched through `tools/breadth/measure.py` at `f3444034`.

## The arms

| arm | model | tier | tasks | passed |
|---|---|---|---|---:|
| `3b-ts-early` | qwen2.5-coder:3b | `pool-ts` | `p001`–`p020` | **0/20** |
| `3b-ts-heldout` | qwen2.5-coder:3b | `pool-ts` | `p282`–`p291` | **0/10** |
| `3b-py-early` | qwen2.5-coder:3b | `pool-py` | `p001`–`p020` | **0/20** |
| `7b-ts-heldout30` | qwen2.5-coder:7b | `pool-ts` | 30 hash-spread from `p282`+ | **1/30** |
| `14b-ts-heldout30` | qwen2.5-coder:14b | `pool-ts` | the same 30 | **5/30** |
| `3b-d1-graded` | qwen2.5-coder:3b | `d1` | all 20 | **10/20** |
| `3b-d2-graded` | qwen2.5-coder:3b | `d2` | all 12 | **5/12** |
| `3b-d3-graded` | qwen2.5-coder:3b | `d3` | all 12 | **2/12** |

The 3B ran on srv1, the 14B on srv2, both `protocol: openai` on 11434.

The two `heldout30` arms serve **identical task ids**, chosen by sorting the 230
never-swept problems on `sha256(id)` and taking the first 30, then sorting back
into id order. Hash-spread rather than contiguous or id-spaced: #197 recorded
that a probe sampled by id spacing read 1/10 where the full sweep read 19.0%,
so neither of the obvious samplings is trustworthy at this size.

## The finding

**Zero is not an instrument artifact.** Across all 50 3B rows: zero parse
refusals and **every `stop_reason` `complete`**, so nothing was cut off. Read
the stop reason, not `overran_cap` — the latter is `output_tokens >
max_output_tokens`, a cap *violation* check, and it is correctly `false` on a
reply that stopped exactly at the ceiling (`runner.py:242`). It is not a
truncation flag and the two are easy to confuse. The replies are well-formed
fenced TypeScript and Python. The
failures were read by hand rather than counted — `p001` declares no `match`
before `while ((match = regex.exec(input)) !== null)`, `p002` returns
`' the quick'` where the test wants `'the quick'`. Genuine wrong answers.

**Not a language effect.** The Python arm reads 0/20 beside TypeScript's 0/30 on
the same twenty problems.

**Context, from records already on disk:**

| task set | n | qwen2.5-coder:3b |
|---|---:|---:|
| HumanEval+ (`finetune-pilot-2026-08-07`, q4_K_M) | 164 | 78.0% |
| breadth `d1` tier, greedy (20 distinct problems) | 243 | 50.6% |
| the #197 pool (here) | 50 | **0%** |

The pool is a different size class of task — median 60-line reference solution
(p90 104, max 233), median 18 assertions (p90 25, max 41), and an admission gate
that rejects anything a stub can pass. HumanEval problems are 5–15 line single
functions. The whole ladder compresses against it: 14B ~90% on HumanEval+ →
33.8% on the pool, 7B → ~19%, 3B → 0.

**The suffix is hard as expected, not anomalously.** The 14B's 5/30 (16.7%) on
`p282`+ against its own 33.8% baseline reproduces #212's ~0.5 batch-difficulty
ratio. The suffix is uniformly about half as passable for every model — and half
of the 3B's zero is still zero, which is why no holdout arithmetic rescues the
design.

## The graded arms: the drop is a slope, not a cliff

The three `*-graded` arms were added to answer a question the first five raised —
between `d1` at ~50% and the pool at 0%, is there a usable band or a cliff? All
three difficulty rungs run at the **same cap (2048)** as the pool arms, so the
comparison carries no cap confound:

| tier | tasks | 3B greedy | max completion tokens |
|---|---:|---:|---:|
| `d1` | 20 | **10/20 (50.0%)** | 2048 (one runaway, below) |
| `d2` | 12 | **5/12 (41.7%)** | 338 |
| `d3` | 12 | **2/12 (16.7%)** | 818 |
| the pool | 50 | **0/50 (0%)** | — |

**`d1` reproduces.** 50.0% here against the 50.6% standing in the records from
the breadth campaign — a different cap (768), different runs, different hosts.
The anchor was not a fluke.

**The band is wider than expected.** `d3` at 16.7% is low but not floored: it
still resolves improvement and regression. So the usable band for a floor
instrument spans roughly `d1` through `d3`, and the collapse to zero happens
somewhere between `d3` and the pool — a range these arms do not resolve, because
nothing exists between them.

**One runaway, and it is #212's finding again.** `d1`/`t04` hit exactly 2048
tokens, stopped `truncated`, and `parse_reply` raised `incomplete-reply` on the
stop reason. It is counted as a failure above. It is a cap event, not a format
event — the same conflation #212 corrected, recurring at a cap 2.7× larger. Note
also that `d3`'s longest reply (818) exceeds the inherited 768, so the old cap
would have censored that tier too.

## What it means, and what it does not

A model at 78% on HumanEval+ and 0% on 60-line, 18-assertion problems is not a
weak model. Its **whole-problem** ceiling sits below the pool's **unit of work**.
Closing that gap is what decomposition, the pipeline and the gates are for, so
the pool measures capability at a granularity mcgyvr is designed never to hand a
small worker. A benchmark that separates 7B from 14B cleanly is a *ceiling*
instrument; the repo owns no floor instrument at all, and that absence — not the
3B's score — is the result this directory records.

## Caveats, stated because the numbers are small

- **These are probes, not sweeps.** 10–30 tasks per arm. #197's own lesson is
  that a probe of this size can be wrong by 2×, and the 7B's 1/30 in particular
  carries a wide interval. The 3B's 0/50 is load-bearing; the 7B's 3.3% is
  directional and should not be quoted as a rate.
- **One quantization, one host each.** No backend control was run; #189 measured
  2.6pp of swing from backend numerics alone. Irrelevant at zero, relevant if
  these arms are ever compared against a re-run.
- **`3b-ts-early` and `3b-py-early` are the first twenty problems by id**, which
  is a batch, not a sample. They were chosen to test the *easy* end deliberately
  — the question was whether the 3B's zero was a property of the hard suffix, and
  it is not.

## Reproducing

```
uv run --no-sync python tools/breadth/measure.py \
    --out records/measurements/floor-probe-2026-08-09/3b-ts-early \
    --endpoint http://srv1:11434 --protocol openai --model qwen2.5-coder:3b \
    --tier pool-ts --tasks p001-parse-duration,...,p020-gapped-match \
    --draws 0 --max-output-tokens 2048
```

The served ids for every arm are in that arm's `run.json` under
`invocations[].tasks`. Note that `tasks_sha256` pins the **whole tier** as it
stands (499 digests), not the served subset, so digest counts match across arms
that served different problems.
