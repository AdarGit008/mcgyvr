# Pool sweep at 14B, 2026-08-07 — is the hard tail too long?

**What this is.** The same instrument as `pool-sweep-2026-08-07`, TypeScript
arm only, pointed at `qwen2.5-coder:14b` on srv2 over the pool as it stood at
269 problems (batches 1–7). Greedy plus two sampled draws, 807 rows. It exists
to answer the question the 7B sweep raised and could not settle: **is the
pool's 117-problem hard tail a distribution defect, or simply harder than a 7B
can reach?**

## The answer: harder than a 7B, not broken

| | 7B (189 problems) | 14B (269 problems) |
|---|---:|---:|
| greedy pass | 36/189 (19.0%) | 86/269 (32.0%) |
| problems with ≥1 pass in 3 draws | 53/189 (28.0%) | 114/269 (42.4%) |
| verified passes | 97/567 | 262/807 |
| `bug_fix` | 26.3% | 52.3% |
| `function_implementation` | 13.1% | 23.9% |
| parse refusals | 6 | 47 |

**On the 189 problems both swept:** the 7B solved 53, the 14B solved 94. The
14B **rescued 48 problems the 7B never once passed**, while 7 went the other
way (sampling noise at three draws, not a capability claim). 88 of the 189 —
46.6% — resisted both.

That is the shape a discriminating instrument should have. A tail that no
larger model could touch would suggest problems that are wrong rather than
hard; instead, doubling the worker recovers nearly half of what the smaller
one missed, and the pass rate rises smoothly rather than saturating. **No
rebalancing is warranted on this evidence.** The remaining both-unsolved 46.6%
is the pool's genuine top end, and it is what will keep the corpus
discriminating as the tier improves.

Two secondary readings:

- **The `bug_fix` advantage is not a small-model artefact.** It roughly
  doubles at both sizes (26.3→52.3 and 13.1→23.9), so the ~2× gap between the
  task types is a property of the task types, not of the worker. Corpus
  sampling should assume it persists.
- **Parse refusals rose eightfold, 6 → 47.** The bigger model fails the
  output contract more often than the smaller one, which is a finding about
  the reply format rather than about capability, and worth a look from
  whatever revisits `worker/reply.py` — refusals are corpus under ADR-0016, so
  they are pinned and available.

## The 80 problems only this sweep saw

Batches 6–7 (p202–p281) were admitted after the 7B sweep started, so only the
14B saw them: it solved 20 of 80 (25%), against 42.4% over the whole 269. The
newer batches are harder than the pool average. Plausible causes are
untested — later batches drew narrower domains and the generators had more
prior art to differentiate against — and nothing here separates "harder
problem" from "harder to state unambiguously". A 7B pass over the same 80
would settle it, and is cheap.

## Caveats

- One arm (TypeScript), one model, three draws. Nothing here is a capability
  ranking; it is a difficulty probe with the worker as the instrument.
- The two sweeps cover different pool sizes (189 vs 269) and different hosts,
  so only the 189-problem intersection supports a paired comparison. That is
  the comparison drawn above; the aggregate columns are reported separately
  rather than differenced.
