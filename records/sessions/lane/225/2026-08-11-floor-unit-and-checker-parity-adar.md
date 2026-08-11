---
record: session/3
lane: lane/225
agent: adar
started: 2026-08-11T15:00:00Z
---

# Session — lane/225 — 2026-08-11 (the floor unit, the checker defect, four ADRs)

## Did

The campaign was paused on the owner. This session did not restart it. It
settled the questions the pause was for, landed the decisions as records rather
than as session prose, and fixed a defect in the instrument that would have
corrupted every ts-vs-py contrast the campaign draws.

## The owner's seven rulings, and where they landed

| ruling | record |
|---|---|
| measure the smallest workforce unit or you cannot use it; the 1.5B is the floor unless ruled out explicitly | ADR-0021 |
| ~400 paired problems **per model**, benches overlap, floor first, ceiling deferred | ADR-0021 (amends ADR-0019 D5) |
| a lever is a feature, not a difficulty knob | ADR-0022 |
| measure the bench stock — no rendered conditions during calibration | ADR-0022 |
| reach 30–50% by authoring simpler problems | ADR-0023 (re-aimed: by **behaviour count**, not size) |
| read prior art before generating — wisdom only, no public datasets | ADR-0023, `docs/bench-shape-prior-art-2026-08-11.md` |
| srv1 is small-model capacity; srv2 is the measurement rig | ADR-0024 |

The ceiling ruling — the ladder may one day reach a 20B/30B MoE on srv2, and
the floor matters more — is recorded in ADR-0021 as a deferral rather than a
plan.

## The correction the audit produced immediately

**The 1.5B had been measured, and this session's first plan said it had not.**
`tools/power/report.py` holds nine sweeps of it on d1: greedy **7/20 = 35.0%**,
zero drift across 8 runs, 95% byte-identical. What it lacked was a measurement
on *current* material. That is a narrower gap than the plan claimed, and it
supplied an anchor the plan did not have: on d1 the ladder reads 1.5B 35% / 3B
50% / 7B 70%.

## MBPP+ on the floor unit

`records/measurements/mbpp-plus-1.5b-2026-08-11/`. Same instrument, host, cap
and decode as the 3B's number, so the two are one comparison.

| | 1.5B | 3B | gap |
|---|---:|---:|---:|
| MBPP (base) | 67.2% | 70.6% | 3.4pp |
| MBPP+ (plus) | **56.9%** | 60.6% | **3.7pp** |

**The model gap widens with problem shape:** 3.7pp at MBPP shape, 15.0pp at d1
shape, and at bench shape the 3B already floors at ~4%. Two consequences, one
settled and one opened.

*Settled:* the 30–50% aim is not out of reach for the floor unit. MBPP+ shape is
if anything too *easy* for it. The aim was never unreachable — it was
unreachable at the shape the bench was authored in.

*Opened:* a band the floor unit can be measured on may not separate it from the
3B. That satisfies ADR-0021's obligation and does not by itself satisfy #224.
Those are two requirements and this is the first evidence one set may not meet
both. Owner's call, recorded as such.

## The defect: 104 py checkers scoring an unstated behaviour

Found while deriving the shape table. Every py checker used a `rejects()` helper
catching **only `ValueError`**; the ts twins use `assert.throws(fn, Error, ...)`,
which any `Error` subclass satisfies. The contracts say "reject … with an error"
and never name a type. So the idiomatic Python answer to "reject a non-string
argument" — a `TypeError` — failed the py arm and passed the ts one, on problems
that are supposed to be the same problem twice.

Uniform across all 214 blocks in 210 files (104 bench, 106 reserve), so one
mechanical change did it. **109/109 py references still pass their own
acceptance.** `admissions.jsonl` digests every problem file, so each affected
entry now carries an `amended` record naming the reason; `admit.py --verify`
passes. Two tests pin the rule in *both* directions — the generator writes new
checkers from the same template, so this is the seam a future tranche would
reintroduce it through.

## The re-grade: recovering every py rate at zero model cost

`tools/bench/regrade.py`. Acceptance is a post-hoc check on saved output, so a
corrected checker can re-score completions already on disk without a token. The
original `results.jsonl` is never rewritten — it records what was measured under
the checker of the day; the re-score lands beside it in `regrade.jsonl` with the
checker digests it ran under.

3,662 rows across all 18 bench measurement directories. **40 cells changed
verdict. Every one is py, every one is a gain, and every ts arm moved +0.** The
ts arms were included precisely as a control: their checkers did not change, and
nothing moved. That is the harness validating itself.

`ablation_report.py` gained `--rows {as-measured,regraded}`, defaulting to
as-measured and naming its choice in the header. Neither file is silently
preferred, and a missing re-score reads as an absent cell rather than falling
back.

## Instrument identity: the serving build

ADR-0024's mechanism. `run.json` now records `serving_build`, and a resume into a
directory served by a different build is refused exactly as a changed
temperature is. **The recorder probes it rather than taking it from a caller** —
`--condition` was a caller-supplied identity field, it reached dispatch and never
`record_run`, and eight manifests described a render nobody had run. Manifests
written before the field adopt the current value rather than refusing, since the
build those runs used is not recoverable either way.

The live confound this closes: srv1 was on ollama 0.32.4 and srv2 on 0.32.5
while the scaffold ablation ran the 3B on one and the 7B on the other.

## The trunk decision audit

Filed as **#243**, as a procedure rather than a list — a hand-typed inventory
would drift before the audit ran, which is the failure mode #234's amendment
convention exists to fight. The rule it enforces: *every trunk decision lands in
an ADR, a CLM, or an issue amendment; nothing decision-bearing lives only in a
session record.* It runs twice, mid-trunk and at exit.

Mid-trunk pass, mechanical half, all re-derived: `power/report.py`,
`ablation_report.py`, `admit.py --verify`, and all in-repo CLM citations resolve.
ADR-0019's "eleven of twelve" already carries an in-repo Correction dated
2026-08-10 — the audit found it *already amended*, which is the system working.

## Not done, and deliberately

The campaign stays paused. No problems were authored, no band was re-aimed. The
generator brief keyed to a behaviour budget (2–4 behaviours, ≤1 error path) is
written as a target in the shape document and is the owner's gate to open.

`MIN_ASSERTIONS = 5` was flagged in ADR-0023 as a possible conflict with a 2–4
behaviour budget. It is not: it counts assertions, not behaviours, and a
3-behaviour problem carrying 5–8 assertions is already admissible.
