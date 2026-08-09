# ADR-0017 — the floor is the product, and the ceiling is priced against it

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-09

## Context

mcgyvr offloads scoped coding work from an agent to a worker ladder. Its reason
to exist is that the offload is *cheap* — fast, local, on hardware the owner
already has. Every property that makes it worth using rather than sending the
work to the API tier is a property of the small end of the ladder.

That was never written down, and the plan drifted away from it without anyone
deciding to. The drift is legible in what got built: the #197 problem pool was
sized so that it would discriminate a 7B worker from a 14B one, which it does
well; #189 tuned a 3B and judged it on HumanEval+; #190 was sequenced behind
that verdict. Each step was locally defensible. Together they pointed the
project's measurement effort at the part of the ladder whose improvement matters
least.

**What forced the issue.** #219 planned to re-tune the 3B and evaluate it on the
pool. Probing before spending (greedy, cap 2048, every reply well-formed, every
failure read by hand and confirmed a genuine wrong answer rather than a harness
artifact):

| task set | n | qwen2.5-coder:3b |
|---|---:|---:|
| HumanEval+ (#189's set, q4_K_M) | 164 | 78.0% |
| breadth `d1` tier (20 distinct problems) | 243 | 50.6% |
| the #197 problem pool | 50 | **0%** |

Not a language effect: the Python arms read 0/20 beside TypeScript's 0/30. The
pool is a different size class of task — median 60-line reference solution (p90
104, max 233) checked by a median 18 assertions (p90 25, max 41), with an
admission gate that rejects anything a stub can satisfy. HumanEval problems are
5–15 line single functions checked a handful of ways.

The whole ladder compresses against it: the 14B falls from ~90% on HumanEval+ to
33.8% on the pool, the 7B to ~19%, the 3B to zero. **A benchmark that separates
7B from 14B cleanly is a ceiling instrument**, and the project owns no floor
instrument at all. That absence — not the 3B's score — is the finding.

The deeper reading: a 3B scoring 78% on HumanEval+ and 0% on 60-line,
18-assertion problems is not a weak model. It is a model whose *whole-problem*
ceiling sits below the pool's *unit of work*. Closing exactly that gap is what
decomposition, the pipeline and the gates are for. The pool measures capability
at a granularity mcgyvr is designed never to hand a small worker.

## Decision

**P1 — raising the floor beats raising the ceiling.** The small models are the
ones most worth improving. A floor raise preserves the properties that justify
the project: the speed of a small model, cheap hardware, easy scaling. A ceiling
raise buys capability and spends all three to get it. **This governs every
feature, not only weights** — decomposition, the pipeline and the gates are
floor-raising machinery in precisely the same sense and are judged the same way.
Where a change could be aimed at either end, it is aimed at the floor, and an
issue that raises only the ceiling says so in its own text.

**P2 — the 7B/14B are not the ceiling, and the real ceiling is bounded.** The
ceiling is the MoE 20B+ class the owner can serve (`gpt-oss:20b`,
`qwen3-coder:30b`, `qwen3:30b-a3b`, `qwen3-coder-next-ud:q3_K_XL`). Those models
work and work better. They are also slower, they mean less to an average user,
and this project's judgment is that **they will never replace the API tier**.
A ceiling result is therefore a bounded gain on a track that structurally cannot
win, and is priced that way when it competes with floor work for the same hours.

**P3 — the floor can move, so nothing hard-codes its tier.** If the small models
are ruled out later, the 7B/14B become the floor and inherit the whole question.
Designs, harnesses, corpora and cap formulas are therefore **parameterized by
target tier** rather than written against one model. Two corollaries: evidence
already gathered at 7B/14B is not discarded as off-target, and a formula fitted
on a single worker (as #216's 1151/805 percentiles were, on 14B TypeScript
alone) is incomplete until it is shown to transfer or is made tier-aware.

## Rejected: measure wherever the instrument is sharpest

The tempting move on discovering the 3B reads 0% was to retarget the experiment
to the 7B, where a pass rate of ~19% leaves room for an effect to show. It is
better science on a worse question. An instrument's power is not a reason to
change what is being measured; it is a reason to build the missing instrument.
Choosing the target by measurability is how the drift described above happened
in the first place — each step picked the tractable question over the important
one, and no single step looked wrong.

## Rejected: treat the pool as a mistake

The #197 pool cost real money and two spend-limit interruptions to build, and
P2 does not condemn it. It is a good instrument that answers a ceiling question:
it separates worker tiers, it exposed that `bug_fix` passes at ~2× the rate of
`function_implementation` at both model sizes, and its hard tail is genuinely
hard rather than broken. What changes is the claim it can support. It is not a
floor instrument and no amount of holdout arithmetic will make it one, because
its unit of work is above the floor's whole-problem ceiling by construction.

## Rejected: fix the floor by naming a permanent floor tier

Declaring "the 3B is the floor, forever" would make designs simpler and would be
wrong within a release. The floor is whichever tier is the cheapest that still
earns its place, and that changes as models, quantization and the pipeline
change. P3 pays a small ongoing cost in parameterization to avoid re-deriving
every harness each time it moves.

## Consequences

- **A floor instrument has to be built.** Nothing in the repo can currently
  measure a small model getting better at work mcgyvr would actually hand it.
  Until one exists, "did this raise the floor?" is unanswerable, and #221's
  question of whether to train small models at all cannot be settled on
  evidence. This is the single largest gap the ADR opens.
- **What a floor instrument needs is *resolution*, not difficulty.** It must sit
  in a band where the target model scores well above 0 and well below 100, so
  that gains and regressions are both visible. Grading the 3B across the
  difficulty rungs at a common cap gives `d1` 50.0% (reproducing the 50.6% above
  at a different cap and host), `d2` 41.7%, `d3` 16.7%,
  the pool 0% — **a slope, not a cliff**, with a usable band reaching further
  down than expected. Two things that follow: the collapse happens somewhere
  between `d3` and the pool and **nothing occupies that range**, so what takes a
  3B from 16.7% to zero is unidentified; and every rung is `jsts`, so the band
  is unmapped for Python. Located as #224, which is upstream of both the
  harness (#113) and the training question (#221). Figures are directional —
  12 tasks per rung, one draw, one rig.
- **The front door does not close it.** HumanEval+ is where the 3B has headroom,
  which makes it tempting. It is also underpowered at n=164 (paired McNemar MDE
  ~+4.8pp against a +3pp bar) and contamination-prone after fine-tuning in
  Qwen2.5 bases. A floor instrument that is the front door measures familiarity
  as well as capability.
- **Open work is re-read against P1–P3** (#220), and decisions previously
  reached under ceiling-first reasoning are corrected in the record rather than
  quietly reinterpreted. #189's verdict and #190's sequencing behind it are the
  first two.
- **The corpus question reopens** (#222). The existing corpus is whole-problem
  measurement exhaust, and only 144 of the pool's 499 problems have ever
  produced a verified pass — training examples require one. If the floor
  question lives at a decomposed unit of work, that material cannot answer it.
- **Cost is admitted, not hidden.** P3's parameterization is overhead on every
  harness, and P1 will sometimes mean declining a cheap, well-powered ceiling
  measurement in favour of an expensive, awkward floor one. That trade is the
  decision, not a side effect of it.
