# ADR-0027 — a routing policy is adopted only if it is inspectable here and measured here

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none
Date: 2026-08-16

## Context

A prior-art dig across five orchestration and routing projects
([`docs/hybrid-orchestration-prior-art-2026-08-16.md`](../hybrid-orchestration-prior-art-2026-08-16.md))
proposed three ways to decide, before dispatch, which rung a task should start
on:

* a **deterministic keyword scorer** — LiteLLM's `ComplexityRouter`, weighted
  regex scoring over token count, code presence, reasoning markers and technical
  terms, `<1ms`, zero tokens;
* a **declarative rule engine** — NadirClaw's priority-ordered YAML with
  `force_escalate` / `set_threshold` / `force_cheap`;
* a **trained per-query router** — microsoft/best-route-llm's DeBERTa pair ranker
  over candidate models, labelled by a reward model.

All three answer a question this project has already opened. #16 — risk
classification and routing floors — states the shape: a floor must be decided
"deterministic, from task type, prompt content and scope, never a model call",
and it has to be **inspectable**, because a floor "does not fire once — it fires
on every task that classifies into that level, for as long as the policy
stands."

So the proposals are not new ground. They are three candidate *fillings* for a
slot whose walls are already built. What matters is whether any of them can be
adopted on the evidence they carry.

## What the evidence turned out to be

**The keyword scorer is uncalibrated.** Its keyword lists are real and modest
(45 code / 19 reasoning / 31 technical / 29 simple terms). Its decision
constants — `DEFAULT_DIMENSION_WEIGHTS`, `DEFAULT_TIER_BOUNDARIES`,
`DEFAULT_TOKEN_THRESHOLDS` — carry no accuracy, AUROC or calibration figure
anywhere in the 1,974-line module. Its sibling in the same package is candid
about the same condition: "All magic numbers are first-pass guesses … Expect to
retune after first 1000 sessions of real traffic." The complexity router is in
that condition without the sentence.

**The rule engine's domain knowledge is self-reported.** Its most interesting
artifact is a trust map keyed to where a checker is weak — verifier AUROC ~1.0
on factual recall, ~0.65 on code generation, the weak domains encoded as
force-escalate rules. The eval harness that produced those numbers is not
shipped.

**The trained router's headline does not exist.** The figure the dig carried —
"22% fewer large-model calls" — is in neither the repository nor either cited
abstract. The two real figures are 60% cost reduction (BEST-Route) and 40% fewer
large-model calls (HybridLLM), and the repository ships no eval artifact to
re-derive either.

## Why this is a decision and not a shrug

Two reasons make it worth a record rather than a closed tab.

**We already have a measured definition of difficulty, and it disagrees in
kind.** [ADR-0023](0023-difficulty-is-behaviour-count.md) decided that difficulty
is *the count of independently specified behaviours that must all be
simultaneously correct*, and explicitly demoted the proxies a keyword scorer
runs on: "Reference size and assertion count are noisy proxies for it and are
not steered directly." A weighted count of code keywords is a proxy of exactly
that family. Adopting it would install a second, competing definition of the
project's most load-bearing quantity, arriving with less evidence than the one
it would sit beside.

**#16's value is measured, not designed.** #16 is blocked by #233, the
combination phase, and says so in its own body: a floor's value comes "not from
judgement" but from the all-on cell — what the cheapest tier can do once every
lever is switched on. A floor written before that number exists is a permanent
ceiling-ward bias set by taste. Importing a vocabulary now does not accelerate
#16; it pre-commits it.

The trained router fails a third test the other two pass. `route.py` exists so
that "a plan is inspectable before anything is spent" — which is what makes
routing reproducible rather than merely deterministic. A DeBERTa classifier
produces a decision no one can read. It is not that it is worse; it is that it
is not the same kind of object.

## Decision

> **DECIDED (2026-08-16, owner).**
>
> 1. **No routing policy is adopted from prior art on the strength of its
>    source's reputation, its latency, or its shape.** It is adopted when it is
>    inspectable in this repository and when its effect has been measured here.
> 2. **The keyword vocabularies are recorded as prior art on #16, not
>    implemented.** They are a seed list for whoever writes the classifier after
>    #233 reports, and they carry no weights, no boundaries and no thresholds
>    across with them.
> 3. **The per-domain verifier trust map is recorded on #16 as a shape**, marked
>    self-reported. Keying a floor to where our *own* checker is weak is a good
>    idea; inheriting someone else's unpublished AUROC table is not.
> 4. **A trained per-query router is out of scope while `route.py`'s
>    inspectability rule stands.** Revisiting it means revisiting that rule
>    first, in its own record.
> 5. **ADR-0023 remains the project's definition of difficulty.** A competing
>    definition may replace it only by measuring better on this project's bench,
>    never by arriving pre-packaged.

## Consequences

**#16 is unchanged and still blocked.** This record adds material to it and
removes nothing. Whoever picks it up after #233 starts with a keyword list they
did not have to invent and an explicit warning that the weights beside it are
guesses.

**A cost is accepted.** LiteLLM's classifier probably does classify most prompts
about right, and we are declining a working artifact in order to wait for a
number. That is the same trade [ADR-0019](0019-the-bar-is-a-reality-floor-and-a-per-lever-rule.md)
made and the same one #189 paid for taking the other way: a plausible lever
adopted without a contrast that could reject it produces a result that decides
nothing.

**The next dig will propose these again.** They are the obvious take from this
corner of the field — LiteLLM's own module credits ClawRouter for the same idea,
so the pattern is already circulating. This record is what makes the second
proposal cheap to resolve: the answer is not "no", it is "after #233, and with
the weights re-measured here."

**Nothing here forbids a deterministic classifier.** #16 requires one. What is
forbidden is shipping someone else's constants as though measuring them were a
formality.
