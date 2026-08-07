# The problem pool — #197's ~500 distinct problems, in both languages

The worker-reply corpus is measurement exhaust (ADR-0016), and as of #196 all
of it answers twenty TypeScript problems: 4,305 verified passes, 2,502
distinct reply texts, 20 problems, one language. The best evidence for
training on verified passes at this scale (SWE-Gym, cited in
`docs/unsloth-fine-tuning-review-2026-08-06.md` §3) got its gains from ~491
**distinct problems**; thousands of draws over twenty is a different object.
This directory grows the problem pool so that ordinary measurement runs feed
the corpus with diversity — no separate curation step.

Sourcing was searched before building: no adoptable dataset exists
(`docs/problem-pool-prior-art-2026-08-07.md`). The pool is generated, and
admission-gated by `admit.py`.

## Shape

One problem, two arms, same id:

```
tools/problems/tasks/ts/p001-<slug>/  contract.yaml  reference.ts  accept.mjs
tools/problems/tasks/py/p001-<slug>/  contract.yaml  reference.py  accept.py
```

- **Directory name and contract `id` are identical** (`p001-<slug>`), unlike
  d1/d2/d3 where `d2/t01` and `d3/t01` collide on the bare name —
  `tools/finetune/build_dataset.py` keys on the task id, and the pool makes
  that key globally unique by construction rather than by care.
- **Both arms state the same problem.** The `task:` prose is shared;
  `interface`, `target` and (for `bug_fix`) `target_content` are the
  language-specific rendering. A problem admitted in one language only is not
  admitted: the pool's unit is the problem, and #189/#190's consumers exist
  on both sides.
- Contracts load through `mcgyvr.contract.load` — same rule as the rigs: a
  task this project's schema would reject is not a task it can dispatch.
- Task types in v1: `function_implementation` and `bug_fix` (18 of the
  original 20). `type_annotation` is deferred — its d1 checkers read their
  own source text, which needs its own anti-triviality design.

## Admission — `admit.py`

```
uv run --no-sync python tools/problems/admit.py p001-slugify p002-…   # named
uv run --no-sync python tools/problems/admit.py --all                 # whole pool
uv run --no-sync python tools/problems/admit.py --all --pin           # + write manifest
```

A problem is admitted only if every check passes in both arms:

1. **Structure.** Both arms present; dir name matches contract `id`; id
   matches `p<nnn>-<slug>`; id unique across the pool *and* the d1/d2/d3 and
   bundle sets.
2. **Contract loads** via the real loader, task type in the v1 set.
3. **Selftest.** The reference passes the contract's declared commands
   (`acceptance`, and `demonstration` for `bug_fix`) in a fresh directory —
   the rigs' own discipline (`--selftest` is a stated precondition of any
   run's validity).
4. **Failing-first for `bug_fix`.** The contract's `target_content` (the
   buggy code) must *fail* `demonstration`, and must differ from the
   reference — the gate's precondition, checked at admission.
5. **Anti-triviality.** Stub solutions derived from the declared `interface`
   — a no-op returning `undefined`/`None`, and an echo of the first argument
   — must **fail** the checker. A checker both stubs pass is measuring
   nothing. (SAGA's finding motivates this: a checker generated alongside its
   reference inherits the generator's blind spots; the stubs are inputs it
   never saw. We did not find this gate in published practice; it is this
   repo's own.)
6. **Checker floor.** ≥ 5 assertions per arm — richness over count is the
   published lever, but below five there is no richness to have.
7. **Held-out eval overlap.** The implemented symbol name must not be any of
   the 164 HumanEval entry points (`humaneval-entrypoints.json`, vendored
   from openai/human-eval, MIT). Item overlap with the front door is
   disqualifying in any language; distribution overlap is a documented
   caveat, not a check — see the prior-art doc's last section.
8. **Near-duplicate screen.** Word-set Jaccard of the `task:` prose against
   every admitted problem and the existing d1/d2/d3/python sets; ≥ 0.55
   rejects, naming the pair. Lexical only — weaker than KodCode's embedding
   screen, and said so here rather than smoothed over.

`--pin` appends admitted problems to `admissions.jsonl`: id, arms, per-file
sha256, provenance note (`--provenance`). The manifest is append-only and
`tests/test_pool.py` holds the tree to it — **an admitted task is pinned the
way the python arm is pinned by digest**, because run directories pin the
tier's `tasks_sha256` and an edited task refuses every prior run a resume.
Repairs follow the d1r discipline: a defective problem is superseded by a new
id and its manifest line marked `superseded_by`, never edited in place.

Rejections are quarantine, not deletion: `admit.py` reports per-check
verdicts and the caller decides; regeneration replaces the whole problem
(reference *and* checker together — KodCode's retry rule, which limits
test–solution co-adaptation).

## Generation batches

Problems are generated in batches by API-tier models, steered for diversity
by a domain × type assignment (the domains list lives in this README so
batches don't converge on the interview canon the near-dup screen would
catch late):

strings/text-processing · parsing/tokenizing · intervals/scheduling ·
graphs/ordering · trees/hierarchies · dynamic programming · numeric/precision
· dates/durations · encodings/serialization · validation/normalization ·
state machines/protocols · collections/iterators · geometry/grids ·
searching/selection · caching/memoization · diff/merge/undo · tabular
data/aggregation · bit manipulation · randomless simulation · pattern
matching.

Batch discipline: ~70% `function_implementation` / ~30% `bug_fix`; difficulty
spread from d1-like to d2-like; every batch runs `admit.py` before anything
is pinned; the batch's generator and date go in `--provenance`.

## Running the pool

`tools/breadth/measure.py --tier pool-ts` and `--tier pool-py` sweep the
pool's arms. The arm lives in the tier name, so run identity (`tier` +
`tasks_sha256` in `run.json`) separates the two with no new mechanism, and
the campaign driver never climbs into either — pool tiers are breadth of
problems, not difficulty rungs. Candidates land in the run's `candidates/`
directory, which `tools/replies/pin.py` already walks: a pool run placed
under `records/measurements/` feeds the corpus exactly the way ADR-0016
already works.

## What the pool does not do (yet)
- **`build_dataset.py` predates paired arms.** Both arms of `p001` share an
  id, so the per-task cap would pool their replies and the prompt-rebuild
  step needs the arm's contract, not "the" contract. That consumer change
  belongs to the lane that first builds a dataset from pool runs.
- **Absence caveat.** The near-dup screen is lexical; the HumanEval screen is
  item-level. Neither claims the pool is free of problems resembling
  something, somewhere — only free of the specific overlaps named above.
