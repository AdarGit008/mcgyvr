# ADR-0022 — a lever is never a difficulty knob

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0018 (one bench under every lever — this says what the bench may
not borrow from the levers it is under)
Date: 2026-08-11

## Context

#225's third tranche asked what makes the bench's problems hard, and answered
it by rendering the same 34 problems three ways: with the scaffold, with the
scaffold's plan only, and with neither. It is a clean paired design and it
produced a real direction — the code a scaffold saves matters more than the
approach it states, the same way in all four model-arm cells.

The scaffold is also one of the levers [ADR-0018](0018-one-bench-every-lever-and-the-whole-system.md)
puts the bench *under*. Using it to calibrate the bench's difficulty would mean
the instrument that later measures "does scaffolding help?" was tuned with
scaffolding. Whatever that instrument then reported about the lever would be
partly a fact about how it was built.

This was caught before anything was calibrated on it, which is why this record
costs a re-filing and not a re-run.

## Decision

> **DECIDED (2026-08-11, owner).**
>
> 1. **A product lever may never be used as a bench difficulty knob.** Scaffold
>    presence, decomposition, bundle size, retrieval breadth and every other
>    lever #113's matrix will test are the *subject* of measurement. They do not
>    get to set the scale.
> 2. **The bench is measured stock.** One condition: the contract as authored.
>    Problems keep the starting code their authors wrote — that is task
>    material — but the pipeline renders no conditions on top of it during
>    calibration.
> 3. **The scaffold ablation is re-filed as a #113 feature finding.** Its result
>    stands as evidence about the lever. It is removed from the difficulty
>    reasoning in `tools/bench/strata.json`.

## Why this is a rule and not a note

The tempting version of the mistake is not "calibrate with a lever" — nobody
proposes that. It is "we need a difficulty knob, and here is a manipulation we
already have tooling for, which happens to be a lever." The tooling argument is
what makes it attractive and it is exactly the wrong reason: the levers have
tooling *because* they are what the project intends to measure.

The same argument applies in the other direction and is worth stating, because
it is the cheaper half. A bench whose difficulty was set independently of the
levers can measure any lever, including ones not yet built. A bench calibrated
with lever A can only ever make claims about levers B and C with a caveat about
A folded into every one.

## Consequences

- **Difficulty is set by properties of the problem, not by how it is
  presented.** See ADR-0023 for what those properties are.
- **`--condition` keeps its place in the rig and loses it in calibration.** The
  ablation machinery is not deleted: #113 needs exactly this, and it now has a
  worked instance plus the two recording defects already fixed out of it.
- **This is the second time a #225 result was filed under the wrong question.**
  The first was ADR-0020's control, which ran on Python contracts and was
  described as JS/TS in three documents. Both were caught by re-reading rather
  than by any check, which is part of the case for the trunk decision audit.
