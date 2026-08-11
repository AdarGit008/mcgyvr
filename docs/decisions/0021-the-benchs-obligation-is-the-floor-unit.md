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
  capacity; the bench never depends on it.
