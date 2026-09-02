---
record: session/1
lane: lane/266
agent: adar
started: 2026-08-14T09:50:00Z
---

# Session — lane/266 — 2026-08-14

## Did

Opened the lane and answered #266's first two acceptance items from the corpus
and the committed runs. The answer is stronger than the issue's own estimate and
it disqualifies both declared candidates outright.

**The eligibility count reproduces exactly.** Per arm: 198
`function_implementation` of which **34 carry `target_content`**, 59 `bug_fix`
(all carrying it), 257 total. Both arms identical in composition. `tools/bench/
eligibility.py` derives it rather than restating it, and
`tests/test_bench_eligibility.py` pins it so a corpus change that moves it fails
the build.

**The finding #266 did not have: the eligible set has no headroom.** The issue
priced the levers by expected discordance — *"34 cells expects m ≈ 2"* — which
assumes the eligible cells behave like the arm they sit in. They do not. Stock
pass rate by stratum, `Gate.run`-scored, from the committed null-a runs:

| stratum | n | 7B py | 7B ts | 1.5B py | 1.5B ts |
|---|---:|---:|---:|---:|---:|
| `bug_fix` | 59 | **55.9%** | **50.8%** | 20.3% | 16.9% |
| `function_implementation`, no scaffold | 164 | 20.1% | 11.0% | 5.5% | 13.4% |
| `function_implementation`, **scaffolded** | 34 | **2.9%** | **8.8%** | 5.9% | 2.9% |

The 34 cells the capacity levers can act on are the **hardest stratum on the
bench** — an order of magnitude below the arm they belong to. The reason is not
mysterious: a task carries a scaffold because it is multi-function, and those are
the ones a small worker fails.

**Why that settles it without an effect size.** A cell that passes under neither
condition is concordant whatever the lever does, so the count passing under
*either* is an arithmetic ceiling on `m`. Measured on the eligible set against
the committed `norule` pair, that ceiling is **1 (7B py), 4 (7B ts), 2 (1.5B py),
2 (1.5B ts)** — and both scaffold levers make the task *harder*, so the ablated
arm can only lose cells. Against ADR-0019's `m >= 6` wall the contrast is
**undecidable by construction**, at any effect size, on either tier.

This is ADR-0026's consequence applied literally: *"a stratum with no headroom is
excluded, not reported as null. 'No effect where nothing passes' is absent
resolution, not absent effect."* Running `noscaffold` would have produced a
publishable-looking null that means nothing — the #133 failure mode, one layer
in.

**Where the headroom actually is, and the bind it creates.** `bug_fix` reads
55.9% / 50.8% at the 7B — the one stratum with real room to move, and the only
one where a 7B is neither flooring nor ceilinging. `matrix.json` rules it
ineligible for both capacity levers for a sound reason (*its `target_content`
**is** the buggy file the task exists to fix*). So the material constraint and
the eligibility rule point in opposite directions: **the cells that can resolve
an effect are exactly the cells these levers may not touch.**

## Left open

- **#225's route choice is unchanged but better constrained.** The control must
  act on `bug_fix`, or on the 164 unscaffolded implementations (20.1% / 11.0% at
  the 7B), because those are the only strata with headroom. Neither capacity
  lever can reach either one. Recorded here; the argument still lands in #225 by
  its own rule.
- **#266's own arithmetic wants correcting in its body** — "expects m ≈ 2" reads
  as underpowered, which invites "then run more cells". The true statement is
  that no number of these cells helps, because the ceiling is set by headroom
  and not by n. Amendment, not a rewrite, per #234's convention.
- **This makes #222's case sharper.** Authoring material is no longer one of
  several answers to a power shortfall; it is the only answer for a scaffold
  manipulation, and the specification is now concrete: scaffolded tasks a floor
  unit can actually pass.
- The round is untouched — `tools/bench/eligibility.py` is not in
  `product.py`'s `SURFACE`, verified: `product_sha256` still `ed508e61`,
  56 files, tree matches.

next: amend #266 with the headroom finding and #225 with the constraint it puts
on the route, then take the route choice to the owner
