# What shape of problem a 1–3B model solves (#225, ADR-0023)

**This document adopts no problems.** Under the adopt-nothing sourcing verdict
and ADR-0020's blocklist, HumanEval's 164 ids and MBPP+'s 378 remain barred
from the campaign, and a public set cannot be made non-public by construction.
What is taken here is *shape*: how many behaviours a problem specifies, how many
error paths, how long its spec runs, how many tests judge it — paired with the
rates small models achieve on it. Those numbers parameterise the generator
brief. Nothing else crosses.

## The question

#225 aimed a band at 30–50% for the 3B twice and undershot both times, steering
reference size and assertion count. ADR-0023 replaced the dial: difficulty is
the count of independently specified behaviours that must all be simultaneously
correct. This document supplies the numbers that dial is set from, and it does
so for the model ADR-0021 makes the floor — `qwen2.5-coder:1.5b`.

## Locally derived: the two shapes, measured

Re-derivable. The MBPP+ column is computed from
`~/.cache/evalplus/MbppPlus-v0.2.0.jsonl` on srv1; the bench columns from
`tools/bench/tasks/{ts,py}/*/`.

| | MBPP+ | bench-ts | bench-py |
|---|---:|---:|---:|
| problems | 378 | 109 | 109 |
| assertions per problem (median) | **3** | **13** | **11** |
| error-path assertions (median) | **0** | **5** | **6** |
| problems with ≥ 1 error path | 1 of 378 (**0.3%**) | 104 of 109 (**95%**) | 103 of 109 (**94%**) |
| spec prose words (median) | **15** | **146** | **146** |
| reference solution lines (median) | **3** | **27** | **19** |

The same 3B reads **70.6% base / 60.6% plus** on the left column and roughly
**4%** on the right two.

## The datum that identifies the dial

EvalPlus's "plus" arm tests **the same 378 problems** against a median of **105
generated inputs** instead of 3 — a 35-fold increase in assertions — and costs
the 3B **10pp** (70.6 → 60.6).

So assertion *count* is not what is expensive. Those 105 inputs re-test the same
one or two behaviours. The bench's 13 assertions test thirteen **different
specified behaviours**, five of them error paths, under all-or-nothing
acceptance. Thirty-five times the assertions over the *same* behaviours costs
10pp; four times the assertions over *different* behaviours costs ~57pp.

That is the whole of ADR-0023 in one paired comparison, and it explains both
failed re-aims: they cut lines and assertion counts and left the multi-rule,
multi-rejection spec shape intact.

## Reported elsewhere: where 1–3B models land, and on what shape

These are **reported figures, not re-derived here**, and they are used only to
locate a shape. Where a number decides anything it is marked.

| model | params | HumanEval pass@1 | MBPP pass@1 | source |
|---|---:|---:|---:|---|
| **Qwen2.5-Coder-1.5B** | 1.5B | **~43.3%** | **~50.0%** | [Qwen2.5-Coder Technical Report](https://arxiv.org/html/2409.12186v3) |
| phi-1 | 1.3B | 50.6% | 55.5% | [Textbooks Are All You Need](https://arxiv.org/abs/2306.11644) |

The first row is the floor unit itself. **A 1.5B model reads 43–50% on
HumanEval/MBPP-shaped problems** — at or above the 30–50% aim two re-aims
missed for a larger model on this bench. The aim is not out of reach for the
floor unit; it is out of reach at the bench's current problem shape.

### And then we measured it ourselves

`records/measurements/mbpp-plus-1.5b-2026-08-11/` — MBPP+ on the floor unit, on
the same instrument and host that produced the 3B's number:

| | 1.5B | 3B | gap |
|---|---:|---:|---:|
| MBPP (base tests) | **67.2%** | 70.6% | 3.4pp |
| MBPP+ (base + extra) | **56.9%** | 60.6% | **3.7pp** |

Two things follow, and the second is the one worth arguing about.

**The reported row understates what we measure.** 67.2% base against a
published ~50.0% MBPP. Prompting, sanitisation, decode and quantisation all
differ, and the direction is a caution about the whole "reported elsewhere"
section: those figures locate a *shape*, and they are not a scale anything
should be calibrated against. The locally derived numbers are.

**The model gap widens with problem shape.** 3.7pp on MBPP+, 15.0pp on d1
(35.0% vs 50.0%), and at bench shape the 3B already floors at ~4%. Capability
differences between a 1.5B and a 3B are nearly invisible where one thing has to
be right and decisive where thirteen do. That is ADR-0023's thesis arriving
from the model side rather than the problem side — and it means a band placed
where the floor unit is measurable may not separate the floor unit from the rung
above it. See the measurement's own `conclusion` field; it is a question for the
owner and not settled here.

The shape those rates are earned on, per the sets' own documentation: one
function, a docstring or one-line prose spec, and **~7.7 unit tests per task for
HumanEval** ([MultiPL-E, arXiv 2208.08227](https://arxiv.org/pdf/2208.08227)),
**3 per problem for MBPP** — which matches the median this project derived
locally, so the two agree where they can be checked against each other.

**MultiPL-E is the one worth naming for the paired arm.** It translates
HumanEval and MBPP into 22 languages including TypeScript, and it translates the
*tests along with the prompts*, so test count per problem is preserved across
languages. That is the same paired-arm discipline this bench uses, arrived at
independently, and it is evidence that a ts/py pairing does not have to change
problem shape between arms.

## What this sets the brief to

| dial | MBPP-shaped (1.5B reads 43–50%) | bench today (3B reads ~4%) | **floor band target** |
|---|---:|---:|---:|
| specified behaviours | 1–2 | ~8–13 | **2–4** |
| error paths | ~0 | 5–6 | **≤ 1** |
| spec prose words | 15 | 146 | **40–70** |
| reference lines | 3 | 19–27 | **8–14** |

The target column sits deliberately *above* the MBPP shape and far below the
bench's. The floor band should not be MBPP — a set the floor model reads at
~50% with contamination in it is not an instrument — but it must be nearer that
shape than to thirteen simultaneous behaviours.

## Limits

- **The reported rates are not verified here.** They locate a shape; no decision
  rests on their exact value. The local MBPP+ measurement of the 3B (70.6/60.6)
  is the one figure in this document produced by this project.
- **Contamination cuts against the easy end, not for it.** MBPP's gold solutions
  appear in pretraining corpora (12.2–20.8%, per the caveat already recorded in
  `records/measurements/mbpp-plus-3b-2026-08-10/run.json`), so the 43–50% figures
  are upper bounds. A shape target derived from them is therefore *optimistic*,
  and the band should be checked by measurement rather than trusted.
- **This is a search over what we found, not over what exists.** The sets named
  here are the ones this read surfaced; nothing in it supports a claim that no
  other set is relevant.
- **Shape is necessary and not sufficient.** The 1.5B's rate on a 2–4-behaviour
  band is an empirical question that only a sweep answers, which is why
  ADR-0023 requires the floor unit located before the band is authored.
