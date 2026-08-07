# Pool probe, 2026-08-07 — the seam under real dispatch

**What this is.** The first sweep of the #197 problem pool against a served
worker: ten problems spread across the pool's id range, both arms, one greedy
draw plus two sampled, `qwen2.5-coder:7b` on srv1 over `openai` on 11434.
Sixty rows. It exists to exercise the rig seam end to end, not to characterise
any model — ten problems and three draws decide nothing about pass rates.

**What it establishes.**

- `--tier pool-ts` and `--tier pool-py` dispatch, capture and score through
  the unmodified rig. No parse refusals, no dispatch errors, 0.1–0.3s
  acceptance per candidate.
- **The corpus is no longer one language.** Re-pinning after this run put
  `info_string: "python"` into `records/corpora/worker-replies/golden.json`
  beside `ts`/`typescript` for the first time — 60 new pinned replies, 8 of
  them verified passes, 4 per arm. #197's premise ("every verified pass is
  TypeScript") stops being true here, by ordinary measurement exhaust and
  not by a curation step, which is what ADR-0016 intends.

**A defect this run found, and the fix it forced.** The first attempt
recorded **157** task digests for `pool-py` against **149** for `pool-ts`:
`load_tier_tasks` served the tier *directory*, and a batch was being written
at the time, so unadmitted candidates entered the run's identity. A tier
whose digest map includes work that never passed admission splits the tier
into versions nobody chose, and two runs a week apart stop being comparable.
The pool tiers now serve only what `tools/problems/admissions.jsonl` pins
(`pinned_pool_ids`), the first run directories were discarded rather than
kept with a footnote, and these rows are from the re-run: 149 digests on
both arms. `tests/test_problem_pool.py` holds the rule.

**Numbers, stated for what they are.** Greedy 1/10 on each arm; three TS
problems and two Python problems produced at least one pass in three draws;
mean 266 completion tokens. The comparison worth drawing is against d1,
where this model family sits near the ceiling: the pool is materially harder
than the twenty-task set, which is useful for a corpus meant to discriminate
and is a caution for yield — a low pass rate means fewer verified passes per
sweep, and the corpus grows in proportion to passes, not to draws. Whether
the pool's difficulty distribution wants rebalancing is a question for a real
sweep across the whole 149, not for this probe.
