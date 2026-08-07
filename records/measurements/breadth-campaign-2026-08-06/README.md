# The breadth campaign — every model walked to where it fails, then swept there

Issue: [#121](https://github.com/AdarGit008/mcgyvr/issues/121), under
[#111](https://github.com/AdarGit008/mcgyvr/issues/111).
Instrument: [`campaign.py`](../../../tools/breadth/campaign.py) driving
[`measure.py`](../../../tools/breadth/measure.py).
Refinement batch beside this one: [`../breadth-batch-b-2026-08-06/`](../breadth-batch-b-2026-08-06/).

## Why this exists and what it replaces

`measure.py`'s first run swept the strongest local model against the easiest
task set and found the first-pass index concentrated entirely at zero — the
result [CLM-0013](../../claims/CLM-0013.json) registers. That number is real
and it is about a ceiling: a model passing 18 of 20 tasks on its first draw has
almost nothing left for a second draw to find, so the distribution was pinned
by the choice of rung and task set rather than by anything about breadth.

This campaign inverts the selection. For each model, smallest first, it probes
one greedy draw per task up a difficulty ladder until the model **stops passing
with ease** (< 90%), then sweeps breadth at that tier with a greedy anchor plus
eight serial sampled draws and no early exit. Breadth's value, if it has one,
lives where a model actually fails — and every model here is measured at its
own failure tier rather than at a shared one.

Failures are classified because they mean different things: a **logic** failure
is a complete, parseable reply the declared acceptance rejected; **parse**
refusals and **cap truncations** are counted apart and are not evidence about
capability.

## Method

- **Hosts.** srv1 (4 models) and srv2 (10), both Ollama over the
  OpenAI-compatible path. Each host's `campaign.json` records every decision
  the driver made.
- **Tiers.** d1 is the bundle rig's pinned 20-task JS/TS set, byte for byte.
  d2 and d3 are harder 12-task sets in `tools/breadth/tasks/`, same format,
  built for this campaign because the top rungs pass d1 at its ceiling.
- **Draws.** One greedy (T=0.0) anchor and eight sampled draws at T=0.7, serial,
  **no early exit** — production stops at the first gate pass and this must not,
  or every observation is truncated at its own answer. A test holds it.
- **Cap.** 768 output tokens, the bundle sweep's, so "truncated" means the same
  thing in both instruments. **This turns out to matter enormously — see below.**
- **"Pass"** is the contract's declared acceptance, executed: the proxy
  CLM-0012 is quoted on, not the full `Gate.run`.
- **Provenance and resume.** `run.json` per stage pins worker, sampler, cap,
  bundle and task digests; a resume under any other identity is refused. This
  campaign was interrupted by a host restart mid-`gpt-oss:20b` and resumed with
  the identical command — the six finished models replayed from disk without a
  dispatch.

## Result

Per model: probe pass rate per tier, the tier it stopped at, and coverage at
one draw against eight at that tier.

### srv1

| model | probe d1 | stop | k=1 | k=8 | of | logic | parse | trunc |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| qwen2.5-coder:1.5b | 0.35 | d1 | 6 | 10 | 20 | 116 | 0 | 0 |
| qwen2.5-coder:3b | 0.50 | d1 | 10 | 15 | 20 | 91 | 0 | 1 |
| llama3.2:3b | 0.35 | d1 | 6 | 10 | 20 | 123 | 0 | 0 |
| qwen2.5-coder:7b | 0.70 | d1 | 13 | 17 | 20 | 59 | 0 | 0 |

### srv2

| model | probe d1 | probe d2 | stop | k=1 | k=8 | of | logic | parse | trunc |
|---|--:|--:|---|--:|--:|--:|--:|--:|--:|
| qwen2.5-coder:1.5b | 0.35 | — | d1 | 5 | 11 | 20 | 119 | 0 | 0 |
| qwen2.5-coder:3b | 0.55 | — | d1 | 10 | 15 | 20 | 96 | 0 | 1 |
| qwen2.5-coder:7b | 0.65 | — | d1 | 15 | 17 | 20 | 52 | 0 | 0 |
| yi-coder:9b | 0.60 | — | d1 | 14 | 16 | 20 | 66 | 0 | 0 |
| deepseek-coder-v2:16b | 0.60 | — | d1 | 10 | 15 | 20 | 75 | 0 | 0 |
| qwen2.5-coder:14b | 0.75 | — | d1 | 14 | 17 | 20 | 48 | 0 | 0 |
| gpt-oss:20b | 0.70 | — | d1 | 12 | 17 | 20 | 3 | 6 | **56** |
| qwen3:30b-a3b | 0.05 | — | d1 | 0 | 2 | 20 | 0 | 0 | **172** |
| qwen3-coder:30b | 0.95 | 0.75 | **d2** | 9 | 11 | 12 | 24 | 0 | 0 |
| qwen3-coder-next-ud:q3_K_XL | 0.95 | 0.83 | **d2** | 11 | **11** | 12 | 16 | 0 | 2 |

### What it says

**Breadth pays, and it pays most where the model is weakest.** Every model
except one gains from eight draws: +4 to +6 tasks of 20 at the bottom of the
ladder, +2 to +3 at the top of d1, +2 of 12 for qwen3-coder:30b on the hard
set. The refinement batch repeats the srv1 cells three times each and the gain
survives (see that record); the d2 gain was repeated three times here and came
back +2 every run.

**And it disappears at the top.** qwen3-coder-next-ud reaches 11 of 12 on its
first draw and 11 of 12 after eight — CLM-0013's flat distribution again, now
on genuinely hard tasks rather than the easy set where it was first seen. That
is one run and should not be quoted as settled, but it is the strongest local
model on this host and it is the shape CLM-0013 described.

So neither "breadth is worth nothing" nor "breadth is worth several tasks" is
a fact about breadth. Both are facts about a rung, and the campaign's spread
from +6 to 0 across one ladder is the finding.

## Two rows that measure the cap, not the model

`qwen3:30b-a3b` truncated **172 of 180 draws** and probed at 0.05. It has zero
logic failures because almost nothing it produced was ever complete enough to
judge. Its "2 of 20" is a statement about a 768-token output budget meeting a
reasoning model, and it is not evidence about capability or about breadth.
`gpt-oss:20b` is the same failure in milder form — 56 truncations against 3
logic failures.

Neither row should be read as a capability measurement, and neither belongs in
any average taken over this table. The right follow-up is a cap raised for
reasoning models, not a re-run at 768 (issue #168's neighbourhood).

## Limits

- One task set family (JS/TS), two hosts, one serving stack, one wire protocol.
- Every cell here is **one run**. Run-to-run spread on the coverage figure was
  measured in the refinement batch at about ±2 tasks, which is larger than
  several of the differences in these tables. Differences under 2 tasks between
  models or tiers should not be read as real.
- "Pass" is the declared acceptance, not `Gate.run`. What a weaker checker does
  to every number above is measured in the refinement batch, and it is severe.
- The ladder stopped at d1 for twelve of fourteen models, so d2 is sampled by
  two models and d3 by none. The campaign is mostly a d1 result.
- `ease = 0.9` is a chosen threshold; a model at 0.88 and one at 0.35 both
  "stop" at d1 and are swept there, which flattens a real difference in how
  much room a rung has left.
