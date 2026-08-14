# Positive-control candidates that survive the floor — the material, surveyed

Issue: [#266](https://github.com/AdarGit008/mcgyvr/issues/266). Route decision:
[#225](https://github.com/AdarGit008/mcgyvr/issues/225). Gate:
[#231](https://github.com/AdarGit008/mcgyvr/issues/231) check 2.
Doctrine: [ADR-0019](decisions/0019-the-bar-is-a-reality-floor-and-a-per-lever-rule.md)
(the `m >= 6` wall),
[ADR-0026](decisions/0026-four-lenses-record-mutate-state-the-property-and-price-the-axes.md)
(a stratum with no headroom is excluded, not reported as null).

This document does **not** choose the control — #225 owns that by its own rule.
It states what the material can and cannot carry, so the choice is made against
numbers rather than against intuition.

## The finding that reframes the question

#266 priced the two declared capacity levers by expected discordance: *"34 cells
expects m ≈ 2."* That framing invites the answer "then run more cells." It is the
wrong framing, and the corpus says so.

A cell that passes under **neither** condition is concordant whatever the lever
does. So the count of cells passing under *either* is an arithmetic **ceiling**
on `m`, independent of effect size. Stock pass rate by stratum, `Gate.run`-scored,
from the committed null-a runs:

| stratum | n / arm | 7B py | 7B ts | 1.5B py | 1.5B ts |
|---|---:|---:|---:|---:|---:|
| `bug_fix` | 59 | **55.9%** | **50.8%** | 20.3% | 16.9% |
| `function_implementation`, no scaffold | 164 | 20.1% | 11.0% | 5.5% | 13.4% |
| `function_implementation`, **scaffolded** | 34 | **2.9%** | **8.8%** | 5.9% | 2.9% |

The 34 cells the capacity levers can act on are the **hardest stratum on the
bench**, an order of magnitude below the arm they sit in. The reason is
structural rather than accidental: a task carries a scaffold because it is
multi-function, and multi-function is what a small worker fails.

Both capacity levers also make the task *harder*, so the ablated arm can only
lose cells. The ceiling therefore binds in the direction that matters.

## What each candidate's material can carry

Eligibility from the corpus; ceiling measured on the committed 7B pair
(`bench-null-gate-7b-a-2026-08-14` against `bench-control-norule-7b-2026-08-14`).
Re-derive with `tools/bench/eligibility.py`.

| candidate | arm | eligible | ceiling on `m` (7B) | vs `m >= 6` |
|---|---|---:|---:|---|
| `nointerface` | `bench-py` | 257 | 73 | clears |
| `nointerface` | `bench-ts` | 257 | 58 | clears |
| `nostop` | `bench-py` | 257 | 73 | clears |
| `nostop` | `bench-ts` | 257 | 58 | clears |
| `noscaffold` / `planonly` | `bench-py` | 34 | **1** | **blocked** |
| `noscaffold` / `planonly` | `bench-ts` | 34 | **4** | **blocked** |
| any lever restricted to `bug_fix` | `bench-py` | 59 | 36 | clears |
| any lever restricted to `bug_fix` | `bench-ts` | 59 | 31 | clears |

**The two declared capacity levers are the only candidates the material refuses,
and it refuses them at any effect size.**

## The candidates, against #266's four criteria

#266 requires a candidate to be present above the floor, decidable, carrying a
mechanism signature, and pre-registered before a draw. Criterion 4 is a process
obligation and is not repeated per row.

### `nointerface` — drop the INTERFACE section

`render_user_message` emits `INTERFACE (the result must expose exactly this)`
from `view["interface"]`, carried by **all 257 contracts on both arms**
(`src/mcgyvr/worker/prompt.py:151`). Ablating it forces the model to infer the
signature from prose.

- **Present above the floor?** Plausible and untested. Inferring a signature is a
  *capacity* demand, not a formatting one, so it is not mediated by the adapter
  rungs — which is exactly the mechanism that decayed between tiers and
  disqualified `norule`.
- **Decidable?** Ceiling 73 (py) / 58 (ts) at the 7B. Twelve times the wall.
- **Mechanism signature?** Distinctive and checkable in advance: a wrong
  signature fails at `acceptance` (the harness cannot call the function), not at
  `lint` or `format`. If the effect appears in the adapter rungs instead, it is
  the `norule` mechanism again and the recovery does not count.
- **Cost.** A `message`-stage lever writing a new `interface_section` slot —
  mechanically identical to `norule`, which already works. No authoring.

### `nostop` — drop the STOP AND REPORT BLOCKED IF section

Same shape, same eligibility (`prompt.py:161`), same ceiling.

- **Weaker prior.** `stop_conditions` names ambiguities the task does not settle.
  A worker that ignores them behaves the same as one never told, so the ablation
  may be closer to a no-op than a capacity manipulation. That is a *reason to
  expect a null*, and a control chosen for commissioning should be an effect we
  expect to find.
- Better as an arm in its own right than as the commissioning control.

### A lever restricted to `bug_fix` — the responsive stratum

`bug_fix` is where the 7B actually has room (55.9% / 50.8%) and where it neither
floors nor ceilings — the band #224 exists to locate.

- **The bind:** `matrix.json` rules `bug_fix` ineligible for both capacity levers
  for a sound reason — *its `target_content` **is** the buggy file the task
  exists to fix, so removing it deletes the task rather than lightening it.*
  **The cells that can resolve an effect are exactly the cells the declared
  levers may not touch.**
- **The candidate this suggests, and its cost:** a `nolocate` ablation — the task
  prose currently *names* the defect (*"at present the newest available package
  jumps the queue instead"*), so removing the localizing clause makes the model
  find the bug itself. That is a real capacity effect on the responsive stratum.
  It is **not mechanical**: the clause sits inside authored prose and would have
  to be cut per task across 59 contracts per arm. Costed here, not recommended
  from here.

## What this does to the other issues

- **#222 (build the corpus)** is sharpened, not merely supported. Authoring
  material is no longer *one* answer to a power shortfall; for a scaffold
  manipulation it is the *only* answer, and the specification is now concrete:
  **scaffolded tasks a floor unit can actually pass.** Today's 34 are not that.
- **#224 (map the band)** gains a measured anchor: at the 7B the band is
  `bug_fix`, and the scaffolded implementations sit below it on both tiers.
- **#233 (combinations)** inherits the same constraint — an interaction term
  needs both single levers decidable first.

## Not decided here

Which control is chosen. #225 holds that, under its own rule that the argument
lands there and #231's body is corrected to match.

---
Scope of record: this survey. Rationale for the boundaries it sits inside:
[ADR-0001](decisions/0001-founding-scope-and-boundaries.md).
