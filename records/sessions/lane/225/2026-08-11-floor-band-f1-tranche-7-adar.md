# Floor band `f1`, tranche 7 (lane/225)

Date: 2026-08-11 (evening)
Issue: #225 (Phase 4). Brief: `2026-08-11-floor-band-f1-brief.md`, **unchanged**.

## What was authored

**b348–b387: 40 paired problems**, 30 `function_implementation` / 10 `bug_fix`,
11 `multi_symbol` (27.5%), 7 carrying one error path (18%). Shapes: 5 numeric,
9 string, 11 iteration, 15 data_structure — weighted toward the two the band was
thinnest in.

| dial | target | median (range) |
|---|---:|---:|
| spec prose words | 40–70 | **41** (31–60) |
| ts reference lines | 8–14 | **12** (6–23) |
| py reference lines | 6–11 | **7.5** (3–19) |
| asserts per arm | 5–8 | **6** (6–7) |

## Two things to watch

**1. Prose is drifting shorter: 49 → 45 → 41 words across tranches 5, 6, 7.**
Still inside the 40–70 band, but three tranches in one direction is a trend and
not noise, and the next one would leave the band. The cause is visible in the
material: later problems lean on shorter specifications because the obvious
long-form domains were used first. **The brief is not to be re-aimed — but the
next tranche should be authored watching this number, and if it lands below 40
that is a shape change to report, not to absorb.**

**2. The screen's refusal rate is rising: 0, 2, 4 across the three tranches it
has run on.** Four drafts were refused here and replaced before admission:

| draft | scored | against |
|---|---:|---|
| `b310` (dedupe keeping first) | 0.89 | `b283-dupe-keys` |
| `b365` (carry a running total into gaps) | 0.84 | `b306-fill-gaps` |
| `b379` (deepest bracket nesting) | 0.90 | `b280-step-back` |
| `b386` (drop the queue's front) | 0.78 | `b301-tick-drop` |

All four are honest catches: track-a-max, sentinel-fill, and one-line-slice are
shapes the band already owns. The rate rising with the band's size is exactly
what should happen — at 160 problems the space of distinct small-function shapes
is genuinely thinning, and the screen is measuring that rather than misfiring.
It is worth watching as a **cost signal for the remaining 240**, not as a defect.

Sixteen further sibling warnings in the 0.55–0.62 band were read and kept.

## State

- **Bench: 378 admitted.** `f1` at **160** (95 bench / 65 reserve).
- The 1.5B's 400: **160 down, 240 to go.**
- `admit.py --verify` clean.
