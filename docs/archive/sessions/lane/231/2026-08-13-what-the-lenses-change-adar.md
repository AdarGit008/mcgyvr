---
record: session/6
lane: 231
agent: adar
started: 2026-08-13
---

## Did

**ADR-0026 — four lenses.** Owner's formulation, adopted verbatim as the review
standard. **The ADR itself moved to `lane/249` (#249, PR #250)** — it is doctrine
rather than commissioning, it amends two ADRs unrelated to this lane's checks,
and inside a 103k-line measurement PR nobody would read it. What stays here is
what the lenses re-rank for *this* lane: record what cannot be reconstructed; mutants as a principle and not a
roadmap; a record states the property rather than a claim about it; plan which
axes are cheap to vary rather than planning experiments.

The ADR carries the evidence table and the consequences. What belongs here is
what the lenses **re-rank**, because a doctrine that changes no priority is a
claim rather than a property — which is lens 3 applied to itself.

### Applied to the day's open work

| lens | what it promotes | what it demotes |
|---|---|---|
| 1 record the unrecoverable | the three digests (bar, model, condition) | storing derived rates; `summary.md`'s numbers are recomputable |
| 2 mutants | generalising the condition matrix into a screening sweep on the **61 responsive cells** | funding each lever (#198, #17, #119, #221) as its own experiment |
| 3 state the property | a sweep for assertions-of-sameness in comments | ADR-0025's "the two move together", already withdrawn |
| 4 price the axes | the language registry (~17 files, three hardcoded adapter tuples) | any measurement taken before language is cheap to vary |

### Two instances of lens 3 found by one grep

`tools/bench/score.py:55` asserts its `ACCEPTANCE_TIMEOUT_S` "matches
`tools/bundle/measure.py`'s" — 120.0 against 30.0, **false by 4x**, and
`tools/bench/admit.py:62`'s claim that admission rehearses bench scoring rests on
it. `src/mcgyvr/orchestrator/repo.py:46` asserts its `_EMPTY_TREE` is "the same
sentinel the gate uses" — **true today**, duplicated, enforced by nothing.

One already false, one latent, same shape. That is the lens working mechanically
rather than by re-reading, which is the property this day was short of.

### The homogeneity finding that made lens-shaped review necessary

Separating the two languages is not sufficient, and this bench says so:

| slice | n | stock → norule |
|---|---:|---|
| ts `function_implementation` | 198 | 23 → 2 (**−10.6pp**) |
| ts `bug_fix` | 59 | 10 → 9 (−1.7pp) |
| py `bug_fix` | 59 | 12 → 10 (−3.4pp) |
| ts band `f1` | 149 | 32 → 8 (**−16.1pp**) |
| ts bands `g0`–`g0b` | 63 | 1 → 3 (~0pp, and **1 of 23 ever passes**) |

Task type moves the effect **6x inside one language**, and on `bug_fix` the two
languages agree — so the language effect is concentrated in
`function_implementation` and a per-language report would have published ts
−8.6pp while hiding that. The g-bands are not evidence of immunity: nothing
passes there, so nothing can move.

`steering_band` and `shape` have been in `meta.json` since authoring and are read
by no analysis tool. Lens 1's corollary, exactly: the capture was never the gap.

## Left open

- **The scope matcher fails open** and is unowned. `Scope.of(('src/**/*.py',),
  ('**/[Ss]ecret*.py',)).forbidden('src/Secrets.py')` is `False` and `permits` is
  `True`; the same for a case difference. A contract's `forbid` list is how it
  says *never touch this*, and it grants full write authorization instead. Not a
  measurement defect, shipped, and it outranks everything else here.
- **Check 2's verdict**, unchanged, and its pooled −5.8pp is now clearly the wrong
  summary of it.
- **Checks 3 and 5** have not started.
- **The bar/model/condition digests** are approved and not yet built.
- **88% of cells are frozen** (453 of 514 never pass under any condition). Zero
  rig time to quantify properly, and it bounds what #224 and #225 can resolve.
- **Nothing in this session's verification is committed** as a measurement — the
  66-vs-328 rule counts, the vocabulary digests and the frozen-cell count exist
  in a conversation and in these records, not in `records/measurements/`.

next: build the three digests as one change — bar, model and condition — because
each is the same defect in a different field, and the model half was proven
obtainable from the serving endpoint today.
