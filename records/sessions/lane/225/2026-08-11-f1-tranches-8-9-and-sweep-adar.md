# Tranches 8 and 9, and the sweep at 240 (lane/225)

Date: 2026-08-11 (evening)
Issue: #225 (Phase 4). Brief: `2026-08-11-floor-band-f1-brief.md`, **unchanged**.
Run: `records/measurements/bench-calibration-15b-f1-240-2026-08-11/`

## What was authored

**b388–b427 and b428–b467: 80 paired problems**, each tranche 30
`function_implementation` / 10 `bug_fix`, 11 `multi_symbol`, 7 error paths.
**Bench: 458 admitted.** `f1` at **240** (135 bench / 105 reserve).

The sibling screen refused **nine** drafts across the two tranches — three in
tranche 8, six in tranche 9 — each replaced before admission, so the gate saw 40
per tranche and admitted 40. One further problem, `b462-top-char`, was rejected
by the gate on its own self-test: the reference tracked the first character to
*reach* the highest count rather than the first to *appear*, which is a different
tie rule from the one the prose states. **The reference was corrected, not the
assertion** — the checker was right and the reference was wrong.

Refusals by tranche now run **0, 2, 4, 3, 6**. The space of distinct
small-function shapes is visibly thinning.

## The sweep: the band holds, but tranche 8 does not

`qwen2.5-coder:1.5b` on srv2, greedy, cap 2048, stock, build 0.32.5 — the same
build as both earlier reads. 270 cells in six minutes.

| set | pass | rate | 95% Wilson |
|---|---:|---:|---:|
| **all f1 bench (240)** | **105/270** | **38.9%** | **33.3–44.8%** |
| bench-ts | 50/135 | 37.0% | 29.4–45.4% |
| bench-py | 55/135 | 40.7% | 32.8–49.2% |

| tranche | pass | rate | 95% Wilson |
|---|---:|---:|---:|
| 4 | 18/40 | 45.0% | 30.7–60.2% |
| 5 | 18/56 | 32.1% | 21.4–45.2% |
| 6 | 24/48 | 50.0% | 36.4–63.6% |
| 7 | 21/46 | 45.7% | 32.2–59.8% |
| **8** | **10/44** | **22.7%** | **12.8–37.0%** |
| 9 | 14/36 | 38.9% | 24.8–55.1% |

**Tranches 4–7 reproduce exactly: 81/190 = 42.6%**, the same figure to the cell
as the sweep at 160. That is the second free determinism check and it means the
comparison below is between measurements on one footing, not two.

**Tranche 8 reads 22.7% — the only tranche below the band's floor.** Against the
tranches 4–7 pool it is z = 2.44, **p = 0.015 uncorrected**. That is the first
drift signal in this campaign that is a measurement rather than a proxy.

### The honest caveat

**p = 0.015 is uncorrected and the comparison was chosen after seeing the
numbers.** Six tranches were examined; Bonferroni puts it at **p = 0.088**. On
that basis this is *suggestive and not established*. A pre-registered test would
have named tranche 8 before the sweep, and nothing did.

## What it probably is, and why it was foreseeable

The mechanism is the one the tranche-7 record flagged as a cost signal, now
showing up as difficulty rather than as authoring effort. As the distinct-shape
space thins, staying distinct pushes the material toward more exotic domains.
Tranche 8 is where that pressure first bit hard: it carries clock arithmetic
(`b388-time-gap`, `b405-day-next`, `b416-time-in` with its wrap past midnight),
grid indexing, path normalisation and validation. Those are harder than "total a
list" at the *same* behaviour count, because the behaviours themselves are less
familiar.

Composition did not drift — tranche 8 holds the same 30/10 split, the same 11
`multi_symbol` and the same 7 error paths as tranches 5 through 7. So this is not
a budget breach. It is the budget meaning something different in an unfamiliar
domain.

## Where this leaves the campaign

- **The band as a whole is in aim: 38.9%, interval 33.3–44.8%**, and the brief's
  stop conditions key on the band's read, not on a tranche's. Nothing in the
  pre-registered rules fires.
- The pooled figure has moved **42.6% → 38.9%** as 80 problems were added, and
  the interval's lower bound is now **33.3%**, closer to the floor than it has
  ever been. Two more tranches at tranche 8's rate would take the pool under 30%.
- **This is the owner's call, and it is a real one.** The choices are to carry on
  unchanged and let the pool absorb it; to keep the brief but deliberately hold
  the behaviour count at the low end of 2–4 when authoring in an unfamiliar
  domain; or to treat the thinning as evidence that 400 per model is not
  reachable at this shape without either repeating shapes or drifting harder.

**Hygiene across all 270 cells: 0 parse refusals, 0 dispatch errors, 0
non-complete stop reasons.**
