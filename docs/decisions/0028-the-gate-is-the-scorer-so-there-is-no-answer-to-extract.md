# ADR-0028 — the gate is the scorer, so there is no answer to extract

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none
Date: 2026-08-16

## Context

The prior-art dig
([`docs/hybrid-orchestration-prior-art-2026-08-16.md`](../hybrid-orchestration-prior-art-2026-08-16.md))
named one proposal its highest-value transfer: port emerge's tag-aware
`compute_accuracy` and its negative tests into this project's bench scoring
layer, "because mcgyvr's own bench is building exactly this measurement
apparatus."

The function is real and it is careful. It scores a model's free text against an
expected answer, with a matcher per benchmark family: MMLU wants a standalone
letter, so `"Both A and C"` must not count as `B`; GSM8K wants the last number,
so `"230"` must not count as `23`. Its tests assert both of those explicitly.

It is good work aimed at a real hazard. The hazard is not ours.

## Why it does not apply

**Our scorer is not a matcher.** #113 made `Gate.run` the bench's scorer — the
same object that decides a production verdict — so a bench result and a shipped
result are the same verdict computed the same way. `Gate.run` does not compare a
reply to an expected string. It applies a change and runs ordered checks over
it: scope, secrets, structured data, syntax, structural hazards, lint, format,
semantic resolution, and the contract's own acceptance commands. Nothing in that
chain has an "expected answer" to be fooled by.

**There is no task shaped like the ones the matcher defends.** MMLU and GSM8K
are multiple-choice and short-numeric benchmarks. This project's corpus is
authored contracts with reference solutions and checkers
([ADR-0021](0021-the-benchs-obligation-is-the-floor-unit.md),
[ADR-0023](0023-difficulty-is-behaviour-count.md)), admitted through
`tools/problems/admit.py`. A substring scorer has nothing to attach to.

**We already made the decision the tests encode.** `escalate.py:148` states the
parsing rule for reading a model's text: "anchored parsing, no substring
search." That is the same conclusion emerge reached, written down here first,
for the same reason.

So the proposal is not wrong about the danger. It is wrong that this project has
the surface where the danger lives.

## Where the danger does live

One layer up, and it is open.

Reading a model's reply is not scoring it, but it is still matching. The reply
parser has to find a code block in prose, and #254 reports it refusing a legal
fence and reporting the refusal as truncation. That is precisely the class of
bug `"230" ≠ "23"` is a test for: a matcher that is nearly right, failing on the
input a careful negative test would have caught.

The transferable thing is therefore not the function. It is the habit of writing
the negative case down as an assertion — pinning what must *not* match, beside
what must.

## Decision

> **DECIDED (2026-08-16, owner).**
>
> 1. **`Gate.run` remains the bench's only scorer.** No free-text
>    answer-extraction scoring is added beside it. There is no task type here
>    that would use one, and adding a second scorer would reintroduce the
>    bench/production split #113 closed.
> 2. **The negative-test discipline is adopted where it applies** — the reply
>    parser, #254. Every matcher in the reply path states what it must not match,
>    as an assertion, not as a comment.
> 3. **A future benchmark family that does need answer extraction reopens this
>    record** rather than quietly adding a matcher. If the corpus ever admits a
>    task whose verdict is not a gate verdict, that is an ADR-sized change to
>    what the bench measures.

## Consequences

**Nothing changes today.** The bench keeps one scorer; #254 gains a test
discipline it can use whether or not it adopts anything else.

**The "highest-value take" was worth reading anyway.** It cost one verification
pass to establish that the most enthusiastic recommendation in the dig had no
attachment point here — and that verification produced the #254 salvage, which
is a real if smaller gain. A brief that reads two repositories and compares them
at the level of module names will keep producing this shape of error, because
"both projects have a scoring layer" is true and useless.

**The rule is narrow on purpose.** This record does not say free-text scoring is
bad, or that emerge is wrong to have it. It says that a scorer without a
matcher cannot import a matcher's defences, and that our scorer has no matcher.
