# Pool sweep, 2026-08-07 — all 189, both arms

**What this is.** Every problem the pool had admitted when the sweep started
(189, batches 1–5), both arms, one greedy draw plus two sampled at T=0.7,
`qwen2.5-coder:7b` — TypeScript on srv1, Python on srv2. 1,134 rows. It
answers the question the ten-problem probe raised and could not settle: what
the pool's difficulty actually looks like, and how much verified corpus one
sweep yields.

The pool has grown past 189 since (batches 6 and 7). These directories pin
the 189-problem set by digest, so a resume against today's pool is refused
rather than silently averaged — which is the intended behaviour, not a
limitation to work around. A sweep of the larger pool is a new directory.

## What it measured

| | TypeScript | Python |
|---|---:|---:|
| greedy pass | 36/189 (19.0%) | 43/189 (22.8%) |
| problems with ≥1 pass in 3 draws | 53/189 (28.0%) | 53/189 (28.0%) |
| verified passes | 97/567 | 111/567 |
| parse refusals | 6 | 1 |
| dispatch errors | 0 | 0 |

**The probe was not representative and this is why the sweep was worth
running.** The ten-problem probe read 1/10 greedy on each arm; the full set
reads 19–23%. Ten problems sampled by id spacing landed harder than the pool
average, and a yield estimate built on them would have been wrong by a
factor of two.

**`bug_fix` is roughly twice as easy as `function_implementation` for this
worker** — 26.3% vs 13.1% (ts), 33.9% vs 13.4% (py). The pool is 70/30
function-implementation-to-bug-fix by count, so the two types will
contribute to a training corpus at much closer to even rates than the
composition suggests. Anything sampling the corpus by task type should read
these numbers rather than the pool's composition.

**The arms are equally hard in aggregate and disagree problem by problem.**
Both arms pass 53 of 189, but only 34 problems pass in both; 19 pass only in
TypeScript, 19 only in Python, 117 in neither. **72 distinct problems
produced at least one verified pass somewhere** — against a corpus whose
entire verified-pass history until today answered 20 problems.

## What it means for #197's purpose

The corpus grows with passes, not with draws. At three draws this sweep
yields 208 verified passes over 72 distinct problems. Scaling the *draws*
raises passes per problem; scaling the *pool* raises distinct problems, and
distinct problems is what SWE-Gym's result rests on. Both matter, and this
sweep says the pool is not so hard that a 7B worker cannot feed it — a real
risk given the pool was written to be harder than d1.

117 problems produced nothing in three draws. That is a distribution
question, not a defect: some of those are the multi-invariant half every
batch was asked for, and a corpus whose problems a 7B worker always solves
would not discriminate. Whether the hard tail is *too* long is worth asking
against a stronger worker before anything is rebalanced — srv2 serves
several, and none of them have been pointed at the pool.

## An operational gotcha, recorded because it cost a test run

`tools/replies/pin.py` walks every run directory under
`records/measurements/`, and a sweep in flight has candidate files whose
rows have not been flushed yet. The pinner refuses a candidate it cannot
join to a row — correctly, since an orphaned candidate is exactly what an
interrupted run leaves — so **the reply corpus cannot be pinned or checked
while a sweep is running**, and `tests/test_reply_corpus.py` fails for the
duration. Pin after the sweep exits. Nothing here changes `pin.py`: its
strictness is #184's contract and the transient case is the caller's problem.
