# ADR-0030 — the pre-gate heuristic verifier is refuted by our own replies

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none
Date: 2026-08-16

## Context

The prior-art dig
([`docs/hybrid-orchestration-prior-art-2026-08-16.md`](../hybrid-orchestration-prior-art-2026-08-16.md))
proposed adding a layer this project does not have: a rule-based verifier that
scores a cheap model's *reply text* before anything expensive runs. NadirClaw's
version checks refusal patterns, uncertainty patterns, JSON validity and length,
in under a millisecond with no weights, and returns a structured score with a
`reasons` list. The observation behind the proposal is accurate — our gate is
deterministic over *code*, and there is no text-response layer above it.

The proposal is cheap, it is architecturally clean, and it is clearly useful in
the product it comes from. The question is what it would catch here.

That question is answerable without building anything, because this project has
kept every reply it has ever scored.

## The measurement

All 23,902 candidates recorded across 31 run directories under
`records/measurements/`, cross-tabulating the runner's transport-level
`stop_reason` against the reply parser's `parse_error`:

| stop_reason | parse_error | n | share |
|---|---|---:|---:|
| complete | — | 23,483 | 98.25% |
| truncated | `incomplete-reply` | 386 | 1.62% |
| complete | `unterminated-fence` | 16 | 0.067% |
| complete | `no-fenced-block` | 10 | 0.042% |
| complete | `ambiguous-blocks` | 7 | 0.029% |

The re-derivation command is in the prior-art record. Three results follow.

**1. Truncation is already detected, at the transport layer, for free.**
`truncated` and `incomplete-reply` are not correlated — they are the same event.
The partition is exact: every truncated reply carries that parse error, no other
row carries it, across all 23,902. A heuristic verifier's length check would
produce a second name for a fact the runner already reports. This is #212's
finding arriving from the other direction: what reads as a reply-format problem
is the output cap.

**2. The entire remaining surface is 33 replies — 0.138%.** Unterminated fence,
no fenced block, ambiguous blocks. That is the ceiling on what a reply-shape
heuristic could newly catch, before asking how many of those 33 it would catch
correctly.

**3. There is no refusal class.** Refusal and uncertainty patterns are the core
of the proposed verifier. In 23,902 recorded replies this project's taxonomy has
never needed the category. The floor models we serve do not refuse coding
contracts; they truncate, or they emit something the gate rejects.

## Why the comparison is the point

The proposal aims at a stage of the pipeline where we already have a measured
intervention. #246 — normalising worker output before judging it, rather than
scoring its shape — is measured at **+13.7pp** over the same class of run data.
It works because `ruff format --diff` already computes the exact fix, the gate
discards it, and a model call is then spent asking a worker to make an edit we
had in hand.

Two proposals, the same stage, a ceiling of 0.138% against a measured +13.7pp.
The useful move at this stage is to *repair* the reply, not to *rate* it.

## Decision

> **DECIDED (2026-08-16, owner).**
>
> 1. **No pre-gate heuristic verifier is added.** Its measured ceiling here is
>    0.138% of candidates, its principal signal duplicates `stop_reason`, and its
>    refusal checks have no observed population.
> 2. **The 33 shape failures are the reply parser's business, not a new
>    layer's.** #254 already reports the parser refusing a legal fence; whatever
>    is wrong with fence handling is fixed there, in the one place that reads a
>    reply, and not by a second component scoring the same text.
> 3. **This measurement is the standing answer.** Any future proposal for a
>    reply-scoring layer states what it would catch as a fraction of recorded
>    candidates, re-derived on the data at that time, before it is designed.
> 4. **A pre-gate stage is not closed — #246 is that stage.** The rejection is of
>    scoring reply shape, not of doing work before the gate.

## Consequences

**A cheap, sensible-looking layer is refused with a number rather than an
argument.** That is the outcome to notice. The proposal was well-formed and
would have been reasonable to accept on judgement; the population it targets
simply is not there, and only counting showed it.

**The refusal is conditional on a population, not on principle.** If a future
worker tier does refuse — a hosted model with content policies, a reasoning
model that answers in prose — the category appears in the data and this record
is reopened by the rule in decision 3. Nothing here says refusal detection is
worthless; it says we have never had a refusal.

**The general lesson is cheaper than the specific one.** This project records
every reply it scores, which meant a proposal about reply text could be settled
in one query against 23,902 real cases instead of a pilot. That is worth doing
first, every time a proposal is about a class of model output — the data is
already sitting in `records/measurements/`.
