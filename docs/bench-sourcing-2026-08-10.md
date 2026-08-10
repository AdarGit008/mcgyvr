# Bench sourcing — the inventory before the campaign (#225)

**Why this document.** #225's first acceptance item: the in-repo inventory is
the first stop, recorded — including the five retired sets with their n,
language, 3B first-pass rates and CLM sources, recorded as the *specification*
of in-band material and as material that may **not** be carried into the bench
— before any outside set is considered. This is that record. The sourcing
order it follows is the issue's: in-repo first (this section), outside sets
second (§3, appended when the search runs), generation only after both.

All rates are qwen2.5-coder:3b Q4_K_M, first-pass, greedy, one seed, unless
stated. "c0–c3" are the bundle rig's four prompt conditions.

## 1. The inventory

### Declared instruments — all retired 2026-08-10 (#240), all barred from the bench

| set | root | n | language | 3B first-pass | source |
|---|---|---:|---|---|---|
| `bundle-ts` (tier `d1`) | `tools/bundle/tasks` | 20 | JS/TS | 45 / 55 / 50 / 45% (c0–c3); 50.0% graded at common cap | CLM-0012; `records/measurements/floor-probe-2026-08-09/` |
| `bundle-py` | `tools/bundle/python/tasks` | 20 | Python | 65 / 70 / 70 / 70% (c0–c3, arm A) — flat, p = 1.00 | CLM-0017 |
| `breadth-d1r` | `tools/breadth/tasks/d1r` | 1 | JS/TS | — (t20 repair, cannot outlive d1) | `tools/instruments.json` |
| `breadth-d2` | `tools/breadth/tasks/d2` | 12 | JS/TS | 41.7% graded at common cap | `records/measurements/floor-probe-2026-08-09/` |
| `breadth-d3` | `tools/breadth/tasks/d3` | 12 | JS/TS | 16.7% graded at common cap | `records/measurements/floor-probe-2026-08-09/` |
| `humaneval-plus` | external (164 ids) | 164 | Python | 78.0% — reported, not evidence (contamination unresolvable) | #189; `tools/instruments.json` `never_trainable` |

The five local sets were released for training
(`records/corpora/training-release-2026-08-10/`, 1,544 examples). Every one of
them is therefore training material, and a bench containing any of it measures
nothing about a tune. HumanEval+ is barred in both directions, permanently.

### Adjacent material that is not a declared instrument — also barred

- **The vendored local-ai originals**
  (`records/evidence/local-ai-2026-08-02/instrument/`, tasks in
  `context_tasks.py`): 20 Python problems, CLM-0004's instrument, CLM-0017's
  arm B (35/50/55/65%) and the material its +20pp positive control actually
  ran on. Not declared, but its problems are released by proxy — `bundle-py`
  is its port, and roughly two-thirds of the underlying problems recur in
  `bundle-ts` (the declaration's own notes record both).
- **The pool** (`tools/problems/`, 499 paired problems): 0/50 on the 3B probe
  — a ceiling instrument for 7B/14B, the wrong unit of work for a floor bench
  (median 44-line reference, median 16 assertions per Python arm). It is
  training-side by design, deliberately not in `tools/instruments.json`, and
  the bench must stay id- and prose-distinct from it (`admit.py` enforces
  this from the declaration).

## 2. What the inventory is now for: the specification

The retired sets remain the specification of in-band material. What they
specify:

- **Shape.** Real contracts — `task_type`, `target`, `interface`,
  `stop_conditions`, a runnable `acceptance` command, `risk`, `scope` —
  against a checked-in reference, scoreable by `Gate.run`, paired arms
  sharing one problem prose across TS and Python.
- **Level.** In band on the floor tier: the sets that measured anything sat
  between 16.7% and 70%, well above 0 and well below 100.
- **Response, not just level.** The JS/TS arm moved under condition (a rise
  and a fall); arm A sat at the same level and moved nothing (1/20 responsive,
  p = 1.00). Level is necessary, response is what buys power — ψ measured
  0.05–0.40 across the four arms (`tools/power/report.py --section
  responsive`), and 13/20 condition-insensitive tasks was the JS/TS arm's
  effective ceiling on n.
- **The failure modes to design against.** A never-passing subset (t02, t03,
  t06, t17, t18, t19 across both stacks) — cells at the task's own ceiling
  contribute nothing; and n = 20, which no effect size rescues (m ≥ 6 wall,
  ADR-0019).

## 3. Outside sets

*Appended when the search runs (Phase 1 of the lane): the
`docs/problem-pool-prior-art-2026-08-07.md` adopt-nothing verdict re-checked
with provenance, and MBPP+ measured against the 3B with its contamination
caveat attached to whatever it reads. Nothing outside the repository has been
considered before this section carries the record of it.*
