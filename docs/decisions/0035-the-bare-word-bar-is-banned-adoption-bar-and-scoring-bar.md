# ADR-0035 — the bare word "bar" is banned: adoption-bar and scoring-bar name two decisions

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none — no prior decision changes; this record changes only what future
prose calls two things that are already decided elsewhere
Relates: ADR-0019 (the adoption-bar), ADR-0025 / ADR-0032 / ADR-0033 / ADR-0034
(the scoring-bar), #299 (the misreading this vocabulary helped survive)
Date: 2026-08-17
Issue: #301

## Context

"The bar" names two different decisions in this project, and nothing in the
word says which:

- the effect size a lever must show before it is adopted — ADR-0019's `b`,
  a reality floor plus a per-lever rule;
- the standard a candidate reply is scored against — the rung set and its
  configuration, per language, hashed where it is resolved (ADR-0025, ADR-0032,
  ADR-0033, ADR-0034).

These are not two aspects of one thing. One is a property of the **instrument
and the lever's cost** — a threshold on a measured contrast, parameterised per
lever class, with no fixed number for the cheapest class at all. The other is a
property of the **scorer** — a concrete set of tools and configs that either
ran against a candidate or did not, and whose identity is digested into every
run. They are decided in different records, they move for different reasons,
and an error in one is not even the same *kind* of error as in the other.

The collision has already cost a real misreading. #299 documents how a number
supplied in conversation hardened into "the 5pp bar" and was quoted onward as
the reason n = 400 was not worth buying — a threshold ADR-0019 explicitly
declines to set. That reading survived partly because the one word let a
**sizing outcome** borrow the register of a **scoring standard**: something
fixed, inherited, already decided, and beneath which a result simply fails.
Nothing about "the adoption-bar for a Class R lever is the bench's MDE" invites
that reading; "the bar is 5pp" does.

The cost of the fix is one hyphenated word per sentence. The cost of the
collision was a wrong sizing argument quoted for two days across three
documents.

## Decision

> **DECIDED (2026-08-17, owner).**
>
> 1. **The bare word "bar" is banned in new prose.** A record, issue, PR body,
>    comment or docstring written after this date names the concept it means:
>    **adoption-bar** or **scoring-bar**. Neither concept is ever again called
>    "the bar" alone.
> 2. **adoption-bar** is ADR-0019's `b`: the effect size a lever must show on
>    the bench before it is adopted. It is a reality floor plus a per-lever
>    rule; for a Class R lever the adoption-bar *is* the bench's MDE. It is a
>    parameter, not a number, and #299 stands as the record of what happens
>    when a number is read into it.
> 3. **scoring-bar** is the standard a candidate is scored against: `Gate.run`'s
>    rung set with the configuration actually staged in the scoring workspace.
>    It is per language and never pooled (ADR-0033), it is hashed where it is
>    resolved (ADR-0033), a rung that cannot say what scoring-bar it applied is
>    a refusal (ADR-0034), and the round pin covers its configuration
>    (ADR-0032).
> 4. **The ban is prospective.** Existing ADR titles and bodies, session
>    records, issue histories and quoted sentences are never rewritten — records
>    are history here, and a quotation keeps its original wording. Code
>    comments and docstrings adopt the compound when the surrounding code is
>    next edited, not in a sweep: a rename-only diff over the gate would put
>    review attention where no behaviour changed.
> 5. **Enforcement is review-time, and the reason there is no check is priced.**
>    Most of the surface this rule governs — issue bodies, PR text, owner
>    conversation — never enters the tree, so a repo-side linter covers a
>    minority of the surface. Covering the in-tree minority would need a
>    changed-lines ratchet over prose that legitimately quotes hundreds of
>    historical uses. That machinery outprices the defect class: one ambiguous
>    word, caught by any reader who knows the rule. If the bare word is found
>    load-bearing in new prose twice, that is the trigger to revisit this
>    clause, and this record is where the trigger is written down.

## Consequences

- **A sizing sentence can no longer borrow a scoring standard's authority by
  vocabulary alone.** "Short of the adoption-bar" forces the next question —
  *which lever class, and what did the record actually set?* — where "short of
  the bar" answered it falsely.
- **The two ADR families become separately addressable.** `grep adoption-bar`
  finds every adoption discussion written after this date; `grep scoring-bar`
  finds every scorer-standard one. Today `grep -w bar` returns both families
  interleaved with quantum rows, README promises and axis labels.
- **Historical prose stays ambiguous, and that is accepted.** A reader of
  ADR-0019 or ADR-0025 still meets the bare word and resolves it from context,
  as before. This record is the disambiguation page; it costs nothing to keep
  and it is where a confused reader lands.
- **The next collision of this shape has a template.** One word covering two
  decisions survived because each use was locally unambiguous to its author.
  The test this record applies — *do the two referents move for different
  reasons?* — is reusable the next time one term quietly covers two things.
