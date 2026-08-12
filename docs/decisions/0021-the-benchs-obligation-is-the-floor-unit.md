# ADR-0021 — the bench's obligation is the floor unit

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0019 (D5's size is per model and per language, not one pooled 400),
ADR-0017 (the floor is the product — this says what that obliges the *bench* to
do), ADR-0018 (the bench under every lever must first be a bench for the
smallest worker)
Date: 2026-08-11

## Context

[ADR-0017](0017-the-floor-is-the-product.md) made the smallest worker the
product rather than a stepping stone. [ADR-0019](0019-the-bar-is-a-reality-floor-and-a-per-lever-rule.md)
priced what it costs to see an effect at all, and D5 sized the bench at 400
paired problems. #225 then built material against that number.

Three sweeps in, the material does not do the job. The 3B reads 1/23 and 5/23
on the band aimed at 30–50%, and 0–2/12 on every band above it. The bands were
re-aimed twice and undershot twice. A bench on which the floor worker scores
near zero everywhere is not a hard bench — it is an instrument that returns the
same answer for every lever, every model and every condition it will ever be
pointed at, which is no answer.

The failure is not that the problems are too hard in the abstract. It is that
"400 paired problems" was read as a property of the *bench* when it is a
property of a **bench-and-model pair**. A set sized for one worker says nothing
about a worker half its size, and #225 spent two tranches discovering that by
authoring.

## Decision

> **DECIDED (2026-08-11, owner).**
>
> 1. **The bench's obligation is the smallest unit of the workforce.** A bench
>    on which the floor worker cannot be measured is not usable, whatever it
>    can see about larger models. The floor worker is currently
>    `qwen2.5-coder:1.5b` and stays the floor until the owner rules it out
>    explicitly.
> 2. **The size is ~400 paired problems *per model measured*, not 400 in
>    total.** This amends ADR-0019 D5, which stated the number without stating
>    its denominator.
> 3. **Benches overlap.** One set measured against several models is the
>    intended shape, not a compromise: it costs rig time and no authoring, and
>    it is the only form in which a cross-model contrast is a contrast at all.
> 4. **The floor is built first and the ceiling is deferred.** Top strata are
>    authored when a model actually ceilings on what exists — not in
>    anticipation. The ladder may eventually need to reach a 20B or 30B MoE
>    worker on srv2; that is a later problem and it does not shape this one.
> 5. **#225's existing 220 admitted problems are the ladder's top, not a
>    failed aim.** The 3B floors on them and the 7B reads 30.6% ts / 25.9% py
>    on their easier half. They are re-labelled, not re-authored and not
>    discarded.

## Why the floor and not the ceiling

The argument for measuring the smallest unit is not thrift. It is that the
smallest unit is the one whose usability is in question. A 7B that solves a
band tells us the band is solvable; it does not tell us whether the thing we
intend to deploy can do the work. Every rung above the floor is a fallback we
already know works.

The 1.5B specifically is worth the floor position because its appeal is
throughput: if it can be harnessed to real completions at all, it is the
cheapest capacity the project has. That is a question about *whether it reaches
real tasks*, and only a bench it can be measured on can answer it.

There is a tension this record does not resolve and should not hide: a band the
1.5B reads at 30–50% may be so small-grained that it no longer resembles the
work the product does. If that turns out to be the case, that is itself the
evidence for ruling the 1.5B out — and the ruling stays the owner's, made on a
measurement, not inferred by whoever is authoring at the time.

## Amendment — 2026-08-11: separation is not a requirement

This record left one question open: `records/measurements/mbpp-plus-1.5b-2026-08-11/`
measured the 1.5B at 3.7pp behind the 3B on MBPP+ shape, and noted that a band
the floor unit can be *measured* on may not *separate* it from the rung above —
ADR-0021's obligation met, #224's requirement possibly not.

> **DECIDED (2026-08-11, owner).** Separation between models is **not** a
> requirement of this bench. Floor coverage is. If a band that covers the floor
> unit cannot tell the 1.5B from the 3B, that is a result and it is reported as
> one — it does not disqualify the band or send it back for re-aiming.
>
> **The 30–50% aim stands, and it is satisfied against the smallest model.**
> Not against the 3B, not against a pooled figure, not on average. Upstream is
> easier and less important: a larger model reading high, or ceilinged, on the
> floor band is an accepted outcome and not a defect to design around.
>
> A finding that the 1.5B matches the 3B on the work we actually dispatch is a
> reason to **deploy the 1.5B**, not a reason to distrust the bench.

So where this record's Decision (3) permits overlapping benches, that permission
is not to be spent building a second band whose purpose is separating models.
The ladder's upper range already exists in the 220 admitted problems, and
nothing further upstream is authored until a model actually ceilings on what is
there — clause (4), unchanged and now load-bearing.

Note what this does *not* say: #224 still asks where a small worker neither
floors nor ceilings, and it may need material this bench does not provide. That
is #224's problem to state when it gets there, and it is no longer a constraint
on the floor band's design.

## Amendment — 2026-08-11: overlap may be total, and the aim is met per model

Decision (3) says benches overlap. It does not say how much, and the floor
band's first 40 problems made the question concrete: b228–b267 are the 1.5B's
first 40 of 400, and nothing here stated whether the 3B's 400 must be different
problems, a superset, or the same forty.

> **DECIDED (2026-08-11, owner).** Overlap between one model's set and
> another's may be **full or partial**, with no upper bound. The same problem
> counts toward two models' 400s.
>
> **The 400 stays intact per model** — this amendment buys no relief from
> Decision (2)'s count. What it removes is the assumption that a second model
> needs 400 *newly authored* problems.
>
> The binding constraint is per model and unchanged: each model's 400 must meet
> **its own** 30–50% aim.

The consequence is that overlap is settled by **measurement, never by
assumption**. A problem earns its second slot by reading in-band twice; a
problem the floor unit sits mid-band on and the rung above ceilings on belongs
to the floor unit's 400 and not to the other's. So a second model's authoring
bill is its *shortfall* — the problems it ceilings on — and that bill cannot be
known until it is swept against what already exists.

This is stricter than "author 400 once and reuse it" and cheaper than "author
400 twice." It also makes the upstream sweep a step of the method rather than a
curiosity: it is the only way to learn what the overlap is. That does not
reorder the work — the floor unit's 400 is completed first, per Decision (4)'s
floor-before-ceiling rule.

Nothing here weakens the previous amendment. Separation is still not required,
and a shared problem is not evidence of a defective band.

## Amendment — 2026-08-12: the 400 is counted in paired cells, both arms

This record was written because ADR-0019 D5 *"stated the number without stating
its denominator"*. The same ambiguity survived one level down and
`records/sessions/lane/225/2026-08-11-f1-responsiveness-adar.md` made it
load-bearing: `f1` counts **problems**, the sweep dispatches **cells**, and a
problem carries a `ts` arm and a `py` arm. At the responsiveness run's measured
figure the two readings give an MDE of 11.8pp and 8.2pp respectively — the
difference between missing D5's own resolution target and meeting it.

> **DECIDED (2026-08-12, owner).** The 400 is **400 problems, each contributing
> both language arms — 800 paired cells.** That is the denominator every sizing
> figure is computed against, and `tools/power/` is fed cells, not problems.
>
> This buys no relief from Decision (2)'s count: it is still 400 problems per
> model. It states what those 400 are worth to the statistic.

Consequence worth naming: at `psi_draw` = 0.659 the completed bench resolves
**8.2pp**, which sits at the edge of the +5 to +8pp D5 planned rather than
outside it. The alarm the responsiveness run raised is substantially answered by
fixing the denominator, and what remains is the open question of what the real
per-lever `psi` is — **#231's to measure**, not this record's to assume.

**That 8.2pp is withdrawn by the amendment below.** It is left standing here,
struck rather than deleted, because the run records and session logs that quote
it are evidence of what was believed on the day.

## Amendment — 2026-08-12: only the bench half is ever swept

The amendment above doubled for the two language arms and did not halve for the
split. It counted **every authored problem**, and half of them are never
dispatched.

`tools/bench/split.py` assigns each admitted problem to the bench half or the
reserve half from a salted hash of its id.
[`docs/bench-design-2026-08-10.md`](../bench-design-2026-08-10.md) states the
reserve is *"never swept in this lane: its representativeness comes from the
construction, its difficulty is never measured here, and no rig tier serves
it,"* and this record's own Consequences say *"the bench never depends on it."*
It is #222's training material. The responsiveness run swept **135 bench-half
ids and no reserve ids**, which is the rule working as designed.

So an authored problem enters the statistic only if the split sent it to the
bench. `f1` stands at 280 authored — **149 bench, 131 reserve**.

> **DECIDED (2026-08-12, owner).** The denominator is **paired cells that are
> actually swept** — bench-half problems, both arms. The reserve is authored
> material and never instrument material, so it is counted in neither the MDE
> nor any sizing figure.
>
> This corrects the amendment above rather than replacing it: a problem is still
> worth two cells. It is worth **zero** if the split sent it to the reserve.

Re-derive with `uv run python tools/bench/redundancy.py --section denominator`.
At `psi_draw` = 0.659 and the realized 53.2% bench share:

| authored | bench half | swept cells | MDE |
|---:|---:|---:|---:|
| 280 (today) | 149 | 298 | **13.4pp** |
| 400 | 213 | 426 | **11.3pp** |
| 800 | 426 | 852 | 8.0pp |

**The two errors nearly cancel.** Doubling for arms without halving for the
split returns almost exactly the 11.8pp the previous amendment was written to
dispose of. **The completed 400 misses D5's +5 to +8pp rather than sitting at
its edge**, and 800 swept cells needs roughly **790 authored problems**.

This is one defect appearing a third time in one chain. This record exists
because D5 *"stated the number without stating its denominator"*; the amendment
above records that the ambiguity *"survived one level down"*. It survived two,
and Decision (2)'s *"~400 paired problems per model measured"* is ambiguous in
exactly the place that matters — it fixes which **model** is measured and never
says whether the **problems** counted are the ones dispatched.

**What this amendment does not decide.** Three questions follow from it and none
is settled here:

1. Whether the 400 is re-read as 400 *bench-half* problems (≈790 authored) or
   the target resolution is re-priced against what 400 authored actually buys.
2. Whether the remaining problems are assigned to the bench half by a declared,
   prospective change to the split — which would cost the halves their
   exchangeability, the *"difficulty-representative by construction"* property
   #222 wanted.
3. Whether the reserve continues to be authored to the instrument's bar at all.
   [`docs/bench-sourcing-2026-08-10.md`](../bench-sourcing-2026-08-10.md)
   justifies adopt-nothing by the bench being *"a measurement instrument"* whose
   material must be non-public by construction; the reserve is not an
   instrument, and it consumes 47% of every tranche.

All three turn on the real per-lever `psi`, which is **#231's to measure**. At
`psi` = 0.35 the same 400 authored resolve ~8.2pp and none of the three binds.
**Nothing about the campaign's size should be decided before #231 reports.**

Derivation and limits:
`records/sessions/lane/225/2026-08-12-screen-and-denominator-adar.md`.

## Consequences

- **The 1.5B is measured before it is designed for.** It has never been swept.
  Two bands were designed for the 3B from an inherited rate–size mapping and
  both undershot; designing a third for a model with no local anchor would be
  the same mistake with a smaller model. See ADR-0023.
- **A band aimed at the floor will put larger models high, possibly at their
  ceiling.** That is expected under (3) and (4): the existing 220 already
  provide the upper range, and a model that ceilings on the floor band is
  measured on the top of the ladder instead.
- **`tools/bench/strata.json` band blocks are steering bands, not strata.**
  Nothing in this record turns g0a/g0b into stratum points, and #224 must not
  read them as any.
- **The reserve half keeps its equal size.** Nothing here changes #222's
  capacity; the bench never depends on it. **That last clause is load-bearing
  and was read too narrowly for a day** — because the bench never depends on the
  reserve, reserve problems are not instrument material and cannot be counted
  toward the 400. See the 2026-08-12 amendment on swept cells.
