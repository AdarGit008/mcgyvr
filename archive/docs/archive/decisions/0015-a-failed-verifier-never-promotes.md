# ADR-0015 — a failed verifier never promotes: instrument failure fails closed

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-06

## Context

The verifier does not exist yet. #179 is the issue that will shape it, and its
fifth question asks what happens to an unparseable verdict; the eighth —
raised in the owner's own comment — asks whether the verifier may blame the
instrument rather than the work. This record answers the policy half of both
now, before the verdict shape is built, for the reason the comment itself
gives: the answer is cheaper before implementation than after.

The question, in plain terms: sometimes the judge breaks rather than the work.
The verifier's reply does not parse; the verifier's process crashes; the
verifier cannot be reached at all. Something must still happen to the change
that was awaiting judgment, and the #175 survey found this decided, in
production, four times — with a genuine split:

- **OpenHands** (`OpenHands/software-agent-sdk` @ `b35c2fee8`): the
  `EnsembleSecurityAnalyzer` fuses child analyzers by maximum severity, and a
  child that *raises* contributes `HIGH` — with the stated reason that this
  "prevents a broken analyzer from silently degrading safety".
- **SWE-agent** (@ `3ea751c0`): the reviewer samples five times, discards
  replies outside `score_range` as uninterpretable, subtracts
  `reduce_by_std × std`, and returns `accepts=[-100.0]` when nothing parses.
  The instrument is checked by resampling itself and is forbidden to abstain.
- **auto-code-rover** (@ `585d3e63`): every parse exception becomes `None`,
  `run_with_retries` retries up to five times, and an exhausted budget raises
  `InvalidLLMResponse` — fail-closed, and bounded by a declared retry count.
- **open-swe** (`langchain-ai/open-swe`, read 2026-08-06, suite clean at 1,672
  passed): `settle_review_check.py` returns a conclusion of `neutral`, on the
  stated ground that the review not completing is reviewer infrastructure
  failing, not the PR failing.

Three fail closed; one declines to charge the work for the instrument. Both
positions are defensible, and open-swe's reasoning is not wrong — the author's
change genuinely is not the cause of our reviewer crashing. The decision
between them is who bears the cost of that truth: the work waits, or the
gate's meaning erodes.

Two prior findings weigh in. RA.Aid (ADR-0014's evidence) is what a checker
that fails invisibly costs: its gate crashed for a year and everything shipped
as if approved. And within mcgyvr, `VERIFIED` is designed to be reachable only
by a verifier's positive act — its absence is a label, not a failure. A policy
under which instrument failure quietly yields the same result as "no verifier
configured" would make a persistently broken verifier indistinguishable from a
deliberately absent one, which is RA.Aid's failure mode arriving through the
side door.

## Decision

**When the verifier fails, the change is not promoted.** An unparseable verdict
after the declared retry budget, a crashed verifier, an unreachable verifier
where policy requires one — none of these may result in the change advancing as
if verified, and none may result in it advancing under a label that an absent
verifier would also produce. In effect: fail closed. A broken judge never
approves, and never steps aside.

**The record says what actually happened.** Fail-closed is a policy about
*effect*, not permission to lie in the ledger. Per ADR-0014's channel
discipline, *rejected by the verifier* and *the verifier never ran* remain
distinguishable wherever the outcome is recorded — the escalation that follows
may be the same, but the record names the instrument when the instrument is
what failed. open-swe's insight is kept in the ledger and refused in the
effect: the work is not blamed, and it also does not ship.

Two riders:

- **Retries are declared, then exhausted, then final.** The budget under which
  a malformed verdict is re-requested is configuration, like every other
  ceiling. What this rule governs is the step after the budget: there is no
  fourth state where the system keeps trying or quietly gives up.
- **This does not decide the verdict's shape.** The eighth question's other
  half — whether the verifier may return "the patch is right and the
  demonstrating instrument is wrong" as a verdict about the *work* — is a
  question about what the verifier reads and says, and it stays open on #179.
  This record covers the verifier's own failure only.

## Rejected: neutral — instrument failure yields no verdict

open-swe's position, and the principled case for it is real: charging the work
for the infrastructure's failure is a false attribution, and a three-valued
outcome channel (which ADR-0014 already requires) can carry "could not tell"
honestly.

It loses on what happens downstream of "no verdict". Either neutral blocks
promotion — in which case it is fail-closed with a more honest name, and this
record already requires the honest name in the ledger — or neutral permits
promotion under a label, and then every consumer of that label must treat it
as unverified, forever, without exception. That is a discipline imposed on all
future callers to preserve a distinction the promotion decision ignores. And it
creates the degradation path: a verifier that breaks on Monday produces
neutral-and-accepted runs all week, each individually reasonable, none
distinguishable in effect from having no verifier — RA.Aid's year-long silence,
re-derived. The cost of fail-closed is a stalled lane and a visible escalation,
which is the failure mode that gets fixed *because* it is expensive.

## Rejected: fail open for infrastructure faults, closed for model faults

A crashed verifier process is our fault; an unparseable verdict is the model's;
one could fail open on the first and closed on the second. This loses because
the boundary between the two is exactly where the hard cases live — a timeout
is which? a refusal is which? (#174: a well-formed refusal defeated a syntax
gate) — and a policy that depends on classifying the failure correctly fails
open precisely when the failure is novel enough to be misclassified. One rule,
no taxonomy, nothing to get wrong at 2am.

## Rejected: defer until the verifier is implemented

The verifier does not exist, so nothing enforces this record today, and the
decision could wait for working code. It loses on ordering: the verdict shape,
the retry budget, and the escalation path all depend on which way this goes,
and #179's comment already identified that the eighth question is cheaper
answered now than retrofitted. Four production systems made this decision;
none of them recorded why; two of them (SWE-agent's `-100`, OpenHands's
`HIGH`) encode it as magic values a reader must reverse-engineer. Writing the
policy before the code is what a decision record is for.

## Consequences

- **#179's fifth question is answered** (fail-closed, after a declared retry
  budget) **and the eighth is half-answered** (the instrument's failure is
  never charged to the work in the record, and never excuses the work in
  effect). The verdict-shape half stays open on the issue.
- **The verifier's failure modes need names in the outcome channel** when it is
  built: at minimum *verified*, *rejected*, and *verifier-failed*, with the
  third never promoting. The implementation inherits ADR-0014's rule that no
  interface collapses these to fewer values than the caller must distinguish.
- **A broken verifier stalls the lane loudly.** That is the accepted cost, and
  it is the design working: the expensive, visible failure is the one that gets
  fixed, and the silent one is the one this record exists to prevent.
- **What this gives up:** throughput under verifier outage. An install whose
  verifier is down ships nothing that policy says needs verification, even
  when every change would have passed. Accepted; the alternative spends the
  gate's meaning to buy availability.
- **What this bets on:** that no future caller legitimately needs
  "verifier failed, promote anyway". If one appears, it must arrive as an
  amendment to this record with the case attached — not as a fourth enum value
  added where nobody is looking.
