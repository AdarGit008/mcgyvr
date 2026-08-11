---
record: session/2
lane: lane/225
agent: adar
started: 2026-08-11T13:40:00Z
---

# Session — lane/225 — 2026-08-11 (the scaffold ablation, read and landed)

## Did

Block 3's post-mortem said: ask the driver question **paired**, as condition
arms on one problem set. That was built and run in the preceding session; this
one read it, found two defects in how it had been recorded, fixed them, and
committed the result.

**The experiment.** Three renders of the *same* problem — `stock` (the
scaffold as production ships it), `planonly` (its comment lines, code
removed), `noscaffold` (no scaffold) — over 34 problems, both language arms,
8 draws per cell, on the 3B (srv1) and the 7B (srv2). 3,264 rows, complete,
0 cap overruns, 0 parse errors, 0 dispatch losses. The three-way split exists
because the two-way one was itself confounded: every scaffold carries a TODO
stating the approach, so `stock vs noscaffold` moves volume *and* recipe
together.

**The reading, on the pre-registered set of 27** (`strata.json` block 4 holds
it in full):

| contrast | 3B ts | 3B py | 7B ts | 7B py |
|---|---|---|---|---|
| stock rate | 10.2% | 9.7% | 30.6% | 25.9% |
| code (stock − planonly) | +5.1 | +3.7 | +11.1 | +6.5 |
| plan (planonly − noscaffold) | +2.3 | −0.5 | −0.5 | +4.6 |

The code contrast moves the same way in all four model-arm cells; the plan
contrast flips sign by arm on both models. Direction: what the scaffold is
worth to a floor model is mostly **the code it does not have to type**, not
the approach it is told. Nothing clears ADR-0019's bar — best sign p = 0.125,
best Wilcoxon p = 0.025 over eight per-arm contrasts, m in the teens at
n = 27. Directionally consistent, not resolved.

**The other finding, which is not what the experiment was for.** The 7B reads
30.6% ts / 25.9% py stock on these 27 (greedy alone 33.3% / 25.9%; 15/27 and
13/27 solved in at least one of 8 draws). That is at or inside the campaign's
30–50% aim, which two consecutive re-aims failed to reach by making problems
easier for the 3B. These 27 are the easier half of the bench and not a
stratum, so this is a locator and not a measurement — but it is the first
evidence that the aim may be reachable by choosing the model measured rather
than by re-aiming the material. Owner's call, not this block's conclusion.

## Two defects found in the reading, both fixed

**1. `--condition` never reached the manifest.** `main` passed it to the
dispatch path and not to `record_run`, so all eight ablated cells wrote
`"condition": "stock"` beside rows drawn without a scaffold. Nothing failed
loudly: the rows were right and the provenance was wrong. Worse, the resume
refusal written in the same commit to prevent exactly this could never fire,
because the field it compares never carried anything but the default — the
six tests all called `record_run` directly. Fixed at the call site, with a
test that drives `main` and asserts the two halves together: what the
manifest records, and what the worker was actually sent.

The eight manifests were repaired in place rather than re-run. That is safe
because the dispatched render is recoverable from the data, not just from the
launch script: mean prompt tokens per condition are strictly ordered
`stock > planonly > noscaffold` in all six cells and reproduce to the token
across two independent rigs.

**2. The analysis set lived only in `/tmp`.** The reader's default was "every
problem in the run" behind a warning, and the pre-registered set existed
nowhere in the repository. This is not cosmetic: over all 34 the 7B
whole-scaffold contrast reads sign p = 0.049 / 0.021, and over the
pre-registered 27 it reads p = 0.180 / 0.146 — the seven excluded problems
were carrying the significance. Landed as `tools/bench/ablation-sets.json`,
where only `dispatched` is listed and `analysis` / `strict` are subtractions,
so the three cannot drift apart. `--set` now takes a declared name and
defaults to `analysis`.

Both exclusion rules are re-derived by tests rather than trusted:
`dispatched` = every scaffolded `function_implementation` (the 19 scaffolded
`bug_fix` problems have no scaffold to remove — deleting a buggy program
deletes the task), and the 7 exclusions = the problems whose prose says a
helper is "already written", so the ablated prompt contradicts itself. Both
rules reproduce their sets exactly, in both arms.

## Verdict, and what it costs to go further

The question "what makes these problems hard" now has a **direction** on
paired evidence — code volume over stated approach — where block 3 had
nothing. It does not have a resolved effect size, and 27 pairs cannot give
one. The honest options are (a) accept the direction and act on it, (b) apply
it to the material (more starting code is the lever for an easier band, not
clearer prose), or (c) buy resolution with problems, which is the wall
ADR-0019 already priced.

Untouched and still available at zero model cost: **strict vs lenient
re-grading of the same saved completions**, the second arm block 3 proposed.
The candidates are pinned; only a second checker per problem is missing.

## Next

Campaign stays paused on the owner's instruction. The open question this
session adds to it: the aim was set for the 3B, and the 7B already reads
inside it.
