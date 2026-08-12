# Floor band `f1` — tranche 10 (b468–b507)

Forty problems authored to
`2026-08-11-floor-band-f1-brief.md` **unchanged**. The brief was not re-aimed,
and nothing in this session touched its target: the band still aims at 30–50%
on `qwen2.5-coder:1.5b`, and the responsiveness run of 2026-08-11 gave the
grounds for carrying on rather than a reason to change the design.

`f1` now stands at **280 of 400** — 149 bench, 131 reserve. **120 remain.**
Bench admitted overall: **498**. `admit.py --verify` clean, `emit.py --audit` at
**0 refusals / 191 warnings**.

## Composition, against what the brief asks

| | brief | tranche 10 |
|---|---|---|
| task type | 30 `function_implementation` / 10 `bug_fix` | **30 / 10** |
| `multi_symbol` | ≥ 25% (11 of 40) | **11 (27.5%)** |
| error paths | ~7 (18%) | **8 (20%)** |
| shape | spread over the four | **10 / 10 / 10 / 10** |

The one departure is the error-path count: eight rather than seven. It arrived
because `b499` needed a cycle guard to be safe to run at all — a chain-following
problem without one can loop forever and hang the gate — and the honest way to
write that guard was as a rejection. Two percentage points, recorded rather than
smoothed over.

## What the sibling screen did, and the one thing it did not

**Nine drafts of forty were refused and redrafted.** That is above the 3–6 the
brief expects, and it is the thinning ADR-0023's record has been tracking:
refusals per tranche now run **0, 2, 4, 3, 6, 9**.

Every refusal was correct on inspection, and several were not near-misses but
the same problem over again:

| draft | scored | against | what it actually was |
|---|---:|---|---|
| `b471-rise-run` | **1.00** | `b362-up-runs` | the same function, to the line |
| `b496-trim-lines` | 0.72 | `b309-line-trim` | the same function |
| `b499-turn-grid` | 0.78 | `b324-grid-flip` | the same transpose |
| `b477-zigzag-take` | 0.78 | `b443-fold-ends` | the same two-pointer walk |
| `b499-odd-ones` | 0.77 | `b373-set-minus` | difference, one loop longer |
| `b500-lace-runs` | 0.73 | `b363-alternate-merge` | the same interleave |
| `b488-drain-tank` | 0.90 | `b313-move-stock` | that, with a cap added |
| `b492-turn-tally` | 0.72 | `b248-hop-chain` | the same pairwise walk |
| `b485-cut-late` | 0.71 | `b365-limit-run` | the same truncate-at-first |

A tenth refusal was **`b485-loop-out` at 0.70 against `b474-bin-rotate`, which
this same tranche had written twenty minutes earlier** — the modulo-index loop
twice. Worth recording because it says the thinning is not only against the
existing corpus but within a single sitting's own output.

### The screen missed one, and it was caught by reading

**`b499-cut-at` scored 0.68 — under the 0.70 refusal — and was the same problem
as `b398-split-at`.** Not a near neighbour: the same signature, the same
find-the-marker-then-slice body, and prose that says what b398's prose says.
It was emitted, then **withdrawn by hand** after reading the sibling the warning
named. It was never admitted, never pinned and never measured, so no id carries
a history and `retired.json` is untouched; the id `b499` was reused for a
different problem within the same session, which is only legitimate because
nothing had ever been recorded against `b499-cut-at`.

This is the concrete case for the rule the workflow already states — *the screen
is the backstop, not the method*. At 0.68 the screen warns and keeps going; a
reader who does not open the named sibling keeps a duplicate. Five other
problems in this tranche warned in the 0.57–0.69 band and were each read against
the sibling named before being kept:

- `b468-bracket-depth` 0.68 vs `b280-step-back` — kept: adds two rejections the
  other has no analogue for, and rejects malformed input rather than scoring it.
- `b497-fold-rests` 0.69 vs `b306-fill-gaps` — kept: collapses a stretch to one
  entry where the other substitutes one-for-one, so the output length differs.
- `b500-pair-off` 0.68 vs `b252-swipe-dedupe` — kept: the pair *cascades*, so
  `["a","b","b","a"]` empties, where dedupe returns `["a","b","a"]`.
- `b482-window-max` 0.65 vs `b317-mean-window` — kept, and it is the weakest of
  the five: the same nested windowing with a different aggregate.
- `b475-crate-stack` 0.67 vs `b423-scan-tally` — kept: returns the kept items and
  stops early, where the other returns a running total over everything.

## The two authoring traps, and how they were held off

Both are enforced by the emitter, and neither fired this tranche, because the
material was written to avoid them rather than to be caught by them:

- **No rounding rule the two languages disagree on.** Every money-shaped problem
  works in whole cents (`b472`, `b484`, `b503`), and every division that has to
  drop a fraction uses `Math.floor` against `//` on non-negative values only
  (`b470`, `b481`, `b488`, `b489`, `b492`).
- **No character-class call that diverges.** Where a problem needs to know
  whether a character is a letter or a figure, it tests membership in a spelled
  constant (`b491`, `b502`) rather than `.isalpha()` against a TypeScript
  regular expression.

## What this tranche does not claim

No sweep was run. **This session produced material, not a measurement**, and the
band's read is still the 240-problem figure of 2026-08-11: pooled 38.9%, Wilson
33.3–44.8%. Whether tranche 10 sits in band is unknown until it is dispatched,
and the pre-registered rules in the brief key on that read, not on this one's
composition.

The obvious next measurement is a sweep of the f1 bench half at 149, which would
also give the tranche-10 rate and a fifth free determinism check against the
149-cell overlap with the last run.
