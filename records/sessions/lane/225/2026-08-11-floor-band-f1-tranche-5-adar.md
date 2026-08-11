# Floor band `f1`, tranche 5 — the brief is spent unchanged (lane/225)

Date: 2026-08-11 (evening)
Issue: #225 (Phase 4). Brief: `2026-08-11-floor-band-f1-brief.md`, **unchanged**.
Governing records: ADR-0021 (as amended twice), ADR-0022, ADR-0023, ADR-0024.

## What the stop condition told us to do

`f1`'s first 40 problems read **45.0%** on `qwen2.5-coder:1.5b` — inside the
pre-registered 30–50% window. The brief names exactly one consequence for that
read:

> If the 1.5B reads **inside 30–50%** on the f1 bench half: the shape is right,
> and the remaining tranches toward ~400 are authored to this brief unchanged.

So this tranche changes nothing. Same behaviour budget, same shape targets, same
composition rule, same brief document. The only thing that moved is the count.

## The amendment that preceded it

The owner settled a question ADR-0021 left open, and it is recorded there rather
than here (ADR-0021, *Amendment — 2026-08-11: overlap may be total, and the aim
is met per model*):

- The **400 stays intact per model**. No relief from the count.
- Overlap between two models' sets may be **full or partial**, no upper bound.
- The binding constraint is per model: each model's 400 must meet **its own**
  30–50% aim.

The consequence recorded there and worth repeating: overlap is settled by
**measurement, never assumption**. A problem earns its second slot by reading
in-band twice. A second model's authoring bill is its *shortfall* — the problems
it ceilings on — and that bill is unknowable until it is swept against what
exists. The floor unit's 400 is still completed first (ADR-0021 clause 4).

## What was authored

**b268–b307: 40 paired problems, 40/40 ADMIT on the first pass.**

Composition, matching tranche 4's realized mix:

| | count | share |
|---|---:|---:|
| `function_implementation` | 30 | 75% |
| `bug_fix` | 10 | 25% |
| `multi_symbol` | 11 | 27.5% (#126 wants ≥ 25%) |
| carrying one error path | 7 | 18% |

Shapes: 10 numeric, 12 string, 9 iteration, 9 data_structure. No
`error_handling` primary — a band capped at one error path cannot honestly carry
it.

Realized shape against the brief's declared targets — **every median inside its
band**:

| dial | target | tranche 5 median (range) |
|---|---:|---:|
| spec prose words | 40–70 | **49** (36–70) |
| ts reference lines | 8–14 | **11** (4–24) |
| py reference lines | 6–11 | **7** (3–13) |
| asserts per arm | 5–8 | **6** (6–8) |
| problems with an error path | ~19% | **18%** |

The ranges run wider than the medians at both ends and that is expected: a
`bug_fix` states its defect in fewer words and its reference is often three
lines, while `wrapWords` and `rampPlan` are genuinely 20-line functions. The
brief targets a distribution, and the distribution landed.

## How it was written

Prose, references and assertions are hand-written, every word. `tools/bench/emit.py`
— committed in `83ad683f` precisely so this tranche would not depend on a
scratchpad — wrote the file shapes: the folded `task:` scalar, the
`demonstration`-versus-`acceptance` split a `bug_fix` turns on, and the ts arm's
`meta.json` sidecar. That division held: 40/40 admitted first pass with no gate
rejection attributable to file shape.

**One rejection, and it was arithmetic.** `b291-climb-gain` asserted
`climbGain([1, 4, 9]) === 11`; the rises are 3 and 5, so it is 8. Both arms
failed identically and the gate caught it before the manifest saw it — which is
the gate's whole job, and worth recording as evidence that the self-test arm
works rather than as an embarrassment.

## Two design traps avoided, recorded because they will recur

**1. A rounding rule that is not the same rule in both languages.** The first
draft of `b298` was "the mean, with a half rounding up". Python's `round()` is
banker's rounding — `round(4.5)` is `4` — while JavaScript's `Math.round(4.5)`
is `5`. An idiomatic solution would have passed ts and failed py *on the same
problem*, which is precisely the class of defect the `ValueError`/`Error` checker
fix was about (see `2026-08-11-floor-unit-and-checker-parity-adar.md`). The
problem was replaced with `b298-price-vat`, whose `//` and `Math.floor` agree.
**Rule: before pairing a numeric problem, check that both languages' built-ins
answer the boundary the same way.**

**2. Domain collision inside the band.** Roughly a third of the first draft was
discarded against the 40 problems already in `f1` — a cyclic-next (b241), a
mask-the-tail (b237), a round-robin deal (b250), a longest-run (b251), a clamp
(b254), an interval merge (b266), a title-case (b242). The Jaccard screen at
0.55 is the backstop, not the method; reading the existing prose first is the
method, and it is cheaper than a gate rejection.

## State after this tranche

- **Bench: 300 admitted**, `f1` at **80** (48 bench / 32 reserve).
- The 48/32 split is the pre-declared salted hash doing what a blind rule does
  at n=80. It is not chosen and is not corrected.
- The 1.5B's 400: **80 down, 320 to go**, at 40 a tranche.
- `admit.py --verify` clean.

## Next

The stop condition is unchanged and still governs: author the remaining tranches
to this brief **unchanged** toward ~400 for the floor unit, then relabel the 220
as the ladder's top, then Phase 5 (#224 re-read, PR). Nothing here re-opens the
band's design.

Two things deliberately **not** done, so they are not mistaken for oversights:

- **No sweep was run on this tranche.** A 40-problem read is a rate estimate the
  band does not need again; `f1`'s shape is settled and re-measuring every
  tranche would invite exactly the n=7 re-design error the brief exists to
  prevent. A sweep across the accumulated `f1` bench half is worth running when
  the count is large enough to narrow the interval meaningfully.
- **No upstream (3B) sweep.** It is now a step of the method under the
  amendment — it is the only way to learn the overlap — but ADR-0021 clause 4
  puts the floor unit's 400 first, and the owner's instruction was explicit:
  finish the 1.5B's 400 before moving on.
