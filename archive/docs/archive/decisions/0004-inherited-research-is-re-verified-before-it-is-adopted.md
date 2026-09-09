# ADR-0004 — inherited research is re-verified before it is adopted

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-01

## Context

A document arrived from local-ai — six numbered architecture decisions distilled
from nine research crews, addressed to "an agent tasked with implementing these
ideas in a generalized version of local-ai (e.g. the mcgyvr repo)". Stop tokens
and structured output; HCP-style context pruning; hallucinated-API detection in
the gate; type checking in the gate; self-contained contracts with a redesigned
worker bundle; best-of-N execution consensus. Six issues had already been filed
straight from it — #93, #94, #95, #96, #97 and #99, opened within twenty minutes
of each other, parented to nothing — before any claim in it was checked. #109
was opened afterwards to be the merge procedure rather than the implementation.
The document's own header promises that "every claim below cites the local-ai
source file or research brief."

Its opening premise carries no citation anywhere: small models "achieve 94%+
syntactic validity with ~0% semantic correctness". Nothing in the document
supports the sentence, and mcgyvr's own vendored data contradicts it. The
HumanEval+ pass@1 figures local-ai measured for exactly these models are 0.652,
0.805 and 0.829 for the 1.5B, 3B and 7B (`data/capability-table.json:77`, `:94`,
`:111`). Whatever the true semantic-correctness floor is, it is not
approximately zero. That matters past the sentence: every gain estimate in the
decision table is an increment on that floor, and the implementation order is
sorted by those increments.

Twenty-four of the document's thirty-one inline citations — better than three
quarters — resolve to nine paths under `.pi-subagents/`. That directory is line
10 of local-ai's own `.gitignore`; it has never been committed and returns 404
on every ref. Those citations were never readable by anyone, the author
included. Three quarters of the evidence is therefore unverifiable by
construction rather than merely inconvenient.

Where citations do point outward, checking them changed the answers. Delulu is
given as arXiv:2606.03130; that identifier is "Synthetic Hallucinations, Real
Gains", a different paper by the same group. Delulu is arXiv:2605.07024, "A
Verified Multi-Lingual Benchmark for Code Hallucination Detection in
Fill-in-the-Middle Tasks", and the 20–40% hallucination rate DEC-3 rests on is
not in it. This record states no replacement rate: none was independently
confirmed, and a base rate is exactly the quantity DEC-3's value depends on.
Hierarchical Context Pruning (arXiv:2406.18294) is real and its finding is
inverted in the retelling — the paper reports that pruning function bodies "does
not significantly reduce the accuracy of completions" and that *increasing* the
dependent-file content improves it, which is a token-budget result, not the
"less context produced better results" the document reads out of it. The
document further claims HCP tested models ≥2B; its smallest was
DeepSeek-Coder-1.3B, and that claim is the entire basis for extrapolating a 4K
context budget down to a 1.5B worker. The T² quote attributed to arXiv:2604.01411
belongs to Snell et al., arXiv:2408.03314, which conditions it on "problems where
a smaller base model attains somewhat non-trivial success rates" — the condition
is dropped in the retelling, and 2604.01411 is a paper about pretraining
budgets. The figure that decides DEC-4's tool choice, mypy at 231 false
positives / 76 false negatives against pyright's 15 / 4, traces to a single blog
rather than to a benchmark, and a companion post on the same site the same day
reads the same 231 as *errors reported* — 142 false positives, against pyright's
5.

Set against that, mcgyvr already holds the machinery this document needed.
`records/claims/` carries one file per external claim, and every citation in one
must state `supports_because`, because "a bare link is not evidence"
(`tools/baseline/schema/record.claim.schema.json:71`). CLM-0004 already
registers the exact measurement the document leans on three separate times: the
45% → 70% bundle result, at medium confidence, 20 tasks on one rig, scoped by an
explicit caveat that the effect appeared on the small worker only and the
percentages "should not be quoted as generalizing to other models, task sets or
languages until re-measured" (`records/claims/CLM-0004.json:4`, `:15`). The
document quotes that one number for DEC-1, DEC-2 and DEC-5 and carries none of
the scoping. For DEC-1 it is a non-sequitur outright: the experiment varied
**bundle size** and nothing else, never stop tokens, and the document itself
concedes a few paragraphs later that there is "no published data on stop-token
effectiveness for Qwen2.5-Coder 1.5B/3B specifically."

## Decision

**Research inherited from local-ai is re-verified — against its own cited sources
and against mcgyvr's measurements — before any of it becomes an issue.** Every
retained numeric claim is either registered in `records/claims/` as a CLM, with
a citation that says why it supports the claim, or it is dropped from the text
that uses it.

Concretely: no issue is opened from an inherited document until its load-bearing
numbers have been traced; an unverifiable citation counts as no citation; and a
number that survives verification but cannot be scoped in a CLM — because nobody
can say what n was, or which model, or on which rig — does not appear in an
acceptance criterion.

