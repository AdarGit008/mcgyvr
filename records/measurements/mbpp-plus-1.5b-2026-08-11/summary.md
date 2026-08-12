# MBPP+ on the floor unit (#225, ADR-0021): locating the 1.5B before designing for it

ADR-0021 makes `qwen2.5-coder:1.5b` the smallest unit of the workforce and
therefore the bench's obligation. ADR-0023 requires it *located* before a band
is authored for it, on the grounds that two bands were designed for the 3B from
an inherited rate–size mapping and both undershot. This is that locator, run on
the same instrument, host, cap and decode that produced the 3B's number, so the
two are one comparison rather than two.

## The number

| | 1.5B | 3B | gap |
|---|---:|---:|---:|
| MBPP (base tests) | **67.2%** | 70.6% | 3.4pp |
| MBPP+ (base + extra) | **56.9%** | 60.6% | **3.7pp** |

Greedy, one seed, cap 768, EvalPlus 0.3.1 via Ollama 0.32.4 on srv1:11434.
Codegen 7m14s, evaluate ~18s.

## The finding: the model gap widens with problem shape

| instrument | 1.5B | 3B | gap |
|---|---:|---:|---:|
| MBPP+ (plus) | 56.9% | 60.6% | 3.7pp |
| d1 (bundle-ts, greedy) | 35.0% | 50.0% | 15.0pp |
| bench (ts/py) | not swept | ~4% | — |

At MBPP shape the two models are nearly the same model. At d1 shape the 3B is
half again better. At bench shape the 3B already floors, so the 1.5B has
nowhere to be.

This is the same story ADR-0023 tells from the other side. MBPP specifies one
or two behaviours per problem and essentially never an error path (1 of 378);
the bench specifies eight to thirteen with five error paths, all-or-nothing.
Capability differences between a 1.5B and a 3B are invisible where only one
thing has to be right and decisive where thirteen do.

## What it settles, and what it opens

**Settled: the 30–50% aim is not out of reach for the floor unit.** MBPP+ shape
is if anything *too easy* for the 1.5B — 56.9% sits above the band. That places
ADR-0023's behaviour budget correctly: 2–4 specified behaviours is *harder* than
MBPP's 1–2 and far easier than the bench's 8–13, which is where a 30–50% read
should fall. The aim was never unreachable; it was unreachable at the shape the
bench was authored in.

**Opened: a band the 1.5B can be measured on may not separate it from the 3B.**
On MBPP the two differ by 3.7pp. A floor band placed near that shape inherits
the problem — it would satisfy ADR-0021's obligation (the floor unit is
measurable, which is what makes the bench usable) while failing to give #224 a
band where models separate.

Those are two different requirements and this measurement is the first evidence
they may not be met by one set. It is a question for the owner, not a conclusion
of this record. The honest options are a floor band that measures levers on the
floor unit plus a separate harder band that separates models — which is what
ADR-0021's overlapping-benches clause already permits — or a single band placed
deliberately at the point where separation begins, which is a measurement nobody
has yet made.

## Limits

- **Contamination inflates both rows equally.** MBPP's gold solutions appear in
  pretraining corpora (12.2–20.8%); 56.9% is an upper bound. The comparison
  survives because whatever contamination is worth, it is worth to both models.
- **MBPP+ is a locator, never an instrument.** Its 378 ids stay on the campaign
  blocklist (ADR-0020) and nothing is adopted from it.
- **The 1.5B still has no measurement on current bench material.** This locates
  it against a shape reference; it does not tell us what it reads on the bench.
  Given the 3B reads ~4% there, the expected answer is near zero, which is the
  point.
