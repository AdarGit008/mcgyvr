# Floor band `f1`, tranche 6 — the screens earn their keep (lane/225)

Date: 2026-08-11 (evening)
Issue: #225 (Phase 4). Brief: `2026-08-11-floor-band-f1-brief.md`, **unchanged**.

## What was authored

**b308–b347: 40 paired problems.** Same behaviour budget, same shape targets,
same brief document — the stop condition for a read inside 30–50% names exactly
one action and this is it.

| | count | share |
|---|---:|---:|
| `function_implementation` | 30 | 75% |
| `bug_fix` | 10 | 25% |
| `multi_symbol` | 11 | 27.5% |
| carrying one error path | 7 | 18% |

Shapes: 10 numeric, 11 string, 8 iteration, 11 data_structure — chosen to pull
the band's cumulative spread toward even, since numeric led at 25 of the first 80.

Realized shape, every median inside the brief's declared band:

| dial | target | median (range) |
|---|---:|---:|
| spec prose words | 40–70 | **45** (33–59) |
| ts reference lines | 8–14 | **11** (4–23) |
| py reference lines | 6–11 | **7** (3–16) |
| asserts per arm | 5–8 | **6** (6–8) |

## The screens caught two, and they were the right two

Tranche 5 added the emitter's two screens after being bitten by both traps. This
is the first tranche authored through them, and they **refused two problems
before either reached the gate**:

- **`b310-set-order`** (dedupe a list keeping first appearance) scored **0.89**
  against `b283-dupe-keys` (report the entries that repeat). Different questions,
  one reference: a `seen` set, a loop, a conditional append. I drafted it knowing
  it was adjacent and let the screen rule; it ruled against. Replaced with
  `b310-pair-keys`.
- **`b340-first-word`** scored **0.73** against `b278-initials-of` — both split a
  line on whitespace, drop the empties, guard the empty case and index. Replaced
  with `b340-case-flip`.

Neither would have been caught by the gate's 0.55 prose Jaccard: "the first word
of a line" and "the initials of a name" share almost no vocabulary. That is the
whole reason the sibling screen reads the reference's shape instead.

The divergence screen also changed how two problems were *written* rather than
whether they survived. `b321-pass-check` and `b329-mix-case` both need "is this a
letter"; the obvious py answer is `str.isalpha()`, which is Unicode-aware, while
the ts twin would have been an ASCII character class. Both were written with an
explicit ASCII alphabet in the py arm so the two arms agree by construction. The
screen would only have warned — it is latent, not fatal — but a warning read at
authoring time is cheaper than an arm asymmetry discovered in a sweep.

Fourteen further sibling warnings landed in the 0.55–0.62 band and were read and
kept: a loop that accumulates into a list is not a problem, it is a language.

## State

- **Bench: 338 admitted.** `f1` at **120** (72 bench / 48 reserve).
- The 1.5B's 400: **120 down, 280 to go.**
- `admit.py --verify` clean, `emit.py --audit` still 0 refusals.

## Next

Unchanged: keep authoring to this brief, relabel the 220 as the ladder's top,
then Phase 5. Still deliberately not done, and still not oversights: no per-tranche
sweep (re-measuring each time invites the n=7 re-design error) and no upstream
sweep until the floor unit's 400 is complete.
