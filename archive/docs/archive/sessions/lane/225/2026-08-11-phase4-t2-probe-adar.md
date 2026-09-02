---
record: session/2
lane: lane/225
agent: adar
started: 2026-08-11T12:00:00Z
---

# Session — lane/225 — 2026-08-11 (Phase 4, tranche 2: the isolation probe)

## Did

The campaign paused to verify its ground floor, and the probe that was
supposed to answer *what makes these problems hard* did not answer it.

**The question, and why it was asked.** Two consecutive re-aims had
undershot the 30–50% aim (the pilot's g1 landed at d3-class; tranche 1's g0
read 4.3% ts / 21.7% py). The owner's instruction: do not drop the aim, and
do not spend more campaign volume until the floor is understood — *being
able to tell what actually drives difficulty is essential to mcgyvr*
(decomposition, contracts, orchestrator all bet on it). The owner also
caught the design flaw in the first proposal: "about half the size, with
fewer edge cases" moves two knobs at once and cannot attribute either.

**The probe as built.** Two cells of 40, each moving ONE knob against g0's
matching subset, everything else held; all 80 `function_implementation` +
`single_definition` so no task-type mix confound (bug_fix passes ~2×).
`g0a` halves reference size at g0's checker load; `g0b` halves checker load
at g0's size. 80/80 through the joint gate, pinned 41 bench / 39 reserve,
1225 tests green, committed before any sweep (`e401fc7b`).

**The result: no contrast resolves, and the arms contradict each other.**

| contrast | ts | py |
|---|---|---|
| baseline (g0 fn_impl/single) | 1/16 = 6.2% | 3/16 = 18.8% |
| g0a — smaller files | 6/23 = 26.1% (+19.8pp, p = 0.206) | 4/23 = 17.4% (−1.4pp, p = 1.000) |
| g0b — lighter checkers | 3/18 = 16.7% (+10.4pp, p = 0.604) | 2/18 = 11.1% (−7.6pp, p = 0.648) |

Per problem, scoring both arms (which respects the arms' pairing) mean arms
solved: baseline 0.25, g0a 0.43, g0b 0.28; g0a is the only cell containing
problems solved in *both* arms (2 of 23). Every ts contrast and the
per-problem score point the same way — smaller references are easier — and
the py arm contradicts it flatly. The measurement itself is sound: 0 of 218
arm-draws overran the cap (max completion 740 of 2048), 0 parse errors.

## Learned

**The greedy sweep is deterministic.** Every pre-existing band reproduced
its tranche-1 rate *exactly* (g0 1/23 ts, 5/23 py; g1 2/13, 2/13; g2 2/14,
1/14; g3 0/12; g4 0/6, 1/6). Cross-sweep comparison is therefore
legitimate, and a re-sweep costs nothing but time — worth knowing before
designing any future contrast.

**Why the probe could not resolve it: the design is unpaired.** The cells
are *different problems* from the baseline, so every comparison spends
power like two independent samples. At 80% power, α .05: the ts-observed
6.2% → 26.1% move needs ~52 measured per group (~105 authored after the
50% split); a 10pp move off a 20% base needs ~293 measured (~586 authored);
a 15pp move ~138 (~276). The probe measured 16–23 per group. **This is
ADR-0019's wall wearing a new costume** — the project already refuses
unpaired 20-problem contrasts as undecidable, and authoring a knob study as
separate cohorts re-buys that problem at generation prices. The mistake was
mine and it was a design mistake, not a sampling accident.

**The manipulation was also weaker than designed**, recorded in
`strata.json` rather than glossed: realized medians (ts lines / asserts)
baseline 22 / 9, g0a 17 / 11, g0b 26 / 7. The baseline subset sat at the
floor of g0's own size band, so g0a is ~23% smaller (not half) *and*
carries slightly more asserts, while g0b is ~18% larger with ~22% fewer
asserts. g0a's confound runs against its own hypothesis (conservative);
g0b's runs with it (optimistic).

**Two readings survive and this measurement cannot separate them:** size
drives difficulty and the py arm is too noisy at n = 23 to show it, or the
ts arm carries a size-dependent penalty the py arm does not — a hypothesis
worth a condition arm, since TypeScript annotations add failure surface per
line and the py arm's baseline is already 3× the ts arm's.

**The spend limit fired twice**, killing 24 agent-runs across two
workflows. The pause doctrine held exactly as written: b155, b176–b180 and
b186 were lost mid-write → retired, never reused, rows re-issued as
b221–b227 with the retirement recorded in the brief's addendum; 14 orphaned
problems were salvaged by gating them directly rather than re-authoring.
Loss rate 7 of ~130 attempted (5.4%, against the ~2.4% baseline — higher
because agents died mid-batch, not mid-write).

## Decided

- Report the probe as unresolved rather than reading a direction as an
  answer. The ts arm's +19.8pp is the kind of number that becomes a project
  fact if stated without its p = 0.206.
- Keep both cells in the bench under their pinned ids. They are steering
  bands, **not strata** — not band points of the ladder, and #224 must not
  read them as one. `strata.json` block 3 says so.
- Do not re-run the probe bigger. ~105–586 authored problems per group to
  settle one knob is the wrong instrument for the question.

## Next

**Ask the driver question paired, as condition arms on one problem set** —
which is exactly #113's condition matrix, governed by ADR-0019's power
tables (discordant pairs, m ≥ 6). Two arms are available at a fraction of
the cost, on material the bench already holds:

1. **Scaffold on/off** — render the same problem with and without its
   `target_content`, varying how much code must be produced while holding
   the problem, the checker and the prose identical. A paired size
   manipulation; the bench already carries scaffolded problems in every
   band.
2. **Strict vs lenient grading** — re-score the *same saved completions*
   against a second, lighter checker per problem. Isolates checker load at
   **zero model cost**: the candidates are already pinned under
   `records/measurements/`.

Neither needs a new cohort, and both answer the question the way the
project's own doctrine says questions get answered here.

The campaign stays paused on the owner's instruction. The aim is not met
and not dropped: g0a is the closest anything has come (ts 26.1%, 95% CI
13–46%; py 17.4%; 35% of its problems solved in at least one arm), and its
size profile — median ts 17 lines, py 14 — is the best easy-band candidate
measured so far.
