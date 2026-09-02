# The problem pool: prior art, searched before building

**Date:** 2026-08-07. **Lane:** lane/197, for issue #197. **Question:** does a
corpus of ~500 distinct, self-contained coding problems — each with a spec, a
reference solution and an executable checker, in both Python and TypeScript —
already exist to adopt, before we generate one? **Method:** three delegated
web investigations (dataset hubs and GitHub; synthetic-corpus pipelines;
benchmark-derived pools and contamination evidence), run 2026-08-07, queries
and URLs recorded in each report. Labels as in
`unsloth-fine-tuning-review-2026-08-06.md`: **[measured]**, **[self-reported]**,
**[docs/code]**, **[derived]**.

**Verdict: adopt nothing; generate.** We did not find any dataset that pairs
≥500 distinct problems with executable checkers in both languages free of the
two disqualifiers below. The searched space and the near-misses are recorded
here so the absence claim has provenance and an expiry — this was true of what
we found on 2026-08-07, not of the world.

## The two disqualifiers

1. **Item overlap with the front door.** The ladder admits models on
   HumanEval+ (`capability.py` reads `humaneval_plus_pass1`; the #189 pilot's
   bar is +3pp on it). A pool containing those items — in any language —
   trains on the exam. MultiPL-E's `humaneval-ts` is the exam translated:
   159 of the 164 items, item for item. [docs/code]
2. **Pretraining memorization confounds the pool's other job.** Pool problems
   double as measurement tasks (that is how ADR-0016 feeds the corpus), and a
   problem the local models memorized measures recall, not capability.
   Riddell, Ni & Cohan (NAACL 2024, arXiv 2403.04811) find 12.2–18.9% of
   HumanEval and up to 20.8% of MBPP gold solutions present in major
   pretraining corpora, with top-vs-bottom similarity deciles differing by
   40–60pp pass rate [measured]. Fine-tuning specifically *revives*
   contamination that pretraining had diluted: injected MBPP items re-open a
   >2% contaminated-vs-clean gap after SFT/GRPO on Qwen2.5 bases — our model
   family (arXiv 2601.06103) [measured].

## What was found, and why each fails

| Candidate | Size / languages | License | Why not |
|---|---|---|---|
| MultiPL-E (`nuprl/MultiPL-E`) | `mbpp-ts` 390, `humaneval-ts` 159; tests runnable, **no target-language reference solutions** | MIT | HumanEval/MBPP-derived: disqualifier 1 (humaneval-ts) and 2 (both) [docs/code] |
| MBXP / mxeval (Amazon) | ~848–974 per language incl. TS, with solutions | Apache-2.0 | MBPP/HumanEval-derived: disqualifier 2 [docs/code] |
| BabelCode (Google) | MBPP/HumanEval → 16 languages incl. TS | not verified | same derivation [docs/code] |
| KodCode-V1 | 447K verified Python triplets | **CC BY-NC 4.0** | Python-only; NC license; seeds include LeetCode/APPS/TACO [docs/code] |
| AutoCodeBench (Tencent, 2025) | 3,920 across 20 languages ≈ **196 TS**, spec+solution+tests | Apache-2.0 | Not benchmark-derived (Stack-Edu-seeded, LLM-generated, sandbox-verified) — the closest miss, but ~196 TS problems, tests shaped for their sandbox harness, and adopting it is adopting another lab's synthetic pipeline output without its admission gate [docs/code] |
| Exercism (problem-specifications + tracks) | ~100 problems with paired Py+TS tests and reference solutions | MIT | Hand-written and benchmark-free, but saturated across public GitHub since years — disqualifier 2 — and a fraction of the scale [docs/code] |
| BigCodeBench | 1,140 Python tasks with tests | Apache-2.0 | Python-only; 2.8 third-party libraries per task on average — not self-contained [docs/code] |
| MBPP+ (EvalPlus) | 378 Python problems, solutions + 35× tests | Apache-2.0 | Python-only and disqualifier 2; also LBPP's result below makes "MBPP-shaped" itself a caveat [docs/code] |
| LiveCodeBench / Multi-LCB | 1,055 by v6; Multi-LCB adds TS | MIT / **CC BY-NC 4.0** (Multi-LCB) | stdin/stdout competitive shape, not contract shape; TS variant is NC [docs/code] |
| Competitive-programming pools (TACO, APPS, CodeContests, rStar-Coder, HARDTESTS, open-r1/codeforces) | 10K–418K, Python/stdio | mixed | stdin/stdout shape, judge-crawled provenance, memorized sources; APPS has a documented false-positive test problem [docs/code] |
| Unsloth (docs, HF org) | — | — | publishes no verified-test coding corpus; their datasets guide names none (checked 2026-08-07) [docs/code] |
| MultiPL-T, PrimeIntellect verifiable-coding-problems, HumanEval-X/XL, McEval | various | various | no TS / HumanEval-derived / ~50 TS items — each fails on scale or derivation [docs/code] |

**Every found dataset pairing TS tests with ≥150 distinct problems is
HumanEval/MBPP-derived.** The non-derived TS-with-tests sources found
(AutoCodeBench ~196, Exercism ~100) do not reach 500 even combined, and
Exercism is memorized. We did not find a synthetic TS problem corpus with
executed checkers at all — the TS half of this pool appears to be genuinely
unbuilt territory. (Search provenance: agent reports of 2026-08-07; sixteen
plus queries listed per report.)

## What the generation pipeline inherits from the literature

The generate→verify pattern is the established 2025 shape (KodCode,
SelfCodeAlign/StarCoder2-Instruct, AutoCodeBench) [docs/code]. Checks adopted
into `tools/problems/admit.py`, with sources:

- **Execution self-verification with bounded retries, regenerating solution
  and tests together** — KodCode discards a question after 10 failed
  attempts; regenerating both limits test–solution co-adaptation [docs/code].
- **Near-duplicate filtering** — KodCode uses embedding cosine; we use
  lexical Jaccard over spec prose (no embedding model in this repo's
  dependency set) and state the weaker guarantee [derived].
- **Quarantine with reasons, not silent drops** — KodCode's
  `use_with_caution` split [docs/code].
- **Richer tests over more tests** — "Verification Limits" (arXiv 2509.20837):
  test richness moved pass@1 ~+3 where raw count plateaued [measured].
- **Self-generated tests are easily passed by their own generator** — SAGA
  (arXiv 2507.06920): LiveCodeBench-passing solutions fail the official judge
  at 20–40% on harder tiers; the generator's blind spots recur in its tests
  [measured]. Consequence here: the checker is generated *with* the reference
  but admission requires it to reject stub solutions it never saw.
- **Trivial-solution rejection as an admission gate** — we did not find a
  named equivalent in published practice; it enters as this repo's own check,
  stated as such.

## The caveat that survives generation

Item-level decontamination is enforceable and enforced (entry-point blocklist
against the 164 HumanEval names; near-dup screening). Distribution-level
overlap is not removable: LBPP (arXiv 2407.07565) measures +14pp HumanEval
from training on *similar-but-not-identical* evol-instruct problems
[measured]. Any pool of short function-synthesis problems — including this
one — overlaps HumanEval+ in distribution, because that distribution is what
the tier is being trained *for*. The consequence is a reading rule, not a
blocker: a post-#197 fine-tune's HumanEval+ delta includes a
format-familiarity component, and the +3pp admission bar is a bar on the
combination. #113's fixed task set (held out from the pool by construction)
is the instrument that can separate the two later.