This is not a bar invented for one document. It is the bar the repository
already meets for the data it ships: `data/README.md:25` — "Nothing in the table
is estimated or interpolated. A model with no valid measurement carries an empty
`quality` array rather than a guess." ADR-0001 boundary 10 holds that records
carry only what code cannot; this adds that what a record does carry has to be
checkable.

## Rejected: adopt the decisions and calibrate afterwards

The estimates are small — ~20 LOC for stop tokens, ~30 for the mypy step, ~50
each for context pruning and hallucination detection. Four of the six are an
afternoon. Measurement is not: the document's own list of gaps runs to a dozen
open experiments, several needing 20–100 task runs on real hardware, each
costing more wall-clock than the code it would inform. Sequencing cheap
reversible changes ahead of expensive measurement is normally right, and a wrong
thirty-line gate step is trivially reverted.

It loses on the word *cheap*. The LOC figures are honest; the numbers that make
those LOC look worth spending are not. A twenty-line change with a known
acceptance gain is obviously first. A twenty-line change with an unknown gain is
not obviously anything. Sorted by unsourced increments, the implementation
**order** is the artifact the missing evidence damages most — and order is the
one output that is not cheap to revert, because the document sequences DEC-4 and
DEC-3 behind DEC-1 explicitly "for gate step ordering", so each is built against
the last one's numbering. Being wrong about which to build first costs more than
being wrong about any one of them. The cheapness of the individual changes is
precisely why their ordering is the only thing worth getting right, and ordering
is what re-measurement decides.

Shipping first would also ship a defect. DEC-1's recommended stop set includes
`\ndef ` and `` ``` ``, while mcgyvr's default reply shape is `whole_file`
(`contract.py:361`, default at `:368`) — one file's complete content in one
fenced block (`data/README.md:129`). A stop sequence is consumed and stripped,
so that set truncates a whole-file reply at its second function and hands the
gate a syntactically plausible partial file: the exact failure class the
decision exists to prevent. ADR-0009 works the case through. "Calibrate
afterwards" means calibrating against that.

## Rejected: discard the document wholesale

The premise is fabricated, three quarters of the citations were never readable,
and four outward-facing citations are wrong in ways that reverse or vacate the
conclusion they support. A document with that error rate has negative
information value: every claim has to be checked anyway, checking costs what
researching from scratch costs, and a plausible wrong number is stickier than no
number. The clean move is to close #109 and the six issues under it and start
over from mcgyvr's own data.

It loses because the audit was not uniform, and verification is not
all-or-nothing. Three threads verified exactly: RSTD (arXiv:2605.15425),
CodeDelegator (arXiv:2601.14914) and shifu, figures included. The bundle result
is real, independently re-derived from raw data, and already carried here as
CLM-0004. DEC-4 and DEC-5 survive on grounds the document did not argue:
`type_check` is already a shipped evidence kind requiring a command, documented
as "the project's type checker passes on the changed target"
(`data/task-catalog.json:50`, `:52`), and the worker/orchestrator split DEC-5
proposes is already enforced by `Field.worker_facing` with `worker_view()` as
the only accessor (`contract.py:180`, `:483`). A document can be badly evidenced
and still contain correct engineering. Discarding it wholesale would throw away
the engineering to punish the evidence, and would leave six real problems
unaddressed with no record of why.

## Consequences

- #93 through #97 and #99 are re-scoped rather than implemented as written. What
  survives survives on mcgyvr's design, and where that is the case the issue
  says so instead of quoting a gain estimate. The six decisions are resolved on
  their merits in ADR-0005 through ADR-0009.
- Every "+X%" figure in the document is deleted rather than adjusted. There is
  no basis on which to adjust one.
- The citation corrections apply wherever those numbers are restated: Delulu is
  arXiv:2605.07024 and the 20–40% rate is not in it; the T² quote is Snell et
  al., arXiv:2408.03314, and carries a condition on the base model's success
  rate; HCP's smallest model was 1.3B and its pruning result is about token
  budget at equal accuracy. A wrong identifier propagates further than a wrong
  number, because the next reader looks it up and finds *a* paper.
- The calibration debt is carried into the re-filed issue tree, not resolved
  here. Carrying it is not the same as owing it — several items exist only to
  decide whether a decision is worth building, and the first of them, rebuilding
  the sizing premise from `data/capability-table.json`, can retire more than one
  decision outright.
- `README.md` and `data/README.md` described local-ai as "(archived)".
  `gh api repos/AdarGit008/local-ai` reports `archived: false`, last pushed
  2026-08-01. Both are corrected. ADR-0001:11 is left as written: it records the
  state of the world at the moment a decision was taken, and a record is not
  edited to track the world. Any re-audit pins to local-ai
  `docs/architecture-decisions-2-6.md` @ b0ff2ac4, since the repository has moved
  since.
- What this costs is speed, and the ratio is unflattering: auditing took
  substantially longer than writing the thing audited, and this record commits
  mcgyvr to paying that ratio again for anything else inherited. Accepted
  deliberately. The alternative is sequencing v1 by numbers nobody can source.
- What this gives up is the possibility that the document was right by luck.
  DEC-3 may well be worth building; this record refuses to build it on a base
  rate nobody can produce, and that refusal will occasionally discard something
  true.
