# Batch B — temperature, breadth's plateau, repeats, and what a thin checker costs

Issue: [#121](https://github.com/AdarGit008/mcgyvr/issues/121).
Refines [`../breadth-campaign-2026-08-06/`](../breadth-campaign-2026-08-06/)
without re-running it. Instruments:
[`measure.py`](../../../tools/breadth/measure.py) and
[`selectivity.py`](../../../tools/breadth/selectivity.py).

The campaign measured one arm — T=0.7, eight draws, one run per cell. Every
question below is one that arm could not answer, and each was chosen against
the campaign's own rows rather than in the abstract.

## B1 — is t20 a broken task or a hard one?

Three tasks (t06, t07, t20) never passed on any model, any draw, either host.
Reading their acceptance against their contracts found a real defect in exactly
one: **t20's contract declares "Whether a repeated key should win or throw is
not stated" while its `accept.mjs` asserts `"a repeated key: last wins"`.** A
worker that stopped where the contract told it to was scored as failing.

`tools/breadth/tasks/d1r/t20` states the rule the acceptance already demanded,
keeping `accept.mjs` and `reference.ts` byte-identical — the repair moves the
contract to meet the test, never the test to meet the workers, and a test in
`tests/test_breadth_rig.py` enforces that.

**Result: the repair changed nothing.** 0 of 36 draws before, 0 of 36 after,
across all four srv1 models, with t06 and t07 run unchanged as controls and
also at 0 of 36. The defect is real and worth keeping repaired; it explains
none of the failures. The floor fails t20 on ordinary bugs — 15 of 36 crashed
before an assertion ran (`Assignment to constant variable`, `Cannot read
properties of undefined`), and the 11 assertion failures were spread over six
different assertions. The campaign's coverage ceilings stand as measured.

d1's own t20 is deliberately **not** repaired: changing its digest refuses a
resume to every existing run directory. That repair follows separately.

## B2/B3/B4 — the temperature axis, and where breadth stops paying

T=0.7 is DEC-6's inherited operating point; nothing had ever measured it.
`--sampled-temperature` makes it an input, and it is part of `run.json`'s
identity, so a directory measured at one temperature refuses another.

**Three runs per cell**, srv1, d1, 20 tasks, coverage as mean [min-max]:

| model | T | k=1 | k=3 | k=5 | k=8 | per-draw |
|---|--:|---|---|---|---|--:|
| qwen2.5-coder:1.5b | 0.7 | 6.0 [6–6] | 8.7 [8–10] | 9.3 [8–10] | **10.0 [10–10]** | 6.83 |
| qwen2.5-coder:1.5b | 1.0 | 6.0 [5–8] | 9.3 [9–10] | 10.0 [9–11] | **12.3 [11–14]** | 5.58 |
| qwen2.5-coder:3b | 0.7 | 9.3 [8–10] | 14.0 [13–15] | 14.7 [14–16] | 15.3 [15–16] | 10.17 |
| qwen2.5-coder:3b | 1.0 | 9.0 [8–10] | 13.7 [12–15] | 14.3 [13–15] | 14.7 [13–16] | 8.96 |
| llama3.2:3b | 0.7 | 6.3 [6–7] | 9.0 [8–11] | 10.0 [9–11] | 11.0 [10–12] | 6.25 |
| llama3.2:3b | 1.0 | 3.0 [2–4] | 8.7 [8–10] | 9.3 [9–10] | 11.0 [11–11] | 5.08 |
| qwen2.5-coder:7b | 0.7 | 13.3 [13–14] | 15.3 [14–16] | 16.3 [16–17] | 16.7 [16–17] | 13.62 |
| qwen2.5-coder:7b | 1.0 | 13.3 [13–14] | 15.0 [15–15] | 16.0 [15–17] | 16.3 [16–17] | 13.38 |

**Temperature is not a general lever.** Only `qwen2.5-coder:1.5b` gains, and
there the ranges are disjoint (10 in all three cold runs, 11–14 across three
hot ones). Every other model is flat or slightly worse with fully overlapping
ranges. Single runs had shown a gain on the 3b as well; the repeats are what
caught that as noise, and that correction is the main methodological result of
this batch.

Per-draw quality falls with temperature in **every** cell. That is the
consistent effect; coverage gain is the exception, not the rule. llama3.2:3b at
T=1.0 is the clearest case: a single hot draw collapses to 3.0 of 20 against
6.3 cold, and eight draws only claw back to the same 11.0 the cold arm reached.

**Single-run arms**, kept separate because they are single runs: T=0.3 across
all four srv1 models was flat-to-worse than 0.7 at k=8 (1.5b 10, 3b 13,
llama 11, 7b 15). On srv2, T=1.0 against the campaign's 0.7: 7b 16 vs 17,
yi-coder:9b 18 vs 16, qwen2.5-coder:14b 19 vs 17. Two mid-ladder models gaining
2 tasks each is exactly the size of the noise measured on srv1, so no rule
about model size survives this — which is itself the finding.

**T=1.3 is past the peak and fails a new way.** Worse than 1.0 at every draw
budget on both small models, and 7 of 20 tasks lose a draw to a reply the
parser refuses (against 0–2 lower down). Past the peak you do not get worse
code, you get output that is not code.

**Breadth plateaus by about the fifth draw.** A K=16 arm added nothing between
draw 6 and draw 16 on the 1.5b. Pooled over every srv1 cell, breadth is worth
**+3 to +8 tasks of 20** from one draw to eight — larger than any temperature
effect measured here.

## B5 — what breadth is worth when the checker is weaker than ours

Breadth moves the burden from the model to the checker: one draw and the model
must be right, eight and the check must spot which one is. Our `accept.mjs`
files pin every requirement and the reference passes them. Real suites do not,
and [#132](https://github.com/AdarGit008/mcgyvr/issues/132) records that we do
not know how often a runnable check is declared at all.

`selectivity.py` thins each acceptance to a fraction of its assertions
(keeping all setup, so the file still runs), re-selects from candidates already
on disk — **no worker dispatched** — and judges the winner by the full file.
Selection is production's: the first draw that passes the *weak* checker wins.

Pooled over **30 sweeps**; the full-strength re-run reproduced **4751 of 4751**
original verdicts before any weakened cell was read:

| checker | breadth gain k=1→k=8 | wrong accepted @k=1 | @k=8 | precision @k=8 |
|---|--:|--:|--:|--:|
| 25% of assertions | +1.9 | 4.4 | 7.3 | 57% |
| 50% | +2.6 | 2.5 | 4.4 | 70% |
| 75% | +3.5 | 1.6 | 3.4 | 77% |
| 100% | **+5.0** | 0.0 | 0.0 | 100% |

Breadth's benefit decays with the checker while wrong answers accepted rise
with k at every weakened strength — the predicted mechanism, measured rather
than argued. At a quarter strength you gain 1.9 correct answers and accept 7.3
wrong ones.

The cliff is between a quarter and a half, not between complete and
incomplete: three quarters of a good suite keeps 70% of the benefit. So the
requirement on a selector is "covers most of what the contract asks", not
"perfect".

## Limits

- srv1's four models, one host, one serving stack, the d1 JS/TS set. srv2 arms
  are single runs and labelled as such above.
- Thinning keeps the **first** N assertions in the author's order, so weak
  checkers here test the obvious cases and skip the corners. Real thin suites
  are thin in messier ways, and a suite that is thorough about the wrong things
  would behave differently.
- "Wrong" means "the full `accept.mjs` rejects it", which is itself a proxy for
  correct — a candidate passing the full file could still be wrong in a way no
  assertion covers.
- Every number is acceptance-passing, not `Gate.run`.
