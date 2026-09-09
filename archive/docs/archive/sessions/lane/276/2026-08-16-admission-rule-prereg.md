---
record: session/1
lane: lane/276
agent: adar
started: 2026-08-16T09:00:00Z
---

# The admission rule — pre-registration (lane/276, #276)

**Declared 2026-08-16, before a single perturbation run is dispatched.** Every
threshold, comparator and exemption below is fixed here. If this document
postdates the runs it is worthless — this campaign has three times paid for
reading a design off a number it had already seen.

Governing records: **ADR-0019** (the `m >= 6` wall, MDE as a function of
discordance), **ADR-0024** (one rig, one build), **ADR-0026** (lens 2, mutants
as a principle; lens 3, a record states the property), **#265** (the encoding
this rule keys), **#231** (which supplies the null).

## What this rule governs, and what it does not

**Recording is unconditional and is not governed here.** Every observable field
is recorded regardless of this rule. A field recorded and never keyed costs
bytes; a field not recorded is unrecoverable, and the runs made in the interval
cannot be re-identified. ADR-0024 settled that asymmetry once —
*"the protection is for runs made from here on"* — and this document does not
reopen it.

This rule governs exactly one thing: **which fields enter the comparability
key.**

## The rule

> A field enters the comparability key if and only if, holding all other fields
> fixed, changing that field alone flips more task verdicts than the bound
> declared for that `(model, tier, bar, build)`.

Formally:

```
admit  iff  flips  >  n_perturbation x wilson_upper(d_null, n_null)
```

where `wilson_upper` is the upper limit of the Wilson score interval on the null
run pair's flip rate, at 95%:

```
p = d / n,  z = 1.96
center = (p + z^2 / 2n) / (1 + z^2 / n)
half   = z / (1 + z^2 / n) * sqrt( p(1-p)/n + z^2 / 4n^2 )
upper  = center + half
```

For `d = 0` this collapses to `z^2 / (n + z^2)`, which reproduces the recorded
`bound_pp = 1.47` at `n = 257` exactly (3.8416 / 260.8416 = 0.014728).

**The threshold is a formula and never a constant.** In flips it is
near-invariant in n *only while the null is clean* — 3.22 at n=20, 3.79 at
n=257, 3.81 at n=400, converging on `z^2 = 3.84` from below. The first null that
flips one cell moves it to ~5.6, a ~50% change from a single observation.
Writing "4" into code would encode an accident of the current null.

**Two conditions on the bound itself**, both required before this rule is
applied:

1. `cells` joins `matching` in `tools/bench/reproducibility.json`. The rate is
   currently keyed on model, tier, `gate_rungs` and `serving_build` but not on
   the denominator it was measured over, so it transfers to subsets it never
   saw — applied to a 34-cell eligible set it is ~7x too strict, where
   `upper(0, 34) = 10.15pp`.
2. The null is measured on **the same paired set that will be perturbed**,
   rather than borrowed across n.

## Corollaries

1. **Untested fields are recorded, not keyed.** A field nobody has perturbed is
   never admitted on plausibility. Absence of a perturbation is not evidence of
   inertness, and this rule does not let it act as one.
2. **Unperturbable fields are admitted by default.** Where a field cannot be
   varied in isolation — host hardware is the standing case, and ADR-0024 chose
   srv2 as *the* measurement rig precisely to avoid varying it — innocence
   cannot be demonstrated, so the field is assumed guilty.
3. **The four bound-key fields are admitted by construction and exempt from the
   test.** The rule cannot hold `model` fixed while varying `model`; the same
   applies to tier, bar and build, which are exactly `BOUND_MATCH`. Without this
   clause the rule is circular for the four fields that matter most.
4. **Screening before factorial.** One-at-a-time perturbation admits.
   Interactions are tested only among already-admitted fields, per ADR-0026
   lens 2's two constraints — which also requires running on responsive cells
   only, since a sweep over the full set mostly measures the ceiling.
5. **Admission is sticky.** Removing a field from the key requires its own
   demonstration. An absence of evidence never removes a field.

## Admission is not a significance test

The threshold sits **below** ADR-0019's `m >= 6` wall by design. A field may be
admitted on a flip count too small to test for significance. This is the
conservative direction and it is deliberate: over-refusal costs a re-run, and
under-refusal costs a published wrong effect.

**Admission means "this can move the instrument". It never means "this effect is
established".** The state ladder below keeps the two apart, and no report may
use the first word where it means the second.

## The state ladder

| state | bar | source |
|---|---|---|
| **admitted** | `flips > bound_flips` | this document |
| **reachable** | some effect size could clear the wall at all | `tools/bench/resolution.py` |
| **decidable** | `m >= 6` discordant pairs | ADR-0019 |
| **detectable at d** | `exact_power(n, psi, d) >= power` | `tools/power/mde.py` |
| **established** | direction **+** mechanism signature **+** p < 0.05 | #231 prereg, 2026-08-13 |

**The three-part bar for `established` is scoped to recoveries of known
effects**, where the signature can be named in advance. It is not a general
definition. A novel lever has no signature to pre-specify, and applying the
clause generally would make every new finding unestablishable by construction.
For a novel lever the bar is direction and `p < 0.05` at `m >= 6`, with the
mechanism reported rather than pre-registered.

The failure states stay distinct, and the words are not interchangeable:

- **not established** — direction and signature present, `p >= 0.05` at
  `m >= 6`. The effect is smaller than expected, or n does not reach it.
- **UNDECIDED** — `m < 6`. The contrast could not have rejected anything at any
  outcome. This is #189's actual verdict, and it was read as a negative result
  for weeks.
- **null** — measured, decidable, inert.

## The perturbation set, fixed in advance

One-at-a-time, in this order. Adding to this list after the first run is a
protocol violation and the run that follows it is not admissible under this
rule.

1. endpoint
2. serving build
3. quantization
4. vocabulary
5. template
6. lint config
7. tool version
8. prompt-as-sent
9. seed presence
10. output cap

**`seed presence` is observed, never set.** Recording `seed: null` states a
fact. Setting a seed is a different experiment and would silently re-baseline
every measurement made before it; that decision does not belong to this rule.

## What would falsify the procedure

The bound is the backstop. If two runs made under an identical record differ by
more than the declared bound, something outside the key is moving, and the
correct response is to find it rather than to widen the bound. A bound that
drifts upward across re-measurements is the signal that this list is incomplete.

**Stated residual:** a field that varies, was never varied, and stays inside the
bound is undetectable by this procedure. The record carries what was done to
look — surface digest, perturbations run, bound applied — rather than a claim of
completeness.

## Left open

- The null re-measurement bill is unpriced. Every `(model, tier, bar, build)`
  cell the re-run produces needs its own bound at ~40 minutes, and the plan's
  own growth in the key multiplies how many are needed. Owned by #231, which
  `reproducibility.json` names as its supplier.
- `bound_flips` has no implementation. The formula above is stated here and
  nothing computes it yet.

next: land the identity changes as one range so a single round boundary covers them, then open r2 — no dispatch in between
