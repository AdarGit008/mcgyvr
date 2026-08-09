# ADR-0019 — the bar is a reality floor and a per-lever rule

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0018 (settles the question Q1 located at #229; Q1–Q4 stand)
Date: 2026-08-10

## Context

[ADR-0018](0018-one-bench-every-lever-and-the-whole-system.md) Q1 split the bar
into two things — a **reality floor** below which an effect is indistinguishable
from the instrument's own noise, and a **per-lever adoption rule**, because the
costs of the levers are not comparable — and located both at #229. It also
withdrew `MIN_QUALITY_GAIN = 0.03` as an adoption threshold: `propose.py:32`
states its real job, which is the separation two *rungs* need before both are
worth carrying in the ladder. #189 borrowed it, and everything downstream
inherited the borrowing.

Owner direction of 2026-08-09 set the target this record has to hit:

> I want all the means to improve the floor to be implemented even for a smaller
> gain than 3pp, or for the very least to be ruled out in a proper way. I want us
> to walk down every path and see where it ends.

Choosing the number required knowing what the instruments can see. That was
measured rather than assumed, and the measurement changed the answer.

## The measurement that decides this record

`tools/power/` derives, from the checked-in records alone, what every paired
contrast this project has ever run could have detected. Re-run with
`python tools/power/report.py`; nothing below is hand-entered.

**Eleven of the twelve bundle contrasts were unresolvable before the model was
dispatched.** Not "came out null" — *unresolvable*: too few tasks changed verdict
for the exact test to reach p < 0.05 at any split, so no possible outcome of
those runs could have rejected anything.

| contrast | n | gained | lost | discordant m | net | exact p | could it ever reject? |
|---|---:|---:|---:|---:|---:|---:|---|
| JS/TS c0→c1 | 20 | 2 | 0 | 2 | +2 | 0.500 | **no** |
| JS/TS c0→c2 | 20 | 3 | 2 | 5 | +1 | 1.000 | **no** |
| JS/TS c0→c3 | 20 | 2 | 2 | 4 | +0 | 1.000 | **no** |
| Python arm A c0→c1/c2/c3 | 20 | 1 | 0 | 1 | +1 | 1.000 | **no** (all three) |
| Python arm B c0→c2 | 20 | 4 | 0 | 4 | +4 | 0.125 | **no** |
| Python arm B c0→c1 | 20 | 5 | 2 | 7 | +3 | 0.453 | yes |
| Python arm B c0→c3 | 20 | 7 | 1 | 8 | +6 | 0.070 | yes |

The mechanism is arithmetic, not statistics: with `m` discordant pairs the
best-case two-sided p is `2 / 2**m`, so **m ≥ 6 is a hard wall**. Below it the
conditional null has too little mass to spend, and the test cannot reject however
large the effect is.

**Nominal n is the wrong denominator, and by how much is measurable.** Over the
whole condition matrix:

| instrument | n | always pass | always fail | responsive |
|---|---:|---:|---:|---:|
| bundle JS/TS, srv1 | 20 | 6 | 7 | **7 (35%)** |
| bundle JS/TS, srv2 | 20 | 6 | 8 | **6 (30%)** |
| bundle Python arm A | 20 | 13 | 6 | **1 (5%)** |
| bundle Python arm B | 20 | 5 | 6 | **9 (45%)** |

The JS/TS figure reproduces CLM-0012's "13 of 20 condition-insensitive" exactly,
which is the check that the method is reading the records correctly. **Arm A's 5%
is new and it matters**: the Python root sits at 65–70%, comfortably in band by
*level*, while nineteen of its twenty tasks are pinned. ADR-0017's correction of
2026-08-09 said the Python arm was in band by level and not shown to be in band
by response. This is the size of that gap. **Being in band is not the same as
having resolution, and level cannot reveal the difference.**

**The instruments are quiet. They are not coarse because they are noisy — they
are coarse because they are small.** Greedy re-runs of a byte-identical
configuration:

| instrument | runs | n | worst pair | drift | byte-identical |
|---|---:|---:|---:|---:|---:|
| d1 @ llama3.2:3b | 6 | 20 | 1 task | 5.0pp | 94% |
| d1 @ qwen2.5-coder:1.5b | 8 | 20 | 0 tasks | 0.0pp | 95% |
| d1 @ qwen2.5-coder:3b | 8 | 20 | 0 tasks | 0.0pp | 98% |
| d1 @ qwen2.5-coder:7b | 6 | 20 | 0 tasks | 0.0pp | 100% |
| d2 @ qwen3-coder:30b | 2 | 12 | 0 tasks | 0.0pp | 33% |
| pool @ qwen2.5-coder:14b | 2 | 255 | 1 problem | 0.4pp | 84% |

The pool row reproduces #216's ±0.7pp greedy figure from the raw rows. The 30B
row is the shape of the whole finding: **a third of its replies differ byte for
byte and not one verdict does.** Text divergence is not verdict divergence, and
the published explanation for the text divergence is batch-dependent reduction
kernels under dynamic batching, not floating-point luck
(`docs/adoption-bar-prior-art-2026-08-10.md`).

So #216's three-way ranking transfers, and the direction of the transfer is
favourable: greedy re-run drift on the 20-task instrument at four model sizes is
**0 or 1 task**, at or below the ±0.7pp the 269-problem pool showed. Under
ADR-0017's P3 that is transfer *shown*, not flagged. The sampled arm (±3.6pp) and
the backend change (2.6pp, from #189's own 2×2 at identical weights) are not
re-measured here and remain P3 obligations on whoever changes sampling or
backend mid-round.

## Decision

### D1 — the reality floor is three layers, and the binding one is resolution

For an instrument of `n` paired tasks with discordance rate `psi`:

1. **Quantum** — `1/n`. One task is the finest effect the instrument can express.
   No power calculation removes it. On n = 20 it is 5pp.
2. **Drift** — the discordant verdict count between two identical runs. Measured
   above: 0–1 task.
3. **Resolution** — the minimum detectable effect from `psi` and `n` at
   α = 0.05, power 0.80, via the exact test. This is always ≥ the quantum and,
   on everything we own, far above the drift.

**Resolution binds.** That is the correction this record makes to #229's own
framing, which expected drift to be the floor. A bench can have *zero* null drift
and still resolve nothing, which is exactly the state of the Python arm.

### D2 — the fitness rule #231 evaluates in writing, before any arm is dispatched

Commissioning reports four numbers and one verdict, per target tier:

- `n` — paired items on the held-out set
- `d` — discordant verdicts across two identical greedy runs (the null)
- `psi` — discordance rate measured on the **commissioning contrast**, which
  ADR-0018 Q3 already fixes as CLM-0017's output-shape line, the known ~+20pp
  effect the bench must recover
- `MDE = detectable_delta(n, psi)` from `tools/power/mde.py`

> **The bench is fit for a bar `b` if and only if `MDE <= b` and `d < b`.**
> Both conditions, per tier, in writing, before an arm runs. A bench that fails
> either is unfit, and every arm dispatched against it returns UNDECIDED by
> construction rather than by judgement.

`d < b` is #231's stop condition as #229 stated it and it is necessary. `MDE <= b`
is the one that was missing, and it is the one that fails today.

### D3 — the adoption rule is per lever, and cost decides which rule applies

The reality floor says whether a number is real. It says nothing about whether the
number is worth its price, and the prices differ by orders of magnitude. Four
classes, assigned by what adopting costs and what reverting costs:

| class | levers | what adoption costs | the rule |
|---|---|---|---|
| **R — reversible, zero marginal cost** | prompt assembly (#198), output caps (#17), target granularity (#126), sampling-breadth *default* (#119) | one run to measure; ships to every rung and backend at once; revert is one commit | **adopt on any resolved gain at all**, in the right direction, with no regression on the cost axis. The bar *is* the bench's MDE. |
| **O — ongoing per-task cost** | decomposition (#50, landed), attempts > 1, breadth > 1 (#119) | orchestrator or worker tokens on every task, forever | resolved gain **and** the cost axis reported per task. Adoption needs a stated exchange rate, not a pass-rate number alone. |
| **W — weights** | fine-tuning (#221, #190) | GPU hours, export path, quantization step, a capability-table entry — and it helps **one model** | resolved gain, **replicated on a second tier** (ADR-0018 Q4), **and** shown to survive a backend change — because #189 measured identical weights swinging 2.6pp on backend alone, which is larger than the gain it was arguing about. |
| **C — cost-only** | deterministic tier (#81) | does not move pass rate | not a bench lever at all. Verified as a suite assertion, as ADR-0018 already records. Not a factor in the combination space. |

**Class R is the whole of the owner's direction, implemented.** For a lever that
ships in one run and reverts in one commit, there is no defensible reason to
demand 3pp. If the bench resolves it and it points the right way, it goes in. A
+1pp prompt line and a +1pp fine-tune are not the same proposition, and after this
record they are not judged by the same number.

### D4 — three verdicts, and only one of them retires a lever

- **EFFECT** — resolved: direction, magnitude, interval, and the bar it cleared.
- **NULL** — *measured at power*: the bench was fit for bar `b` per D2, the arm
  ran at full size, and the result does not reject. Reported as "no effect ≥ `b`,
  at power 0.80". This **is** a completion, and it retires the lever at that bar.
- **UNDECIDED** — the bench was not fit for `b`, or the arm did not run at full
  size. **Not a verdict on the lever.** It never retires anything, and it carries
  an obligation: state the `n` that would have been required.

> **A lever may be retired only by NULL. Never by UNDECIDED, and never by a
> small number.**

Applied to what we already hold: **every bundle contrast in the table above is
UNDECIDED, not NULL.** That includes the one CLM-0012 reports as a null.

This does not withdraw CLM-0012's conclusion, and the reason is worth stating
because it vindicates the design that produced it. The *statistical* arm was
never resolvable. What carries CLM-0012 is CLM-0017's **positive control** — the
output-shape instruction moving 7/20 to 11/20 and completion tokens from 427 to
122, an effect predicted in advance by CLM-0012's own token analysis. Mechanism
plus a positive control is what makes an underpowered null readable. That is what
a positive control is *for*, and it is why ADR-0018 Q3 makes one a commissioning
requirement.

### D5 — the size is a function, not a number, and its input is measured

Required paired tasks, exact test, α = 0.05, power 0.80
(`python tools/power/report.py --section sizing`):

| bar | psi = 0.10 | psi = 0.20 | psi = 0.35 | quantum |
|---:|---:|---:|---:|---:|
| 1pp | 8,034 | 15,890 | 27,666 | n ≥ 100 |
| 2pp | 2,043 | 4,017 | 6,963 | n ≥ 50 |
| 3pp | 920 | 1,800 | 3,113 | n ≥ 34 |
| 5pp | 337 | 658 | 1,133 | n ≥ 20 |
| 10pp | 78 | 168 | 289 | n ≥ 10 |

**The `psi` range is ours, measured, not borrowed**: 0.05 (Python arm A) to 0.40
(arm B c0→c3), with the JS/TS instrument at 0.10–0.25. The responsive fractions
those come from are reported in the table above — 35%, 30%, 5% and 45%.

`psi` is a property of the **(instrument, lever) pair**, never of a task set
alone: a task pinned under the bundle may well move under decomposition. So the
sizing above cannot be resolved to a single number in advance, and this record
does not pretend to. **#231 measures `psi` on the commissioning contrast and
#225 is sized from that measurement**, using the same tool, with the range above
as the planning prior until it exists.

**What #225 should build, and what it buys:**

| n | psi = 0.10 | psi = 0.20 | psi = 0.35 |
|---:|---:|---:|---:|
| 20 (today) | unreachable | unreachable | unreachable |
| 200 | +6pp | +10pp | +12pp |
| **400** | **+5pp** | **+6pp** | **+8pp** |

**n = 400 paired tasks** is the recommendation. It resolves +5 to +8pp across the
whole measured `psi` range, and it is where the curve turns: 3pp costs 920–3,113
tasks, which is 2.7× the material for 1.7× the resolution.

**The cost of that is not rig time.** A full 8-cell round — baseline, six single
levers, all-on — over 400 tasks at the 3B's measured 2.4–3.1s per dispatch is
**about 3–5 rig-hours**, against the 3.25 hours one pool sweep already cost. The
price of #225 is **authoring 400 admissible contracts with runnable acceptance**,
and #222 is sized behind the same number. The audit's "only the widening costs
meaningful rig time" is the wrong axis; the widening costs meaningful *authoring*.

### D6 — a lever below the bench's resolution is carried, not dropped

At n = 400 the resolvable single-lever effect is 5–8pp, and a 1pp bar would need
8,000–27,700 tasks — 16 to 55 times a pool that cost real money and two
spend-limit interruptions. So sub-resolution effects cannot be individually
resolved at any affordable size, and D4 forbids retiring them.

They are carried instead, by two routes that already exist in the plan:

1. **The all-on cell (#233).** ADR-0018 Q2 makes it a first-class measurement.
   Six levers each worth an unresolvable +1pp compose into an effect the bench
   resolves easily, and leave-one-out then prices each one *inside* the full
   system. This is the affordable way to see small effects, and it is the direct
   answer to "walk down every path and see where it ends."
2. **Draws per task.** Resolution can be bought with replication instead of
   material — the published worked example takes an MDE from 13.2% to 7.5% that
   way. It costs dispatches rather than authoring, which is the cheaper axis
   here, and it interacts with #119. Not adopted by this record; named as the
   lever to reach for when authoring is the constraint and rig time is not.

A lever whose single-arm result is UNDECIDED and whose leave-one-out contribution
in the all-on cell is also UNDECIDED has been walked to the end of its path at
the power the project can afford. **That, stated with its `n`, is what "ruled
out" means here.**

## Rejected: pick one number and apply it everywhere

The inherited state, and the thing that produced the +1.9pp "miss". One number
cannot serve both jobs: the reality floor is a property of the *instrument* and
moves whenever `n`, `psi` or the tier changes, while the adoption bar is a
property of the *lever's cost* and does not move at all. Fusing them means every
re-sizing of the bench silently re-prices every lever.

## Rejected: raise the bar to what our instruments can already resolve

Honest, and it inverts the project. The bundle instruments reach 80% power at
**no effect size at all** across the measured `psi` range; the smallest outcome
that could even reach p < 0.05 is 6 of 20 tasks flipping one way, which is
+30pp, and the smallest that reaches 80% power is +40pp and needs `psi` ≥ 0.40
to go with it. Adopting any of those as the bar would rule out every lever
mcgyvr has, in one line, on the strength of an instrument defect rather than a
result. This is ADR-0017's rejected
"measure wherever the instrument is sharpest" wearing a different hat — letting
the instrument choose the question.

## Rejected: keep n = 20 and report directional results

Cheap, and it is what the project has been doing. The table at the top is the
cost: twelve contrasts, eleven structurally unable to reject, four claims and one
ADR amendment built on top of them, and a downstream reader with no way to tell a
measured null from an arithmetic impossibility. Direction without resolution is
not a weaker result, it is a differently-shaped one, and the record did not carry
the distinction.

## Consequences

- **`tools/power/` is now on the critical path.** #231's fitness verdict, #225's
  size and every arm's verdict all come out of it. It reads the checked-in
  records and nothing else, so `report.py` re-derives every figure in this ADR.
- **#225's brief changes from "widen" to "size to 400 and state `psi`".** Its
  output is sized by D5 and its cost is authoring, not rig hours.
- **#231 gains a second commissioning condition.** `MDE <= b`, evaluated per
  tier, alongside the null-drift check it already had. It is the condition that
  currently fails.
- **Historical verdicts are re-labelled, not re-run.** #189's "miss" becomes
  UNDECIDED (amended in `records/measurements/finetune-pilot-2026-08-07/`), and
  the bundle contrasts become UNDECIDED-with-mechanism. No measurement is
  discarded; CLM-0012, CLM-0013 and CLM-0017 keep their data and their
  confidence notes, which already flagged the responsive-fraction limit.
- **`MIN_QUALITY_GAIN` keeps its value and its job.** Rung separation is a
  different question and this record does not touch it. `propose.py` now states
  the distinction where the constant lives.
- **A small gain is now adoptable, and that is the point.** For a Class R lever
  the bar is whatever the bench resolves — there is no floor of 3pp, or of any
  other inherited number, standing between a measured improvement and shipping.
- **Cost is admitted.** 400 authored contracts is real work that produces no
  answer by itself, the per-lever table will be argued about, and D6 means some
  levers end their lives labelled "unresolved at affordable power" rather than
  decided. That is the decision, not a side effect of it.
