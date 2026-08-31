# ADR-0026 — four lenses: record what is unrecoverable, mutate to discover, state the property, price the axes

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0024 (run identity is content, not a name), ADR-0025 (the premise
that two bars "move together" was asserted and is false)
Date: 2026-08-13

## Context

On 2026-08-13 the same defect was found eleven times in one day, in shipped
code, in measurement tooling, in decisions of record, and twice in tooling
written that morning to diagnose it. In every instance a **cheap label stood in
for the property it named**:

| the label | the property | the gap, measured |
|---|---|---|
| `gate_rungs: [scope, secrets, structured, adapters, acceptance]` | the rule sets behind them | 328 ruff rules against 66 eslint rules; 154 rejections against 32 |
| `model: qwen2.5-coder:1.5b` | weights, vocabulary, template, quantization | 0 of 133 manifests carry any of them |
| `condition: norule` | the prompt actually sent | `bundle_sha256` hashes the *system* prompt; the ablation edits the *user* message, so stock and norule manifests are byte-identical apart from the label |
| "matches `tools/bundle/measure.py`'s `ACCEPTANCE_TIMEOUT_S`" | 120.0 against 30.0 | asserted in a comment, false by 4x |
| "the bundle device is not language-specific" | −0.8pp Python, −14.9pp TypeScript | 14.1pp, and Python was not power-limited |
| ADR-0025's "the two move together" | the bar reverses which arm leads | py 8.9/ts 12.8 under the bar, py 27.3/ts 23.9 on correctness alone |

None of these was found by a check. Every one was found by a person or an agent
re-reading. That is the fact this ADR responds to.

## Decision

Four lenses. Work is reviewed against all four, and each is stated so that it can
refuse something.

### 1. Record what cannot be reconstructed. Never record what can be recomputed.

Raw replies, resolved configurations, rendered prompts, digests and the inputs a
figure was derived from are unrecoverable once a run ends. Derived rates are
always recomputable, and a stored rate is how a figure goes stale and is then
quoted. Where a derived number *is* stored — a declared bound, a stratum table —
it carries the inputs that produce it, so it can be re-derived rather than
believed.

The corollary, and the reason volume is not the point: `steering_band` and
`shape` were recorded at authoring time and read by nothing. **The join is the
requirement, not the capture.**

### 2. Mutants are a principle, not a roadmap.

We cannot plan which axes matter; we can perturb them and measure which move.
The condition matrix (#113) is already a mutant generator — `norule` is a
mutant — and generalising it from "levers we chose" to "perturbations that
reveal sensitivity" is a change of intent, not of machinery.

Two constraints, or it measures nothing: **screening before factorial**
(one-at-a-time first, interactions only where a single moved), and **run on
responsive cells only** — 453 of 514 cells never pass under any condition, so a
sweep over the full set mostly measures the ceiling.

A mutant says what changes the number. It does not say what is worth having.

### 3. A record states the property, not a claim about it. Records are first-class.

A comment asserting that two separately-defined things are equal is a claim, and
a claim is not enforcement. Two were found by one grep: a timeout comment
already false by 4x, and a duplicated git empty-tree sentinel that is true today
and enforced by nothing.

Every such assertion is made to hold by a check, or deleted. A record that
states a property carries the property — a digest, a resolved value, a
fingerprint — and where the real property is unobtainable, the record says
`unknown` rather than substituting a name.

**And the strong form, which applies to every bar, test, check and measurement:
it states what it contains, or it is worse than dead weight.**

Dead weight is neutral — it costs and does nothing. A check that cannot say what
it applied is *negative*, because it reports health while applying an unknown
bar, and a reader cannot tell the difference between "this passed" and "nothing
ran". Every instance below was live in this repository, and each looked healthy
from the outside:

| what it reported | what it applied |
|---|---|
| the JavaScript lint rung, in `Gate.run`'s rung list and in every manifest | eslint absent → "inconclusive" → a pass; then present and parserless → severity-1 warnings the adapter did not count |
| `ruff`, installed and running | no config staged, so a rule set far wider than the project selects — `TRY004` alone rejected 75 of 257 reference solutions |
| `gate_rungs`, identical on both arms | 328 rules against 66 |
| `tsc --noEmit`, named in the bar | `tsconfig.json` never staged, so it never ran |
| `structured`, named in the bar | vacuous on both bench arms — its extensions match no file either arm produces |

The rule that follows: **a check declares its content, and something proves the
declaration is live.** The declaration is the digest of what it actually applied;
the proof is a positive control — a reference that must pass and a canary that
must fail, per declared rung, per language. Neither half is sufficient. A digest
with no control records precisely which inert bar was applied; a control with no
digest proves something rejected without saying what.

The cost of getting this wrong is not a missed defect. It is a published number
that nobody can re-derive and everybody believes.

### 4. Do not plan experiments. Plan which axes are cheap to vary.

Adding a language costs ~17 files of code across three separately hardcoded
adapter tuples with no registry. Adding a task type costs one data file, enforced
by a test. That asymmetry — not any experimental design — is why this project
varied task types freely, held language fixed, and did not find a 14.9pp language
effect for six weeks.

**People measure what is cheap, so what is made cheap decides what is found.**
Infrastructure planning is therefore question planning at a coarser grain, and the
axes worth making cheap are the ones currently most expensive.

## Consequences

- **Three fields change from name to content**: the bar (a digest of each arm's
  resolved rule sets and tool versions), the model (vocabulary, merges, template
  digests and effective context — all verified obtainable at runtime from the
  serving endpoint on 2026-08-13), and the condition (a digest of the rendered
  prompt as sent).
- **A report refuses a pooled figure across a stratum where the effect is
  heterogeneous**, and reports per stratum instead. Language is one such stratum
  and not the strongest: on this bench task type moves the same effect 6x within
  one language, and on `bug_fix` the two languages agree.
- **A stratum with no headroom is excluded, not reported as null.** "No effect
  where nothing passes" is absent resolution, not absent effect.
- **Comparability guards name every field that can move a number**, and are
  tested by mutating a manifest and requiring a refusal. A guard that names five
  fields permits the sixth silently, which reads as having checked.
- ADR-0025's decision clauses stand; its premise that the two bars "move
  together" is withdrawn as asserted rather than measured.
- The costs are real and are accepted: more recorded fields are more surface that
  can be wrong, which is why lens 3 is not optional. Screening sweeps consume rig
  time, which this project has treated as its spare axis.

## What this does not say

It does not say measure everything. It says stop claiming generality across axes
that were not measured — scope sentences narrow, work does not multiply.

It does not replace commissioning. An instrument still needs a positive control:
#133 is the case where an all-zero measurement with no control could not
distinguish "no effect" from "broken rig", and no amount of recording fixes that.

---
Scope of record: this decision. Rationale for the boundaries it sits inside:
[ADR-0001](0001-founding-scope-and-boundaries.md).
